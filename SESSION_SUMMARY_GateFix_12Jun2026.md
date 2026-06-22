# 📝 Session summary — AuditAgent gate-fix, benchmark & reproducibility
_12 June 2026 · A record of what we did, what we found, and the lessons worth keeping._
_Companion to the forward-looking `HANDOFF_AuditAgent_GateFix_COMPLETE.md` (for the next chat). This file is for **you** to revisit and learn from._

---

## 1. The one-line story

> A citation-enforcing contract-review agent was **losing to a single API call** because its own gate was too strict. We diagnosed it, fixed it, re-measured, **caught a second flaw (benchmark noise)**, fixed that too, and ended with a reproducible, honest result across two model families. The fix's win — **+0.30 citation faithfulness** — replicates on both Claude and DeepSeek.

That arc (measure → find your own flaw → fix → re-measure → find another → fix) is the whole point. It's what a real solution architect does and what a portfolio-faker can't.

---

## 2. The problem we walked into

The agent's "citation gate" only accepted a finding if its quote was a **byte-exact substring** of the contract. But real LLMs return quotes that are *meaning-exact, text-off*: a curly quote `“` instead of `"`, a collapsed double-space, an em-dash for a hyphen, a line-break removed.

- Every cosmetic mismatch → gate **rejects a correct finding** → counted as a miss → **recall craters**.
- First real eval: agent high-risk recall **0.625** vs single-shot **0.958**. The agent's complexity was a net negative.

🧠 **Lesson:** a guardrail that's *too literal* is itself a bug. "Verify the citation" must mean "verify it points to real text," not "verify the bytes match a noisy model's formatting."

---

## 3. What we built

### 3a. Fuzzy-but-verified anchoring (`anchor.py`)
The core fix. Three ideas stacked:

1. **Normalise a throwaway copy** of the contract (fold smart-quotes/dashes/ellipses to ASCII, collapse whitespace) just to *find* where the quote lives.
2. **Keep an index map** back to the original character offsets.
3. **Return a citation sliced from the ORIGINAL text** at those offsets — so the quote is still a real, exact slice of the contract.

🔒 The non-negotiable invariant survived: `raw_text[start:end] == quote`, always. Fuzzy matching only *locates*; the citation itself is never fuzzy. A hallucinated quote (not in the doc) still fails to anchor → still rejected.

🧠 **Analogy:** the model hands you a slightly smudged photocopy of a quote. Instead of rejecting it, you use the smudged copy to *find* the original paragraph in the contract, then cite the **original** — clean and exact. You never quote the smudge.

### 3b. An honest three-way benchmark (`eval/runner.py`)
The old eval compared apples to oranges (single-shot counted all findings; agent counted only gate-survivors). We rebuilt it to show:

- **B1 naive** — single-shot with exact-only anchoring (what most demos ship).
- **B1 fair** — single-shot *with* the new anchorer (a strong, honest baseline).
- **B2 agent** — fuzzy anchor + the gate.

Plus a **detection-vs-verification** split (did we *find* it vs did the gate *keep* it) and a **wrong-location diagnostic** (citations that verify as real slices but point at the wrong clause).

🧠 **Lesson:** how you frame the baseline decides the story. Quietly weakening the baseline to make your system look good is the cardinal sin. We deliberately kept a *strong* fair baseline — the result has to survive that.

### 3c. Supporting fixes
- **`temperature=0`** added to both model adapters (was unset → defaulting to 1.0). This was the cause of the benchmark noise (see §5).
- **`DeepSeekReviewer`** wired so a DeepSeek run is one model end-to-end (detector + gate), not a DeepSeek detector wearing a Claude gate.
- **Connection-timeout retries** in both adapters (a TLS handshake blip no longer kills a paid run mid-way).
- **`scripts/benchmark_twice.sh`** — runs the eval 2× at temp=0, auto-detects the provider, and prints a ✅/🚨 reproducibility diff. (Now also takes an optional full-split path.)
- **60 tests green.**

---

## 4. The results (20-contract held-out sample, temperature 0)

| | Claude Sonnet 4.6 | DeepSeek V4 Flash |
|---|---|---|
| **Anchorer lift** (naive→anchored faithfulness) | 0.5467 → 0.8533 (**+0.31**) | 0.5867 → 0.8833 (**+0.30**) |
| B2 high-risk recall | 0.9167 | 0.9583 |
| B2 macro-F1 | 0.6769 | 0.7774 |
| Gate effect on detection | slight cost (−0.04 recall) | neutral (tied) |
| **$/contract** | ~$0.046 | **~$0.0032 (~14× cheaper)** |
| **speed** | ~24 s | **~3.9 s (~5× faster)** |
| Reproducibility | 2× checked ✅ | 2× checked ✅ |

**What's safe to claim** (true + reproducible):
- The anchoring fix lifts citation faithfulness **+0.30** across two different model families. *(Headline.)*
- Every finding the agent surfaces is a **verified, exact quote** — guaranteed by construction.
- The benchmark is **reproducible at temperature 0** (we caught & fixed a noise artifact).
- **DeepSeek for the demo:** comparable accuracy, ~14× cheaper, ~5× faster.

**What NOT to claim:**
- ❌ "The agent beats single-shot." It doesn't — the gate is a *precision/integrity mechanism, not an accuracy booster*. Its small recall cost = findings it refused to surface uncited (correct for assurance).
- ❌ "DeepSeek beats Claude." Within noise; the honest word is **comparable**.

---

## 5. The plot twist: benchmark noise (the best lesson)

After the fix, we re-ran the 20-contract eval and the agent **lost**. Then we ran it again — same code — and it **tied**. The headline metric **flipped sign between two identical runs.**

- **Cause:** the model calls had no `temperature` set → API default **1.0** (maximum randomness). The run-to-run noise was *bigger than the effect we were trying to measure.*
- **Fix:** set `temperature=0`. After that, the deltas matched across runs (spread ≈ 0).
- **Residual:** DeepSeek still drifts slightly on *detection* metrics even at temp=0 (mixture-of-experts routing) — but its *faithfulness* numbers are rock-solid (spread 0.0).

🧠 **The lesson worth tattooing on:** *a number you can't reproduce is not a result.* If you run a benchmark once and screenshot the number, you have no idea whether you measured your system or measured luck. Always re-run; if the headline moves, your sample or your sampling is too noisy to draw the conclusion.

---

## 6. Decisions we made (and why)

| Decision | Choice | Why |
|---|---|---|
| Report B1 fairly or weakly? | **Three-way (naive + fair + gated)** | Shows the anchorer's win *and* survives a strong baseline = honest + impressive. |
| Chase a "win" by tuning? | **No** — report what falls out | The project's whole value is anti-overclaim. |
| Production model | **DeepSeek** (demo) / **Claude** (benchmark) | 14× cheaper, 5× faster, comparable. Never merge the two models' numbers. |
| Spend $ on the full split? | **Defer** | n=20 story is solid; full split (102 contracts) is cheap later if needed. |
| Temperature for benchmarks | **0** | Reproducibility. |

---

## 7. Cost & scale reference

- **Demo (one contract through the agent):** Claude ~$0.046 · DeepSeek ~$0.0032.
- **20-contract benchmark:** Claude ~$1.8 · DeepSeek ~$0.13.
- **Full CUAD test split = 102 contracts** (not 510 — that was an error in the old handoff): Claude ~$9 · DeepSeek **<$1**. Run with `bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json`.

---

## 8. Commands cheat-sheet (run on your Mac; the sandbox can't reach model APIs)

```bash
cd ~/Documents/Claude/Projects/Agentic\ AI\ Portfolio/auditagent

# tests (no key needed)
PYTHONPATH=src python3.14 -m pytest -q                 # 60 passed

# Claude benchmark, reproducibility-checked
unset DEEPSEEK_API_KEY
export ANTHROPIC_API_KEY=sk-ant-...                    # terminal only, never in chat
bash scripts/benchmark_twice.sh
cp eval_claude_run1.json eval_report.json && cp eval_claude_run1.md eval_report.md

# DeepSeek benchmark, reproducibility-checked
export DEEPSEEK_API_KEY=sk-...
bash scripts/benchmark_twice.sh
cp eval_deepseek_run1.json eval_deepseek.json && cp eval_deepseek_run1.md eval_deepseek.md

# full 102-contract split (optional, cheap on DeepSeek)
bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json
```

⚠️ **Terminal habits learned this session:** paste commands **one line at a time** (multi-line paste leaks a `[` from bracketed-paste mode); never paste a command with a trailing `# comment` (your zsh mis-parses the em-dash); keys go in the terminal env **only** — never in chat or a screenshot (one key was exposed and had to be rotated).

---

## 9. What's done vs what's next

✅ **Done:** fuzzy anchorer + tests; three-way eval; temp=0 fix; DeepSeek reviewer; timeout retries; both models 2×-benchmarked & committed; handoff written.

⏭️ **Next:** build the deployed website — two model boxes (**Claude = benchmark numbers, DeepSeek = demo/cost**) + a "How we measured" section featuring the temperature catch. Lead with the cross-model anchorer result (+0.30), not the cost. Optional later: full 102-split, and diagnosing the 3 wrong-location findings (likely `uncapped_liability`).

---

## 10. The portfolio takeaway

You now have an artifact that demonstrates: building a guardrail, **measuring it honestly, catching two of your own flaws, and fixing them with reproducible evidence** — across two model families, with a real cost/quality trade-off behind the production choice. That's not a demo. That's the job.

_End of session summary._
