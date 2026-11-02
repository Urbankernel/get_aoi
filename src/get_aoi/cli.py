# -*- coding: utf-8 -*-
"""命令行入口：run（名称清单 → AOI 面）/ estimate（干跑估算）/ convert（仅坐标转换）。

    get-aoi run -c configs/example.yaml                     # 新跑
    get-aoi run -c configs/example.yaml --resume runs/xxx   # 断点续跑
    get-aoi estimate -c configs/example.yaml                # 干跑估算（不发 POI 请求）
    get-aoi convert -i in.csv --crs gcj02                   # 仅坐标转换（不联网）
"""
from __future__ import annotations

import argparse
import csv
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import __version__
from .config import Config, ConfigError, load_config
from .core.cache import BoundaryCache
from .core.fetcher import fetch
from .core.filter import (deduplicate_candidates, filter_candidates,
                          relevant_candidates, select_candidates)
from .core.matcher import MatchWeights, match_best
from .core.retriever import retrieve
from .core.state import StateStore
from .exporters import export
from .exporters.csv import export_attributes_csv, export_summary_csv
from .models import POIInput
from .providers import get_provider
from .store import RunStore
from .utils.coords import convert_point
from .utils.http import AntiBotError, HttpClient
from .utils.logger import attach_file_handler, get_logger, set_verbose
from .utils.ratelimit import RateLimiter

logger = get_logger()


# ---------- 输入 ----------
def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def read_names(path):
    """读取地名清单。支持带表头 name,city,lng,lat，或无表头单列。"""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "name" in reader.fieldnames:
            for row in reader:
                name = (row.get("name") or "").strip()
                if name:
                    rows.append(POIInput(
                        name=name,
                        city=(row.get("city") or "").strip() or None,
                        lng=_to_float(row.get("lng")),
                        lat=_to_float(row.get("lat"))))
        else:
            f.seek(0)
            for line in f:
                name = line.strip().split(",")[0]
                if name:
                    rows.append(POIInput(name=name))
    return rows


# ---------- 快照与续跑校验 ----------
def _mask(value: str) -> str:
    """凭证脱敏：只露前 5 位。"""
    value = str(value)
    return value[:5] + "..." if len(value) > 5 else "***"


def _masked_snapshot(cfg: Config) -> dict:
    """配置快照：keys / headers 脱敏、key_file 路径移除（不进快照明文）。"""
    snapshot = dict(cfg.raw)
    if isinstance(snapshot.get("keys"), dict):
        snapshot["keys"] = {k: _mask(v) for k, v in snapshot["keys"].items()}
    if isinstance(snapshot.get("headers"), dict):
        snapshot["headers"] = {k: _mask(v) for k, v in snapshot["headers"].items()}
    snapshot.pop("key_file", None)
    return snapshot


def _check_resume_compat(snapshot: dict, cfg: Config) -> None:
    """续跑前校验关键配置与快照一致（数据源/清单/过滤变了续跑会串数据）。"""
    for key in ("provider", "input", "keep_types", "min_area", "max_area"):
        if snapshot.get(key) != cfg.raw.get(key):
            raise ConfigError(
                f"续跑配置与快照不一致（{key}）：\n"
                f"  快照: {snapshot.get(key)}\n  当前: {cfg.raw.get(key)}\n"
                f"请用原配置续跑，或另起新任务。"
            )


def _amap_boundary_headers(cfg: Config) -> dict:
    """从配置 headers 读取高德动态头，映射为请求头名，不记录其值。"""
    mapping = {
        "amap_bx_ua": "Bx-Ua",
        "amap_bx_umidtoken": "Bx-Umidtoken",
        "amap_bx_et": "Bx_et",
        "amap_x_csrf_token": "X-Csrf-Token",
        "amap_x_adiu": "X-Adiu",
        "amap_referer": "Referer",
    }
    return {header: cfg.headers[field]
            for field, header in mapping.items()
            if cfg.headers.get(field)}


# ---------- 数据源与 HTTP ----------
def _provider_factory(cfg: Config, limiter: RateLimiter):
    """返回 provider 工厂：每次调用创建独立 HttpClient/Provider。

    并发下每个 worker 各自持有独立 requests.Session（Session 非线程安全），
    共享同一个限流器控制总 QPS；串行时同样可用。
    """

    def make():
        cookie = cfg.headers.get(f"{cfg.provider}_cookie") or None
        user_agent = cfg.headers.get(f"{cfg.provider}_user_agent") or None
        http = HttpClient(
            min_interval=cfg.request.min_interval,
            max_interval=cfg.request.max_interval,
            retries=cfg.request.retries,
            timeout=cfg.request.timeout,
            cookie=cookie, user_agent=user_agent,
            proxies={"http": cfg.request.proxy, "https": cfg.request.proxy}
            if cfg.request.proxy else None,
            limiter=limiter)
        if cfg.provider == "amap":
            return get_provider("amap", key=cfg.amap_key, http=http,
                                max_candidates=cfg.max_candidates,
                                boundary_headers=_amap_boundary_headers(cfg))
        return get_provider("baidu", ak=cfg.baidu_ak, http=http,
                            max_candidates=cfg.max_candidates)

    return make


def _make_cache(cfg: Config):
    """按配置创建边界缓存；cache.enabled=False 时返回 None（不缓存）。"""
    if not cfg.cache.enabled:
        return None
    cache_dir = cfg.cache.dir or str(Path.home() / ".cache" / "get_aoi")
    return BoundaryCache(Path(cache_dir) / "boundary.db")


# ---------- 主流程 ----------
def _resolve_poi(provider, cfg: Config, poi: POIInput, weights, keep_types,
                 cache) -> tuple:
    """处理单个地名：检索 → 过滤 → 匹配 → 抠边界，返回 (results, status)。"""
    if cfg.city and not poi.city:
        poi.city = cfg.city
    ref_loc = (poi.lng, poi.lat) if poi.lng is not None and poi.lat is not None else None

    candidates = retrieve(provider, poi)
    filtered = filter_candidates(candidates, keep_types=keep_types,
                                 query_name=poi.name)
    relevant = relevant_candidates(filtered, poi.name)
    kept = select_candidates(relevant, want=cfg.want, keyword=cfg.keyword)
    kept = deduplicate_candidates(kept)
    logger.info("  候选 %d → 分类/子面过滤 %d → 名称相关与取舍 %d",
                len(candidates), len(filtered), len(kept))

    if not kept:
        return [], "No Candidate"

    entries = [(cand, fetch(provider, cand, user_loc=ref_loc, cache=cache))
               for cand in kept]

    if cfg.want == "all":
        results = [rec for _, rec in entries
                   if rec and rec.geometry
                   and cfg.min_area <= rec.area_km2 <= cfg.max_area]
    else:
        best = match_best(entries, poi.name, weights=weights,
                          ref_location=ref_loc,
                          min_area_km2=cfg.min_area,
                          max_area_km2=cfg.max_area)
        results = [best[2]] if best else []

    for rec in results:
        rec.provider = cfg.provider
    status = "Matched" if results else "No Geometry"
    return results, status


def _mark_done(state, cfg: Config, poi: POIInput, status, results, lock=None):
    """写断点状态；lock 非空时加锁（并发场景保证 state.json 串行写）。"""
    if not state:
        return
    record = [{"poi_id": r.poi_id, "name": r.name, "area_km2": r.area_km2}
              for r in results]
    if lock:
        with lock:
            state.mark(cfg.provider, poi.name, status, record)
            state.save()
    else:
        state.mark(cfg.provider, poi.name, status, record)
        state.save()


def _restore_completed(state, provider, cache, all_records, summary):
    """续跑：从边界缓存回填断点里已完成项的几何，避免导出覆盖历史成果。

    state.json 只存了每个面的 poi_id 摘要，完整几何在 BoundaryCache（sqlite）
    里；据此重建上次已抠出的面。缓存缺失或未启用缓存的项，清除其完成标记，
    交由后续流程重新抓取（不静默丢数据；边界请求仍会命中缓存，仅多耗检索额度）。
    """
    if not state.data:
        return
    reopened = 0
    for key, entry in list(state.data.items()):
        prov, sep, name = key.partition("|")
        if not sep or prov != provider:
            continue
        status = entry.get("status", "No Candidate")
        records = [r for r in (entry.get("records") or [])
                   if isinstance(r, dict) and r.get("poi_id")]
        if not records:
            # 无面结论（No Candidate / No Geometry）：无需几何，直接恢复结论
            summary.append((name, status, 0))
            continue
        restored = []
        if cache is not None:
            for rec in records:
                cached = cache.get(provider, rec["poi_id"])
                if cached is not None:
                    cached.provider = provider
                    restored.append(cached)
        if restored and len(restored) == len(records):
            all_records.extend(restored)
            summary.append((name, status, len(restored)))
        else:
            state.data.pop(key, None)
            reopened += 1
    if reopened:
        state.save()
        if cache is None:
            logger.warning(
                "续跑：%d 个已完成项因未启用边界缓存（cache.enabled 应为 true）"
                "无法回填几何，将重新抓取", reopened)
        else:
            logger.warning(
                "续跑：%d 个已完成项的边界缓存缺失，将重新抓取"
                "（边界请求仍会命中缓存，仅多耗检索额度）", reopened)


def _iter_pois(cfg: Config, provider_factory, state, weights, keep_types,
               cache):
    """遍历地名清单，产出 (poi, status, results)。每名即写断点，支持并发。"""
    pois = read_names(cfg.input)
    pending = []
    for poi in pois:
        if state and state.is_done(cfg.provider, poi.name):
            logger.info("已完成，跳过（断点续爬）：%s", poi.name)
            continue
        pending.append(poi)

    concurrency = cfg.request.concurrency
    state_lock = threading.Lock()

    if concurrency <= 1 or len(pending) <= 1:
        provider = provider_factory()
        for idx, poi in enumerate(pending, 1):
            logger.info("[%d/%d] %s", idx, len(pending), poi.name)
            results, status = _resolve_poi(provider, cfg, poi, weights,
                                           keep_types, cache)
            _mark_done(state, cfg, poi, status, results)
            logger.info("  结果：%s（%d 个面）", status, len(results))
            yield poi, status, results
        return

    def work(poi):
        provider = provider_factory()
        results, status = _resolve_poi(provider, cfg, poi, weights,
                                       keep_types, cache)
        _mark_done(state, cfg, poi, status, results, lock=state_lock)
        return poi, status, results

    ex = ThreadPoolExecutor(max_workers=concurrency)
    futures = [ex.submit(work, p) for p in pending]
    try:
        for fut in as_completed(futures):
            poi, status, results = fut.result()
            logger.info("  %s：%s（%d 个面）", poi.name, status, len(results))
            yield poi, status, results
    except AntiBotError:
        for f in futures:
            f.cancel()
        raise
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def _output_path(store: RunStore, fmt: str) -> Path:
    ext = {"geojson": "geojson", "gpkg": "gpkg", "shp": "shp"}[fmt]
    return store.outputs_dir / f"aoi.{ext}"


def _export_reports(store: RunStore, cfg: Config, summary, records) -> None:
    """导出 summary.csv 与 aoi_attributes.csv（outputs.report=True 时）。"""
    if not cfg.outputs.report:
        return
    try:
        names = []
        if summary:
            export_summary_csv(summary, store.outputs_dir / "summary.csv")
            names.append("summary.csv")
        if records:
            export_attributes_csv(records, store.outputs_dir / "aoi_attributes.csv")
            names.append("aoi_attributes.csv")
        if names:
            logger.info("报告已生成：%s", "、".join(names))
    except Exception as exc:  # 报告失败不影响主成果
        logger.warning("生成 CSV 报告失败（不影响主成果）：%s", exc)


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config, _overrides(args))
    weights = MatchWeights()
    keep_types = cfg.keep_types.split(",") if cfg.keep_types else None

    if args.resume:
        store = RunStore.resume(args.resume)
        _check_resume_compat(store.load_snapshot(), cfg)
    else:
        tag = f"{Path(cfg.input).stem}_{cfg.provider}"
        store = RunStore.create(cfg.outputs.dir, tag, _masked_snapshot(cfg))
    attach_file_handler(store.run_dir)
    logger.info("run 目录: %s", store.run_dir)

    limiter = RateLimiter(cfg.request.min_interval, cfg.request.max_interval)
    provider_factory = _provider_factory(cfg, limiter)
    cache = _make_cache(cfg)
    state = StateStore(str(store.state_path))
    all_records = []
    summary = []  # [(name, status, matched_count), ...]

    if args.resume:
        _restore_completed(state, cfg.provider, cache, all_records, summary)

    try:
        for poi, status, results in _iter_pois(cfg, provider_factory, state,
                                               weights, keep_types, cache):
            all_records.extend(results)
            summary.append((poi.name, status, len(results)))
    except AntiBotError as exc:
        logger.error("触发访问风控，流程中断：%s", exc)
        if all_records:
            output_path = _output_path(store, cfg.outputs.format)
            fmt = export(all_records, output_path, cfg.outputs.format)
            _export_reports(store, cfg, summary, all_records)
            logger.warning("已保存中断前已完成的 %d 个 AOI 面 → %s（%s，WGS-84）；"
                           "其余名称因风控未处理，可 --resume %s 续跑",
                           len(all_records), output_path, fmt, store.run_dir)
        return 2
    finally:
        if cache:
            cache.close()

    if not all_records:
        logger.warning("没有匹配到任何 AOI 面，未生成输出文件。")
        _export_reports(store, cfg, summary, all_records)
        return 0
    output_path = _output_path(store, cfg.outputs.format)
    fmt = export(all_records, output_path, cfg.outputs.format)
    _export_reports(store, cfg, summary, all_records)
    logger.info("完成：共 %d 个 AOI 面 → %s（%s，WGS-84）",
                len(all_records), output_path, fmt)
    return 0


# ---------- 干跑估算 ----------
def cmd_estimate(args: argparse.Namespace) -> int:
    cfg = load_config(args.config, _overrides(args))
    pois = read_names(cfg.input)
    n = len(pois)
    print(f"地名清单: {cfg.input}")
    print(f"地名数: {n} 个，数据源: {cfg.provider}，并发: {cfg.request.concurrency}")
    print(f"预估请求数: 检索约 {n} 次（max_candidates 较大时可能翻页）"
          f" + 边界 ≤ {n * cfg.max_candidates} 次"
          f"（每名称检索 1~多页 + 每个候选 1 次边界请求）")
    print(f"提示：高德个人 key 通常 5000 次/日配额；百度 100 次/日。"
          f"大清单请控制频率并开启断点续跑。")
    return 0


# ---------- convert 子命令（不联网） ----------
def cmd_convert(args: argparse.Namespace) -> int:
    with open(args.input, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        logger.error("输入为空：%s", args.input)
        return 1
    out_rows = []
    for row in rows:
        lng, lat = _to_float(row.get("lng")), _to_float(row.get("lat"))
        if lng is None or lat is None:
            continue
        olng, olat = convert_point(lng, lat, args.crs, args.to)
        row[f"{args.to}_lng"] = round(olng, 7)
        row[f"{args.to}_lat"] = round(olat, 7)
        out_rows.append(row)
    if not out_rows:
        logger.error("没有有效的 lng/lat 行。")
        return 1
    fieldnames = list(out_rows[0].keys())
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    logger.info("转换完成：%d 行 → %s", len(out_rows), args.output)
    return 0


# ---------- 参数解析 ----------
def _overrides(args: argparse.Namespace) -> dict:
    return {
        "provider": args.provider, "input": args.input, "city": args.city,
        "want": args.want, "keyword": args.keyword,
        "keep_types": args.keep_types,
        "min_area": args.min_area, "max_area": args.max_area,
        "max_candidates": args.max_candidates,
        "concurrency": args.concurrency,
        "output_dir": args.output_dir, "format": args.format,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="get-aoi", allow_abbrev=False,
        description="名称 → AOI 兴趣面获取工具（高德 / 百度）")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="调试日志")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("-c", "--config", required=True, help="YAML 配置文件路径")
        p.add_argument("--provider", choices=["amap", "baidu"],
                       help="数据源（覆盖配置）")
        p.add_argument("-i", "--input", help="地名清单 csv（覆盖配置）")
        p.add_argument("--city", help="全局城市（csv 无 city 列时生效，覆盖配置）")
        p.add_argument("--want", choices=["all", "main", "keyword"],
                       help="多结果取舍（覆盖配置）")
        p.add_argument("--keyword", help="want=keyword 时的分支关键词（覆盖配置）")
        p.add_argument("--keep-types", help="一级分类白名单，逗号分隔（覆盖配置）")
        p.add_argument("--min-area", type=float, help="最小面积 km²（覆盖配置）")
        p.add_argument("--max-area", type=float, help="最大面积 km²（覆盖配置）")
        p.add_argument("--max-candidates", type=int, help="每地名最大候选数（覆盖配置）")
        p.add_argument("--concurrency", type=int, help="并发 worker 数（覆盖配置 request.concurrency）")
        p.add_argument("--output-dir", help="run 目录根（覆盖配置 outputs.dir）")
        p.add_argument("--format", choices=["geojson", "gpkg", "shp"],
                       help="输出格式（覆盖配置）")

    run = sub.add_parser("run", help="名称清单 → AOI 边界面", allow_abbrev=False)
    add_common(run)
    run.add_argument("--resume", help="从既有 run 目录断点续跑")
    run.set_defaults(func=cmd_run)

    est = sub.add_parser("estimate", help="干跑：只读清单、估算请求数（不联网）",
                         allow_abbrev=False)
    add_common(est)
    est.set_defaults(func=cmd_estimate)

    conv = sub.add_parser("convert", help="仅坐标转换（不联网）", allow_abbrev=False)
    conv.add_argument("-i", "--input", required=True, help="输入 csv（含 lng,lat 列）")
    conv.add_argument("--crs", required=True,
                      choices=["wgs84", "gcj02", "bd09", "bd09mc"], help="源坐标系")
    conv.add_argument("--to", default="wgs84",
                      choices=["wgs84", "gcj02", "bd09", "bd09mc"], help="目标坐标系")
    conv.add_argument("-o", "--output", default="converted.csv", help="输出 csv")
    conv.set_defaults(func=cmd_convert)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    set_verbose(args.verbose)
    try:
        return args.func(args) or 0
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中断。断点状态已落盘，可用 --resume 续跑。", file=sys.stderr)
        return 130
    except Exception as exc:
        logger.error("运行失败：%s", exc)
        if args.verbose:
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
