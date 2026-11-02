# -*- coding: utf-8 -*-
"""高德 Provider：place/text 检索 + getPoiInfo 抠边界。

前半段（官方）：https://restapi.amap.com/v3/place/text
后半段（隐藏）：https://amap-pc-ssr.amap.com/ssr/api/getPoiInfo?id=<id>
边界字段 spec.mining_shape.shape（; 分隔），备用 bound（_ 分隔），GCJ-02。
"""
from typing import List, Optional

from ..core.geometry import (geometry_area_km2, geometry_center,
                             multipolygon_geometry, split_rings)
from ..models import AOIRecord, Candidate, Status
from ..utils.coords import convert_points
from ..utils.http import HttpClient
from ..utils.logger import get_logger
from .base import BaseProvider

logger = get_logger()


class AmapProvider(BaseProvider):
    name = "amap"
    source_crs = "gcj02"
    SEARCH_URL = "https://restapi.amap.com/v3/place/text"
    BOUNDARY_URL = "https://amap-pc-ssr.amap.com/ssr/api/getPoiInfo"
    DETAIL_FIELDS = ("typecode", "type", "newtype", "adcode", "citycode",
                     "cityname", "districtname", "tel")

    def __init__(self, key, http: Optional[HttpClient] = None,
                 max_candidates: int = 25, boundary_headers=None):
        if not key:
            raise ValueError("请在 .env 中配置高德 Web 服务 Key：AMAP_KEY")
        self.key = key
        self.http = http or HttpClient()
        self.max_candidates = max_candidates
        self.boundary_headers = dict(boundary_headers or {})

    # ---------- 前半段：名称 → 候选 ----------
    def search(self, name: str, city: Optional[str] = None) -> List[Candidate]:
        # 翻页取候选：place/text 每页 offset≤25，重名场景（区政府/人民医院）
        # 候选可能超一页，逐页翻直到取满 max_candidates 或无更多。
        page_size = 25
        needed = self.max_candidates
        max_pages = (needed + page_size - 1) // page_size
        candidates: List[Candidate] = []
        rank = 0
        for page in range(1, max_pages + 1):
            params = {
                "keywords": name,
                "city": city or "全国",
                "output": "JSON",
                "offset": page_size,
                "page": page,
                "key": self.key,
                "extensions": "all",
            }
            data = self.http.get_json(self.SEARCH_URL, params=params)
            if not data or data.get("status") != "1":
                if page == 1:
                    logger.warning("高德检索失败：%s，返回：%s", name,
                                   (data or {}).get("info", "无响应"))
                break
            pois = data.get("pois", [])
            if not pois:
                break
            for p in pois:
                candidates.append(self._to_candidate(p, rank))
                rank += 1
            if len(pois) < page_size or len(candidates) >= needed:
                break
        return candidates[:needed]

    def _to_candidate(self, p, rank):
        parent = p.get("parent")
        return Candidate(
            poi_id=self._s(p.get("id")),
            name=self._s(p.get("name")),
            poi_type=self._s(p.get("type")),
            typecode=self._s(p.get("typecode")),
            keytag=self._s(p.get("keytag")),
            location=self._parse_location(p.get("location")),
            parent_id=parent if isinstance(parent, str) else "",
            source_rank=rank,
            address=self._s(p.get("address")),
        )

    @staticmethod
    def _s(v):
        return v if isinstance(v, str) else ""

    @staticmethod
    def _parse_location(loc):
        if isinstance(loc, str) and "," in loc:
            try:
                lng, lat = loc.split(",")[:2]
                return float(lng), float(lat)
            except ValueError:
                return None
        return None

    # ---------- 后半段：id → 边界 ----------
    def fetch_boundary(self, poi_id: str,
                       user_loc: Optional[tuple] = None) -> Optional[AOIRecord]:
        params = {"id": poi_id}
        if user_loc:
            params["user_loc"] = f"{user_loc[0]},{user_loc[1]}"
        data = self.http.get_json(
            self.BOUNDARY_URL, params=params,
            referer="https://ditu.amap.com/",
            extra_headers={"Origin": "https://ditu.amap.com",
                           **self.boundary_headers})
        if not data:
            return None
        payload = data.get("data", data) if isinstance(data, dict) else {}
        shape_str, sep = self._extract_shape(payload)
        if not shape_str:
            return None
        ring = self._parse_ring(shape_str, sep)
        if len(ring) < 3:
            return None
        # 按闭合点拆成多个环，支持飞地/多校区等多部件 AOI
        rings = [r for r in split_rings(ring) if len(r) >= 3]
        if not rings:
            return None
        wgs_rings = [convert_points(r, "gcj02", "wgs84") for r in rings]
        geometry = multipolygon_geometry([[r] for r in wgs_rings])
        if not geometry:
            return None
        return AOIRecord(
            poi_id=poi_id, name="", provider=self.name,
            geometry=geometry, raw_coords=shape_str,
            center=geometry_center(geometry),
            area_km2=geometry_area_km2(geometry),
            status=Status.MATCHED,
            extra=self._extract_attributes(payload),
        )

    @classmethod
    def _extract_attributes(cls, payload):
        """提取 data.base 基础属性及 data.tags 标签，兼容字段平铺响应。"""
        attributes = cls._extract_tags(payload)
        base = payload.get("base") if isinstance(payload, dict) else None
        source = base if isinstance(base, dict) else payload
        for key in cls.DETAIL_FIELDS:
            value = source.get(key) if isinstance(source, dict) else None
            attributes[key] = value if isinstance(value, str) else ""
        return attributes

    @staticmethod
    def _extract_tags(payload):
        """提取边界响应 data.tags 的四个属性字段，保持稳定属性结构。"""
        tags = payload.get("tags", {}) if isinstance(payload, dict) else {}
        if not isinstance(tags, dict):
            tags = {}
        return {
            "tag_show_info": (tags.get("tag_show_info")
                              if isinstance(tags.get("tag_show_info"), list) else []),
            "t_tag_list": (tags.get("t_tag_list")
                           if isinstance(tags.get("t_tag_list"), list) else []),
            "t_tag": tags.get("t_tag") if isinstance(tags.get("t_tag"), str) else "",
            "tag_display": (tags.get("tag_display")
                            if isinstance(tags.get("tag_display"), str) else ""),
        }

    @staticmethod
    def _extract_shape(payload):
        if not isinstance(payload, dict):
            return None, None
        spec = payload.get("spec", {})
        if isinstance(spec, dict):
            mining = spec.get("mining_shape", {})
            if isinstance(mining, dict) and mining.get("shape"):
                return mining["shape"], ";"
        if payload.get("bound"):
            return payload["bound"], "_"
        return None, None

    @staticmethod
    def _parse_ring(shape_str, sep):
        ring = []
        for pair in shape_str.split(sep):
            pair = pair.strip()
            if not pair:
                continue
            parts = [p.strip() for p in pair.split(",")]
            if len(parts) < 2:
                continue
            try:
                ring.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
        return ring
