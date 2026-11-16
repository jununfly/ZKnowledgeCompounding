-- 0011: 节点墓碑软删除（ADR-0013，DI-5 被推翻后的语义落地 S1）。
--
-- 决策语义（Q1/Q5）：墓碑 is_delete=1 用单字段 `deleted_at` 承载 —— NULL=未墓碑，
-- 非 NULL=墓碑时刻且兼作 TTL(7d) 起算点（单字段保证墓碑态与起算点原子一致）。
--
-- 两表加列（参照 0003 version_seq 范式）：node_history 也加，否则 history() 的
-- node UNION ALL node_history 显式列清单两侧列数错位（已知坑）。
-- 索引：部分索引只覆盖墓碑节点，避免为全表未墓碑行付索引写入代价。
--
-- 审计表：node_id 刻意**无 FK** —— 真删 node 后审计行必须独立存在（Q8）；
-- title 是删除时快照，不记 content。event_kind 三态覆盖墓碑/恢复/真删。

ALTER TABLE public.node         ADD COLUMN deleted_at timestamptz;
ALTER TABLE public.node_history ADD COLUMN deleted_at timestamptz;

CREATE INDEX node_deleted_idx ON public.node (deleted_at) WHERE deleted_at IS NOT NULL;

CREATE TABLE public.node_deletion_audit (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id       uuid NOT NULL,
    title         text NOT NULL,
    tombstoned_at timestamptz NOT NULL,
    event_kind    text NOT NULL CHECK (event_kind IN ('tombstone','restore','purge')),
    deleted_at    timestamptz,
    ttl_days      integer,
    operator      text NOT NULL,
    reason        text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX nda_node_idx ON public.node_deletion_audit (node_id);
CREATE INDEX nda_kind_idx ON public.node_deletion_audit (event_kind, deleted_at DESC);
