-- 回滚 0011：移除墓碑列与审计表（顺序与 up 相反）。
-- 注意：回滚会丢失已记录的墓碑审计事件；真删已发生的节点不可恢复（双时态随 CASCADE 已清）。
DROP TABLE IF EXISTS public.node_deletion_audit;
DROP INDEX IF EXISTS public.node_deleted_idx;
ALTER TABLE public.node_history DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE public.node         DROP COLUMN IF EXISTS deleted_at;
