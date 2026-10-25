"""Identity resolution: request email -> user -> every current and historical identifier.

The request email may be current or historical. user_audit_log.csv records each
change of email, phone or email hash, so the full history is walked, including
chains (A -> B -> C). Email hashes are sha256(lowercase(email)), so the hash of
every known email is added: some records are keyed only by an old email's hash.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from . import normalize as nz
from .models import Identity


def email_sha256(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


class IdentityResolver:
    def __init__(self, identities: list[dict], audit_log: list[dict]):
        self.current = {r["user_id"]: r for r in identities}
        self.changes: dict[str, list[dict]] = defaultdict(list)
        for row in sorted(audit_log, key=lambda r: (r["event_time"], r["audit_id"])):
            self.changes[row["user_id"]].append(row)
        # identifier -> user, over every value ever held (used to resolve and to detect other owners)
        self.owner: dict[tuple, str] = {}
        for uid, row in self.current.items():
            for ident in self._ids_from_values(row.get("email"), row.get("phone"), row.get("email_hash")):
                self.owner.setdefault(ident, uid)
            self.owner.setdefault(("user", uid), uid)
        for uid, rows in self.changes.items():
            for row in rows:
                for value in (row["old_value"], row["new_value"]):
                    for ident in self._ids_for_field(row["field_name"], value):
                        self.owner.setdefault(ident, uid)

    @staticmethod
    def _ids_from_values(email, phone, email_hash) -> set:
        ids = set()
        if (e := nz.email(email)):
            ids |= {("email", e), ("hash", email_sha256(e))}
        if (p := nz.phone(phone)):
            ids.add(("phone", p))
        if (h := nz.email_hash(email_hash)):
            ids.add(("hash", h))
        return ids

    def _ids_for_field(self, field: str, value: str) -> set:
        field = (field or "").lower()
        if field == "email":
            return self._ids_from_values(value, None, None)
        if field == "phone":
            return self._ids_from_values(None, value, None)
        if field == "email_hash":
            return self._ids_from_values(None, None, value)
        return set()

    def user_for_email(self, email: str) -> str | None:
        e = nz.email(email)
        return self.owner.get(("email", e)) if e else None

    def owner_of(self, ident: tuple) -> str | None:
        return self.owner.get(ident)

    def resolve(self, email: str, audit_at: str) -> Identity:
        uid = self.user_for_email(email)
        emails, phones, hashes, names = set(), set(), set(), set()
        if (e := nz.email(email)):
            emails.add(e)
        if uid:
            row = self.current.get(uid, {})
            for kind, value in self._ids_from_values(row.get("email"), row.get("phone"), row.get("email_hash")):
                {"email": emails, "phone": phones, "hash": hashes}[kind].add(value)
            if (n := nz.name(row.get("name"))):
                names.add(n)
            for change in self.changes.get(uid, []):
                if change["event_time"] > audit_at:
                    continue
                for value in (change["old_value"], change["new_value"]):
                    for kind, v in self._ids_for_field(change["field_name"], value):
                        {"email": emails, "phone": phones, "hash": hashes}[kind].add(v)
        hashes |= {email_sha256(e) for e in emails}
        return Identity(uid, frozenset(emails), frozenset(phones), frozenset(hashes), frozenset(names))
