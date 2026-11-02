# -*- coding: utf-8 -*-
"""坐标转换与几何的离线单元测试（标准库 unittest，零第三方依赖）。

运行：python -m unittest discover -s tests -v
或：  python tests/test_coords.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.core.geometry import (geometry_area_km2, geometry_center,
                                   haversine_km, multipolygon_geometry,
                                   polygon_geometry)
from get_aoi.utils.coords import (bd09mc_to_wgs84, convert_point,
                                  gcj02_to_wgs84, wgs84_to_gcj02)


class TestCoords(unittest.TestCase):
    def test_gcj02_wgs84_roundtrip(self):
        lng, lat = 121.502250, 31.282587
        glng, glat = wgs84_to_gcj02(lng, lat)
        back = gcj02_to_wgs84(glng, glat)
        # gcj02_to_wgs84 为近似逆变换，往返存在米级误差，允许 < 1e-4 度
        self.assertLess(abs(back[0] - lng), 1e-4)
        self.assertLess(abs(back[1] - lat), 1e-4)

    def test_gcj02_offset_direction(self):
        # 火星坐标纠偏后应回到原位（偏移非零但可逆）
        lng, lat = 121.502250, 31.282587
        w = gcj02_to_wgs84(lng, lat)
        self.assertNotAlmostEqual(w[0], lng, places=7)

    def test_bd09mc_to_wgs84_tongji(self):
        # 实测：同济大学四平路校区 bbox 两角点（qt=ext content.geo）
        sw = bd09mc_to_wgs84(13525768.205948, 3647239.065793)
        ne = bd09mc_to_wgs84(13527157.524836, 3648454.369920)
        self.assertAlmostEqual(sw[0], 121.491695, places=4)
        self.assertAlmostEqual(sw[1], 31.279915, places=4)
        self.assertAlmostEqual(ne[0], 121.504231, places=4)
        self.assertAlmostEqual(ne[1], 31.289296, places=4)

    def test_convert_point(self):
        p = convert_point(121.5, 31.28, "gcj02", "wgs84")
        self.assertEqual(len(p), 2)
        # 补逆变换后，wgs84/gcj02/bd09/bd09mc 两两均可互转
        p2 = convert_point(121.5, 31.28, "gcj02", "bd09mc")
        self.assertEqual(len(p2), 2)
        self.assertGreater(abs(p2[0]), 1e6)  # 墨卡托 x 为百万级米制坐标

    def test_bd09_mc_roundtrip(self):
        # bd09 ↔ bd09mc 应精确往返（< 1e-3 米）
        bd = (121.502721, 31.283568)
        mc = convert_point(*bd, "bd09", "bd09mc")
        back = convert_point(*mc, "bd09mc", "bd09")
        self.assertLess(abs(back[0] - bd[0]), 1e-5)
        self.assertLess(abs(back[1] - bd[1]), 1e-5)


class TestGeometry(unittest.TestCase):
    def test_polygon_area_center(self):
        # 约 0.01°×0.01° 的方块（上海附近），面积 ~1 km² 量级
        ring = [(121.0, 31.0), (121.01, 31.0), (121.01, 31.01), (121.0, 31.01)]
        geom = polygon_geometry([ring])
        self.assertEqual(geom["type"], "Polygon")
        # 首尾闭合
        self.assertEqual(geom["coordinates"][0][0], geom["coordinates"][0][-1])
        area = geometry_area_km2(geom)
        self.assertGreater(area, 0.5)
        self.assertLess(area, 2.0)
        center = geometry_center(geom)
        self.assertAlmostEqual(center[0], 121.005, places=5)

    def test_haversine(self):
        # 同一纬度 0.01° 经度差，上海约 0.95 km
        d = haversine_km(121.0, 31.0, 121.01, 31.0)
        self.assertGreater(d, 0.5)
        self.assertLess(d, 1.5)

    def test_multipolygon_center_uses_largest_part(self):
        # P2-9：多校区/飞地合并成 MultiPolygon 时，中心应取面积最大部件，
        # 而非所有顶点均值（后者会被远处小部件拉偏到空地）。
        big = [(121.0, 31.0), (121.02, 31.0), (121.02, 31.02), (121.0, 31.02)]
        small = [(121.5, 31.5), (121.501, 31.5), (121.501, 31.501), (121.5, 31.501)]
        geom = multipolygon_geometry([[big], [small]])
        self.assertEqual(geom["type"], "MultiPolygon")
        center = geometry_center(geom)
        self.assertAlmostEqual(center[0], 121.01, places=3)
        self.assertAlmostEqual(center[1], 31.01, places=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
