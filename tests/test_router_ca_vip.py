import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "home-ca-vip.py"
SPEC = importlib.util.spec_from_file_location("home_ca_vip", MODULE_PATH)
vip_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vip_module)


class HomeCaVipTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "schema_version": 1,
            "ca_id": "HOME-CA-001",
            "certificate": {"sha256_fingerprint": "aabbcc"},
            "trust": {"trust_status": "PENDING"},
            "management": {"last_inspected": "2026-11-08T10:00:00Z"}
        }

    def test_same_metadata_and_bucket_produce_same_vip(self):
        first = datetime(2026, 11, 8, 20, 50, 0, tzinfo=timezone.utc)
        second = datetime(2026, 11, 8, 20, 54, 59, tzinfo=timezone.utc)
        a = vip_module.derive(self.metadata, first)
        b = vip_module.derive(self.metadata, second)
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[1], b[1])

    def test_new_bucket_changes_vip(self):
        first = datetime(2026, 11, 8, 20, 50, 0, tzinfo=timezone.utc)
        second = datetime(2026, 11, 8, 20, 55, 0, tzinfo=timezone.utc)
        self.assertNotEqual(
            vip_module.derive(self.metadata, first)[1],
            vip_module.derive(self.metadata, second)[1]
        )

    def test_volatile_inspection_timestamp_is_excluded(self):
        before = vip_module.derive(self.metadata, datetime(2026, 11, 8, 20, 50, tzinfo=timezone.utc))
        changed = dict(self.metadata)
        changed["management"] = {"last_inspected": "2026-11-08T10:10:00Z"}
        after = vip_module.derive(changed, datetime(2026, 11, 8, 20, 50, tzinfo=timezone.utc))
        self.assertEqual(before[0], after[0])

    def test_vip_is_ipv6_ula(self):
        digest, address, *_ = vip_module.derive(
            self.metadata, datetime(2026, 11, 8, 20, 50, tzinfo=timezone.utc)
        )
        self.assertEqual(len(digest), 128)
        self.assertEqual(address.split(":")[0][:2], "fd")
        self.assertTrue(address.startswith("fd"))
        self.assertEqual(len(address.split(":")), 8)

    def test_rejects_wrong_schema(self):
        with self.assertRaises(ValueError):
            vip_module.derive({"schema_version": 2}, datetime.now(timezone.utc))

    def test_cli_writes_digest_and_expiry_record(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata_path = root / "home-ca-metadata.json"
            digest_path = root / "crypto" / "sha-512" / "r-ca-vip.key"
            record_path = root / "home-ca-vip.json"
            metadata_path.write_text(json.dumps(self.metadata), encoding="utf-8")
            result = subprocess.run(
                [
                    "python3", str(MODULE_PATH),
                    "--metadata", str(metadata_path),
                    "--digest-output", str(digest_path),
                    "--record-output", str(record_path),
                    "--now", "2026-11-08T20:50:00Z"
                ],
                capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(digest_path.read_text().strip()), 128)
            record = json.loads(record_path.read_text())
            self.assertEqual(record["expires_at"], "2026-11-08T20:55:00Z")
            self.assertFalse(record["authentication_established"])
            self.assertEqual((digest_path.stat().st_mode & 0o777), 0o600)


if __name__ == "__main__":
    unittest.main()
