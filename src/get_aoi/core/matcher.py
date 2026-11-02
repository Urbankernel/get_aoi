# -*- coding: utf-8 -*-
"""候选处理第三层：综合排序取最优（四维加权打分）。

四维：search_rank（检索相关性）/ similarity（名称相似度）/
      distance（参考坐标 ↔ 面中心距离）/ area（面积合理性）。
其中 search_rank、similarity 检索阶段即可得；distance、area 需抠边界后计算，
故综合排序位于流程末端。思路参考 BaiduAOISpider。
"""
import difflib
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..models import AOIRecord, Candidate
from .geometry import haversine_km
from .text import normalize_name


@dataclass
class MatchWeights:
    search_rank: float = 0.4
    similarity: float = 0.3
    distance: float = 0.2
    area: float = 0.1


def _median(values):
    """有序（或任意）数值列表的中位数，稳健抗异常值。"""
    values = sorted(values)
    n = len(values)
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def match_best(entries: List[Tuple[Candidate, Optional[AOIRecord]]],
               query_name: str,
               weights: Optional[MatchWeights] = None,
               ref_location: Optional[tuple] = None,
               min_area_km2: float = 0.0,
               max_area_km2: float = 1e9):
    """对 (候选, 边界) 列表打分，返回 (score, candidate, record) 最优项。

    面积不在 [min_area_km2, max_area_km2] 范围内的候选直接剔除；
    area 维度按"候选集面积中位数的对数偏离度"打分，越接近典型面积得分越高，
    用于压低异常大/异常小的面，而非恒为满分。
    """
    weights = weights or MatchWeights()
    # 先筛出有效候选（有几何且面积在允许范围内）
    valid = [(cand, rec) for cand, rec in entries
             if rec is not None and rec.geometry is not None
             and min_area_km2 <= rec.area_km2 <= max_area_km2]
    if not valid:
        return None
    # 面积参考：有效候选面积的中位数（稳健，不受个别极端面影响）
    median_area = _median([rec.area_km2 for _, rec in valid])
    if median_area <= 0:
        median_area = 1.0  # 防御：面积异常为 0 时退化为中性
    normalized_query = normalize_name(query_name)
    scored = []
    for cand, rec in valid:
        rank_score = 1.0 / (1 + cand.source_rank)
        sim = difflib.SequenceMatcher(
            None, normalized_query, normalize_name(cand.name or "")).ratio()
        dist_score = 0.0
        if ref_location and rec.center:
            d = haversine_km(ref_location[0], ref_location[1],
                             rec.center[0], rec.center[1])
            dist_score = 1.0 / (1 + d)
        area_score = 1.0 / (1.0 + abs(math.log(rec.area_km2 / median_area)))
        score = (weights.search_rank * rank_score
                 + weights.similarity * sim
                 + weights.distance * dist_score
                 + weights.area * area_score)
        scored.append((score, cand, rec))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0]
