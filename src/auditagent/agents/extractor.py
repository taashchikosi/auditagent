"""Extractor agent — parse + chunk (reuses the M1 offset-exact foundation)."""

from __future__ import annotations

from ..chunker import chunk_contract
from ..models import Chunk, ParsedContract
from ..parser import parse_text


def extract(
    raw_text: str, *, doc_id: str, source_name: str
) -> tuple[ParsedContract, list[Chunk]]:
    """Raw contract text → offset-exact ParsedContract + retrieval chunks."""
    parsed = parse_text(raw_text, doc_id=doc_id, source_name=source_name)
    chunks = chunk_contract(parsed)
    return parsed, chunks
