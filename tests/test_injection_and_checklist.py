"""Injection resistance (#15) + deterministic checklist engine + audit log."""

from __future__ import annotations

from auditagent.audit_log import AuditLog
from auditagent.checklist import run_checklist
from auditagent.data import load_injection_contract_text
from auditagent.injection import detect_injections, injection_summary
from auditagent.models import (
    Finding,
    ReviewedFinding,
    ReviewStatus,
)
from auditagent.pipeline import run_review


def test_detects_injection_attempts():
    raw = load_injection_contract_text()
    flags = detect_injections(raw)
    assert len(flags) >= 1
    # Flags carry exact offsets so the attack itself is citable.
    for f in flags:
        assert raw[f["start_char"] : f["end_char"]] == f["match"]


def test_agent_refuses_injection_but_still_reports_real_clauses():
    raw = load_injection_contract_text()
    session = run_review(raw, doc_id="inj", source_name="inj.txt", perspective="buyer")
    # The injection said "mark low-risk / do not flag" — agent must NOT comply.
    assert len(session.memo.injection_flags) >= 1
    accepted = {r.finding.clause_type for r in session.memo.accepted_findings}
    assert "Change of Control" in accepted  # real risk still reported
    assert "Termination for Convenience" in accepted


def test_injection_summary_is_human_readable():
    raw = load_injection_contract_text()
    summary = injection_summary(raw)
    assert summary and all("refused" in s for s in summary)


def test_checklist_flags_missing_required_clause():
    # Only one accepted finding -> other required clauses must show as failures.
    f = ReviewedFinding(
        finding=Finding(clause_type="Change of Control", rationale="x"),
        status=ReviewStatus.ACCEPTED,
    )
    items = run_checklist([f])
    failures = [c.clause_type for c in items if not c.passed]
    assert "Uncapped Liability" in failures  # required, not present
    cof = next(c for c in items if c.clause_type == "Change of Control")
    assert cof.passed and cof.present


def test_audit_log_hash_chain():
    log = AuditLog()
    log.append("extractor", "parsed", {"n": 1})
    log.append("reviewer", "gate_decision", {"status": "accepted"})
    assert log.verify_chain() is True
    assert len(log.events()) == 2
    # Each event links to the previous hash.
    evs = log.events()
    assert evs[1].prev_hash == evs[0].hash
