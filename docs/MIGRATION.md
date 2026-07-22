# SQLite → Postgres Migration — Status & Cutover Guide

**Current state: NOT complete. SQLite is the sole source of truth in every deployed environment.**
This document is the single place to check before touching anything migration-related. It doesn't
replace [`PHASE3_EXECUTION_PLAN.md`](PHASE3_EXECUTION_PLAN.md) (the full milestone plan) or
[`PHASE3_FLAGS.md`](PHASE3_FLAGS.md) (the live flag ledger) — it summarizes both and gives the
exact remaining steps.

## What's already built (code-complete, not yet activated)

Every domain has dual-write code merged and tested, gated behind its own env var flag (default
`sqlite`, optionally `dual`):

| Domain | Flag | Dual-write covers |
|---|---|---|
| Projects | `PROJECTS_BACKEND` | create/update, best-effort sync to Postgres |
| Knowledge Base | `KB_BACKEND` | create + delete-as-archive (extracted text NOT synced) |
| Equipment | `EQUIPMENT_BACKEND` | create/update/delete + kb-sourced links |
| QMS (deviations/CAPAs/change controls/risk assessments) | `QMS_BACKEND` | flat fields + audit trail |

In `dual` mode, SQLite stays the read source of truth; every write also best-effort syncs to
Postgres (failures logged, never raised, SQLite write is never blocked). Backfill scripts
(`scripts/backfill_*.py`) and parity-check scripts (`scripts/check_*_parity.py`) exist for all
four domains and have each been run once against real Supabase with 0 drift (2026-07-12).

**None of this has been exercised under real, sustained production-like traffic yet — a one-shot
backfill + single parity check is not the same as an extended soak.**

## The non-negotiable gate before SQLite retirement (Phase 3.6)

Per `PHASE3_EXECUTION_PLAN.md` §3.6, stated as absolute:

1. **An extended Staging soak** of `PROJECTS_BACKEND`/`KB_BACKEND`/`EQUIPMENT_BACKEND`/
   `QMS_BACKEND` each running in `dual` in a real deployed Staging environment, long enough to
   surface drift under real usage patterns — not just a one-shot backfill.
2. **A 2-company RLS isolation spot-check** for each of the 4 domains — confirming Postgres Row
   Level Security actually prevents cross-tenant reads once two distinct companies have data in
   the same tables.

**As of this writing, neither has been performed.** `PHASE3_FLAGS.md` is the authoritative,
continuously-updated record of this — check it directly before assuming anything below has
changed.

## Cutover procedure, once the gate is satisfied

### Step 1 — Staging soak (env var flip, no code change)

In the Staging environment only, set:

```
PROJECTS_BACKEND=dual
KB_BACKEND=dual
EQUIPMENT_BACKEND=dual
QMS_BACKEND=dual
```

This is a pure env var change — the code path already exists. Run backfill scripts once, then run
parity-check scripts on a schedule for the soak duration. Do **not** set these in `render.yaml`'s
production `envVars` block, or in any production environment, until Step 1 and Step 2 both pass.

### Step 2 — 2-company RLS isolation spot-check

Create two distinct companies in the Staging Postgres instance, populate each with data across all
4 domains, and verify — as company A — that no query can read company B's rows (and vice versa).
Do this for each of the 4 domains independently.

### Step 3 — Update the flag ledger

Once both pass, update `PHASE3_FLAGS.md`'s Status column for each flag and record the soak
duration/dates and RLS spot-check results. This is the actual gate-pass artifact — Phase 3.6 does
not start without it.

### Step 4 — Phase 3.6: SQLite retirement (real code change, not a flag flip)

This is **not** a single toggle. Per `PHASE3_EXECUTION_PLAN.md` §3.6:

- Remove the SQLite branches from `pharmagpt/database.py` and its 9 sibling `*_database.py` files.
- Remove the `*_BACKEND` flags from `pharmagpt/config.py` and every route that checks them.
- For **Projects specifically**: a genuine Postgres read-cutover additionally requires a route/ID
  reshape first — the target `projects` table drops several fields present in SQLite today
  (`equipment_name`, `manufacturer`, `department`, etc. — those move to the Equipment Library) and
  uses UUID ids where every route today uses `<int:project_id>`. Flipping reads to Postgres without
  this change would break the frontend, not just move where the bytes live — this is why no
  `postgres` (read-cutover) state exists for `PROJECTS_BACKEND` today, only `sqlite`/`dual`. This
  reshape is real engineering work, not a config change, and has not been started.
- Run the full test suite against the Postgres-only path.
- Remove `DB_PATH`, the `disk:` block, and the persistent disk itself from `render.yaml` (they
  become dead, still-billed infrastructure once SQLite is retired) — but only in the same change
  that completes retirement, not before (removing the disk before cutover loses the production
  database on the next redeploy).
- Tag `phase3-complete`.

**Do not attempt Step 4 preemptively.** Everything above Step 4 (env var flip, soak, RLS check) is
low-risk and reversible. Step 4 is not — it deletes the SQLite fallback that currently is the only
production source of truth, in a multi-tenant regulated system where a cross-tenant isolation bug
was fixed as recently as this migration effort itself. Treat it with the same care as any
irreversible production data-path change.

## Where things stand right now

- Deployed environments: `sqlite` everywhere (all flags at their default).
- Staging soak: not started.
- 2-company RLS spot-check: not performed.
- Phase 3.6 (SQLite retirement / route reshape): not started, blocked on the above.
