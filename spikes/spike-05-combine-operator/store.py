"""Postgres access for spike 05 (same DSN/db as spike 04: zkc on 55433)."""
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
    """Idempotent: spike-01 base (if absent) + spike-04 ext + spike-05 ext."""
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


def persist_combine(cur, source_ids: list[str], artifact: dict) -> tuple[str, str]:
    """Persist one combine product set: transform + artifact + chained reverse links."""
    cur.execute(
        "INSERT INTO transform (kind, params) VALUES ('combine', %s) RETURNING id",
        (Jsonb({"source_ids": source_ids}),),
    )
    t_id = str(cur.fetchone()[0])

    cur.execute(
        """INSERT INTO modeling_artifact
             (title, kind, body, evidence_refs, produced_by)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (
            artifact["title"], artifact["kind"], Jsonb(artifact),
            list(artifact["evidence_refs"]), t_id,
        ),
    )
    a_id = str(cur.fetchone()[0])

    # reverse links chaining the fused sources (attributable to the transform)
    for a, b in zip(source_ids, source_ids[1:]):
        cur.execute(
            "INSERT INTO edge (src, dst, kind, produced_by) VALUES (%s, %s, 'reverse_link', %s)",
            (a, b, t_id),
        )
    return t_id, a_id


def revise_artifact(cur, old_id: str, edits: dict) -> str:
    """Append-only revision: close old row (tx_to only), insert new row."""
    cur.execute(
        "SELECT title, kind, body, evidence_refs, produced_by FROM modeling_artifact WHERE id = %s",
        (old_id,),
    )
    title, kind, body, evidence, produced_by = cur.fetchone()
    merged = dict(body)
    for k in ("title", "kind"):
        if k in edits:
            merged[k] = edits[k]
    cur.execute(
        "UPDATE modeling_artifact SET tx_to = now() WHERE id = %s AND tx_to IS NULL",
        (old_id,),
    )
    cur.execute(
        """INSERT INTO modeling_artifact
             (title, kind, body, evidence_refs, produced_by, revises)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (merged.get("title", title), merged.get("kind", kind), Jsonb(merged),
         evidence, produced_by, old_id),
    )
    return str(cur.fetchone()[0])


def discard_transform(cur, transform_id: str) -> dict:
    """Revert a transform: cascade removes artifact + its edges, nothing else."""
    cur.execute("SELECT count(*) FROM modeling_artifact WHERE produced_by = %s", (transform_id,))
    artifacts_before = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM edge WHERE produced_by = %s", (transform_id,))
    edges_before = cur.fetchone()[0]
    cur.execute("DELETE FROM transform WHERE id = %s", (transform_id,))
    return {"artifacts_removed": artifacts_before, "edges_removed": edges_before}
