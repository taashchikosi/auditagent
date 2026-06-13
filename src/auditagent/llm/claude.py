"""Real Claude adapters for AuditAgent.

Two roles, same API surface (both implement LLMProvider.classify):

  * ClaudeReviewer — the citation-gate re-extractor (~2% of calls). When a
    finding arrives uncited or mis-cited, ask Claude to RE-EXTRACT a verbatim
    quote from the supplied source spans. The deterministic offset check still
    runs afterward — Claude proposes, the gate verifies. Never self-certifies.

  * ClaudeClassifier — the PRIMARY clause detector when DeepSeek is not the
    chosen model (e.g. benchmarking with Claude before the production DeepSeek
    swap). Recall-first prompt; demands an exact verbatim quote so the citation
    gate can verify it downstream.

Both record token usage so the eval reports a MEASURED cost, not a guess.
Activated only when ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import json
import os

from ..clauses import ClauseSpec
from .base import ClauseHit

_ENDPOINT = "https://api.anthropic.com/v1/messages"

_REVIEW_SYSTEM = (
    "You re-extract evidence for a contract clause. Given candidate source "
    "text, return a quote copied VERBATIM and EXACTLY (character-for-character) "
    "that supports the clause, or an empty quote if none truly applies. Never "
    "invent text. Respond ONLY as JSON: "
    '{"hits":[{"clause_key":"...","quote":"...","rationale":"...","confidence":0.0}]}'
)

_CLASSIFY_SYSTEM = (
    "You are a contract-clause detector. For each clause type the user lists, "
    "decide if the contract contains it. RECALL MATTERS MORE THAN PRECISION: a "
    "missed high-risk clause is the dangerous error. If present, return a quote "
    "copied VERBATIM and EXACTLY from the contract (character-for-character, no "
    "paraphrasing). Respond ONLY as JSON: "
    '{"hits":[{"clause_key":"...","quote":"...","rationale":"...","confidence":0.0}]}'
)


def _call_claude(
    api_key: str, model: str, system: str, user: str, clause_specs
) -> list[ClauseHit]:
    """Shared POST + parse + usage-recording for both Claude roles."""
    import time

    import httpx  # lazy

    # Honor SSL_CERT_FILE for custom CA bundles (corporate proxies / on-prem
    # Big-4 networks routinely TLS-intercept egress). Falls back to default.
    verify = os.environ.get("SSL_CERT_FILE") or True
    payload_json = {
        "model": model,
        "max_tokens": int(os.environ.get("AUDITAGENT_MAX_TOKENS", "4096")),
        # Benchmarks must be reproducible: default to temperature 0 so the
        # B2-vs-B1 delta reflects the PIPELINE, not sampling noise. Without this
        # the API default (1.0) makes the headline metric swing run-to-run —
        # enough to flip the sign of the agent-vs-single-shot comparison on n=20.
        # Override with AUDITAGENT_TEMPERATURE for sensitivity analysis.
        "temperature": float(os.environ.get("AUDITAGENT_TEMPERATURE", "0")),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    # Retry with backoff on rate limits (429) and transient overload (529/503).
    # Anthropic returns Retry-After; honor it, else exponential backoff w/ cap.
    max_attempts = int(os.environ.get("AUDITAGENT_MAX_RETRIES", "6"))
    resp = None
    for attempt in range(max_attempts):
        try:
            resp = httpx.post(_ENDPOINT, headers=headers, json=payload_json,
                              timeout=120, verify=verify)
        except httpx.TransportError as exc:
            # Connection-level failures (TLS handshake timeout, connect/read
            # timeout, connection reset) are raised BEFORE any HTTP status, so
            # the status-code retry below never sees them. Without this, one
            # transient network blip aborts a paid 20-contract run mid-way.
            # Retry with the same backoff; re-raise only after the last attempt.
            if attempt < max_attempts - 1:
                time.sleep(min(2.0 ** attempt, 30.0) + 0.5)
                continue
            raise
        if resp.status_code in (429, 503, 529) and attempt < max_attempts - 1:
            retry_after = resp.headers.get("retry-after")
            wait = float(retry_after) if retry_after else min(2.0 ** attempt, 30.0)
            time.sleep(wait + 0.5)  # small pad so the per-minute window resets
            continue
        break
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage", {})
    from .usage import USAGE  # record measured tokens for cost reporting

    USAGE.add(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    content = body["content"][0]["text"]
    valid_keys = {c.key for c in clause_specs}
    return _parse_hits(content, valid_keys)


def _parse_hits(content: str, valid_keys: set[str]) -> list[ClauseHit]:
    """Parse hits from a model reply, tolerant of truncation/markdown.

    A single malformed or token-truncated reply must not crash a long eval. We
    first try strict JSON; if that fails (e.g. the response was cut at
    max_tokens mid-array), we salvage every COMPLETE `{...}` hit object we can
    find and drop the trailing partial one. Worst case → no hits from this call,
    which honestly counts as a miss rather than aborting the whole run.
    """
    import re

    def _collect(raws) -> list[ClauseHit]:
        out: list[ClauseHit] = []
        for raw in raws:
            if isinstance(raw, dict) and raw.get("clause_key") in valid_keys and raw.get("quote"):
                try:
                    out.append(ClauseHit(**raw))
                except Exception:
                    continue
        return out

    # Strict path: isolate the outermost JSON object and parse it.
    start, end = content.find("{"), content.rfind("}")
    payload = content[start : end + 1] if start != -1 and end != -1 else content
    try:
        return _collect(json.loads(payload).get("hits", []))
    except json.JSONDecodeError:
        pass

    # Salvage path: parse each self-contained hit object individually.
    salvaged: list[dict] = []
    for m in re.finditer(r"\{[^{}]*\}", content):
        try:
            salvaged.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            continue
    return _collect(salvaged)


def _clause_menu(clause_specs: tuple[ClauseSpec, ...]) -> str:
    # Include the per-clause DEFINITION, not just the label. A bare name left
    # the model to guess clause boundaries — the root cause of
    # uncapped_liability's 0.20 precision and run-to-run wobble at n=102.
    def _line(c: ClauseSpec) -> str:
        head = f"- {c.key}: {c.name}"
        return f"{head}\n    {c.definition}" if c.definition else head

    return "\n".join(_line(c) for c in clause_specs)


class ClaudeReviewer:
    name = "claude-sonnet-4-6"

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        self.api_key = os.environ["ANTHROPIC_API_KEY"]

    def classify(
        self, text: str, clause_specs: tuple[ClauseSpec, ...]
    ) -> list[ClauseHit]:
        user = (
            f"Clause types:\n{_clause_menu(clause_specs)}\n\n"
            f"Candidate source text:\n\"\"\"\n{text}\n\"\"\""
        )
        return _call_claude(
            self.api_key, self.model, _REVIEW_SYSTEM, user, clause_specs
        )


class ClaudeClassifier:
    """Primary clause detector backed by Claude (recall-first)."""

    name = "claude-sonnet-4-6"

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        self.api_key = os.environ["ANTHROPIC_API_KEY"]

    def classify(
        self, text: str, clause_specs: tuple[ClauseSpec, ...]
    ) -> list[ClauseHit]:
        user = (
            f"Clause types to detect:\n{_clause_menu(clause_specs)}\n\n"
            f"Contract:\n\"\"\"\n{text}\n\"\"\""
        )
        return _call_claude(
            self.api_key, self.model, _CLASSIFY_SYSTEM, user, clause_specs
        )
