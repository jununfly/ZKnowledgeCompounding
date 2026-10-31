"""ZKC · 冷启动 dogfood 驱动 + 验证（P4.2 两个外生锚真实写入）。

前提：python -m zkc.web 已在后台跑（localhost:8000），且已用 dogfood_review_seed.py 播种。

本脚本：
  1. 轮询 /review/api/queue 直到服务就绪；
  2. GET /review（确认 SSR 页面 200 且含标题）；
  3. 按标题把 4 条 DOGFOOD 节点映射到四种结果并 POST /review/api/decide
     （仍有效 / 已变 / 已腐 / 仅浏览）；
  4. POST /review/api/observe（每日收口：pushed=10, queue_remaining=3）；
  5. 用独立 PG 连接直查，验证两个外生锚真的落库：
       锚 A · 复审结果标注 → node.last_reviewed_at 复位 + decay=0；changed/stale 写 interval_adjustment(feedback)
       锚 B · 每日收口埋点 → attention_observation(completed/labeled/pushed/queue_remaining)

运行：python scripts/dogfood_review_drive.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zkc.repository import get_storage

import psycopg
from psycopg.rows import dict_row

BASE = "http://127.0.0.1:8000"
TITLE_TO_OUTCOME = {
    "仍有效": "still_valid",
    "已变": "changed",
    "已腐": "stale",
    "仅浏览": "browse",
}


def _http(method: str, path: str, form: dict | None = None) -> dict:
    url = BASE + path
    data = urllib.parse.urlencode(form).encode() if form else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/x-www-form-urlencoded"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def wait_ready() -> dict:
    for _ in range(50):
        try:
            q = _http("GET", "/review/api/queue")
            return q
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("server not ready after 15s")


def main() -> None:
    print("== 1) 等待服务就绪 + 拉取队列 ==")
    q = wait_ready()
    print(f"   due_count={q['due_count']}，今日观测={q.get('today_observation')}，"
          f"闸门={q['gate']['gate']}，预算={q['budget']['confidence']}")

    print("== 2) GET /review 页面 ==")
    import urllib.request as u
    with u.urlopen(BASE + "/review", timeout=10) as r:
        html = r.read().decode()
    ok = r.status == 200 and "每日复审队列" in html
    print(f"   HTTP {r.status}，含标题={'是' if ok else '否'}")

    print("== 3) 按标题映射，喂 4 条复审标注（锚 A + 锚 B 累加）==")
    by_outcome: dict[str, str] = {}
    for it in q["items"]:
        outcome = next((o for k, o in TITLE_TO_OUTCOME.items() if k in it["title"]), None)
        if outcome is None:
            continue
        res = _http("POST", "/review/api/decide",
                    form={"node_id": it["id"], "outcome": outcome})
        by_outcome[outcome] = res
        print(f"   {it['title'][:18]:<20} -> {outcome:<10} verdict={res.get('verdict')} "
              f"applied={res.get('applied')} new_interval={res.get('new_interval_days')} "
              f"今日标注={res['today_observation']['labeled_completed']}/{res['today_observation']['completed']}")

    print("== 4) 每日收口（锚 B）：pushed=10, queue_remaining=3 ==")
    obs = _http("POST", "/review/api/observe", form={"pushed": 10, "queue_remaining": 3})
    print(f"   attention_observation -> {obs}")

    print("== 5) 独立 PG 直查，验证两个外生锚真实写入 ==")
    verify()


def verify() -> None:
    store = get_storage("pg")
    now = datetime.now(timezone.utc)
    cur = store._conn.cursor(row_factory=dict_row)

    # 锚 A：node 复位 + interval_adjustment
    cur.execute(
        "SELECT id, title, last_reviewed_at, decay_score, review_interval "
        "FROM public.node WHERE title LIKE 'DOGFOOD%' ORDER BY title")
    rows = cur.fetchall()
    print("  [锚 A] 复审后 node 状态：")
    all_reset = True
    for r in rows:
        lr = r["last_reviewed_at"]
        delta = (now - lr).total_seconds() if lr else 9999
        # 复审后 decay 应≈0（mark_reviewed 置 0；队列刷新会按 elapsed 重算成极小值，非精确 0）
        reset_ok = (lr is not None and abs(delta) < 120 and float(r["decay_score"]) < 1e-3)
        all_reset = all_reset and reset_ok
        print(f"    {r['title'][:22]:<24} decay={float(r['decay_score']):.2e} "
              f"last_reviewed={lr.isoformat() if lr else None} (Δ{delta:.0f}s) {'✓' if reset_ok else '✗'}")

    cur.execute(
        "SELECT node_id, kind, old_days, new_days FROM public.interval_adjustment "
        "WHERE node_id IN (SELECT id FROM public.node WHERE title LIKE 'DOGFOOD%') "
        "ORDER BY node_id")
    ia = cur.fetchall()
    print(f"  [锚 A] interval_adjustment 写入 {len(ia)} 行（on_time 无操作已跳过审计；仅 too_late=7→4.9 缩短）：")
    for r in ia:
        print(f"    node={str(r['node_id'])[:8]} kind={r['kind']} {r['old_days']}d -> {float(r['new_days']):.2f}d")

    # 锚 B：attention_observation
    cur.execute(
        "SELECT day, pushed, completed, queue_remaining, labeled_completed "
        "FROM public.attention_observation WHERE day = current_date")
    ao = cur.fetchall()
    print(f"  [锚 B] attention_observation 今日 {len(ao)} 行：")
    for r in ao:
        print(f"    day={r['day']} pushed={r['pushed']} completed={r['completed']} "
              f"queue_remaining={r['queue_remaining']} labeled_completed={r['labeled_completed']}")

    # 断言
    assert all_reset, "锚 A 失败：存在未复位的 node"
    feedback = [r for r in ia if r["kind"] == "feedback"]
    shortened = [r for r in feedback if float(r["new_days"]) < float(r["old_days"])]
    assert len(shortened) == 2, f"锚 A 失败：too_late 缩短行应为 2（已变+已腐），实际 {len(shortened)}"
    assert any(float(r["new_days"]) < float(r["old_days"]) for r in feedback), "锚 A 失败：too_late 未缩短 interval"
    assert ao and ao[0]["completed"] == 4, f"锚 B 失败：completed 应为 4，实际 {ao[0]['completed'] if ao else '无'}"
    assert ao and ao[0]["labeled_completed"] == 3, f"锚 B 失败：labeled_completed 应为 3（browse 不标注），实际 {ao[0]['labeled_completed'] if ao else '无'}"
    assert ao and ao[0]["pushed"] == 10 and ao[0]["queue_remaining"] == 3, "锚 B 失败：收口 pushed/queue_remaining 未写入"
    print("\n✅ 两个外生锚均真实写入：锚 A（node 复位 + interval_adjustment feedback×2）+ 锚 B（attention_observation 收口埋点）。")


if __name__ == "__main__":
    main()
