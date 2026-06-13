"""CUAD loader — real expert labels, mapped to the 5 v1 clause types.

CUAD is SQuAD-style: each contract is a `context` with 41 questions (one per
clause type). A question with answers means the clause is PRESENT, and each
answer carries an `answer_start` char offset that anchors exactly against the
context — the same offset model AuditAgent uses. `is_impossible`/no-answers
means the clause is ABSENT (a gold negative — essential for precision).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# CUAD category name -> our v1 clause key.
CUAD_CATEGORY_TO_KEY: dict[str, str] = {
    "Change Of Control": "change_of_control",
    "Uncapped Liability": "uncapped_liability",
    "Notice Period To Terminate Renewal": "auto_renewal",
    "Non-Compete": "non_compete",
    "Termination For Convenience": "termination_for_convenience",
}

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "cuad"
SAMPLE_PATH = _DATA_DIR / "cuad_test_sample.json"

_CAT_RE = re.compile(r'related to "([^"]+)"')


@dataclass
class GoldSpan:
    start: int
    end: int
    text: str


@dataclass
class EvalContract:
    """One contract with gold labels for the 5 v1 clauses."""

    doc_id: str
    context: str
    gold: dict[str, list[GoldSpan]]  # clause_key -> gold spans ([] = absent)

    def is_present(self, clause_key: str) -> bool:
        return bool(self.gold.get(clause_key))


def _category_of(question: str) -> str | None:
    m = _CAT_RE.search(question)
    return m.group(1) if m else None


def load_cuad_file(path: str | Path, *, limit: int | None = None) -> list[EvalContract]:
    """Load contracts from a raw CUAD json (CUADv1.json or test.json)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    contracts: list[EvalContract] = []
    for entry in raw["data"]:
        para = entry["paragraphs"][0]
        ctx = para["context"]
        gold: dict[str, list[GoldSpan]] = {k: [] for k in CUAD_CATEGORY_TO_KEY.values()}
        for q in para["qas"]:
            key = CUAD_CATEGORY_TO_KEY.get(_category_of(q["question"]) or "")
            if key is None:
                continue
            if not q.get("is_impossible", False):
                for a in q["answers"]:
                    s, t = a["answer_start"], a["text"]
                    if ctx[s : s + len(t)] == t:  # keep only exact-anchoring gold
                        gold[key].append(GoldSpan(s, s + len(t), t))
        contracts.append(EvalContract(doc_id=entry["title"][:60], context=ctx, gold=gold))
        if limit and len(contracts) >= limit:
            break
    return contracts


def load_cuad_sample(*, limit: int | None = None) -> list[EvalContract]:
    """Load the shipped real CUAD test-split sample (no download needed)."""
    raw = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    contracts: list[EvalContract] = []
    for c in raw["contracts"]:
        gold = {
            k: [GoldSpan(s, e, t) for s, e, t in spans]
            for k, spans in c["gold"].items()
        }
        contracts.append(EvalContract(doc_id=c["doc_id"], context=c["context"], gold=gold))
        if limit and len(contracts) >= limit:
            break
    return contracts
