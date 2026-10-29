-- ZKC spike 04: distill-loop extension over spike-01 schema.
-- Encodes the two acceptance constraints from architecture §6.4:
--   (1) bitemporal writes are append-only: history rows are never rewritten in content,
--       only closed via tx_to; revisions are new rows.
--   (2) every distillation product carries produced_by -> transform(id) ON DELETE CASCADE,
--       so discarding a transform reverts ALL its side effects.

-- A transform instance = one run of a knowledge transformation (distill / combine / ...)
CREATE TABLE IF NOT EXISTS transform (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind       text NOT NULL,                    -- 'distill' | 'combine' | ...
  params     jsonb NOT NULL DEFAULT '{}',      -- inputs / settings for replayability
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Claims become versioned (append-only) + attributable to the transform that made them
ALTER TABLE meta_claim
  ADD COLUMN IF NOT EXISTS produced_by uuid REFERENCES transform(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS revises     uuid REFERENCES meta_claim(id),
  ADD COLUMN IF NOT EXISTS tx_from     timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS tx_to       timestamptz;   -- NULL = current version

-- Reverse-link edges produced by a transform are likewise attributable + revertible
ALTER TABLE edge
  ADD COLUMN IF NOT EXISTS produced_by uuid REFERENCES transform(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS claim_produced_idx ON meta_claim (produced_by);
CREATE INDEX IF NOT EXISTS claim_current_idx  ON meta_claim (revises) WHERE tx_to IS NULL;
CREATE INDEX IF NOT EXISTS edge_produced_idx  ON edge (produced_by);
