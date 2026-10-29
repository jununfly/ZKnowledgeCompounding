"""Postgres access for spike 06 (same DSN/db as spike 04/05: zkc on 55433)."""
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

DSN = os.environ.get("ZKC_PG_DSN", "postgresql://postgres:zkc@localhost:55433/zkc")
_HERE = Path(__file__).resolve().parent
SPIKE01_SCHEMA = _HERE.parent / "spike-01-dual-track-decay" / "schema.sql"
SPIKE04_EXT = _HERE.parent / "spike-04-distill-loop" / "schema_ext.sql"
SCHEMA_EXT = _HERE / "schema_ext.sql"


def connect() -> psycopg.Connection:
    return psycopg.connect(DSN)


def apply_schema() -> None:
    """Idempotent: spike-01 base (if absent) + spike-04 ext (if absent) + spike-06 ext."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('node')")
        if cur.fetchone()[0] is None:
            cur.execute(SPIKE01_SCHEMA.read_text())
        cur.execute("SELECT to_regclass('transform')")
        if cur.fetchone()[0] is None:
            cur.execute(SPIKE04_EXT.read_text())
        cur.execute(SCHEMA_EXT.read_text())


def insert_node(cur, title: str, content: str, track: str = "static") -> str:
    cur.execute(
        "INSERT INTO node (track, title, content) VALUES (%s, %s, %s) RETURNING id",
        (track, title, content),
    )
    return str(cur.fetchone()[0])


def insert_node_vec(cur, title: str, content: str, vec_str: str, track: str = "static") -> str:
    """Insert a node with a deterministic synthetic 1024-d embedding (for discovery tests)."""
    cur.execute(
        "INSERT INTO node (track, title, content, embedding) VALUES (%s, %s, %s, %s::vector) RETURNING id",
        (track, title, content, vec_str),
    )
    return str(cur.fetchone()[0])


def discard_assembly(cur, transform_id: str) -> dict:
    """Revert an assembly transform: cascade removes its context + members (FK CASCADE)."""
    cur.execute("SELECT count(*) FROM context WHERE produced_by = %s", (transform_id,))
    contexts_before = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM context_member WHERE produced_by = %s", (transform_id,))
    members_before = cur.fetchone()[0]
    cur.execute("DELETE FROM transform WHERE id = %s", (transform_id,))
    return {"contexts_removed": contexts_before, "members_removed": members_before}
