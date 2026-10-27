"""
services/company_branding.py — Client Company Branding -> Document Control
bridge (SOP DOCX header/footer company name).

Company display name lives on the `companies` table (Supabase/PostgREST),
not SQLite -- Document Control (qms_documents) is SQLite-backed, so this is
the one place a Document Control export path reaches across to the
identity/tenancy store, exactly as routes/companies.py already does for the
same table.

Deliberately does NOT resolve company_settings.logo_url into an embedded
image. That column has no upload/storage integration (migration 0017's own
comment: "No Supabase Storage integration exists yet ... upload handling and
DOCX injection are explicitly out of scope for this migration") and carries
no validation beyond a max-length check -- fetching it server-side as an
image URL during DOCX export would be a live SSRF vector (any company_admin
could point it at an internal service or a cloud metadata endpoint), and
there is no way to distinguish a genuine logo URL from anything else since
nothing has ever consumed this field before now. Logo auto-population
therefore needs either a real image upload/storage integration or a
hardened, allow-listed fetcher (scheme/host/IP validation, no redirects,
size cap, content-type check) before it can be added safely -- see the SOP
branding integration report for this as a flagged follow-up decision, not
an oversight.
"""

import logging

from pharmagpt.auth.decorators import extract_bearer_token
from pharmagpt.services.supabase_client import get_authenticated_client

logger = logging.getLogger(__name__)


def get_company_name_for_docx(company_id: str | None) -> str:
    """Read the caller's own company's legal_name for use in a generated
    document's header -- never another company's.

    Uses the REQUESTING USER'S OWN bearer token (get_authenticated_client),
    not the service-role client: `companies` carries an RLS policy
    (migration 0011, companies_company_admin_read_own) that lets any
    authenticated user read only the company row matching their own
    `auth.uid()` -- isolation is enforced by the database itself, not by the
    `company_id` filter added here (which only narrows the query). A caller
    cannot read another company's name by passing a different company_id:
    Postgres ANDs our filter with the RLS policy, so a mismatched id simply
    returns no row, never someone else's -- there is no company_id-spoofing
    bypass here even in principle.

    Returns "" (never raises) if company_id is falsy (e.g. a super_admin
    outside Assume Company Context -- TenantContext.company_id is None for
    that role, see pharmagpt/auth/context.py), there is no request bearer
    token, the row doesn't exist, or the Supabase call fails for any reason
    (missing configuration, network error, etc.). A branding lookup failure
    must never block document export.
    """
    if not company_id:
        return ""
    try:
        token = extract_bearer_token()
        if not token:
            return ""
        client = get_authenticated_client(token)
        result = (
            client.table("companies").select("legal_name")
            .eq("id", company_id).maybe_single().execute()
        )
        row = result.data if result else None
        return (row or {}).get("legal_name") or ""
    except Exception:
        # Covers a missing/invalid token, no active Flask request context
        # (extract_bearer_token() requires one), missing Supabase
        # configuration, network errors, and any Postgrest/API error alike
        # — every one of them must degrade to "no company name", never
        # raise into the caller.
        logger.exception(
            "get_company_name_for_docx: branding lookup failed for company_id=%s", company_id
        )
        return ""
