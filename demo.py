"""Zero-config M1 demo: parse the pre-loaded contract, prove citations anchor.

    python demo.py

Shows, with no setup and no network:
  1. The contract parses into offset-exact spans.
  2. EVERY span round-trips (raw_text[start:end] == span.text).
  3. The 5 v1 target clauses are locatable by character offset — i.e. a
     citation could already point at the exact source text today.
"""

from __future__ import annotations

from auditagent.chunker import chunk_contract
from auditagent.data import SAMPLE_CONTRACT_PATH, load_sample_contract_text
from auditagent.parser import parse_text

# v1 thin-slice clause types -> a phrase that appears in that clause.
TARGET_CLAUSES = {
    "Change of Control": "Change of Control",
    "Uncapped Liability": "liability shall be unlimited",
    "Auto-renewal Notice": "automatically renew",
    "Non-Compete": "competes with the Provider",
    "Termination for Convenience": "for any reason or no reason",
}


def main() -> None:
    raw = load_sample_contract_text()
    parsed = parse_text(raw, doc_id="sample", source_name=SAMPLE_CONTRACT_PATH.name)
    chunks = chunk_contract(parsed)
    report = parsed.integrity_report()

    print("=" * 70)
    print("AuditAgent — Milestone 1 demo")
    print("=" * 70)
    print(f"Contract       : {parsed.source_name}")
    print(f"Characters     : {parsed.n_chars}")
    print(f"Spans          : {parsed.n_spans}")
    print(f"Chunks         : {len(chunks)}")
    print(f"Citation anchor: {'ALL OK ✅' if report['all_spans_anchor'] else 'FAILING ❌'}"
          f"  ({report['n_spans'] - report['n_failing']}/{report['n_spans']} round-trip)")
    print()
    print("Locating the 5 v1 target clauses by exact character offset:")
    print("-" * 70)

    for clause_name, needle in TARGET_CLAUSES.items():
        hit = next((s for s in parsed.spans if needle in s.text), None)
        if hit is None:
            print(f"  ❌ {clause_name:<28} not found")
            continue
        # Prove the offsets are real: re-slice raw text independently.
        quoted = raw[hit.start_char : hit.end_char]
        ok = quoted == hit.text
        preview = " ".join(hit.text.split())[:60]
        print(f"  ✅ {clause_name:<28} chars [{hit.start_char}:{hit.end_char}] "
              f"(anchor {'ok' if ok else 'BROKEN'})")
        print(f"       “{preview}…”")

    print("-" * 70)
    print("Every offset above was re-sliced from the raw document and matched.")
    print("That round-trip is the foundation every later citation depends on.")


if __name__ == "__main__":
    main()
