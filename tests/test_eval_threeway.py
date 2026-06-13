"""The three-way eval framing: naive B1 vs fair B1 vs gated B2.

Pins the honest comparison that makes the gate-fix story defensible:
  * `raw_quote` is captured so the eval can re-anchor the SAME model output
    exact-vs-fuzzy without extra model calls.
  * naive (exact-only) and fair (fuzzy) baselines share detections, so only
    citation-faithfulness differs — that delta IS the anchorer's contribution.
  * the report exposes a right-answer-wrong-location diagnostic.
"""

from __future__ import annotations

from auditagent.agents.classifier import anchor_quote, classify_clauses
from auditagent.anchor import fuzzy_anchor_quote
from auditagent.eval.cuad import EvalContract, GoldSpan
from auditagent.eval.runner import _findings_reanchored, render_markdown, run_ladder
from auditagent.llm import get_classifier

RAW = (
    '8.1  In the event of a "Change of Control" - including a merger or sale of '
    "substantially all assets - this Agreement transfers to the successor "
    "entity. Provider may terminate for convenience on 60 days notice. "
    "In no event shall total liability be limited or capped."
)


def test_classify_populates_raw_quote():
    findings = classify_clauses(RAW, get_classifier())
    assert findings, "deterministic classifier should detect at least one clause"
    assert all(f.raw_quote is not None for f in findings)


def test_reanchor_exact_vs_fuzzy_share_detections():
    findings = classify_clauses(RAW, get_classifier())
    naive = _findings_reanchored(findings, RAW, anchor_quote)
    fair = _findings_reanchored(findings, RAW, fuzzy_anchor_quote)
    # Same clauses flagged either way — detection must not depend on anchorer.
    assert set(naive) == set(fair)
    for key in naive:
        assert naive[key].present == fair[key].present is True


def test_fuzzy_recovers_a_span_exact_misses():
    # A model quote with a smart quote: exact anchoring returns no span,
    # fuzzy anchoring recovers one. Proves the naive→fair faithfulness lift.
    from auditagent.models import Finding

    f = Finding(
        clause_type="Change of Control",
        rationale="x",
        raw_quote="“Change of Control”",  # curly quotes vs straight in RAW
    )
    naive = _findings_reanchored([f], RAW, anchor_quote)
    fair = _findings_reanchored([f], RAW, fuzzy_anchor_quote)
    key = next(iter(naive))
    assert naive[key].span is None        # exact can't anchor the curly quote
    assert fair[key].span is not None     # fuzzy recovers it


def test_run_ladder_reports_threeway_and_diagnostic():
    i = RAW.find("this Agreement transfers to the successor entity")
    j = RAW.find("Provider may terminate for convenience")
    gold = {
        "change_of_control": [GoldSpan(i, i + 47, RAW[i : i + 47])],
        "termination_for_convenience": [GoldSpan(j, j + 38, RAW[j : j + 38])],
    }
    c = EvalContract(doc_id="d1", context=RAW, gold=gold)
    rep = run_ladder([c], provider_label="deterministic (offline)")
    assert "B1_naive" in rep
    assert "B2_wrong_location_findings" in rep
    md = render_markdown(rep)
    assert "Citation quality" in md
    assert "naive single-shot" in md
    assert "right answer, wrong location" in md
