# -*- coding: utf-8 -*-
"""边界缓存：按「数据源 + poi_id」持久化已抠出的边界，跨次运行复用。

首次抠边界后写入本地 sqlite，下次遇到同一 poi_id 直接命中，省去一次
网页隐藏接口请求——既提速，也降低被反爬识别的风险（批量重跑时尤其明显）。

缓存的是 provider.fetch_boundary 的成果（AOIRecord 序列化），命中后由
fetcher 回填当前候选的名称/分类/地址。缓存键含 provider，避免高德 B 开头
id 与百度十六进制 uid 意外撞车。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from ..models import AOIRecord, Status


def _record_to_json(rec: AOIRecord) -> str:
    return json.dumps({
        "poi_id": rec.poi_id,
        "name": rec.name,
        "provider": rec.provider,
        "poi_type": rec.poi_type,
        "address": rec.address,
        "center": list(rec.center) if rec.center else None,
        "geometry": rec.geometry,
        "raw_coords": rec.raw_coords,
        "area_km2": rec.area_km2,
        "status": rec.status.value if hasattr(rec.status, "value") else str(rec.status),
        "extra": rec.extra or {},
    }, ensure_ascii=False)


def _record_from_json(payload: str) -> Optional[AOIRecord]:
    try:
        d = json.loads(payload)
    except (ValueError, TypeError):
        return None
    center = d.get("center")
    return AOIRecord(
        poi_id=d.get("poi_id", ""),
        name=d.get("name", ""),
        provider=d.get("provider", ""),
        poi_type=d.get("poi_type", ""),
        address=d.get("address", ""),
        center=tuple(center) if center else None,
        geometry=d.get("geometry"),
        raw_coords=d.get("raw_coords", ""),
        area_km2=d.get("area_km2", 0.0),
        status=Status(d.get("status", "Matched")),
        extra=d.get("extra", {}),
    )


class BoundaryCache:
    """sqlite 持久化边界缓存（线程安全，可跨多次运行复用）。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + 自持锁：并发抓取下由单连接串行读写
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS boundary ("
            "key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        self._conn.commit()

    @staticmethod
    def _key(provider: str, poi_id: str) -> str:
        return f"{provider}|{poi_id}"

    def get(self, provider: str, poi_id: str) -> Optional[AOIRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM boundary WHERE key=?",
                (self._key(provider, poi_id),)).fetchone()
        return _record_from_json(row[0]) if row else None

    def put(self, provider: str, record: AOIRecord) -> None:
        payload = _record_to_json(record)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO boundary (key, payload) VALUES (?, ?)",
                (self._key(provider, record.poi_id), payload))
            self._conn.commit()

    def size(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM boundary").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
