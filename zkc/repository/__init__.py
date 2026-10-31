"""ZKC · repository 包入口（P1.2）。

唯一对外注入点 = `get_storage()`。应用代码只 `from zkc.repository import get_storage`，
拿到 `Storage` 门面，绝不 import 具体 Pg / Memory 实现——这是 seam 成立的硬约束。
"""
from __future__ import annotations

import os
from typing import Optional

from .protocols import Storage
from .memory import MemoryStorage


def get_storage(kind: Optional[str] = None) -> Storage:
    """返回配置的 Storage 实现。

    kind 缺省读环境变量 ZKC_STORAGE（默认 "pg"）。可选 "memory"（无 DB 单测用）。
    Pg 实现懒加载（import 失败只在显式请求 pg 时暴露），不影响内存 fake 导入。
    """
    kind = (kind or os.environ.get("ZKC_STORAGE", "pg")).lower()
    if kind == "memory":
        return MemoryStorage()
    if kind == "pg":
        from .pg import PgStorage

        return PgStorage()
    raise ValueError(f"未知 storage kind: {kind!r}（支持 pg|memory）")


__all__ = ["get_storage", "Storage"]
