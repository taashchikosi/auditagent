"""Chunker — group spans into retrieval units WITHOUT losing offsets.

A chunk's text is the literal slice `raw_text[chunk.start_char:chunk.end_char]`
(spanning from its first span's start to its last span's end). So even after
chunking for embedding/BM25, a retrieved chunk still round-trips to the
original document — retrieval can never "lose the thread" back to source.
"""

from __future__ import annotations

from .models import Chunk, ParsedContract


def chunk_contract(
    parsed: ParsedContract,
    *,
    target_chars: int = 1000,
    overlap_spans: int = 1,
) -> list[Chunk]:
    """Pack consecutive spans into ~`target_chars` chunks with span overlap.

    Args:
        target_chars: soft cap on chunk size (a single oversized span still
            becomes its own chunk — we never split a span and break offsets).
        overlap_spans: how many trailing spans to repeat at the next chunk's
            start, so a clause straddling a boundary isn't lost to retrieval.
    """
    spans = parsed.spans
    raw = parsed.raw_text
    chunks: list[Chunk] = []
    if not spans:
        return chunks

    i = 0
    chunk_no = 0
    n = len(spans)
    while i < n:
        j = i
        start_char = spans[i].start_char
        end_char = spans[i].end_char
        # Grow the window until we hit the size target (always >= 1 span).
        while j + 1 < n and (spans[j + 1].end_char - start_char) <= target_chars:
            j += 1
            end_char = spans[j].end_char
        chunk_no += 1
        chunks.append(
            Chunk(
                id=f"c{chunk_no}",
                text=raw[start_char:end_char],
                start_char=start_char,
                end_char=end_char,
                span_ids=[s.id for s in spans[i : j + 1]],
            )
        )
        if j + 1 >= n:
            break
        # Step forward, leaving `overlap_spans` of overlap (but always advance).
        i = max(i + 1, j + 1 - overlap_spans)
    return chunks
