"""Immutable, hash-chained audit log — the assurance-grade decision trail.

Every agent action (parse, classify, accept/reject, checklist, HITL) is
appended as an event whose hash includes the PREVIOUS event's hash. Tampering
with any historical entry breaks every hash after it, so the log is
tamper-evident — the property Big-4 assurance work actually requires.

Backends (chosen at construction; the hash-chain logic is identical for both):

  * **SQLite** (default; `:memory:` for tests) — one isolated chain per
    `AuditLog` instance, exactly as before.
  * **Postgres** (opt-in via `AUDITAGENT_DATABASE_URL` or `database_url=`) — the
    locked production target. Many runs share one table, each an independent
    chain keyed by `run_id`; appends are serialised per run with a transaction
    advisory lock so concurrent writers can't fork the chain.

Both backends store the same columns and compute the same hash, so a chain is
portable across them and `verify_chain()` is backend-agnostic. `psycopg` is
imported lazily — the default SQLite path needs no extra dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from .models import AuditEvent

_GENESIS = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
)
"""


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
    """Append-only, hash-chained event log (SQLite default, Postgres opt-in)."""

    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        database_url: str | None = None,
        run_id: str | None = None,
    ) -> None:
        # Each log instance scopes its own chain. With SQLite :memory: the DB is
        # already per-instance; with a shared Postgres DB the run_id keeps each
        # run's chain independent.
        self.run_id = run_id or uuid.uuid4().hex
        url = database_url if database_url is not None else os.getenv("AUDITAGENT_DATABASE_URL")
        url = (url or "").strip()

        if url:
            self.backend = "postgres"
            self._pg = _connect_postgres(url)
            self._conn = None  # no sqlite handle on the Postgres path
            with self._pg.cursor() as cur:
                cur.execute(_SCHEMA)
            self._pg.commit()
        else:
            self.backend = "sqlite"
            self._pg = None
            self._conn = sqlite3.connect(db_path)
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    # ---- append (the only mutating op) ------------------------------------
    def append(self, actor: str, action: str, detail: dict | None = None) -> AuditEvent:
        detail = detail or {}
        ts = datetime.now(timezone.utc).isoformat()
        if self.backend == "postgres":
            return self._append_pg(actor, action, detail, ts)
        return self._append_sqlite(actor, action, detail, ts)

    def _build(self, last_seq: int, prev_hash: str, actor, action, detail, ts):
        seq = last_seq + 1
        h = _hash_event(seq, actor, action, detail, ts, prev_hash)
        return seq, h

    def _append_sqlite(self, actor, action, detail, ts) -> AuditEvent:
        row = self._conn.execute(
            "SELECT seq, hash FROM audit_events WHERE run_id=? ORDER BY seq DESC LIMIT 1",
            (self.run_id,),
        ).fetchone()
        last_seq, prev_hash = (row[0], row[1]) if row else (0, _GENESIS)
        seq, h = self._build(last_seq, prev_hash, actor, action, detail, ts)
        self._conn.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)",
            (self.run_id, seq, actor, action,
             json.dumps(detail, sort_keys=True), ts, prev_hash, h),
        )
        self._conn.commit()
        return AuditEvent(seq=seq, actor=actor, action=action, detail=detail,
                          timestamp=ts, prev_hash=prev_hash, hash=h)

    def _append_pg(self, actor, action, detail, ts) -> AuditEvent:
        # Serialise appends for this run so two writers can't both read the same
        # "last" row and fork the chain. The advisory lock is released on commit.
        with self._pg.transaction():
            with self._pg.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.run_id,))
                cur.execute(
                    "SELECT seq, hash FROM audit_events WHERE run_id=%s "
                    "ORDER BY seq DESC LIMIT 1",
                    (self.run_id,),
                )
                row = cur.fetchone()
                last_seq, prev_hash = (row[0], row[1]) if row else (0, _GENESIS)
                seq, h = self._build(last_seq, prev_hash, actor, action, detail, ts)
                cur.execute(
                    "INSERT INTO audit_events VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (self.run_id, seq, actor, action,
                     json.dumps(detail, sort_keys=True), ts, prev_hash, h),
                )
        return AuditEvent(seq=seq, actor=actor, action=action, detail=detail,
                          timestamp=ts, prev_hash=prev_hash, hash=h)

    # ---- reads ------------------------------------------------------------
    def events(self) -> list[AuditEvent]:
        sql = (
            "SELECT seq,actor,action,detail,timestamp,prev_hash,hash "
            "FROM audit_events WHERE run_id={ph} ORDER BY seq"
        )
        if self.backend == "postgres":
            with self._pg.cursor() as cur:
                cur.execute(sql.format(ph="%s"), (self.run_id,))
                rows = cur.fetchall()
        else:
            rows = self._conn.execute(sql.format(ph="?"), (self.run_id,)).fetchall()
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
        if self._conn is not None:
            self._conn.close()
        if self._pg is not None:
            self._pg.close()


def _connect_postgres(url: str):
    """Open a psycopg connection. Imported lazily so the SQLite path is dep-free."""
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised on Mac/prod
        raise RuntimeError(
            "AUDITAGENT_DATABASE_URL is set but the 'psycopg' driver is not "
            "installed. Install the Postgres extra:  pip install '.[postgres]'"
        ) from exc
    return psycopg.connect(url, autocommit=False)
