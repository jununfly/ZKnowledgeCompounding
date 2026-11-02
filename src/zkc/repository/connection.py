"""ZKC · Postgres 连接封装（P1.2）。

只读环境变量，绝不硬编码 DSN；psycopg 懒加载（import 失败只影响 Pg 实现，
内存 fake 与协议层不受影响，单测可在无 DB 环境跑）。
"""
from __future__ import annotations

import os
from typing import Optional

DEFAULT_DSN = "postgresql://postgres:zkc@localhost:55433/zkc_dev"


def get_dsn() -> str:
    return os.environ.get("ZKC_PG_DSN", DEFAULT_DSN)


def connect(dsn: Optional[str] = None):
    """返回 psycopg 连接。懒加载 psycopg（避免无依赖环境 import 失败）。"""
    import psycopg

    return psycopg.connect(dsn or get_dsn(), autocommit=False)
