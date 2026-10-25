"""Stage B: the per-case LangGraph.

    intent --(not deletion)--> not_applicable --> END
    intent --(deletion)------> identity -> link -> state -> policy -> plan -> validate --> END

Each node is a small plain function over a shared, read-only CaseContext
(evidence index, identities, global link assignment, policy). The graph makes
the flow explicit and runs many cases in parallel with graph.batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .index import EvidenceIndex
from .intent import IntentResult
from .linking import CaseLinks
from .models import Identity, Request
from .planner import plan
from .policy import Policy
from .state import resolve_state
from .validate import validate_row


@dataclass(frozen=True)
class CaseContext:
    index: EvidenceIndex
    intents: dict[str, IntentResult]
    identities: dict[str, Identity]
    links: dict[str, CaseLinks]
    policy: Policy


class CaseState(TypedDict, total=False):
    request: Request
    intent: IntentResult
    identity: Identity
    linked: dict[str, str]
    states: list
    decisions: list
    status: str
    steps: list
    errors: list
    trace: dict[str, Any]


def build_graph(ctx: CaseContext):
    def intent(s: CaseState) -> CaseState:
        return {"intent": ctx.intents[s["request"].request_text.strip()]}

    def not_applicable(s: CaseState) -> CaseState:
        return {"status": "NOT_APPLICABLE", "steps": [], "errors": []}

    def identity(s: CaseState) -> CaseState:
        return {"identity": ctx.identities[s["request"].case_id]}

    def link(s: CaseState) -> CaseState:
        return {"linked": dict(ctx.links[s["request"].case_id].resources)}

    def state(s: CaseState) -> CaseState:
        audit_at = s["request"].audit_at
        states = [st for rid in sorted(s["linked"]) if (st := resolve_state(ctx.index, rid, audit_at))]
        return {"states": states}

    def policy(s: CaseState) -> CaseState:
        audit_at = s["request"].audit_at
        return {"decisions": [d for st in s["states"] if (d := ctx.policy.decide(st, audit_at))]}

    def make_plan(s: CaseState) -> CaseState:
        status, steps = plan(s["decisions"])
        return {"status": status, "steps": steps}

    def validate(s: CaseState) -> CaseState:
        times = {fid: f.captured_at for fid, f in ctx.index.files.items()}
        return {"errors": validate_row(s["status"], s["steps"], s["request"].audit_at, times)}

    g = StateGraph(CaseState)
    for name, fn in [("intent", intent), ("not_applicable", not_applicable), ("identity", identity),
                     ("link", link), ("state", state), ("policy", policy), ("plan", make_plan),
                     ("validate", validate)]:
        g.add_node(name, fn)
    g.set_entry_point("intent")
    g.add_conditional_edges("intent", lambda s: "identity" if s["intent"].is_deletion else "not_applicable",
                            {"identity": "identity", "not_applicable": "not_applicable"})
    for a, b in [("identity", "link"), ("link", "state"), ("state", "policy"), ("policy", "plan"),
                 ("plan", "validate")]:
        g.add_edge(a, b)
    g.add_edge("validate", END)
    g.add_edge("not_applicable", END)
    return g.compile()
