"""
pharmagpt.db — Phase 3 database migration seam.

This package is the single place later Phase 3 sub-phases (3.2 Projects,
3.3 Knowledge Base, 3.4 Equipment, 3.5 QMS) add a per-domain repository that
can read/write either SQLite (pharmagpt/database.py and siblings, today's
source of truth) or Postgres (Supabase, once a domain's tables are populated
and parity-verified), selected via config.DATABASE_BACKEND.

Nothing in pharmagpt/database.py or pharmagpt/routes/ imports this package
yet — it has zero effect on running behavior until a domain's cutover lands.
See docs/PHASE3_EXECUTION_PLAN.md.
"""
