"""AuditAgent — autonomous contract-review & risk-flagging agent.

Milestone 1 scope: offset-exact contract parsing + FastMCP tool layer.
The whole project rests on one invariant: every span knows its exact
character position in the original document, so every later finding can
cite the precise source text. See ARCHITECTURE.md.
"""

__version__ = "0.1.0"  # M1
