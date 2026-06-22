"""SessionStore — the in-memory (default, no-DB) behaviour.

The Postgres durable path is covered in test_postgres_backend.py (skips without a
DB). This file pins the default path that ships in every build: live decide works,
and a fresh store makes NO durability claim it can't keep.
"""

from __future__ import annotations

from auditagent.data import load_sample_contract_text
from auditagent.pipeline import run_review
from auditagent.sessions import SessionStore


def _paused_session():
    raw = load_sample_contract_text()
    return run_review(raw, doc_id="mem", source_name="s.txt", perspective="buyer")


def test_in_memory_store_is_not_durable():
    store = SessionStore(database_url="")
    assert store.durable is False


def test_live_decide_resolves_the_session():
    session = _paused_session()
    assert session.memo.hitl_status == "pending"
    store = SessionStore(database_url="")
    store.put("s1", session)
    memo = store.decide("s1", "approved")
    assert memo is not None and memo.hitl_status == "approved"


def test_unknown_session_returns_none():
    # → the API turns this into a 404.
    assert SessionStore(database_url="").decide("nope", "approved") is None


def test_in_memory_has_no_cross_instance_durability():
    # Without a DB, a "restarted" (new) store legitimately can't see the session.
    session = _paused_session()
    SessionStore(database_url="").put("s2", session)
    assert SessionStore(database_url="").decide("s2", "approved") is None
