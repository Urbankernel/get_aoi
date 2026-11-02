# -*- coding: utf-8 -*-
"""CSV 报告导出（summary.csv / aoi_attributes.csv）离线测试。"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.core.geometry import polygon_geometry
from get_aoi.exporters.csv import export_attributes_csv, export_summary_csv
from get_aoi.models import AOIRecord, Status


def _record(poi_id, name):
    geom = polygon_geometry([[
        (121.0, 31.0), (121.01, 31.0), (121.01, 31.01), (121.0, 31.01)]])
    return AOIRecord(poi_id=poi_id, name=name, provider="amap",
                     geometry=geom, center=(121.005, 31.005), area_km2=1.234,
                     status=Status.MATCHED, extra={"tag": ["a", "b"],
                                                   "adcode": "310110"})


class TestCsvReport(unittest.TestCase):
    def test_summary_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "summary.csv"
            n = export_summary_csv(
                [("同济大学", "Matched", 2), ("不存在", "No Candidate", 0)], p)
            self.assertEqual(n, 2)
            with open(p, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["name"], "同济大学")
            self.assertEqual(rows[0]["matched_count"], "2")
            self.assertEqual(rows[1]["status"], "No Candidate")

    def test_attributes_csv_flattens(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "attrs.csv"
            rec = _record("B001", "同济大学")
            n = export_attributes_csv([rec], p)
            self.assertEqual(n, 1)
            with open(p, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["poi_id"], "B001")
            self.assertEqual(rows[0]["name"], "同济大学")
            self.assertAlmostEqual(float(rows[0]["center_lng"]), 121.005, places=6)
            # 数组字段 JSON 字符串化，可还原
            self.assertEqual(json.loads(rows[0]["tag"]), ["a", "b"])
            self.assertEqual(rows[0]["adcode"], "310110")

    def test_attributes_union_fields(self):
        # 不同记录 extra 字段不同时，列取并集
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "attrs.csv"
            r1 = _record("B001", "甲")
            r2 = _record("B002", "乙")
            r2.extra = {"cityname": "上海市"}
            n = export_attributes_csv([r1, r2], p)
            self.assertEqual(n, 2)
            with open(p, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)
            self.assertIn("tag", fieldnames)
            self.assertIn("cityname", fieldnames)
            self.assertEqual(rows[0]["cityname"], "")
            self.assertEqual(rows[1]["cityname"], "上海市")


if __name__ == "__main__":
    unittest.main(verbosity=2)
