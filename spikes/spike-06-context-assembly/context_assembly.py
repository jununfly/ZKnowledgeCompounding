"""Context topology assembly operator (spike 06).

T4.1 (discovery): given a seed node, find its nearest neighbours by embedding similarity
and propose a higher_dim context from the seed + neighbours.
T4.2 (membership): model membership as a junction table (context_member) carrying
produced_by (for cascade-undo) + weight (soft membership). An assembly transform
produces ONE context + its member rows; reverting the transform cascades both away.
"""
from psycopg.types.json import Jsonb


class ContextAssembly:
    def create_context(self, cur, scope: str, title: str | None = None,
                       produced_by: str | None = None) -> str:
        cur.execute(
            "INSERT INTO context (scope, title, produced_by) VALUES (%s, %s, %s) RETURNING id",
            (scope, title, produced_by),
        )
        return str(cur.fetchone()[0])

    def assemble(self, cur, scope: str, node_ids: list[str], title: str | None = None,
                 weight: float = 1.0) -> tuple[str, str]:
        """One assembly transform -> one context + one membership row per node."""
        if scope not in ("self_loop", "higher_dim"):
            raise ValueError(f"invalid scope: {scope}")
        cur.execute(
            "INSERT INTO transform (kind, params) VALUES ('context_assembly', %s) RETURNING id",
            (Jsonb({"scope": scope, "node_ids": node_ids}),),
        )
        t_id = str(cur.fetchone()[0])
        c_id = self.create_context(cur, scope, title, produced_by=t_id)
        for nid in node_ids:
            cur.execute(
                """INSERT INTO context_member (context_id, node_id, produced_by, weight)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (context_id, node_id) DO UPDATE SET produced_by = EXCLUDED.produced_by, weight = EXCLUDED.weight""",
                (c_id, nid, t_id, weight),
            )
        return c_id, t_id

    def add_member_human(self, cur, context_id: str, node_id: str, weight: float = 1.0) -> None:
        """Human-added membership: produced_by NULL, removable directly (not via transform)."""
        cur.execute(
            """INSERT INTO context_member (context_id, node_id, produced_by, weight)
               VALUES (%s, %s, NULL, %s)
               ON CONFLICT (context_id, node_id) DO UPDATE SET weight = EXCLUDED.weight""",
            (context_id, node_id, weight),
        )

    def remove_member_human(self, cur, context_id: str, node_id: str) -> None:
        cur.execute(
            "DELETE FROM context_member WHERE context_id = %s AND node_id = %s AND produced_by IS NULL",
            (context_id, node_id),
        )

    def contexts_of(self, cur, node_id: str) -> list[tuple]:
        cur.execute(
            "SELECT c.id, c.scope, c.title FROM context c "
            "JOIN context_member m ON m.context_id = c.id WHERE m.node_id = %s "
            "ORDER BY c.scope, c.id",
            (node_id,),
        )
        return cur.fetchall()

    def members_of(self, cur, context_id: str) -> list[tuple]:
        cur.execute(
            "SELECT node_id, weight FROM context_member WHERE context_id = %s "
            "ORDER BY weight DESC, node_id",
            (context_id,),
        )
        return cur.fetchall()

    def discover_higher_dim(self, cur, seed_node_id: str, k: int = 5) -> list[tuple]:
        """T4.1 heuristic: k nearest neighbours of the seed by embedding (cosine/L2 via pgvector)."""
        cur.execute(
            """SELECT n.id, n.title, 1 - (n.embedding <=> q.embedding) AS sim
               FROM node n, (SELECT embedding FROM node WHERE id = %s) q
               WHERE n.id <> %s AND n.embedding IS NOT NULL
               ORDER BY n.embedding <=> q.embedding
               LIMIT %s""",
            (seed_node_id, seed_node_id, k),
        )
        return cur.fetchall()
