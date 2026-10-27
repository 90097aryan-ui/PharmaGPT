"""
scripts/check_rls_isolation.py — Phase 3.6 gate: live 2-company Postgres RLS
isolation spot-check.

Context: docs/PHASE3_EXECUTION_PLAN.md §4's Go/No-Go checklist and
docs/MIGRATION.md Step 2 both require a live 2-company RLS isolation
spot-check, across all four Phase 3 domains, before Phase 3.6 (SQLite
retirement / `phase3-complete`) can start. TENANCY_VALIDATION.md and
docs/MULTI_TENANT_SECURITY_REPORT.md both verified the schema/policy/grant
layer statically and independently concluded the live check "cannot be
faked from a repo checkout" and requires two real company accounts against
a deployed environment. This script is that check, made repeatable.

Scope: 7 tables across the 4 domains named in PHASE3_FLAGS.md —
    Projects            -> projects
    Knowledge Base/Docs -> documents (source_context='knowledge_base')
    Equipment           -> equipment
    QMS                 -> deviations, capas, change_controls, risk_assessments

Out of scope, deliberately: pharmagpt/services/retrieval_engine.py's
chunk-retrieval/scoring logic. That code still reads SQLite only
(KB_BACKEND defaults to "sqlite" — see pharmagpt/config.py) and already has
its own, separate, passing regression coverage for the SQLite path
(tests/test_retrieval_engine_tenant_isolation.py, TEN-01). This script
validates the Postgres/RLS boundary directly via supabase-py — it does not
go through the Flask app and does not depend on, or change, any
*_BACKEND flag.

What this proves, and how: two real Supabase Auth identities are created
(or reused), one per test company, each with role 'user' — the role the
target RLS policies are documented as covering ("any authenticated user
may read/write rows in their own company", migrations/0005_projects_rls_up.sql).
One marked row is seeded per company in each of the 7 tables using the
SERVICE-ROLE client (bypasses RLS — same as every other Phase 3
backfill/seed script; setup only, never used for the assertions
themselves). Every isolation assertion then runs through a client
authenticated as one of the two real users (anon key + a real signed-in
access token — the same mechanism
pharmagpt/services/supabase_client.py::get_authenticated_client() uses on
every live request), so a pass here means Postgres RLS itself blocked the
read/write, not application code.

For each of the 7 tables, in both directions (Company A acting against
Company B's data, and the reverse):
    1. precondition_own_row_visible — the acting company's own seeded row
       IS visible via an authenticated list query (a positive control —
       without this, an isolation "pass" could just mean the connection/
       auth setup is broken, not that RLS is doing anything). If this
       fails, the remaining checks for that leg are marked INCONCLUSIVE,
       not skipped silently.
    2. list_excludes_other_company — the other company's row does not
       appear in an authenticated list query.
    3. direct_fetch_blocked — a direct fetch by the other company's known
       row id returns empty.
    4. update_blocked — an attempted UPDATE against the other company's
       known row id affects 0 rows, independently re-verified via the
       service-role client to confirm no mutation actually occurred
       (checks the RLS policy's WITH CHECK side, not just USING).

Evidence: one [PASS]/[FAIL]/[INCONCLUSIVE] line per check, plus a final
gate-ready summary block (paste-ready for docs/PHASE3_FLAGS.md, per
docs/MIGRATION.md's "record the soak duration/dates and RLS spot-check
results" instruction). Exit code 0 only when every check passed and none
were inconclusive.

Safety:
  - Refuses to run without an explicit --yes flag (any write, including
    --cleanup, requires it).
  - Refuses to run unless RLS_TEST_CONFIRM_STAGING=staging is set exactly
    — no default, no fuzzy match. This is a new env var, specific to this
    script only (same convention as SUPER_ADMIN_EMAIL being specific to
    scripts/bootstrap_super_admin.py).
  - Refuses to run, even with that confirmation, if SUPABASE_URL contains
    "prod" — a check that cannot be bypassed by the confirmation var.
  - Prints the resolved SUPABASE_URL prominently before anything else.
  - All seeded data uses fixed, highly distinctive markers
    ("RLS-ISOLATION-TEST::<table>::company-<a|b>", company legal names
    prefixed "RLS Isolation Test —", emails on the .invalid TLD) so it can
    never be confused with real tenant data and is safe to identify for
    manual cleanup even without --cleanup.
  - --cleanup (off by default) deletes only rows/identities matching
    those exact fixed markers — never a table-wide or company-wide
    delete. Safe to run standalone, independent of a prior run's state.

Usage:
    python scripts/check_rls_isolation.py --yes
    python scripts/check_rls_isolation.py --yes --cleanup

Reads from .env:
    SUPABASE_URL
    SUPABASE_ANON_KEY
    SUPABASE_SERVICE_ROLE_KEY
    RLS_TEST_CONFIRM_STAGING   (must be exactly "staging")

Run this against Staging only. Never production.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, create_client
from supabase_auth.errors import AuthApiError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bootstrap_super_admin import find_auth_user_by_email  # noqa: E402


class IsolationTestError(Exception):
    """Raised for any condition that should stop the isolation test before
    it writes anything or draws a conclusion."""


# ── Configuration ─────────────────────────────────────────────────────────

REQUIRED_ENV_VARS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY")
ENV_CONFIRM_VAR = "RLS_TEST_CONFIRM_STAGING"
ENV_CONFIRM_VALUE = "staging"

TEST_ROLE_NAME = "user"
# Fixed on purpose (same convention as scripts/seed_nutra_demo.py's
# DEMO_PASSWORD) — these identities are only ever reached via the
# .invalid-TLD email below, never a real inbox, and email_confirm=True
# means no mail is ever sent regardless.
TEST_PASSWORD = "RlsIsolationTest!2026-DoNotUse"

COMPANY_LABELS = ("a", "b")

COMPANY_LEGAL_NAMES = {
    "a": "RLS Isolation Test — Company A (safe to delete)",
    "b": "RLS Isolation Test — Company B (safe to delete)",
}
COMPANY_INDUSTRY_SEGMENT = "pharma"

USER_EMAILS = {
    "a": "rls-test-company-a@pharmagpt-internal-test.invalid",
    "b": "rls-test-company-b@pharmagpt-internal-test.invalid",
}
USER_DISPLAY_NAMES = {
    "a": "RLS Isolation Test User A",
    "b": "RLS Isolation Test User B",
}

# One spec per table under test. marker_field is the NOT NULL text column
# used both to hold the identifying marker and as the update_blocked
# check's tamper target. extra carries any other required/constrained
# columns (migrations/0004_core_schema_up.sql).
TABLE_SPECS = [
    {"domain": "Projects", "table": "projects", "marker_field": "name", "extra": {}},
    {
        "domain": "Knowledge Base/Documents", "table": "documents", "marker_field": "document_type",
        "extra": {"source_context": "knowledge_base", "status": "draft"},
    },
    {"domain": "Equipment", "table": "equipment", "marker_field": "name", "extra": {}},
    {"domain": "QMS — Deviations", "table": "deviations", "marker_field": "title", "extra": {}},
    {"domain": "QMS — CAPAs", "table": "capas", "marker_field": "title", "extra": {}},
    {"domain": "QMS — Change Controls", "table": "change_controls", "marker_field": "title", "extra": {}},
    {"domain": "QMS — Risk Assessments", "table": "risk_assessments", "marker_field": "title", "extra": {}},
]


def marker_value(table: str, company_label: str) -> str:
    return f"RLS-ISOLATION-TEST::{table}::company-{company_label}"


# ── Config loading / safety gate ────────────────────────────────────────────

def load_config(env: dict) -> dict:
    """Pull configuration out of an environment mapping (a plain dict, not
    os.environ directly, so tests can exercise this without a real .env
    file — same pattern as every other Phase 3 script)."""
    config = {name: env.get(name) for name in REQUIRED_ENV_VARS}
    config[ENV_CONFIRM_VAR] = env.get(ENV_CONFIRM_VAR)

    missing = [name for name in REQUIRED_ENV_VARS if not config[name]]
    if missing:
        raise IsolationTestError("Missing required .env values: " + ", ".join(missing))

    return config


def assert_safe_target(supabase_url: str, confirm_value: str | None) -> None:
    """Refuse to run unless the operator has explicitly, exactly confirmed
    the target is Staging, AND the URL itself doesn't look production-
    named. Neither check can substitute for the other."""
    if (confirm_value or "") != ENV_CONFIRM_VALUE:
        raise IsolationTestError(
            f"Refusing to run: {ENV_CONFIRM_VAR} is not set to exactly "
            f"{ENV_CONFIRM_VALUE!r}. This script creates real Supabase Auth "
            "identities and rows in whatever project SUPABASE_URL points at. "
            f"Set {ENV_CONFIRM_VAR}={ENV_CONFIRM_VALUE} in your Staging "
            "environment's .env only after you have personally confirmed "
            "SUPABASE_URL is Staging — never production."
        )
    if "prod" in supabase_url.lower():
        raise IsolationTestError(
            f"Refusing to run: SUPABASE_URL ({supabase_url}) contains 'prod'. "
            f"This check cannot be bypassed by {ENV_CONFIRM_VAR}."
        )


# ── Supabase clients ─────────────────────────────────────────────────────

def build_service_role_client(url: str, service_role_key: str) -> Client:
    """Setup/teardown only — bypasses RLS. Never used for an isolation
    assertion itself; see module docstring."""
    return create_client(url, service_role_key)


def sign_in(url: str, anon_key: str, email: str, password: str) -> str:
    client = create_client(url, anon_key)
    try:
        session = client.auth.sign_in_with_password({"email": email, "password": password})
    except AuthApiError as exc:
        raise IsolationTestError(f"Could not sign in as {email}: {exc}") from exc
    return session.session.access_token


def build_authenticated_client(url: str, anon_key: str, access_token: str) -> Client:
    """The real RLS path: anon key + a real user's access token, exactly
    like pharmagpt/services/supabase_client.py::get_authenticated_client()."""
    client = create_client(url, anon_key)
    client.postgrest.auth(access_token)
    return client


# ── Fixture setup (service-role client) ─────────────────────────────────────

def get_role_id(client: Client, role_name: str) -> int:
    result = client.table("roles").select("id").eq("name", role_name).maybe_single().execute()
    row = result.data if result else None
    if not row:
        raise IsolationTestError(
            f"No {role_name!r} row in roles table — has migrations/0001_identity_tenancy_up.sql "
            "been applied to this project?"
        )
    return row["id"]


def find_or_create_company(client: Client, legal_name: str) -> str:
    existing = client.table("companies").select("id").eq("legal_name", legal_name).limit(1).execute()
    if existing.data:
        return existing.data[0]["id"]
    created = client.table("companies").insert(
        {"legal_name": legal_name, "industry_segment": COMPANY_INDUSTRY_SEGMENT}
    ).execute()
    return created.data[0]["id"]


def find_or_create_test_user(client: Client, email: str, display_name: str, company_id: str,
                              role_id: int, password: str) -> str:
    auth_user = find_auth_user_by_email(client, email)
    if auth_user is None:
        try:
            response = client.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"display_name": display_name},
            })
            auth_user = response.user
        except AuthApiError as exc:
            raise IsolationTestError(f"Could not create test identity {email}: {exc}") from exc

    existing_profile = client.table("users").select("id").eq("id", auth_user.id).maybe_single().execute()
    if not (existing_profile.data if existing_profile else None):
        client.table("users").insert({
            "id": auth_user.id,
            "company_id": company_id,
            "role_id": role_id,
            "display_name": display_name,
            "status": "active",
        }).execute()

    return auth_user.id


def find_or_create_row(client: Client, table: str, company_id: str, marker_field: str,
                        marker: str, extra: dict) -> str:
    existing = (
        client.table(table).select("id")
        .eq("company_id", company_id).eq(marker_field, marker).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    payload = {"company_id": company_id, marker_field: marker, **extra}
    created = client.table(table).insert(payload).execute()
    return created.data[0]["id"]


def setup_fixtures(service_client: Client) -> dict:
    """Idempotent. Returns {"company_ids": {a,b}, "row_ids": {table: {a,b}}}."""
    role_id = get_role_id(service_client, TEST_ROLE_NAME)

    company_ids = {
        label: find_or_create_company(service_client, COMPANY_LEGAL_NAMES[label])
        for label in COMPANY_LABELS
    }

    for label in COMPANY_LABELS:
        find_or_create_test_user(
            service_client, USER_EMAILS[label], USER_DISPLAY_NAMES[label],
            company_ids[label], role_id, TEST_PASSWORD,
        )

    row_ids: dict[str, dict[str, str]] = {}
    for spec in TABLE_SPECS:
        row_ids[spec["table"]] = {
            label: find_or_create_row(
                service_client, spec["table"], company_ids[label],
                spec["marker_field"], marker_value(spec["table"], label), spec["extra"],
            )
            for label in COMPANY_LABELS
        }

    return {"company_ids": company_ids, "row_ids": row_ids}


# ── Checks ───────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    domain: str
    table: str
    direction: str
    check: str
    passed: bool
    inconclusive: bool
    detail: str

    def line(self) -> str:
        if self.inconclusive:
            tag = "[INCONCLUSIVE]"
        else:
            tag = "[PASS]" if self.passed else "[FAIL]"
        return (f"{tag} domain={self.domain!r} table={self.table} direction={self.direction} "
                f"check={self.check} — {self.detail}")


def check_update_blocked(auth_client: Client, service_client: Client, table: str,
                          marker_field: str, other_row_id: str, original_marker: str) -> tuple[bool, str]:
    """Attempt to mutate the other company's row as the acting company's
    authenticated user, then independently re-read it via the service-role
    client (bypasses RLS) to confirm no mutation actually happened —
    trusts a real read-back over PostgREST's reported affected-row count
    alone."""
    tamper_value = original_marker + "::TAMPER-ATTEMPT"
    try:
        update_result = (
            auth_client.table(table).update({marker_field: tamper_value}).eq("id", other_row_id).execute()
        )
        affected = update_result.data or []
    except APIError:
        affected = []  # a hard permission error is also a block, not a failure to check

    verify = service_client.table(table).select(marker_field).eq("id", other_row_id).maybe_single().execute()
    current_value = (verify.data or {}).get(marker_field) if verify else None

    passed = (len(affected) == 0) and (current_value == original_marker)
    if passed:
        detail = "update attempt affected 0 rows, value confirmed unchanged via service-role read-back"
    else:
        detail = (f"LEAK: update affected {len(affected)} row(s); current value={current_value!r} "
                  f"(expected unchanged {original_marker!r})")
    return passed, detail


def run_checks_for_table(spec: dict, auth_clients: dict[str, Client], service_client: Client,
                          row_ids: dict[str, dict[str, str]]) -> list[CheckResult]:
    results: list[CheckResult] = []
    table = spec["table"]
    domain = spec["domain"]
    marker_field = spec["marker_field"]

    for attacker, victim in (("a", "b"), ("b", "a")):
        direction = f"{attacker.upper()}→{victim.upper()}"
        client = auth_clients[attacker]
        own_row_id = row_ids[table][attacker]
        other_row_id = row_ids[table][victim]
        other_marker = marker_value(table, victim)

        try:
            listed = client.table(table).select(f"id, {marker_field}").execute()
            rows = listed.data or []
        except Exception as exc:  # noqa: BLE001 — any failure here invalidates this leg, not the run
            results.append(CheckResult(
                domain, table, direction, "precondition_own_row_visible", False, True,
                f"authenticated list query raised {exc!r} — cannot draw a conclusion for this leg",
            ))
            continue

        own_visible = any(r.get("id") == own_row_id for r in rows)
        if not own_visible:
            results.append(CheckResult(
                domain, table, direction, "precondition_own_row_visible", False, True,
                "own seeded row not visible via authenticated list query — auth/setup problem, "
                "not an isolation result; remaining checks for this leg skipped",
            ))
            continue

        results.append(CheckResult(
            domain, table, direction, "precondition_own_row_visible", True, False,
            "own seeded row visible as expected (positive control)",
        ))

        other_leaked = any(r.get("id") == other_row_id for r in rows)
        results.append(CheckResult(
            domain, table, direction, "list_excludes_other_company", not other_leaked, False,
            "other company's row absent from list query" if not other_leaked else
            f"LEAK: other company's row (id={other_row_id}) appeared in list query",
        ))

        fetch = client.table(table).select("id").eq("id", other_row_id).execute()
        fetch_blocked = not (fetch.data or [])
        results.append(CheckResult(
            domain, table, direction, "direct_fetch_blocked", fetch_blocked, False,
            "direct fetch by id returned empty as expected" if fetch_blocked else
            f"LEAK: direct fetch by id returned other company's row {other_row_id}",
        ))

        update_passed, update_detail = check_update_blocked(
            client, service_client, table, marker_field, other_row_id, other_marker,
        )
        results.append(CheckResult(domain, table, direction, "update_blocked", update_passed, False, update_detail))

    return results


# ── Reporting ────────────────────────────────────────────────────────────

def print_evidence(results: list[CheckResult]) -> tuple[int, int, int]:
    for result in results:
        print(result.line())
    passed = sum(1 for r in results if r.passed and not r.inconclusive)
    failed = sum(1 for r in results if not r.passed and not r.inconclusive)
    inconclusive = sum(1 for r in results if r.inconclusive)
    return passed, failed, inconclusive


def print_summary(supabase_url: str, results: list[CheckResult]) -> str:
    passed, failed, inconclusive = (
        sum(1 for r in results if r.passed and not r.inconclusive),
        sum(1 for r in results if not r.passed and not r.inconclusive),
        sum(1 for r in results if r.inconclusive),
    )
    total = len(results)
    verdict = "PASS" if failed == 0 and inconclusive == 0 and total > 0 else "FAIL"

    print()
    print("=" * 70)
    print("RLS ISOLATION TEST SUMMARY")
    print(f"Target: {supabase_url}")
    print(f"Timestamp (UTC): {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print(f"Tables covered: {len(TABLE_SPECS)}")
    print(f"Total checks: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Inconclusive: {inconclusive}")
    print(f"Gate verdict: {verdict}")
    print("=" * 70)
    print()
    print("Paste into docs/PHASE3_FLAGS.md:")
    print(
        f"  RLS isolation spot-check: {verdict}, {passed}/{total} checks passed, "
        f"{inconclusive} inconclusive, run against {supabase_url} on "
        f"{datetime.date.today().isoformat()}."
    )
    return verdict


# ── Cleanup (opt-in) ─────────────────────────────────────────────────────

def cleanup_fixtures(service_client: Client) -> None:
    """Delete only rows/identities matching this script's own fixed,
    distinctive markers/company names/emails — never a table-wide or
    unscoped delete. Safe to run standalone; idempotent (deleting nothing
    found is a no-op)."""
    for spec in TABLE_SPECS:
        for label in COMPANY_LABELS:
            marker = marker_value(spec["table"], label)
            service_client.table(spec["table"]).delete().eq(spec["marker_field"], marker).execute()
            print(f"[CLEANUP] {spec['table']}: deleted rows matching marker={marker!r} (if any)")

    for label in COMPANY_LABELS:
        email = USER_EMAILS[label]
        auth_user = find_auth_user_by_email(service_client, email)
        if auth_user is not None:
            service_client.table("users").delete().eq("id", auth_user.id).execute()
            service_client.auth.admin.delete_user(auth_user.id)
            print(f"[CLEANUP] deleted test identity {email}")
        else:
            print(f"[CLEANUP] no identity found for {email} (already clean)")

    for label in COMPANY_LABELS:
        legal_name = COMPANY_LEGAL_NAMES[label]
        service_client.table("companies").delete().eq("legal_name", legal_name).execute()
        print(f"[CLEANUP] companies: deleted row matching legal_name={legal_name!r} (if any)")


# ── Entry point ──────────────────────────────────────────────────────────

def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Live 2-company Postgres RLS isolation spot-check.")
    parser.add_argument("--yes", action="store_true",
                         help="Required before any write (seeding fixtures, or --cleanup).")
    parser.add_argument("--cleanup", action="store_true",
                         help="Delete only this script's own test fixtures, then exit. Off by default.")
    args = parser.parse_args()

    try:
        config = load_config(os.environ)
    except IsolationTestError as exc:
        print(f"check_rls_isolation: {exc}", file=sys.stderr)
        return 1

    supabase_url = config["SUPABASE_URL"]
    print(f"Target SUPABASE_URL: {supabase_url}")

    try:
        assert_safe_target(supabase_url, config[ENV_CONFIRM_VAR])
    except IsolationTestError as exc:
        print(f"check_rls_isolation: {exc}", file=sys.stderr)
        return 1

    if not args.yes:
        print(
            "Refusing to run: this script writes real Auth identities and rows to the "
            "project above. Re-run with --yes once you have confirmed the target.",
            file=sys.stderr,
        )
        return 1

    service_client = build_service_role_client(supabase_url, config["SUPABASE_SERVICE_ROLE_KEY"])

    if args.cleanup:
        cleanup_fixtures(service_client)
        print("Cleanup complete.")
        return 0

    try:
        fixtures = setup_fixtures(service_client)

        auth_clients = {
            label: build_authenticated_client(
                supabase_url, config["SUPABASE_ANON_KEY"],
                sign_in(supabase_url, config["SUPABASE_ANON_KEY"], USER_EMAILS[label], TEST_PASSWORD),
            )
            for label in COMPANY_LABELS
        }
    except IsolationTestError as exc:
        print(f"check_rls_isolation: setup failed: {exc}", file=sys.stderr)
        return 1

    results: list[CheckResult] = []
    for spec in TABLE_SPECS:
        results.extend(run_checks_for_table(spec, auth_clients, service_client, fixtures["row_ids"]))

    print_evidence(results)
    verdict = print_summary(supabase_url, results)

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
