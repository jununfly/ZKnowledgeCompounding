-- 0005_proposal_log_seed · 记录被忽略种子（让 dismiss 真生效）
--
-- 用途：proposal_log 原仅按 (day, kind) 计数，无法区分「哪条种子被人工忽略」。
-- 更高维聚合接入复审流后，dismiss 必须让当日 sweep 跳过该种子（否则每次刷新都再提议，
-- "忽略"成了装饰）。本迁移给 proposal_log 加可空 seed_id，并在 dismiss 时落 kind=
-- 'higher_dim_dismissed' + seed_id；dismissed_seed_ids(day) 据此返回当日被忽略种子集。
--
-- 与 0004 同源（都是"外生锚"式埋点）；seed_id 可空以向后兼容既有 higher_dim 计数行。

ALTER TABLE public.proposal_log
    ADD COLUMN seed_id uuid REFERENCES public.node(id) ON DELETE CASCADE;

CREATE INDEX pl_day_kind_seed_idx ON public.proposal_log (day, kind, seed_id);
