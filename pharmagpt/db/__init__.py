"""
pharmagpt.db — Phase 3 database migration seam.

This package is the single place later Phase 3 sub-phases (3.2 Projects,
3.3 Knowledge Base, 3.4 Equipment, 3.5 QMS) add a per-domain repository that
can read/write either SQLite (pharmagpt/database.py and siblings, today's
source of truth) or Postgres (Supabase, once a domain's tables are populated
and parity-verified), selected via config.DATABASE_BACKEND.

As of Phase 3.2-3.5, pharmagpt/routes/projects.py, knowledge_base.py,
equipment.py, risk.py, qms_capa.py, qms_deviations.py, and
qms_change_control.py import repos from this package for their dual-write
paths, gated behind each domain's *_BACKEND flag (default "sqlite", so this
remains a no-op until a flag is set to "dual"). See docs/PHASE3_EXECUTION_PLAN.md.
"""
