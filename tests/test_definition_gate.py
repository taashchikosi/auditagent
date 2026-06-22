"""The definitional gate — the citation gate's second half.

Every span below is the ACTUAL text DeepSeek cited in the 18-Jun live dry-run on
the two real CUAD demo contracts (Webhelp hosting, Tuniu cooperation). The gate
must REJECT the faithful-but-wrong flags and KEEP every lawyer-confirmed one, so
these tests are the regression contract for the precision fix.

Two layers are tested:
  1. `check_definition` in isolation (the rules).
  2. `review_findings` end-to-end with the gate toggled on/off (proving it is
     opt-in: OFF reproduces the committed behaviour exactly).
"""

from __future__ import annotations

import pytest

from auditagent.agents import review_findings
from auditagent.agents.classifier import anchor_quote
from auditagent.agents.definition_gate import check_definition
from auditagent.llm import get_reviewer
from auditagent.models import Finding, ReviewStatus

# --- Real dry-run citations -------------------------------------------------

# Faithful-but-WRONG (the over-flags the gate must catch):
WEBHELP_TERM_FOR_CAUSE = (
    "either party may terminate this Agreement by giving to the other party "
    "written notice of such termination upon the other party's material breach "
    "of any material term, the other party's insolvency, or the institution of "
    "any bankruptcy proceeding"
)
TUNIU_PLAIN_TERM = (
    "the term of cooperation under this Agreement shall commence from the "
    "execution date hereof and end on the expiration date of the operation "
    "term of Party B"
)
TUNIU_ANTI_ASSIGNMENT = (
    "The rights and obligations of each Party under this Agreement shall not be "
    "transferred, except for the transfer by Party B to its affiliates."
)

# Lawyer-confirmed CORRECT (the gate must NOT touch these):
WEBHELP_AUTORENEW = (
    "This Agreement shall continue in effect from the Effective Date for a one "
    "(1) year period, and thereafter shall renew automatically for successive "
    "one (1) year periods unless either party gives at least thirty (30) days "
    "prior written notice of its intent not to renew"
)
WEBHELP_COC_DEFENSIBLE = (
    "no consent shall be required for an assignment of this Agreement made "
    "pursuant to a merger, consolidation, or the acquisition of all or "
    "substantially all of the business and assets of a party"
)
TUNIU_NONCOMPETE = (
    "Party A irrevocably undertakes that, without Party B's consent, Party A "
    "shall not conduct any other business that may be competitive with Party "
    "B's business"
)
TUNIU_TERM_FOR_CONVENIENCE = (
    "Party B shall have the right to terminate this Agreement in advance "
    "without the prior written consent from Party A, by sending a written "
    "notice to Party A but Party A may not terminate or rescind this Agreement"
)
# The noisy category we deliberately DON'T gate (CUAD labels it both ways):
TUNIU_INDIRECT_EXCLUSION = (
    "neither Party shall be responsible to the other Party in respect of any "
    "indirect loss or damage caused hereunder"
)


# --- Layer 1: the rules in isolation ---------------------------------------

# Only the POLARITY rule survives. The n=102 A/B showed keyword "require_any"
# rules cost recall (change_of_control 0.808→0.673, non_compete 0.913→0.783) for
# a small precision gain — the wrong trade for a recall-first project — so they
# were pulled. The for-cause/for-convenience polarity rule was a strict win
# (precision +0.039 AND recall +0.017) and is kept.
def test_polarity_rule_rejects_for_cause_termination():
    ok, why = check_definition("Termination for Convenience", WEBHELP_TERM_FOR_CAUSE)
    assert ok is False, f"should have rejected for-cause termination: {why}"
    assert why


@pytest.mark.parametrize("clause_type,quote", [
    # The require_any rules are GONE, so these no longer reject (recall protected):
    ("Auto-renewal Notice", TUNIU_PLAIN_TERM),
    ("Change of Control", TUNIU_ANTI_ASSIGNMENT),
    # ...and the correct/ungated ones still pass:
    ("Auto-renewal Notice", WEBHELP_AUTORENEW),
    ("Change of Control", WEBHELP_COC_DEFENSIBLE),
    ("Non-Compete", TUNIU_NONCOMPETE),
    ("Termination for Convenience", TUNIU_TERM_FOR_CONVENIENCE),
    ("Uncapped Liability", TUNIU_INDIRECT_EXCLUSION),  # never gated
])
def test_keeps_everything_except_polarity_contradictions(clause_type, quote):
    ok, _ = check_definition(clause_type, quote)
    assert ok is True


def test_require_any_is_disabled_to_protect_recall():
    """Guard: re-adding a keyword require_any rule must be a deliberate, measured

    choice — not a silent edit. If these start rejecting again, someone put the
    recall-costing rules back without re-running the n=102 A/B.
    """
    from auditagent.clauses import CLAUSES_BY_KEY
    for key in ("change_of_control", "auto_renewal", "non_compete"):
        assert CLAUSES_BY_KEY[key].require_any == ()


def test_resolves_by_key_and_by_name():
    # Findings carry the display name; specs are keyed — both must resolve.
    assert check_definition("termination_for_convenience", WEBHELP_TERM_FOR_CAUSE)[0] is False
    assert check_definition("Termination for Convenience", WEBHELP_TERM_FOR_CAUSE)[0] is False


def test_termination_section_listing_both_survives():
    """A real section that offers BOTH convenience AND cause must NOT be rejected

    — the convenience signal suppresses the cause-word rule (no false negative).
    """
    both = ("Either party may terminate for convenience on 30 days notice, or "
            "immediately upon a material breach of this Agreement.")
    ok, _ = check_definition("Termination for Convenience", both)
    assert ok is True


def test_unknown_clause_passes_through():
    ok, _ = check_definition("Some Future Clause", "anything at all")
    assert ok is True


# --- Layer 2: end-to-end through the gate (opt-in proof) --------------------

def _finding(clause_type: str, raw: str) -> Finding:
    return Finding(clause_type=clause_type, rationale="x",
                   citation=anchor_quote(raw, raw))


def test_gate_off_by_default_accepts_faithful_but_wrong():
    """DEFAULT (flag unset): a faithful citation is ACCEPTED — committed

    behaviour is unchanged, so the n=102 numbers are untouched.
    """
    f = _finding("Termination for Convenience", WEBHELP_TERM_FOR_CAUSE)
    r = review_findings([f], WEBHELP_TERM_FOR_CAUSE, get_reviewer())[0]
    assert r.status == ReviewStatus.ACCEPTED


def test_gate_on_rejects_faithful_but_wrong(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_DEFINITION_GATE", "1")
    f = _finding("Termination for Convenience", WEBHELP_TERM_FOR_CAUSE)
    r = review_findings([f], WEBHELP_TERM_FOR_CAUSE, get_reviewer())[0]
    assert r.status == ReviewStatus.REJECTED_DEFINITION
    # The citation was real (faithful), so the trail says so, not "bad citation".
    assert "does not satisfy" in r.reason
    assert r.attempts[-1].action == "reject"


def test_gate_on_keeps_lawyer_confirmed(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_DEFINITION_GATE", "1")
    f = _finding("Auto-renewal Notice", WEBHELP_AUTORENEW)
    r = review_findings([f], WEBHELP_AUTORENEW, get_reviewer())[0]
    assert r.status == ReviewStatus.ACCEPTED
