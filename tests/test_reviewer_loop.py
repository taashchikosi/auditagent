"""The citation gate's verify → reflect → retry loop is now explicit and

records a per-attempt trace. These tests prove two things:
  1. The trace faithfully reflects what the loop did (accept / retry / reject).
  2. Recording the trace does NOT change any accept/reject OUTCOME — the
     verdicts and `retries` counts are identical to the pre-refactor gate,
     so the committed CUAD eval numbers are unaffected.
"""

from __future__ import annotations

from auditagent.agents import review_findings
from auditagent.agents.classifier import anchor_quote
from auditagent.llm import get_reviewer
from auditagent.models import Citation, Finding, ReviewStatus

RAW = (
    "8.1 In the event of a merger, acquisition, or sale of substantially all "
    "assets, this Agreement transfers to the successor entity. "
    "Provider may terminate for any reason or no reason on 60 days notice."
)


def test_accept_on_first_verify_records_single_attempt():
    cit = anchor_quote(RAW, "transfers to the successor entity")
    f = Finding(clause_type="Change of Control", rationale="x", citation=cit)
    r = review_findings([f], RAW, get_reviewer())[0]
    assert r.status == ReviewStatus.ACCEPTED
    assert r.retries == 0
    assert [a.outcome for a in r.attempts] == ["verified"]
    assert r.attempts[0].action == "verify"


def test_accept_on_retry_records_reflect_then_reextract():
    # Present clause, but arrives uncited -> loop reflects and re-extracts.
    f = Finding(clause_type="Change of Control", rationale="x", citation=None)
    r = review_findings([f], RAW, get_reviewer())[0]
    assert r.status == ReviewStatus.ACCEPTED
    assert r.retries == 1
    outcomes = [a.outcome for a in r.attempts]
    assert outcomes[0] == "no_citation"          # attempt 0 failed
    assert "re_extracted" in outcomes            # it reflected
    assert outcomes[-1] == "verified"            # retry succeeded
    assert r.finding.citation.verify_against(RAW)


def test_reject_records_failed_verify_then_rejected():
    # Absent clause, uncited -> retry can't find it -> rejected.
    f = Finding(clause_type="Non-Compete", rationale="invented", citation=None)
    r = review_findings([f], RAW, get_reviewer())[0]
    assert r.status == ReviewStatus.REJECTED_UNCITED
    outcomes = [a.outcome for a in r.attempts]
    assert outcomes[0] == "no_citation"
    assert outcomes[-1] == "rejected"
    assert r.attempts[-1].action == "reject"


def test_bad_citation_rejected_and_traced():
    bad = Citation(quote="liability shall be unlimited", start_char=0, end_char=28)
    f = Finding(clause_type="Uncapped Liability", rationale="x", citation=bad)
    r = review_findings([f], RAW, get_reviewer())[0]
    assert r.status == ReviewStatus.REJECTED_BAD_CITATION
    assert r.attempts[0].outcome == "anchor_failed"
    assert r.attempts[-1].outcome == "rejected"


def test_outcomes_unchanged_regression():
    """The verdicts + retry counts must match the original straight-line gate

    exactly (this is the eval-number safety net). Mixed batch of every case.
    """
    cited = Finding(
        clause_type="Change of Control", rationale="x",
        citation=anchor_quote(RAW, "transfers to the successor entity"),
    )
    retry_ok = Finding(clause_type="Termination for Convenience", rationale="x", citation=None)
    absent = Finding(clause_type="Non-Compete", rationale="x", citation=None)
    bad = Finding(
        clause_type="Uncapped Liability", rationale="x",
        citation=Citation(quote="liability shall be unlimited", start_char=0, end_char=28),
    )
    reviewed = review_findings([cited, retry_ok, absent, bad], RAW, get_reviewer())
    got = [(r.status, r.retries) for r in reviewed]
    assert got == [
        (ReviewStatus.ACCEPTED, 0),
        (ReviewStatus.ACCEPTED, 1),
        (ReviewStatus.REJECTED_UNCITED, 1),
        (ReviewStatus.REJECTED_BAD_CITATION, 1),
    ]
    # Every accepted finding is still a verified exact slice.
    for r in reviewed:
        if r.accepted:
            assert r.finding.citation.verify_against(RAW)


def test_max_retries_zero_skips_loop_and_still_rejects():
    f = Finding(clause_type="Change of Control", rationale="x", citation=None)
    r = review_findings([f], RAW, get_reviewer(), max_retries=0)[0]
    # With no retry budget a present-but-uncited finding is rejected, retries=0.
    assert r.status == ReviewStatus.REJECTED_UNCITED
    assert r.retries == 0
    assert all(a.action != "re_extract" for a in r.attempts)
