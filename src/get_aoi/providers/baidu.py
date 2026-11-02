# -*- coding: utf-8 -*-
"""百度 Provider：place/v2/search 检索 + qt=ext 抠边界。

前半段（官方）：https://api.map.baidu.com/place/v2/search
后半段（隐藏）：https://map.baidu.com/?newmap=1&qt=ext&uid=<uid>&ext_ver=new&ie=utf-8&l=11
边界字段 content.geo（bd09mc 百度墨卡托），ext_ver=new 为关键开关。
"""
from typing import List, Optional

from ..core.geometry import (geometry_area_km2, geometry_center,
                             multipolygon_geometry)
from ..models import AOIRecord, Candidate, Status
from ..utils.coords import convert_points
from ..utils.http import HttpClient
from ..utils.logger import get_logger
from .base import BaseProvider

logger = get_logger()


class BaiduProvider(BaseProvider):
    name = "baidu"
    source_crs = "bd09mc"
    SEARCH_URL = "https://api.map.baidu.com/place/v2/search"
    BOUNDARY_URL = "https://map.baidu.com/"

    def __init__(self, ak, http: Optional[HttpClient] = None,
                 max_candidates: int = 20):
        if not ak:
            raise ValueError("请在 .env 中配置百度 AK：BAIDU_AK")
        self.ak = ak
        self.http = http or HttpClient()
        self.max_candidates = max_candidates

    # ---------- 前半段：名称 → 候选 ----------
    def search(self, name: str, city: Optional[str] = None) -> List[Candidate]:
        # 翻页取候选：place/v2/search 每页 page_size≤20，逐页翻（page_num
        # 从 0 起）直到取满 max_candidates 或无更多，避免漏掉重名候选。
        page_size = 20
        needed = self.max_candidates
        max_pages = (needed + page_size - 1) // page_size
        candidates: List[Candidate] = []
        rank = 0
        for page_num in range(max_pages):
            params = {
                "query": name,
                "region": city or "全国",
                "output": "json",
                "ak": self.ak,
                "scope": 2,
                "page_size": page_size,
                "page_num": page_num,
            }
            data = self.http.get_json(self.SEARCH_URL, params=params)
            if not data or data.get("status") != 0:
                if page_num == 0:
                    logger.warning("百度检索失败：%s，返回：%s", name,
                                   (data or {}).get("message", "无响应"))
                break
            results = data.get("results", [])
            if not results:
                break
            for r in results:
                candidates.append(self._to_candidate(r, rank))
                rank += 1
            if len(results) < page_size or len(candidates) >= needed:
                break
        return candidates[:needed]

    def _to_candidate(self, r, rank):
        info = r.get("detail_info", {}) or {}
        loc = r.get("location") or {}
        location = None
        if "lng" in loc and "lat" in loc:
            location = (loc["lng"], loc["lat"])
        return Candidate(
            poi_id=r.get("uid", ""),
            name=r.get("name", ""),
            poi_type=info.get("classified_poi_tag") or info.get("tag", ""),
            location=location,
            parent_id=info.get("parent_id", "") or "",
            source_rank=rank,
            detail=r.get("detail"),
            address=r.get("address", "") or "",
        )

    # ---------- 后半段：id → 边界 ----------
    def fetch_boundary(self, poi_id: str,
                       user_loc: Optional[tuple] = None) -> Optional[AOIRecord]:
        params = {
            "newmap": 1,
            "qt": "ext",
            "uid": poi_id,
            "ext_ver": "new",
            "ie": "utf-8",
            "l": 11,
        }
        data = self.http.get_json(self.BOUNDARY_URL, params=params,
                                  referer="https://map.baidu.com/")
        if not data:
            return None
        content = data.get("content") or {}
        geo_str = content.get("geo")
        if not geo_str:
            return None
        polygons = self._parse_geo(geo_str)
        if not polygons:
            return None
        polys_wgs = [convert_points(poly, "bd09mc", "wgs84")
                     for poly in polygons]
        geometry = multipolygon_geometry([[ring] for ring in polys_wgs])
        if not geometry:
            return None
        return AOIRecord(
            poi_id=poi_id, name="", provider=self.name,
            geometry=geometry, raw_coords=geo_str,
            center=geometry_center(geometry),
            area_km2=geometry_area_km2(geometry),
            status=Status.MATCHED,
        )

    @staticmethod
    def _parse_geo(geo_str):
        """geo 字符串 -> 多边形列表（bd09mc 坐标）。

        结构："N|bbox左下;bbox右上|1-x1,y1,x2,y2,...;"，"-" 分隔各多边形。
        """
        parts = geo_str.split("|")
        poly_part = parts[-1].rstrip(";")
        polygons = []
        segs = poly_part.split("-")
        for seg in segs[1:]:
            seg = seg.strip().strip(";")
            if not seg:
                continue
            nums = seg.split(",")
            pts = []
            for i in range(0, len(nums) - 1, 2):
                try:
                    pts.append((float(nums[i].strip()),
                                float(nums[i + 1].strip())))
                except (ValueError, IndexError):
                    continue
            if len(pts) >= 3:
                polygons.append(pts)
        return polygons
