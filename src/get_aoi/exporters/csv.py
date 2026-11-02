# -*- coding: utf-8 -*-
"""CSV 报告导出（零第三方依赖）：summary.csv + aoi_attributes.csv。

面向非 GIS 用户：无需打开 GeoJSON 即可在 Excel / WPS 里核对
「哪些地名成功 / 失败 / 匹配了几个面」，以及每个面的扁平属性表。
"""
import csv
import json
from pathlib import Path

from ..models import AOIRecord

BASE_FIELDS = ["poi_id", "name", "provider", "poi_type", "address",
               "area_km2", "center_lng", "center_lat", "status"]


def _write_csv(rows, fieldnames, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _attribute_row(r: AOIRecord) -> dict:
    row = {
        "poi_id": r.poi_id,
        "name": r.name,
        "provider": r.provider,
        "poi_type": r.poi_type,
        "address": r.address,
        "area_km2": round(r.area_km2, 6),
        "center_lng": round(r.center[0], 7) if r.center else "",
        "center_lat": round(r.center[1], 7) if r.center else "",
        "status": r.status.value if hasattr(r.status, "value") else str(r.status),
    }
    for key, value in (r.extra or {}).items():
        if isinstance(value, (list, tuple, dict)):
            value = json.dumps(value, ensure_ascii=False)
        row[key] = value
    return row


def export_summary_csv(rows, path) -> int:
    """rows: [(name, status, matched_count), ...] -> summary.csv"""
    data = [{"name": name, "status": status, "matched_count": count}
            for name, status, count in rows]
    return _write_csv(data, ["name", "status", "matched_count"], path)


def export_attributes_csv(records, path) -> int:
    """每个 AOI 面一行，扁平属性表；字段取所有记录的并集。"""
    rows = [_attribute_row(r) for r in records if r.geometry]
    if not rows:
        return 0
    fieldnames = list(BASE_FIELDS)
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    return _write_csv(rows, fieldnames, path)
