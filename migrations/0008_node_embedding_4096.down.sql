-- 0008 down: 删除 4096d 候选召回列（768 列不受影响）。
ALTER TABLE public.node DROP COLUMN IF EXISTS embedding_4096;
