"""Postgres access for spike 08 (expiry routing: distill vs archive vs abstain).

Reuses the spike-01 base schema + spike-04/05/06/07 extensions (single substrate).
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg

DSN = os.environ.get("ZKC_PG_DSN", "postgresql://postgres:zkc@localhost:55433/zkc")
_HERE = Path(__file__).resolve().parent
SPIKE01 = _HERE.parent / "spike-01-dual-track-decay" / "schema.sql"
SPIKE04 = _HERE.parent / "spike-04-distill-loop" / "schema_ext.sql"
SPIKE05 = _HERE.parent / "spike-05-combine-operator" / "schema_ext.sql"
SPIKE06 = _HERE.parent / "spike-06-context-assembly" / "schema_ext.sql"
SPIKE07 = _HERE.parent / "spike-07-compounding-metrics" / "schema_ext.sql"
SCHEMA_EXT = _HERE / "schema_ext.sql"

# mirror architecture §6.3
ROT_THRESHOLD = 0.9


def connect() -> psycopg.Connection:
    return psycopg.connect(DSN)


def apply_schema() -> None:
    """Idempotent: base + all prior ext + our own review_queue."""
    with connect() as conn, conn.cursor() as cur:
        for tbl, path in [
            ("node", SPIKE01),
            ("transform", SPIKE04),
            ("modeling_artifact", SPIKE05),
            ("context_member", SPIKE06),
            ("citation", SPIKE07),
        ]:
            cur.execute(f"SELECT to_regclass('{tbl}')")
            if cur.fetchone()[0] is None:
                cur.execute(path.read_text())
        cur.execute("SELECT to_regclass('review_queue')")
        if cur.fetchone()[0] is None:
            cur.execute(SCHEMA_EXT.read_text())


def truncate_all(cur) -> None:
    cur.execute(
        "TRUNCATE node, meta_claim, edge, context, context_member, "
        "transform, modeling_artifact, citation, review_queue RESTART IDENTITY CASCADE"
    )


def insert_node(cur, title: str, content: str, track: str = "static",
                decay_score: float = 0.0, archived: bool = False) -> str:
    arch = datetime.now(timezone.utc) if archived else None
    cur.execute(
        "INSERT INTO node (track, title, content, decay_score, archived_at) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (track, title, content, decay_score, arch),
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
    cur.execute(
        "INSERT INTO edge (src, dst, kind) VALUES (%s,%s,%s)",
        (src, dst, kind),
    )


def seed_routing(cur) -> dict:
    """Deterministic scenario for the test suite.

    Expected routing:
      d1 expired + connected (reverse_link) + NOT captured  -> DISTILL
      d2 expired + orphan (no edges/context)                -> ABSTAIN
      d3 expired + is evidence of claim c1                  -> ARCHIVE
      d4 fresh (decay 0.20, not expired)                    -> not routable
    """
    s1 = insert_node(cur, "S1", "static anchor", "static")
    d1 = insert_node(cur, "D1", "expired connected", "dynamic", decay_score=0.95)
    d2 = insert_node(cur, "D2", "expired orphan", "dynamic", decay_score=0.95)
    d3 = insert_node(cur, "D3", "expired is-evidence", "dynamic", decay_score=0.95)
    d4 = insert_node(cur, "D4", "fresh", "dynamic", decay_score=0.20)
    c1 = insert_claim(cur, "claim grounded on D3", "fact", [d3])
    insert_edge(cur, s1, d1, "reverse_link")   # d1 has a connection, not yet captured
    return dict(s1=s1, d1=d1, d2=d2, d3=d3, d4=d4, c1=c1)
