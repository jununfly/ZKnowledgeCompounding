"""Postgres access for spike 07 (compounding metrics, T7.1 + T6.2 citation instrumentation)."""
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

DSN = os.environ.get("ZKC_PG_DSN", "postgresql://postgres:zkc@localhost:55433/zkc")
_HERE = Path(__file__).resolve().parent
SPIKE01_SCHEMA = _HERE.parent / "spike-01-dual-track-decay" / "schema.sql"
SPIKE04_EXT = _HERE.parent / "spike-04-distill-loop" / "schema_ext.sql"
SPIKE05_EXT = _HERE.parent / "spike-05-combine-operator" / "schema_ext.sql"
SCHEMA_EXT = _HERE / "schema_ext.sql"

# mirror architecture §6.3
ROT_THRESHOLD = 0.9


def connect() -> psycopg.Connection:
    return psycopg.connect(DSN)


def apply_schema() -> None:
    """Idempotent: spike-01 base + spike-04 ext + spike-05 ext + spike-07 ext."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('node')")
        if cur.fetchone()[0] is None:
            cur.execute(SPIKE01_SCHEMA.read_text())
        cur.execute("SELECT to_regclass('transform')")
        if cur.fetchone()[0] is None:
            cur.execute(SPIKE04_EXT.read_text())
        cur.execute("SELECT to_regclass('modeling_artifact')")
        if cur.fetchone()[0] is None:
            cur.execute(SPIKE05_EXT.read_text())
        cur.execute(SCHEMA_EXT.read_text())


def truncate_all(cur) -> None:
    cur.execute(
        "TRUNCATE node, meta_claim, edge, context, context_member, "
        "transform, modeling_artifact, citation RESTART IDENTITY CASCADE"
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


def insert_transform(cur, kind: str, params: dict = None) -> str:
    cur.execute(
        "INSERT INTO transform (kind, params) VALUES (%s,%s) RETURNING id",
        (kind, Jsonb(params or {})),
    )
    return str(cur.fetchone()[0])


def insert_artifact(cur, title: str, kind: str, body: dict,
                   evidence_refs: list, produced_by: str) -> str:
    cur.execute(
        "INSERT INTO modeling_artifact (title, kind, body, evidence_refs, produced_by) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (title, kind, Jsonb(body), evidence_refs, produced_by),
    )
    return str(cur.fetchone()[0])


def insert_edge(cur, src: str, dst: str, kind: str) -> None:
    cur.execute(
        "INSERT INTO edge (src, dst, kind) VALUES (%s,%s,%s)",
        (src, dst, kind),
    )


def insert_citation(cur, citing_node_id: str, cited_claim_id: str,
                    produced_by=None) -> str:
    cur.execute(
        "INSERT INTO citation (citing_node_id, cited_claim_id, produced_by) "
        "VALUES (%s,%s,%s) RETURNING id",
        (citing_node_id, cited_claim_id, produced_by),
    )
    return str(cur.fetchone()[0])


def seed_scenario(cur) -> dict:
    """Deterministic scenario used by the test suite.

    Yields the following expected metrics:
      - dynamic nodes: d1(d1 decay .95, archived), d2(.95 leaked), d3(.20 cites c1), d4(.20 isolated)
      - connection_density = 1/4 = 0.25   (only d1 has a reverse_link edge)
      - reuse_rate        = 1/2 = 0.5    (c1 cited by d3; c2 never cited)
      - methodology_output = 1           (one combine artifact over s1,s2)
      - decay_controllability = 1/2 = 0.5 (d1 handled via archive; d2 leaked)
      - compounding_factor (equal weights, method_target=10) = (0.25+0.5+0.1+0.5)/4 = 0.3375
    """
    s1 = insert_node(cur, "S1", "static one", "static")
    s2 = insert_node(cur, "S2", "static two", "static")
    d1 = insert_node(cur, "D1", "expired+archived", "dynamic", decay_score=0.95, archived=True)
    d2 = insert_node(cur, "D2", "expired+leaked", "dynamic", decay_score=0.95)
    d3 = insert_node(cur, "D3", "fresh+cites", "dynamic", decay_score=0.20)
    d4 = insert_node(cur, "D4", "fresh+isolated", "dynamic", decay_score=0.20)
    c1 = insert_claim(cur, "claim one", "fact", [s1])
    c2 = insert_claim(cur, "claim two", "fact", [s2])
    insert_edge(cur, s1, d1, "reverse_link")      # d1 connected
    insert_citation(cur, d3, c1)                  # c1 reused by d3
    t = insert_transform(cur, "combine")
    insert_artifact(cur, "artifact A", "methodology", {"x": 1}, [s1, s2], t)
    return dict(s1=s1, s2=s2, d1=d1, d2=d2, d3=d3, d4=d4, c1=c1, c2=c2)
