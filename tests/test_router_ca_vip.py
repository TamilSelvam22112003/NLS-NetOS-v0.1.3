import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "derive-router-ca-vip.py"
SPEC = importlib.util.spec_from_file_location("derive_router_ca_vip", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RouterCaVipTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "schema_version": 1,
            "ca_id": "HOME-CA-001",
            "certificate": {"sha256_fingerprint": "AA:BB:CC"},
            "management": {"last_inspected": "2026-11-08T20:50:00Z"},
        }

    def test_same_metadata_and_bucket_produce_same_vip(self):
        a = MODULE.derive_vip(self.metadata, datetime(2026, 11, 8, 20, 50, 0, tzinfo=timezone.utc))
        b = MODULE.derive_vip(self.metadata, datetime(2026, 11, 8, 20, 54, 59, tzinfo=timezone.utc))
        self.assertEqual(a["vip_ipv6_address"], b["vip_ipv6_address"])
        self.assertEqual(a["sha512_digest_hex"], b["sha512_digest_hex"])

    def test_new_bucket_changes_vip(self):
        a = MODULE.derive_vip(self.metadata, datetime(2026, 11, 8, 20, 50, 0, tzinfo=timezone.utc))
        b = MODULE.derive_vip(self.metadata, datetime(2026, 11, 8, 20, 55, 0, tzinfo=timezone.utc))
        self.assertNotEqual(a["vip_ipv6_address"], b["vip_ipv6_address"])

    def test_metadata_change_changes_vip(self):
        a = MODULE.derive_vip(self.metadata, datetime(2026, 11, 8, 20, 50, 0, tzinfo=timezone.utc))
        changed = {**self.metadata, "ca_id": "HOME-CA-002"}
        b = MODULE.derive_vip(changed, datetime(2026, 11, 8, 20, 50, 0, tzinfo=timezone.utc))
        self.assertNotEqual(a["vip_ipv6_address"], b["vip_ipv6_address"])

    def test_volatile_inspection_timestamp_does_not_change_vip(self):
        a = MODULE.derive_vip(self.metadata, datetime(2026, 11, 8, 20, 50, 0, tzinfo=timezone.utc))
        changed = {**self.metadata, "management": {"last_inspected": "2026-11-08T20:52:00Z"}}
        b = MODULE.derive_vip(changed, datetime(2026, 11, 8, 20, 50, 30, tzinfo=timezone.utc))
        self.assertEqual(a["vip_ipv6_address"], b["vip_ipv6_address"])

    def test_address_is_ula_and_digest_is_sha512(self):
        result = MODULE.derive_vip(self.metadata, datetime(2026, 11, 8, 20, 50, 0, tzinfo=timezone.utc))
        self.assertTrue(result["vip_ipv6_address"].startswith("fd"))
        self.assertEqual(len(result["sha512_digest_hex"]), 128)
        self.assertEqual(result["expires_at_utc"], "2026-11-08T20:55:00Z")


if __name__ == "__main__":
    unittest.main()
