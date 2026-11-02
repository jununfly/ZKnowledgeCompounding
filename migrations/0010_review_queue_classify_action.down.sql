-- 回滚 0010：恢复 0001 原始约束。
-- 注意：若表中已有 action='classify' 的行，本回滚会因约束校验失败——
-- 需先清理或 resolve 掉 classify 条目再执行。
ALTER TABLE public.review_queue DROP CONSTRAINT IF EXISTS review_queue_action_check;
ALTER TABLE public.review_queue
    ADD CONSTRAINT review_queue_action_check
    CHECK (action IN ('distill', 'archive', 'abstain'));
