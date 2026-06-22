# AuditAgent — CUAD eval report (102 contracts)

- **Provider:** DeepSeek (real)
- **Cost model:** `deepseek-v4-flash`

## Baseline ladder

| Baseline | macro-F1 | high-risk recall | laziness | citation faith. | $/contract | s/contract |
|---|---|---|---|---|---|---|
| **B0** RoBERTa-large (CUAD paper, NeurIPS 2021) | — | — (P@80R=0.482) | — | — | — | — |
| **B1** single-shot | 0.6765 | 0.8132 | 0.2483 | 0.7126 | 0.0017 | 9.012 |
| **B2** agent (gate) | 0.6654 | 0.7363 | 0.2908 | 0.9333 | 0.00189 | 10.168 |

**B2 − B1 high-risk recall delta: -0.0769**  (macro-F1 delta: -0.0112)

## Detection vs verification (separating the detector from the gate)

_B1 counts every finding (cited or not); B2-verified counts only gate-accepted ones. B2-detection is what the agent found PRE-gate — scored on the same gold. A large detection→verified gap means the gate, not the detector, is the cost; the fuzzy anchorer should shrink it._

| Stage | high-risk recall | macro-F1 | laziness |
|---|---|---|---|
| B1 single-shot (recall, any) | 0.8132 | 0.6765 | 0.2483 |
| B2 detection (pre-gate) | 0.8352 | 0.6687 | 0.2185 |
| B2 verified (post-gate) | 0.7363 | 0.6654 | 0.2908 |

**Gate gap (detection − verified high-risk recall): +0.0989** — target ≈ 0 (the gate keeps what the detector found).

## Citation quality — what the anchorer and the gate each buy

_Same model, same detections (recall identical). The only thing that moves is whether each citation lands on the RIGHT text, and whether an unverifiable finding can reach output. This is the real product story._

| Pipeline | high-risk recall | citation faithfulness | every accepted finding a verifiable slice? |
|---|---|---|---|
| B1 naive single-shot (exact-anchor) | 0.8132 | 0.4651 | no |
| B1 fair single-shot (fuzzy-anchor) | 0.8132 | 0.7126 | anchored ones only |
| B2 agent (fuzzy-anchor + gate) | 0.7363 | 0.9333 | **yes — gate rejects unanchorable** |

- **Anchorer lift:** naive → fair citation faithfulness 0.4651 → 0.7126 (same detections, better-placed citations).
- **Gate guarantee:** 100% of B2's accepted findings re-slice the raw contract exactly; an unanchorable (likely hallucinated) finding cannot pass.
- **Honest limit:** 6 accepted finding(s) verify as a real slice but miss the gold clause region (right answer, wrong location). The gate checks slice-integrity, not gold-overlap — so it cannot catch these. This is the next quality target.

## Per-clause F1 (B2)

| Clause | P | R | F1 | laziness | cite-faith | support |
|---|---|---|---|---|---|---|
| change_of_control | 0.5806 | 0.6923 | 0.6316 | 0.3077 | 0.7222 | 26 |
| uncapped_liability | 0.0909 | 0.2308 | 0.1304 | 0.7692 | 1.0 | 13 |
| auto_renewal | 0.9333 | 0.875 | 0.9032 | 0.125 | 1.0 | 16 |
| non_compete | 0.8182 | 0.7826 | 0.8 | 0.2174 | 0.9444 | 23 |
| termination_for_convenience | 0.7778 | 0.9655 | 0.8615 | 0.0345 | 1.0 | 29 |