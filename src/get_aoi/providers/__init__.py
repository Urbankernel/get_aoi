# -*- coding: utf-8 -*-
"""数据源 Provider：高德 / 百度。"""
from .amap import AmapProvider
from .baidu import BaiduProvider


def get_provider(name, **kwargs):
    name = (name or "").lower()
    if name == "amap":
        return AmapProvider(**kwargs)
    if name == "baidu":
        return BaiduProvider(**kwargs)
    raise ValueError(f"不支持的数据源：{name}（可选 amap / baidu）")
