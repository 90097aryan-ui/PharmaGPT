#!/usr/bin/env python
"""
Approval-gated Nutra Validation signer provisioning (see docs/NUTRA_SIGNER_PROVISIONING_PLAN.md).

    python scripts/provision_validation_signers.py --approval approval.json --company-id <uuid>            # dry run (default)
    python scripts/provision_validation_signers.py --approval approval.json --company-id <uuid> --execute --rollback-out rollback.json

Dry run is read-only. --execute refuses without a complete written-approval record. The approval file
holds pseudonyms and approval references only (no names/emails) and must NOT be committed.
Run it from a checkout that contains the org_assignment audit-integrity fixes.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pharmagpt.services import signer_provisioning as sp  # noqa: E402


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--approval", required=True)
    ap.add_argument("--company-id", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--rollback-out", help="where to write the original rows (required with --execute)")
    args = ap.parse_args(argv)
    try:
        rec = json.load(open(args.approval, encoding="utf-8"))
        changes = sp.validate_approval(rec)
        if client is None:
            from pharmagpt.services.supabase_client import get_service_role_client
            client = get_service_role_client()
        steps = sp.plan(client, args.company_id, changes, rec["actor_pseudonym"])
    except (sp.ProvisioningError, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}")
        return 2
    for s in steps[:-1]:
        print(f"  {s['action']:6} {s['designation']:20} user {s['pseudonym']} -> {s['department_code']}/{s['functional_role']}"
              f" (is_primary={s['is_primary']}, before={s['before']})")
    if not args.execute:
        print("DRY RUN: nothing written.")
        return 0
    if not args.rollback_out:
        print("REFUSED: --rollback-out is required with --execute")
        return 2
    ref = "; ".join(f"{k}:{v['reference']}" for k, v in rec["approvals"].items())
    with open(args.rollback_out, "w", encoding="utf-8") as f:  # originals captured BEFORE any write
        json.dump([{k: s[k] for k in ("designation", "pseudonym", "department_code", "action", "before")}
                   for s in steps[:-1]], f, indent=2, default=str)
    try:
        results = sp.execute(client, args.company_id, steps, ref)
    except sp.ProvisioningError as exc:
        print(f"STOPPED: {exc}")
        return 1
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
