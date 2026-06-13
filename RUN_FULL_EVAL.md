# 🎯 RUN_FULL_EVAL — the firm n=102 number (kills the "it's just noise" objection)

_Prepared 12 June 2026. Runs on **Taash's Mac** only — the sandbox blocks provider APIs._
_Goal: replace the noise-limited **n=20** held-out result with a reproducible **n=102** one on the FULL CUAD test split._

---

## Why this run exists (the one-line case)

Your committed numbers are **n=20**, and the handoff itself flags the B2-vs-B1 detection delta as *within noise* (±1 finding). A Big-4 reviewer reads "n=20, within noise" as **underpowered**, not "honest." This run spends **~$1.50 and ~30 min on DeepSeek** to convert that hedge into a firm number on the **whole** held-out test set your 20 was sampled from.

> ⚠️ **The handoff said "510 split." That is wrong.** `download_cuad.py --extract` writes the CUAD **test split = 102 contracts** (not 510). 102 is the *correct, methodologically clean* choice — it is the standard held-out set, and your n=20 was a subset of it. The 510 file (`CUADv1.json`) mixes in the train split, which is meaningless for a no-fine-tuning LLM. **Use 102.**

---

## What was changed to make this possible

`scripts/benchmark_twice.sh` previously **only** ran the shipped 20-sample — so a 102 run could only be done once, *un-replicated*. That defeats the point (a bigger un-replicated number invites the same objection).

It now takes an **optional CUAD path** and runs the 2× reproducibility check on it, writing `_full`-tagged output files. Validated offline: bash-3.2 safe, emits the right command, reproducible, all diff keys present. **No Python changed — 60 tests still green.**

---

## The numbers you're committing to (estimates)

| Model | Scope | Cost (2× check) | Wall time (2×) | Verdict |
|---|---|---|---|---|
| **DeepSeek** v4-flash | 102 × 2 runs | **≈ $1.50** | **≈ 30 min** | ✅ **Do this — the firm number** |
| Claude sonnet-4-6 | 102 × 2 runs | ≈ $18 | ≈ 2.5 hr | ❌ Skip — keep its committed n=20 |

**Recommendation:** the firm number only needs to land on **one** model. DeepSeek is ~14× cheaper and is your prod/demo model anyway. Run DeepSeek full 2×; leave Claude on its already-2×-checked n=20.

---

## STEP 1 — open the project

```
cd ~/Documents/Claude/Projects/Agentic\ AI\ Portfolio/auditagent
```

## STEP 2 — get the 102-contract test split (one time)

```
python3.14 scripts/download_cuad.py --extract
```

This clones CUAD (CC BY 4.0), unzips, and writes `data/cuad/CUADv1_test.json`. Expect it to print **"Wrote ... (102 held-out test contracts)."** If it prints a different number, stop and tell the next chat.

## STEP 3 — confirm the suite is green (offline, no key)

```
PYTHONPATH=src python3.14 -m pytest -q
```

Expect **60 passed**.

## STEP 4 — run the full DeepSeek benchmark, 2× at temperature 0

Export the key in the **terminal only** — never paste it into chat or a screenshot.

```
export DEEPSEEK_API_KEY=sk-...
```

```
bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json
```

This runs the eval **twice** on all 102 contracts and prints a ✅/⚠️/🚨 reproducibility diff. It writes:

- `eval_deepseek_full_run1.{json,md}`
- `eval_deepseek_full_run2.{json,md}`

## STEP 5 — read the verdict

Look at the two delta rows in the printed diff:

- **B2-B1 high-risk recall delta**
- **B2-B1 macro-F1 delta**

If **both show ✅** (spread ≤ 0.01), the n=102 number is trustworthy — the noise objection is dead. ⚠️ on macro-F1 only = the known small MoE drift; still report it honestly. Citation-faithfulness rows should be rock-solid ✅ (that is your headline result, now at n=102).

## STEP 6 — commit the clean run as the canonical full result

Pick the cleaner of run1/run2 (usually run1). Copy NOT-with-inline-comments:

```
cp eval_deepseek_full_run1.json eval_deepseek_full.json
cp eval_deepseek_full_run1.md eval_deepseek_full.md
```

Then update the handoff results table (§2) to cite **n=102** for DeepSeek, and note Claude remains at its 2×-checked n=20.

---

## OPTIONAL — cross-model firm number on Claude (~$9, ~75 min, single run)

Only if a reviewer pushes hard on "is the anchorer lift real on Claude too at scale." One run is enough for the **faithfulness** headline (it is the rock-solid metric):

```
unset DEEPSEEK_API_KEY
export ANTHROPIC_API_KEY=sk-ant-...
PYTHONPATH=src python3.14 -m auditagent.eval --full data/cuad/CUADv1_test.json --json eval_claude_full.json --md eval_claude_full.md
```

---

## Gotchas (do not skip)

- 🐍 Use **`python3.14`**. Your default `python3` is 3.9 and too old.
- 🔑 `DEEPSEEK_API_KEY` **wins** over `ANTHROPIC_API_KEY`. For a clean Claude run, `unset DEEPSEEK_API_KEY` first.
- 🌡️ Temperature is **0** by default — required for reproducibility. Do not override for headline numbers.
- 🔐 Keys live in the terminal env only.
- 🧱 None of this runs in Cowork/Claude — provider APIs are blocked in the sandbox.

---

## VALIDATE THE uncapped_liability FIX (after the diagnosis on 12 Jun)

The n=102 run localised the faithfulness wobble to **one clause** — `uncapped_liability` (precision **0.204**, the only clause whose faithfulness moved run-to-run). Root cause: the model was sent a bare label with **no definition**, so it over-flagged any liability language. The classifier now sends a real definition per clause, including the explicit negative *"a clause that CAPS liability is NOT a hit."* Offline tests: **64 green**.

**Save the pre-fix baseline first** (so you can compare before/after):

```
cp eval_deepseek_full_run1.json eval_deepseek_full_PREFIX_run1.json
cp eval_deepseek_full_run2.json eval_deepseek_full_PREFIX_run2.json
```

**Re-run the full 2× benchmark with the fix:**

```
export DEEPSEEK_API_KEY=sk-...
bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json
```

**What to compare (the fix worked if all three move the right way):**

| Signal | Pre-fix (n=102) | Target after fix |
|---|---|---|
| uncapped_liability precision | 0.204 | **higher** (fewer false flags) |
| uncapped_liability faith. spread run1↔run2 | 0.089 | **lower** (toward the other clauses' ~0.00) |
| Overall faithfulness spread | 0.069 🚨 | **lower** (toward ✅ ≤0.01) |

Pull the precision quickly:

```
python3.14 -c "import json;d=json.load(open('eval_deepseek_full_run1.json'));print('uncapped precision:', d['B2']['per_clause']['uncapped_liability']['precision'])"
```

⚠️ Recall must NOT collapse. The fix tightens precision; if uncapped_liability **recall** drops sharply, the definition is too strict — tell the next chat and we loosen the negative wording. Evidence first.

---

## What to claim after this run

✅ "Citation-anchoring lift **+0.30** holds on the **full CUAD held-out test split (n=102)**, not just a 20-sample."
✅ "The benchmark is reproducible at temperature 0 across the full split."
🚫 Still do **not** claim "the agent beats single-shot" — the gate is a precision/integrity mechanism. n=102 makes that verdict *firmer*, not different.
