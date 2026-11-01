-- 0006 回滚：约束恢复为 0004 原始口径。
-- 注意：已存在的 higher_dim_dismissed 行会阻止回滚；回滚前须先清理该类行。

ALTER TABLE public.proposal_log
    DROP CONSTRAINT IF EXISTS proposal_log_kind_check;

ALTER TABLE public.proposal_log
    ADD CONSTRAINT proposal_log_kind_check
    CHECK (kind IN ('higher_dim', 'self_loop'));
