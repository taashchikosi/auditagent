# AuditAgent

**Autonomous contract-review agent that flags risky clauses, cites the exact source text, and proves its accuracy on expert-labelled data.**

> In 2025, Deloitte Australia partially refunded the federal government after an AI-assisted report contained fabricated citations. AuditAgent is built to make that failure impossible: **every finding must quote the exact contract text it came from, or it is rejected.**

`Status: 🟢 Milestone 3 of 4 — CUAD eval harness + baseline ladder live. (M1: parsing · M2: pipeline + citation gate.)`

---

## Why this project

Contract review is the highest-volume agentic use case at the Big 4 (Deloitte Zora, KPMG Clara). Most portfolio demos can't put a *number* on accuracy. This one can — it's evaluated against [CUAD](https://www.atticusprojectai.org/cuad) (510 real contracts, 41 expert-defined clause types, 13,000+ lawyer labels, CC BY 4.0).

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

The 4-agent pipeline is wired through **LangGraph**, and the **citation gate** is live — the core differentiator. Every accepted finding quotes an exact source span or it's rejected.

| Delivered (M2) | Where |
|---|---|
| LangGraph supervisor: Extractor → Classifier → Risk Analyzer → Reviewer | `src/auditagent/graph.py`, `agents/` |
| **Citation gate** — uncited/mis-cited findings auto-rejected (1 retry, then reject) | `agents/reviewer.py` |
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
20-contract sample ships in the repo; the full 510 download via
`make eval-full`). The scorer (`eval/scorer.py`) computes per-clause
precision/recall/F1, Precision@Recall, plus the metrics that matter for
contract review: **laziness rate** (present clauses wrongly called absent),
**citation faithfulness** (right answer *and* right evidence), and **high-risk
recall**. The baseline ladder is **B0** (published RoBERTa P@80%R ≈ 0.482) →
**B1** single-shot → **B2** agent; the headline is the **B2 − B1 delta on
high-risk recall**.

> ⚠️ **Honest status:** the numbers committed in `eval_report.md` are from the
> **deterministic stand-in detector** (no model API reachable in this build
> environment), so they validate the *measurement machinery* against real
> labels — they are **not** a publishable benchmark result. The real DeepSeek
> B1/B2 numbers come from `make eval` on a host where the DeepSeek API is
> reachable (`DEEPSEEK_API_KEY` set). The harness reports **measured**
> cost+latency per contract from the API's token usage — never guessed.

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
export DEEPSEEK_API_KEY=sk-...   # rotate any key shared in plaintext
make eval-full                   # download full CUAD test split, run real B1/B2
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
| **M3 ✅ (here)** | CUAD scorer + baseline ladder B0/B1/B2 + per-clause F1 + laziness/faithfulness + measured cost/latency, in CI. *(Real-model numbers pending a DeepSeek-reachable run.)* |
| **M4** | Live on the shared host as a route in the unified portfolio site; amazing-on-open README + demo |

---

## Stack (default — LangGraph, portable across all four Big 4)

Python · LangGraph · **FastMCP** · **Pydantic v2** · FastAPI (SSE) · Postgres + pgvector · hybrid BM25 + cross-encoder rerank · DeepSeek V4 Flash (primary) + Claude Sonnet 4.6 (citation gate) · bge-small embeddings · DeepEval + custom CUAD scorer · Langfuse · Next.js + assistant-ui.
*Azure-native is a documented optional ~half-day re-skin (KPMG/Microsoft-shop interviews only).*

## Deployment

Backend containerises onto the **shared always-on VPS** (port 8002, beside RetrofitGPT); the UI is a route in the unified portfolio site. `/health` drives the live-status dot. No cold start.

## References

CUAD — Hendrycks et al., NeurIPS 2021 (CC BY 4.0). · ContractEval — arXiv 2508.03080 (2025), the "laziness" metric. · OWASP LLM Top 10 (LLM01 prompt injection). · License: MIT (code); sample contract is synthetic.
