# -*- coding: utf-8 -*-
"""HTTP 风控识别与高德动态头读取的离线测试。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.cli import _amap_boundary_headers
from get_aoi.config import Config
from get_aoi.utils.http import AntiBotError, HttpClient


class FakeResponse:
    def __init__(self, text):
        self.text = text


class TestHttp(unittest.TestCase):
    def test_html_antibot_page(self):
        resp = FakeResponse('<!DOCTYPE html><html><script src="AWSC/CAPTCHA"></script>punish</html>')
        with self.assertRaises(AntiBotError):
            HttpClient._check_antibot(resp)

    def test_json_antibot_response(self):
        resp = FakeResponse('{"ret":["FAIL_SYS_USER_VALIDATE"]}')
        data = {"ret": ["FAIL_SYS_USER_VALIDATE", "RGV587_ERROR"]}
        with self.assertRaises(AntiBotError):
            HttpClient._check_antibot(resp, data)

    def test_normal_json_response(self):
        HttpClient._check_antibot(FakeResponse('{"status":"1"}'), {"status": "1"})

    def test_amap_dynamic_headers_from_config(self):
        cfg = Config(provider="amap", input="names.csv", headers={
            "amap_bx_ua": "bx-value",
            "amap_bx_umidtoken": "umid-value",
            "amap_bx_et": "et-value",
            "amap_x_csrf_token": "csrf-value",
            "amap_x_adiu": "adiu-value",
            "amap_referer": "https://ditu.amap.com/detail",
        })
        headers = _amap_boundary_headers(cfg)
        self.assertEqual(headers["Bx-Ua"], "bx-value")
        self.assertEqual(headers["Bx-Umidtoken"], "umid-value")
        self.assertEqual(headers["Bx_et"], "et-value")
        self.assertEqual(headers["X-Csrf-Token"], "csrf-value")
        self.assertEqual(headers["X-Adiu"], "adiu-value")
        self.assertEqual(headers["Referer"], "https://ditu.amap.com/detail")

    def test_amap_dynamic_headers_empty_when_unset(self):
        cfg = Config(provider="amap", input="names.csv", headers={})
        self.assertEqual(_amap_boundary_headers(cfg), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
