# Override the interpreter if your default python3 is too old (needs >=3.10):
#   make install PYTHON=python3.12
PYTHON ?= python3

.PHONY: install test demo serve mcp lint clean

install:        ## Install package + dev deps
	$(PYTHON) -m pip install ".[dev]"

test:           ## Run the test suite (offset round-trip is the key one)
	$(PYTHON) -m pytest -q

demo:           ## M1: parse the pre-loaded contract, prove citations anchor
	$(PYTHON) demo.py

demo-m2:        ## M2: full pipeline — the catch, citation gate, injection, audit
	$(PYTHON) demo_m2.py

eval:           ## M3: run the CUAD baseline ladder (B0/B1/B2) + per-clause F1
	$(PYTHON) -m auditagent.eval --json eval_report.json --md eval_report.md

eval-full:      ## M3: download CUAD, eval on the full 102-contract held-out test split
	$(PYTHON) scripts/download_cuad.py --extract
	$(PYTHON) -m auditagent.eval --full data/cuad/CUADv1_test.json

serve:          ## Run the FastAPI app (GET /health, /parse/sample) on :8002
	uvicorn auditagent.app:app --reload --port 8002

mcp:            ## Run the FastMCP contract-tools server (stdio)
	$(PYTHON) -m auditagent.mcp_server

lint:           ## Ruff lint
	ruff check src tests

clean:
	rm -rf .pytest_cache **/__pycache__ *.egg-info build dist
