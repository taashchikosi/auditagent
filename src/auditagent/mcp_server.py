"""FastMCP server — the tool layer downstream agents call.

Milestone-1 tools (parse/chunk/inspect). Later milestones add retrieve and
checklist tools here; the Classifier/Reviewer agents will reach the contract
ONLY through these tools, never by touching files directly. That keeps every
agent action observable and auditable (the Big-4 signal).

Run standalone:   python -m auditagent.mcp_server
"""

from __future__ import annotations

from fastmcp import FastMCP

from .chunker import chunk_contract
from .data import SAMPLE_CONTRACT_PATH, load_sample_contract_text
from .parser import parse_text

mcp: FastMCP = FastMCP("AuditAgent-Contract-Tools")


@mcp.tool
def parse_contract_text(
    raw_text: str, doc_id: str = "adhoc", source_name: str = "inline.txt"
) -> dict:
    """Parse raw contract text into offset-exact spans.

    Returns spans where raw_text[start_char:end_char] == text, plus a
    citation-integrity report (the number that proves anchoring works).
    """
    parsed = parse_text(raw_text, doc_id=doc_id, source_name=source_name)
    return {
        "doc_id": parsed.doc_id,
        "n_chars": parsed.n_chars,
        "n_spans": parsed.n_spans,
        "spans": [s.model_dump() for s in parsed.spans],
        "integrity": parsed.integrity_report(),
    }


@mcp.tool
def parse_sample_contract() -> dict:
    """Parse the bundled pre-loaded CUAD-style contract (zero-arg demo)."""
    raw = load_sample_contract_text()
    parsed = parse_text(
        raw, doc_id="sample", source_name=SAMPLE_CONTRACT_PATH.name
    )
    return {
        "doc_id": parsed.doc_id,
        "source_name": parsed.source_name,
        "n_chars": parsed.n_chars,
        "n_spans": parsed.n_spans,
        "spans": [s.model_dump() for s in parsed.spans],
        "integrity": parsed.integrity_report(),
    }


@mcp.tool
def chunk_contract_text(
    raw_text: str, target_chars: int = 1000, overlap_spans: int = 1
) -> dict:
    """Parse then chunk text into offset-preserving retrieval units."""
    parsed = parse_text(raw_text, doc_id="adhoc", source_name="inline.txt")
    chunks = chunk_contract(
        parsed, target_chars=target_chars, overlap_spans=overlap_spans
    )
    return {
        "n_chunks": len(chunks),
        "chunks": [c.model_dump() for c in chunks],
    }


@mcp.tool
def get_span_text(raw_text: str, start_char: int, end_char: int) -> dict:
    """Return the exact substring at [start_char, end_char) — a citation fetch.

    This is what the click-to-source provenance UI calls: given offsets, hand
    back the precise quoted text from the source document.
    """
    return {
        "start_char": start_char,
        "end_char": end_char,
        "quote": raw_text[start_char:end_char],
    }


if __name__ == "__main__":
    mcp.run()
