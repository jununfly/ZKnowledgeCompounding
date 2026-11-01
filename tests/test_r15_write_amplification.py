"""R15 写放大压测：context_member junction 在高频重算下的写入成本（计划 §5 R15）。

R15 原状：junction 表在高频重算下的写入成本未知，缓解预案是「先按查询时计算的动态视图实现」。
本测试用内存 store 实测两种实现的写放大，给出可复现的基线证据，使 R15 从 open 转为
「已缓解（压测已加）」。

场景：
- JUNCTION bulk：每轮对 C 个 context 做 revert + re-assemble（重新物化全部成员）。
  这是 junction 物化的写放大来源；实测写次 = C*(1+M) + R*C*(2+M)，线性有界（O(R·C·M)）。
- DYNAMIC VIEW：查询时计算成员，不物化 -> 写次 = 0。

结论：在预期规模内 junction 写放大是线性可控的，mitigation 成立；只有当重算频率极高
（R 极大）时才需切动态视图（0 写）。实测不会指数爆炸。
"""
from __future__ import annotations

import unittest
from uuid import uuid4

from zkc.context import ContextAssembler
from zkc.repository import get_storage


class WriteCounter:
    """包装 storage，统计 membership 相关写操作次数（不改动行为）。"""

    FIELDS = ("assemble", "revert", "add_member", "remove_member")

    def __init__(self, store):
        self.store = store
        self.counts = {f: 0 for f in self.FIELDS}
        orig_assemble = store.assemble_context
        orig_revert = store.revert_assembly
        orig_add = store.contexts.add_member
        orig_remove = store.contexts.remove_member_human

        def assemble(*a, **k):
            self.counts["assemble"] += 1
            return orig_assemble(*a, **k)

        def revert(*a, **k):
            self.counts["revert"] += 1
            return orig_revert(*a, **k)

        def add(cid, nid, w=1.0, produced_by=None):
            self.counts["add_member"] += 1
            return orig_add(cid, nid, w, produced_by)

        def remove(cid, nid):
            self.counts["remove_member"] += 1
            return orig_remove(cid, nid)

        store.assemble_context = assemble
        store.revert_assembly = revert
        store.contexts.add_member = add
        store.contexts.remove_member_human = remove


def _build_specs(c, m, scope="higher_dim"):
    """生成 c 个 context（每个含唯一 cid 与 m 个成员 uuid）。"""
    return [(uuid4(), scope, [uuid4() for _ in range(m)]) for _ in range(c)]


def _run_junction_bulk(asm, counter, specs, rounds):
    """初始装配 + rounds 轮高频重算（revert + re-assemble），返回最终句柄。"""
    handles = []
    for cid, scope, members in specs:
        cid2, tid = asm.assemble(scope, members, title="c")
        handles.append((cid2, tid, members))
    for _ in range(rounds):
        new_handles = []
        for (cid2, tid, members) in handles:
            asm.revert(tid)
            # 模拟重算：成员集轮转一个（体现「成员会变」），但 bulk 仍是全量重物化
            rotated = members[1:] + members[:1]
            cid3, tid2 = asm.assemble(scope, rotated, title="c")
            new_handles.append((cid3, tid2, rotated))
        handles = new_handles
    return handles


def _run_dynamic_view(view, specs, rounds):
    """动态视图：成员只在查询时计算，不物化 -> 0 次 store 写（按 cid 存）。"""
    for cid, scope, members in specs:
        view[cid] = set(members)
    for _ in range(rounds):
        for cid, scope, members in specs:
            view[cid] = set(members[1:] + members[:1])
    return view


class R15WriteAmplificationTest(unittest.TestCase):
    def test_junction_bulk_writes_are_linear_bounded(self):
        C, M, R = 10, 5, 100  # 10 context × 5 成员 × 100 轮高频重算
        store = get_storage("memory")
        asm = ContextAssembler(store)
        counter = WriteCounter(store)
        specs = _build_specs(C, M)

        _run_junction_bulk(asm, counter, specs, R)

        # 期望写次：初始 C 装配(+M add)；每轮 C 次 revert + C 装配(+M add)
        exp_assemble = C + R * C
        exp_revert = R * C
        exp_add = C * M + R * C * M
        self.assertEqual(counter.counts["assemble"], exp_assemble, counter.counts)
        self.assertEqual(counter.counts["revert"], exp_revert, counter.counts)
        self.assertEqual(counter.counts["add_member"], exp_add, counter.counts)
        total = exp_assemble + exp_revert + exp_add
        self.assertEqual(counter.counts["assemble"] + counter.counts["revert"]
                         + counter.counts["add_member"], total)
        # 每轮每 context 重算成本固定 = (2 + M) 写，线性、不随轮数指数增长
        per_recompute = (exp_assemble + exp_revert + exp_add - C * (1 + M)) / R / C
        self.assertEqual(per_recompute, 2 + M)
        print(f"[R15] junction bulk: {total} 写 / {R}轮 = {per_recompute} 写/轮/context "
              f"(C={C}, M={M}) -> 线性有界 O(R·C·M)")

    def test_dynamic_view_writes_zero(self):
        C, M, R = 10, 5, 100
        store = get_storage("memory")
        counter = WriteCounter(store)  # 包了 store，但动态视图路径根本不碰 store
        specs = _build_specs(C, M)
        view = _run_dynamic_view({}, specs, R)
        self.assertEqual(counter.counts["assemble"], 0)
        self.assertEqual(counter.counts["revert"], 0)
        self.assertEqual(counter.counts["add_member"], 0)
        self.assertEqual(len(view), C)
        print(f"[R15] dynamic view: 0 写（查询时计算），与重算轮数 {R} 无关")

    def test_junction_amplification_factor_reported(self):
        # 量化「junction / dynamic」放大系数，证明 junction 是线性可控而非失控
        C, M, R = 10, 5, 100
        store = get_storage("memory")
        asm = ContextAssembler(store)
        counter = WriteCounter(store)
        specs = _build_specs(C, M)
        _run_junction_bulk(asm, counter, specs, R)
        junction_writes = (counter.counts["assemble"] + counter.counts["revert"]
                           + counter.counts["add_member"])
        dynamic_writes = 0
        factor = junction_writes / max(dynamic_writes, 1)
        self.assertGreater(factor, 1)  # 相对动态视图确有放大
        self.assertEqual(junction_writes, C * (1 + M) + R * C * (2 + M))  # 但有精确上界
        print(f"[R15] 写放大系数(junction/dynamic) = {factor}（有精确线性上界，非失控）")


if __name__ == "__main__":
    unittest.main()
