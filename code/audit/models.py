"""Core data records shared by every stage."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceFile:
    file_id: str
    path: str
    origin: str
    captured_at: str


@dataclass(frozen=True)
class Observation:
    """One fact about one resource at one moment, from one piece of evidence.

    exists:   True / False / None (unknown)
    exposed:  True if the record still carries direct identifiers (name, email,
              phone, email hash); False if de-identified; None if not stated.
    active:   for data flows: enabled; for backups: restore allowed; else None.
    link_ids: normalized identifiers that tie the record to a person, e.g.
              ("email", "person@example.com"), ("user", "user_123"). Used for linking only.
    implied:  True when absence is inferred from a complete snapshot that does not
              list the resource, rather than stated explicitly.
    """

    evidence_id: str
    observed_at: str
    system_id: str
    resource_id: str
    category: str | None
    exists: bool | None
    exposed: bool | None = None
    active: bool | None = None
    link_ids: frozenset = frozenset()
    instance: str = "default"
    implied: bool = False
    details: tuple = ()


@dataclass(frozen=True)
class Coverage:
    """A snapshot that lists every record of a category in a system at a moment.

    Any known resource of that system and category that the snapshot does not
    list was absent at that moment.
    """

    evidence_id: str
    observed_at: str
    system_id: str
    category: str
    instance: str
    present: frozenset
    snapshot_rows: int = 0  # rows in the whole snapshot; 0 marks an empty, suspect capture


@dataclass(frozen=True)
class Request:
    case_id: str
    email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str


@dataclass(frozen=True)
class Identity:
    """Everything that identifies the request subject, current and historical."""

    user_id: str | None
    emails: frozenset
    phones: frozenset
    hashes: frozenset
    names: frozenset

    @property
    def strong_ids(self) -> frozenset:
        """Identifiers allowed to link a record on their own (names are excluded)."""
        ids = {("email", e) for e in self.emails} | {("phone", p) for p in self.phones}
        ids |= {("hash", h) for h in self.hashes}
        if self.user_id:
            ids.add(("user", self.user_id))
        return frozenset(ids)


@dataclass(frozen=True)
class ResourceState:
    """The state of one linked resource at audit_at, and the evidence that proves it."""

    system_id: str
    resource_id: str
    category: str | None
    exists: bool | None
    exposed: bool | None
    active: bool | None
    evidence_id: str
    observed_at: str
    via: str  # "explicit", "coverage", or "known_late" (row <= audit_at in a file captured later)
    details: tuple = ()

    @property
    def citable(self) -> bool:
        return self.via != "known_late"


@dataclass
class ParseResult:
    observations: list[Observation] = field(default_factory=list)
    coverages: list[Coverage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def extend(self, other: "ParseResult") -> None:
        self.observations.extend(other.observations)
        self.coverages.extend(other.coverages)
        self.warnings.extend(other.warnings)
