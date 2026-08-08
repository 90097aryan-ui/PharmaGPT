"""
pharmagpt/providers — Pluggable AI provider backends.

Selection is driven by AI_PROVIDER (pharmagpt/config.py, sourced from
.env) via get_ai_client() in factory.py. See factory.py for the interface
contract every provider must satisfy.
"""
