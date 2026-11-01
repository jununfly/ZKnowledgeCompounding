# TODO — zj 待办任务（临时记录，任务队列 UI 上线后废弃）

> 背景：任务应以队列形式呈现在 UI 上，避免遗忘。该功能已立项 **roadmap 1-9**（pending）。
> 本文件是过渡方案：观察期（1-7-4）期间人工对照执行，勿删。

## 每天（观察期硬前提）

- [ ] 打开 `http://localhost:8000/review`，处理到期条目：每条**带标注**（仍有效 / 已变 / 已腐）
  - 标注率 ≥70% 是 L3 学习的硬门槛；只浏览不标注 = 不给学习信号
- [ ] 每日收口：底部表单填 pushed / queue_remaining → 记录（budget 估计唯一外生锚）

## 每周五（15 分钟）

- [ ] `python scripts/metrics_snapshot.py` 跑度量快照
- [ ] 对照 user-guide §4 复盘清单：复利系数趋势 / 拆四项 / 标注率 / 收口纪律

## 带日历的预警

- **~11/05-11/06**：60 条 orphan(7d) 基线集中到期，pushed 预计冲到 ~60 —— 如实收口，不调参
- **累计 ≥20 个带标注复审**：达成即判 1-7-4（R10 降级判定），届时 roadmap 翻 completed

## 一次性

- [ ] commit + push 本轮改动（README / Makefile / scripts/cold_start_import.py / roadmap / TODO.md）—— 等显式触发
