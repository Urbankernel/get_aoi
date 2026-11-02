# -*- coding: utf-8 -*-
"""断点续爬：按"数据源 + 名称"记已完成清单，中断后续跑不重复请求。

状态文件为 JSON：{ "amap|同济大学": {status, records:[...]}, ... }
"""
import json
from pathlib import Path
from typing import Optional


class StateStore:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    @staticmethod
    def key(provider: str, name: str) -> str:
        return f"{provider}|{name}"

    def is_done(self, provider: str, name: str) -> bool:
        return self.key(provider, name) in self.data

    def get(self, provider: str, name: str) -> Optional[dict]:
        return self.data.get(self.key(provider, name))

    def mark(self, provider: str, name: str, status: str, records: list):
        self.data[self.key(provider, name)] = {
            "status": status,
            "records": records,
        }

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8")
