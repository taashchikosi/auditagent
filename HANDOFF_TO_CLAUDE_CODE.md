# 🤝 HANDOFF → Claude Code — AuditAgent M4 (deploy)

**Read this whole file first. It is the single source of truth for the next session.**
_Last updated: 13 June 2026. Prior context: `HANDOFF_AuditAgent_GateFix_COMPLETE.md` (eval work, DONE), `CASE_STUDY_n102_wobble.md` (the n=102 story), `MASTER_HANDOFF_AuditAgent.md` (project bible)._

---

## 0. TL;DR

AuditAgent (citation-anchored CUAD contract-review agent) is **M1–M3 complete with a real, reproducible n=102 benchmark**. A deployment-readiness audit (13 Jun) cleared the three red blockers — **it is now demo-deployable**. What remains is **M4: get it live on the shared host with durable state.** All work is local; **73 tests pass**. Your job is M4, in the priority order in §5.

**FIRST ACTION:** finalize the uncommitted commit (see §3) — the previous session built the blocker fixes but a filesystem-mount quirk left them uncommitted.

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
| Git repo initialised | ✅ first commit `f898ad2` |
| **Rate-limit + bearer-token gate** on paid routes | ✅ `security.py` + 7 tests |
| **Pinned deps** (`requirements.lock`) + reproducible Dockerfile | ✅ |
| README refreshed with real numbers | ✅ |
| **Test suite** | ✅ **73 passing** · ruff clean |
| Final quality pass (13 Jun): proxy-aware rate-limit (X-Forwarded-For), uuid session ids, `/health` milestone→M3, 404 on unknown session, version→0.3.0 | ✅ |

**Headline result (defensible):** the fuzzy-but-verified citation anchorer lifts faithfulness **+0.29** (DeepSeek n=102) / **+0.33** (Claude n=20). The gate is a **precision/integrity mechanism — do NOT claim "agent beats single-shot."**

---

## 3. ⚠️ FIRST: finalize the uncommitted commit

The blocker fixes are written to disk but **uncommitted** (the previous session ran in a sandbox whose mount couldn't delete `.git/index.lock`). On this machine you have full permissions:

```
cd ~/Documents/Claude/Projects/Agentic\ AI\ Portfolio/auditagent
rm -f .git/index.lock .git/HEAD.lock
PYTHONPATH=src python3.14 -m pytest -q
git add -A
git commit -m "Deployment hardening: rate-limit + token gate, pinned deps, README refresh"
git remote -v
git push -u origin main
```

**Acceptance:** `pytest` shows **73 passed**; `git status` clean; `git push` succeeds to the repo Taash created; the CI workflow (`.github/workflows/eval.yml`) runs and goes green on GitHub. This is the moment CI runs for the first time ever — watch it.

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

## 5. M4 — remaining work, in priority order

### 5.1 🔴 Push + green CI (≈15 min) — do this first (it's §3)
Acceptance: remote has the code, CI passes. Consider adding `ruff check` as a CI step (see §7 for the 5 known cosmetic lints to fix first, or add `--exit-zero`).

### 5.2 🔴 Deploy the container to the shared VPS (port 8002)
- Build from the pinned Dockerfile; run beside RetrofitGPT (8001).
- Wire `/health` to the unified site's 🟢/🔴 status dot.
- Set `AUDITAGENT_API_TOKEN` + `DEEPSEEK_API_KEY` in the host env (NOT in the image).
- Acceptance: `GET /health` returns 200 with `"citation_anchoring":"ok"`; a paid route returns 401 without the token and 200 with it; rate-limit returns 429 past the cap.

### 5.3 🟡 Durable state (the real production gap)
Currently everything is in-process and lost on restart:
- **LangGraph checkpointer** is `MemorySaver` (`graph.py:137`) → swap to `langgraph.checkpoint.postgres.PostgresSaver` so a paused HITL run survives a restart/redeploy.
- **`_SESSIONS` dict** (`app.py:73`) → back with the shared Postgres (keyed by a real session id, not `id(session)`).
- **Audit log** is SQLite/`:memory:` (`audit_log.py:46`) → point `db_path` at the shared Postgres. The hash-chain logic is storage-agnostic; only the connection changes (note: sqlite3 → psycopg means the INSERT/SELECT SQL needs a parametrise-style check, it's not literally zero-change).
- Acceptance: kill the container mid-HITL, restart, resume the decision successfully; `verify_chain()` still true across a restart.

### 5.4 🟡 Langfuse tracing
- Wrap the LangGraph nodes / LLM calls with Langfuse so each run is a trace (the observability story in ARCHITECTURE.md). Shared Langfuse instance per `portfolio-one-website` decision.
- Acceptance: a `/review` call produces a visible trace with per-node spans + token usage.

### 5.5 🟢 Next.js UI route in the unified site
- Click-to-source provenance: the UI calls `get_span_text` (already an MCP tool) to highlight the exact cited span.
- Acceptance: the demo contract reviews end-to-end in the browser with citations that highlight source text.

### 5.6 🟢 Optional polish
- Harden injection beyond regex if time (it's defense-in-depth today).
- (Already done in the 13 Jun quality pass: ruff is clean, version bumped to 0.3.0, Makefile/health/docstrings de-staled, proxy-aware rate-limit, uuid session ids, 404 on unknown session.)

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

## 7. Known limitations (honest — keep them honest)

- **Durability:** HITL/sessions/audit log are in-process/SQLite → lost on restart (fixed by 5.3). This is the main thing between "demo" and "production".
- **Injection detection** (`injection.py`) is **regex-only** — defense-in-depth, bypassable by obfuscation. The primary integrity control is the citation gate, not this.
- **MCP boundary:** ARCHITECTURE.md says agents reach the contract "only through MCP tools"; in practice the pipeline calls the same functions directly (the MCP server is a parallel, demonstrable surface). Don't oversell this in the demo.
- **Rate-limit store** is in-process (per-container). Correct for the single always-on container; a multi-replica deploy needs Redis behind the same `security.py` interface. It IS proxy-aware (reads `X-Forwarded-For`).
- **CI vs Docker deps:** CI installs `.[dev]` (latest, catches breakage early); Docker installs `requirements.lock` (pinned, reproducible). Intentional.

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
