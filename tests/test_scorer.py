"""Known-answer tests for the CUAD scorer — metrics must be exactly right."""

from __future__ import annotations

from auditagent.eval.cuad import EvalContract, GoldSpan
from auditagent.eval.scorer import PredItem, score_predictions


def _contract(doc_id, gold):
    return EvalContract(doc_id=doc_id, context="x" * 200, gold=gold)


def test_perfect_predictions_give_f1_one():
    contracts = [
        _contract("d1", {"change_of_control": [GoldSpan(0, 5, "xxxxx")],
                          "non_compete": [], "uncapped_liability": [],
                          "auto_renewal": [], "termination_for_convenience": []}),
    ]
    preds = {"d1": {"change_of_control": PredItem(present=True, span=(0, 5), confidence=0.9)}}
    rep = score_predictions(contracts, preds)
    coc = rep.per_clause["change_of_control"]
    assert coc.tp == 1 and coc.fp == 0 and coc.fn == 0
    assert coc.f1 == 1.0
    assert coc.citation_faithfulness == 1.0


def test_false_negative_is_laziness():
    contracts = [
        _contract("d1", {"non_compete": [GoldSpan(0, 5, "xxxxx")],
                         "change_of_control": [], "uncapped_liability": [],
                         "auto_renewal": [], "termination_for_convenience": []}),
    ]
    preds = {"d1": {}}  # missed it entirely
    rep = score_predictions(contracts, preds)
    nc = rep.per_clause["non_compete"]
    assert nc.fn == 1 and nc.recall == 0.0
    assert nc.laziness_rate == 1.0


def test_false_positive_hurts_precision():
    contracts = [
        _contract("d1", {"non_compete": [],  # absent
                         "change_of_control": [], "uncapped_liability": [],
                         "auto_renewal": [], "termination_for_convenience": []}),
    ]
    preds = {"d1": {"non_compete": PredItem(present=True, span=None, confidence=0.5)}}
    rep = score_predictions(contracts, preds)
    nc = rep.per_clause["non_compete"]
    assert nc.fp == 1 and nc.precision == 0.0


def test_right_answer_wrong_evidence_fails_faithfulness():
    contracts = [
        _contract("d1", {"uncapped_liability": [GoldSpan(100, 110, "xxxxxxxxxx")],
                         "change_of_control": [], "non_compete": [],
                         "auto_renewal": [], "termination_for_convenience": []}),
    ]
    # Correct detection, but the cited span doesn't overlap the gold span.
    preds = {"d1": {"uncapped_liability": PredItem(present=True, span=(0, 10), confidence=0.8)}}
    rep = score_predictions(contracts, preds)
    ul = rep.per_clause["uncapped_liability"]
    assert ul.tp == 1
    assert ul.citation_faithfulness == 0.0  # right answer, wrong evidence


def test_high_risk_recall_excludes_medium_clause():
    # auto_renewal is base MEDIUM, so it must NOT count toward high-risk recall.
    contracts = [
        _contract("d1", {"auto_renewal": [GoldSpan(0, 5, "xxxxx")],
                         "change_of_control": [GoldSpan(10, 15, "xxxxx")],
                         "uncapped_liability": [], "non_compete": [],
                         "termination_for_convenience": []}),
    ]
    preds = {"d1": {"change_of_control": PredItem(present=True, span=(10, 15), confidence=0.9)}}
    rep = score_predictions(contracts, preds)
    # CoC caught (high-risk), auto_renewal missed (medium) -> high-risk recall = 1.0
    assert rep.high_risk_recall == 1.0
