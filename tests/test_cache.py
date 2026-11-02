# -*- coding: utf-8 -*-
"""边界缓存（BoundaryCache）离线测试。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.core.cache import BoundaryCache
from get_aoi.core.geometry import polygon_geometry
from get_aoi.models import AOIRecord, Status


def _record(poi_id, name="测试"):
    geom = polygon_geometry([[
        (121.0, 31.0), (121.01, 31.0), (121.01, 31.01), (121.0, 31.01)]])
    return AOIRecord(poi_id=poi_id, name=name, provider="amap",
                     geometry=geom, center=(121.005, 31.005), area_km2=1.0,
                     status=Status.MATCHED, extra={"tag": ["a", "b"]})


class TestBoundaryCache(unittest.TestCase):
    def test_put_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            cache = BoundaryCache(Path(d) / "boundary.db")
            cache.put("amap", _record("B001"))
            got = cache.get("amap", "B001")
            self.assertIsNotNone(got)
            self.assertEqual(got.poi_id, "B001")
            self.assertEqual(got.center, (121.005, 31.005))
            self.assertEqual(got.extra["tag"], ["a", "b"])
            self.assertEqual(got.status, Status.MATCHED)
            self.assertEqual(cache.size(), 1)
            cache.close()

    def test_provider_isolation(self):
        # 高德 B 开头 id 与百度十六进制 uid 即便相同也不应互相命中
        with tempfile.TemporaryDirectory() as d:
            cache = BoundaryCache(Path(d) / "b.db")
            cache.put("amap", _record("SAME"))
            self.assertIsNone(cache.get("baidu", "SAME"))
            cache.close()

    def test_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            cache = BoundaryCache(Path(d) / "b.db")
            self.assertIsNone(cache.get("amap", "nope"))
            cache.close()

    def test_persists_across_reopen(self):
        # 跨次运行复用：关闭后重开仍能命中
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "b.db"
            cache = BoundaryCache(path)
            cache.put("amap", _record("B001"))
            cache.close()
            cache2 = BoundaryCache(path)
            self.assertIsNotNone(cache2.get("amap", "B001"))
            cache2.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
