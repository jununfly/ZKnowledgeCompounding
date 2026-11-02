"""ZKC · 任务队列领域逻辑（1-9，MVP）。

把观察期 zj 的过渡待办清单，转为「规则自动生成的任务卡片队列」，并入 /review
顶部，避免遗忘，并打通现有闭环（复审标注率 / budget 收口埋点）。

设计要点：
- 纯函数层（generate_due_tasks / task_queue_view / complete_task）无 HTTP 依赖，
  可脱离 web 栈单测（MemoryStorage 注入）。
- 任务由「规则」产出 TaskSpec，`store.tasks.ensure_today` 按 (day, kind) 幂等 upsert：
  已存在项保留其 status（done 不被覆盖）——这是「每日重算但已完成不回弹」的关键。
- 一次性任务 commit_push 不自动执行 git（UI 完成仅标记 done + 记 note），git 操作仍等
  用户显式触发（一次性任务完成仅标记 done + 记 note；git 操作仍等用户显式触发）。

溯源锚：roadmap 1-9 decisions；原过渡待办清单已逐项映射到下方规则。
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional
from uuid import UUID

from zkc.repository.models import TaskItem, TaskSpec
from zkc.repository.protocols import Storage

# --- 规则常量（与 roadmap 1-9 对齐；如需调参集中在此）---
LABEL_JUDGMENT_THRESHOLD = 20          # 累计带标注复审 ≥20 → 判 1-7-4（R10 降级判定）
ORPHAN_SPIKE_START = date(2026, 11, 5)  # orphan(7d) 基线集中到期窗口起点
ORPHAN_SPIKE_END = date(2026, 11, 6)    # 窗口终点


def _as_datetime(d: date) -> datetime:
    return datetime.combine(d, time.min)


def generate_due_tasks(store: Storage, now: Optional[datetime] = None) -> list[TaskSpec]:
    """产出「当日应生成」的任务规格清单（不含持久态）。

    三类：周期 / 预警 / 一次性。
    labeled_judgment 需读 attention 观测累计标注数，故接收 store。
    """
    now = now or datetime.now(timezone.utc)
    day = now.date()
    specs: list[TaskSpec] = []

    # ---- 周期流程（每天）----
    specs.append(TaskSpec(
        day=now, category="periodic", kind="daily_review",
        title="每日复审标注",
        detail="打开 /review 处理到期条目并标注（仍有效/已变/已腐）；标注率≥70% 是 L3 学习硬门槛。",
        source_rule="periodic.daily_review",
    ))
    specs.append(TaskSpec(
        day=now, category="periodic", kind="daily_close",
        title="每日收口",
        detail="底部表单填 pushed / queue_remaining，记录 budget 估计唯一外生锚。",
        source_rule="periodic.daily_close",
    ))

    # ---- 周期流程（每周五）----
    if day.weekday() == 4:  # Friday
        specs.append(TaskSpec(
            day=now, category="periodic", kind="weekly_snapshot",
            title="每周五度量快照",
            detail="scripts/metrics_snapshot.py 跑度量快照 + 对照 user-guide §4 复盘清单。",
            source_rule="periodic.weekly_snapshot",
            payload={"script": "scripts/metrics_snapshot.py"},
        ))

    # ---- 带日历预警：orphan(7d) 基线集中到期尖峰 ----
    if ORPHAN_SPIKE_START <= day <= ORPHAN_SPIKE_END:
        specs.append(TaskSpec(
            day=now, category="alert", kind="orphan_spike",
            title="orphan(7d) 基线集中到期尖峰",
            detail="60 条 orphan(7d) 基线集中到期，pushed 预计冲到 ~60——如实收口，不调参。",
            due_date=_as_datetime(day), source_rule="alert.orphan_spike",
        ))

    # ---- 带日历预警：累计 ≥20 标注复审判定 1-7-4 ----
    total_labeled = _total_labeled_completed(store)
    if total_labeled >= LABEL_JUDGMENT_THRESHOLD:
        specs.append(TaskSpec(
            day=now, category="alert", kind="labeled_judgment",
            title="达成 1-7-4 降级判定",
            detail=f"累计带标注复审已达 {total_labeled}（≥{LABEL_JUDGMENT_THRESHOLD}）→ 判 1-7-4（R10），"
                   "roadmap 翻 completed。",
            due_date=_as_datetime(day),
            source_rule="alert.labeled_judgment",
            payload={"total_labeled": total_labeled},
        ))

    # ---- 一次性：commit + push 本轮改动（等显式触发，UI 完成仅标记 done）----
    specs.append(TaskSpec(
        day=now, category="once", kind="commit_push",
        title="commit + push 本轮改动",
        detail="等显式触发（不在 UI 自动执行 git）。完成后标记 done 仅作提醒闭环。",
        source_rule="once.commit_push",
    ))

    return specs


def _total_labeled_completed(store: Storage) -> int:
    """跨全部观测累计 labeled_completed（memory fake 的 list_recent 返回最近 N 条，
    用大窗口近似全量；PG 实现按日期过滤真实全量）。"""
    obs = store.attention.list_recent(366)
    return sum((o.labeled_completed or 0) for o in obs)


def _item_to_dict(it: TaskItem) -> dict:
    return dict(
        id=str(it.id),
        day=(it.day.isoformat() if isinstance(it.day, datetime) else it.day.isoformat()),
        category=it.category,
        kind=it.kind,
        title=it.title,
        detail=it.detail,
        due_date=(it.due_date.isoformat()
                  if isinstance(it.due_date, datetime) else
                  (it.due_date.isoformat() if it.due_date is not None else None)),
        status=it.status,
        source_rule=it.source_rule,
        completed_at=(it.completed_at.isoformat() if it.completed_at else None),
    )


def task_queue_view(store: Storage, now: Optional[datetime] = None) -> dict:
    """取当日任务队列快照（供页面渲染与 API 返回）：先 ensure 当日任务，再读全量统计。"""
    now = now or datetime.now(timezone.utc)
    day = now.date()
    store.tasks.ensure_today(generate_due_tasks(store, now))
    items = store.tasks.list_by_day(day)
    open_items = [it for it in items if it.status == "open"]
    return dict(
        as_of=now.isoformat(),
        day=str(day),
        items=[_item_to_dict(it) for it in items],
        open_count=len(open_items),
        done_count=len(items) - len(open_items),
    )


def complete_task(store: Storage, task_id, now: Optional[datetime] = None) -> dict:
    """标记一条任务完成（status='done'）。返回更新后的序列化项。"""
    now = now or datetime.now(timezone.utc)
    if isinstance(task_id, str):
        task_id = UUID(task_id)
    item = store.tasks.complete(task_id, now)
    return _item_to_dict(item)
