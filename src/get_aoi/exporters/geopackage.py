# -*- coding: utf-8 -*-
"""GeoPackage 导出（需 geopandas）。"""
from .base import export_geopandas


def export_geopackage(records, path):
    export_geopandas(records, path, "GPKG")
