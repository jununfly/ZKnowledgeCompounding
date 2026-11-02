"""ZKC · repository 层异常（P1.2 引入 OCC 后新增）。

仅放跨实现（Pg / Memory）共用的领域异常，避免领域代码依赖具体驱动的错误类型。
"""
from __future__ import annotations


class ConcurrentModification(Exception):
    """乐观并发控制（OCC）冲突：写入时期望的 version_seq 与库中当前版本不符。

    触发条件：两个写者都读到同一旧版本（version_seq = N）后，先提交者把
    version_seq 自增到 N+1；后提交者再带过期版本号 N 去写 →
    `WHERE ... AND version_seq = N` 不匹配（当前已是 N+1）→ 抛此异常。

    语义等价于 HTTP 412 Precondition Failed。调用方应重新读取最新版本后重试，
    或把冲突上报给用户裁决。
    """
