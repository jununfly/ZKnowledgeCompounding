-- ZKC spike 09 切片 B：注意力预算的观测与估计。
-- Depends on spike-09 schema_ext.sql (interval_adjustment) + spike-04 ext (transform).
--
-- WHY A TABLE AND NOT A CONSTANT:
--   `budget_per_day` is a CAPACITY, and capacity can only be observed, not declared.
--   But observing it is a *censored* problem: on a day when the review queue empties,
--   the number of completed reviews is only a LOWER BOUND on capacity (supply-limited).
--   Only on a day that ends with a backlog did we actually hit the ceiling (capacity-limited).
--   Without this distinction the estimate silently collapses: budget_down -> intervals
--   stretched -> fewer items surfaced -> fewer reviews observed -> budget_down further.
--   So the observation must record supply (pushed) and leftover (queue_remaining),
--   not merely how many reviews happened.

CREATE TABLE IF NOT EXISTS attention_observation (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  day             date NOT NULL UNIQUE,
  pushed          int  NOT NULL CHECK (pushed >= 0),           -- 进入注意力的条数（供给侧）
  completed       int  NOT NULL CHECK (completed >= 0),        -- 当天实际完成复审的条数
  queue_remaining int  NOT NULL CHECK (queue_remaining >= 0),  -- 日末未处理积压
  -- 带「结果标注」的完成数（D8）。L3 只认显式标注，不认 decay 数值（decay-only 反馈恒为
  -- no-op，见切片 A F1），所以标注率必须被观测——低于门槛时 L3 必须停机，而不是继续用
  -- 无声的复习行为冒充信号。
  labeled_completed int NOT NULL DEFAULT 0,
  CONSTRAINT labeled_le_completed CHECK (labeled_completed <= completed),
  -- saturated := queue_remaining > 0 —— 当天撞到容量上限（completed 是容量的确证），
  -- 否则只是下界（供给受限，人还能做更多）。
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ao_day_idx ON attention_observation (day DESC);
