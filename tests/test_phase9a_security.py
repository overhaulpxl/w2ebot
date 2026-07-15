from datetime import timedelta
import unittest

from economy.dashboard_security import (
    DashboardSecurityError, InternalEnvelope, canonical_json, payload_hash,
    verify_envelope_signature, utc_now,
)
from tests.phase9a_test_utils import INTERNAL_KEY


class Phase9ASecurityTests(unittest.TestCase):
    def envelope(self, payload):
        now = int(utc_now().timestamp())
        return InternalEnvelope(
            key_id="internal-v1", method="POST", canonical_route="/internal/phase9a/health",
            guild_id="887968847842402355", actor_id="123456789012345678",
            permission_class="DASHBOARD_VIEW", request_id="request-1", issued_at=now,
            expires_at=now + 30, nonce="nonce-1", payload_hash=payload_hash(payload),
            session_token_hash="a" * 64, session_version=0,
        )

    def test_canonical_json_rejects_floats(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')
        self.assertEqual(canonical_json({"pesan": "aman"}), '{"pesan":"aman"}')
        self.assertEqual(canonical_json({"pesan": "é"}), '{"pesan":"é"}')
        with self.assertRaises(DashboardSecurityError):
            canonical_json({"value": 1.5})

    def test_signature_tamper_route_and_expiry(self):
        payload = {}
        envelope = self.envelope(payload)
        headers = envelope.as_headers(INTERNAL_KEY)
        verify_envelope_signature(envelope, headers["X-W2E-Signature"], INTERNAL_KEY,
                                  method="POST", route=envelope.canonical_route, payload=payload)
        with self.assertRaises(DashboardSecurityError):
            verify_envelope_signature(envelope, headers["X-W2E-Signature"], INTERNAL_KEY,
                                      method="POST", route="/wrong", payload=payload)
        with self.assertRaises(DashboardSecurityError):
            verify_envelope_signature(envelope, headers["X-W2E-Signature"], INTERNAL_KEY,
                                      method="POST", route=envelope.canonical_route, payload=payload,
                                      now=utc_now() + timedelta(minutes=2))
