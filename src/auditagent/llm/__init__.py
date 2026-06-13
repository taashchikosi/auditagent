"""Pluggable LLM layer.

The pipeline never imports a vendor SDK directly — it talks to an
`LLMProvider`. That keeps the orchestration, citation gate, checklist and
audit log fully runnable and testable with ZERO API keys (the deterministic
provider), while real DeepSeek/Claude drop in the moment a key is set.
"""

from .base import ClauseHit, LLMProvider
from .factory import get_classifier, get_reviewer

__all__ = ["ClauseHit", "LLMProvider", "get_classifier", "get_reviewer"]
