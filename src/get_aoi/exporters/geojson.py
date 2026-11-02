# -*- coding: utf-8 -*-
"""GeoJSON 导出（EPSG:4326，零第三方依赖）。"""
import json
from pathlib import Path

from .base import records_to_features


def export_geojson(records, path):
    fc = {"type": "FeatureCollection",
          "features": records_to_features(records)}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fc, ensure_ascii=False, indent=2),
                    encoding="utf-8")
