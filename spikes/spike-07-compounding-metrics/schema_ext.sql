-- ZKC spike 07: compounding metrics (T7.1) + citation instrumentation (T6.2).
-- Depends on spike-01 base (node/meta_claim/edge) + spike-04 ext (transform) + spike-05 ext (modeling_artifact).
--
-- T6.2 引用埋点：记录「后续条目复用某 claim」的引用关系，支撑复用率指标。
-- 与 context_member 同构：每行带 produced_by，可接入 spike-04/05 的级联撤销不变量。
-- 注意：meta_claim.evidence_refs 指向「claim 自身的来源」，方向相反；本表指向「claim 被谁复用」，
-- 二者共同构成双向溯源，复用率需本表才能计算（evidence_refs 单向无法得出）。
CREATE TABLE IF NOT EXISTS citation (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  citing_node_id  uuid REFERENCES node(id)       ON DELETE CASCADE,  -- 复用方（后续条目）
  cited_claim_id  uuid REFERENCES meta_claim(id) ON DELETE CASCADE,  -- 被复用的 claim
  produced_by     uuid REFERENCES transform(id)  ON DELETE CASCADE,  -- 产生该引用的变换（可级联撤销）
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cit_citing_idx ON citation (citing_node_id);
CREATE INDEX IF NOT EXISTS cit_cited_idx  ON citation (cited_claim_id);
CREATE INDEX IF NOT EXISTS cit_prod_idx   ON citation (produced_by);

-- 衰减可控所需信号：标记「已归档」的动态条目（被处理而非静默丢失）。
-- 与 spike-06 给 context 加 produced_by/tx_from/tx_to 同构：给 node 加生命周期状态列。
-- 衰减可控 = 到期动态节点中「被蒸馏/结合引用 (evidence_refs) 或已被归档」的比例。
ALTER TABLE node ADD COLUMN IF NOT EXISTS archived_at timestamptz;
