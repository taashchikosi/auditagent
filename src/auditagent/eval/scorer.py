"""CUAD scorer — detection metrics + the custom ones contract review needs.

Detection (L1) is what CUAD can measure. For each (contract, clause):
    gold_present?  vs  predicted_present?  →  TP / FP / FN / TN
From those: precision, recall, F1, macro-F1, a Precision–Recall sweep
(P@80%R, P@90%R, AUPR), plus:
  * laziness rate     — FN/(TP+FN): present clauses wrongly called absent
                        (ContractEval's failure mode; lower is better).
  * citation faithfulness — of correct detections, how many quoted a span
                        that actually overlaps a gold span (right answer AND
                        right evidence).
  * high-risk recall  — recall restricted to the high-severity clauses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..clauses import CLAUSES_BY_KEY
from ..models import RiskLevel
from .cuad import EvalContract, GoldSpan


# A single prediction for one (contract, clause).
@dataclass
class PredItem:
    present: bool
    span: tuple[int, int] | None = None
    confidence: float = 0.0


HIGH_RISK_KEYS = {k for k, s in CLAUSES_BY_KEY.items() if s.base_risk == RiskLevel.HIGH}


def _overlaps(span: tuple[int, int], golds: list[GoldSpan]) -> bool:
    s, e = span
    return any(max(0, min(e, g.end) - max(s, g.start)) > 0 for g in golds)


@dataclass
class ClauseScore:
    clause_key: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    faithful: int = 0  # TP whose span overlaps a gold span

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def laziness_rate(self) -> float:
        d = self.tp + self.fn
        return self.fn / d if d else 0.0

    @property
    def citation_faithfulness(self) -> float:
        return self.faithful / self.tp if self.tp else 0.0


def _pr_sweep(instances: list[tuple[float, bool]]) -> dict[str, float]:
    """instances = (score, gold_present). Returns P@80R, P@90R, AUPR."""
    n_pos = sum(1 for _, y in instances if y)
    if n_pos == 0:
        return {"p_at_80r": 0.0, "p_at_90r": 0.0, "aupr": 0.0}
    ranked = sorted(instances, key=lambda x: x[0], reverse=True)
    tp = fp = 0
    points: list[tuple[float, float]] = []  # (recall, precision)
    for _score, y in ranked:
        if y:
            tp += 1
        else:
            fp += 1
        recall = tp / n_pos
        precision = tp / (tp + fp)
        points.append((recall, precision))

    def p_at(target: float) -> float:
        best = 0.0
        for recall, precision in points:
            if recall >= target:
                best = max(best, precision)
        return best

    # AUPR via trapezoid over (recall, precision).
    aupr = 0.0
    prev_r = 0.0
    prev_p = points[0][1] if points else 0.0
    for recall, precision in points:
        aupr += (recall - prev_r) * (precision + prev_p) / 2
        prev_r, prev_p = recall, precision
    return {"p_at_80r": p_at(0.8), "p_at_90r": p_at(0.9), "aupr": aupr}


@dataclass
class EvalReport:
    per_clause: dict[str, ClauseScore] = field(default_factory=dict)
    pr: dict[str, dict[str, float]] = field(default_factory=dict)
    n_contracts: int = 0

    @property
    def macro_f1(self) -> float:
        scores = list(self.per_clause.values())
        return sum(s.f1 for s in scores) / len(scores) if scores else 0.0

    @property
    def high_risk_recall(self) -> float:
        hi = [s for k, s in self.per_clause.items() if k in HIGH_RISK_KEYS]
        tp = sum(s.tp for s in hi)
        fn = sum(s.fn for s in hi)
        return tp / (tp + fn) if (tp + fn) else 0.0

    @property
    def mean_laziness(self) -> float:
        scores = list(self.per_clause.values())
        return sum(s.laziness_rate for s in scores) / len(scores) if scores else 0.0

    @property
    def mean_citation_faithfulness(self) -> float:
        scores = [s for s in self.per_clause.values() if s.tp]
        return sum(s.citation_faithfulness for s in scores) / len(scores) if scores else 0.0

    def to_dict(self) -> dict:
        return {
            "n_contracts": self.n_contracts,
            "macro_f1": round(self.macro_f1, 4),
            "high_risk_recall": round(self.high_risk_recall, 4),
            "mean_laziness_rate": round(self.mean_laziness, 4),
            "mean_citation_faithfulness": round(self.mean_citation_faithfulness, 4),
            "per_clause": {
                k: {
                    "precision": round(s.precision, 4),
                    "recall": round(s.recall, 4),
                    "f1": round(s.f1, 4),
                    "laziness_rate": round(s.laziness_rate, 4),
                    "citation_faithfulness": round(s.citation_faithfulness, 4),
                    "p_at_80r": round(self.pr.get(k, {}).get("p_at_80r", 0.0), 4),
                    "aupr": round(self.pr.get(k, {}).get("aupr", 0.0), 4),
                    "support": s.tp + s.fn,
                }
                for k, s in self.per_clause.items()
            },
        }


def score_predictions(
    contracts: list[EvalContract],
    predictions: dict[str, dict[str, PredItem]],
) -> EvalReport:
    """Score predictions against CUAD gold. predictions[doc_id][clause_key]."""
    report = EvalReport(n_contracts=len(contracts))
    clause_keys = list(CLAUSES_BY_KEY.keys())
    pr_instances: dict[str, list[tuple[float, bool]]] = {k: [] for k in clause_keys}

    for key in clause_keys:
        score = ClauseScore(clause_key=key)
        for contract in contracts:
            gold_present = contract.is_present(key)
            pred = predictions.get(contract.doc_id, {}).get(key, PredItem(present=False))
            # PR instance: score is confidence when flagged, else 0.
            pr_instances[key].append((pred.confidence if pred.present else 0.0, gold_present))

            if gold_present and pred.present:
                score.tp += 1
                if pred.span and _overlaps(pred.span, contract.gold[key]):
                    score.faithful += 1
            elif gold_present and not pred.present:
                score.fn += 1
            elif not gold_present and pred.present:
                score.fp += 1
            else:
                score.tn += 1
        report.per_clause[key] = score
        report.pr[key] = _pr_sweep(pr_instances[key])
    return report
