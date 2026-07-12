"""
backend.py — reads which database backend is active for the current process.

Phase 3.1 scope only: this module exposes the switch point. It does not
itself talk to SQLite or Postgres, and no domain module is wired to it yet —
that happens per-domain in Phase 3.2+ (docs/PHASE3_EXECUTION_PLAN.md).
"""

from pharmagpt import config

VALID_BACKENDS = ("sqlite", "postgres")


def get_backend_name() -> str:
    """Return the configured backend name: "sqlite" (default) or "postgres"."""
    backend = config.DATABASE_BACKEND
    if backend not in VALID_BACKENDS:
        raise ValueError(
            f"Invalid DATABASE_BACKEND={backend!r}; expected one of {VALID_BACKENDS}"
        )
    return backend


def is_postgres_backend() -> bool:
    """True once DATABASE_BACKEND=postgres — always False until a later phase
    sets it, since nothing writes that env var today."""
    return get_backend_name() == "postgres"
