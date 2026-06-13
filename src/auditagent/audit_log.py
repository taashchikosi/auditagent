"""Immutable, hash-chained audit log — the assurance-grade decision trail.

Every agent action (parse, classify, accept/reject, checklist, HITL) is
appended as an event whose hash includes the PREVIOUS event's hash. Tampering
with any historical entry breaks every hash after it, so the log is
tamper-evident — the property Big-4 assurance work actually requires.

Backend: SQLite (default; `:memory:` for tests). The locked production target
is Postgres — the schema and chaining logic are identical; only the
connection string changes (documented in ARCHITECTURE.md).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from .models import AuditEvent

_GENESIS = "0" * 64


def _hash_event(
    seq: int, actor: str, action: str, detail: dict, timestamp: str, prev_hash: str
) -> str:
    payload = json.dumps(
        {
            "seq": seq,
            "actor": actor,
            "action": action,
            "detail": detail,
            "timestamp": timestamp,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only, hash-chained event log."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                seq INTEGER PRIMARY KEY,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _last(self) -> tuple[int, str]:
        row = self._conn.execute(
            "SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return (row[0], row[1]) if row else (0, _GENESIS)

    def append(self, actor: str, action: str, detail: dict | None = None) -> AuditEvent:
        detail = detail or {}
        last_seq, prev_hash = self._last()
        seq = last_seq + 1
        ts = datetime.now(timezone.utc).isoformat()
        h = _hash_event(seq, actor, action, detail, ts, prev_hash)
        self._conn.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)",
            (seq, actor, action, json.dumps(detail, sort_keys=True), ts, prev_hash, h),
        )
        self._conn.commit()
        return AuditEvent(
            seq=seq, actor=actor, action=action, detail=detail,
            timestamp=ts, prev_hash=prev_hash, hash=h,
        )

    def events(self) -> list[AuditEvent]:
        rows = self._conn.execute(
            "SELECT seq,actor,action,detail,timestamp,prev_hash,hash "
            "FROM audit_events ORDER BY seq"
        ).fetchall()
        return [
            AuditEvent(
                seq=r[0], actor=r[1], action=r[2], detail=json.loads(r[3]),
                timestamp=r[4], prev_hash=r[5], hash=r[6],
            )
            for r in rows
        ]

    def verify_chain(self) -> bool:
        """True iff every event's hash is valid and links to its predecessor."""
        prev_hash = _GENESIS
        for ev in self.events():
            if ev.prev_hash != prev_hash:
                return False
            recomputed = _hash_event(
                ev.seq, ev.actor, ev.action, ev.detail, ev.timestamp, ev.prev_hash
            )
            if recomputed != ev.hash:
                return False
            prev_hash = ev.hash
        return True

    def close(self) -> None:
        self._conn.close()
