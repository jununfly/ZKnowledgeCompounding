"""Postgres access for spike 09 (automatic review_interval assignment).

Reuses the spike-01 base schema + spike-04..08 extensions (single substrate).
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

DSN = os.environ.get("ZKC_PG_DSN", "postgresql://postgres:zkc@localhost:55433/zkc")
_HERE = Path(__file__).resolve().parent
SPIKE01 = _HERE.parent / "spike-01-dual-track-decay" / "schema.sql"
SPIKE04 = _HERE.parent / "spike-04-distill-loop" / "schema_ext.sql"
SPIKE05 = _HERE.parent / "spike-05-combine-operator" / "schema_ext.sql"
SPIKE06 = _HERE.parent / "spike-06-context-assembly" / "schema_ext.sql"
SPIKE07 = _HERE.parent / "spike-07-compounding-metrics" / "schema_ext.sql"
SPIKE08 = _HERE.parent / "spike-08-expiry-routing" / "schema_ext.sql"
SCHEMA_EXT = _HERE / "schema_ext.sql"
SCHEMA_BUDGET = _HERE / "schema_ext_budget.sql"


def connect() -> psycopg.Connection:
    return psycopg.connect(DSN)


def apply_schema() -> None:
    """Idempotent: base + all prior ext + our own interval columns/audit table."""
    with connect() as conn, conn.cursor() as cur:
        for tbl, path in [
            ("node", SPIKE01),
            ("transform", SPIKE04),
            ("modeling_artifact", SPIKE05),
            ("context_member", SPIKE06),
            ("citation", SPIKE07),
            ("review_queue", SPIKE08),
        ]:
            cur.execute(f"SELECT to_regclass('{tbl}')")
            if cur.fetchone()[0] is None:
                cur.execute(path.read_text())
        cur.execute("SELECT to_regclass('interval_adjustment')")
        if cur.fetchone()[0] is None:
            cur.execute(SCHEMA_EXT.read_text())
        cur.execute("SELECT to_regclass('attention_observation')")
        if cur.fetchone()[0] is None:
            cur.execute(SCHEMA_BUDGET.read_text())
        else:
            # slice-B migration: `labeled_completed` (D8) was added after the table had
            # already been created by an earlier run. Idempotent, matching the spike's
            # "schema files are the source of truth, re-runnable" convention.
            cur.execute("ALTER TABLE attention_observation ADD COLUMN IF NOT EXISTS "
                        "labeled_completed int NOT NULL DEFAULT 0")
            # (Postgres has no ADD CONSTRAINT IF NOT EXISTS, so guard explicitly.)
            cur.execute("SELECT 1 FROM pg_constraint WHERE conname='labeled_le_completed'")
            if cur.fetchone() is None:
                cur.execute("ALTER TABLE attention_observation "
                            "ADD CONSTRAINT labeled_le_completed "
                            "CHECK (labeled_completed <= completed)")


def truncate_all(cur) -> None:
    cur.execute(
        "TRUNCATE node, meta_claim, edge, context, context_member, transform, "
        "modeling_artifact, citation, review_queue, interval_adjustment, "
        "attention_observation RESTART IDENTITY CASCADE"
    )


def days_to_interval(days):
    return None if days is None else timedelta(days=float(days))


def interval_to_days(value):
    """psycopg maps PG `interval` -> timedelta; keep float days as the working unit."""
    if value is None:
        return None
    return value.total_seconds() / 86400.0


def insert_node(cur, title: str, content: str, track: str = "static",
                decay_score: float = 0.0, review_interval=None,
                interval_source: str = "auto", archived: bool = False) -> str:
    arch = datetime.now(timezone.utc) if archived else None
    cur.execute(
        "INSERT INTO node (track, title, content, decay_score, review_interval, "
        "interval_source, archived_at) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (track, title, content, decay_score,
         days_to_interval(review_interval), interval_source, arch),
    )
    return str(cur.fetchone()[0])


def insert_claim(cur, statement: str, level: str, evidence_refs: list,
                 produced_by=None) -> str:
    cur.execute(
        "INSERT INTO meta_claim (statement, level, evidence_refs, produced_by) "
        "VALUES (%s,%s,%s,%s) RETURNING id",
        (statement, level, evidence_refs, produced_by),
    )
    return str(cur.fetchone()[0])


def insert_edge(cur, src: str, dst: str, kind: str) -> None:
    cur.execute("INSERT INTO edge (src, dst, kind) VALUES (%s,%s,%s)", (src, dst, kind))


def insert_context(cur, scope: str, title: str) -> str:
    cur.execute(
        "INSERT INTO context (scope, title) VALUES (%s,%s) RETURNING id",
        (scope, title),
    )
    return str(cur.fetchone()[0])


def add_member(cur, context_id: str, node_id: str) -> None:
    cur.execute(
        "INSERT INTO context_member (context_id, node_id) VALUES (%s,%s) "
        "ON CONFLICT DO NOTHING",
        (context_id, node_id),
    )


def new_transform(cur, kind: str, params: dict) -> str:
    from psycopg.types.json import Jsonb
    cur.execute(
        "INSERT INTO transform (kind, params) VALUES (%s,%s) RETURNING id",
        (kind, Jsonb(params)),
    )
    return str(cur.fetchone()[0])


def seed_interval(cur) -> dict:
    """Deterministic scenario for the test suite.

    Expected baselines (see interval_policy.BASELINE_*):
      s1 static                                  -> None
      d1 "下周三前提交" + self_loop member       -> 7   (explicit horizon wins)
      d2 self_loop member, no horizon            -> 3
      d3 higher_dim member                       -> 14
      d4 orphan dynamic                          -> 7
      d5 captured (evidence of claim c1)         -> 28
      d6 "3 天内跟进"                            -> 3
      d7 orphan + interval_source='human'        -> baseline 7, immune to auto-scaling
    """
    s1 = insert_node(cur, "S1", "static anchor", "static")

    proj = insert_context(cur, "self_loop", "项目 A")
    topic = insert_context(cur, "higher_dim", "主题 B")

    d1 = insert_node(cur, "D1", "下周三前提交评审材料", "dynamic", decay_score=0.2)
    d2 = insert_node(cur, "D2", "项目 A 的当前阻塞点", "dynamic", decay_score=0.2)
    d3 = insert_node(cur, "D3", "主题 B 的长期观察", "dynamic", decay_score=0.2)
    d4 = insert_node(cur, "D4", "一段随手记的灵感", "dynamic", decay_score=0.2)
    d5 = insert_node(cur, "D5", "已被提炼过的记录", "dynamic", decay_score=0.2)
    d6 = insert_node(cur, "D6", "3 天内跟进反馈", "dynamic", decay_score=0.2)
    d7 = insert_node(cur, "D7", "人工固定节奏的条目", "dynamic", decay_score=0.2,
                     review_interval=10, interval_source="human")

    add_member(cur, proj, d1)
    add_member(cur, proj, d2)
    add_member(cur, topic, d3)

    c1 = insert_claim(cur, "D5 的结论已被提炼", "insight", [d5])
    insert_edge(cur, s1, d5, "derived_from")

    return dict(s1=s1, d1=d1, d2=d2, d3=d3, d4=d4, d5=d5, d6=d6, d7=d7, c1=c1,
                proj=proj, topic=topic)
