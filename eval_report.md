# AuditAgent — CUAD eval report (20 contracts)

- **Provider:** Claude (real)
- **Cost model:** `claude-sonnet-4-6`

## Baseline ladder

| Baseline | macro-F1 | high-risk recall | laziness | citation faith. | $/contract | s/contract |
|---|---|---|---|---|---|---|
| **B0** RoBERTa-large (CUAD paper, NeurIPS 2021) | — | — (P@80R=0.482) | — | — | — | — |
| **B1** single-shot | 0.6911 | 0.9583 | 0.0286 | 0.8533 | 0.0426 | 19.951 |
| **B2** agent (gate) | 0.6769 | 0.9167 | 0.0619 | 0.88 | 0.04636 | 24.374 |

**B2 − B1 high-risk recall delta: -0.0417**  (macro-F1 delta: -0.0142)

## Detection vs verification (separating the detector from the gate)

_B1 counts every finding (cited or not); B2-verified counts only gate-accepted ones. B2-detection is what the agent found PRE-gate — scored on the same gold. A large detection→verified gap means the gate, not the detector, is the cost; the fuzzy anchorer should shrink it._

| Stage | high-risk recall | macro-F1 | laziness |
|---|---|---|---|
| B1 single-shot (recall, any) | 0.9583 | 0.6911 | 0.0286 |
| B2 detection (pre-gate) | 0.9583 | 0.6852 | 0.0286 |
| B2 verified (post-gate) | 0.9167 | 0.6769 | 0.0619 |

**Gate gap (detection − verified high-risk recall): +0.0417** — target ≈ 0 (the gate keeps what the detector found).

## Citation quality — what the anchorer and the gate each buy

_Same model, same detections (recall identical). The only thing that moves is whether each citation lands on the RIGHT text, and whether an unverifiable finding can reach output. This is the real product story._

| Pipeline | high-risk recall | citation faithfulness | every accepted finding a verifiable slice? |
|---|---|---|---|
| B1 naive single-shot (exact-anchor) | 0.9583 | 0.5467 | no |
| B1 fair single-shot (fuzzy-anchor) | 0.9583 | 0.8533 | anchored ones only |
| B2 agent (fuzzy-anchor + gate) | 0.9167 | 0.88 | **yes — gate rejects unanchorable** |

- **Anchorer lift:** naive → fair citation faithfulness 0.5467 → 0.8533 (same detections, better-placed citations).
- **Gate guarantee:** 100% of B2's accepted findings re-slice the raw contract exactly; an unanchorable (likely hallucinated) finding cannot pass.
- **Honest limit:** 3 accepted finding(s) verify as a real slice but miss the gold clause region (right answer, wrong location). The gate checks slice-integrity, not gold-overlap — so it cannot catch these. This is the next quality target.

## Per-clause F1 (B2)

| Clause | P | R | F1 | laziness | cite-faith | support |
|---|---|---|---|---|---|---|
| change_of_control | 0.5 | 0.8333 | 0.625 | 0.1667 | 0.8 | 6 |
| uncapped_liability | 0.3571 | 1.0 | 0.5263 | 0.0 | 0.6 | 5 |
| auto_renewal | 0.5714 | 1.0 | 0.7273 | 0.0 | 1.0 | 4 |
| non_compete | 0.75 | 0.8571 | 0.8 | 0.1429 | 1.0 | 7 |
| termination_for_convenience | 0.5455 | 1.0 | 0.7059 | 0.0 | 1.0 | 6 |