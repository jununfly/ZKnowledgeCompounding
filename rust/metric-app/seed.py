"""Deterministic DB seeds for the metrics_report app-level black-box recording.

Each variant resets zkc_metric_record to a fixed state that exercises a distinct
branch of the five metrics (division guards, saturation, decay boundary, handled
vs unhandled). Fixed UUIDs => byte-stable DB dump across runs. The variant is
selected by ZKC_SEED_VARIANT (passed through the case env by `app record`).
Never touches zkc_dev (the developer's historical DB).
"""
import os
import psycopg

DSN = os.environ.get(
    "ZKC_PG_DSN", "postgresql://postgres:zkc@localhost:55433/zkc_metric_record"
)
# `app record --db-reset` does NOT inherit the case's env, so the variant is
# delivered as a file in the case's working directory (the `files` field of
# --inputs). Env remains a convenience for manual runs.
def _select_variant() -> str:
    try:
        with open("variant.txt", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return os.environ.get("ZKC_SEED_VARIANT", "seeded")


VARIANT = _select_variant()


def u(n: int) -> str:
    """Fixed, human-readable UUID from a small integer."""
    return f"00000000-0000-0000-0000-{n:012d}"


# Each variant: nodes (id, track, decay, archived), edges (src, dst, kind),
# claims (id, evidence_refs), citations (claim_id), artifacts (evidence_refs).
VARIANTS = {
    # All five metrics non-zero and distinguishable (the original case).
    "seeded": {
        "nodes": [
            (u(1), "dynamic", 0.95, False),
            (u(2), "dynamic", 0.50, False),
            (u(3), "dynamic", 0.95, True),
            (u(4), "dynamic", 0.95, False),
            (u(11), "static", 0.0, False),
        ],
        "edges": [(u(1), u(2), "reverse_link"),
                  (u(2), u(3), "derived_from")],
        "claims": [(u(201), [u(1)]), (u(202), [u(3)])],
        "citations": [u(201), u(201), u(202)],
        "artifacts": [[u(2)]],
    },
    # Empty DB: every division guard returns 0.
    "empty": {"nodes": [], "edges": [], "claims": [], "citations": [], "artifacts": []},
    # Only static nodes: connection_density's `dyn` empty guard, decay's empty guard.
    "static-only": {
        "nodes": [(u(11), "static", 0.0, False), (u(12), "static", 0.95, False)],
        "edges": [], "claims": [], "citations": [], "artifacts": [],
    },
    # Dynamic nodes exist but no qualifying edge: connection_density = 0 with non-empty dyn.
    "no-edges": {
        "nodes": [(u(1), "dynamic", 0.5, False), (u(2), "dynamic", 0.5, False),
                  (u(3), "dynamic", 0.5, False), (u(4), "dynamic", 0.5, False)],
        "edges": [(u(1), u(2), "mentions")],
        "claims": [(u(201), []), (u(202), [])],
        "citations": [u(201)],
        "artifacts": [],
    },
    # All dynamic nodes connected: connection_density = 1.0.
    "all-connected": {
        "nodes": [(u(1), "dynamic", 0.5, False), (u(2), "dynamic", 0.5, False),
                  (u(3), "dynamic", 0.5, False), (u(4), "dynamic", 0.5, False)],
        "edges": [(u(1), u(2), "reverse_link"),
                  (u(2), u(3), "derived_from"),
                  (u(3), u(4), "reverse_link")],
        "claims": [(u(201), []), (u(202), [])],
        "citations": [u(201), u(202)],
        "artifacts": [],
    },
    # Expired dynamic nodes but none handled: decay_controllability = 0.
    "expired-unhandled": {
        "nodes": [(u(1), "dynamic", 0.95, False), (u(2), "dynamic", 0.95, False),
                  (u(3), "dynamic", 0.95, False)],
        "edges": [], "claims": [], "citations": [], "artifacts": [],
    },
    # All expired nodes handled (archived + evidence): decay_controllability = 1.0.
    "all-handled": {
        "nodes": [(u(1), "dynamic", 0.95, True), (u(2), "dynamic", 0.95, True),
                  (u(3), "dynamic", 0.95, True)],
        "edges": [],
        "claims": [(u(201), [u(1)])],
        "citations": [u(201)],
        "artifacts": [[u(2)]],
    },
    # More artifacts than method target (10): methodology_output saturates at 1.0.
    "method-saturated": {
        "nodes": [(u(1), "dynamic", 0.5, False), (u(2), "dynamic", 0.5, False)],
        "edges": [(u(1), u(2), "reverse_link")],
        "claims": [(u(201), [])],
        "citations": [u(201)],
        "artifacts": [[] for _ in range(12)],
    },
    # More citations than claims: citations_per_claim > 1 while reuse_rate = 1.0.
    "citation-heavy": {
        "nodes": [(u(1), "dynamic", 0.5, False), (u(2), "dynamic", 0.5, False)],
        "edges": [(u(1), u(2), "reverse_link")],
        "claims": [(u(201), []), (u(202), []), (u(203), [])],
        "citations": [u(201), u(201), u(202), u(202), u(203), u(203)],
        "artifacts": [],
    },
    # decay_score exactly equal to ROT (0.9) counts as expired; just below does not.
    "decay-boundary": {
        "nodes": [(u(1), "dynamic", 0.9, False), (u(2), "dynamic", 0.8999, False)],
        "edges": [(u(1), u(2), "reverse_link")],
        "claims": [(u(201), [u(1)])],
        "citations": [u(201)],
        "artifacts": [],
    },
}

TABLES = [
    "citation", "context_member", "context", "interval_adjustment",
    "review_queue", "task_queue", "node_deletion_audit", "node_history",
    "modeling_artifact", "meta_claim", "edge", "proposal_log", "transform", "node",
]


def main() -> None:
    data = VARIANTS[VARIANT]
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE " + ", ".join(f"public.{t}" for t in TABLES) + " CASCADE;")
            # created_at/content are deterministic and NOT emitted by dump.sh (which selects only
            # id/track/decay_score/archived) nor read by metrics_report's queries — adding them is
            # baseline-invisible. They exist so the structured-search A-path (ORDER BY created_at,
            # ILIKE over title/content) has stable, comparable results across original and Rust.
            for idx, (nid, track, decay, archived) in enumerate(data["nodes"]):
                cur.execute(
                    "INSERT INTO public.node (id, track, title, content, decay_score, "
                    "archived_at, created_at) VALUES (%s::uuid, %s::track_kind, %s, %s, %s, %s, %s::timestamptz);",
                    (nid, track, f"seed-{nid[-1]}", f"body {nid[-1]} shared", decay,
                     "2026-01-01T00:00:00Z" if archived else None,
                     f"2026-06-01 00:00:{idx:02d}+00"),
                )
            for i, (src, dst, kind) in enumerate(data["edges"]):
                cur.execute(
                    "INSERT INTO public.edge (id, src, dst, kind) "
                    "VALUES (%s::uuid, %s::uuid, %s::uuid, %s);",
                    (u(100 + i), src, dst, kind),
                )
            # Always insert one combine transform; artifact queries join it.
            cur.execute(
                "INSERT INTO public.transform (id, kind) VALUES (%s::uuid, 'combine');",
                (u(301),),
            )
            for i, (cid, refs) in enumerate(data["claims"]):
                cur.execute(
                    "INSERT INTO public.meta_claim (id, statement, evidence_refs) "
                    "VALUES (%s::uuid, %s, %s::uuid[]);",
                    (cid, f"seed claim {i}", refs),
                )
            for i, cid in enumerate(data["citations"]):
                cur.execute(
                    "INSERT INTO public.citation (id, cited_claim_id) VALUES (%s::uuid, %s::uuid);",
                    (u(500 + i), cid),
                )
            for i, refs in enumerate(data["artifacts"]):
                cur.execute(
                    "INSERT INTO public.modeling_artifact "
                    "(id, title, kind, body, evidence_refs, produced_by) "
                    "VALUES (%s::uuid, %s, 'methodology', '{}'::jsonb, %s::uuid[], %s::uuid);",
                    (u(400 + i), f"artifact {i}", refs, u(301)),
                )


if __name__ == "__main__":
    main()
