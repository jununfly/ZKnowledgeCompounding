-- ZKC spike 06: context topology assembly (T4.1 discovery + T4.2 membership).
-- Depends on spike-01 base schema (node/context/edge/meta_claim) + spike-04 ext (transform).
--
-- Design decision validated by this spike (supersedes architecture §5 sketch):
--   architecture §5 sketched `context.member_nodes uuid[]`. An array column cannot carry
--   per-member provenance, so it cannot participate in the spike-04/05 `produced_by`
--   cascade-undo invariant (every transform product must be revertible). We therefore model
--   membership as a JUNCTION TABLE `context_member` carrying `produced_by` (which assembly
--   transform produced it) + `weight` (soft membership). `context.member_nodes` is left in
--   place but unused (legacy); this deviation must be backfilled into architecture §5.

-- Make `context` carry provenance + lifecycle so an assembly transform can be fully reverted.
ALTER TABLE context ADD COLUMN IF NOT EXISTS title      text;
ALTER TABLE context ADD COLUMN IF NOT EXISTS produced_by uuid REFERENCES transform(id) ON DELETE CASCADE;
ALTER TABLE context ADD COLUMN IF NOT EXISTS tx_from   timestamptz NOT NULL DEFAULT now();
ALTER TABLE context ADD COLUMN IF NOT EXISTS tx_to     timestamptz;

-- Scope is a closed vocabulary. NOTE: the base schema (spike-01) already models `scope`
-- as a Postgres ENUM `context_scope` ('self_loop' | 'higher_dim'), which enforces this
-- more strictly than architecture §5's `text` sketch — a tightening to backfill into §5.
-- No extra CHECK needed; the enum is the source of truth.

-- Junction table: the real membership model (T4.2). produced_by NULL = human-added
-- (removable directly); non-NULL = produced by an assembly transform (cascades on revert).
CREATE TABLE IF NOT EXISTS context_member (
  context_id  uuid REFERENCES context(id) ON DELETE CASCADE,
  node_id     uuid REFERENCES node(id)    ON DELETE CASCADE,
  produced_by uuid REFERENCES transform(id) ON DELETE CASCADE,
  weight      real NOT NULL DEFAULT 1.0,
  added_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (context_id, node_id)
);

CREATE INDEX IF NOT EXISTS cm_context_idx  ON context_member (context_id);
CREATE INDEX IF NOT EXISTS cm_node_idx     ON context_member (node_id);
CREATE INDEX IF NOT EXISTS cm_produced_idx ON context_member (produced_by);
