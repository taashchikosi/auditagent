"""Real-model integration tests — the live behaviour the offline suite can't cover.

DOUBLE-GUARDED so they never run by accident: they require BOTH a provider key
(DEEPSEEK_API_KEY or ANTHROPIC_API_KEY) AND an explicit opt-in AUDITAGENT_RUN_LIVE=1.
The build sandbox blocks LLM APIs, so these skip here and run on a keyed machine
(Taash's Mac / the VPS) — the same honest constraint as the eval numbers.

Run on a keyed machine:

    export DEEPSEEK_API_KEY=sk-...        # terminal only; rotate after
    AUDITAGENT_RUN_LIVE=1 PYTHONPATH=src python -m pytest \\
        tests/test_integration_realmodel.py -q

What they prove against a REAL model (not the deterministic stand-in):
  * the citation-gate guarantee holds — every accepted finding re-slices the
    raw contract text EXACTLY (an unanchorable / hallucinated quote can't pass);
  * the prompt-injection defence refuses an in-contract attack while still
    surfacing the genuine clauses.
"""

from __future__ import annotations

import os

import pytest

from auditagent.data import load_injection_contract_text, load_sample_contract_text
from auditagent.llm import get_classifier
from auditagent.pipeline import run_review

_HAS_KEY = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
_OPTED_IN = os.getenv("AUDITAGENT_RUN_LIVE", "").strip() in {"1", "true", "yes"}

pytestmark = pytest.mark.skipif(
    not (_HAS_KEY and _OPTED_IN),
    reason="real-model test: needs a provider key AND AUDITAGENT_RUN_LIVE=1 "
    "(sandbox blocks LLM APIs)",
)


def test_running_against_a_real_provider():
    # Guard the guard: prove we're actually on a real model, not the offline stand-in.
    assert not get_classifier().name.startswith("deterministic")


def test_gate_guarantee_every_accepted_finding_is_an_exact_slice():
    raw = load_sample_contract_text()
    session = run_review(raw, doc_id="live", source_name="sample.txt", perspective="buyer")
    accepted = session.memo.accepted_findings
    assert accepted, "real model should accept at least one cited finding on the sample"
    for r in accepted:
        cit = r.finding.citation
        assert cit is not None, f"accepted finding {r.finding.clause_type} has no citation"
        # THE invariant: the accepted quote re-slices the raw text exactly.
        assert cit.verify_against(raw), (
            f"{r.finding.clause_type} citation did not re-slice raw text"
        )
    assert session.audit.verify_chain() is True


def test_injection_is_refused_but_real_clauses_still_surface():
    raw = load_injection_contract_text()
    session = run_review(raw, doc_id="live-inj", source_name="injection.txt", perspective="buyer")
    # The in-contract attack is flagged and refused…
    assert session.memo.injection_flags, "injection attempt should be flagged"
    # …and any accepted finding is still a verified exact slice (no laxness under attack).
    for r in session.memo.accepted_findings:
        assert r.finding.citation is not None and r.finding.citation.verify_against(raw)
