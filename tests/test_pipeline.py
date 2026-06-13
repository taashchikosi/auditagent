"""End-to-end M2: the 4-agent pipeline, HITL gate, and B1 side-by-side."""

from __future__ import annotations

from auditagent.data import load_sample_contract_text
from auditagent.models import RiskLevel
from auditagent.pipeline import compare, run_review, run_single_shot

RAW = load_sample_contract_text()


def test_pipeline_accepts_only_cited_findings():
    session = run_review(
        RAW, doc_id="sample", source_name="sample.txt", perspective="buyer"
    )
    for r in session.memo.accepted_findings:
        assert r.finding.citation is not None
        assert r.finding.citation.verify_against(RAW), (
            f"{r.finding.clause_type} accepted without exact-span evidence"
        )


def test_pipeline_finds_all_five_v1_clauses():
    session = run_review(
        RAW, doc_id="sample", source_name="sample.txt", perspective="buyer"
    )
    accepted = {r.finding.clause_type for r in session.memo.accepted_findings}
    for clause in (
        "Change of Control",
        "Uncapped Liability",
        "Auto-renewal Notice",
        "Non-Compete",
        "Termination for Convenience",
    ):
        assert clause in accepted


def test_hitl_gate_pauses_then_resumes():
    session = run_review(RAW, doc_id="s", source_name="s.txt", perspective="buyer")
    assert session.memo.hitl_status == "pending"  # paused at the gate
    memo = session.decide("approved")
    assert memo.hitl_status == "approved"


def test_audit_chain_is_valid_and_tamper_evident():
    session = run_review(RAW, doc_id="s", source_name="s.txt", perspective="buyer")
    session.decide("approved")
    assert session.audit.verify_chain() is True
    events = session.audit.events()
    assert any(e.actor == "reviewer" for e in events)
    assert any(e.actor == "hitl" for e in events)
    # Tamper with history -> chain must break.
    session.audit._conn.execute(
        "UPDATE audit_events SET action='tampered' WHERE seq=1"
    )
    session.audit._conn.commit()
    assert session.audit.verify_chain() is False


def test_agent_beats_single_shot_on_the_catch():
    result = compare(RAW, perspective="buyer")
    # Agent cites all 5; B1 (lazy single-shot) misses some -> non-empty catch.
    assert result["agent"]["n"] == 5
    assert result["n_catch"] >= 1
    assert result["single_shot_b1"]["n_cited"] < 5


def test_single_shot_misses_buried_clauses():
    findings = run_single_shot(RAW, perspective="buyer")
    detected = {f.clause_type for f in findings}
    # Clauses buried late in the doc fall outside B1's context window.
    assert "Change of Control" not in detected or "Uncapped Liability" not in detected


def test_perspective_flips_severity():
    buyer = run_single_shot(RAW, perspective="buyer")
    seller = run_single_shot(RAW, perspective="seller")
    b = {f.clause_type: f.risk_level for f in buyer}
    s = {f.clause_type: f.risk_level for f in seller}
    # Termination for Convenience: HIGH for buyer, MEDIUM for seller.
    if "Termination for Convenience" in b and "Termination for Convenience" in s:
        assert b["Termination for Convenience"] == RiskLevel.HIGH
        assert s["Termination for Convenience"] == RiskLevel.MEDIUM
