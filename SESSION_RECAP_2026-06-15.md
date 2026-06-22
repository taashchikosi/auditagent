# 📋 Session Recap — AuditAgent: n=102 benchmark → fix → deploy audit → hardening

_Generated 15 June 2026. Covers the full working session. Companion to `HANDOFF_TO_CLAUDE_CODE.md` (forward-looking) and `CASE_STUDY_n102_wobble.md` (the narrative)._

---

## 0. What this session accomplished (one screen)

1. **Prepped + ran the full n=102 CUAD benchmark** (was n=20) — and corrected a "510 contracts" mislabel to the real **102-contract held-out test split**.
2. **The bigger sample broke a claim:** "faithfulness perfectly reproducible" failed at n=102 (spread 0.069). Investigated → isolated → root-caused → fixed → confirmed.
3. **Root cause = a missing prompt definition** on one clause. Fixed it: `uncapped_liability` precision **0.20 → 0.39 with zero recall loss**; run-to-run wobble on the gated output **→ 0.000**.
4. **Ran a full deployment-readiness audit.** Verdict: strong agent, weak scaffolding. Cleared 3 red blockers (git, auth/rate-limit, pinned deps), refreshed the README.
5. **Quality pass:** fixed real issues (proxy-aware rate limiting, uuid session ids, `/health` milestone, 404 handling), cleared all ruff lints, bumped version.
6. **Wrote the Claude Code handoff** for M4.
7. **New HARD RULE set** (production-grade, no shortcuts) — realigned the docs to it.

**Test suite went 60 → 73 green. Ruff: clean.**

---

## 1. The n=102 benchmark + the 510 correction

- The shipped headline was **n=20** — and the handoff itself flagged the detection deltas as "within noise." For a Big-4 reviewer, "n=20, within noise" reads as *underpowered*.
- The download script extracts `test.json` = **102 contracts** (the standard CUAD held-out test split), **NOT 510** as the old handoff claimed. (`CUADv1.json`=510 mixes in train, meaningless for a no-fine-tuning LLM; `train`=408.) 102 is the correct, methodologically clean firm number.
- Patched `scripts/benchmark_twice.sh` to accept a `--full <path>` arg (it previously only ran the 20-sample), so the firm number is **2× reproducibility-checked**, not a one-off. Validated offline (bash-3.2-safe, harness deterministic).

---

## 2. The wobble — and what it revealed

The n=102 DeepSeek run **overturned three optimistic n=20 claims**:

| Metric | n=20 (claimed) | n=102 (real) |
|---|---|---|
| B1 macro-F1 | 0.777 | 0.605 (20-sample was easy) |
| High-risk recall | 0.958 | 0.890 |
| Faithfulness reproducibility | spread **0.000** | spread **0.069** 🚨 |
| Gate detection delta | "neutral" | −0.01 to −0.03 recall |

**Investigation (evidence-first):**
- Ran the **deterministic provider 2× on n=102** → spread 0.000 everywhere ⇒ **the harness is bit-for-bit deterministic; the wobble is the real model.**
- Diffed per-clause → the wobble was **one clause: `uncapped_liability`** (Δfaith 0.089; the other 4 clauses ≤0.013, three exactly 0.000).
- That clause had the **lowest support (13)** and **worst precision (0.204)** — the model was over-flagging any liability language.
- **Root cause:** the classifier sent the model only `- uncapped_liability: Uncapped Liability` — *no definition* — plus a recall-first prompt. It was guessing what "uncapped" meant and never told that a *capped* clause is a negative.

---

## 3. The fix + confirmation

**Fix:** added a one-line `definition` per clause (`clauses.py`), wired into both Claude + DeepSeek prompt menus, with the explicit negative for the weak clause: *"a clause that CAPS or LIMITS liability is the OPPOSITE — do NOT flag it."* Locked with a regression test (`test_clause_definitions.py`).

**Confirmed on a fresh n=102 2× run:**

| Signal | Pre-fix | Post-fix |
|---|---|---|
| `uncapped_liability` precision | 0.204 | **0.385** (~doubled) |
| `uncapped_liability` recall | 0.769 | **0.769** (unchanged — no trade) |
| B2 citation-faithfulness spread (gated output) | 0.020 | **0.000** ✅ reproducible |
| Overall B2 macro-F1 | 0.589 | **0.649** |
| High-risk recall | 0.879 | **0.912** |

**Headline result (defensible):** the fuzzy-but-verified citation anchorer lifts faithfulness **+0.29** (DeepSeek n=102) / **+0.33** (Claude n=20) — same fix, two model families. The gate is a **precision/integrity mechanism**, *not* an accuracy booster — do NOT claim "agent beats single-shot."

Committed `eval_deepseek_full.{json,md}` as canonical; wrote `CASE_STUDY_n102_wobble.md`.

---

## 4. Deployment-readiness audit — verdict

**NOT publicly deployable as found; demo-deployable after fixes.** The agent logic was strong; the gaps were all scaffolding.

| Axis | Grade |
|---|---|
| Agent logic & correctness | A− |
| Eval integrity | A |
| Security/integrity | B |
| Deployment infra | D (the blockers) |
| Docs freshness | C |

**🔴 Blockers found & fixed:**
1. **Not a git repo** → `git init` + committed (`f898ad2` → `99290aa`).
2. **No auth / no rate-limit** on paid LLM routes (cost/abuse vector) → `security.py`: bearer-token gate + in-memory rate limiter; `/health` stays open. +7 tests.
3. **Unpinned dependencies** → `requirements.lock` (93 pinned) + reproducible Dockerfile (`-r lock` then `--no-deps .`).
4. **Stale README** → real n=102 numbers, accurate M4 status, security env docs; dropped "510"/"pending".

---

## 5. Quality pass — real issues fixed (not just cosmetics)

| Issue | Severity | Fix |
|---|---|---|
| Rate limiter keyed on `request.client.host` → collapses to one bucket behind the VPS proxy | 🔴 real bug | now reads `X-Forwarded-For` |
| Session IDs used `id(session)` (predictable, GC-collision) | 🟡 | `uuid4().hex` |
| `/health` reported `"milestone":"M1"` (stale) | 🟡 | now `M3` |
| `/hitl/decide` returned 200 + error body on unknown session | 🟡 | proper `404` |
| 5 ruff lints (1 real unused var + data literals) | 🟢 | cleared — **ruff fully clean** |
| version `0.1.0`/"M1", stale docstrings/Makefile | 🟢 | bumped `0.3.0`, de-staled |

Confirmed **CORS middleware** is present in `app.py` (env `AUDITAGENT_ALLOWED_ORIGINS`, default `*`) — so the Vercel→backend browser calls won't be blocked.

---

## 6. The HARD RULE (new, all projects)

> **Never compromise quality or thoroughness to rush to deployment. No skipped corners, no shortcuts. Always aim for production-grade. Overrides any contradicting line in any project doc.**

Applied immediately:
- Saved to memory (`quality-over-speed-hard-rule`).
- `HANDOFF_TO_CLAUDE_CODE.md`: added a hard-rule banner (§0.1); **all M4 items reclassified as required** (added real-model integration tests, real injection defense, observability, resilience/load test); added a **Definition of Done** (§5.9).
- `RUN_DEPLOY.md`: "in-process for the demo" reframed as a known gap that must be closed.
- The guardrail against never-shipping: the §5.9 Definition of Done. De-scope only in writing, never silently.

---

## 7. Files created / changed this session

**Created:** `security.py`, `tests/test_security.py`, `tests/test_clause_definitions.py`, `requirements.lock`, `RUN_FULL_EVAL.md`, `CASE_STUDY_n102_wobble.md`, `HANDOFF_TO_CLAUDE_CODE.md`, this recap.
**Modified:** `scripts/benchmark_twice.sh` (--full), `clauses.py` (+definitions), `llm/claude.py` + `llm/deepseek.py` (menu + lint), `app.py` (security deps, uuid, M3, 404), `eval/scorer.py` + `eval/runner.py` (lint), `injection.py` (lint), `Dockerfile` (pinned), `Makefile`, `README.md`, `__init__.py` (v0.3.0), `RUN_DEPLOY.md`.
**Eval artifacts:** `eval_deepseek_full.{json,md}` (canonical, post-fix), `eval_deepseek_full_PREFIX_*` (pre-fix baseline).

---

## 8. Current state & what's next

- **State:** M1–M3 complete; real reproducible n=102 benchmark in; 73 tests green; ruff clean; committed locally (`99290aa` on `master`), **not yet pushed**.
- **Immediate next (Claude Code, §3 of the handoff):** `git branch -M main` → add remote → `git push -u origin main`; watch first CI run (CI triggers on `main`, current branch is `master` — fix the mismatch).
- **Then M4 (all required, see handoff §5):** real-model integration tests · durable Postgres state (sessions + HITL checkpoint + audit log) · real injection defense · Langfuse + logging · resilience/load test · Next.js UI route. Clear the Definition of Done (§5.9).

---

## 9. Locked decisions referenced this session

- **M1 invariant:** every citation satisfies `raw_text[start:end] == quote`; `verify_against` stays strict. Fuzzy matching only *locates*.
- **L1 (detection, CUAD-scored) ≠ L2 (severity, deterministic rule).** Never present severity as measured accuracy.
- **Models:** DeepSeek V4 Flash (prod/demo — cost) · Claude Sonnet 4.6 (benchmark). A model's numbers belong only to that model.
- **Temperature = 0** for all headline numbers. DeepSeek is non-deterministic at temp 0 on the hardest clause only — documented, not a bug to chase.
- **One unified portfolio site** (Vercel routes + shared VPS containers + shared Postgres/Langfuse). Market = Australia, Big 4. v1 = 5 clauses.
