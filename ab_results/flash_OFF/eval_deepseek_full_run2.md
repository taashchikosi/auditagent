# AuditAgent — CUAD eval report (102 contracts)

- **Provider:** DeepSeek (real)
- **Cost model:** `deepseek-v4-flash`

## Baseline ladder

| Baseline | macro-F1 | high-risk recall | laziness | citation faith. | $/contract | s/contract |
|---|---|---|---|---|---|---|
| **B0** RoBERTa-large (CUAD paper, NeurIPS 2021) | — | — (P@80R=0.482) | — | — | — | — |
| **B1** single-shot | 0.6718 | 0.8022 | 0.2493 | 0.7346 | 0.0017 | 8.771 |
| **B2** agent (gate) | 0.6449 | 0.7692 | 0.2793 | 0.7476 | 0.00199 | 9.885 |

**B2 − B1 high-risk recall delta: -0.033**  (macro-F1 delta: -0.027)

## Detection vs verification (separating the detector from the gate)

_B1 counts every finding (cited or not); B2-verified counts only gate-accepted ones. B2-detection is what the agent found PRE-gate — scored on the same gold. A large detection→verified gap means the gate, not the detector, is the cost; the fuzzy anchorer should shrink it._

| Stage | high-risk recall | macro-F1 | laziness |
|---|---|---|---|
| B1 single-shot (recall, any) | 0.8022 | 0.6718 | 0.2493 |
| B2 detection (pre-gate) | 0.7912 | 0.6505 | 0.2639 |
| B2 verified (post-gate) | 0.7692 | 0.6449 | 0.2793 |

**Gate gap (detection − verified high-risk recall): +0.022** — target ≈ 0 (the gate keeps what the detector found).

## Citation quality — what the anchorer and the gate each buy

_Same model, same detections (recall identical). The only thing that moves is whether each citation lands on the RIGHT text, and whether an unverifiable finding can reach output. This is the real product story._

| Pipeline | high-risk recall | citation faithfulness | every accepted finding a verifiable slice? |
|---|---|---|---|
| B1 naive single-shot (exact-anchor) | 0.8022 | 0.5067 | no |
| B1 fair single-shot (fuzzy-anchor) | 0.8022 | 0.7346 | anchored ones only |
| B2 agent (fuzzy-anchor + gate) | 0.7692 | 0.7476 | **yes — gate rejects unanchorable** |

- **Anchorer lift:** naive → fair citation faithfulness 0.5067 → 0.7346 (same detections, better-placed citations).
- **Gate guarantee:** 100% of B2's accepted findings re-slice the raw contract exactly; an unanchorable (likely hallucinated) finding cannot pass.
- **Honest limit:** 6 accepted finding(s) verify as a real slice but miss the gold clause region (right answer, wrong location). The gate checks slice-integrity, not gold-overlap — so it cannot catch these. This is the next quality target.

## Per-clause F1 (B2)

| Clause | P | R | F1 | laziness | cite-faith | support |
|---|---|---|---|---|---|---|
| change_of_control | 0.5676 | 0.8077 | 0.6667 | 0.1923 | 0.8571 | 26 |
| uncapped_liability | 0.0333 | 0.0769 | 0.0465 | 0.9231 | 0.0 | 13 |
| auto_renewal | 0.875 | 0.875 | 0.875 | 0.125 | 0.9286 | 16 |
| non_compete | 0.7 | 0.913 | 0.7925 | 0.087 | 0.9524 | 23 |
| termination_for_convenience | 0.7714 | 0.931 | 0.8438 | 0.069 | 1.0 | 29 |