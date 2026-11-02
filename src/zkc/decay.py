"""ZKC · 衰减模型（P1.3，生产落地 spike-01）。

双轨语义：衰减**只服务于动态轨**（腐化）；静态轨走双时态 valid_from/valid_to 表达事实
演进，衰减恒为 0（架构 §5/§6：双时态≠双轨，仅服务静态事实）。

阈值来源：全部走 ``zkc.tuning``（禁止裸数字，P1.4 铁律）。
- ``DECAY_FUNCTION``：linear（spike 01 当选；step 否决、exponential 备选）
- ``SURFACE_THRESHOLD`` = 0.6（进入注意力）
- ``ROT_THRESHOLD`` = 0.9（已腐化）

为什么是「应用层维护扫描」而非 DB 触发器：架构 §6 明确「所有候选均无原生 TTL/衰减
语义 → 衰减必须应用层建模」。故本模块提供纯函数模型 + 一个刷新器（refresh_decay），
由调用方在读取/调度前跑一次，把动态轨节点的 decay_score 重算并写回。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from . import tuning


# ---------------------------------------------------------------- 衰减函数


def decay_linear(elapsed_days: float, interval_days: float) -> float:
    """线性：腐化随流逝时间等比增长，到 interval 时饱和。

    spike 01 结论：阶梯（step）因「表面与腐化阈值同瞬跨越、行动窗口 0、rot 100%」被否决；
    指数窗口更大但触发过晚。线性是 MVP 当选模型。
    """
    if interval_days <= 0:
        return 1.0
    return min(1.0, max(0.0, elapsed_days / interval_days))


def decay_exponential(elapsed_days: float, half_life_days: float) -> float:
    """指数：每过一个半衰期衰减一半，渐近但永远到不了 1（spike 01 备选）。"""
    if half_life_days <= 0:
        return 1.0
    return min(1.0, max(0.0, 1.0 - 0.5 ** (elapsed_days / half_life_days)))


def decay_step(elapsed_days: float, interval_days: float) -> float:
    """阶梯：interval 前新鲜、到期瞬间全腐（spike 01 否决，保留作对比基线）。"""
    if interval_days <= 0:
        return 1.0
    return 1.0 if elapsed_days >= interval_days else 0.0


_DECAY_FUNCS = {
    "linear": decay_linear,
    "exponential": decay_exponential,
    "step": decay_step,
}


def _func() -> Any:
    return _DECAY_FUNCS[tuning.get("DECAY_FUNCTION")]


# ---------------------------------------------------------------- 取值助手


def _get(node: Any, key: str, default: Any = None) -> Any:
    """兼容 dict 与 Node 对象（dataclass），统一取值。"""
    if isinstance(node, Mapping):
        return node.get(key, default)
    return getattr(node, key, default)


def _as_utc(dt: Any) -> Any:
    """归一化到 UTC。DB 返回的是 tz-aware（timestamptz）；应用传入可能是 naive。

    两者混减会抛 TypeError，故统一到 UTC 后再相减。naive 视为 UTC。
    """
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def elapsed_days(node: Any, now: datetime) -> float:
    """距上次复审（或创建）的天数；无锚点则视为 0。"""
    anchor = _get(node, "last_reviewed_at") or _get(node, "created_at") or now
    if isinstance(anchor, datetime):
        return max(0.0, (_as_utc(now) - _as_utc(anchor)).total_seconds() / 86400.0)
    return 0.0


def compute_decay_score(node: Any, now: datetime) -> float:
    """当前 decay_score。**静态轨恒 0**；动态轨按所选函数计算。"""
    if _get(node, "track") == "static":
        return 0.0
    interval = _get(node, "review_interval")
    if interval is None:
        return 0.0
    if isinstance(interval, timedelta):
        interval_days = interval.total_seconds() / 86400.0
    else:
        interval_days = float(interval)
    if interval_days <= 0:
        return 1.0
    return _func()(elapsed_days(node, now), interval_days)


# ---------------------------------------------------------------- 调度助手


def surface(
    items: Iterable[Any],
    now: datetime,
    threshold: Optional[float] = None,
    budget: Optional[int] = None,
) -> list[Any]:
    """取 decay 超过阈值、且最腐化的若干条（注意力清单）。

    默认阈值走 ``SURFACE_THRESHOLD``；``budget`` 为注意力预算上限（条数）。
    """
    if threshold is None:
        threshold = tuning.get("SURFACE_THRESHOLD")
    scored = [(compute_decay_score(i, now), i) for i in items]
    above = [(s, i) for s, i in scored if s >= threshold]
    above.sort(key=lambda t: (-t[0],))  # 最腐化优先，稳定排序
    picked = [i for _, i in above]
    if budget is not None:
        picked = picked[:budget]
    return picked


def review_reset(node: Any, now: datetime) -> dict:
    """复审/蒸馏触碰：复位衰减时钟（返回新 dict，不就地改）。

    写库由仓库层的 save/update 负责（会触发双时态版本链快照）。
    """
    updated = dict(node) if isinstance(node, Mapping) else vars(node).copy()
    updated["last_reviewed_at"] = now
    updated["decay_score"] = 0.0
    return updated


# ---------------------------------------------------------------- 应用层触发器


def refresh_decay(repo: Any, now: datetime) -> int:
    """衰减维护扫描（应用层「触发器」）：重算并写回所有动态轨节点的 decay_score。

    对任意实现了 ``list_by_track`` + ``update_decay`` 的仓库生效（内存 fake 与 PG 同构）。
    返回刷新的节点数。静态轨节点被跳过（衰减恒 0，无需写）。
    """
    n = 0
    for node in repo.list_by_track("dynamic"):
        score = compute_decay_score(node, now)
        repo.update_decay(node.id, score)
        n += 1
    return n
