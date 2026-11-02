-- 0010: review_queue.action 放宽，允许 'classify'（P2.2 摄入分流的弃权人工定轨）。
--
-- 根因（2026-11-02 实跑发现）：0001 的 CHECK 只覆盖复审调度动作
-- ('distill','archive','abstain')；P2.2 起摄入弃权路径复用本表入队
-- action='classify'。memory 后端无字符串校验 → 单测全绿；PG 实库
-- 一捕获就 CheckViolation（观察期 lexical gate 恒弃权，必现 500）。
ALTER TABLE public.review_queue DROP CONSTRAINT IF EXISTS review_queue_action_check;
ALTER TABLE public.review_queue
    ADD CONSTRAINT review_queue_action_check
    CHECK (action IN ('distill', 'archive', 'abstain', 'classify'));
