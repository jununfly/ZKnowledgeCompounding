-- 0006 · 放宽 proposal_log.kind CHECK，纳入人工忽略事件 higher_dim_dismissed
--
-- 背景：P1 收尾把 propose_higher_dim_daily 接入复审流，新增 dismiss_higher_dim，
-- 落 proposal_log(kind='higher_dim_dismissed', seed_id)，使当日 sweep 可跳过被忽略种子
-- （dismissed_seed_ids 查询同源）。但 0004 的 CHECK 仅允许 ('higher_dim','self_loop')，
-- 缺 dismissed 变体 → 真实 PG 下 CheckViolation（内存 fake 无约束，单测漏网）。
--
-- 本迁移扩展约束，不回改 0004（否则破坏 schema_migration 的 sha256 校验闸门）。

ALTER TABLE public.proposal_log
    DROP CONSTRAINT IF EXISTS proposal_log_kind_check;

ALTER TABLE public.proposal_log
    ADD CONSTRAINT proposal_log_kind_check
    CHECK (kind IN ('higher_dim', 'self_loop', 'higher_dim_dismissed'));
