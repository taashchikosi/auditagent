"""Fuzzy-but-verified citation anchoring.

The problem this solves (see HANDOFF_GateFix_AuditAgent.md):
    A real LLM returns a quote that is *semantically* an exact lift of the
    contract but *textually* off by whitespace, smart-quotes, en/em-dashes,
    or an ellipsis. A byte-exact ``raw_text.find(quote)`` then fails, the
    citation gate rejects a CORRECT finding, recall craters, and the agent
    loses to a single API call.

The fix:
    Normalize a throwaway *view* of the contract (collapse whitespace,
    fold smart-quotes/dashes/ellipses to ASCII) purely to LOCATE the region,
    while keeping an index map back to the original raw offsets. Then return a
    Citation whose ``quote`` is sliced straight from ``raw_text`` at those
    offsets — so it is a real, exact slice and ``Citation.verify_against`` is
    true BY CONSTRUCTION.

🔒 INVARIANT (M1 — never weaken): every Citation returned here satisfies
    ``raw_text[cit.start_char:cit.end_char] == cit.quote`` exactly. Fuzzy
    matching only finds the *region*; the citation itself is always a literal
    raw slice. A quote that is not really in the document must still fail to
    anchor (the hallucination-rejection guarantee).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Citation

# Characters an LLM commonly substitutes for their ASCII source equivalents.
_CHAR_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",  # single quotes
    "“": '"', "”": '"', "„": '"', "‟": '"',  # double quotes
    "«": '"', "»": '"',                                 # guillemets
    "–": "-", "—": "-", "‒": "-", "―": "-",   # en/em dashes
    "−": "-", "‐": "-", "‑": "-",                  # minus/hyphens
    "…": "...",                                              # ellipsis
    " ": " ", " ": " ", " ": " ", " ": " ",   # nbsp/thin sp
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _normalize(raw: str, *, lower: bool) -> tuple[str, list[int], list[int]]:
    """Build a normalized view of ``raw`` plus a per-char map back to offsets.

    Returns (norm_text, starts, ends) where for normalized char ``i``:
        ``starts[i]`` / ``ends[i]`` are the raw [start, end) offsets it came from.
    Whitespace runs collapse to a single space mapped to the first ws char.
    A char that expands (e.g. '…' -> '...') maps every output char to it.
    """
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    prev_space = False
    for i, ch in enumerate(raw):
        if ch.isspace():
            if prev_space:
                continue
            prev_space = True
            out.append(" ")
            starts.append(i)
            ends.append(i + 1)
            continue
        prev_space = False
        repl = _CHAR_MAP.get(ch, ch)
        if lower:
            repl = repl.lower()
        for rc in repl:
            out.append(rc)
            starts.append(i)
            ends.append(i + 1)
    return "".join(out), starts, ends


def _strip_to_offsets(
    norm: str, ns: int, ne: int, starts: list[int], ends: list[int]
) -> tuple[int, int] | None:
    """Trim leading/trailing spaces off a normalized span, map to raw offsets."""
    while ns < ne and norm[ns] == " ":
        ns += 1
    while ne > ns and norm[ne - 1] == " ":
        ne -= 1
    if ne <= ns:
        return None
    return starts[ns], ends[ne - 1]


def _make_citation(raw: str, start: int, end: int) -> Citation | None:
    if end <= start:
        return None
    return Citation(quote=raw[start:end], start_char=start, end_char=end)


def _fuzzy_locate(
    norm_raw: str, norm_quote: str, *, min_ratio: float
) -> tuple[int, int, float] | None:
    """Token-anchored bounded fuzzy search. Returns (ns, ne, ratio) or None.

    Bounded by anchoring on the quote's longest token so we never run
    SequenceMatcher over the whole contract — only ~quote-sized windows.
    """
    tokens = sorted(_TOKEN_RE.findall(norm_quote), key=len, reverse=True)
    anchor = next((t for t in tokens if len(t) >= 4), None)
    if anchor is None:
        return None

    qlen = len(norm_quote)
    pad = max(8, qlen // 5)
    best: tuple[int, int, float] | None = None
    search_from = 0
    while True:
        hit = norm_raw.find(anchor, search_from)
        if hit == -1:
            break
        search_from = hit + 1
        # Window roughly the size of the quote, centered on the anchor token.
        offset_in_q = norm_quote.find(anchor)
        ws = max(0, hit - offset_in_q - pad)
        we = min(len(norm_raw), hit - offset_in_q + qlen + pad)
        window = norm_raw[ws:we]
        sm = SequenceMatcher(None, window, norm_quote, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
        if not blocks:
            continue
        # Score by how much of the QUOTE we matched (recall), not by ratio over
        # the padded window — padding must not dilute a real near-exact lift.
        matched = sum(b.size for b in blocks)
        score = matched / len(norm_quote)
        if best is None or score > best[2]:
            a_start = ws + blocks[0].a
            a_end = ws + blocks[-1].a + blocks[-1].size
            best = (a_start, a_end, score)

    if best is None or best[2] < min_ratio:
        return None
    return best


def fuzzy_anchor_quote(
    raw_text: str, quote: str, *, min_ratio: float = 0.9
) -> Citation | None:
    """Anchor ``quote`` to an exact raw slice, tolerating cosmetic diffs.

    Order of attempts (cheapest first):
      1. Exact substring — the existing fast path, unchanged behaviour.
      2. Normalized-exact — fold whitespace/quotes/dashes, exact-search that.
      3. Normalized-exact, case-insensitive.
      4. Bounded token-anchored fuzzy match (>= ``min_ratio``), length-guarded.
    Returns None if nothing anchors confidently (hallucination → rejected).
    """
    quote = quote.strip()
    if not quote:
        return None

    # 1. Exact — byte-for-byte. Preserves all prior passing behaviour.
    idx = raw_text.find(quote)
    if idx != -1:
        return _make_citation(raw_text, idx, idx + len(quote))

    # 2 & 3. Normalized-exact (case-sensitive, then case-insensitive).
    for lower in (False, True):
        norm_raw, starts, ends = _normalize(raw_text, lower=lower)
        norm_q, _, _ = _normalize(quote, lower=lower)
        norm_q = norm_q.strip()
        if not norm_q:
            continue
        pos = norm_raw.find(norm_q)
        if pos != -1:
            mapped = _strip_to_offsets(
                norm_raw, pos, pos + len(norm_q), starts, ends
            )
            if mapped:
                return _make_citation(raw_text, *mapped)

    # 4. Bounded fuzzy fallback (case-insensitive view for robustness).
    norm_raw, starts, ends = _normalize(raw_text, lower=True)
    norm_q, _, _ = _normalize(quote, lower=True)
    norm_q = norm_q.strip()
    if not norm_q:
        return None
    located = _fuzzy_locate(norm_raw, norm_q, min_ratio=min_ratio)
    if located is None:
        return None
    ns, ne, _ratio = located
    mapped = _strip_to_offsets(norm_raw, ns, ne, starts, ends)
    if mapped is None:
        return None
    start, end = mapped
    # Length guard: a real fuzzy anchor covers a region close to the quote's
    # length. A wildly different length means we anchored to the wrong place.
    matched_len = end - start
    if not (0.6 * len(norm_q) <= matched_len <= 1.6 * len(norm_q)):
        return None
    return _make_citation(raw_text, start, end)
