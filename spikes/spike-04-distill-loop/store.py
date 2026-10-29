"""Postgres access for spike 04 (pgvector/pg16 docker, published on 55433)."""
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

DSN = os.environ.get("ZKC_PG_DSN", "postgresql://postgres:zkc@localhost:55433/zkc")
SPIKE01_SCHEMA = Path(__file__).resolve().parent.parent / "spike-01-dual-track-decay" / "schema.sql"
SCHEMA_EXT = Path(__file__).resolve().parent / "schema_ext.sql"


def connect() -> psycopg.Connection:
    return psycopg.connect(DSN)


def apply_schema() -> None:
    """Apply spike-01 base schema (only if absent) then the spike-04 extension.

    Both steps are idempotent: the extension uses IF NOT EXISTS throughout.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('node')")
        if cur.fetchone()[0] is None:
            cur.execute(SPIKE01_SCHEMA.read_text())
        cur.execute(SCHEMA_EXT.read_text())


def insert_node(cur, title: str, content: str, track: str = "static") -> str:
    cur.execute(
        "INSERT INTO node (track, title, content) VALUES (%s, %s, %s) RETURNING id",
        (track, title, content),
    )
    return str(cur.fetchone()[0])


def persist_distill(cur, source_ids: list[str], claim: dict) -> tuple[str, str]:
    """Write one distillation product set: transform row + claim + reverse-link edge.

    All products carry produced_by (acceptance constraint 2).
    """
    cur.execute(
        "INSERT INTO transform (kind, params) VALUES ('distill', %s) RETURNING id",
        (Jsonb({"source_ids": source_ids}),),
    )
    t_id = str(cur.fetchone()[0])

    cur.execute(
        """INSERT INTO meta_claim
             (statement, level, confidence, evidence_refs, produced_by)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (
            claim["statement"], claim["level"], claim["confidence"],
            [sid for sid in source_ids], t_id,
        ),
    )
    c_id = str(cur.fetchone()[0])

    # distillation provenance also yields reverse links between source nodes
    if len(source_ids) >= 2:
        cur.execute(
            "INSERT INTO edge (src, dst, kind, produced_by) VALUES (%s, %s, 'reverse_link', %s)",
            (source_ids[0], source_ids[1], t_id),
        )
    return t_id, c_id


def revise_claim(cur, old_id: str, edits: dict) -> str:
    """Append-only revision: close the old row's tx_to, insert a new row.

    Content columns of the history row are NEVER rewritten (acceptance constraint 1).
    """
    cur.execute("SELECT statement, level, confidence, evidence_refs, produced_by FROM meta_claim WHERE id = %s", (old_id,))
    statement, level, confidence, evidence, produced_by = cur.fetchone()

    merged = {
        "statement": edits.get("statement", statement),
        "level": edits.get("level", level),
        "confidence": edits.get("confidence", confidence),
    }
    cur.execute(
        "UPDATE meta_claim SET tx_to = now() WHERE id = %s AND tx_to IS NULL",  # closure only
        (old_id,),
    )
    cur.execute(
        """INSERT INTO meta_claim
             (statement, level, confidence, evidence_refs, produced_by, revises)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (merged["statement"], merged["level"], merged["confidence"], evidence, produced_by, old_id),
    )
    return str(cur.fetchone()[0])


def discard_transform(cur, transform_id: str) -> dict:
    """Revert a transform: cascading delete removes every product it made."""
    cur.execute("SELECT count(*) FROM meta_claim WHERE produced_by = %s", (transform_id,))
    claims_before = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM edge WHERE produced_by = %s", (transform_id,))
    edges_before = cur.fetchone()[0]
    cur.execute("DELETE FROM transform WHERE id = %s", (transform_id,))
    return {"claims_removed": claims_before, "edges_removed": edges_before}
