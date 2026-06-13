# Architecture

## The full picture (target v1)

```
Contract PDF/DOCX/TXT
        │
        ▼
  Supervisor (LangGraph)
        │
  ┌─────┼───────────────┐
  ▼     ▼               ▼
Extractor  Clause Classifier  Risk Analyzer
(parse +   (41 CUAD types)    (severity + "why")
 offsets)
  └─────┼───────────────┘
        ▼
  🔒 Reviewer / Citation Gate
  every finding MUST quote an exact span; uncited → REJECT → retry
        ▼
  📋 Deterministic checklist engine   ← rule-based, NOT the LLM
        ▼
  🗄️ Immutable audit log (Postgres)
        ▼
  Cited risk memo + 👤 HITL approve/escalate
        ▼
  Next.js UI (streamed findings, severity heatmap, evidence panel)
```

## What Milestone 1 actually implements

M1 builds the **Extractor** plus the **tool layer** every agent will call. Nothing else is real yet — and that is deliberate.

```
contract.txt
   │  parser.parse_contract()
   ▼
ParsedContract            ← raw_text is the single source of truth
   ├── raw_text (immutable)
   └── spans[]            ← each: text + [start_char, end_char) into raw_text
   │  chunker.chunk_contract()
   ▼
Chunk[]                   ← retrieval units, offsets preserved

exposed via:
  • FastMCP tools  (parse_contract_text, chunk_contract_text, get_span_text, parse_sample_contract)
  • FastAPI        (GET /health, GET /parse/sample)
```

## The one decision that matters at M1: offsets, not strings

A naive parser "cleans" text (strips whitespace, normalises quotes) and then records positions **into the cleaned text**. The moment you try to highlight a clause in the *original* PDF, you're off by N characters and every citation is subtly wrong.

AuditAgent's rule:

- `raw_text` is read once and **never mutated**.
- All "cleaning" happens by **moving offsets inward** (`parser._trim`), never by editing characters.
- Therefore `raw_text[span.start_char:span.end_char] == span.text` holds for every span, forever.

This is verified three ways: a Pydantic `model_validator` (text length must equal offset width), `ParsedContract.integrity_report()` (a returned metric, not just an assert), and `tests/test_parser.py::test_every_span_round_trips`.

## Why a tool layer (FastMCP) instead of direct function calls

Later milestones add the Classifier and Reviewer agents. They will reach the contract **only through MCP tools**, never by reading files directly. Every contract operation therefore becomes an observable, loggable tool call — which is what makes the audit trail (and Langfuse traces) meaningful. Building the tool boundary now, before any agent exists, keeps that discipline from day one.

## What Milestone 2 adds

The 4 agents are now wired through a LangGraph supervisor, with the citation
gate as the load-bearing differentiator:

```
raw_text
  │  build_graph() → LangGraph StateGraph (checkpointed)
  ▼
extract → classify → risk → review(GATE) → checklist → HITL interrupt → memo
                              │
                              └─ every finding: citation must re-slice raw text
                                 exactly, else 1 retry (reviewer re-extract),
                                 else REJECT. Hallucinated/uncited → rejected.

side channels:
  • injection.py  — scans raw text; in-contract attacks flagged + refused (LLM01)
  • audit_log.py  — every node appends a hash-chained, tamper-evident event
  • llm/          — provider protocol; deterministic offline + DeepSeek/Claude
  • pipeline.compare() — B1 single-shot vs agent ("the catch")
```

### Two M2 design decisions worth calling out

- **Checkpointed state holds primitives only.** The HITL interrupt serializes
  graph state; keeping it to strings (and holding typed findings/memo in a
  per-run `RunContext` closure) avoids serializing custom types — no
  deprecation risk, JSON-native checkpoints, and each run stays isolated.
- **The LLM is never trusted to self-certify.** Classifier and reviewer both
  return a *claimed* quote; it earns a citation only by exact-matching raw
  text. So a fabricated quote fails the anchor check regardless of model
  confidence — the gate is deterministic, the model is replaceable.

## Component status

| Component | Status |
|---|---|
| Extractor (parse + offsets) | ✅ M1 |
| Chunker (offset-preserving) | ✅ M1 |
| MCP tool layer (parse/chunk/get-span) | ✅ M1 |
| Pydantic schemas (Span/Chunk/Citation/Finding/RiskMemo/AuditEvent) | ✅ M1–M2 |
| `/health` + `/parse/sample` | ✅ M1 |
| LangGraph supervisor (4 agents) | ✅ M2 |
| **Citation gate** (reject uncited → retry → reject) | ✅ M2 (core differentiator) |
| Risk Analyzer (L2 perspective-aware severity) | ✅ M2 |
| Deterministic checklist engine | ✅ M2 |
| Immutable hash-chained audit log (SQLite; Postgres in prod) | ✅ M2 |
| Prompt-injection resistance (OWASP LLM01) | ✅ M2 |
| HITL Approve/Escalate gate | ✅ M2 |
| Pluggable LLM (deterministic + DeepSeek/Claude) | ✅ M2 |
| CUAD loader (real labels, offset-anchored gold) | ✅ M3 |
| CUAD scorer (P/R/F1, P@R, AUPR, laziness, faithfulness) | ✅ M3 |
| Baseline ladder runner B0/B1/B2 + cost/latency | ✅ M3 |
| Hybrid retrieval (BM25 + pgvector + rerank) | ⏳ M3.1 (cost control for real-model B2) |
| Next.js UI (evidence panel, heatmap) | ⏳ M4 |

## Milestone 3 — the accuracy harness

```
CUAD test split (real, CC BY 4.0)        eval/cuad.py
  └─ per (contract, clause): present? + gold spans (offset-anchored)
        │
        ▼
run B1 (single-shot)  and  B2 (agent pipeline)   eval/runner.py
        │  predictions: present? + cited span + confidence
        ▼
score vs gold                                    eval/scorer.py
  TP/FP/FN → precision · recall · F1 · macro-F1 · P@80R · AUPR
  + laziness rate · citation faithfulness · high-risk recall
        ▼
baseline ladder report (B0 published · B1 · B2) + measured cost/latency
```

**Why the gold offsets matter:** CUAD's `answer_start` anchors exactly against
the contract text — the *same* offset model AuditAgent uses for citations. So
"citation faithfulness" is computable: a correct detection is faithful only if
its cited span overlaps a gold span (catching right-answer/wrong-evidence).

**L1 vs L2, kept separate in the harness:** the scorer measures **detection**
(L1, what CUAD labels). Severity (L2) is never scored against CUAD — it's the
deterministic perspective-aware rule layer, reported separately. Conflating
them is the credibility failure this project is designed to avoid.

**Provider-agnostic, honest about it:** the harness runs B1/B2 through the same
pluggable provider as the pipeline. Offline it uses the deterministic detector
(validates the machinery + a floor against real labels); with `DEEPSEEK_API_KEY`
it runs the real model and reports measured token cost. The report explicitly
tags whether numbers are real-model or stand-in, so a stand-in result can never
be mistaken for a benchmark.

### Audit log: SQLite now, Postgres in prod

The locked production store is Postgres (immutable decision log). The hash
chain and schema are storage-agnostic — `AuditLog(db_path=...)` uses SQLite
(`:memory:` in tests); swapping to Postgres changes only the connection, not
the chaining logic. Tamper-evidence is proven by `verify_chain()` (and a test
that mutates a row and asserts the chain breaks).

## Technical decisions (ADR-lite)

- **Plain-text-first parsing.** M1 nails the offset invariant on `.txt` (zero heavy deps, fully tested). PDF (pdfplumber) and DOCX (python-docx) are wired but lazily imported, so the scaffold runs offline. Rationale: prove the hard part (offset fidelity) before adding format-specific noise.
- **Synthetic sample contract ships; real CUAD downloads on demand.** Keeps the repo lightweight and the demo network-free, while `scripts/download_cuad.py` documents pulling the full corpus for the M3 eval ladder. The sample deliberately contains all 5 v1 target clauses.
- **Integrity as a returned metric, not just an assertion.** `integrity_report()` lets `/health` and CI surface citation anchoring as a number — consistent with the project's "accuracy is a number, not a vibe" thesis.
- **Half-open offsets `[start, end)`.** Matches Python slicing exactly, so `raw[start:end]` is the citation with no off-by-one translation.
