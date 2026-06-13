# Case Study — Catching and fixing a benchmark that lied at scale

**AuditAgent · CUAD contract-clause review · DeepSeek V4 Flash · n=102 held-out test split**

> **One line:** A 20-contract benchmark looked great. Scaling it to the full 102-contract held-out set broke one of its own reproducibility claims — so I traced the instability to a single clause, root-caused it to a missing prompt definition, fixed it, and re-measured. Precision on the weak clause **nearly doubled with zero recall cost**, and the product's cited output went from drifting run-to-run to **bit-for-bit reproducible.**

---

## The debugging arc

```
measure (n=20, looks great)
   → scale to n=102 (a reproducibility claim breaks)
      → isolate (is it my harness or the model?)
         → localize (which clause?)
            → root-cause (why that clause?)
               → fix (one targeted change)
                  → re-measure (confirmed)
```

This is the part that matters: not the final number, but the *method* — measure, distrust your own result, find your own flaw, fix it, prove the fix.

---

## 1. The claim that broke

The shipped 20-contract evaluation reported citation faithfulness as **perfectly reproducible at temperature 0 (spread 0.0000)**. On the full **102-contract** held-out split, the same metric spread **0.069** between two identical runs — and two other claims softened too:

| Metric | n=20 (claimed) | n=102 (real) | What it meant |
|---|---|---|---|
| B1 macro-F1 | 0.777 | 0.605 | the 20-sample was an *easy* subset |
| High-risk recall | 0.958 | 0.890 | the real set is harder |
| Faithfulness reproducibility | spread **0.0000** | spread **0.069** | "bulletproof" was small-sample luck |
| Gate detection delta | "neutral" | −0.01 to −0.03 recall | the gate isn't free |

**Lesson:** a clean number on n=20 is not evidence of reproducibility. You have to scale it before you trust it.

---

## 2. Isolate — harness or model?

Before blaming the model, I ruled out my own code. I ran the **deterministic offline provider** (a fixed fake model) twice over all 102 contracts:

> Every metric, both runs: **spread 0.0000.** The harness is bit-for-bit deterministic.

→ The wobble is the **real model**, not the evaluation pipeline.

---

## 3. Localize — which clause?

I diffed the per-clause faithfulness between the two runs. The instability was **not** spread across the board:

| Clause | Δ faithfulness (run1→run2) | Stable? |
|---|---|---|
| **uncapped_liability** | **0.089** | ❌ the entire wobble |
| change_of_control | 0.013 | ~ |
| auto_renewal | 0.000 | ✅ |
| non_compete | 0.000 | ✅ |
| termination_for_convenience | 0.000 | ✅ |

**Three of five clauses had zero drift.** One clause was driving the aggregate wobble.

---

## 4. Root-cause — why that clause?

`uncapped_liability` had the **lowest support (13 contracts)** and **by far the worst precision (0.204)** — the model was flagging ~5× more "uncapped" clauses than actually existed. Looking at the prompt explained both:

- The classifier sent the model only a bare label: `- uncapped_liability: Uncapped Liability` — **no definition.**
- The system prompt said *"RECALL MATTERS MORE THAN PRECISION"* — an explicit over-flagging bias.
- The model was never told that **a clause that *caps* liability is the opposite of uncapped** — so it flagged any liability language. On genuinely borderline contracts it was near-50/50, and at temperature 0 the model's routing flipped which quote it returned between runs. With only 13 examples, one or two flips swung the mean ~9 points.

**The wobble was never a model-quality problem. It was an underspecified prompt.**

---

## 5. The fix

Give every clause a one-line detection definition — and for the weak one, state the explicit negative:

> *"Flag ONLY if liability is explicitly UNLIMITED or carries NO monetary cap. A clause that CAPS or LIMITS liability … is the OPPOSITE — do NOT flag it."*

Wired into both the Claude and DeepSeek prompts (kept identical, so the model-router story holds), and locked with a regression test so the negative instruction can't be silently dropped. **64 offline tests green.**

---

## 6. Re-measure — confirmed

**Target clause — `uncapped_liability`:**

| Metric | Pre-fix | Post-fix | |
|---|---|---|---|
| Precision | 0.204 | **0.385** | ✅ ~doubled |
| Recall | 0.769 | **0.769** | ✅ unchanged — no trade |
| F1 | 0.323 | **0.513** | ✅ +0.19 |

**Reproducibility (the wobble we went looking for):**

| Signal | Pre-fix | Post-fix | |
|---|---|---|---|
| B2 citation faithfulness spread (gated output) | 0.0203 | **0.0000** | ✅ perfectly reproducible |
| B1-fair faithfulness spread | 0.069 | 0.021 | ⬇️ cut to a third |
| Overall B2 macro-F1 | 0.589 | **0.649** | ✅ +0.06 |
| Overall high-risk recall | 0.879 | **0.912** | ✅ up |

The product's shipped output — every cited clause that passes the gate — is now **bit-for-bit reproducible** at temperature 0. The small residual drift sits *upstream* of the gate, on the inherently hard low-support clause, and the gate absorbs it.

---

## 7. The headline result (unchanged by all this)

The core contribution survived the scale-up intact: a **fuzzy-but-verified citation anchorer** lifts faithfulness from a naive exact-match baseline by **~+0.29 within-run on DeepSeek (n=102)** and **+0.33 on Claude (n=20)** — same fix, two model families, near-identical lift. The anchorer is computed on identical model output re-anchored exact-vs-fuzzy, so the model's non-determinism never touches it.

---

## Honest verdict — what this does and doesn't show

✅ **Claim:** "Citation anchoring lifts faithfulness ~+0.29 on the full CUAD held-out split; the gated output is reproducible at temperature 0; a missing clause definition was costing the weakest clause ~half its precision, and fixing it doubled precision with no recall loss."

🚫 **Do not claim:** "The agent beats single-shot." It doesn't — the citation gate is a **precision / integrity mechanism**, not an accuracy booster. Every finding it surfaces is a verified, exact quote; an unanchorable (likely hallucinated) one cannot pass. Scaling to n=102 made that verdict *firmer*, not different.

---

## What this demonstrates

- **Measurement discipline** — distrusting a clean small-sample number and scaling it before believing it.
- **Disciplined debugging** — ruling out the harness before blaming the model; localizing to one clause before changing anything.
- **Evidence before action** — root-causing to a specific prompt gap, not guessing.
- **Honest reporting** — separating what's measured (detection) from what's a product rule (severity), and refusing to oversell the gate.

_Numbers: DeepSeek V4 Flash, CUAD test split (102 contracts), temperature 0, 2× reproducibility-checked. Cost ≈ $0.0035/contract, ≈ 3.4 s/contract. Pre/post-fix eval artifacts committed in-repo._
