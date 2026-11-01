-- 0004_proposal_log · D9 更高维 context 提议日志（调度层·注意力预算）
--
-- 用途：支撑「全局每日提议数频率上限」。原有的去重闸门（find_higher_dim_for_seed）
-- 只防「同种子重复」，不防「全库每日过量提议」——而每日提议同样消耗人审注意力，
-- 须与复审预算同源受限（注意力预算）。本表按 (day, kind) 累计系统当日已提议条数，
-- 供 scheduling.proposal_budget_for_day 跨种子限流。
--
-- 与 attention_observation 同源（都是「外生锚」式埋点），但语义不同：
--   attention_observation = 复审队列的每日收口（pushed/completed/queue_remaining/labeled）
--   proposal_log          = 系统主动提议的更高维聚合数（限流用）

CREATE TABLE public.proposal_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    day         date NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('higher_dim', 'self_loop')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX pl_day_kind_idx ON public.proposal_log (day, kind);
