"""
tests/test_migrations_rls_recursion.py — static regression guard against
self-referencing RLS policies (Postgres 42P17 "infinite recursion detected
in policy for relation X").

Root cause this guards against (see HOTFIX_RLS_RECURSION.md, migration
0013): a `CREATE POLICY ... ON <table>` whose USING/WITH CHECK clause
subqueries that *same* table (`FROM <table>` / `JOIN <table>`) makes Postgres
re-evaluate the table's own RLS policies while evaluating the policy itself
— infinite recursion, breaking every query against that table (this broke
production login via migration 0012's users_company_admin_* policies).

This suite never touches a real Postgres/Supabase instance (matches every
other test in this repo — see tests/test_companies.py). It parses the
`*_up.sql` migration files as text.

Migrations are an append-only historical record — 0012's original (broken)
policy definitions are deliberately left on disk unchanged, superseded at
apply-time by migration 0013's `drop policy if exists` + `create policy`
for the same policy names (idempotent migrations, applied in numeric
order — every earlier `migrations/*.md`/runbook in this repo assumes this).
So this test computes the *effective* policy set — for each (table, policy
name), only the definition from the highest-numbered migration file that
(re)defines it — and checks that. Checking every historical file
individually would permanently fail on 0012, which is expected to still
contain the pre-fix definition.
"""

import glob
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "migrations")

_POLICY_START_RE = re.compile(
    r"create\s+policy\s+(\S+)\s+on\s+(\S+)", re.IGNORECASE
)


def _extract_policy_statements(sql_text):
    """Yield (policy_name, table_name, statement_body) for every
    CREATE POLICY statement in sql_text, paren-balanced so multi-line
    USING/WITH CHECK clauses are captured whole."""
    for match in _POLICY_START_RE.finditer(sql_text):
        policy_name, table_name = match.group(1), match.group(2).rstrip(",;")
        start = match.start()
        depth = 0
        end = None
        for i in range(start, len(sql_text)):
            ch = sql_text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == ";" and depth == 0:
                end = i
                break
        if end is None:
            end = len(sql_text)
        yield policy_name, table_name, sql_text[start:end]


def _self_references_table(statement_body, table_name, policy_name):
    """True if the policy body subqueries its own table via FROM/JOIN,
    excluding the leading 'create policy X on <table_name>' header itself."""
    header_match = re.search(
        r"create\s+policy\s+" + re.escape(policy_name) + r"\s+on\s+" + re.escape(table_name),
        statement_body,
        re.IGNORECASE,
    )
    body_after_header = statement_body[header_match.end():] if header_match else statement_body
    pattern = re.compile(
        r"\b(from|join)\s+" + re.escape(table_name) + r"\b", re.IGNORECASE
    )
    return bool(pattern.search(body_after_header))


def _all_up_migrations():
    return sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*_up.sql")))


def _effective_policies():
    """(table, policy_name) -> (statement_body, defining_file), keeping only
    the latest (highest-numbered migration) definition of each policy, since
    later `drop policy if exists` + `create policy` supersedes earlier ones
    when migrations are applied in order."""
    effective = {}
    for path in _all_up_migrations():
        with open(path, "r", encoding="utf-8") as fh:
            sql_text = fh.read()
        for policy_name, table_name, statement_body in _extract_policy_statements(sql_text):
            effective[(table_name, policy_name)] = (statement_body, os.path.basename(path))
    return effective


def test_no_effective_policy_subqueries_its_own_table():
    """No policy, as it will actually exist after all migrations are
    applied in order, may reference its own target table in a FROM/JOIN
    inside its USING/WITH CHECK clause — that is exactly the shape that
    caused the production login outage (42P17) fixed by migration 0013."""
    offenders = []
    for (table_name, policy_name), (statement_body, source_file) in _effective_policies().items():
        if _self_references_table(statement_body, table_name, policy_name):
            offenders.append((table_name, policy_name, source_file))

    assert not offenders, (
        f"Self-referencing RLS polic(y/ies) that will recurse (42P17): {offenders}. "
        f"Use a `security definer` helper function instead of a direct subquery "
        f"on the same table (see current_user_company_id()/current_user_role_name() "
        f"in migrations/0013_fix_users_rls_recursion_up.sql)."
    )


@pytest.mark.parametrize(
    "policy_name", ["users_company_admin_read_company", "users_company_admin_update_company"]
)
def test_0013_supersedes_0012_recursive_users_policy(policy_name):
    """Regression pin for the exact incident: after 0013 is applied, these
    two policies on `users` (originally defined recursively by 0012) must
    no longer subquery `users`, and 0013 must be the file that defines the
    effective version."""
    effective = _effective_policies()
    key = ("users", policy_name)
    assert key in effective, f"expected {policy_name} to still exist in the effective policy set"

    statement_body, source_file = effective[key]
    assert source_file == "0013_fix_users_rls_recursion_up.sql", (
        f"{policy_name}'s effective definition comes from {source_file}, expected "
        f"migration 0013 to be the latest (superseding) definition"
    )
    assert not _self_references_table(statement_body, "users", policy_name), (
        f"{policy_name} still self-references `users` after 0013 — "
        f"the recursion fix did not take effect"
    )
