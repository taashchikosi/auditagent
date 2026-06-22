# 🤝 HANDOFF → Claude Code — AuditAgent M4 (deploy)

**Read this whole file first. It is the single source of truth for the next session.**
_Last updated: 13 June 2026. Prior context: `HANDOFF_AuditAgent_GateFix_COMPLETE.md` (eval work, DONE), `CASE_STUDY_n102_wobble.md` (the n=102 story), `MASTER_HANDOFF_AuditAgent.md` (project bible)._

---

## 0. TL;DR

AuditAgent (citation-anchored CUAD contract-review agent) is **M1–M3 complete with a real, reproducible n=102 benchmark**. A deployment-readiness audit (13 Jun) cleared the three deploy blockers and the codebase is clean (73 tests, ruff green). **It is NOT "done" — M4 is real production hardening** (durable state, real injection defense, observability, integration tests, UI), all required (§5). Your job is to take it to production-grade, in the order in §5, clearing the Definition of Done in §5.9.

**FIRST ACTION:** all work is committed locally (latest `99290aa` on branch **`master`**) but **not yet pushed**, and the branch name **mismatches CI**. See §3 — it's a 2-command fix, and until it's pushed to the remote Taash created, the code exists nowhere but her disk and CI has never run.

---

## 0.1 ⛔ HARD RULE (overrides everything below)

**Never compromise quality or thoroughness to rush to deployment. No skipped corners, no shortcuts. Aim for production-grade.** This rule overrides any line in this or any other project doc that says or implies "good enough for the demo," "optional," "ship the MVP," or "do it later." If you find such framing, treat the item as required work. "Demo-deployable" ≠ "done"; the bar is §5.9. (The one allowed exception is a gap Taash **explicitly** de-scopes in writing — and even then, flag it, don't assume it.)

---

## 1. What this project is (one paragraph)

An autonomous contract-review agent: a 4-agent **LangGraph** pipeline (Extractor → Classifier → RiskAnalyzer → Reviewer) that flags 5 high-risk clause types and **cites the exact source span for every finding or rejects it** (the M1 invariant). Detection is measured against **CUAD** (real expert labels). Production model is **DeepSeek V4 Flash** (cost); **Claude Sonnet 4.6** is the benchmark twin. Ships as one container on a shared VPS, port 8002, as a route in a unified portfolio site (alongside RetrofitGPT).

---

## 2. Current state — what's DONE (don't redo)

| Area | Status |
|---|---|
| M1 parser/chunker, offset-exact spans, FastMCP tool layer | ✅ |
| M2 LangGraph 4-agent pipeline + **citation gate** + HITL + injection flag + hash-chained audit log | ✅ |
| M3 CUAD eval harness, baseline ladder B0/B1/B2, per-clause F1 | ✅ |
| **Real n=102 DeepSeek benchmark, reproducible at temp 0** | ✅ committed `eval_deepseek_full.{json,md}` |
| `uncapped_liability` precision fix (0.20→0.39, recall held) | ✅ `clauses.py` definitions + `test_clause_definitions.py` |
| Git repo initialised + hardening committed | ✅ `f898ad2` (init) → `99290aa` (hardening), branch `master`, **not pushed yet** |
| **Rate-limit + bearer-token gate** on paid routes | ✅ `security.py` + 7 tests |
| **Pinned deps** (`requirements.lock`) + reproducible Dockerfile | ✅ |
| README refreshed with real numbers | ✅ |
| **Test suite** | ✅ **73 passing** · ruff clean |
| Final quality pass (13 Jun): proxy-aware rate-limit (X-Forwarded-For), uuid session ids, `/health` milestone→M3, 404 on unknown session, version→0.3.0 | ✅ |

**Headline result (defensible):** the fuzzy-but-verified citation anchorer lifts faithfulness **+0.29** (DeepSeek n=102) / **+0.33** (Claude n=20). The gate is a **precision/integrity mechanism — do NOT claim "agent beats single-shot."**

---

## 3. ⚠️ FIRST: push to the remote + fix the branch/CI mismatch

Everything is **committed locally** (`f898ad2` init → `99290aa` hardening, 73 tests pass) but **not pushed**, and the local branch is **`master`** while the CI workflow triggers on **`main`** (`.github/workflows/eval.yml` → `on: push: branches: [main]`). Pushing `master` as-is will NOT run the push-CI. Rename to `main` (standard, matches CI), wire the remote Taash created, and push:

```
cd ~/Documents/Claude/Projects/Agentic\ AI\ Portfolio/auditagent
git branch -M main
git remote -v
```

If no remote is listed, add the one Taash created (replace the URL):

```
git remote add origin https://github.com/<her-user>/<her-repo>.git
```

Then push and confirm CI:

```
git push -u origin main
```

**Acceptance:** `git push` succeeds; the branch on GitHub is `main`; the CI workflow (`.github/workflows/eval.yml`) runs on the push and goes **green** (it runs `pytest` + the deterministic CUAD eval — no key needed). This is the first CI run ever — watch it. If CI should also publish real-model numbers, add `DEEPSEEK_API_KEY` to the repo secrets and have the eval step use it (the workflow has a comment showing where).

> Alternative if Taash prefers to keep `master`: change the workflow's `branches: [main]` to `[master]` instead of renaming. Renaming to `main` is the recommended path.

---

## 4. Environment & how to run (this machine)

- **Python:** use `python3.14` (the default `python3` is 3.9 — too old; needs ≥3.10).
- **Install:** `make install PYTHON=python3.14` (or `pip install -e ".[dev]"`).
- **Run from source:** prefix `PYTHONPATH=src` to pick up edits without reinstalling.
- **Tests (offline, no key):** `PYTHONPATH=src python3.14 -m pytest -q` → 73 passed.
- **Serve locally:** `make serve` → FastAPI on :8002 (`/health`, `/review/sample`, `/compare/sample`, `/hitl/decide`).
- **Keys** live in the terminal env only — never in chat, code, or screenshots.
  - `DEEPSEEK_API_KEY` wins precedence over `ANTHROPIC_API_KEY` for BOTH detector and gate.
  - Real eval: `bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json` (after `python scripts/download_cuad.py --extract`). DeepSeek 2× ≈ $1.50 / ~30 min.
- **Security env (production):** set `AUDITAGENT_API_TOKEN` to enforce the bearer gate; `AUDITAGENT_RATE_LIMIT` (default 20) / `AUDITAGENT_RATE_WINDOW_SEC` (default 60). Gate fails **open** when the token is unset (local/demo).

---

## 5. M4 — remaining work (ALL items required for "done")

> **Per the project HARD RULE (§0.1): every item below is REQUIRED for production-grade.**
> None are "optional" or "demo-only". Do them in this order (dependencies first); do not stop early or skip a step because the demo "looks fine." The Definition of Done in §5.9 is the bar — clear all of it.

### 5.1 🔴 Push + green CI — do first (it's §3)
- Push to `main`; CI green. **Add `ruff check src tests` AND a coverage gate to CI** (ruff is already clean). CI must fail the build on lint error or a dropped test.
- Acceptance: remote on `main`; CI runs `pytest` + `ruff` + deterministic eval and is green.

### 5.2 🔴 Real-model integration tests (don't rely only on the offline stub)
- The 73 tests use the deterministic provider. Add a **keyed integration test** (marked `@pytest.mark.integration`, skipped without a key) that runs `/review` against real DeepSeek and asserts: every accepted finding's citation re-slices the contract exactly (M1 invariant holds end-to-end on the real model), and an injected contract is flagged.
- Acceptance: `pytest -m integration` passes with `DEEPSEEK_API_KEY` set; the offline suite stays green and fast without a key.

### 5.3 🔴 Durable state (the core production gap — NOT deferrable)
Everything is in-process today and lost on restart. All three must move to the shared Postgres:
- **LangGraph checkpointer** `MemorySaver` (`graph.py:137`) → `PostgresSaver` so a paused HITL run survives restart/redeploy.
- **`_SESSIONS` dict** (`app.py`) → shared Postgres, keyed by the real session id.
- **Audit log** SQLite/`:memory:` (`audit_log.py:46`) → shared Postgres. The hash-chain is storage-agnostic, but sqlite3 → psycopg needs a real parametrised-SQL pass + a migration; **re-run `verify_chain()` against Postgres, don't assume.**
- Acceptance: kill the container mid-HITL, restart, resume the decision successfully; `verify_chain()` true across a restart; concurrent reviews don't collide.

### 5.4 🔴 Production-grade prompt-injection defense (regex is not enough)
- `injection.py` is regex-only — bypassable by obfuscation/unicode/paraphrase. For an assurance product this must be real: add structural defenses (delimiter/quote-only extraction, an injection-classification check, and a test that the agent never downgrades risk on an adversarial set) and **measure a pass-rate over an adversarial corpus**, reported like the CUAD metrics.
- Acceptance: documented adversarial set with a measured refusal rate; obfuscated-injection cases the old regex missed are caught.

### 5.5 🔴 Observability — Langfuse tracing + structured logging
- Wrap LangGraph nodes / LLM calls with Langfuse (shared instance per `portfolio-one-website`); add structured request logging + error capture on the API.
- Acceptance: a `/review` call produces a trace with per-node spans + token usage; errors are logged with context, never swallowed.

### 5.6 🔴 Resilience + load/security verification
- Verify graceful behaviour under failure: provider timeout/5xx (retry path already exists — test it), malformed/oversized contract input (add request-size limits), and the rate-limit/token gate under concurrent load.
- Acceptance: a documented load/abuse test showing 429s engage, the token gate holds, and a provider outage degrades gracefully (clear error, no crash, audit log intact).

### 5.7 🔴 Next.js UI route in the unified site
- Click-to-source provenance: the UI calls `get_span_text` (already an MCP tool) to highlight the exact cited span. Include the B1-vs-agent "catch" view and the injection-refusal demo.
- Acceptance: the demo contract reviews end-to-end in the browser with citations that highlight source text; loading/error states handled.

### 5.8 🟡 Full-corpus benchmark + cross-model confirmation
- Re-run the n=102 eval after the 5.4 injection/prompt changes (prompts changed → numbers can move). Confirm the anchorer lift and uncapped precision hold; keep `eval_deepseek_full.{json,md}` canonical and reproducible.
- Acceptance: committed, reproducible (2×, temp 0) numbers that match the README claims after all prompt changes.

### 5.9 ✅ Definition of Done (the production-grade bar — all must be true)
1. On `main`, CI green (pytest + ruff + coverage threshold + deterministic eval).
2. Real-model integration test passing; M1 invariant verified end-to-end on the live model.
3. State durable across restart (sessions, HITL checkpoint, audit log on Postgres; `verify_chain()` holds).
4. Injection defense measured on an adversarial set, not regex-only.
5. Langfuse traces + structured logging + graceful failure on provider/`input` errors.
6. Load/abuse test documented; token gate + rate limit verified under concurrency.
7. UI live on the unified site with click-to-source; `/health` drives the status dot.
8. README/ARCHITECTURE/case-study numbers match the committed reproducible eval.
9. No stubs, no TODOs, no swallowed exceptions in shipped paths; secrets only in env.

_(Already complete from the 13 Jun quality pass: ruff clean, version 0.3.0, de-staled docs, proxy-aware rate-limit, uuid session ids, 404 on unknown session.)_

---

## 6. File map

| File | Role |
|---|---|
| `src/auditagent/graph.py` | LangGraph supervisor; **MemorySaver → PostgresSaver in 5.3** |
| `src/auditagent/pipeline.py` | `run_review` / `run_single_shot` / `compare` entry points |
| `src/auditagent/app.py` | FastAPI surface; `_PAID` deps applied to LLM routes; in-memory `_SESSIONS` → Postgres in 5.3 |
| `src/auditagent/security.py` | **NEW** — token gate + rate limiter (in-memory; Redis for multi-replica) |
| `src/auditagent/agents/` | extractor, classifier, risk_analyzer, reviewer (the citation gate) |
| `src/auditagent/anchor.py` | fuzzy-but-verified anchorer (the headline contribution) |
| `src/auditagent/clauses.py` | 5 clause specs + **per-clause `definition`** (the uncapped fix) + L2 severity |
| `src/auditagent/models.py` | Pydantic schemas; **`verify_against` = the M1 invariant (DO NOT weaken)** |
| `src/auditagent/audit_log.py` | hash-chained tamper-evident log; SQLite → Postgres in 5.3 |
| `src/auditagent/llm/factory.py` | provider precedence DeepSeek → Claude → deterministic |
| `src/auditagent/eval/` | CUAD loader + scorer + 3-way runner |
| `scripts/benchmark_twice.sh` | 2× reproducibility runner (supports `--full <path>`) |
| `requirements.lock` | **NEW** — 93 pinned deps; Dockerfile installs this then `--no-deps .` |
| `eval_deepseek_full.{json,md}` | **canonical real result (n=102)** |
| `CASE_STUDY_n102_wobble.md` | the measure→scale→root-cause→fix narrative |

---

## 7. Known gaps — to CLOSE before "done" (not accepted limitations)

Per the HARD RULE, these are not things to ship around — each maps to a required §5 task. Listed so nothing is forgotten.

- **Durability:** HITL/sessions/audit log are in-process/SQLite → lost on restart. **Close in 5.3** (Postgres). This is the main thing between "demo" and "production" — so it is required, not deferred.
- **Injection defense** (`injection.py`) is regex-only, bypassable. The citation gate is the primary integrity control, but for an assurance product the injection defense must be real and measured. **Close in 5.4.**
- **Real-model coverage:** tests use the deterministic stub; the live model is only exercised manually. **Close in 5.2.**
- **Observability:** no Langfuse/structured logging yet. **Close in 5.5.**
- **MCP boundary:** ARCHITECTURE.md says agents reach the contract "only through MCP tools"; in practice the pipeline calls the same functions directly. Either route agent contract-access through the MCP tools (preferred, matches the doc) or correct the doc — **don't leave the claim and the code disagreeing.**
- **Rate-limit store** is in-process (per-container), proxy-aware via `X-Forwarded-For`. Fine for one container; **if the deploy is multi-replica, move to Redis (5.6).**
- **CI vs Docker deps:** CI installs `.[dev]` (latest, catches breakage early); Docker installs `requirements.lock` (pinned). Intentional — keep.

---

## 8. LOCKED decisions — DO NOT re-open

- **M1 invariant:** every `Citation`/`Span` satisfies `raw_text[start:end] == quote`. `verify_against` stays strict. Fuzzy matching only *locates*; the stored citation is always a literal raw slice. **Weakening this defeats the entire project.**
- **L1 (detection, what CUAD scores) ≠ L2 (severity, deterministic rule layer).** Never present severity as measured accuracy.
- **Models:** DeepSeek V4 Flash (prod/demo — cost) · Claude Sonnet 4.6 (benchmark). Same pipeline, swap the key. A model's published numbers belong only to that model.
- **Market = Australia, Big 4.** v1 = 5 clauses (Change of Control · Uncapped Liability · Auto-renewal Notice · Non-Compete · Termination for Convenience). 41 clauses = v1.1.
- **One unified portfolio site** (Vercel routes + shared VPS containers + shared Postgres/Langfuse). AuditAgent gets the same `/health`, rate-limit, container treatment as RetrofitGPT.
- **Temperature = 0** for all headline/benchmark numbers (reproducibility). DeepSeek is non-deterministic at temp 0 on the hardest clause only — that's documented, not a bug to chase.

---

## 9. Communication style for Taash

- Lead with the uncomfortable truth; never open with agreement. Tag confidence **[Certain]/[Likely]/[Guessing]**.
- Visual/systems thinker: full picture first, then steps. Tables + bullets, not walls of text. Concise.
- She's learning agentic AI for a Big-4 AI-engineer / solution-architect role — **teach as you build**, give exact copy-paste terminal commands (her zsh mis-parses inline `#` comments — keep commands comment-free).
- Quote API costs before spending; prefer the cheapest run that answers the question.

_End of handoff._
