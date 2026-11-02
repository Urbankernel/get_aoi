# -*- coding: utf-8 -*-
"""单次运行目录管理（runs/<时间戳>_<标签>/）。

run 目录结构（每次运行独立子目录）：
    runs/<时间戳>_<CSV文件名>_<引擎>/
    ├── config.snapshot.yaml   配置快照（key 脱敏，续跑校验用）
    ├── state.json             断点续跑状态（由 core.state.StateStore 写入）
    ├── run.log                日志（由 utils.logger.attach_file_handler 写入）
    └── outputs/               完成后生成的 aoi.geojson / aoi.gpkg / aoi.shp
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def sanitize_tag(text: str, max_len: int = 50) -> str:
    """把 CSV 文件名 / provider 等转成安全目录名片段。"""
    tag = re.sub(r"[^\w一-鿿.-]+", "_", str(text)).strip("_")
    return tag[:max_len] or "run"


class RunStore:
    """单次运行的磁盘状态管理。"""

    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.outputs_dir = self.run_dir / "outputs"
        self.snapshot_path = self.run_dir / "config.snapshot.yaml"
        self.state_path = self.run_dir / "state.json"

    @classmethod
    def create(cls, root: str | Path, tag: str,
               config_snapshot: dict[str, Any]) -> "RunStore":
        """创建新 run 目录并写入配置快照。同一秒内重名自动追加序号。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(root) / f"{ts}_{sanitize_tag(tag)}"
        run_dir = base
        n = 1
        while run_dir.exists():
            n += 1
            run_dir = Path(f"{base}_{n}")
        (run_dir / "outputs").mkdir(parents=True)
        store = cls(run_dir)
        with open(store.snapshot_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_snapshot, f, allow_unicode=True, sort_keys=False)
        return store

    @classmethod
    def resume(cls, run_dir: str | Path) -> "RunStore":
        """打开既有 run 目录准备续跑。"""
        store = cls(run_dir)
        if not store.state_path.exists():
            raise FileNotFoundError(
                f"续跑失败：{store.state_path} 不存在，该目录不是有效的 run 目录")
        return store

    def load_snapshot(self) -> dict[str, Any]:
        with open(self.snapshot_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
