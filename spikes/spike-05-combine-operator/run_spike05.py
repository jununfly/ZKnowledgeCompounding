"""End-to-end demo of the spike-05 combine operator.

Prints the full funnel report and the modeling artifact so a human can evaluate
the §9 acceptance question: 是否真形成方法论，而非摘要堆砌？
"""
import uuid

from combine_op import CombineOperator
from store import apply_schema, connect, discard_transform, insert_node, persist_combine

SOURCES = [
    ("MVCC 一致性读", "MVCC 用事务 ID 与快照实现一致性读，写不阻塞读，旧版本行需要后台清理。"),
    ("索引写入放大", "每个二级索引都会放大写入成本：一次写入变成 N 次索引维护。"),
    ("批量导入先删索引", "大批量导入前删掉二级索引、导完再重建，比边写边维护快一个量级。"),
    ("长事务危害", "长事务阻止旧版本清理，导致表膨胀，进而拖垮读写性能。"),
    ("VACUUM 调参", "autovacuum 参数过保守时清理跟不上产生速度，表与索引持续膨胀。"),
]

QUERY = "PostgreSQL 写放大、一致性读与表膨胀如何互相牵制？给出可操作的方法论"


def main() -> None:
    apply_schema()
    with connect() as conn, conn.cursor() as cur:
        sources = [
            {"id": insert_node(cur, t, c), "title": t, "content": c}
            for t, c in SOURCES
        ]

    op = CombineOperator(max_sources=4)
    result = op.combine(QUERY, sources)

    print("== RCS 漏斗报告 ==")
    for k in result["report"]["kept"]:
        print(f"  [keep {k['score']:.2f}] {k['title']}：{k['summary']}")
    for k in result["report"]["dropped"]:
        print(f"  [drop {k['score']:.2f}] {k['title']}")
    print(f"  dropped_claims(引用无效被删): {result['artifact'].get('_dropped_claims', 0)}")

    a = result["artifact"]
    print(f"\n== 建模产物（kind={a['kind']}）==")
    print(f"标题: {a['title']}")
    print("claims:")
    for c in a["claims"]:
        print(f"  - ({c['level']}, conf={c['confidence']}) {c['statement']}")
        print(f"    evidence: {[e[:8] for e in c['evidence_ids']]}")
    print("local:")
    for s in a.get("local") or []:
        print(f"  - {s}")
    print("global:")
    for s in a.get("global_insights") or a.get("global") or []:
        print(f"  - {s}")
    if not (a.get("local") and (a.get("global_insights") or a.get("global"))):
        print("  ⚠️ 双层有空层 —— 蒸馏不足的质量信号（1.5B 模型已知短板）")
    if a.get("methodology_steps"):
        print("methodology steps:")
        for i, s in enumerate(a["methodology_steps"], 1):
            print(f"  {i}. {s}")

    with connect() as conn, conn.cursor() as cur:
        t_id, a_id = persist_combine(cur, result["report"]["kept_ids"], a)
        print(f"\n== 已落库 == transform={t_id}  artifact={a_id}")
        stats = discard_transform(cur, t_id)
        print(f"== 演示级联撤销 == {stats}（真实使用中不撤销，仅验证机制）")


if __name__ == "__main__":
    main()
