"""Contract parser — raw bytes in, offset-exact spans out.

THE invariant this file exists to guarantee:
    raw_text[span.start_char:span.end_char] == span.text   (always, exactly)

How we keep it:
  * `raw_text` is read once and never mutated.
  * "Cleaning" (stripping whitespace, dropping blank lines) is done by MOVING
    offsets inward, never by editing strings. A span is always a literal
    slice of the original document.
  * Sentence/paragraph segmentation only chooses WHERE to cut — it never
    rewrites characters.

That discipline is why citations will anchor correctly to the original PDF
later (click-to-source provenance, M4). Get it wrong here and every finding
downstream is off by N characters.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import ParsedContract, SpanKind
from .models import Span as SpanModel

# A blank line = newline, optional horizontal whitespace, newline.
_PARA_SEP = re.compile(r"\n[ \t\r]*\n")

# Candidate sentence boundary: ., ! or ? followed by whitespace.
_SENT_END = re.compile(r"[.!?](?=\s)")

# Tokens that look like a sentence end but aren't (legal text is full of them).
_ABBREVIATIONS = {
    "inc", "ltd", "llc", "llp", "corp", "co", "no", "nos", "sec", "art",
    "para", "pp", "vs", "v", "mr", "mrs", "ms", "dr", "jr", "sr", "st",
    "approx", "e.g", "i.e", "etc", "u.s", "u.k", "fig", "ref",
}


def _trim(raw: str, start: int, end: int) -> tuple[int, int]:
    """Shrink [start, end) inward past surrounding whitespace. Offsets only."""
    while start < end and raw[start].isspace():
        start += 1
    while end > start and raw[end - 1].isspace():
        end -= 1
    return start, end


def _paragraph_windows(raw: str) -> list[tuple[int, int]]:
    """Offset windows of paragraph blocks (runs of non-blank lines)."""
    windows: list[tuple[int, int]] = []
    pos = 0
    for sep in _PARA_SEP.finditer(raw):
        s, e = _trim(raw, pos, sep.start())
        if e > s:
            windows.append((s, e))
        pos = sep.end()
    s, e = _trim(raw, pos, len(raw))
    if e > s:
        windows.append((s, e))
    return windows


def _is_false_boundary(raw: str, dot: int) -> bool:
    """Heuristic guard: is the '.' at index `dot` NOT a real sentence end?"""
    # Decimal or numbered section: digit immediately before or after the dot.
    if dot > 0 and raw[dot - 1].isdigit():
        return True
    if dot + 1 < len(raw) and raw[dot + 1].isdigit():
        return True
    # Single-letter initial: "A." (one uppercase letter preceded by space/start).
    if dot >= 1 and raw[dot - 1].isupper():
        before = raw[dot - 2] if dot >= 2 else " "
        if not before.isalpha():
            return True
    # Known abbreviation just before the dot.
    word_start = dot
    while word_start > 0 and (raw[word_start - 1].isalnum() or raw[word_start - 1] == "."):
        word_start -= 1
    token = raw[word_start:dot].lower().strip(".")
    if token in _ABBREVIATIONS:
        return True
    return False


def _sentence_windows(raw: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split a paragraph window into sentence windows, offsets preserved."""
    windows: list[tuple[int, int]] = []
    seg_start = start
    for m in _SENT_END.finditer(raw, start, end):
        dot = m.start()
        if _is_false_boundary(raw, dot):
            continue
        s, e = _trim(raw, seg_start, dot + 1)  # include the punctuation
        if e > s:
            windows.append((s, e))
        seg_start = dot + 1
    # Trailing fragment with no terminal punctuation.
    s, e = _trim(raw, seg_start, end)
    if e > s:
        windows.append((s, e))
    return windows


def _read_raw(path: Path) -> tuple[str, str]:
    """Return (raw_text, kind) for a .txt/.pdf/.docx file.

    Only .txt is needed for Milestone 1. PDF/DOCX are wired but lazily
    imported so the M1 scaffold runs with zero heavy dependencies.
    """
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8"), "text"
    if suffix == ".pdf":
        return _read_pdf(path), "pdf"
    if suffix == ".docx":
        return _read_docx(path), "docx"
    raise ValueError(f"Unsupported contract format: {suffix!r}")


def _read_pdf(path: Path) -> str:
    try:
        import pdfplumber  # lazy: only needed for PDFs
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "PDF parsing needs pdfplumber: pip install 'auditagent[pdf]'"
        ) from exc
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    # Join with form-feed so page boundaries are recoverable; offsets are into
    # THIS assembled raw_text (the document of record for citations).
    return "\f".join(pages)


def _read_docx(path: Path) -> str:
    try:
        import docx  # python-docx, lazy
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "DOCX parsing needs python-docx: pip install 'auditagent[docx]'"
        ) from exc
    document = docx.Document(str(path))
    return "\n\n".join(p.text for p in document.paragraphs)


def parse_text(raw_text: str, *, doc_id: str, source_name: str) -> ParsedContract:
    """Parse already-loaded raw text into an offset-exact ParsedContract."""
    spans: list[SpanModel] = []
    counter = 0
    for p_start, p_end in _paragraph_windows(raw_text):
        for s_start, s_end in _sentence_windows(raw_text, p_start, p_end):
            counter += 1
            spans.append(
                SpanModel(
                    id=f"s{counter}",
                    kind=SpanKind.SENTENCE,
                    text=raw_text[s_start:s_end],
                    start_char=s_start,
                    end_char=s_end,
                )
            )
    return ParsedContract(
        doc_id=doc_id,
        source_name=source_name,
        raw_text=raw_text,
        spans=spans,
    )


def parse_contract(path: str | Path, *, doc_id: str | None = None) -> ParsedContract:
    """Parse a contract file (.txt/.pdf/.docx) into an offset-exact result."""
    path = Path(path)
    raw_text, _kind = _read_raw(path)
    return parse_text(
        raw_text,
        doc_id=doc_id or path.stem,
        source_name=path.name,
    )
