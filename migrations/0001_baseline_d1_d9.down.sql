-- ZKC P1.1 · 基线迁移 0001 的回滚脚本
-- 由 `zkc/migrate.py downgrade` 在单事务内执行。顺序与 up 严格相反（依赖倒序）。
--
-- ⚠️ 本脚本会**删除全部领域数据**（ON DELETE CASCADE 会带走关联行）。
--    生产/含真实素材的库上执行前必须先备份。MVP 阶段只用于 zkc_dev 反复重放。

DROP TABLE IF EXISTS public.attention_observation;
DROP INDEX IF EXISTS public.ao_day_idx;

DROP TABLE IF EXISTS public.interval_adjustment;
DROP INDEX IF EXISTS public.ia_node_idx;
DROP INDEX IF EXISTS public.ia_prod_idx;

DROP TABLE IF EXISTS public.review_queue;
DROP INDEX IF EXISTS public.rq_node_idx;
DROP INDEX IF EXISTS public.rq_open_idx;

DROP TABLE IF EXISTS public.citation;
DROP INDEX IF EXISTS public.cit_citing_idx;
DROP INDEX IF EXISTS public.cit_cited_idx;
DROP INDEX IF EXISTS public.cit_prod_idx;

DROP TABLE IF EXISTS public.context_member;
DROP INDEX IF EXISTS public.cm_context_idx;
DROP INDEX IF EXISTS public.cm_node_idx;
DROP INDEX IF EXISTS public.cm_produced_idx;

DROP TABLE IF EXISTS public.context;

DROP TABLE IF EXISTS public.edge;
DROP INDEX IF EXISTS public.edge_src_idx;
DROP INDEX IF EXISTS public.edge_dst_idx;
DROP INDEX IF EXISTS public.edge_produced_idx;

DROP TABLE IF EXISTS public.modeling_artifact;
DROP INDEX IF EXISTS public.artifact_evidence_idx;
DROP INDEX IF EXISTS public.artifact_produced_idx;

DROP TABLE IF EXISTS public.meta_claim;
DROP INDEX IF EXISTS public.claim_evidence_idx;
DROP INDEX IF EXISTS public.claim_produced_idx;
DROP INDEX IF EXISTS public.claim_current_idx;
DROP INDEX IF EXISTS public.claim_faith_status_idx;
DROP INDEX IF EXISTS public.claim_faith_route_idx;
DROP INDEX IF EXISTS public.claim_human_verdict_at_idx;

DROP TABLE IF EXISTS public.node;
DROP INDEX IF EXISTS public.node_track_decay_idx;
DROP INDEX IF EXISTS public.node_attention_idx;
DROP INDEX IF EXISTS public.node_embedding_idx;

DROP TABLE IF EXISTS public.transform;

DROP TYPE IF EXISTS public.human_verdict_kind;
DROP TYPE IF EXISTS public.faithfulness_status;
DROP TYPE IF EXISTS public.context_scope;
DROP TYPE IF EXISTS public.track_kind;

-- 注意：不 DROP EXTENSION vector —— 它可能与其他对象共享，且降级后再升级仍需它。
