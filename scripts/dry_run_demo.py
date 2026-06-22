"""Demo dry-run gate — run BEFORE building the live demo UI.

Confirms three things on YOUR machine (the Cowork sandbox blocks the model API):
  1. The live model finds + cites the lawyer-labelled clauses in the two demo
     contracts (Webhelp hosting agreement, Tuniu cooperation agreement).
  2. The citations are sensible exact slices (not garbage spans).
  3. The adversarial contract triggers injection refusal while STILL reporting
     the real clauses — i.e. the "or it's thrown out" behaviour is real.

Usage (terminal only — never paste your key into a chat):
    cd ~/Documents/Claude/Projects/Agentic\\ AI\\ Portfolio/auditagent
    export DEEPSEEK_API_KEY=sk-...
    PYTHONPATH=src python3.14 scripts/dry_run_demo.py

With no key set it falls back to the offline deterministic provider — that only
proves the script runs; the REAL check needs the key.
"""

from __future__ import annotations

import os

from auditagent.data import load_injection_contract_text
from auditagent.eval.cuad import load_cuad_sample
from auditagent.pipeline import run_review

TARGETS = [
    ("WEBHELPCOMINC", "Web Hosting Agreement — Webhelp.com (SEC, 2000)"),
    ("TUNIUCORP", "Cooperation Agreement — Tuniu Corp (SEC, 2014)"),
]


def _find(contracts, match: str):
    for c in contracts:
        if match.lower() in c.doc_id.lower():
            return c
    return None


def _run(title: str, raw: str, perspective: str = "buyer") -> dict:
    print("\n" + "=" * 78)
    print(f"{title}   ({len(raw):,} chars · perspective={perspective})")
    print("=" * 78)
    session = run_review(
        raw, doc_id="dryrun", source_name="dryrun.txt", perspective=perspective
    )
    s = session.memo.summary()
    print(
        f"accepted={s['n_accepted']}  rejected={s['n_rejected']}  "
        f"high_risk={s['high_risk']}  injection_flags={len(s['injection_flags'])}  "
        f"audit_chain_valid={session.audit.verify_chain()}"
    )
    for r in session.memo.findings:
        cit = r.finding.citation
        risk = getattr(r.finding.risk_level, "value", None) or "-"
        if cit:
            quote = cit.quote[:90] + ("…" if len(cit.quote) > 90 else "")
            loc = f"chars {cit.start_char}-{cit.end_char}"
        else:
            quote, loc = "—", "no citation"
        print(f"  [{r.status.value:22}] {r.finding.clause_type:28} risk={risk:6} retries={r.retries}")
        print(f'      {loc}: "{quote}"')
    return s


def main() -> None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    print("Provider:", "REAL DeepSeek" if key else
          "OFFLINE deterministic — set DEEPSEEK_API_KEY for the real check")
    contracts = load_cuad_sample()
    for match, title in TARGETS:
        c = _find(contracts, match)
        if c is None:
            print(f"\nMISSING from sample: {match}")
            continue
        _run(title, c.context)
    _run("ADVERSARIAL contract — prompt-injection refusal check",
         load_injection_contract_text())

    print("\n" + "-" * 78)
    print("DEMO-READY CHECK:")
    print("  • Each real contract above should ACCEPT its labelled clauses with a")
    print("    sensible cited quote (Webhelp → Uncapped Liability + Auto-renewal;")
    print("    Tuniu → Non-Compete + Termination for Convenience).")
    print("  • The adversarial run should show injection_flags > 0 AND still accept")
    print("    the real clauses (it refuses the attack, doesn't go blind).")
    print("  Paste this output back into the chat and we decide go / swap-a-contract.")


if __name__ == "__main__":
    main()
