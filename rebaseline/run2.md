# AuditAgent — CUAD eval report (102 contracts)

- **Provider:** DeepSeek (real)
- **Cost model:** `deepseek-v4-flash`

## Baseline ladder

| Baseline | macro-F1 | high-risk recall | laziness | citation faith. | $/contract | s/contract |
|---|---|---|---|---|---|---|
| **B0** RoBERTa-large (CUAD paper, NeurIPS 2021) | — | — (P@80R=0.482) | — | — | — | — |
| **B1** single-shot | 0.6773 | 0.8132 | 0.2406 | 0.8403 | 0.00171 | 9.257 |
| **B2** agent (gate) | 0.6779 | 0.8022 | 0.2503 | 0.8726 | 0.00186 | 9.921 |

**B2 − B1 high-risk recall delta: -0.011**  (macro-F1 delta: +0.0006)

## Detection vs verification (separating the detector from the gate)

_B1 counts every finding (cited or not); B2-verified counts only gate-accepted ones. B2-detection is what the agent found PRE-gate — scored on the same gold. A large detection→verified gap means the gate, not the detector, is the cost; the fuzzy anchorer should shrink it._

| Stage | high-risk recall | macro-F1 | laziness |
|---|---|---|---|
| B1 single-shot (recall, any) | 0.8132 | 0.6773 | 0.2406 |
| B2 detection (pre-gate) | 0.8132 | 0.6821 | 0.2416 |
| B2 verified (post-gate) | 0.8022 | 0.6779 | 0.2503 |

**Gate gap (detection − verified high-risk recall): +0.011** — target ≈ 0 (the gate keeps what the detector found).

## Citation quality — what the anchorer and the gate each buy

_Same model, same detections (recall identical). The only thing that moves is whether each citation lands on the RIGHT text, and whether an unverifiable finding can reach output. This is the real product story._

| Pipeline | high-risk recall | citation faithfulness | every accepted finding a verifiable slice? |
|---|---|---|---|
| B1 naive single-shot (exact-anchor) | 0.8132 | 0.5 | no |
| B1 fair single-shot (fuzzy-anchor) | 0.8132 | 0.8403 | anchored ones only |
| B2 agent (fuzzy-anchor + gate) | 0.8022 | 0.8726 | **yes — gate rejects unanchorable** |

- **Anchorer lift:** naive → fair citation faithfulness 0.5 → 0.8403 (same detections, better-placed citations).
- **Gate guarantee:** 100% of B2's accepted findings re-slice the raw contract exactly; an unanchorable (likely hallucinated) finding cannot pass.
- **Honest limit:** 4 accepted finding(s) verify as a real slice but miss the gold clause region (right answer, wrong location). The gate checks slice-integrity, not gold-overlap — so it cannot catch these. This is the next quality target.

## Per-clause F1 (B2)

| Clause | P | R | F1 | laziness | cite-faith | support |
|---|---|---|---|---|---|---|
| change_of_control | 0.6216 | 0.8846 | 0.7302 | 0.1154 | 0.913 | 26 |
| uncapped_liability | 0.069 | 0.1538 | 0.0952 | 0.8462 | 0.5 | 13 |
| auto_renewal | 0.875 | 0.875 | 0.875 | 0.125 | 1.0 | 16 |
| non_compete | 0.7407 | 0.8696 | 0.8 | 0.1304 | 0.95 | 23 |
| termination_for_convenience | 0.8235 | 0.9655 | 0.8889 | 0.0345 | 1.0 | 29 |