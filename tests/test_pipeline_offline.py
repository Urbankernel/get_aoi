# -*- coding: utf-8 -*-
"""离线集成验证：用真实接口 JSON 结构驱动 检索→过滤→抠边界→导出，全程不联网。

运行：python tests/test_pipeline_offline.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from get_aoi.core.fetcher import fetch
from get_aoi.core.filter import (filter_candidates, relevant_candidates,
                                 select_candidates)
from get_aoi.core.matcher import match_best
from get_aoi.exporters import export
from get_aoi.exporters.base import record_table_properties
from get_aoi.models import POIInput
from get_aoi.providers.amap import AmapProvider


class FakeHttp:
    """模拟 HttpClient，按 URL 返回真实结构的 JSON。"""
    def __init__(self):
        self.last_extra_headers = None
        self.last_referer = None
        self.search_extra_headers = "not-called"

    def get_json(self, url, params=None, referer=None, extra_headers=None):
        self.last_extra_headers = extra_headers
        self.last_referer = referer
        if "place/text" in url:
            self.search_extra_headers = extra_headers
            return {
                "status": "1", "count": "3",
                "pois": [
                    {"id": "B00155K8FL", "name": "同济大学(四平路校区)",
                     "type": "科教文化服务;学校;高等院校", "typecode": "141201",
                     "keytag": "985大学", "location": "121.502250,31.282587",
                     "parent": [], "address": "四平路1239号"},
                    {"id": "BV10024697", "name": "同济大学(地铁站)",
                     "type": "交通设施服务;地铁站;地铁站", "typecode": "150500",
                     "location": "121.506269,31.281904", "parent": []},
                    {"id": "B00155MMUO", "name": "同济大学四平路校区南区",
                     "type": "科教文化服务;学校;高等院校", "typecode": "141201",
                     "parent": "B00155K8FL"},
                ],
            }
        if "getPoiInfo" in url:
            return {"data": {
                "base": {
                    "poiid": "B00155K8FL",
                    "id": "B00155K8FL",
                    "name": "同济大学(四平路校区)",
                    "address": "四平路1239号",
                    "tel": "021-65982200;021-65982643;021-65983643",
                    "typecode": "141201",
                    "type": "141201",
                    "newtype": "141201",
                    "adcode": "310110",
                    "citycode": "310000",
                    "cityname": "上海市",
                    "districtname": "杨浦区",
                },
                "spec": {"mining_shape": {"shape":
                    "121.502250,31.282587;121.503250,31.282587;"
                    "121.503250,31.283587;121.502250,31.283587"}},
                "tags": {
                    "tag_show_info": ["双一流", "985高校", "211高校"],
                    "t_tag_list": ["985大学", "大学", "高等教育"],
                    "t_tag": "985大学",
                    "tag_display": "985大学",
                },
            }}
        return None


def main():
    http = FakeHttp()
    provider = AmapProvider(
        key="fake", http=http,
        boundary_headers={"Bx-Ua": "session-value", "X-Csrf-Token": "csrf-value"})
    poi = POIInput(name="同济大学", city="上海")

    candidates = provider.search(poi.name, poi.city)
    assert len(candidates) == 3, f"候选数异常：{len(candidates)}"
    print(f"检索候选：{[(c.name, c.poi_id) for c in candidates]}")

    filtered = filter_candidates(candidates, query_name=poi.name)
    kept = relevant_candidates(filtered, poi.name)
    # 地铁站(交通设施) + 南区(子面) 应被过滤，仅余四平路校区
    assert len(kept) == 1, f"过滤后应为1，实际{len(kept)}：{[c.name for c in kept]}"
    print(f"过滤后：{[c.name for c in kept]}")

    kept = select_candidates(kept, want="main")
    entries = [(c, fetch(provider, c)) for c in kept]
    best = match_best(entries, poi.name)
    assert best is not None, "综合排序无结果"
    rec = best[2]
    assert rec.geometry and rec.geometry["type"] == "Polygon"
    assert rec.name == "同济大学(四平路校区)"
    assert http.last_extra_headers["Bx-Ua"] == "session-value"
    assert http.last_extra_headers["X-Csrf-Token"] == "csrf-value"
    assert http.last_extra_headers["Origin"] == "https://ditu.amap.com"
    assert http.last_referer == "https://ditu.amap.com/"
    assert http.search_extra_headers is None, "动态头不应混入官方检索请求"
    assert rec.extra["tag_show_info"] == ["双一流", "985高校", "211高校"]
    assert rec.extra["t_tag_list"] == ["985大学", "大学", "高等教育"]
    detail_fields = {
        "typecode": "141201", "type": "141201", "newtype": "141201",
        "adcode": "310110", "citycode": "310000", "cityname": "上海市",
        "districtname": "杨浦区",
        "tel": "021-65982200;021-65982643;021-65983643",
    }
    assert all(rec.extra[key] == value for key, value in detail_fields.items())
    table_props = record_table_properties(rec)
    assert json.loads(table_props["tag_show_info"])[0] == "双一流"
    assert json.loads(table_props["t_tag_list"])[0] == "985大学"
    shp_props = record_table_properties(rec, shapefile=True)
    assert "tag_show" in shp_props and "tag_disp" in shp_props
    assert shp_props["district"] == "杨浦区"
    assert shp_props["adcode"] == "310110"
    assert all(len(key) <= 10 for key in shp_props)
    print(f"最优匹配：{rec.name}，面积 {rec.area_km2:.6f} km²，中心 {rec.center}")

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "aoi.geojson"
        export([rec], out)
        fc = json.loads(out.read_text(encoding="utf-8"))
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 1
        props = fc["features"][0]["properties"]
        assert props["provider"] == "amap"
        assert props["tag_show_info"] == ["双一流", "985高校", "211高校"]
        assert props["t_tag_list"] == ["985大学", "大学", "高等教育"]
        assert props["t_tag"] == "985大学"
        assert props["tag_display"] == "985大学"
        assert all(props[key] == value for key, value in detail_fields.items())
        print(f"GeoJSON 导出验证通过：{props['name']} / {props['poi_id']}")

    print("\n离线端到端验证全部通过 ✔")


if __name__ == "__main__":
    main()
