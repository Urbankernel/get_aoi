# -*- coding: utf-8 -*-
"""抠边界封装：候选 → AOIRecord，并回填候选的名称/分类/地址。

可传入 BoundaryCache：按 poi_id 复用已抠边界，跨次运行避免重复请求。
"""
from typing import Optional

from ..models import AOIRecord, Candidate
from ..providers.base import BaseProvider
from .cache import BoundaryCache


def fetch(provider: BaseProvider, candidate: Candidate,
          user_loc: Optional[tuple] = None,
          cache: Optional[BoundaryCache] = None) -> Optional[AOIRecord]:
    if cache is not None:
        rec = cache.get(provider.name, candidate.poi_id)
        if rec is not None:
            # 命中缓存：回填当前候选的名称/分类/地址后直接返回
            rec.name = candidate.name
            rec.poi_type = candidate.poi_type
            rec.address = candidate.address
            return rec
    rec = provider.fetch_boundary(candidate.poi_id, user_loc=user_loc)
    if rec is not None:
        rec.name = candidate.name
        rec.poi_type = candidate.poi_type
        rec.address = candidate.address
        if cache is not None:
            cache.put(provider.name, rec)
    return rec
