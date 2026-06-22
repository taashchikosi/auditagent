"""Postgres-backed audit log — durability, run isolation, tamper-evidence.

CI-safe: these skip cleanly unless AUDITAGENT_TEST_DATABASE_URL points at a
reachable Postgres (the default SQLite path is covered by test_pipeline /
test_injection). A SEPARATE var from the production AUDITAGENT_DATABASE_URL is
used on purpose — so setting it for these tests never silently flips the rest of
the suite (e.g. the SQLite tamper test in test_pipeline) onto Postgres. The URL
is passed to AuditLog explicitly. Run locally with, e.g.:

    docker run -d --name auditagent-pg -e POSTGRES_PASSWORD=audit \\
        -e POSTGRES_USER=audit -e POSTGRES_DB=audit \\
        -p 127.0.0.1:5435:5432 postgres:16
    AUDITAGENT_TEST_DATABASE_URL=postgresql://audit:audit@127.0.0.1:5435/audit \\
        PYTHONPATH=src python -m pytest tests/test_postgres_backend.py -q
"""

from __future__ import annotations

import os
import uuid

import pytest

from auditagent.audit_log import AuditLog

_URL = os.getenv("AUDITAGENT_TEST_DATABASE_URL", "").strip()


def _reachable(url: str) -> bool:
    try:
        import psycopg
    except ModuleNotFoundError:
        return False
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (_URL and _URL.startswith(("postgres://", "postgresql://")) and _reachable(_URL)),
    reason="no reachable AUDITAGENT_DATABASE_URL (Postgres-only test)",
)


def _fresh() -> AuditLog:
    return AuditLog(database_url=_URL, run_id=uuid.uuid4().hex)


def test_postgres_backend_selected():
    log = _fresh()
    try:
        assert log.backend == "postgres"
    finally:
        log.close()


def test_append_and_verify_chain():
    log = _fresh()
    try:
        log.append("extractor", "parsed", {"n": 1})
        log.append("reviewer", "gate_decision", {"status": "accepted"})
        evs = log.events()
        assert [e.seq for e in evs] == [1, 2]
        assert evs[1].prev_hash == evs[0].hash
        assert log.verify_chain() is True
    finally:
        log.close()


def test_durable_across_new_connection():
    """The whole point of M4: a fresh AuditLog (new connection — a 'restart')

    reading the same run_id sees the persisted chain. This fails on the
    in-memory backend, which is exactly why durability needs Postgres.
    """
    run_id = uuid.uuid4().hex
    first = AuditLog(database_url=_URL, run_id=run_id)
    try:
        first.append("hitl", "decision", {"status": "approved"})
    finally:
        first.close()

    second = AuditLog(database_url=_URL, run_id=run_id)
    try:
        evs = second.events()
        assert len(evs) == 1
        assert evs[0].actor == "hitl"
        assert second.verify_chain() is True
    finally:
        second.close()


def test_runs_are_isolated_chains():
    a, b = _fresh(), _fresh()
    try:
        a.append("x", "a1", {})
        a.append("x", "a2", {})
        b.append("y", "b1", {})
        # each run is its own chain starting at seq 1 — they don't interleave
        assert [e.seq for e in a.events()] == [1, 2]
        assert [e.seq for e in b.events()] == [1]
        assert a.verify_chain() and b.verify_chain()
    finally:
        a.close()
        b.close()


def test_checkpointer_hitl_resume_on_postgres(monkeypatch):
    """End-to-end: the graph compiles on the Postgres checkpointer, runs to the

    HITL interrupt (state checkpointed to Postgres), and resumes on decide().
    Uses the deterministic offline provider — no model/key needed.
    """
    monkeypatch.setenv("AUDITAGENT_DATABASE_URL", _URL)
    from auditagent.data import load_sample_contract_text
    from auditagent.pipeline import run_review

    raw = load_sample_contract_text()
    session = run_review(raw, doc_id="pg-hitl", source_name="s.txt", perspective="buyer")
    # paused at the HITL gate, with the audit chain on Postgres
    assert session.memo.hitl_status == "pending"
    assert session.audit.backend == "postgres"
    assert session.audit.verify_chain() is True
    # resume past the interrupt, reading the checkpoint back from Postgres
    memo = session.decide("approved")
    assert memo.hitl_status == "approved"


def test_durable_session_resume_after_restart(monkeypatch):
    """The M4 payoff: a session paused at HITL is resumable from a *fresh*

    process. We pause a real run, persist it, then a brand-new SessionStore
    (empty memory, same DB — i.e. a restart) rehydrates it from Postgres and
    resumes the graph on the Postgres checkpointer.
    """
    monkeypatch.setenv("AUDITAGENT_DATABASE_URL", _URL)
    from auditagent.data import load_sample_contract_text
    from auditagent.pipeline import run_review
    from auditagent.sessions import SessionStore

    raw = load_sample_contract_text()
    session = run_review(raw, doc_id="durable", source_name="s.txt", perspective="buyer")
    assert session.memo.hitl_status == "pending"

    store1 = SessionStore(database_url=_URL)
    assert store1.durable is True
    store1.put("sess-durable-1", session)

    # Simulate a restart: a new store with EMPTY memory, pointing at the same DB.
    store2 = SessionStore(database_url=_URL)
    assert "sess-durable-1" not in store2._mem
    memo = store2.decide("sess-durable-1", "approved")
    assert memo is not None
    assert memo.hitl_status == "approved"

    # Re-deciding is idempotent (returns the stored outcome, no crash).
    assert store2.decide("sess-durable-1", "approved").hitl_status == "approved"
    # Unknown session → None (the API turns this into a 404).
    assert store2.decide("does-not-exist", "approved") is None


def test_tamper_breaks_chain():
    import psycopg

    run_id = uuid.uuid4().hex
    log = AuditLog(database_url=_URL, run_id=run_id)
    try:
        log.append("extractor", "parsed", {"n": 1})
        log.append("reviewer", "gate_decision", {"status": "accepted"})
        assert log.verify_chain() is True
        # Mutate history out-of-band (simulating tampering) → chain must break.
        with psycopg.connect(_URL) as conn:
            conn.execute(
                "UPDATE audit_events SET action='tampered' WHERE run_id=%s AND seq=1",
                (run_id,),
            )
            conn.commit()
        assert log.verify_chain() is False
    finally:
        log.close()
