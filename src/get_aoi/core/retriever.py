# -*- coding: utf-8 -*-
"""检索封装：名称 → 候选列表。"""
from typing import List

from ..models import Candidate, POIInput
from ..providers.base import BaseProvider


def retrieve(provider: BaseProvider, poi: POIInput) -> List[Candidate]:
    return provider.search(poi.name, poi.city)
