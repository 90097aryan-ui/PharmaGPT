# Phase 3 Feature Flag Ledger

Tracked per `docs/PHASE3_EXECUTION_PLAN.md` §2 risk "Feature-flag sprawl." Every flag introduced during Phase 3 is listed here from the commit that adds it until the commit that resolves it (removed + old path deleted, per 3.6). None may reach Phase 3.6 unresolved.

| Flag | Default | States | Introduced | Status |
|---|---|---|---|---|
| `DATABASE_BACKEND` | `sqlite` | `sqlite`, `postgres` (reserved, unused) | 3.1 (`4da4913`) | Open — global seam, not yet consumed by any domain; superseded in practice by per-domain flags below. |
| `PROJECTS_BACKEND` | `sqlite` | `sqlite`, `dual` | 3.2 (`d235c86`) | Open — code written; not yet confirmed deployed/soaked in Staging (accelerated execution mode, see thread). A `postgres` (read-cutover) state is out of scope for 3.2 — see plan §3.2 note. |
| `KB_BACKEND` | `sqlite` | `sqlite`, `dual` | 3.3 (`57e62fa`) | Open — code written; not yet deployed. Covers create+delete(as archive) only — extracted-text sync is explicitly NOT dual-written (see config.py comment); backfill does a one-time copy only. |
| `EQUIPMENT_BACKEND` | `sqlite` | `sqlite`, `dual` | 3.4 (`a796f8f`) | Open — code written; not yet deployed. Covers create/update/(real)delete + kb-sourced link/unlink only. |

**Resolution owner:** whoever flips a flag in Staging/Production is responsible for updating this table's Status column in the same PR/commit.
