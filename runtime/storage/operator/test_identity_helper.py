"""Hermetic tests for the operator-only identity helper (M8). No Docker, no network, no DB."""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import identity_helper as ih


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class InitTokenTest(unittest.TestCase):
    def test_writes_valid_token_0600(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "operator.token")
            self.assertEqual(ih.main(["init-token", "--out", out, "--id", "operator"]), 0)
            # exact shape cmd/factory reads: {"id","secret"}
            tok = _load(out)
            self.assertEqual(set(tok), {"id", "secret"})
            self.assertEqual(tok["id"], "operator")
            self.assertGreaterEqual(len(tok["secret"]), 32)
            # 0600 and no group/other bits
            mode = stat.S_IMODE(os.stat(out).st_mode)
            self.assertEqual(mode & 0o077, 0, f"token must not be group/other readable (mode {mode:o})")

    def test_secret_is_unique_per_invocation(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a"), os.path.join(d, "b")
            ih.main(["init-token", "--out", a])
            ih.main(["init-token", "--out", b])
            sa = _load(a)["secret"]
            sb = _load(b)["secret"]
            self.assertNotEqual(sa, sb)

    def test_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "operator.token")
            ih.main(["init-token", "--out", out])
            with self.assertRaises(SystemExit):
                ih.main(["init-token", "--out", out])
            # --force replaces
            self.assertEqual(ih.main(["init-token", "--out", out, "--force"]), 0)


class EnrollProjectTest(unittest.TestCase):
    def test_writes_request_no_secret(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "enroll.json")
            u = "123e4567-e89b-12d3-a456-426614174000"
            self.assertEqual(ih.main(["enroll-project", "--uuid", u, "--label", "A", "--out", out]), 0)
            rec = _load(out)
            self.assertEqual(rec["uuid"], u)
            self.assertEqual(rec["label"], "A")
            self.assertNotIn("secret", rec)
            self.assertEqual(rec["kind"], "project-enrollment-request")

    def test_rejects_bad_uuid(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "enroll.json")
            with self.assertRaises(SystemExit):
                ih.main(["enroll-project", "--uuid", "not-a-uuid", "--label", "A", "--out", out])
            self.assertFalse(os.path.exists(out))

    def test_rejects_empty_label(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "enroll.json")
            u = "123e4567-e89b-12d3-a456-426614174000"
            with self.assertRaises(SystemExit):
                ih.main(["enroll-project", "--uuid", u, "--label", "   ", "--out", out])


if __name__ == "__main__":
    unittest.main()
