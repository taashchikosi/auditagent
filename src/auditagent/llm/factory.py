"""Env-driven provider selection. No keys → deterministic (CI-safe) default."""

from __future__ import annotations

import os

from .base import LLMProvider
from .deterministic import DeterministicProvider


def get_classifier() -> LLMProvider:
    """Primary clause classifier.

    Precedence: DeepSeek (locked production model) → Claude (real-model
    benchmark / fallback) → deterministic (CI-safe). DeepSeek first means the
    deploy-time swap back to DeepSeek is a no-op — just set its key.
    """
    if os.environ.get("DEEPSEEK_API_KEY"):
        from .deepseek import DeepSeekProvider

        return DeepSeekProvider()
    if os.environ.get("ANTHROPIC_API_KEY"):
        from .claude import ClaudeClassifier

        return ClaudeClassifier()
    return DeterministicProvider(lazy=False)


def get_reviewer() -> LLMProvider:
    """Citation-gate re-extractor.

    Precedence MIRRORS the classifier: DeepSeek → Claude → deterministic, so a
    DeepSeek run gets a DeepSeek gate (one model end-to-end — an honest, clean
    benchmark) rather than a DeepSeek detector wearing a Claude gate.
    """
    if os.environ.get("DEEPSEEK_API_KEY"):
        from .deepseek import DeepSeekReviewer

        return DeepSeekReviewer()
    if os.environ.get("ANTHROPIC_API_KEY"):
        from .claude import ClaudeReviewer

        return ClaudeReviewer()
    return DeterministicProvider(lazy=False)


def get_single_shot_baseline() -> LLMProvider:
    """B1 baseline: the thing the agent must beat.

    With a REAL model, B1 uses the SAME model and SAME full-context input as the
    agent — the only difference is that B1 has NO citation gate and NO retry.
    This is the honest test: the agent's edge must come from the gate/retry, not
    from crippling the baseline. (Offline, the deterministic baseline truncates
    context to *simulate* single-shot laziness — which is why offline numbers are
    a stand-in, not a benchmark.)
    """
    if os.environ.get("DEEPSEEK_API_KEY"):
        from .deepseek import DeepSeekProvider

        return DeepSeekProvider()  # one shot, no chunking/retry around it
    if os.environ.get("ANTHROPIC_API_KEY"):
        from .claude import ClaudeClassifier

        return ClaudeClassifier()  # same model as the agent; gate is the only diff
    return DeterministicProvider(lazy=True)
