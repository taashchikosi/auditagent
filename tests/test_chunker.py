"""Chunks must also round-trip, and must cover the document without gaps."""

from __future__ import annotations

import pytest

from auditagent.chunker import chunk_contract
from auditagent.data import load_sample_contract_text
from auditagent.parser import parse_text

RAW = load_sample_contract_text()


@pytest.fixture(scope="module")
def parsed():
    return parse_text(RAW, doc_id="sample", source_name="sample_contract.txt")


def test_chunks_round_trip(parsed):
    chunks = chunk_contract(parsed, target_chars=800, overlap_spans=1)
    assert len(chunks) > 1
    for chunk in chunks:
        assert RAW[chunk.start_char : chunk.end_char] == chunk.text


def test_chunks_reference_real_spans(parsed):
    span_ids = {s.id for s in parsed.spans}
    chunks = chunk_contract(parsed)
    for chunk in chunks:
        assert chunk.span_ids, "chunk has no spans"
        assert set(chunk.span_ids) <= span_ids


def test_chunks_cover_all_spans(parsed):
    """Every span appears in at least one chunk (nothing dropped)."""
    chunks = chunk_contract(parsed, target_chars=600, overlap_spans=1)
    covered = {sid for c in chunks for sid in c.span_ids}
    assert covered == {s.id for s in parsed.spans}


def test_oversized_span_becomes_its_own_chunk():
    """A single span larger than target_chars must not be split (would break offsets)."""
    big = "x" * 50 + ". " + "y" * 2000 + ". short tail."
    parsed = parse_text(big, doc_id="t", source_name="t.txt")
    chunks = chunk_contract(parsed, target_chars=500, overlap_spans=0)
    for chunk in chunks:
        assert big[chunk.start_char : chunk.end_char] == chunk.text


def test_empty_contract_yields_no_chunks():
    parsed = parse_text("", doc_id="t", source_name="t.txt")
    assert chunk_contract(parsed) == []
