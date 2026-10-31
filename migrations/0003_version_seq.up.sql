-- ZKC P1.2 后续 · 迁移 0003：OCC 版本号列（version_seq）
--
-- 解决上轮 concurrency 收尾标注的两个遗留：
--   ① meta_claim / context 的并发/版本链未获与 node 同等的保护；
--   ② 未引入 OCC / version_seq（node 当时只有悲观行锁 FOR UPDATE，没有乐观版本号）。
--
-- 方案（对称、最小、可测）：
--   给 node / node_history / meta_claim / context 各加
--   `version_seq BIGINT NOT NULL DEFAULT 1`。
--   所有写路径（node.save / update_decay / set_interval + claim/context upsert）
--   在「写时自增 version_seq + WHERE version_seq = 期望版本」；期望版本不匹配
--   → 抛 ConcurrentModification（OCC 语义：后提交者用过期版本号写被拒）。
--   首次 INSERT 写入 version_seq = 1。
--
-- 范围边界（重要，不静默归并）：
--   * modeling_artifact 当前**无 repository 实现**（仅 0001 建了 schema），没有写路径
--     可加固 → 不在本次；其 revises 链沿用 schema 级 tx_from/tx_to，留待补 repo 时再补。
--   * edge / review_queue / attention_observation 是 INSERT 或幂等覆盖（last-write-wins）
--     语义，冲突不敏感 → 不引入 OCC。
--
-- 依赖：0001（建表）+ 0002（node_history）。PostgreSQL 16 + pgvector。

ALTER TABLE public.node          ADD COLUMN version_seq BIGINT NOT NULL DEFAULT 1;
ALTER TABLE public.node_history  ADD COLUMN version_seq BIGINT NOT NULL DEFAULT 1;
ALTER TABLE public.meta_claim    ADD COLUMN version_seq BIGINT NOT NULL DEFAULT 1;
ALTER TABLE public.context       ADD COLUMN version_seq BIGINT NOT NULL DEFAULT 1;
