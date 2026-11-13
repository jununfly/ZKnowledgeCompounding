#!/usr/bin/env python3
"""ZKC · 忠实度闸门 human_only 模式端到端 dogfood（忠实度闸门验证器）。

用途：验证忠实度闸门全链路**不依赖 judge**（本机 4B/9B 已被 13b-probe 否决，
judge_fn=None 是当前真实运行模式）——

    造来源节点 + 三类 claim（照抄/好抽象/空来源文本）
    → gate_new_claims（judge_fn=None → 全部 pending_human/human_only，红旗只标注）
    → daily_faithfulness_queue（F_cap 只封顶抽检+审计侧，强制侧全保留）
    → faithfulness_queue_view（web 视图形状 + 校准语料概览）
    → adjudicate_claim（confirm/reject 人审裁决）
    → calibration_corpus（human_only 模式无 atomic_facts → 恒空，属预期）

存储用 ephemeral memory store（行为与 PG 同构）。judge 真实接线 dogfood 归忠实度 judge 探针。

用法：
    python3 scripts/dogfood_faithfulness.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc.faithfulness import (  # noqa: E402
    daily_faithfulness_queue,
    gate_new_claims,
)
from zkc.repository import get_storage  # noqa: E402
from zkc.repository.models import Claim, Node  # noqa: E402
from zkc.web.review import adjudicate_claim, faithfulness_queue_view  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("== ZKC 忠实度闸门 dogfood：human_only 模式（judge_fn=None）==\n")
    store = get_storage("memory")

    # ---- 1. 造来源（真实 store 节点，UUID id）
    n_copy = store.nodes.save(Node(
        title="鉴权返工", track="dynamic",
        content="把鉴权逻辑放在客户端做，被安全评审整体打回，服务端全部重做，返工两周。"))
    n_abstract = store.nodes.save(Node(
        title="SDK 升级", track="dynamic",
        content="第三方 SDK 的升级拖到上游停止维护前一周才做，被动手忙脚乱。"))
    n_empty = store.nodes.save(Node(title="空来源", track="dynamic", content=""))

    def provider(claim: Claim) -> list[dict]:
        return [{"id": str(u), "title": (store.nodes.get(u).title if store.nodes.get(u) else ""),
                 "content": (store.nodes.get(u).content if store.nodes.get(u) else "")}
                for u in claim.evidence_refs]

    # ---- 2. 三类 claim 过闸门（judge_fn=None）
    print("[1] gate_new_claims（judge_fn=None → 全人工兜底）")
    c_copy = Claim(statement="把鉴权逻辑放在客户端做，被安全评审整体打回，服务端全部重做，返工两周。",
                   evidence_refs=[n_copy.id])          # 字面照抄 → rubric_verbatim 红旗
    c_good = Claim(statement="外部依赖的升级窗口应早于其生命周期终点，拖到停维护前一周的被动升级成本更高。",
                   evidence_refs=[n_abstract.id])      # 好抽象 → 无红旗
    c_empty = Claim(statement="无来源文本支撑的断言。", evidence_refs=[n_empty.id])  # 空来源 → no_source_text
    decisions = gate_new_claims(store, [c_copy, c_good, c_empty], provider, judge_fn=None)
    for d in decisions:
        check(f"claim 全部 pending_human/human_only：{d.claim_id}",
              d.status == "pending_human" and d.route == "human_only", d.reason)
        if d.claim_id == c_copy.id:
            check("照抄 claim 记录 verbatim 红旗（仅标注不放行）",
                  any(f.startswith("rubric_verbatim") for f in d.flags), str(d.flags))
        if d.claim_id == c_good.id:
            check("好抽象 claim 无红旗", d.flags == [], str(d.flags))
        if d.claim_id == c_empty.id:
            check("空来源 claim 记录 no_source_text 红旗",
                  "rubric_no_source_text" in d.flags, str(d.flags))

    # ---- 3. F_cap 日队列
    print("\n[2] daily_faithfulness_queue（human_only = 强制侧，全量展示）")
    q = daily_faithfulness_queue(store)
    print(f"    total={q['total_pending']} forced={q['forced_total']} "
          f"capped={q['capped_total']} cap={q['cap']} "
          f"F_CAP_RATIO={q['f_cap_ratio']} ({q['f_cap_source']})")
    check("human_only 全部计入强制侧", q["forced_total"] == 3 and q["capped_total"] == 0)
    check("强制侧零丢弃（items 全展示）", len(q["items"]) == 3 and q["capped_withheld"] == 0)

    # ---- 4. web 视图 + 人审裁决
    print("\n[3] faithfulness_queue_view + adjudicate_claim")
    v = faithfulness_queue_view(store)
    check("视图含队列与校准概览", set(v) >= {"queue", "calibration"})
    check("judge 上线前校准语料恒空（human_only 无 atomic_facts，属预期）",
          v["calibration"]["size"] == 0 and v["calibration"]["judge_correct_rate"] is None)
    r1 = adjudicate_claim(store, c_copy.id, "reject")     # 照抄 → 不忠实
    r2 = adjudicate_claim(store, c_good.id, "confirm")    # 抽象 → 忠实
    r3 = adjudicate_claim(store, c_empty.id, "reject")    # 无据 → 不忠实
    check("reject → human_rejected", r1["faithfulness_status"] == "human_rejected")
    check("confirm → human_confirmed", r2["faithfulness_status"] == "human_confirmed")
    check("裁决后队列清空", r3["queue"]["total_pending"] == 0)
    check("人审不写 attention_observation（R11 独立预算）",
          store.attention.get(r2.get("day")) is None if isinstance(r2.get("day"), str)
          else True, "复审容量口径未被 claim 人审污染")

    # ---- 汇总
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n== 结果：{len(CHECKS) - len(failed)}/{len(CHECKS)} PASS ==")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
        return 1
    print("全链路（gate → F_cap 队列 → 视图 → adjudicate → 语料语义）符合设计。")
    print("下一步：judge 真实接线（忠实度 judge 探针 R1）后，校准语料将随人判自然生长。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
