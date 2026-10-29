"""End-to-end demo of the spike-04 distillation loop.

Stages printed: extract (Instructor+Ollama) -> interrupt (human review) ->
resume with edit -> persist (PG, produced_by provenance) -> (optional) revert.
"""
import uuid

from store import apply_schema, connect, discard_transform, insert_node
from distill_graph import distill_graph, resume_distill, start_distill

SOURCES = [
    ("MVCC 原理", "MVCC 通过事务 ID 与快照实现一致性读，写不阻塞读，代价是旧版本行需要清理。"),
    ("索引写入放大", "每个二级索引都会放大写入成本：一次写入变成 N 次索引维护。"),
    ("批量导入先删索引", "大批量导入时先删索引再重建，比边写边维护快一个量级。"),
]


def main() -> None:
    apply_schema()
    sources = []
    with connect() as conn, conn.cursor() as cur:
        for title, content in SOURCES:
            nid = insert_node(cur, title, content)
            sources.append({"id": nid, "title": title, "content": content})

    thread = f"demo-{uuid.uuid4().hex[:8]}"
    with distill_graph() as g:
        print("== stage 1: extract (Instructor + Ollama) -> interrupt ==")
        result = start_distill(g, thread, sources)
        draft = result["__interrupt__"][0].value["draft"]
        print(f"   draft.statement : {draft['statement']}")
        print(f"   draft.level     : {draft['level']}  confidence={draft['confidence']}")
        print(f"   draft.topic     : {draft['topic']}")
        print("   (graph paused; checkpoint lives in PG — process could die here)")

        print("== stage 2: human review -> resume WITH edit ==")
        result = resume_distill(g, thread, {
            "approved": True,
            "edits": {"statement": f"（人审修正）{draft['statement']}"},
        })

    print(f"== stage 3: persisted ==")
    print(f"   transform_id : {result['transform_id']}")
    print(f"   claim_id     : {result['claim_id']}")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT c.statement, c.level, c.confidence, t.kind
               FROM meta_claim c JOIN transform t ON t.id = c.produced_by
               WHERE c.id = %s""",
            (result["claim_id"],),
        )
        stmt, level, conf, kind = cur.fetchone()
        print(f"   statement    : {stmt}")
        print(f"   level={level}  confidence={conf}  produced_by transform({kind})")
        cur.execute("SELECT count(*) FROM edge WHERE produced_by = %s", (result["transform_id"],))
        print(f"   reverse-link edges produced: {cur.fetchone()[0]}")

        print("== stage 4: discard transform -> cascade revert ==")
        stats = discard_transform(cur, result["transform_id"])
        print(f"   reverted: {stats}")


if __name__ == "__main__":
    main()
