# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""File policy is rechecked beside the final snapshot comparison."""

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import drift
import resolve


class ReplacePolicyRecheck(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)
        self.path = self.dir / "s.yaml"
        self.path.write_bytes(b"original\n")
        os.chmod(self.path, 0o644)

    def replace_with(self, change):
        real_fsync = os.fsync

        def fsync(fd):
            real_fsync(fd)
            change()

        with mock.patch.object(drift.os, "fsync", side_effect=fsync), \
                mock.patch.object(drift.os, "replace") as replace:
            with self.assertRaises(resolve.ResolutionError):
                drift.replace_snapshot(self.path, b"original\n", b"rewritten\n")
        replace.assert_not_called()
        self.assertEqual(sorted(p.name for p in self.dir.iterdir() if p.name.startswith("spec-rewrite-")), [])

    def test_hard_link_added_during_staging(self):
        self.replace_with(lambda: os.link(self.path, self.dir / "link.yaml"))

    def test_made_read_only_during_staging(self):
        self.replace_with(lambda: os.chmod(self.path, 0o444))

    def test_setgid_added_during_staging(self):
        self.replace_with(lambda: os.chmod(self.path, 0o2644))

    def test_mode_changed_during_staging(self):
        self.replace_with(lambda: os.chmod(self.path, 0o600))

    def test_replaced_by_symlink_during_staging(self):
        def swap():
            target = self.dir / "target.yaml"
            target.write_bytes(b"original\n")
            self.path.unlink()
            self.path.symlink_to(target)

        self.replace_with(swap)

    def test_unchanged_policy_replaces(self):
        drift.replace_snapshot(self.path, b"original\n", b"rewritten\n")
        self.assertEqual(self.path.read_bytes(), b"rewritten\n")
        self.assertEqual(os.stat(self.path).st_mode & 0o7777, 0o644)


if __name__ == "__main__":
    unittest.main()
