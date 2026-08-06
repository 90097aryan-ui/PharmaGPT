"""
tests/test_esignature_service.py — Regression coverage for
pharmagpt/services/esignature_service.py (21 CFR Part 11 / EU GMP Annex 11).

Uses the same db_path/client fixtures as the rest of the SQLite-backed QMS
test suite (tests/conftest.py) for the storage-layer tests, and mocks
esignature_service.reauthenticate directly for tests that don't need a real
Supabase project — the same boundary tests/test_*.py already treat as an
external dependency elsewhere in this suite.
"""

from unittest.mock import patch

import pytest

from pharmagpt import qms_database as qmsdb
from pharmagpt.auth.context import TenantContext
from pharmagpt.services import esignature_service as esig

TENANT = TenantContext(
    user_id="user-1", email="signer@example.com", display_name="Jane Signer",
    role="company_admin", company_id="company-a",
)

REAUTH_PATH = "pharmagpt.services.esignature_service.reauthenticate"


def test_validate_meaning_and_reason_rejects_unknown_meaning():
    with pytest.raises(esig.ESignatureError):
        esig.validate_meaning_and_reason("Signed Off", "because")


def test_validate_meaning_and_reason_rejects_missing_reason():
    with pytest.raises(esig.ESignatureError):
        esig.validate_meaning_and_reason("Approved", "   ")


def test_validate_meaning_and_reason_accepts_every_fixed_meaning():
    for meaning in esig.SIGNATURE_MEANINGS:
        esig.validate_meaning_and_reason(meaning, "valid reason")  # must not raise


def test_require_esignature_raises_before_reauth_if_meaning_invalid():
    with patch(REAUTH_PATH) as mock_reauth:
        with pytest.raises(esig.ESignatureError):
            esig.require_esignature(TENANT, "correct-password", "Not A Real Meaning", "reason")
    mock_reauth.assert_not_called()  # fail fast — never even attempts to verify the password


def test_require_esignature_raises_reauthentication_error_on_wrong_password():
    with patch(REAUTH_PATH, return_value=False):
        with pytest.raises(esig.ReauthenticationError):
            esig.require_esignature(TENANT, "wrong-password", "Approved", "reason")


def test_require_esignature_passes_with_correct_password():
    with patch(REAUTH_PATH, return_value=True):
        esig.require_esignature(TENANT, "correct-password", "Approved", "reason")  # must not raise


def test_compute_signature_hash_is_deterministic_and_order_independent():
    payload_a = {"a": 1, "b": 2}
    payload_b = {"b": 2, "a": 1}
    assert esig.compute_signature_hash(payload_a) == esig.compute_signature_hash(payload_b)


def test_compute_signature_hash_changes_if_any_field_changes():
    base = {"record_id": 1, "meaning": "Approved"}
    changed = {"record_id": 1, "meaning": "Rejected"}
    assert esig.compute_signature_hash(base) != esig.compute_signature_hash(changed)


def test_record_signature_writes_immutable_row_and_audit_entry(client, db_path):
    """Uses the `client`/`db_path` fixtures only to get an initialized
    SQLite schema and a request context for audit.log()'s IP/session
    capture — no HTTP call is made in this test."""
    with client.application.test_request_context("/"):
        row = esig.record_signature(
            tenant=TENANT, meaning="Approved", reason="Looks correct",
            record_type="document", record_id=42, version_number="1.0",
            old_status="Pending Approval", new_status="Effective",
        )

    assert row["meaning"] == "Approved"
    assert row["reason"] == "Looks correct"
    assert row["user_id"] == "user-1"
    assert row["full_name"] == "Jane Signer"
    assert row["role"] == "company_admin"
    assert row["old_status"] == "Pending Approval"
    assert row["new_status"] == "Effective"
    assert row["signature_hash"]
    assert esig.verify_signature_integrity(row) is True

    trail = qmsdb.get_esignatures("document", 42)
    assert len(trail) == 1
    assert trail[0]["id"] == row["id"]

    audit_trail = qmsdb.get_audit_trail("document", 42)
    assert any(a["action"] == "E-Signature: Approved" for a in audit_trail)


def test_no_update_or_delete_function_exists_for_esignatures():
    """Immutability is enforced by omission: there must be no function in
    qms_database.py that can update or delete a qms_esignatures row."""
    assert not hasattr(qmsdb, "update_esignature")
    assert not hasattr(qmsdb, "delete_esignature")


def test_verify_signature_integrity_detects_tampering(client, db_path):
    with client.application.test_request_context("/"):
        row = esig.record_signature(
            tenant=TENANT, meaning="Approved", reason="Looks correct",
            record_type="document", record_id=7,
        )
    tampered = dict(row)
    tampered["new_status"] = "Effective (tampered)"
    assert esig.verify_signature_integrity(tampered) is False
