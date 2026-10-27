#!/usr/bin/env python
"""
READ-ONLY pre-deployment check for the standardized Validation approval workflow.

    python scripts/validation_approval_preflight.py --sqlite pharmagpt/pharmagpt.db
    python scripts/validation_approval_preflight.py --sqlite <db> --supabase          # live company directory (SELECT only)
    python scripts/validation_approval_preflight.py --sqlite <db> --directory-json snapshot.json --json report.json

Exit code: 0 = no blocking findings, 2 = blocking findings (do not deploy until resolved),
1 = could not run. Never writes to the database or the directory. See
docs/VALIDATION_APPROVAL_RECOVERY.md for what to do about each finding code.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pharmagpt.services import validation_preflight as pf  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite", required=True, help="path to the SQLite database (opened read-only)")
    ap.add_argument("--supabase", action="store_true", help="read companies/departments/roles from Supabase (SELECT only)")
    ap.add_argument("--directory-json", help="offline directory snapshot (companies/users/memberships/grants)")
    ap.add_argument("--json", dest="json_out", help="write the full report to this file")
    args = ap.parse_args(argv)

    directory = None
    if args.directory_json:
        directory = pf.StaticDirectory(json.load(open(args.directory_json, encoding="utf-8")))
    elif args.supabase:
        from pharmagpt.services.supabase_client import get_service_role_client
        directory = pf.SupabaseDirectory(get_service_role_client())

    try:
        report = pf.run_preflight(args.sqlite, directory)
    except Exception as exc:  # noqa: BLE001
        print(f"preflight could not run: {exc}", file=sys.stderr)
        return 1

    s = report["summary"]
    print(f"Validation approval preflight (read-only) — {'GO' if s['go'] else 'NO-GO'}")
    print(f"  blocking={s['blocking']}  action_required={s['action_required']}  warnings={s['warnings']}  ok={s['ok']}")
    for m in report["schema_migrations_pending"]:
        print(f"  [startup migration] {m['item']}: {m['effect']}")
    for c in report["companies"]:
        mark = "ready" if c["ready"] else "NOT READY"
        print(f"  company {c['company_name'] or c['company_id']}: {mark} (distinct assignable {c['distinct_assignable']}/7)")
        for f in c["findings"]:
            print(f"      {f['severity']}: {f['code']} {f.get('designation', '')} — {f['detail']}")
    for code, n in sorted(s["documents_by_code"].items()):
        print(f"  documents {code}: {n}")
    for f in report["documents"]:
        if f["severity"] in (pf.BLOCKING, pf.ACTION):
            print(f"      {f['severity']}: {f['kind']} #{f['id']} ({f['status']}) {f['code']} — {f['detail']}")
    for f in report["environment"]:
        if f["severity"] != pf.OK:
            print(f"      {f['severity']}: {f['detail']}")
    if args.json_out:
        json.dump(report, open(args.json_out, "w", encoding="utf-8"), indent=2, default=str)
        print(f"  full report written to {args.json_out}")
    return 0 if s["go"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
