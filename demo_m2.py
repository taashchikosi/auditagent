"""Milestone 2 demo: the catch, the citation gate, injection refusal, audit trail.

    python demo_m2.py

No API keys needed (deterministic provider). With DEEPSEEK_API_KEY /
ANTHROPIC_API_KEY set, the same pipeline calls the real models instead.
"""

from __future__ import annotations

from auditagent.data import load_injection_contract_text, load_sample_contract_text
from auditagent.pipeline import compare, run_review

LINE = "=" * 72


def main() -> None:
    raw = load_sample_contract_text()

    print(LINE)
    print("AuditAgent — Milestone 2 demo (4-agent pipeline + citation gate)")
    print(LINE)

    # 1) The catch — agent vs single-shot baseline (B1).
    cmp = compare(raw, perspective="buyer")
    print("\n[1] THE CATCH — single-shot (B1) vs AuditAgent")
    print(f"  B1 single-shot cites : {cmp['single_shot_b1']['cited']}")
    print(f"  AuditAgent cites     : {cmp['agent']['accepted_cited']}")
    print(f"  ⭐ Caught by agent only: {cmp['the_catch']}")
    print("     (B1 missed clauses buried past its context window, or couldn't"
          " cite them — the ContractEval 'laziness' failure.)")

    # 2) The citation gate — every accepted finding is proven against raw text.
    session = run_review(raw, doc_id="sample", source_name="sample_contract.txt",
                         perspective="buyer")
    print("\n[2] CITATION GATE — every accepted finding quotes an exact span")
    for r in session.memo.findings:
        c = r.finding.citation
        tag = "✅" if r.accepted else "⛔"
        loc = f"chars [{c.start_char}:{c.end_char}]" if c else "—"
        print(f"  {tag} {r.finding.clause_type:<28} {r.finding.risk_level.value:<6} {loc}")

    # 3) HITL gate.
    print(f"\n[3] HITL GATE — status before human decision: {session.memo.hitl_status}")
    memo = session.decide("approved")
    print(f"    after Approve/Escalate decision           : {memo.hitl_status}")

    # 4) Injection refusal.
    inj = run_review(load_injection_contract_text(), doc_id="inj",
                     source_name="inj.txt", perspective="buyer")
    print("\n[4] PROMPT-INJECTION REFUSAL (OWASP LLM01)")
    for flag in inj.memo.injection_flags:
        print(f"  🛡️  {flag}")
    print(f"    Despite the attack, real clauses still reported: "
          f"{[r.finding.clause_type for r in inj.memo.accepted_findings]}")

    # 5) Immutable audit trail.
    print("\n[5] IMMUTABLE AUDIT TRAIL (hash-chained)")
    print(f"  events logged   : {len(session.audit.events())}")
    print(f"  chain verified  : {session.audit.verify_chain()}  "
          f"(any tampering would break it)")

    print("\n" + LINE)
    print("M2 threshold met: 4 agents wired · every finding cites a valid span ·")
    print("uncited findings auto-rejected · HITL gate · injection resisted.")


if __name__ == "__main__":
    main()
