"""Real DeepSeek adapters — primary production model (~90% of calls).

Activated only when DEEPSEEK_API_KEY is set; otherwise the factory falls back
to the deterministic provider so nothing breaks offline.

Two roles, mirroring the Claude adapters so a DeepSeek benchmark is clean
(DeepSeek detector + DeepSeek gate), not a DeepSeek detector wearing a Claude
gate:
  * DeepSeekProvider  — recall-first clause DETECTOR (classifier + B1 baseline).
  * DeepSeekReviewer  — the citation-gate re-extractor (verbatim quote or none).

Both demand an EXACT verbatim quote; the citation gate then verifies it against
the raw contract, so a hallucinated quote is caught downstream regardless.
"""

from __future__ import annotations

import json
import os

from ..clauses import ClauseSpec
from .base import ClauseHit

_ENDPOINT = "https://api.deepseek.com/chat/completions"

# The API model id. Default is the current production model; override per run
# with AUDITAGENT_DEEPSEEK_MODEL (e.g. "deepseek-v4-pro" to A/B the larger model
# on the eval). NOTE: the old "deepseek-chat"/"deepseek-reasoner" aliases are
# deprecated by DeepSeek (they error after 2026-07-24), so we default to the
# explicit v4 id, and `.name` follows the real model so the eval report + cost
# table never mislabel which model produced a number.
_DEFAULT_MODEL = "deepseek-v4-flash"


def _resolve_model(explicit: str | None) -> str:
    return explicit or os.environ.get("AUDITAGENT_DEEPSEEK_MODEL", _DEFAULT_MODEL)

_CLASSIFY_SYSTEM = (
    "You are a contract-clause detector. For each clause type the user lists, "
    "decide if the contract contains it. RECALL MATTERS MORE THAN PRECISION: a "
    "missed high-risk clause is the dangerous error. If present, return a quote "
    "copied VERBATIM and EXACTLY from the contract (character-for-character, no "
    "paraphrasing). Respond ONLY as JSON: "
    '{"hits":[{"clause_key":"...","quote":"...","rationale":"...","confidence":0.0}]}'
)

_REVIEW_SYSTEM = (
    "You re-extract evidence for a contract clause. Given candidate source "
    "text, return a quote copied VERBATIM and EXACTLY (character-for-character) "
    "that supports the clause, or an empty quote if none truly applies. Never "
    "invent text. Respond ONLY as JSON: "
    '{"hits":[{"clause_key":"...","quote":"...","rationale":"...","confidence":0.0}]}'
)


def _call_deepseek(
    api_key: str, model: str, system: str, user: str, clause_specs
) -> list[ClauseHit]:
    """One DeepSeek call → validated ClauseHits, with measured cost recorded."""
    import time

    import httpx  # lazy

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # Benchmarks must be reproducible — keep sampling deterministic.
        "temperature": float(os.environ.get("AUDITAGENT_TEMPERATURE", "0")),
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    max_attempts = int(os.environ.get("AUDITAGENT_MAX_RETRIES", "6"))
    resp = None
    for attempt in range(max_attempts):
        try:
            resp = httpx.post(_ENDPOINT, headers=headers, json=payload, timeout=120)
        except httpx.TransportError:
            # Transient connection/handshake/read timeout — retry with backoff
            # so one network blip can't abort a long eval. Re-raise on the last.
            if attempt < max_attempts - 1:
                time.sleep(min(2.0**attempt, 30.0) + 0.5)
                continue
            raise
        if resp.status_code in (429, 503, 529) and attempt < max_attempts - 1:
            retry_after = resp.headers.get("retry-after")
            wait = float(retry_after) if retry_after else min(2.0**attempt, 30.0)
            time.sleep(wait + 0.5)
            continue
        break
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage", {})
    from .usage import USAGE  # record measured tokens for cost reporting

    USAGE.add(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
    # `.get` not `[]`: a reasoning model (e.g. deepseek-v4-pro) can return a null
    # / empty `content` (its text lands in `reasoning_content`), which used to
    # crash json.loads and ABORT the whole eval mid-run. Tolerant parsing makes
    # one bad reply an honest "0 hits for this contract" instead.
    content = body["choices"][0]["message"].get("content") or ""
    valid_keys = {c.key for c in clause_specs}
    return _parse_deepseek_hits(content, valid_keys)


def _parse_deepseek_hits(content: str, valid_keys: set[str]) -> list[ClauseHit]:
    """Strict JSON → salvage complete {..} objects → []. Never raises.

    Mirrors the Claude adapter's resilience so a single empty or truncated reply
    (reasoning model with no JSON, rate-limit-garbled body, max_tokens cutoff)
    yields 'no hits for this contract' rather than killing a 102-contract run.
    Empty / unparseable replies print a stderr warning so a SYSTEMIC failure
    (e.g. a model that returns empty every time) is loud, not silently scored 0.
    """
    import re
    import sys

    def _collect(raws: list) -> list[ClauseHit]:
        out: list[ClauseHit] = []
        for raw in raws:
            if isinstance(raw, dict) and raw.get("clause_key") in valid_keys and raw.get("quote"):
                try:
                    out.append(ClauseHit(**raw))
                except Exception:
                    continue
        return out

    text = content.strip()
    if not text:
        print("⚠️  deepseek: empty model reply — 0 hits for this contract", file=sys.stderr)
        return []
    # Strict path: isolate the outermost JSON object and parse it.
    start, end = text.find("{"), text.rfind("}")
    payload = text[start : end + 1] if start != -1 and end != -1 else text
    try:
        return _collect(json.loads(payload).get("hits", []))
    except json.JSONDecodeError:
        pass
    # Salvage path: parse each self-contained hit object individually.
    salvaged: list[dict] = []
    for m in re.finditer(r"\{[^{}]*\}", text):
        try:
            salvaged.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            continue
    if not salvaged:
        print("⚠️  deepseek: unparseable model reply — 0 hits for this contract", file=sys.stderr)
    return _collect(salvaged)


def _clause_menu(clause_specs: tuple[ClauseSpec, ...]) -> str:
    # Include the per-clause DEFINITION, not just the label. A bare name left
    # the model to guess clause boundaries — the root cause of
    # uncapped_liability's 0.20 precision and run-to-run wobble at n=102.
    def _line(c: ClauseSpec) -> str:
        head = f"- {c.key}: {c.name}"
        return f"{head}\n    {c.definition}" if c.definition else head

    return "\n".join(_line(c) for c in clause_specs)


class DeepSeekProvider:
    """Primary clause DETECTOR (also the B1 single-shot baseline)."""

    def __init__(self, model: str | None = None) -> None:
        self.model = _resolve_model(model)
        self.name = self.model  # honest: the label IS the model that ran
        self.api_key = os.environ["DEEPSEEK_API_KEY"]

    def classify(
        self, text: str, clause_specs: tuple[ClauseSpec, ...]
    ) -> list[ClauseHit]:
        user = (
            f"Clause types to detect:\n{_clause_menu(clause_specs)}\n\n"
            f'Contract:\n"""\n{text}\n"""'
        )
        return _call_deepseek(
            self.api_key, self.model, _CLASSIFY_SYSTEM, user, clause_specs
        )


class DeepSeekReviewer:
    """Citation-gate re-extractor — DeepSeek twin of ClaudeReviewer.

    Lets a DeepSeek run use a DeepSeek gate, so the benchmark measures one
    model end-to-end instead of a DeepSeek detector with a Claude gate.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = _resolve_model(model)
        self.name = self.model
        self.api_key = os.environ["DEEPSEEK_API_KEY"]

    def classify(
        self, text: str, clause_specs: tuple[ClauseSpec, ...]
    ) -> list[ClauseHit]:
        user = (
            f"Clause types:\n{_clause_menu(clause_specs)}\n\n"
            f'Candidate source text:\n"""\n{text}\n"""'
        )
        return _call_deepseek(
            self.api_key, self.model, _REVIEW_SYSTEM, user, clause_specs
        )
