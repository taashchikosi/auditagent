"""Durable session store — keeps HITL review sessions across a restart.

`/review*` pauses at the HITL gate and hands back a `session_id`; later
`/hitl/decide` resumes that run with the human's Approve/Escalate. In-memory
that mapping dies on restart (the paused reviewer would be unreachable). With
`AUDITAGENT_DATABASE_URL` set this store also persists each session to Postgres,
so a decision made after a restart still resolves.

How resume-after-restart works despite the closure design (see graph.py): the
only `RunContext` field the HITL pass reads is `ctx.memo`. So we persist the memo
JSON + the checkpoint `thread_id` + the audit `run_id`; on a cold decision we
rehydrate a `RunContext(memo=…)`, rebuild the graph on the **Postgres
checkpointer** (which holds the paused graph state for that thread), reattach the
original audit chain, and resume. That's a genuine cross-process resume, not just
a recorded decision.

Backend selection mirrors the audit log / checkpointer: no URL → pure in-memory
(unchanged default, what the test suite runs on); URL → in-memory fast path plus
a durable Postgres mirror.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .audit_log import _connect_postgres
from .models import RiskMemo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_sessions (
    session_id   TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    audit_run_id TEXT,
    doc_id       TEXT,
    source_name  TEXT,
    perspective  TEXT,
    memo_json    TEXT NOT NULL,
    hitl_status  TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    decided_at   TEXT
)
"""


class SessionStore:
    """In-memory by default; durable in Postgres when a URL is configured."""

    def __init__(self, database_url: str | None = None) -> None:
        self._mem: dict[str, object] = {}
        url = database_url if database_url is not None else os.getenv("AUDITAGENT_DATABASE_URL")
        self._url = (url or "").strip() or None
        if self._url:
            conn = _connect_postgres(self._url)
            try:
                with conn.cursor() as cur:
                    cur.execute(_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    @property
    def durable(self) -> bool:
        return self._url is not None

    # ---- writes -----------------------------------------------------------
    def put(self, session_id: str, session) -> None:
        """Register a paused session (live in memory; mirrored to Postgres)."""
        self._mem[session_id] = session
        if self._url:
            self._persist(session_id, session)

    def _persist(self, session_id: str, session) -> None:
        memo: RiskMemo = session.memo
        now = datetime.now(timezone.utc).isoformat()
        audit_run_id = getattr(getattr(session, "audit", None), "run_id", None)
        row = (
            session_id, session.thread_id, audit_run_id,
            memo.doc_id, memo.source_name, memo.perspective.value,
            memo.model_dump_json(), memo.hitl_status, now,
        )
        conn = _connect_postgres(self._url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO review_sessions
                        (session_id, thread_id, audit_run_id, doc_id, source_name,
                         perspective, memo_json, hitl_status, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        thread_id=EXCLUDED.thread_id,
                        audit_run_id=EXCLUDED.audit_run_id,
                        memo_json=EXCLUDED.memo_json,
                        hitl_status=EXCLUDED.hitl_status
                    """,
                    row,
                )
            conn.commit()
        finally:
            conn.close()

    def _record_decision(self, session_id: str, memo: RiskMemo) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = _connect_postgres(self._url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE review_sessions SET memo_json=%s, hitl_status=%s, "
                    "decided_at=%s WHERE session_id=%s",
                    (memo.model_dump_json(), memo.hitl_status, now, session_id),
                )
            conn.commit()
        finally:
            conn.close()

    # ---- decide -----------------------------------------------------------
    def decide(self, session_id: str, decision: str) -> RiskMemo | None:
        """Resume the paused run. Returns the updated memo, or None if unknown."""
        live = self._mem.get(session_id)
        if live is not None:
            memo = live.decide(decision)  # type: ignore[attr-defined]
            if self._url:
                self._record_decision(session_id, memo)
            return memo
        if self._url:
            return self._resume_durable(session_id, decision)
        return None

    def _resume_durable(self, session_id: str, decision: str) -> RiskMemo | None:
        row = self._fetch(session_id)
        if row is None:
            return None
        memo = RiskMemo.model_validate_json(row["memo_json"])
        if row["hitl_status"] != "pending":
            return memo  # already decided — return the stored outcome idempotently

        # Rehydrate + resume on the Postgres checkpointer (imports kept local to
        # avoid an import cycle and to keep the default path dependency-free).
        from langgraph.types import Command

        from .audit_log import AuditLog
        from .graph import RunContext, build_graph

        audit = AuditLog(run_id=row["audit_run_id"]) if row["audit_run_id"] else None
        graph, _log, ctx = build_graph(audit=audit, ctx=RunContext(memo=memo))
        config = {"configurable": {"thread_id": row["thread_id"]}}
        graph.invoke(Command(resume=decision), config)
        self._record_decision(session_id, ctx.memo)
        return ctx.memo

    def _fetch(self, session_id: str) -> dict | None:
        conn = _connect_postgres(self._url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT thread_id, audit_run_id, memo_json, hitl_status "
                    "FROM review_sessions WHERE session_id=%s",
                    (session_id,),
                )
                r = cur.fetchone()
        finally:
            conn.close()
        if r is None:
            return None
        return {
            "thread_id": r[0], "audit_run_id": r[1],
            "memo_json": r[2], "hitl_status": r[3],
        }
