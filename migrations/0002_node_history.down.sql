-- ZKC P1.2 后续 · 回滚 0002：删除 node_history 版本表
-- 只删表，不动 node 当前态表与其 FK。

DROP TABLE IF EXISTS public.node_history;
