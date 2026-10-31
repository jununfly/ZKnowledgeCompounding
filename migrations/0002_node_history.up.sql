-- ZKC P1.2 后续 · 迁移 0002：node 双时态版本链（append-only 历史表）
--
-- 背景（架构 v1.2 §6.4 + 第一性不变量）：
--   node.save 必须是 append-only：不改写历史行，只闭合旧行的 tx_to 并插入新行。
--   但 0001 把 node.id 设为 PRIMARY KEY（edge/review_queue/context_member/citation
--   都 FK 引用 node(id)），同一 id 无法共存多行 → 无法在同一张表里做版本链。
--
-- 方案（MVP 正确且最小侵入）：
--   - node 仍是「当前态」表，id 保持唯一 PK（所有 FK 不动）。
--   - 新增 node_history：镜像 node 全部列 + tx_to，PK=(id, tx_from)，
--     FK id->node(id) ON DELETE CASCADE（删 node 级联清历史）。
--   - 每次「更新」先 snapshot 当前行入 node_history（tx_to=now()），再 UPDATE 当前行
--     并刷新 tx_from=now()。查询全历史 = node(当前) UNION node_history。
--
-- 为什么不是「单表复合 PK (id, tx_from)」：会破坏 4 个 FK 引用语义
-- （它们引用逻辑 node，不是某个版本行）。历史表模式保持 FK 全绿。
--
-- 范围：本 refine 只覆盖 node（衰减/调度/注意力的核心）。meta_claim/context/
-- modeling_artifact 的 tx_from/tx_to 沿用各自 revises 链，不在本次内（见每日日志）。
--
-- 依赖：0001（node 表与 track_kind 枚举已存在）。PostgreSQL 16 + pgvector。

CREATE TABLE public.node_history (
    -- 与 node 同构的列（含类型与 CHECK），仅 PK 改为版本复合键
    id                 uuid NOT NULL,
    track              public.track_kind NOT NULL DEFAULT 'unrouted',
    routing_confidence real,
    title              text NOT NULL,
    content            text,
    valid_from         timestamptz,
    valid_to           timestamptz,
    tx_from            timestamptz NOT NULL DEFAULT now(),
    tx_to              timestamptz,
    decay_score        real NOT NULL DEFAULT 0
                       CHECK (decay_score >= 0 AND decay_score <= 1),
    review_interval    interval,
    last_reviewed_at   timestamptz,
    attention_signal   real NOT NULL DEFAULT 0,
    created_at         timestamptz NOT NULL DEFAULT now(),
    embedding          public.vector(768),
    archived_at        timestamptz,
    baseline_interval  interval,
    interval_source    text NOT NULL DEFAULT 'auto'
                       CHECK (interval_source IN ('auto', 'human')),
    -- 版本链主键：逻辑 id + 事务起始时刻
    PRIMARY KEY (id, tx_from),
    -- 删 node 级联清其全部历史版本
    FOREIGN KEY (id) REFERENCES public.node(id) ON DELETE CASCADE
);

-- 按逻辑 id 查历史；按 tx_to 过滤「是否仍开着」（当前态在 node 表，不在 history）
CREATE INDEX node_history_id_idx ON public.node_history (id);
CREATE INDEX node_history_tx_to_idx ON public.node_history (tx_to);
