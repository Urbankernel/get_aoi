# -*- coding: utf-8 -*-
"""导出基础：AOIRecord -> GeoJSON Feature，及 geopandas 通用导出。"""
import json

from ..models import AOIRecord


SHAPEFILE_FIELD_ALIASES = {
    "tag_show_info": "tag_show",
    "tag_display": "tag_disp",
    "districtname": "district",
}


def record_properties(r: AOIRecord) -> dict:
    """GeoJSON 属性：保留 extra 中的数组等原生 JSON 类型。"""
    properties = dict(r.extra or {})
    properties.update({
        "poi_id": r.poi_id,
        "name": r.name,
        "provider": r.provider,
        "poi_type": r.poi_type,
        "address": r.address,
        "area_km2": round(r.area_km2, 6),
        "status": r.status.value if hasattr(r.status, "value") else str(r.status),
    })
    return properties


def record_table_properties(r: AOIRecord, shapefile=False) -> dict:
    """GIS 表属性：数组/对象转 JSON 字符串；Shapefile 字段名不超过 10 字符。"""
    properties = record_properties(r)
    rows = {}
    for key, value in properties.items():
        if isinstance(value, (list, tuple, dict)):
            value = json.dumps(value, ensure_ascii=False)
        output_key = SHAPEFILE_FIELD_ALIASES.get(key, key) if shapefile else key
        rows[output_key] = value
    return rows


def records_to_features(records):
    features = []
    for r in records:
        if not r.geometry:
            continue
        features.append({
            "type": "Feature",
            "properties": record_properties(r),
            "geometry": r.geometry,
        })
    return features


def export_geopandas(records, path, driver):
    """用 geopandas 导出 shp/gpkg（可选依赖，GeoJSON 导出不需要）。"""
    try:
        import geopandas as gpd
        from shapely.geometry import shape
    except ImportError as exc:
        raise RuntimeError(
            f"导出 {driver} 需要 geopandas，请先执行：pip install geopandas"
        ) from exc
    rows = []
    for r in records:
        if not r.geometry:
            continue
        row = record_table_properties(r, shapefile=driver == "ESRI Shapefile")
        row["geometry"] = shape(r.geometry)
        rows.append(row)
    if not rows:
        raise RuntimeError("没有可导出的 AOI 面记录。")
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    gdf.to_file(str(path), driver=driver)
