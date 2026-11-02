# -*- coding: utf-8 -*-
"""候选过滤逻辑的离线测试。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.core.filter import (deduplicate_candidates, filter_candidates,
                                 relevant_candidates, select_candidates)
from get_aoi.models import Candidate


class TestFilter(unittest.TestCase):
    def test_exact_parent_target_survives_and_similar_pois_are_excluded(self):
        candidates = [
            Candidate("target", "东陆新村六街坊", parent_id="parent"),
            Candidate("other", "金杨新村六街坊"),
            Candidate("child", "东陆新村六街坊176弄", parent_id="target"),
            Candidate("kindergarten", "东陆幼儿园"),
        ]
        filtered = filter_candidates(candidates, query_name="东陆新村六街坊")
        relevant = relevant_candidates(filtered, "东陆新村六街坊")
        self.assertEqual([c.poi_id for c in relevant], ["target"])

    def test_campus_variants_exclude_affiliates_and_unrelated_schools(self):
        names = [
            "同济大学(四平路校区)", "同济大学(嘉定校区)",
            "同济大学(沪北校区)", "同济大学(沪西校区)",
            "同济大学彰武路校区", "同济大学附属同济医院", "同济小学",
            "同济大学-东区", "同济大学东区D楼",
        ]
        candidates = [Candidate(str(i), name) for i, name in enumerate(names)]
        filtered = filter_candidates(candidates, query_name="同济大学")
        relevant = relevant_candidates(filtered, "同济大学")
        self.assertEqual([c.name for c in relevant], names[:5])
        self.assertNotIn("同济大学附属同济医院", [c.name for c in relevant])

    def test_exact_transport_poi_does_not_shadow_campus_variants(self):
        candidates = [
            Candidate("campus", "同济大学(四平路校区)",
                      poi_type="教育培训;高等院校", detail=1),
            Candidate("metro", "同济大学", poi_type="交通设施;地铁站",
                      detail=1),
            Candidate("bus", "同济大学", poi_type="交通设施;公交车站",
                      detail=0),
        ]
        filtered = filter_candidates(candidates, query_name="同济大学")
        relevant = relevant_candidates(filtered, "同济大学")
        self.assertEqual([c.poi_id for c in relevant], ["campus"])

    def test_generic_branch_variants_across_poi_types(self):
        cases = [
            ("上海博物馆", ["上海博物馆", "上海博物馆(人民广场馆)",
                          "上海博物馆东馆", "上海博物馆附近文创店"],
             ["上海博物馆", "上海博物馆(人民广场馆)", "上海博物馆东馆"]),
            ("市立医院", ["市立医院", "市立医院北院区", "市立医院附属康复中心"],
             ["市立医院", "市立医院北院区"]),
            ("创新产业园", ["创新产业园", "创新产业园二期", "创新产业园周边停车场"],
             ["创新产业园", "创新产业园二期"]),
            ("xx博物馆", ["ＸＸ博物馆（北馆）"], ["ＸＸ博物馆（北馆）"]),
        ]
        for query, names, expected in cases:
            with self.subTest(query=query):
                candidates = [Candidate(str(i), name)
                              for i, name in enumerate(names)]
                actual = [c.name for c in relevant_candidates(candidates, query)]
                self.assertEqual(actual, expected)

    def test_city_prefix_name_is_accepted(self):
        # 官方名带城市/行政区前缀，query 落在名称末尾，应视为同一目标
        candidates = [
            Candidate("park", "上海和平公园"),
            Candidate("park2", "上海市和平公园"),
            Candidate("shop", "和平公园老面馒头店(杨浦分店)"),
            Candidate("exact", "和平公园"),
        ]
        relevant = relevant_candidates(candidates, "和平公园")
        ids = [c.poi_id for c in relevant]
        self.assertIn("park", ids)    # 城市前缀 → 同一目标
        self.assertIn("park2", ids)   # 行政区前缀 → 同一目标
        self.assertIn("exact", ids)   # 精确同名
        self.assertNotIn("shop", ids)  # 馒头店不是"和平公园"的分支

    def test_branch_word_buried_in_full_name_is_rejected(self):
        # "分店"藏在完整店名里（如"XX公园老面馒头店(杨浦分店)"），
        # 不是 query 的分支，应排除；而"校区/分店"紧跟名称才是分支。
        candidates = [
            Candidate("shop", "和平公园老面馒头店(杨浦分店)"),
            Candidate("branch", "和平公园杨浦分店"),
        ]
        relevant = relevant_candidates(candidates, "和平公园")
        self.assertEqual([c.poi_id for c in relevant], ["branch"])

    def test_deduplicate_and_keyword_selection_are_generic(self):
        candidates = [
            Candidate("1", "市立医院"),
            Candidate("2", "市立医院北院区"),
            Candidate("2", "市立医院北院区（重复）"),
        ]
        unique = deduplicate_candidates(candidates)
        self.assertEqual([c.poi_id for c in unique], ["1", "2"])
        selected = select_candidates(unique, want="keyword", keyword="北院")
        self.assertEqual([c.poi_id for c in selected], ["2"])


class TestKeepTypesLevels(unittest.TestCase):
    """keep_types 白名单按「任一级命中」匹配，支持二级/三级分类。"""

    def _mk(self, poi_id, poi_type):
        return Candidate(poi_id, "任意名称", poi_type=poi_type)

    def test_second_level_match(self):
        kept = filter_candidates(
            [self._mk("1", "商务住宅;住宅区;住宅小区")], keep_types=["住宅区"])
        self.assertEqual([c.poi_id for c in kept], ["1"])

    def test_first_level_still_matches(self):
        kept = filter_candidates(
            [self._mk("1", "商务住宅;住宅区;住宅小区")], keep_types=["商务住宅"])
        self.assertEqual([c.poi_id for c in kept], ["1"])

    def test_third_level_match(self):
        kept = filter_candidates(
            [self._mk("1", "金融;银行;ATM")], keep_types=["ATM"])
        self.assertEqual([c.poi_id for c in kept], ["1"])

    def test_pipe_separator(self):
        kept = filter_candidates(
            [self._mk("1", "金融|银行|ATM")], keep_types=["银行"])
        self.assertEqual([c.poi_id for c in kept], ["1"])

    def test_no_match_is_dropped(self):
        kept = filter_candidates(
            [self._mk("1", "商务住宅;住宅区;住宅小区")], keep_types=["餐饮服务"])
        self.assertEqual(kept, [])

    def test_whitespace_in_keep_types_is_trimmed(self):
        kept = filter_candidates(
            [self._mk("1", "商务住宅;住宅区;住宅小区")], keep_types=[" 住宅区 "])
        self.assertEqual([c.poi_id for c in kept], ["1"])

    def test_empty_poi_type_with_keep_is_dropped(self):
        kept = filter_candidates([self._mk("1", "")], keep_types=["住宅区"])
        self.assertEqual(kept, [])

    def test_keep_types_none_keeps_all(self):
        kept = filter_candidates(
            [self._mk("1", "商务住宅;住宅区;住宅小区")], keep_types=None)
        self.assertEqual([c.poi_id for c in kept], ["1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
