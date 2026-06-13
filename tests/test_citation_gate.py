"""The citation gate is the core M2 differentiator — test it hard.

Every accepted finding MUST have a citation that re-slices raw text exactly.
Uncited / mis-cited / hallucinated findings MUST be rejected.
"""

from __future__ import annotations

from auditagent.agents import review_findings
from auditagent.agents.classifier import anchor_quote
from auditagent.anchor import fuzzy_anchor_quote
from auditagent.llm import get_reviewer
from auditagent.models import Citation, Finding, ReviewStatus

RAW = (
    "8.1 In the event of a merger, acquisition, or sale of substantially all "
    "assets, this Agreement transfers to the successor entity. "
    "Provider may terminate for any reason or no reason on 60 days notice."
)


def test_accepts_finding_with_valid_citation():
    cit = anchor_quote(RAW, "transfers to the successor entity")
    assert cit is not None
    f = Finding(clause_type="Change of Control", rationale="x", citation=cit)
    reviewed = review_findings([f], RAW, get_reviewer())
    assert reviewed[0].status == ReviewStatus.ACCEPTED


def test_rejects_uncited_finding_when_clause_absent():
    # Clause not present in RAW, no citation -> retry fails -> reject.
    f = Finding(clause_type="Non-Compete", rationale="invented", citation=None)
    reviewed = review_findings([f], RAW, get_reviewer())
    assert reviewed[0].status == ReviewStatus.REJECTED_UNCITED
    assert not reviewed[0].accepted


def test_rejects_finding_with_fabricated_offsets():
    # Citation whose offsets do NOT match the quoted text in RAW.
    bad = Citation(quote="liability shall be unlimited", start_char=0, end_char=28)
    f = Finding(clause_type="Uncapped Liability", rationale="x", citation=bad)
    reviewed = review_findings([f], RAW, get_reviewer())
    assert reviewed[0].status == ReviewStatus.REJECTED_BAD_CITATION


def test_retry_re_extracts_a_valid_citation():
    # Clause IS present, but the finding arrives uncited; the gate's retry
    # should re-extract a verifiable quote and accept it.
    f = Finding(clause_type="Change of Control", rationale="x", citation=None)
    reviewed = review_findings([f], RAW, get_reviewer())
    assert reviewed[0].status == ReviewStatus.ACCEPTED
    assert reviewed[0].retries == 1
    assert reviewed[0].finding.citation.verify_against(RAW)


def test_every_accepted_finding_is_truly_cited():
    f1 = Finding(clause_type="Termination for Convenience", rationale="x", citation=None)
    f2 = Finding(clause_type="Non-Compete", rationale="x", citation=None)  # absent
    reviewed = review_findings([f1, f2], RAW, get_reviewer())
    for r in reviewed:
        if r.accepted:
            assert r.finding.citation is not None
            assert r.finding.citation.verify_against(RAW)


# --- Gate-fix: cosmetically-off-but-real quotes must now SURVIVE the gate ---


def test_gate_accepts_fuzzy_anchored_smart_quote_finding():
    # A real LLM quote with smart quotes + collapsed whitespace. The fuzzy
    # anchorer maps it back to a real raw slice, so the gate ACCEPTS it
    # (previously this was rejected as a bad citation — the recall bug).
    cit = fuzzy_anchor_quote(RAW, "Provider may terminate for any reason or no reason")
    f = Finding(clause_type="Termination for Convenience", rationale="x", citation=cit)
    reviewed = review_findings([f], RAW, get_reviewer())
    assert reviewed[0].status == ReviewStatus.ACCEPTED
    assert reviewed[0].finding.citation.verify_against(RAW)


def test_gate_still_rejects_hallucinated_quote_after_fuzzy():
    # The fuzzy anchorer must NOT rescue a quote that isn't in the document.
    cit = fuzzy_anchor_quote(RAW, "liability shall be unlimited and uncapped")
    assert cit is None  # hallucination-rejection survives fuzzy matching
    f = Finding(clause_type="Uncapped Liability", rationale="x", citation=cit)
    reviewed = review_findings([f], RAW, get_reviewer())
    assert not reviewed[0].accepted
