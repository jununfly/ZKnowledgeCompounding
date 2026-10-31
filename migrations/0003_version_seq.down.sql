-- 回滚 0003：移除 OCC 版本号列（与 up 顺序相反）。
ALTER TABLE public.context      DROP COLUMN version_seq;
ALTER TABLE public.meta_claim   DROP COLUMN version_seq;
ALTER TABLE public.node_history DROP COLUMN version_seq;
ALTER TABLE public.node         DROP COLUMN version_seq;
