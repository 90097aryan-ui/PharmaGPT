"""
logging_config.py — One-time structured logging setup for PharmaGPT.

Every module in the codebase already follows `logger = logging.getLogger(__name__)`
(see extractor.py, docs.py, knowledge_base.py, retrieval_engine.py, etc.) —
that convention is kept as-is. What was missing is any call that actually
configures a handler/level/formatter, so under gunicorn those messages were
silently dropped below the default WARNING level. configure_logging() fixes
that with a single INFO-level formatter for the whole `pharmagpt` logger
namespace, without needing per-module changes.
"""

import logging

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the `pharmagpt` logger namespace once. Safe to call multiple
    times (e.g. once per gunicorn worker import) — idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    logger = logging.getLogger("pharmagpt")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.propagate = False

    _CONFIGURED = True
