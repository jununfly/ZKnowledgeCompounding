-- 0005_proposal_log_seed 回滚

DROP INDEX IF EXISTS public.pl_day_kind_seed_idx;

ALTER TABLE public.proposal_log
    DROP COLUMN IF EXISTS seed_id;
