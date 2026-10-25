#!/usr/bin/env bash
# audit_workflow_backfill_safety_readonly.sh
#
# READ-ONLY evidence-collection script for the Yuktav RBAC backfill safety
# check. Run this ONLY on the production host, against the REAL production
# SQLite file. It performs zero writes: opens the database via Python's
# built-in sqlite3 module using a read-only URI (mode=ro) AND sets
# `PRAGMA query_only = ON;` as a second, independent guard, then runs
# SELECT-only queries.
#
# Uses Python's stdlib sqlite3 module instead of the `sqlite3` CLI binary
# (which is not installed on the Oracle host) — this app's own persistence
# layer (pharmagpt/database.py) already requires a working Python sqlite3
# module to run at all, so its presence here is guaranteed, not assumed.
# The read-only guarantee is equivalent-or-stronger than the CLI's
# `-readonly` flag: `mode=ro` in the connection URI opens the underlying
# file descriptor itself as read-only at the OS level (SQLite refuses any
# write attempt with `sqlite3.OperationalError: attempt to write a
# readonly database`, before `PRAGMA query_only` is even reached), and
# `PRAGMA query_only = ON` remains as the second, independent guard on top.
#
# It does NOT:
#   - INSERT / UPDATE / DELETE / ALTER / DROP / VACUUM / REINDEX anything
#   - modify Supabase, users, workflow assignments, or any file
#   - deploy, restart services, or touch systemd/Nginx
#   - print names, emails, display_name, or any document/record content
#
# It DOES:
#   - verify the target file is the intended production DB (exact path
#     match, refuses .bak/.old/copy files, refuses a missing file)
#   - run `PRAGMA integrity_check`
#   - confirm the 3 required tables exist
#   - for the 7 Initiator-tier candidates + User-019, check whether they
#     are a named approver on any ACTIVE (pending/in_progress step, in
#     in_progress instance) approval-type workflow step
#   - print a PASS / REVIEW REQUIRED verdict
#
# ── FILL IN THE 8 REAL USER IDS BELOW BEFORE RUNNING ─────────────────────
# These are the actual Supabase `users.id` (uuid) values this script will
# search for in qms_workflow_step_approvers.user_id. Nothing else in this
# script needs editing. Leave a value blank ("") to skip that user (it will
# be reported as "NOT CHECKED", not silently treated as zero).

USER_004="2d9a2f87-046a-42d3-ad73-5b42e126dde6"
USER_005="39882122-7f0c-4dbd-99bd-c526ebfab981"
USER_010="7e24317f-af56-4e5e-a20c-a58b81ed31d8"
USER_011="80133165-4d1f-41a8-ab13-4bea14c1353d"
USER_018="c743f776-59bd-4687-a1ee-6e884aed875a"
USER_021="e839c62e-5c58-4b8a-8da6-2ce3574b0cd4"
USER_023="ec2cfb1f-a71a-49ca-b822-a7ff52917705"
USER_019="cc92d76e-169f-4964-b50b-685e0956f2e8"   # Coordinator — checked separately per task §7, not part of the pass/fail verdict

# ── Expected production DB path — the script refuses anything else ───────
EXPECTED_DB_PATH="/home/ubuntu/PharmaGPT/pharmagpt/pharmagpt.db"
DB_PATH="${DB_PATH:-$EXPECTED_DB_PATH}"

set -u
echo "=================================================================="
echo "YUKTAV RBAC BACKFILL — WORKFLOW APPROVAL SAFETY AUDIT (READ-ONLY)"
echo "=================================================================="
echo

# ── 1/2. Identify + verify the database ──────────────────────────────────
echo "--- Database identification ---"
echo "Target path      : $DB_PATH"

if [[ "$DB_PATH" != "$EXPECTED_DB_PATH" ]]; then
    echo "WARNING: DB_PATH does not match the expected production path"
    echo "         ($EXPECTED_DB_PATH). Refusing to continue unless you"
    echo "         explicitly intended to point at a different file."
    exit 1
fi

case "$DB_PATH" in
    *.bak|*.old|*copy*|*backup*)
        echo "REFUSED: path looks like a backup/copy file, not the live production DB."
        exit 1
        ;;
esac

if [[ ! -f "$DB_PATH" ]]; then
    echo "REFUSED: file does not exist at $DB_PATH"
    exit 1
fi
echo "File exists      : YES"

DB_SIZE=$(stat -c '%s' "$DB_PATH" 2>/dev/null || stat -f '%z' "$DB_PATH" 2>/dev/null)
echo "File size (bytes): ${DB_SIZE:-unknown}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "REFUSED: python3 not found on this host — cannot run the read-only audit."
    exit 1
fi

# Python read-only query helper, written once to a temp file with a QUOTED
# heredoc ('PYEOF') so bash performs zero variable/glob expansion inside
# it — the Python source is byte-for-byte fixed, never templated from
# shell input. Opens strictly via a read-only URI (mode=ro), sets
# PRAGMA query_only = ON immediately after connecting, executes the
# statements from the query file (split on ';'), and prints only the
# last statement's result rows, '|'-delimited — identical output shape
# to the sqlite3 CLI's default batch/list mode, so every consumer below
# (grep -c, sed) is completely unchanged.
PY_HELPER=$(mktemp)
cat > "$PY_HELPER" <<'PYEOF'
import sqlite3
import sys

db_path = sys.argv[1]
query_file = sys.argv[2]

with open(query_file, "r") as f:
    sql = f.read()

uri = "file:" + db_path + "?mode=ro"
conn = sqlite3.connect(uri, uri=True)
conn.execute("PRAGMA query_only = ON;")

cur = conn.cursor()
last_rows = []
for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
    cur.execute(stmt)
    try:
        rows = cur.fetchall()
        if rows:
            last_rows = rows
    except sqlite3.ProgrammingError:
        pass  # statement returned no result set (e.g. a PRAGMA with no rows)

for row in last_rows:
    print("|".join("" if v is None else str(v) for v in row))

conn.close()
PYEOF

SQL_TMP=$(mktemp)

run_ro_query() {
    # $1 = SQL (one or more ';'-separated statements). Prints the last
    # statement's rows, '|'-delimited, exactly like the old `$SQLITE`
    # CLI invocation did.
    printf '%s' "$1" > "$SQL_TMP"
    python3 "$PY_HELPER" "$DB_PATH" "$SQL_TMP"
}

INTEGRITY=$(run_ro_query "PRAGMA query_only = ON; PRAGMA integrity_check;" 2>&1)
echo "integrity_check  : $INTEGRITY"
if [[ "$INTEGRITY" != "ok" ]]; then
    echo "REFUSED: integrity_check did not return 'ok'. Investigate before using this file for anything."
    exit 1
fi
echo

# ── 3. Required tables ────────────────────────────────────────────────────
echo "--- Required table existence ---"
for T in qms_workflow_step_approvers qms_workflow_instance_steps qms_workflow_instances; do
    EXISTS=$(run_ro_query "PRAGMA query_only = ON; SELECT count(*) FROM sqlite_master WHERE type='table' AND name='$T';")
    if [[ "$EXISTS" == "1" ]]; then
        echo "  $T : EXISTS"
    else
        echo "  $T : MISSING — cannot continue"
        exit 1
    fi
done
echo

# ── 5. The active-assignment query ────────────────────────────────────────
# Schema (confirmed from pharmagpt/qms_database.py — not assumed):
#   qms_workflow_instances.status        IN ('in_progress','completed','rejected')
#   qms_workflow_instance_steps.status   IN ('pending','in_progress','approved','rejected','returned','skipped')
#   qms_workflow_instance_steps.step_type IN ('approval','activity')
#   qms_workflow_step_approvers only ever holds rows for step_type='approval'
#   steps (activity steps are role-eligibility based, never named) — so any
#   row found here is, by construction, an approval-permission-requiring
#   assignment.
#
# "Active/in-flight" = the step itself is pending or in_progress AND its
# owning instance is in_progress (a completed/rejected instance has no
# live approval decision left to make, regardless of a stale step row).

run_check() {
    local label="$1" user_id="$2"
    if [[ -z "$user_id" ]]; then
        echo "$label:"
        echo "  NOT CHECKED (no user id supplied)"
        echo
        return
    fi
    local rows
    rows=$(run_ro_query "
PRAGMA query_only = ON;
SELECT s.instance_id, s.id, i.record_type, s.step_type, s.status, i.status
FROM qms_workflow_step_approvers a
JOIN qms_workflow_instance_steps s ON s.id = a.instance_step_id
JOIN qms_workflow_instances i ON i.id = s.instance_id
WHERE a.user_id = '$user_id'
  AND s.status IN ('pending','in_progress')
  AND i.status = 'in_progress';
")
    local count
    count=$(printf '%s\n' "$rows" | grep -c . || true)
    echo "$label:"
    echo "  Active named approval steps: $count"
    if [[ "$count" -gt 0 ]]; then
        echo "  instance_id|step_id|record_type|step_type|step_status|instance_status"
        printf '%s\n' "$rows" | sed 's/^/    /'
        echo "  Approval permission required: YES (all rows here are step_type='approval' by table design)"
    fi
    echo
    # Emit for the final tally.
    echo "$count" >> "$TALLY_FILE"
}

TALLY_FILE=$(mktemp)
trap 'rm -f "$PY_HELPER" "$SQL_TMP" "$TALLY_FILE"' EXIT

echo "--- Per-user active named-approval check ---"
run_check "USER-004" "$USER_004"
run_check "USER-005" "$USER_005"
run_check "USER-010" "$USER_010"
run_check "USER-011" "$USER_011"
run_check "USER-018" "$USER_018"
run_check "USER-021" "$USER_021"
run_check "USER-023" "$USER_023"

echo "--- User-019 (separate, informational only — not part of the pass/fail verdict) ---"
if [[ -z "$USER_019" ]]; then
    echo "USER-019:"
    echo "  NOT CHECKED (no user id supplied)"
else
    ROWS_019=$(run_ro_query "
PRAGMA query_only = ON;
SELECT s.instance_id, s.id, i.record_type, s.step_type, s.status, i.status
FROM qms_workflow_step_approvers a
JOIN qms_workflow_instance_steps s ON s.id = a.instance_step_id
JOIN qms_workflow_instances i ON i.id = s.instance_id
WHERE a.user_id = '$USER_019'
  AND s.status IN ('pending','in_progress')
  AND i.status = 'in_progress';
")
    COUNT_019=$(printf '%s\n' "$ROWS_019" | grep -c . || true)
    echo "USER-019:"
    echo "  Active named approval steps: $COUNT_019"
    if [[ "$COUNT_019" -gt 0 ]]; then
        printf '%s\n' "$ROWS_019" | sed 's/^/    /'
    fi
fi
echo

# ── 8. Decision ────────────────────────────────────────────────────────────
TOTAL=$(paste -sd+ "$TALLY_FILE" 2>/dev/null | bc 2>/dev/null || awk '{s+=$1} END{print s+0}' "$TALLY_FILE")
echo "=================================================================="
if [[ "${TOTAL:-0}" -eq 0 ]]; then
    echo "RBAC BACKFILL APPROVAL REGRESSION CHECK: PASS"
else
    echo "RBAC BACKFILL APPROVAL REGRESSION CHECK: REVIEW REQUIRED"
fi
echo "=================================================================="
echo
echo "PRODUCTION SQLITE MODIFIED: NO (opened via Python sqlite3 read-only URI mode=ro, PRAGMA query_only=ON, SELECT-only)"
