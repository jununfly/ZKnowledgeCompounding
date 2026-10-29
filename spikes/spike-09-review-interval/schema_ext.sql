-- ZKC spike 09: automatic `review_interval` assignment (架构 §9 剩余项 ④).
-- Depends on spike-01 base schema + spike-04 ext (transform) + spike-06/07/08 exts.
--
-- DESIGN FINDING (recorded as deviations D6/D7, not silently accepted):
--   `review_interval` is NOT a free per-item attribute. It is a two-layer quantity:
--       effective_i = baseline_i (individual rot rate)  x  budget factor (global scarcity)
--   because attention is a HARD budget (spike 01): daily demand = SUM(1 / (0.6 * I_i)).
--   Setting each item to its individually-optimal baseline can blow the budget, so the
--   per-item suggestion must be normalised globally. Prior-probability prediction is also
--   unreliable, hence a third layer: closed-loop feedback from actual reviews.
--
-- D6: two extra columns on `node` to keep the two layers auditable and to protect
--     human overrides from being silently rewritten by automation.
-- D7: `interval_adjustment` — append-only audit of every interval change, carrying
--     produced_by -> transform(id) ON DELETE CASCADE so a budget-normalisation batch can
--     be reverted as a whole (architecture §6.4 C2: side effects fully rollbackable).

ALTER TABLE node ADD COLUMN IF NOT EXISTS baseline_interval interval;
ALTER TABLE node ADD COLUMN IF NOT EXISTS interval_source  text NOT NULL DEFAULT 'auto'
  CHECK (interval_source IN ('auto', 'human'));

CREATE TABLE IF NOT EXISTS interval_adjustment (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id     uuid NOT NULL REFERENCES node(id)      ON DELETE CASCADE,
  kind        text NOT NULL CHECK (kind IN ('baseline', 'budget', 'feedback')),
  old_days    real,                       -- NULL when the item had no interval before
  new_days    real NOT NULL,
  reason      text NOT NULL,              -- every change must be explainable
  produced_by uuid REFERENCES transform(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ia_node_idx ON interval_adjustment (node_id);
CREATE INDEX IF NOT EXISTS ia_prod_idx ON interval_adjustment (produced_by);
