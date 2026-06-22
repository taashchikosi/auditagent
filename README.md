# AuditAgent

**Autonomous contract-review agent that flags risky clauses, cites the exact source text, and proves its accuracy on expert-labelled data.**

> In 2025, Deloitte Australia partially refunded the federal government after an AI-assisted report contained fabricated citations. AuditAgent is built to make that failure impossible: **every finding must quote the exact contract text it came from, or it is rejected.**

`Status: 🟢 M1–M3 complete & deployed live · 108 tests green · M4 production-hardening in progress (opt-in durable Postgres audit log + LangGraph checkpointer + HITL session store, Langfuse tracing). (M1: parsing · M2: pipeline + citation gate · M3: CUAD eval harness on the n=102 held-out test split.)`

> ✅ **Headline re-baselined (22 Jun 2026).** The old `0.912` was built on a DeepSeek alias the provider silently re-pointed; re-running on a **pinned** `deepseek-v4-flash`, n=102 ×3, gives **macro-F1 0.674 (spread 0.013, reproducible)**. Agent high-risk recall **0.795 ± 0.044** is *below* single-shot's **0.828** — so the **citation gate is an integrity / faithfulness mechanism, not an accuracy booster, and the agent does not "beat single-shot."** Citation-faithfulness figures are too run-to-run noisy on this model to publish as point estimates (the naive→gate *lift* is large, ~+0.35 mean, reported directionally). Full numbers in the [results section](#real-model-result--re-baselined-deepseek-v4-flash-pinned-full-cuad-test-split-n102-temp-0-3-mean--spread) below.

---

## Why this project

Contract review is the highest-volume agentic use case at the Big 4 (Deloitte Zora, KPMG Clara). Most portfolio demos can't put a *number* on accuracy. This one can — it's evaluated on the held-out **test split (102 contracts)** of [CUAD](https://www.atticusprojectai.org/cuad) (a dataset of 510 real contracts, 41 expert-defined clause types, 13,000+ lawyer labels, CC BY 4.0). The 102-contract figure is the number scored; 510 is the full corpus size.

Two un-fakeable proofs of depth:

1. **Citation enforcement** — a finding with no exact-span quote is auto-rejected and re-run.
2. **Measurable accuracy** — real precision / recall / F1 against ground-truth labels, beating a published baseline.

> 🇦🇺 *Evaluated on CUAD (US corpus, expert-labelled); the architecture is corpus-agnostic and deployable on Australian contracts. Clause risk is jurisdiction-neutral.*

---

## The thesis (this project has a point of view)

The 2025 **ContractEval** benchmark ran 19 LLMs on CUAD and found they are *"lazy"* — they falsely answer "no related clause" when one is present. In contract review, a **false negative is the dangerous error** (you miss the indemnity that sinks the deal).

**The bet:** retrieval-first classification + a citation gate that forces the model to quote evidence or admit uncertainty will **raise recall on rare high-risk clauses** versus single-shot prompting. Falsifiable, and measured (M3).

---

## What's built now (Milestone 2)

Four stages are wired through **LangGraph** — and they are *deliberately* deterministic except where judgment is actually needed. Parsing, severity, and the mandatory-clause checklist are plain code (knowing when **not** to call an LLM is part of the design). The one genuinely agentic component is the **Reviewer**: an `act → verify → reflect → retry → decide` loop bounded by a retry budget, whose per-attempt trace is recorded and streamed. So this is a **deterministic workflow with one agentic verification loop**, not a chain of LLM calls relabelled "agents" — the distinction is Anthropic's own (*Building Effective Agents*). Every accepted finding quotes an exact source span or the loop rejects it.

| Delivered (M2) | Where |
|---|---|
| LangGraph pipeline: Extractor → Classifier → Risk Analyzer → Reviewer (streamed in real order via `/review/stream`) | `src/auditagent/graph.py`, `agents/`, `app.py` |
| **Citation gate** — explicit verify→reflect→retry loop; uncited/mis-cited findings rejected (1 retry, then reject); per-attempt trace | `agents/reviewer.py` |
| Deterministic checklist engine (pass/fail in code, not the LLM) | `checklist.py` |
| Immutable, hash-chained audit log (tamper-evident) | `audit_log.py` |
| Prompt-injection detector — agent refuses in-contract attacks (OWASP LLM01) | `injection.py` |
| HITL Approve/Escalate gate (resumable LangGraph interrupt) | `graph.py`, `/hitl/decide` |
| Pluggable LLM layer: deterministic (offline) + real DeepSeek/Claude adapters | `llm/` |
| Side-by-side B1-vs-agent comparison ("the catch") | `pipeline.py`, `/compare/sample` |

**Built in M1 (the foundation):** offset-exact parser + chunker, Pydantic schemas, FastMCP tool layer, `/health`. The M1 invariant still holds and everything builds on it:

```
raw_text[span.start_char : span.end_char] == span.text     # always, exactly
```

## Accuracy harness (Milestone 3) — measured against real CUAD labels

`make eval` scores detection against the **real CUAD held-out test split** (a
20-contract sample ships in the repo; the **full 102-contract test split** via
`make eval-full`). The scorer (`eval/scorer.py`) computes per-clause
precision/recall/F1, Precision@Recall, plus the metrics that matter for
contract review: **laziness rate** (present clauses wrongly called absent),
**citation faithfulness** (right answer *and* right evidence), and **high-risk
recall**. The baseline ladder is **B0** (published RoBERTa P@80%R ≈ 0.482) →
**B1** single-shot → **B2** agent.

### Real-model result — RE-BASELINED, DeepSeek **V4 Flash (pinned)**, full CUAD test split (n=102, temp 0, **3× mean ± spread**)

The headline number was re-established the honest way after the old `deepseek-chat` figure stopped reproducing: one **pinned** model, **3 runs**, report the mean and the run-to-run spread, and publish a metric **only if its spread is tight** (≤0.03).

| Metric | Mean (n=102, ×3) | Spread | Publishable? |
|---|---|---|---|
| **B2 macro-F1** | **0.674** | 0.013 | ✅ yes — reproducible |
| B1 single-shot high-risk recall | **0.828** | 0.022 | ✅ yes |
| B2 **agent** high-risk recall | **0.795** | 0.044 | ⚠️ drifty — quote only as ~0.79 ± 0.04 |
| Citation faithfulness — naive→gate **lift** | **≈ +0.35 mean** | — | ⚠️ directional — components are noisy (below) |
| Citation faithfulness (B2 gate / B1 fair / B1 naive) | 0.92 / 0.85 / 0.57 | 0.07 / 0.09 / 0.20 | 🚨 too noisy — do **not** publish as point estimates |

**The honest story (this is the asset, not a weakness):**
- **The agent does NOT beat single-shot.** On this re-baseline, agent high-risk recall **0.795 < single-shot 0.828** — the gate is a **precision / integrity** mechanism (every accepted finding is a verified exact quote; an unanchorable one can't pass), *not* an accuracy booster. Saying otherwise would be false.
- **The old `0.912` headline does not reproduce and is retired.** The current honest, reproducible number is **macro-F1 0.674** (spread 0.013).
- The **citation anchorer lift is large** (naive→gate ≈ **+0.35 mean**), but the absolute faithfulness figures swing run-to-run on this model (spread up to 0.20), so the lift is reported **directionally**, never as a clean `+0.29`.
- Cost / latency (measured from token usage): DeepSeek V4 Flash ~**$0.0032 · ~3.9 s** per contract.

> Source: `rebaseline/REBASELINE_SUMMARY.{json,md}` (`bash scripts/rebaseline.sh`, 22 Jun 2026). `eval_report.{json,md}` remains the offline deterministic floor that validates the measurement machinery in CI without a key.

### The catch (run `make demo-m2`)

On the pre-loaded contract, buyer perspective — deterministic provider, no keys:

```
B1 single-shot cites : Auto-renewal Notice, Termination for Convenience
AuditAgent cites     : all 5 (each with exact char offsets)
⭐ Caught by agent only: Change of Control, Non-Compete, Uncapped Liability
```

B1 misses clauses buried past its context window and can't anchor its quotes — the ContractEval "laziness" failure. The agent reads the whole document and the gate proves every citation. *(With `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` set, the same pipeline runs the real models; offline it uses a deterministic stand-in so the architecture is fully testable. Detection accuracy against CUAD labels is measured at M3.)*

---

## Quickstart

```bash
make install        # pip install -e ".[dev]"
make test           # all green — incl. offset round-trip + citation-gate tests
make demo           # M1: locate the 5 clauses by exact char offset
make demo-m2        # M2: the catch, citation gate, injection refusal, audit trail
make eval           # M3: CUAD baseline ladder (B0/B1/B2) + per-clause F1
make serve          # FastAPI :8002 → /health, /review/sample, /compare/sample, /hitl/decide
make mcp            # run the FastMCP contract-tools server
```

For the real model numbers (where DeepSeek is reachable):

```bash
export DEEPSEEK_API_KEY=sk-...
python scripts/download_cuad.py --extract        # writes the 102-contract test split
bash scripts/benchmark_twice.sh data/cuad/CUADv1_test.json   # real B1/B2, 2x reproducibility
```

---

## v1 thin slice (deliberate scope control)

v1 targets **5 high-value clause types**, not all 41:

`Change of Control · Uncapped Liability · Auto-renewal Notice · Non-Compete · Termination for Convenience`

Five clauses with a real F1 table beats 41 half-working. Expanding to 41 is v1.1.

---

## Roadmap

| Milestone | Threshold |
|---|---|
| **M1 ✅** | FastMCP runs; contract parses to offset-exact spans; `/health` up; contract pre-loaded |
| **M2 ✅** | 4-agent LangGraph pipeline; **citation gate** rejects uncited findings; HITL approve gate; injection resistance; B1-vs-agent side-by-side |
| **M3 ✅** | CUAD scorer + baseline ladder B0/B1/B2 + per-clause F1 + laziness/faithfulness + measured cost/latency, in CI. **Real DeepSeek numbers in at n=102, reproducible at temp 0.** |
| **M4 🔨 (in progress)** | Live on the shared host as a route in the unified portfolio site. **Done:** Docker + pinned deps, `/health`, bearer-token + rate-limit on paid routes; **opt-in Postgres backend** for the audit log + LangGraph checkpointer + HITL session store (`AUDITAGENT_DATABASE_URL`); **opt-in Langfuse tracing** (no-op when unset). **Remaining:** push to remote + CI run; re-baseline the headline number on a pinned model (Mac/live); real-model integration tests run on a keyed machine. |

---

## Stack (default — LangGraph, portable across all four Big 4)

Python · LangGraph · **FastMCP** · **Pydantic v2** · FastAPI (SSE) · Postgres + pgvector · hybrid BM25 + cross-encoder rerank · DeepSeek V4 Flash (primary) + Claude Sonnet 4.6 (citation gate) · bge-small embeddings · DeepEval + custom CUAD scorer · Langfuse · Next.js + assistant-ui.
*Azure-native is a documented optional ~half-day re-skin (KPMG/Microsoft-shop interviews only).*

## Deployment

Backend containerises onto the **shared always-on VPS** (port 8002, beside RetrofitGPT); the UI is a route in the unified portfolio site. `/health` drives the live-status dot. No cold start. Builds are reproducible — `requirements.lock` pins the full transitive set; the Dockerfile installs the lock then the package `--no-deps`.

**Edge protection on the paid (LLM-calling) routes** — `/review`, `/review/sample`, `/compare/*`:

```bash
export AUDITAGENT_API_TOKEN=...        # if set, these routes require Authorization: Bearer <token>; /health stays open
export AUDITAGENT_RATE_LIMIT=20        # requests per window per client (default 20)
export AUDITAGENT_RATE_WINDOW_SEC=60   # window length in seconds (default 60)
```

The token gate fails **open** when no token is configured (zero-config local demo) and enforces the moment the env var is present. Rate-limit state is in-process — correct for the single always-on container; a multi-replica deploy moves the window to Redis behind the same dependency interface.

## Configuration (env vars)

All optional — the package runs zero-config with sensible defaults. Keys/URLs go in the **terminal env only**, never in chat or committed files.

| Variable | Default | What it does |
|---|---|---|
| `AUDITAGENT_API_TOKEN` | unset (open) | If set, `/review` + `/review/sample` + `/compare/*` require `Authorization: Bearer <token>`; `/health` stays open. |
| `AUDITAGENT_RATE_LIMIT` / `AUDITAGENT_RATE_WINDOW_SEC` | `20` / `60` | Per-client request budget on the paid routes. |
| `AUDITAGENT_ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins (set to the Vercel domain in prod). |
| `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` | unset | Enable the real models. With neither set, a deterministic offline stand-in runs (CI-safe, **never** a benchmark). |
| `AUDITAGENT_CLASSIFIER` / `AUDITAGENT_REVIEWER` | provider precedence | Force the detector/gate model independently (e.g. `claude`) without unsetting keys — used to A/B model families. |
| `AUDITAGENT_DEEPSEEK_MODEL` | `deepseek-v4-flash` | Pin the DeepSeek model id explicitly (the alias re-point is what broke the headline number — always pin for an eval). |
| `AUDITAGENT_DEFINITION_GATE` | `0` (off) | Opt-in **definitional gate** — the citation gate's semantic second half. Only the for-cause/for-convenience **polarity rule** is active (it's a strict win: precision +0.039 *and* recall +0.017 on n=102). The keyword "require_any" rules were measured to **cost recall** and are intentionally disabled — see [`RUN_DEFINITION_GATE.md`](RUN_DEFINITION_GATE.md). |
| `AUDITAGENT_DATABASE_URL` | unset (in-memory) | **M4, opt-in.** Postgres connection string. When set, the audit log, the LangGraph checkpointer, and the HITL session store persist to Postgres instead of in-memory; unset = the current in-memory behaviour (what the test suite runs on). |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | unset (no-op) | **M4, opt-in.** When all set, each review run + node emits a Langfuse trace/span; unset = a no-op shim with zero overhead and no dependency required. |

## References

CUAD — Hendrycks et al., NeurIPS 2021 (CC BY 4.0). · ContractEval — arXiv 2508.03080 (2025), the "laziness" metric. · OWASP LLM Top 10 (LLM01 prompt injection). · License: MIT (code); sample contract is synthetic.
