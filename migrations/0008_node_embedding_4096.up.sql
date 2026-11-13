-- 0008: R18 加列路径（双列共存）——nomic 768d 保留，新增 qwen3-embedding 4096d 列。
-- /browse 候选召回切到本列（R18 实测：768d Recall@10=0.562 不合格，4096d=0.938 合格）。
-- node_history 不镜像本列：embedding 是派生数据非事实，双时态快照只镜像 768 列（历史行为不变）。
ALTER TABLE public.node ADD COLUMN embedding_4096 vector(4096);
