# -*- coding: utf-8 -*-
"""导出模块：按格式分发到 GeoJSON / Shapefile / GeoPackage。"""
from pathlib import Path

from .geojson import export_geojson
from .geopackage import export_geopackage
from .shapefile import export_shapefile

FORMATS = ("geojson", "shp", "gpkg")

_EXT_MAP = {".geojson": "geojson", ".json": "geojson",
            ".shp": "shp", ".gpkg": "gpkg"}


def detect_format(path, fmt=None):
    if fmt:
        fmt = fmt.lower()
        if fmt in ("shp", "shapefile"):
            return "shp"
        if fmt in ("gpkg", "geopackage"):
            return "gpkg"
        return "geojson"
    return _EXT_MAP.get(Path(path).suffix.lower(), "geojson")


def export(records, path, fmt=None):
    fmt = detect_format(path, fmt)
    if fmt == "shp":
        export_shapefile(records, path)
    elif fmt == "gpkg":
        export_geopackage(records, path)
    else:
        export_geojson(records, path)
    return fmt
