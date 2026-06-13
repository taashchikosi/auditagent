"""Baseline-ladder runner — B0 (published) · B1 (single-shot) · B2 (agent).

Runs B1 and B2 over a CUAD sample, scores both against gold, and emits a
report with the ladder, per-clause F1, and measured cost+latency. The headline
signal is the B2 − B1 delta on high-risk-clause recall: does the agent's
citation gate + recall-recovery actually beat single-shot prompting?

Provider-agnostic: deterministic offline (validates the harness + a floor),
or real DeepSeek/Claude when API keys are set (the real numbers).
"""

from __future__ import annotations

import time

from ..agents.classifier import anchor_quote  # exact-only (naive baseline)
from ..anchor import fuzzy_anchor_quote
from ..clauses import CLAUSES_BY_KEY
from ..llm.usage import USAGE
from ..pipeline import run_review, run_single_shot
from .cuad import EvalContract
from .scorer import EvalReport, PredItem, score_predictions

# B0 — published CUAD reference points (NOT re-run; cited from the literature).
B0_REFERENCE = {
    "name": "RoBERTa-large (CUAD paper, NeurIPS 2021)",
    "p_at_80r": 0.482,  # DeBERTa-xlarge ~0.440
    "note": "fine-tuned encoder baseline; we beat or contextualise this bar",
}

_NAME_TO_KEY = {spec.name: key for key, spec in CLAUSES_BY_KEY.items()}


def _findings_to_predictions(findings, *, accepted_only: bool) -> dict[str, PredItem]:
    preds: dict[str, PredItem] = {}
    for f in findings:
        key = _NAME_TO_KEY.get(f.clause_type)
        if key is None:
            continue
        cit = f.citation
        preds[key] = PredItem(
            present=True,
            span=(cit.start_char, cit.end_char) if cit else None,
            confidence=f.confidence,
        )
    return preds


def _findings_reanchored(findings, raw_text, anchorer) -> dict[str, PredItem]:
    """Score the SAME model findings under a chosen anchorer (exact vs fuzzy).

    Detection (`present`) is unchanged — the model flagged the clause either way.
    Only the SPAN differs, so only citation-faithfulness moves. That isolates
    'did anchoring put the citation on the right text?' from 'did we detect it?'.
    """
    preds: dict[str, PredItem] = {}
    for f in findings:
        key = _NAME_TO_KEY.get(f.clause_type)
        if key is None:
            continue
        quote = f.raw_quote or (f.citation.quote if f.citation else None)
        cit = anchorer(raw_text, quote) if quote else None
        preds[key] = PredItem(
            present=True,
            span=(cit.start_char, cit.end_char) if cit else None,
            confidence=f.confidence,
        )
    return preds


def run_b1(contracts: list[EvalContract]) -> tuple[dict, dict, float]:
    """B1: single lazy pass, no gate.

    Scored TWO ways from the SAME model samples (no extra calls):
      * naive  — exact-substring anchoring only (what most demos ship).
      * fair   — fuzzy-but-verified anchoring (a strong, honest baseline).
    Same detections, so recall/F1 are identical; only citation-faithfulness
    differs — which is exactly the anchorer's contribution, made visible.
    Returns (naive_preds, fair_preds, seconds).
    """
    naive: dict[str, dict[str, PredItem]] = {}
    fair: dict[str, dict[str, PredItem]] = {}
    t0 = time.perf_counter()
    for c in contracts:
        findings = run_single_shot(c.context, perspective="neutral")
        naive[c.doc_id] = _findings_reanchored(findings, c.context, anchor_quote)
        fair[c.doc_id] = _findings_reanchored(findings, c.context, fuzzy_anchor_quote)
    return naive, fair, time.perf_counter() - t0


def run_b2(contracts: list[EvalContract]) -> tuple[dict, dict, float]:
    """B2: full agent pipeline.

    Returns THREE things so detection and verification are scored separately:
      * verified_preds  — only citation-gate-accepted findings (the product
                          claim: "found it AND proved it").
      * detection_preds — ALL classifier findings, pre-gate (did the agent
                          detect the clause at all, before the gate ruled?).
    Comparing the two isolates the gate's effect: if detection recall is high
    but verified recall is low, the gate — not the detector — is the cost.
    The fuzzy anchorer is meant to collapse the gap between them.
    """
    verified: dict[str, dict[str, PredItem]] = {}
    detection: dict[str, dict[str, PredItem]] = {}
    t0 = time.perf_counter()
    for c in contracts:
        session = run_review(
            c.context, doc_id=c.doc_id, source_name=c.doc_id, perspective="neutral"
        )
        accepted = [r.finding for r in session.memo.accepted_findings]
        pre_gate = [r.finding for r in session.memo.findings]  # every detection
        verified[c.doc_id] = _findings_to_predictions(accepted, accepted_only=True)
        detection[c.doc_id] = _findings_to_predictions(pre_gate, accepted_only=False)
    return verified, detection, time.perf_counter() - t0


def run_ladder(
    contracts: list[EvalContract],
    *,
    model_name: str = "deepseek-v4-flash",
    provider_label: str = "deterministic (offline)",
) -> dict:
    """Run B1 + B2, score both, return the full ladder report."""
    USAGE.reset()
    b1_naive_preds, b1_fair_preds, b1_secs = run_b1(contracts)
    b1_cost = USAGE.cost_usd(model_name)
    b1_tokens = USAGE.prompt_tokens + USAGE.completion_tokens

    USAGE.reset()
    b2_verified_preds, b2_detection_preds, b2_secs = run_b2(contracts)
    b2_cost = USAGE.cost_usd(model_name)
    b2_tokens = USAGE.prompt_tokens + USAGE.completion_tokens

    # B1 reported = the FAIR (fuzzy-anchored) baseline — the honest strong bar.
    # B1 naive (exact-only) is shown alongside to expose the anchorer's lift.
    b1: EvalReport = score_predictions(contracts, b1_fair_preds)
    b1_naive: EvalReport = score_predictions(contracts, b1_naive_preds)
    b2: EvalReport = score_predictions(contracts, b2_verified_preds)
    b2_detect: EvalReport = score_predictions(contracts, b2_detection_preds)
    # Right-answer-wrong-location: accepted findings that verify as a real slice
    # but miss the gold clause region. The gate guarantees slice-integrity, NOT
    # gold-overlap, so it cannot catch these — report them honestly.
    b2_wrong_location = sum(s.tp - s.faithful for s in b2.per_clause.values())
    n = len(contracts)

    label = provider_label.lower()
    is_real = any(k in label for k in ("real", "deepseek", "claude", "anthropic"))
    return {
        "n_contracts": n,
        "model": model_name,
        "provider": provider_label,
        "numbers_are_real_model": is_real,
        "B0": B0_REFERENCE,
        "B1": {
            **b1.to_dict(),
            "sec_per_contract": round(b1_secs / n, 3) if n else 0.0,
            "cost_usd_total": round(b1_cost, 4),
            "cost_usd_per_contract": round(b1_cost / n, 5) if n else 0.0,
            "tokens": b1_tokens,
        },
        "B2": {
            **b2.to_dict(),
            "sec_per_contract": round(b2_secs / n, 3) if n else 0.0,
            "cost_usd_total": round(b2_cost, 4),
            "cost_usd_per_contract": round(b2_cost / n, 5) if n else 0.0,
            "tokens": b2_tokens,
        },
        # Pre-gate detection: did the agent FIND the clause, before the gate
        # decided whether it could prove it? Scored on the same gold labels.
        "B2_detection": {
            "high_risk_recall": round(b2_detect.high_risk_recall, 4),
            "macro_f1": round(b2_detect.macro_f1, 4),
            "mean_laziness_rate": round(b2_detect.mean_laziness, 4),
        },
        # Naive single-shot: same detections as B1, exact-only anchoring. Its
        # lower faithfulness is the gap the fuzzy anchorer closes.
        "B1_naive": {
            "high_risk_recall": round(b1_naive.high_risk_recall, 4),
            "macro_f1": round(b1_naive.macro_f1, 4),
            "mean_citation_faithfulness": round(b1_naive.mean_citation_faithfulness, 4),
        },
        "B2_wrong_location_findings": b2_wrong_location,
        "delta_high_risk_recall_B2_minus_B1": round(
            b2.high_risk_recall - b1.high_risk_recall, 4
        ),
        "delta_macro_f1_B2_minus_B1": round(b2.macro_f1 - b1.macro_f1, 4),
        # Gate gap: detection recall minus verified recall. The fuzzy-anchor
        # fix should drive this toward zero (the gate stops dropping findings
        # it actually detected).
        "gate_gap_high_risk_recall": round(
            b2_detect.high_risk_recall - b2.high_risk_recall, 4
        ),
    }


def render_markdown(report: dict) -> str:
    """Human-readable baseline-ladder report (for the README / CI artifact)."""
    b1, b2 = report["B1"], report["B2"]
    lines = [
        f"# AuditAgent — CUAD eval report ({report['n_contracts']} contracts)",
        "",
        f"- **Provider:** {report['provider']}"
        + ("" if report["numbers_are_real_model"] else "  ⚠️"),
        f"- **Cost model:** `{report['model']}`",
    ]
    if not report["numbers_are_real_model"]:
        lines += [
            "",
            "> ⚠️ **These are STAND-IN numbers, not the real model.** Detection here "
            "uses a keyword detector, and the B1 baseline truncates context — which "
            "*exaggerates* the B2−B1 gap. They prove the harness measures correctly "
            "against real CUAD gold labels; they are NOT a benchmark result to "
            "publish. Run `make eval` with `DEEPSEEK_API_KEY` set for the real "
            "B1/B2 numbers.",
        ]
    lines += [
        "",
        "## Baseline ladder",
        "",
        "| Baseline | macro-F1 | high-risk recall | laziness | citation faith. | $/contract | s/contract |",
        "|---|---|---|---|---|---|---|",
        f"| **B0** {report['B0']['name']} | — | — (P@80R={report['B0']['p_at_80r']}) | — | — | — | — |",
        f"| **B1** single-shot | {b1['macro_f1']} | {b1['high_risk_recall']} | "
        f"{b1['mean_laziness_rate']} | {b1['mean_citation_faithfulness']} | "
        f"{b1['cost_usd_per_contract']} | {b1['sec_per_contract']} |",
        f"| **B2** agent (gate) | {b2['macro_f1']} | {b2['high_risk_recall']} | "
        f"{b2['mean_laziness_rate']} | {b2['mean_citation_faithfulness']} | "
        f"{b2['cost_usd_per_contract']} | {b2['sec_per_contract']} |",
        "",
        f"**B2 − B1 high-risk recall delta: {report['delta_high_risk_recall_B2_minus_B1']:+}**  "
        f"(macro-F1 delta: {report['delta_macro_f1_B2_minus_B1']:+})",
        "",
        "## Detection vs verification (separating the detector from the gate)",
        "",
        "_B1 counts every finding (cited or not); B2-verified counts only "
        "gate-accepted ones. B2-detection is what the agent found PRE-gate — "
        "scored on the same gold. A large detection→verified gap means the gate, "
        "not the detector, is the cost; the fuzzy anchorer should shrink it._",
        "",
        "| Stage | high-risk recall | macro-F1 | laziness |",
        "|---|---|---|---|",
        f"| B1 single-shot (recall, any) | {b1['high_risk_recall']} | "
        f"{b1['macro_f1']} | {b1['mean_laziness_rate']} |",
        f"| B2 detection (pre-gate) | {report['B2_detection']['high_risk_recall']} | "
        f"{report['B2_detection']['macro_f1']} | "
        f"{report['B2_detection']['mean_laziness_rate']} |",
        f"| B2 verified (post-gate) | {b2['high_risk_recall']} | "
        f"{b2['macro_f1']} | {b2['mean_laziness_rate']} |",
        "",
        f"**Gate gap (detection − verified high-risk recall): "
        f"{report['gate_gap_high_risk_recall']:+}** "
        "— target ≈ 0 (the gate keeps what the detector found).",
        "",
        "## Citation quality — what the anchorer and the gate each buy",
        "",
        "_Same model, same detections (recall identical). The only thing that "
        "moves is whether each citation lands on the RIGHT text, and whether an "
        "unverifiable finding can reach output. This is the real product story._",
        "",
        "| Pipeline | high-risk recall | citation faithfulness | every accepted finding a verifiable slice? |",
        "|---|---|---|---|",
        f"| B1 naive single-shot (exact-anchor) | {report['B1_naive']['high_risk_recall']} | "
        f"{report['B1_naive']['mean_citation_faithfulness']} | no |",
        f"| B1 fair single-shot (fuzzy-anchor) | {b1['high_risk_recall']} | "
        f"{b1['mean_citation_faithfulness']} | anchored ones only |",
        f"| B2 agent (fuzzy-anchor + gate) | {b2['high_risk_recall']} | "
        f"{b2['mean_citation_faithfulness']} | **yes — gate rejects unanchorable** |",
        "",
        f"- **Anchorer lift:** naive → fair citation faithfulness "
        f"{report['B1_naive']['mean_citation_faithfulness']} → "
        f"{b1['mean_citation_faithfulness']} (same detections, better-placed citations).",
        f"- **Gate guarantee:** 100% of B2's accepted findings re-slice the raw "
        "contract exactly; an unanchorable (likely hallucinated) finding cannot pass.",
        f"- **Honest limit:** {report['B2_wrong_location_findings']} accepted "
        "finding(s) verify as a real slice but miss the gold clause region "
        "(right answer, wrong location). The gate checks slice-integrity, not "
        "gold-overlap — so it cannot catch these. This is the next quality target.",
        "",
        "## Per-clause F1 (B2)",
        "",
        "| Clause | P | R | F1 | laziness | cite-faith | support |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, m in b2["per_clause"].items():
        lines.append(
            f"| {key} | {m['precision']} | {m['recall']} | {m['f1']} | "
            f"{m['laziness_rate']} | {m['citation_faithfulness']} | {m['support']} |"
        )
    return "\n".join(lines)
