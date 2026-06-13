# 🧾 HANDOFF — AuditAgent gate-fix: BUILT, BENCHMARKED, REPRODUCIBLE

### Single source of truth for the NEXT chat. Read this whole file before touching code.
_Last updated: 12 June 2026 · Supersedes `HANDOFF_GateFix_AuditAgent.md` (the work order) — that job is now DONE._
_Project bible: `MASTER_HANDOFF_AuditAgent.md`. This file = current state + verified results + what's left._

---

## 0. TL;DR (read this, then §2 and §8)

- The citation gate's **exact-substring anchoring was destroying recall** (real LLM quotes differ by whitespace/smart-quotes/dashes → rejected → counted as misses). **FIXED** with `fuzzy_anchor_quote()` — normalise to *locate* the region, return a citation that is still a real exact slice (M1 invariant intact).
- Eval reworked into an honest **three-way** comparison (naive B1 / fair B1 / gated B2) + a **detection-vs-verification** split + a **right-answer-wrong-location** diagnostic.
- Both models benchmarked on the 20-contract held-out sample, **both reproducibility-checked 2× at temp=0.** Faithfulness rock-solid on both; detection deltas carry small residual noise.
- **The headline win is the anchorer, and it replicates across two model families:** citation faithfulness naive→anchored **+0.31 (Claude), +0.30 (DeepSeek)**.
- **The honest verdict:** the gate is a *precision/integrity mechanism, NOT an accuracy booster*. It costs ~0.04 high-risk recall on both models. Do **not** claim "the agent beats single-shot."
- **Test suite: 60 green.** All work is in the repo. No keyed eval can run in the sandbox (provider APIs blocked) — runs happen on Taash's Mac.

---

## 1. WHERE WE ARE (one paragraph)

M1–M3 were built in prior chats. The first real-model eval (Claude, 20 CUAD contracts) showed the agent **losing** to single-shot because the citation gate demanded a byte-exact quote. This session we (a) built fuzzy-but-verified anchoring, (b) reframed the eval so detection and verification are scored separately and a naive baseline is visible, (c) discovered and fixed a **temperature=1.0 sampling-noise artifact** that had been flipping the headline metric's sign between runs, (d) wired a DeepSeek reviewer so a DeepSeek run is one model end-to-end, (e) hardened both adapters against connection timeouts, and (f) produced reproducible Claude numbers + a first DeepSeek run. The result is honest and defensible: the gate slightly costs recall, the anchorer clearly lifts faithfulness, and the whole thing is now reproducible.

---

## 2. THE RESULTS (the numbers that matter) — 20 CUAD contracts, temperature 0

### Claude `claude-sonnet-4-6` — committed to `eval_report.{md,json}` · reproducibility-checked 2×

| Pipeline | macro-F1 | high-risk recall | laziness ↓ | citation faith. ↑ | $/contract | s/contract |
|---|---|---|---|---|---|---|
| **B1** single-shot (fair) | 0.6911 | 0.9583 | 0.0286 | 0.8533 | 0.0426 | 19.95 |
| **B2** agent (gate) | 0.6769 | 0.9167 | 0.0619 | 0.88 | 0.0464 | 24.37 |
| B1 **naive** (exact-anchor) | — | 0.9583 | — | **0.5467** | — | — |

- **B2 − B1: recall −0.0417, macro-F1 −0.0142.** Reproducible across both runs (recall delta spread 0.0000, macro-F1 spread 0.0033).
- **Gate gap (detection − verified high-risk recall) = +0.0417** → the gate dropped one high-risk finding it detected (it could not anchor/verify it).
- Wrong-location accepted findings: **3** (verify as a real slice but miss the gold clause region).
- B2 faithfulness wobbles 0.88↔0.92 (spread 0.04) = **small-sample, NOT temperature** (one finding flipping at n=20).

### DeepSeek `deepseek-v4-flash` — reproducibility-checked **2×** (`eval_deepseek_run1/2.*`)

Numbers below are **run1** (the clean reproducibility run — recommend committing it as the canonical `eval_deepseek.*`):

| Pipeline | macro-F1 | high-risk recall | laziness ↓ | citation faith. ↑ | $/contract | s/contract |
|---|---|---|---|---|---|---|
| **B1** single-shot (fair) | 0.7774 | 0.9583 | 0.0286 | 0.8833 | 0.0032 | 4.44 |
| **B2** agent (gate) | 0.7774 | 0.9583 | 0.0286 | 0.8833 | 0.0032 | 3.94 |
| B1 **naive** (exact-anchor) | — | 0.9583 | — | **0.5867** | — | — |

- **B2 − B1 in the 2× check: recall +0.0000 (both runs), macro-F1 +0.0000 / +0.0145.** The gate is **neutral on detection** for DeepSeek — no recall cost, F1 tied-to-slightly-positive.
- ✅ **Citation faithfulness perfectly reproducible** (spread 0.0000): B1 fair 0.8833, B2 0.8833, naive 0.5867. Anchorer lift = **+0.2966 ≈ +0.30**, bulletproof.
- ⚠️ **Residual detection noise at temp=0:** the macro-F1 delta drifts 0.0000→0.0145 (B1 macro-F1 wobbles 0.7628–0.7774; B2 is steadier at 0.7774). DeepSeek is **not** fully deterministic at temp=0 (MoE routing) — but only on detection, never on faithfulness.
- 🔎 **The earlier single run** (committed as `eval_deepseek.*`: recall −0.0417, macro-F1 +0.0328) was **within that residual noise band** — an outlier, not the truth. Re-commit run1 over it.
- DeepSeek is **~14× cheaper** ($0.0032 vs $0.0464) and **~5× faster** (3.9s vs 24.4s) than Claude.

### The cross-model invariant (the headline)
**Citation-faithfulness anchorer lift: naive → anchored = +0.31 (Claude), +0.30 (DeepSeek).** Same fix, two different model families, near-identical lift. The contribution is model-agnostic.

> ⚠️ n=20 (the shipped held-out sample). **Both models are now 2× reproducibility-checked at temp=0.** Faithfulness is rock-solid on both; detection deltas carry small residual noise (~±1 finding / ~0.01–0.03 F1), so the B2-vs-B1 *detection* comparison is within noise — i.e. the gate is ~neutral on accuracy (slight cost on Claude, neutral on DeepSeek). Full 510 split is the firm number if ever needed (cheap on DeepSeek, ~$2; ~$45 on Claude).

---

## 3. THE HONEST VERDICT — what to claim, what NOT to claim

✅ **Claim (true + reproducible):**
- "A citation-anchoring fix lifts faithfulness **+0.30–0.31** across two model families (Claude + DeepSeek), with no loss to detection recall on the baseline."
- "Every finding the agent surfaces is a **verified, exact quote** — guaranteed by construction; an unanchorable (likely hallucinated) finding cannot pass the gate."
- "Benchmark is **reproducible at temperature 0** — we caught and fixed a sampling-noise artifact that had flipped the headline metric's sign between runs." (Measurement rigor.)
- "DeepSeek chosen for the demo: **comparable accuracy, ~14× cheaper, ~5× faster.**"

🚫 **Do NOT claim:**
- "The agent beats single-shot." It doesn't — the gate is ~neutral on detection (slight ~0.04 recall cost on Claude; **neutral on DeepSeek in the 2× check**). The gate is a **precision/integrity mechanism, not an accuracy booster.** Any "lost" recall is findings it refused to surface uncited — correct behaviour for assurance.
- "DeepSeek beats Claude." Both are now 2× checked, but DeepSeek's apparent F1 edge is within run-to-run noise (its B1 macro-F1 alone wobbles 0.76–0.78). The honest word is **"comparable."**
- "DeepSeek's gate improves F1 (+0.0328)." That figure was a single-run outlier; the 2× check shows the gate delta is 0.0–0.0145 (≈ neutral). Don't quote the outlier.
- Any number from a temp=1.0 / non-reproducibility-checked run.

🎁 **The narrative gift:** measure → find your own flaw (gate strictness destroying recall) → fix (fuzzy-but-verified anchoring) → re-measure → catch a *second* flaw (sampling noise) → fix (temp=0) → reproducible. That arc is exactly what a Big-4 solution architect does and what fakers can't fake. Lead with the cross-model anchorer result; cost is the procurement footnote.

---

## 4. WHAT CHANGED THIS SESSION (so you know the current code)

1. **`src/auditagent/anchor.py` (NEW)** — `fuzzy_anchor_quote(raw_text, quote, *, min_ratio=0.9)`. Exact-first → normalised-exact (whitespace collapse + smart-quote/dash/ellipsis fold, case-insensitive fallback) → bounded token-anchored fuzzy (difflib, length-guarded). Returns a `Citation` whose `quote` is sliced from raw text, so `verify_against` is true **by construction**. Hallucinated/wrong-region quotes still return None.
2. **`agents/classifier.py`** — `classify_clauses` uses `fuzzy_anchor_quote`; now also stores the model's `raw_quote` on each Finding. `anchor_quote` (exact) kept as the primitive.
3. **`agents/reviewer.py`** — gate retry (`_reextract`) uses `fuzzy_anchor_quote`.
4. **`models.py`** — `Finding.raw_quote: str | None` added (lets the eval re-anchor the same model output exact-vs-fuzzy with no extra calls). `Citation.verify_against` **UNCHANGED** (the M1 invariant — never weaken it).
5. **`eval/runner.py`** — `run_b1` scores naive (exact) + fair (fuzzy) from the SAME samples; `run_b2` returns verified + pre-gate detection preds; report adds `B1_naive`, `B2_detection`, `gate_gap_high_risk_recall`, `B2_wrong_location_findings`; markdown adds a "Detection vs verification" table + a "Citation quality" table + the honest-limit line.
6. **`llm/claude.py`** — payload now sets `temperature` (default **0** via `AUDITAGENT_TEMPERATURE`); retry loop now also catches `httpx.TransportError` (TLS handshake / connect / read timeouts) with backoff.
7. **`llm/deepseek.py`** — refactored to a shared `_call_deepseek`; added **`DeepSeekReviewer`** (DeepSeek twin of `ClaudeReviewer`); temp=0 default; TransportError retry.
8. **`llm/factory.py`** — `get_reviewer` precedence now DeepSeek → Claude → deterministic (so a DeepSeek run is one model end-to-end).
9. **`scripts/benchmark_twice.sh` (NEW)** — runs the eval 2× at temp=0, **provider-aware** (auto-detects DeepSeek vs Claude from keys), writes `eval_<prov>_run1/2.*`, prints a ✅/🚨 reproducibility diff.
10. **Tests** — `tests/test_anchor.py` (NEW, 10), `tests/test_eval_threeway.py` (NEW, 4), + 2 gate tests. **60 green** offline.

---

## 5. FILES MAP

| File | Role |
|---|---|
| `src/auditagent/anchor.py` | **The fix.** Fuzzy-but-verified anchorer. |
| `src/auditagent/models.py` | `Citation.verify_against` = the M1 invariant (DO NOT weaken). `Finding.raw_quote`. |
| `src/auditagent/agents/classifier.py` | Detector; exact-then-fuzzy anchoring; stores raw_quote. |
| `src/auditagent/agents/reviewer.py` | The citation gate; fuzzy retry. |
| `src/auditagent/eval/runner.py` | Three-way scoring, detection column, diagnostics, markdown. |
| `src/auditagent/eval/scorer.py` | CUAD metrics (unchanged this session). |
| `src/auditagent/llm/claude.py` | Claude detector + reviewer; temp=0; timeout retry. |
| `src/auditagent/llm/deepseek.py` | DeepSeek detector + **reviewer**; temp=0; timeout retry. |
| `src/auditagent/llm/factory.py` | Provider precedence (DeepSeek → Claude → deterministic) for BOTH classifier and reviewer. |
| `scripts/benchmark_twice.sh` | Provider-aware 2× reproducibility runner. |
| `eval_report.{md,json}` | **Committed Claude result** (reproducible temp=0). |
| `eval_deepseek.{md,json}` | DeepSeek result (1×). |
| `tests/test_anchor.py`, `tests/test_eval_threeway.py`, `tests/test_citation_gate.py` | The fix's tests. |

---

## 6. HOW TO RUN (on Taash's Mac — sandbox CANNOT run real models)

```bash
cd ~/Documents/Claude/Projects/Agentic\ AI\ Portfolio/auditagent

# one-time / after dep changes:
make install PYTHON=python3.14

# tests (offline, no key):
PYTHONPATH=src python3.14 -m pytest -q          # expect 60 passed

# --- CLAUDE benchmark (reproducible, 2×) ---
unset DEEPSEEK_API_KEY
export ANTHROPIC_API_KEY=sk-ant-...             # terminal only, never in chat
bash scripts/benchmark_twice.sh                 # writes eval_claude_run1/2.*, prints ✅/🚨

# commit the good run as the canonical report:
cp eval_claude_run1.json eval_report.json && cp eval_claude_run1.md eval_report.md

# --- DEEPSEEK benchmark (do the 2× check too) ---
export DEEPSEEK_API_KEY=sk-...                  # wins precedence → full DeepSeek detector+gate
bash scripts/benchmark_twice.sh                 # writes eval_deepseek_run1/2.*

# single run to a named file (what produced the current eval_deepseek.*):
PYTHONPATH=src python3.14 -m auditagent.eval --json eval_deepseek.json --md eval_deepseek.md
```

Cost/time per 20-run: Claude ≈ $1.8 / ~15 min; DeepSeek ≈ $0.13 / ~3 min. Full 510: `--full PATH_TO_CUAD.json` (DeepSeek ≈ $2; Claude ≈ $45).

---

## 7. ENVIRONMENT GOTCHAS (hard-won — saves the next chat an hour)

- 🧱 **Sandbox blocks ALL provider APIs** (`api.anthropic.com` returns a bare proxy 401; `api.deepseek.com` refused). **No keyed eval runs in Cowork/Claude — only on Taash's Mac.** Don't try.
- 🐍 **Python:** use **`python3.14`** (python.org). Her default `python3` is 3.9 — too old.
- ⚡ **Run from source** with `PYTHONPATH=src` to pick up edits without `make install`.
- 🌡️ **Temperature:** default is now **0** (reproducible benchmarks). Override with `AUDITAGENT_TEMPERATURE` for sensitivity analysis. A non-zero temp re-introduces the sign-flip noise — don't, for headline numbers.
- 🔑 **Key precedence:** `DEEPSEEK_API_KEY` **wins** over `ANTHROPIC_API_KEY` for BOTH detector and gate. For a clean Claude run, `unset DEEPSEEK_API_KEY` first (benchmark_twice warns/branches on this).
- 🔁 **Retries:** both adapters retry 429/503/529 **and** `httpx.TransportError` (TLS handshake / connect / read timeouts) with backoff (`AUDITAGENT_MAX_RETRIES`, default 6). A connect-timeout was traced to Taash's network/VPN, not the code — switching network / retrying cleared it.
- ✂️ **max_tokens** via `AUDITAGENT_MAX_TOKENS` (default 4096); `_parse_hits` salvages complete `{...}` objects from a truncated/markdown-wrapped reply.
- 🔐 **Keys** go in the terminal env only — **never pasted into chat or screenshots.** (A key was exposed in a screenshot this session and has since been rotated.)

---

## 8. OPEN ITEMS / NEXT STEPS (in priority order)

1. ✅ **DeepSeek 2× reproducibility — DONE** (`eval_deepseek_run1/2.*`): faithfulness ✅ (spread 0), recall delta ✅ (spread 0), macro-F1 delta ⚠️ (0.0145 drift = small residual MoE noise). **Re-commit the clean run as canonical:** `cp eval_deepseek_run1.json eval_deepseek.json && cp eval_deepseek_run1.md eval_deepseek.md` (the existing `eval_deepseek.*` is the earlier outlier single run).
2. **Website / deploy:** two model boxes — **Claude = benchmark numbers, DeepSeek = demo (chosen for cost)** — never merged. Add a **"How we measured"** section featuring the temp-noise catch. Lead with the cross-model anchorer lift (+0.30/+0.31), not cost.
3. **(Quality, optional) Diagnose the 3 wrong-location findings** (likely `uncapped_liability`: precision ~0.36–0.40, faithfulness ~0.53–0.80). Instrument a run to log which accepted findings miss the gold region BEFORE tuning `min_ratio`. Evidence first, not guesses.
4. **(Optional) Full 510 split** for the firm number — cheap on DeepSeek (~$2). Won't change the narrative; skip unless a reviewer pushes on sample size.
5. **Portfolio site integration** — this ships on the ONE unified portfolio site (see `portfolio-one-website` decision): Vercel routes + shared VPS containers + shared Postgres/Langfuse. AuditAgent needs the same `/health`, auto-run, rate-limit treatment as RetrofitGPT.

---

## 9. LOCKED DECISIONS — DO NOT RE-OPEN

- Market = **Australia**, Big 4. P2 = **AuditAgent / CUAD contract review**.
- **LangGraph** orchestration. v1 = **5 clauses** (Change of Control · Uncapped Liability · Auto-renewal Notice · Non-Compete · Termination for Convenience).
- Stack: FastMCP · Pydantic v2 · FastAPI · **DeepSeek V4 Flash (prod/demo — cost)** · **Claude Sonnet 4.6 (benchmark)** · Langfuse · Next.js. Model-router story is real: same pipeline, swap the key. **A model's published numbers belong only to that model** — never advertise a number a given prod model can't hit.
- **L1 (detection, what CUAD scores) ≠ L2 (severity, deterministic rule layer).** Never conflate; never present severity as measured accuracy.
- **M1 invariant:** every Citation satisfies `raw_text[start:end] == quote`. `verify_against` stays strict. Fuzzy matching only *locates*; the citation is always a literal raw slice. Weakening this defeats the entire project.

---

## 10. HOW TO COMMUNICATE WITH TAASH (adopt immediately)

- ❌ Never open with agreement. First sentence challenges an assumption / leads with the uncomfortable truth.
- 🏷️ Tag confidence: **[Certain] / [Likely] / [Guessing]**. If mostly guessing, say so first.
- 🚫 Banned: "Great question", "You're absolutely right", "That makes sense", "Absolutely", "Definitely".
- 👁️ **Visual / systems thinker:** full picture first, then steps. Tables, bullets, a few emojis. ❌ no walls of text. Be concise.
- 🧩 On "I don't understand" → drop jargon, use a concrete everyday analogy with real numbers.
- 🎓 She's **learning agentic AI to land a Big-4 AI-engineer / solution-architect role.** Teach as you build. Conceptually sharp; needs exact step-by-step for terminal/Python ops (give full copy-paste commands, NO inline `#` comments — her zsh mis-parses them).
- 🛡️ Don't fold under pushback without new information. Job = improve her decisions, not validate them.
- 💸 She watches API spend — quote costs, prefer the cheapest run that answers the question.

---

## 11. FIRST MOVES FOR THE NEW CHAT

1. Read this file + skim `MASTER_HANDOFF_AuditAgent.md` + open `eval_report.md` and `eval_deepseek.md`.
2. Confirm 60 tests green: `PYTHONPATH=src python3.14 -m pytest -q`.
3. Re-commit the clean DeepSeek run if not done (§8.1): `cp eval_deepseek_run1.{json,md}` over `eval_deepseek.{json,md}`.
4. Then move to the **website / deploy** (§8.2) — the benchmark work is COMPLETE (both models 2× checked).

_End of handoff._
