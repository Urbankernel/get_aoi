# -*- coding: utf-8 -*-
"""核心数据结构定义。

geometry 统一采用 GeoJSON dict（WGS-84，EPSG:4326），
Polygon 或 MultiPolygon，避免核心流程强依赖几何库。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Status(str, Enum):
    MATCHED = "Matched"            # 匹配到 AOI
    NO_CANDIDATE = "No Candidate"  # 检索无候选 / 全部被过滤
    NO_GEOMETRY = "No Geometry"    # 无边界 / 不满足面积过滤


@dataclass
class POIInput:
    """输入：一个地名（核心字段），可带城市与参考坐标。"""
    name: str
    city: Optional[str] = None
    lng: Optional[float] = None    # 参考经度，用于 distance 打分 / user_loc
    lat: Optional[float] = None


@dataclass
class Candidate:
    """检索阶段返回的一个候选 POI。"""
    poi_id: str                            # 高德 id（B001...）/ 百度 uid（十六进制）
    name: str
    poi_type: str = ""                     # type / tag 原始分类串
    typecode: str = ""                     # 高德 6 位编码（百度为空）
    keytag: str = ""                       # 高德关键词标签（如"地铁站"）
    location: Optional[tuple] = None       # (lng, lat)，检索接口原生坐标
    parent_id: str = ""                    # 子面指向父 POI（非空即子面）
    source_rank: int = 0                   # 检索返回索引 = search_rank
    detail: Optional[int] = None           # 百度 detail：1=面状主 POI，0=附属点
    address: str = ""


@dataclass
class AOIRecord:
    """抠边界后的 AOI 记录，geometry 为 GeoJSON dict（WGS-84）。"""
    poi_id: str
    name: str
    provider: str
    poi_type: str = ""
    address: str = ""
    center: Optional[tuple] = None         # (lng, lat) WGS-84
    geometry: Optional[dict] = None        # GeoJSON Polygon / MultiPolygon
    raw_coords: str = ""                   # 原始坐标串（留档）
    area_km2: float = 0.0
    status: Status = Status.NO_CANDIDATE
    extra: dict = field(default_factory=dict)
