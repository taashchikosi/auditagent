"""Bundled sample data (CUAD-style contract) + loader helpers."""

from __future__ import annotations

from pathlib import Path

_DATA_DIR = Path(__file__).parent
SAMPLE_CONTRACT_PATH = _DATA_DIR / "sample_contract.txt"
SAMPLE_INJECTION_PATH = _DATA_DIR / "sample_contract_injection.txt"


def load_sample_contract_text() -> str:
    """Return the raw text of the pre-loaded sample contract."""
    return SAMPLE_CONTRACT_PATH.read_text(encoding="utf-8")


def load_injection_contract_text() -> str:
    """Return the adversarial contract with a hidden prompt-injection (wow #15)."""
    return SAMPLE_INJECTION_PATH.read_text(encoding="utf-8")
