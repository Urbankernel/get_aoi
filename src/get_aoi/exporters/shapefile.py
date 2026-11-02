# -*- coding: utf-8 -*-
"""Shapefile 导出（需 geopandas）。"""
from .base import export_geopandas


def export_shapefile(records, path):
    export_geopandas(records, path, "ESRI Shapefile")
