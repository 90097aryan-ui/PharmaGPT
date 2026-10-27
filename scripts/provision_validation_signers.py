#!/usr/bin/env python
"""
Authenticated, break-glass-gated Nutra Validation signer provisioning (see docs/NUTRA_SIGNER_PROVISIONING_PLAN.md).
FAILS CLOSED and is a DRY RUN unless --execute is given. Run only from a checkout containing the org_assignment fixes.

  1. python scripts/provision_validation_signers.py --company-id <uuid> --approval a.json --print-change-set-hash
        (read-only: prints the SHA-256 the approvers must write into the approval file as change_set_sha256)
  2. dry run (default; still authenticates, authorizes and verifies everything, writes nothing):
     python scripts/provision_validation_signers.py --company-id <uuid> --approval a.json \
        --actor-token-file actor.jwt --qa-approver-token-file qa.jwt [--admin-approver-token-file admin.jwt]
  3. add --execute --rollback-out rollback.json to apply (only after written approvals are established).
  4. python scripts/provision_validation_signers.py --company-id <uuid> --rollback rollback.json \
        --actor-token-file actor.jwt [--execute]            (audited undo; dry run unless --execute)

Identity: each *.jwt file holds a live Supabase access token for that person (never an id typed into a file); tokens
are verified with the application's own auth. A super_admin actor needs an ACTIVE break_glass_access grant for the
company. Independent QA approval is mandatory (QA approver != actor != changed users). Token and approval files hold
secrets/approval evidence: keep them OUTSIDE git.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pharmagpt.services import signer_provisioning as sp  # noqa: E402


def _read(path):
    if not path:
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _print_plan(steps):
    for s in steps:
        print(f"  {s['action']:6} {s['designation']:20} user {s['pseudonym']} -> {s['department_code']}/{s['functional_role']}"
              f" (is_primary={s['is_primary']}, before={s['before']})")


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company-id", required=True)
    ap.add_argument("--approval")
    ap.add_argument("--print-change-set-hash", action="store_true")
    ap.add_argument("--actor-token-file")
    ap.add_argument("--admin-approver-token-file")
    ap.add_argument("--qa-approver-token-file")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--rollback-out")
    ap.add_argument("--rollback", help="rollback file written by a previous --execute")
    args = ap.parse_args(argv)
    try:
        if args.rollback:
            return _rollback_mode(args, client)
        if not args.approval:
            raise sp.ProvisioningError("--approval is required")
        rec = json.load(open(args.approval, encoding="utf-8"))
        if args.print_change_set_hash:
            # structure-only: hash of the proposed change set (no approvals needed yet, no network, no writes)
            choice = (rec.get("reviewer_choice") or "").upper()
            print(sp.change_set_hash(args.company_id, choice, rec.get("changes") or []))
            return 0
        changes = sp.validate_approval(rec, args.company_id)
        if client is None:
            from pharmagpt.services.supabase_client import get_service_role_client
            client = get_service_role_client()
        parties = sp.establish_authority(client, args.company_id, rec, actor_token=_read(args.actor_token_file),
                                         admin_token=_read(args.admin_approver_token_file),
                                         qa_token=_read(args.qa_approver_token_file))
        steps = sp.plan(client, args.company_id, changes, parties)
    except (sp.ProvisioningError, OSError, ValueError, KeyError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    _print_plan(steps)
    print(f"actor verified; break-glass grant: {parties['grant_id'] or 'n/a (company_admin)'}")
    if not args.execute:
        print("DRY RUN: all checks passed, nothing written.")
        return 0
    if not args.rollback_out:
        print("REFUSED: --rollback-out is required with --execute")
        return 2
    with open(args.rollback_out, "w", encoding="utf-8") as f:  # originals captured BEFORE any write
        json.dump({"company_id": args.company_id, "approval": rec, "grant_id": parties["grant_id"],
                   "steps": sp.steps_for_rollback_file(steps)}, f, indent=2, default=str)
    try:
        results = sp.execute(client, args.company_id, steps, parties, rec)
    except sp.ProvisioningError as exc:
        print(f"STOPPED: {exc}")
        return 1
    print(json.dumps(results, indent=2, default=str))
    return 0


def _rollback_mode(args, client) -> int:
    saved = json.load(open(args.rollback, encoding="utf-8"))
    if saved.get("company_id") != args.company_id:
        raise sp.ProvisioningError("rollback file is for a different company")
    if client is None:
        from pharmagpt.services.supabase_client import get_service_role_client
        client = get_service_role_client()
    actor = sp.authenticate(_read(args.actor_token_file), "actor")
    grant = sp.authorize_administrator(client, actor, args.company_id, "actor")
    steps = saved["steps"]
    print(f"ROLLBACK of {len(steps)} change(s) as authenticated actor (break-glass: {grant or 'n/a (company_admin)'})")
    if not args.execute:
        print("DRY RUN: nothing written.")
        return 0
    problems = sp.rollback(client, args.company_id, steps, {"actor": actor, "grant_id": grant}, saved["approval"])
    print("ROLLED BACK" if not problems else f"ROLLBACK PROBLEMS: {problems}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
