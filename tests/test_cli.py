# -*- coding: utf-8 -*-
"""CLI 参数解析的离线测试。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.cli import build_parser


class TestCli(unittest.TestCase):
    def test_version_flag(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--version"])

    def test_no_secret_arguments(self):
        # 密钥只走配置文件 / key_file / 环境变量，命令行不接受 --key/--ak
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["run", "-c", "x.yaml", "--key", "secret"])
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["run", "-c", "x.yaml", "--ak", "secret"])

    def test_run_requires_config(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["run"])

    def test_resume_takes_directory(self):
        args = build_parser().parse_args(
            ["run", "-c", "x.yaml", "--resume", "runs/xxx"])
        self.assertEqual(args.resume, "runs/xxx")

    def test_convert_has_no_config(self):
        args = build_parser().parse_args(
            ["convert", "-i", "in.csv", "--crs", "gcj02"])
        self.assertEqual(args.crs, "gcj02")

    def test_convert_to_bd09mc(self):
        args = build_parser().parse_args(
            ["convert", "-i", "in.csv", "--crs", "gcj02", "--to", "bd09mc"])
        self.assertEqual(args.to, "bd09mc")

    def test_run_concurrency_override(self):
        args = build_parser().parse_args(
            ["run", "-c", "x.yaml", "--concurrency", "4"])
        self.assertEqual(args.concurrency, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
