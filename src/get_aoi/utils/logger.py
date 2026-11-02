# -*- coding: utf-8 -*-
"""日志工具（标准库 logging，零额外依赖）：控制台 + 文件双通道。

控制台默认 INFO；run 目录确定后调用 attach_file_handler 追加 DEBUG 级
文件通道（run.log），便于排障。重复调用安全（不会堆叠 handler）。
"""
import logging
import sys
from pathlib import Path

ROOT_LOGGER = "get_aoi"

_CONSOLE_FMT = "%(asctime)s [%(levelname)s] %(message)s"
_FILE_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_logger(name=ROOT_LOGGER):
    """返回包级 logger，并确保控制台通道已配置。"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # 包级放宽，由各 handler 自行过滤
    logger.propagate = False
    if not any(getattr(h, "_getaoi_console", False) for h in logger.handlers):
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(_CONSOLE_FMT, "%H:%M:%S"))
        console._getaoi_console = True  # type: ignore[attr-defined]
        logger.addHandler(console)
    return logger


def set_verbose(verbose=True):
    """切换控制台通道为 DEBUG / INFO。"""
    level = logging.DEBUG if verbose else logging.INFO
    for h in logging.getLogger(ROOT_LOGGER).handlers:
        if getattr(h, "_getaoi_console", False):
            h.setLevel(level)


def attach_file_handler(run_dir):
    """为本次运行追加文件日志通道（run.log），返回日志文件路径。"""
    logger = logging.getLogger(ROOT_LOGGER)
    log_path = Path(run_dir) / "run.log"
    if not any(getattr(h, "_getaoi_file", False) for h in logger.handlers):
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_FILE_FMT))
        file_handler._getaoi_file = True  # type: ignore[attr-defined]
        logger.addHandler(file_handler)
    return log_path
