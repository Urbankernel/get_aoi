# -*- coding: utf-8 -*-
"""续跑回填（_restore_completed）离线测试。

验证：断点里已完成项通过 poi_id 从 BoundaryCache 回填完整几何；
无面结论直接恢复；缓存缺失 / 未启用时清除完成标记交由重抓，不静默丢数据。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.cli import _restore_completed
from get_aoi.core.cache import BoundaryCache
from get_aoi.core.geometry import polygon_geometry
from get_aoi.core.state import StateStore
from get_aoi.models import AOIRecord, Status


def _record(poi_id, name="同济大学"):
    geom = polygon_geometry([[
        (121.0, 31.0), (121.01, 31.0), (121.01, 31.01), (121.0, 31.01)]])
    return AOIRecord(poi_id=poi_id, name=name, provider="amap",
                     geometry=geom, center=(121.005, 31.005), area_km2=1.0,
                     status=Status.MATCHED)


def _entry(status, records):
    return {"status": status, "records": records}


class TestResumeRestore(unittest.TestCase):
    def test_hit_restores_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            cache = BoundaryCache(Path(d) / "b.db")
            rec = _record("B001")
            cache.put("amap", rec)
            state = StateStore(Path(d) / "state.json")
            state.data = {"amap|同济大学": _entry(
                "Matched", [{"poi_id": "B001", "name": "同济大学",
                             "area_km2": 1.0}])}
            all_records, summary = [], []
            _restore_completed(state, "amap", cache, all_records, summary)
            self.assertEqual(len(all_records), 1)
            self.assertEqual(all_records[0].poi_id, "B001")
            self.assertEqual(all_records[0].geometry, rec.geometry)
            self.assertEqual(summary, [("同济大学", "Matched", 1)])
            self.assertIn("amap|同济大学", state.data)  # 命中不重抓
            cache.close()

    def test_no_candidate_restored_without_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            cache = BoundaryCache(Path(d) / "b.db")
            state = StateStore(Path(d) / "state.json")
            state.data = {"amap|不存在": _entry("No Candidate", [])}
            all_records, summary = [], []
            _restore_completed(state, "amap", cache, all_records, summary)
            self.assertEqual(all_records, [])
            self.assertEqual(summary, [("不存在", "No Candidate", 0)])
            self.assertIn("amap|不存在", state.data)  # 无面结论不清除
            cache.close()

    def test_cache_miss_reopens(self):
        with tempfile.TemporaryDirectory() as d:
            cache = BoundaryCache(Path(d) / "b.db")  # 空缓存，必然 miss
            state = StateStore(Path(d) / "state.json")
            state.data = {"amap|某地": _entry(
                "Matched", [{"poi_id": "MISSING", "name": "某地",
                             "area_km2": 1.0}])}
            all_records, summary = [], []
            _restore_completed(state, "amap", cache, all_records, summary)
            self.assertEqual(all_records, [])
            self.assertEqual(summary, [])
            self.assertNotIn("amap|某地", state.data)  # 标记清除，交给重抓
            cache.close()

    def test_no_cache_reopens(self):
        with tempfile.TemporaryDirectory() as d:
            state = StateStore(Path(d) / "state.json")
            state.data = {"amap|某地": _entry(
                "Matched", [{"poi_id": "B001", "name": "某地",
                             "area_km2": 1.0}])}
            all_records, summary = [], []
            _restore_completed(state, "amap", None, all_records, summary)
            self.assertEqual(all_records, [])
            self.assertEqual(summary, [])
            self.assertNotIn("amap|某地", state.data)

    def test_partial_hit_reopens_whole_name(self):
        # 同名多个面，部分缓存命中 → 整体清除标记重抓，避免只恢复一半
        with tempfile.TemporaryDirectory() as d:
            cache = BoundaryCache(Path(d) / "b.db")
            cache.put("amap", _record("B001"))
            state = StateStore(Path(d) / "state.json")
            state.data = {"amap|同济大学": _entry(
                "Matched", [{"poi_id": "B001", "name": "同济大学",
                             "area_km2": 1.0},
                            {"poi_id": "B002", "name": "同济大学",
                             "area_km2": 0.5}])}
            all_records, summary = [], []
            _restore_completed(state, "amap", cache, all_records, summary)
            self.assertEqual(all_records, [])
            self.assertEqual(summary, [])
            self.assertNotIn("amap|同济大学", state.data)
            cache.close()

    def test_other_provider_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            cache = BoundaryCache(Path(d) / "b.db")
            state = StateStore(Path(d) / "state.json")
            state.data = {"baidu|某地": _entry(
                "Matched", [{"poi_id": "X", "name": "某地",
                             "area_km2": 1.0}])}
            all_records, summary = [], []
            _restore_completed(state, "amap", cache, all_records, summary)
            self.assertEqual(all_records, [])
            self.assertEqual(summary, [])
            self.assertIn("baidu|某地", state.data)  # 其他 provider 不动
            cache.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
