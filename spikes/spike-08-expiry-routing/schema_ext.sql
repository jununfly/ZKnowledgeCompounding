-- ZKC spike 08: expiry routing (distill vs archive vs abstain).
--
-- DESIGN FINDING (recorded as a deviation, not silently accepted):
--   The routing rule needs NO new signal columns. Every signal it uses already exists:
--     - expiry:        node.track='dynamic' AND node.decay_score >= ROT_THRESHOLD (0.9)
--     - already value: meta_claim.evidence_refs / modeling_artifact.evidence_refs @> {node}
--     - connection:    edge rows touching the node
--     - context:       context_member rows for the node
--   So the spike only adds the *operational* table that makes the ABSTAIN/DISTILL outcome
--   actionable (a human-in-the-loop queue), consistent with Spike 02/04 review gates.
CREATE TABLE IF NOT EXISTS review_queue (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id    uuid REFERENCES node(id) ON DELETE CASCADE,
  action     text NOT NULL CHECK (action IN ('distill','archive','abstain')),
  reason     text,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved   bool NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS rq_node_idx ON review_queue (node_id);
CREATE INDEX IF NOT EXISTS rq_open_idx ON review_queue (resolved) WHERE resolved = false;
