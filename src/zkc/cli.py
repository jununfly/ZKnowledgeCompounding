"""ZKC · 顶层 CLI（Form B：去服务器化，composer Plan `zkc-daily-run-forms-v1`）。

把已落地的 direct-mode 纯函数（record_daily_observation_auto / decide_review /
review_queue_view / E1 仪表 build_report）提升为正式 `zkc` CLI 子命令，使每日循环
不再依赖 web 服务常驻（ADR-0007 已授权；E1 校准闭环是 product execution，本文件即
harness gap 修复）。

子命令：
  zkc daily           每日真值收口（替代 /review/api/observe/auto，无需 web 服务）
  zkc meter [--json]  E1 校准进度仪表（E1 退出判据读数）
  zkc p64 [--json]    PRD §9 P6.4 观察期达成读数（只读，不写埋点）
  zkc decide          人环复审：
                      默认（无 --id）= 列出当前 due 复审条目（供 harness 呈现给人）
                      --id <id> --verdict <v> = 写一条复审标注
                      （v ∈ still_valid | changed | stale | browse）
  zkc archive --corpus [--dry-run] [--json]
                       导入语料批量归档（D2）：只写 archived_at，不动标注埋点
  zkc embed [--dry-run] [--json]
                       补齐节点 embedding 双列（全轨、幂等、空正文用标题兜底）

存储：默认 pg（ZKC_PG_DSN 或默认 localhost:55433/zkc_dev）；--storage memory 走内存后端。

硬约束（架构 §6.5.1 / ADR-0007）：decide 的 verdict 必须由人给出，CLI 绝不替人编造
（自动化 = 伪造外生锚 A，废掉 L3 闭环）。本 CLI 只把人已做的决定写入存储。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from zkc import scheduling as S
from zkc.calibration import (
    build_p64_report,
    build_report,
    format_human,
    format_p64_human,
)
from zkc.repository import get_storage
from zkc.web.review import (
    decide_review,
    record_daily_observation_auto,
    review_queue_view,
)

VERDICTS = ("still_valid", "changed", "stale", "browse")


def _make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="zkc",
        description="ZKC 知识复利工具 CLI（去服务器化运行形态）",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_daily = sub.add_parser("daily", help="每日真值收口（无需 web 服务）")
    p_daily.add_argument("--storage", default="pg", help="pg（默认）或 memory")

    p_meter = sub.add_parser("meter", help="E1 校准进度仪表（E1 退出判据读数）")
    p_meter.add_argument("--storage", default="pg", help="pg（默认）或 memory")
    p_meter.add_argument("--json", action="store_true", help="输出 JSON 供管道消费")

    p_p64 = sub.add_parser(
        "p64", help="PRD §9 P6.4 观察期达成读数（只读，不写埋点）")
    p_p64.add_argument("--storage", default="pg", help="pg（默认）或 memory")
    p_p64.add_argument("--json", action="store_true", help="输出 JSON 供管道消费")

    p_decide = sub.add_parser(
        "decide", help="人环复审：默认列 due 条目；--id+--verdict 写标注")
    p_decide.add_argument("--storage", default="pg", help="pg（默认）或 memory")
    p_decide.add_argument("--id", help="节点 id（与 --verdict 同用，写一条复审标注）")
    p_decide.add_argument("--verdict", choices=VERDICTS,
                          help="still_valid | changed | stale | browse")
    p_decide.add_argument("--list", action="store_true",
                          help="列出当前 due 复审条目（默认行为，可省略）")
    p_decide.add_argument("--json", action="store_true", help="输出 JSON")

    p_archive = sub.add_parser(
        "archive", help="导入语料批量归档（D2：移出调度回路，不写标注埋点）")
    p_archive.add_argument("--storage", default="pg", help="pg（默认）或 memory")
    p_archive.add_argument("--corpus", action="store_true",
                           help="按导入语料派生特征批量归档")
    p_archive.add_argument("--dry-run", action="store_true", help="只预览命中，不写库")
    p_archive.add_argument("--json", action="store_true", help="输出 JSON")

    p_embed = sub.add_parser(
        "embed", help="补齐节点 embedding 双列（全轨、幂等、空正文用标题兜底）")
    p_embed.add_argument("--storage", default="pg", help="pg（默认）或 memory")
    p_embed.add_argument("--dry-run", action="store_true", help="只统计缺口，不编码不写库")
    p_embed.add_argument("--json", action="store_true", help="输出 JSON 供管道消费")
    return ap


def parse_args(argv=None) -> argparse.Namespace:
    """公开解析入口（供测试注入 argv）。"""
    return _make_parser().parse_args(argv)


def dispatch(args: argparse.Namespace, store=None, encoders=None) -> int:
    """命令分发核心。store / encoders 可注入（单测用内存后端与 fake encoder）。"""
    store = store or get_storage(args.storage)

    if args.command == "daily":
        obs = record_daily_observation_auto(store)
        print(f"=== ZKC daily（真值收口）@ {datetime.now(timezone.utc).isoformat()} ===")
        print(f"  pushed={obs.get('pushed')} queue_remaining={obs.get('queue_remaining')} "
              f"completed={obs.get('completed')} labeled={obs.get('labeled_completed')}")
        return 0

    if args.command == "meter":
        r = build_report(args.storage, storage=store)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
        else:
            format_human(r)
        return 0

    if args.command == "p64":
        r = build_p64_report(args.storage, storage=store)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
        else:
            format_p64_human(r)
        return 0

    if args.command == "decide":
        if args.list or not (args.id and args.verdict):
            # 默认 / 显式：列 due 条目（供 harness 在对话里呈现给人）
            view = review_queue_view(store)
            if args.json:
                print(json.dumps(view, ensure_ascii=False, indent=2, default=str))
            else:
                print(f"=== ZKC decide · 待复审队列（{view['due_count']} 条）===")
                for it in view["items"]:
                    print(f"  - {it['id']}  [{it['track']}] {it['title']}")
                    print(f"      decay={it['decay_score']} "
                          f"节奏={it['review_interval_days']}d ({it['interval_source']}) "
                          f"last={it['last_reviewed_at']}")
                g = view["gate"]
                print(f"\n  标注率闸门: {g.get('gate')} (rate={g.get('rate')})  "
                      f"预算: {view['budget'].get('estimate')} "
                      f"({view['budget'].get('confidence')})")
            return 0
        # --id + --verdict 齐备：写一条复审标注（human-in-loop，verdict 必来自人）
        res = decide_review(store, args.id, args.verdict)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"=== ZKC decide {args.id} → {args.verdict} ===")
            print(f"  verdict={res.get('verdict')} applied={res.get('applied')} "
                  f"new_interval_days={res.get('new_interval_days')}")
            print(f"  reason={res.get('reason')}")
            to = res.get("today_observation") or {}
            print(f"  今日观测: completed={to.get('completed')} "
                  f"labeled={to.get('labeled_completed')}")
        return 0

    if args.command == "archive":
        if not args.corpus:
            print("archive 目前只支持 --corpus（按导入语料派生特征批量归档）",
                  file=sys.stderr)
            return 2
        from zkc.corpus import archive_corpus

        result = archive_corpus(store, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"=== ZKC archive · {result['action']} ===")
            print(f"  matched={result['matched']} archived={result['archived']} "
                  f"dry_run={result['dry_run']}")
            print(f"  labeled_touched={result['labeled_touched']} "
                  f"review_queue_resolved={result['review_queue_resolved']}")
        return 0

    if args.command == "embed":
        from zkc.embedding_backfill import backfill_embeddings, make_default_encoders

        result = backfill_embeddings(
            store, encoders=encoders or make_default_encoders(),
            dry_run=args.dry_run,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"=== ZKC embed · 双列补齐（dry_run={result['dry_run']}）===")
            print(f"  scanned={result['scanned']} "
                  f"archived_skipped={result['archived_skipped']} "
                  f"gap_nodes={result['gap_nodes']} "
                  f"gap_columns={result['gap_columns']} "
                  f"unique_texts={result['unique_texts']}")
            print(f"  encoded={result['encoded']} "
                  f"columns_written={result['columns_written']}")
            if not result["columns_written"]:
                print("  已是全覆盖，无需写入（幂等）")
        return 0

    return 2  # 兜底（argparse required 已拦截未知命令）


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        return dispatch(args)
    except Exception as e:  # noqa: BLE001 — CLI 顶层：任何错都转非零退出码
        print(f"zkc error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
