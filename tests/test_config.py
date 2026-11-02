# -*- coding: utf-8 -*-
"""YAML 配置加载与校验的离线测试。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.config import ConfigError, load_config


class TestConfig(unittest.TestCase):
    def _make_input(self, d):
        p = Path(d) / "names.csv"
        p.write_text("name,city,lng,lat\n同济大学,上海,,\n", encoding="utf-8")
        return p

    def _write_cfg(self, d, body):
        p = Path(d) / "cfg.yaml"
        p.write_text(body, encoding="utf-8")
        return str(p)

    def test_keys_from_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'key-a'\n")
            cfg = load_config(cfg_path)
            self.assertEqual(cfg.amap_key, "key-a")

    def test_keys_from_env(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(d, f"provider: amap\ninput: {inp}\n")
            with patch.dict("os.environ", {"AMAP_KEY": "env-key"}, clear=True):
                cfg = load_config(cfg_path)
            self.assertEqual(cfg.amap_key, "env-key")

    def test_keys_from_key_file(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            kf = Path(d) / "keys.txt"
            kf.write_text("amap=file-key\n", encoding="utf-8")
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkey_file: {kf}\n")
            with patch.dict("os.environ", {}, clear=True):
                cfg = load_config(cfg_path)
            self.assertEqual(cfg.amap_key, "file-key")

    def test_yaml_priority_over_env(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'yaml-key'\n")
            with patch.dict("os.environ", {"AMAP_KEY": "env-key"}, clear=True):
                cfg = load_config(cfg_path)
            self.assertEqual(cfg.amap_key, "yaml-key")

    def test_missing_key_raises(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(d, f"provider: amap\ninput: {inp}\n")
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ConfigError):
                    load_config(cfg_path)

    def test_placeholder_key_filtered(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: '你的key'\n")
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ConfigError):
                    load_config(cfg_path)

    def test_cli_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\nwant: all\n")
            cfg = load_config(cfg_path, overrides={"want": "main", "city": "上海"})
            self.assertEqual(cfg.want, "main")
            self.assertEqual(cfg.city, "上海")

    def test_invalid_want_raises(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\nwant: xxx\n")
            with self.assertRaises(ConfigError):
                load_config(cfg_path)

    def test_invalid_format_raises(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\n"
                   f"outputs:\n  format: csv\n")
            with self.assertRaises(ConfigError):
                load_config(cfg_path)

    def test_missing_input_raises(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = self._write_cfg(
                d, "provider: amap\ninput: not_exist.csv\nkeys:\n  amap: 'k'\n")
            with self.assertRaises(ConfigError):
                load_config(cfg_path)

    def test_concurrency_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\n"
                   f"request:\n  concurrency: 4\n")
            cfg = load_config(cfg_path)
            self.assertEqual(cfg.request.concurrency, 4)

    def test_concurrency_default_one(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\n")
            cfg = load_config(cfg_path)
            self.assertEqual(cfg.request.concurrency, 1)

    def test_concurrency_invalid_raises(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\n"
                   f"request:\n  concurrency: 0\n")
            with self.assertRaises(ConfigError):
                load_config(cfg_path)

    def test_cache_and_report_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\n")
            cfg = load_config(cfg_path)
            self.assertTrue(cfg.cache.enabled)
            self.assertEqual(cfg.cache.dir, "")
            self.assertTrue(cfg.outputs.report)

    def test_cache_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\n"
                   f"cache:\n  enabled: false\n")
            cfg = load_config(cfg_path)
            self.assertFalse(cfg.cache.enabled)

    def test_concurrency_cli_override(self):
        with tempfile.TemporaryDirectory() as d:
            inp = self._make_input(d)
            cfg_path = self._write_cfg(
                d, f"provider: amap\ninput: {inp}\nkeys:\n  amap: 'k'\n")
            cfg = load_config(cfg_path, overrides={"concurrency": 6})
            self.assertEqual(cfg.request.concurrency, 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
