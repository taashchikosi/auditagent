"""AuditAgent — autonomous contract-review & risk-flagging agent.

Through M3: offset-exact parsing + FastMCP tool layer (M1), the 4-agent
LangGraph pipeline + citation gate (M2), and the CUAD eval harness with a
real reproducible n=102 benchmark (M3). The whole project rests on one
invariant: every span knows its exact character position in the original
document, so every finding can cite the precise source text. See
ARCHITECTURE.md.
"""

__version__ = "0.3.0"  # M3 complete; M4 (deploy) in progress
