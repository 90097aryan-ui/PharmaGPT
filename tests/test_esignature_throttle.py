"""Per-user e-signature password failure limit (21 CFR Part 11 unauthorized-use attempts).

Throttles e-signatures only (never login), counts only genuine wrong passwords (not Supabase
outages / 429s), and refuses throttled attempts WITHOUT calling Supabase.
"""

import pytest
from supabase_auth.errors import AuthApiError

from pharmagpt import database as maindb
from pharmagpt.auth.context import TenantContext
from pharmagpt.services import esignature_service as esig
from pharmagpt.services import validation_approval as va

COMPANY = "52df3b4a-d37e-4176-8a52-7171adf39637"


def _tenant(uid="u1"):
    return TenantContext(user_id=uid, email=f"{uid}@x.io", display_name=uid, role="reviewer_qa", company_id=COMPANY)


class _Client:
    def __init__(self, exc):
        self.exc = exc
        self.auth = self

    def sign_in_with_password(self, creds):
        if self.exc:
            raise self.exc
        return object()


def test_reauthenticate_distinguishes_wrong_password_from_outage(monkeypatch):
    def with_exc(exc):
        monkeypatch.setattr(esig, "get_anonymous_client", lambda: _Client(exc))

    with_exc(AuthApiError("Invalid login credentials", 400, "invalid_credentials"))
    assert esig.reauthenticate("a@b.c", "bad") is False
    with_exc(None)
    assert esig.reauthenticate("a@b.c", "good") is True
    for exc in (AuthApiError("rate limit", 429, "over_request_rate_limit"), AuthApiError("boom", 500, None),
                ConnectionError("down")):
        with_exc(exc)
        with pytest.raises(esig.ReauthUnavailableError):
            esig.reauthenticate("a@b.c", "x")


def _wrong(monkeypatch, calls):
    monkeypatch.setattr(esig, "reauthenticate", lambda e, p: calls.append(1) or p == "right")


def test_sixth_wrong_attempt_is_throttled_without_calling_supabase(db_path, monkeypatch):
    calls = []
    _wrong(monkeypatch, calls)
    for _ in range(esig.MAX_FAILED_ATTEMPTS):
        with pytest.raises(esig.ReauthenticationError) as e:
            esig.require_esignature(_tenant(), "wrong", "Approved", "r")
        assert not isinstance(e.value, esig.ESignatureThrottledError)
    with pytest.raises(esig.ESignatureThrottledError):
        esig.require_esignature(_tenant(), "right", "Approved", "r")   # even the right password is refused
    assert len(calls) == esig.MAX_FAILED_ATTEMPTS                       # Supabase not called when throttled


def test_other_users_and_login_are_unaffected_and_success_resets(db_path, monkeypatch):
    calls = []
    _wrong(monkeypatch, calls)
    for _ in range(esig.MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(esig.ReauthenticationError):
            esig.require_esignature(_tenant("u1"), "wrong", "Approved", "r")
    esig.require_esignature(_tenant("u1"), "right", "Approved", "r")    # success resets the count
    for _ in range(esig.MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(esig.ReauthenticationError):
            esig.require_esignature(_tenant("u1"), "wrong", "Approved", "r")
    esig.require_esignature(_tenant("u2"), "right", "Approved", "r")    # another user: never throttled


def test_supabase_outage_is_not_counted_against_the_user(db_path, monkeypatch):
    def down(e, p):
        raise esig.ReauthUnavailableError("down")
    monkeypatch.setattr(esig, "reauthenticate", down)
    for _ in range(esig.MAX_FAILED_ATTEMPTS + 2):
        with pytest.raises(esig.ReauthUnavailableError):
            esig.require_esignature(_tenant(), "p", "Approved", "r")
    assert maindb.get_connection().execute("SELECT COUNT(*) FROM qms_esignature_attempts").fetchone()[0] == 0


def test_throttle_expires_after_the_window(db_path, monkeypatch):
    calls = []
    _wrong(monkeypatch, calls)
    for _ in range(esig.MAX_FAILED_ATTEMPTS):
        with pytest.raises(esig.ReauthenticationError):
            esig.require_esignature(_tenant(), "wrong", "Approved", "r")
    conn = maindb.get_connection()
    with conn:
        conn.execute("UPDATE qms_esignature_attempts SET at = datetime('now', '-16 minutes')")
    conn.close()
    esig.require_esignature(_tenant(), "right", "Approved", "r")


def test_approval_endpoint_maps_throttle_to_429_and_outage_to_503(db_path, monkeypatch):
    monkeypatch.setattr(va.module_access, "has_business_permission", lambda *a, **k: True)
    monkeypatch.setattr(va.config, "VALIDATION_SIGNATORY_DEPARTMENT_ENFORCEMENT", False)
    monkeypatch.setattr(va.audit, "log_failure", lambda *a, **k: None)

    def act():
        return va.perform_action(
            tenant=_tenant(), doc_type="URS", audit_type="urs",
            record={"id": 5, "status": "approved", "revision": "A"},
            data={"action": "Make Effective", "password": "wrong", "reason": "r"}, performed_by="u1",
            role="reviewer_qa", validate_transition=lambda c, r: None, apply_update=lambda u: None,
            add_trail=lambda *a: {}, creator={})

    monkeypatch.setattr(esig, "reauthenticate", lambda e, p: False)
    for _ in range(esig.MAX_FAILED_ATTEMPTS):
        with pytest.raises(va.ApprovalError) as e:
            act()
        assert e.value.http_status == 401
    with pytest.raises(va.ApprovalError) as e:
        act()
    assert e.value.http_status == 429

    def down(e, p):
        raise esig.ReauthUnavailableError("down")
    monkeypatch.setattr(esig, "reauthenticate", down)
    monkeypatch.setattr(esig.qmsdb, "recent_esignature_failures", lambda *a: 0)
    with pytest.raises(va.ApprovalError) as e:
        act()
    assert e.value.http_status == 503
