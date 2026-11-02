# -*- coding: utf-8 -*-
"""RunStore 目录管理离线测试。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.store import RunStore, sanitize_tag


class TestSanitizeTag(unittest.TestCase):
    def test_sanitize_plain(self):
        self.assertEqual(sanitize_tag("names_amap"), "names_amap")

    def test_sanitize_chinese(self):
        self.assertEqual(sanitize_tag("高校 名单"), "高校_名单")

    def test_sanitize_special(self):
        self.assertEqual(sanitize_tag("a/b\\c:d"), "a_b_c_d")


class TestRunStore(unittest.TestCase):
    def test_create_makes_run_dir(self):
        with tempfile.TemporaryDirectory() as d:
            store = RunStore.create(d, "names_amap", {"provider": "amap"})
            self.assertTrue(store.run_dir.is_dir())
            self.assertTrue(store.outputs_dir.is_dir())
            self.assertTrue(store.snapshot_path.exists())
            self.assertIn("names_amap", store.run_dir.name)

    def test_create_same_tag_gets_suffix(self):
        with tempfile.TemporaryDirectory() as d:
            first = RunStore.create(d, "names_amap", {})
            second = RunStore.create(d, "names_amap", {})
            self.assertNotEqual(first.run_dir, second.run_dir)

    def test_resume_requires_state(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                RunStore.resume(Path(d) / "nonexistent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
