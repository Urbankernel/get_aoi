# -*- coding: utf-8 -*-
"""YAML 配置加载 + CLI 覆盖 + 校验。

凭证三级来源（优先级从高到低）：
  1. 配置文件 keys / headers 字段
  2. key_file 文件（每行「字段=值」，# 开头为注释）
  3. 环境变量（AMAP_KEY / BAIDU_AK / AMAP_COOKIE / AMAP_BX_UA 等）

CLI 参数（--provider/--city/--want/--keyword/--input/--keep-types/
--min-area/--max-area/--max-candidates/--output-dir）覆盖 YAML 同名项。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """配置错误（缺 key、参数非法、数值越界等）。"""


# 凭证字段（keys + 网页隐藏接口风控字段）
CREDENTIAL_FIELDS = (
    "amap", "baidu",
    "amap_cookie", "amap_user_agent",
    "amap_bx_ua", "amap_bx_umidtoken", "amap_bx_et",
    "amap_x_csrf_token", "amap_x_adiu", "amap_referer",
    "baidu_cookie", "baidu_user_agent",
)

# 字段名 → 环境变量名（key 字段沿用历史命名 AMAP_KEY / BAIDU_AK，其余取大写）
_ENV_MAP = {"amap": "AMAP_KEY", "baidu": "BAIDU_AK"}


@dataclass
class RequestConfig:
    min_interval: float = 1.0   # 请求最小间隔（秒）
    max_interval: float = 3.0   # 请求最大间隔（秒，随机抖动）
    retries: int = 3            # 失败重试次数
    timeout: float = 15.0       # 单次请求超时（秒）
    proxy: str = ""             # 代理，如 http://127.0.0.1:7890
    concurrency: int = 1        # 并发 worker 数（1=串行；>1 时共享限流器控制总 QPS）


@dataclass
class OutputsConfig:
    dir: str = "runs"           # run 目录根（每次运行独立子目录）
    format: str = "geojson"     # geojson | gpkg | shp
    report: bool = True         # 是否额外导出 summary.csv 与 aoi_attributes.csv


@dataclass
class CacheConfig:
    enabled: bool = True        # 是否启用按 poi_id 的边界缓存
    dir: str = ""               # 缓存目录，空则用 ~/.cache/get_aoi


@dataclass
class Config:
    provider: str               # amap | baidu
    input: str                  # 地名清单 csv
    amap_key: str = ""
    baidu_ak: str = ""
    city: str = ""              # 全局城市（csv 无 city 列时生效）
    want: str = "all"           # all | main | keyword
    keyword: str = ""           # want=keyword 时的分支关键词
    keep_types: str = ""        # 分类白名单，逗号分隔，任一级命中即保留（可填一级或二级分类）
    min_area: float = 0.0       # 最小面积 km²
    max_area: float = 1e9       # 最大面积 km²
    max_candidates: int = 25    # 每地名最大候选数
    request: RequestConfig = field(default_factory=RequestConfig)
    outputs: OutputsConfig = field(default_factory=OutputsConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    headers: dict[str, str] = field(default_factory=dict)  # 风控字段（除 amap/baidu 外）
    raw: dict[str, Any] = field(default_factory=dict)      # 合并覆盖后的原始配置（快照用）


def _load_credentials(raw: dict[str, Any]) -> dict[str, str]:
    """三级来源合并凭证，字段名（amap/baidu/amap_cookie/...）→ 值。"""
    creds: dict[str, str] = {}

    # 1) 配置文件 keys / headers
    keys = raw.get("keys") or {}
    if isinstance(keys, dict):
        for k in ("amap", "baidu"):
            v = keys.get(k)
            if v and str(v).strip() and not str(v).startswith("你的"):
                creds[k] = str(v).strip()
    headers = raw.get("headers") or {}
    if isinstance(headers, dict):
        for k, v in headers.items():
            if v and str(v).strip():
                creds[str(k).strip()] = str(v).strip()

    # 2) key_file（字段=值，逐行；文件不存在时跳过，由后续校验统一报缺 key）
    key_file = raw.get("key_file")
    if key_file:
        p = Path(str(key_file)).expanduser()
        if p.exists():
            with open(p, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and v and k not in creds:  # 不覆盖 YAML
                        creds[k] = v

    # 3) 环境变量
    for field in CREDENTIAL_FIELDS:
        env_name = _ENV_MAP.get(field, field.upper())
        v = os.environ.get(env_name, "").strip()
        if v and field not in creds:
            creds[field] = v
    return creds


def _validate(provider: str, want: str, out_format: str,
              min_area: float, max_area: float, max_candidates: int) -> None:
    if provider not in ("amap", "baidu"):
        raise ConfigError(f"provider 必须是 amap/baidu，当前: {provider!r}")
    if want not in ("all", "main", "keyword"):
        raise ConfigError(f"want 必须是 all/main/keyword，当前: {want!r}")
    if out_format not in ("geojson", "gpkg", "shp"):
        raise ConfigError(f"outputs.format 必须是 geojson/gpkg/shp，当前: {out_format!r}")
    if min_area < 0 or max_area < min_area:
        raise ConfigError(f"min_area/max_area 不合法: min={min_area}, max={max_area}")
    if max_candidates <= 0:
        raise ConfigError("max_candidates 必须为正整数")


def load_config(path: str | Path, overrides: dict[str, Any] | None = None) -> Config:
    """加载 YAML 配置并应用 CLI 覆盖，返回校验后的 Config。"""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    import yaml
    with open(path, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    # ---- CLI 覆盖 ----
    ov = overrides or {}
    if ov.get("provider"):
        raw["provider"] = ov["provider"]
    if ov.get("input"):
        raw["input"] = ov["input"]
    if ov.get("city"):
        raw["city"] = ov["city"]
    if ov.get("want"):
        raw["want"] = ov["want"]
    if ov.get("keyword"):
        raw["keyword"] = ov["keyword"]
    if ov.get("keep_types"):
        raw["keep_types"] = ov["keep_types"]
    if ov.get("min_area") is not None:
        raw["min_area"] = ov["min_area"]
    if ov.get("max_area") is not None:
        raw["max_area"] = ov["max_area"]
    if ov.get("max_candidates") is not None:
        raw["max_candidates"] = ov["max_candidates"]
    if ov.get("concurrency") is not None:
        raw.setdefault("request", {})["concurrency"] = ov["concurrency"]
    if ov.get("output_dir"):
        raw.setdefault("outputs", {})["dir"] = ov["output_dir"]
    if ov.get("format"):
        raw.setdefault("outputs", {})["format"] = ov["format"]

    # ---- 组装与校验 ----
    provider = str(raw.get("provider") or "amap").strip().lower()
    input_path = str(raw.get("input") or "").strip()
    if not input_path:
        raise ConfigError("未配置输入清单 input（地名清单 csv 路径）")
    if not Path(input_path).exists():
        raise ConfigError(f"输入清单不存在: {input_path}")

    want = str(raw.get("want") or "all").strip().lower()
    out_format = str((raw.get("outputs") or {}).get("format", "geojson")).strip().lower()
    min_area = float(raw.get("min_area", 0.0))
    max_area = float(raw.get("max_area", 1e9))
    max_candidates = int(raw.get("max_candidates", 25))
    _validate(provider, want, out_format, min_area, max_area, max_candidates)

    creds = _load_credentials(raw)
    amap_key = creds.get("amap", "")
    baidu_ak = creds.get("baidu", "")
    if provider == "amap" and not amap_key:
        raise ConfigError(
            "未配置高德 key：请在配置文件 keys.amap / key_file（amap=xxx）/ "
            "环境变量 AMAP_KEY 中填写"
        )
    if provider == "baidu" and not baidu_ak:
        raise ConfigError(
            "未配置百度 AK：请在配置文件 keys.baidu / key_file（baidu=xxx）/ "
            "环境变量 BAIDU_AK 中填写"
        )

    r = raw.get("request") or {}
    request = RequestConfig(
        min_interval=float(r.get("min_interval", 1.0)),
        max_interval=float(r.get("max_interval", 3.0)),
        retries=int(r.get("retries", 3)),
        timeout=float(r.get("timeout", 15.0)),
        proxy=str(r.get("proxy", "") or "").strip(),
        concurrency=int(r.get("concurrency", 1)),
    )
    if request.min_interval < 0 or request.max_interval < request.min_interval:
        raise ConfigError(
            f"request.min_interval/max_interval 不合法: "
            f"min={request.min_interval}, max={request.max_interval}"
        )
    if request.concurrency < 1:
        raise ConfigError("request.concurrency 必须为正整数（≥1）")

    o = raw.get("outputs") or {}
    outputs = OutputsConfig(
        dir=str(o.get("dir", "runs")),
        format=out_format,
        report=bool(o.get("report", True)),
    )

    c = raw.get("cache") or {}
    cache = CacheConfig(
        enabled=bool(c.get("enabled", True)),
        dir=str(c.get("dir", "") or "").strip(),
    )

    headers = {k: v for k, v in creds.items() if k not in ("amap", "baidu")}

    return Config(
        provider=provider, input=input_path,
        amap_key=amap_key, baidu_ak=baidu_ak,
        city=str(raw.get("city") or "").strip(),
        want=want,
        keyword=str(raw.get("keyword") or "").strip(),
        keep_types=str(raw.get("keep_types") or "").strip(),
        min_area=min_area, max_area=max_area, max_candidates=max_candidates,
        request=request, outputs=outputs, cache=cache, headers=headers,
        raw=raw,
    )
