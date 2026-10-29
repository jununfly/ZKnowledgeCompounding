"""Expiry routing operator (Spike 08): distill vs archive vs abstain for expired dynamic nodes.

The rule is a pure read-side decision over signals that already exist in the schema
(see schema_ext.sql header for the design finding). It is deterministic and transparent,
with a forced ABSTAIN for unknown/orphan cases so nothing is silently dropped — matching
the PRD §8 conservative stance ("宁少勿错").

Decision table
--------------
  already_captured (node is evidence of a claim/artifact)  -> ARCHIVE  (value preserved; archive raw)
  connected (edge) OR in active context, not captured      -> DISTILL  (lift insight to meta layer)
      .. unless attention_pressure >= PRESSURE_DEFER       -> ABSTAIN  (defer: distill costs review attention)
  orphan (no connection, no context, not captured)         -> ABSTAIN  (human decides; never auto-drop)
"""
from store import ROT_THRESHOLD

DECISION_DISTILL = "distill"
DECISION_ARCHIVE = "archive"
DECISION_ABSTAIN = "abstain"

# attention pressure (0..1) above which a DISTILL candidate is deferred to ABSTAIN
PRESSURE_DEFER = 0.8


def _signals(cur, node_id: str) -> dict:
    cur.execute(
        """
        SELECT
          (SELECT 1 FROM meta_claim m WHERE m.evidence_refs @> ARRAY[%s]::uuid[] LIMIT 1) IS NOT NULL
            AS is_evidence_claim,
          (SELECT 1 FROM modeling_artifact a WHERE a.evidence_refs @> ARRAY[%s]::uuid[] LIMIT 1) IS NOT NULL
            AS is_evidence_artifact
        """,
        (node_id, node_id),
    )
    ev_claim, ev_artifact = cur.fetchone()
    already_captured = bool(ev_claim) or bool(ev_artifact)

    cur.execute(
        "SELECT count(*) FROM edge WHERE src = %s::uuid OR dst = %s::uuid",
        (node_id, node_id),
    )
    connection_count = cur.fetchone()[0]

    cur.execute(
        "SELECT count(*) FROM context_member WHERE node_id = %s::uuid",
        (node_id,),
    )
    context_count = cur.fetchone()[0]

    return dict(
        already_captured=already_captured,
        connection_count=connection_count,
        context_count=context_count,
    )


def route_expired(cur, node_id: str, attention_pressure: float = 0.0) -> dict:
    """Return a routing decision for one node.

    Returns {routable, action, reason, signals}. action is None when not routable
    (not an expired dynamic node, or already archived).
    """
    cur.execute(
        "SELECT track, decay_score, archived_at FROM node WHERE id = %s::uuid",
        (node_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"node {node_id} not found")
    track, decay, archived = row
    if track != "dynamic" or decay is None or decay < ROT_THRESHOLD:
        return dict(action=None, routable=False,
                    reason="not an expired dynamic node", signals={})
    if archived is not None:
        return dict(action=None, routable=False, reason="already archived", signals={})

    sig = _signals(cur, node_id)
    if sig["already_captured"]:
        action, reason = DECISION_ARCHIVE, "value already lifted to meta layer (claim/artifact evidence)"
    elif sig["connection_count"] >= 1 or sig["context_count"] >= 1:
        if attention_pressure >= PRESSURE_DEFER:
            action, reason = (DECISION_ABSTAIN,
                              "would distill but attention budget full -> defer to human")
        else:
            action, reason = DECISION_DISTILL, "connected/contextual but not captured -> lift insight"
    else:
        action, reason = (DECISION_ABSTAIN,
                          "orphan (no connection/context) -> human decides, never silently drop")
    return dict(action=action, routable=True, reason=reason, signals=sig)


def apply_archive(cur, node_id: str) -> None:
    """Mark a node archived (the 'archive' outcome is locally applicable)."""
    cur.execute(
        "UPDATE node SET archived_at = now() WHERE id = %s::uuid AND archived_at IS NULL",
        (node_id,),
    )


def enqueue_review(cur, node_id: str, action: str, reason: str) -> str:
    """Persist an ABSTAIN/DISTILL decision into the human review queue."""
    cur.execute(
        "INSERT INTO review_queue (node_id, action, reason) VALUES (%s,%s,%s) RETURNING id",
        (node_id, action, reason),
    )
    return str(cur.fetchone()[0])


def route_and_apply(cur, node_id: str, attention_pressure: float = 0.0) -> dict:
    """Route one node and apply the locally-actionable part.

    - ARCHIVE  -> archived_at set now.
    - DISTILL  -> enqueued for human/LLM execution (no auto-distill in MVP).
    - ABSTAIN  -> enqueued for human judgment.
    """
    decision = route_expired(cur, node_id, attention_pressure)
    if not decision["routable"]:
        return decision
    action = decision["action"]
    if action == DECISION_ARCHIVE:
        apply_archive(cur, node_id)
    elif action in (DECISION_DISTILL, DECISION_ABSTAIN):
        enqueue_review(cur, node_id, action, decision["reason"])
    return decision
