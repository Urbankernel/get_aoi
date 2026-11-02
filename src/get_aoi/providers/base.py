# -*- coding: utf-8 -*-
"""Provider 抽象基类：名称 → 候选 → 边界，两段式统一接口。"""
from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import AOIRecord, Candidate


class BaseProvider(ABC):
    name: str = ""          # "amap" | "baidu"
    source_crs: str = ""    # 该源边界原生坐标系（gcj02 / bd09mc）

    @abstractmethod
    def search(self, name: str, city: Optional[str] = None) -> List[Candidate]:
        """前半段：名称 → 候选列表（官方检索接口，按相关性排序）。"""

    @abstractmethod
    def fetch_boundary(self, poi_id: str,
                       user_loc: Optional[tuple] = None) -> Optional[AOIRecord]:
        """后半段：id → 边界（网页隐藏接口），失败/无边界返回 None。"""
