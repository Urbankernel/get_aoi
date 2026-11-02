# -*- coding: utf-8 -*-
"""综合排序（match_best）单元测试。

覆盖：area 中位数打分、名称标准化相似度、面积过滤、距离/检索排名打分。
运行：python -m unittest tests.test_matcher -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.core.geometry import polygon_geometry
from get_aoi.core.matcher import MatchWeights, match_best
from get_aoi.core.text import normalize_name
from get_aoi.models import AOIRecord, Candidate


def _record(poi_id, name, area_km2, center=(121.5, 31.2)):
    """构造一个带小方块几何的 AOIRecord，center/area 预填。"""
    d = 0.005
    geom = polygon_geometry([[
        (center[0] - d, center[1] - d),
        (center[0] + d, center[1] - d),
        (center[0] + d, center[1] + d),
        (center[0] - d, center[1] + d),
    ]])
    return AOIRecord(poi_id=poi_id, name=name, provider="test",
                     geometry=geom, center=center, area_km2=area_km2)


class TestNormalizeName(unittest.TestCase):
    """P0-2：名称标准化一致性（filter 与 matcher 共用同一规则）。"""

    def test_normalize_ignores_width_punct_space(self):
        a = normalize_name("同济大学（四平路校区）")
        b = normalize_name("同济大学(四平路校区)")
        c = normalize_name("同济大学 四平路校区")
        d = normalize_name("同济大学-四平路校区")
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertEqual(a, d)

    def test_normalize_casefold(self):
        self.assertEqual(normalize_name("ABC大学"), normalize_name("abc大学"))


class TestMatchBest(unittest.TestCase):
    def test_single_candidate_returns_it(self):
        cand = Candidate(poi_id="1", name="同济大学")
        rec = _record("1", "同济大学", area_km2=1.0)
        best = match_best([(cand, rec)], "同济大学")
        self.assertIsNotNone(best)
        self.assertEqual(best[1].poi_id, "1")

    def test_no_valid_entries_returns_none(self):
        best = match_best([(Candidate(poi_id="1", name="X"), None)], "X")
        self.assertIsNone(best)

    def test_area_filter_excludes_out_of_range(self):
        cand = Candidate(poi_id="1", name="X")
        rec = _record("1", "X", area_km2=50.0)
        best = match_best([(cand, rec)], "X", min_area_km2=0.0, max_area_km2=10.0)
        self.assertIsNone(best)

    def test_area_median_penalizes_outlier(self):
        """P0-1：面积越偏离候选集中位数，得分越低；异常大者落选。

        三个候选其余维度完全相同，面积 1.0 / 1.1 / 100，中位数 1.1。
        旧实现 area_score 恒为 1，三者打平会取第 0 条；新实现应选中位数者。
        """
        c1 = Candidate(poi_id="1", name="测试园区")
        c2 = Candidate(poi_id="2", name="测试园区")
        c3 = Candidate(poi_id="3", name="测试园区")
        entries = [
            (c1, _record("1", "测试园区", area_km2=1.0)),
            (c2, _record("2", "测试园区", area_km2=1.1)),
            (c3, _record("3", "测试园区", area_km2=100.0)),
        ]
        best = match_best(entries, "测试园区")
        self.assertEqual(best[1].poi_id, "2")

    def test_area_median_tie_when_equal(self):
        """面积全相等时 area_score 均为满分，不改变名次（回归保护）。"""
        c1 = Candidate(poi_id="1", name="X")
        c2 = Candidate(poi_id="2", name="X")
        entries = [
            (c1, _record("1", "X", area_km2=1.0)),
            (c2, _record("2", "X", area_km2=1.0)),
        ]
        best = match_best(entries, "X")
        self.assertEqual(best[1].poi_id, "1")

    def test_similarity_uses_normalized_name(self):
        """P0-2：全半角括号不拉低相似度，精确同名（标准化后）者胜。"""
        query = "同济大学(四平路校区)"
        c_full = Candidate(poi_id="1", name="同济大学（四平路校区）")
        c_other = Candidate(poi_id="2", name="同济大学（嘉定校区）")
        entries = [
            (c_full, _record("1", "同济大学（四平路校区）", area_km2=1.0)),
            (c_other, _record("2", "同济大学（嘉定校区）", area_km2=1.0)),
        ]
        best = match_best(entries, query)
        self.assertEqual(best[1].poi_id, "1")

    def test_distance_scoring_prefers_nearer(self):
        """有参考坐标时，面中心越近得分越高。"""
        c_near = Candidate(poi_id="1", name="X")
        c_far = Candidate(poi_id="2", name="X")
        entries = [
            (c_near, _record("1", "X", area_km2=1.0, center=(121.500, 31.200))),
            (c_far, _record("2", "X", area_km2=1.0, center=(121.600, 31.200))),
        ]
        best = match_best(entries, "X", ref_location=(121.500, 31.200))
        self.assertEqual(best[1].poi_id, "1")

    def test_rank_scoring_prefers_earlier(self):
        """检索返回越靠前（source_rank 越小）得分越高。"""
        c_first = Candidate(poi_id="1", name="X", source_rank=0)
        c_later = Candidate(poi_id="2", name="X", source_rank=5)
        entries = [
            (c_first, _record("1", "X", area_km2=1.0)),
            (c_later, _record("2", "X", area_km2=1.0)),
        ]
        best = match_best(entries, "X")
        self.assertEqual(best[1].poi_id, "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
