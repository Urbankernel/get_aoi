# -*- coding: utf-8 -*-
"""检索翻页（P1-7）离线测试：用 mock http 模拟多页返回。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.providers.amap import AmapProvider
from get_aoi.providers.baidu import BaiduProvider


class AmapPagedHttp:
    """模拟高德 place/text：每页 offset 条，第 N 页从 (page-1)*offset 起。"""
    def __init__(self, total):
        self.total = total
        self.calls = []

    def get_json(self, url, params=None, referer=None, extra_headers=None):
        self.calls.append(dict(params))
        page = params["page"]
        offset = params["offset"]
        start = (page - 1) * offset
        pois = []
        for i in range(start, min(start + offset, self.total)):
            pois.append({"id": f"B{i:03d}", "name": f"候选{i}",
                         "type": "科教文化服务;学校", "location": "121.5,31.2",
                         "parent": []})
        return {"status": "1", "pois": pois}


class BaiduPagedHttp:
    """模拟百度 place/v2/search：每页 page_size 条，page_num 从 0 起。"""
    def __init__(self, total):
        self.total = total
        self.calls = []

    def get_json(self, url, params=None, referer=None, extra_headers=None):
        self.calls.append(dict(params))
        page_num = params.get("page_num", 0)
        page_size = params.get("page_size", 10)
        start = page_num * page_size
        results = []
        for i in range(start, min(start + page_size, self.total)):
            results.append({"uid": f"u{i:03d}", "name": f"候选{i}",
                            "location": {"lng": 121.5, "lat": 31.2},
                            "detail": 1, "detail_info": {}})
        return {"status": 0, "results": results}


class TestAmapPagination(unittest.TestCase):
    def test_paginates_when_needed(self):
        http = AmapPagedHttp(total=30)
        p = AmapProvider(key="k", http=http, max_candidates=30)
        cands = p.search("测试")
        self.assertEqual(len(cands), 30)
        self.assertEqual(len(http.calls), 2)  # 第 2 页补足 30
        # 跨页 source_rank 连续递增
        self.assertEqual([c.source_rank for c in cands[:3]], [0, 1, 2])
        self.assertEqual(cands[25].source_rank, 25)

    def test_stops_when_page_short(self):
        http = AmapPagedHttp(total=26)
        p = AmapProvider(key="k", http=http, max_candidates=50)
        cands = p.search("测试")
        self.assertEqual(len(cands), 26)  # 第 2 页仅 1 条，停止翻页
        self.assertEqual(len(http.calls), 2)

    def test_default_one_page(self):
        http = AmapPagedHttp(total=100)
        p = AmapProvider(key="k", http=http, max_candidates=25)
        cands = p.search("测试")
        self.assertEqual(len(cands), 25)
        self.assertEqual(len(http.calls), 1)  # 25 正好一页，不翻页


class TestBaiduPagination(unittest.TestCase):
    def test_paginates_when_needed(self):
        http = BaiduPagedHttp(total=30)
        p = BaiduProvider(ak="k", http=http, max_candidates=30)
        cands = p.search("测试")
        self.assertEqual(len(cands), 30)
        self.assertEqual(len(http.calls), 2)  # 20 + 10
        self.assertEqual(cands[20].source_rank, 20)

    def test_stops_when_no_more(self):
        http = BaiduPagedHttp(total=15)
        p = BaiduProvider(ak="k", http=http, max_candidates=40)
        cands = p.search("测试")
        self.assertEqual(len(cands), 15)
        self.assertEqual(len(http.calls), 1)  # 15 < page_size 20，立即停止

    def test_rank_starts_at_zero(self):
        http = BaiduPagedHttp(total=3)
        p = BaiduProvider(ak="k", http=http, max_candidates=20)
        cands = p.search("测试")
        self.assertEqual([c.source_rank for c in cands], [0, 1, 2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
