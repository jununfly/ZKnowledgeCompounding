-- ZKC P1.1 · 基线迁移 0001：D1–D9 全量建表
-- 生成方式：以 14 个 spike 累积的、已实测通过的 `zkc` 库 schema 为蓝本（pg_dump -s 导出），
--           再按架构 v1.2 §5 与后续拍板**修正三处 drift**（见下方 CHANGELOG），手工整理为可重放迁移。
-- 依赖：PostgreSQL 16 + pgvector（实测 16.15 / 0.8.7，容器 zkc-spike-pg）。
-- 执行：由 `zkc/migrate.py` 在单事务内应用（--single-transaction），失败整体回滚。
--
-- ==== CHANGELOG（相对遗留库的三处修正，务必保留说明）====
-- 1. 【R16 / spike 14】node.embedding: vector(1024) → **vector(768)**
--    1024 是 spike 01 验证 DDL 可执行性的占位；spike 14 实测 nomic-embed-text = 768d。
--    换维度 = 重建索引，故必须在有数据前改完（现 node 为 0 行，窗口在此）。
-- 2. 【A10 / spike 13】meta_claim 补 **D9 六个 faithfulness 字段**
--    MVP 忠实度闸门走 human-in-the-loop，这些字段是闸门的状态载体，缺了闸门无法落地。
-- 3. 【A11 / spike 06】context 去掉已弃用的 `member_nodes uuid[]`
--    D2 已由 `context_member` junction 取代；保留冗余列会造成「两处成员来源」的双写风险。
--
-- 不在本迁移内的表：checkpoint / checkpoint_blobs / checkpoint_writes / checkpoint_migrations
--   —— 由 LangGraph 的 Postgres checkpointer 自建自管（`setup()`），不纳入 ZKC 领域 schema。

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------- 枚举类型
CREATE TYPE public.track_kind AS ENUM ('static', 'dynamic', 'unrouted');
CREATE TYPE public.context_scope AS ENUM ('self_loop', 'higher_dim');

-- D9：忠实度闸门状态（spike 13 §5）
CREATE TYPE public.faithfulness_status AS ENUM (
    'auto_passed', 'pending_human', 'human_confirmed', 'human_rejected', 'sampled_pending'
);
-- D9：人审结论（confirm / reject / edit）
CREATE TYPE public.human_verdict_kind AS ENUM ('confirm', 'reject', 'edit');

-- ---------------------------- 变换溯源（一切产物的 produced_by 指向此表）
CREATE TABLE public.transform (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind        text NOT NULL,
    params      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------- 双轨 + 双时态 + decay + 调度（D4/D6/D7）
CREATE TABLE public.node (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    track              public.track_kind NOT NULL DEFAULT 'unrouted',
    routing_confidence real,
    title              text NOT NULL,
    content            text,
    -- 双时态：服务静态轨（事实演进 + 溯源）
    valid_from         timestamptz,
    valid_to           timestamptz,
    tx_from            timestamptz NOT NULL DEFAULT now(),
    tx_to              timestamptz,
    -- 衰减：仅动态轨有意义；静态轨 decay_score 恒 0
    decay_score        real NOT NULL DEFAULT 0
                       CHECK (decay_score >= 0 AND decay_score <= 1),
    review_interval    interval,
    last_reviewed_at   timestamptz,
    attention_signal   real NOT NULL DEFAULT 0,
    created_at         timestamptz NOT NULL DEFAULT now(),
    -- 【修正 1】768d，与 spike 14 实测的 nomic-embed-text 一致
    embedding          public.vector(768),
    -- D4 归档信号
    archived_at        timestamptz,
    -- D6 基线 interval + 来源（human 不被自动化改写）
    baseline_interval  interval,
    interval_source    text NOT NULL DEFAULT 'auto'
                       CHECK (interval_source IN ('auto', 'human'))
);
CREATE INDEX node_track_decay_idx ON public.node (track, decay_score DESC);
CREATE INDEX node_attention_idx   ON public.node (attention_signal DESC);
-- 向量检索（架构 §6：pgvector HNSW）；768d 与 spike 14 绑定
CREATE INDEX node_embedding_idx   ON public.node USING hnsw (embedding vector_cosine_ops);

-- ---------------------------- 元认知 claim（D9 在此）
CREATE TABLE public.meta_claim (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    statement     text NOT NULL,
    level         text,
    confidence    real,
    -- 溯源权威：schema 级 NOT NULL，是 claim 存在的前提（架构 §5 权威声明）
    evidence_refs uuid[] NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    produced_by   uuid REFERENCES public.transform(id) ON DELETE CASCADE,
    revises       uuid REFERENCES public.meta_claim(id),
    tx_from       timestamptz NOT NULL DEFAULT now(),
    tx_to         timestamptz,
    -- ---- D9 · 忠实度闸门六字段（spike 13 §5）----
    faithfulness_status public.faithfulness_status,
    faithfulness_route  text CHECK (faithfulness_route IS NULL OR faithfulness_route IN
                            ('forced_contradicted', 'forced_empty_atomic', 'sampled_unsupported',
                             'periodic_audit', 'auto_supported', 'human_only')),
    judge_raw           jsonb,        -- Judgment（atomic_facts + overall + reason），judge 不可用时可空
    judge_model         text,         -- 判定器标识（可复现 / 离盒追溯）
    human_verdict       public.human_verdict_kind,
    human_verdict_at    timestamptz
);
CREATE INDEX claim_evidence_idx ON public.meta_claim USING gin (evidence_refs);
CREATE INDEX claim_produced_idx ON public.meta_claim (produced_by);
CREATE INDEX claim_current_idx  ON public.meta_claim (revises) WHERE tx_to IS NULL;
-- D9 索引（spike 13 §5 指定）
CREATE INDEX claim_faith_status_idx ON public.meta_claim (faithfulness_status);
CREATE INDEX claim_faith_route_idx  ON public.meta_claim (faithfulness_route);
CREATE INDEX claim_human_verdict_at_idx ON public.meta_claim (human_verdict_at);

-- ---------------------------- 建模产物（结合算子输出）
CREATE TABLE public.modeling_artifact (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title         text NOT NULL,
    kind          text NOT NULL CHECK (kind IN ('methodology', 'mental_model', 'tradeoff_map')),
    body          jsonb NOT NULL,
    evidence_refs uuid[] NOT NULL,
    produced_by   uuid REFERENCES public.transform(id) ON DELETE CASCADE,
    revises       uuid REFERENCES public.modeling_artifact(id),
    tx_from       timestamptz NOT NULL DEFAULT now(),
    tx_to         timestamptz
);
CREATE INDEX artifact_evidence_idx  ON public.modeling_artifact USING gin (evidence_refs);
CREATE INDEX artifact_produced_idx  ON public.modeling_artifact (produced_by);

-- ---------------------------- 边（连接 / 反向连接）
CREATE TABLE public.edge (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    src         uuid NOT NULL REFERENCES public.node(id) ON DELETE CASCADE,
    dst         uuid NOT NULL REFERENCES public.node(id) ON DELETE CASCADE,
    kind        text NOT NULL,
    weight      real,
    produced_by uuid REFERENCES public.transform(id) ON DELETE CASCADE,
    CONSTRAINT edge_check CHECK (src <> dst)
);
CREATE INDEX edge_src_idx      ON public.edge (src);
CREATE INDEX edge_dst_idx      ON public.edge (dst);
CREATE INDEX edge_produced_idx ON public.edge (produced_by);

-- ---------------------------- D1/D2 context 拓扑装配
CREATE TABLE public.context (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope       public.context_scope NOT NULL,
    label       text,
    title       text,
    produced_by uuid REFERENCES public.transform(id) ON DELETE CASCADE,
    tx_from     timestamptz NOT NULL DEFAULT now(),
    tx_to       timestamptz
    -- 【修正 3】已移除弃用的 member_nodes uuid[]（由 context_member 取代）
);

-- D2 junction（带 produced_by 接入级联撤销 + weight）
CREATE TABLE public.context_member (
    context_id  uuid NOT NULL REFERENCES public.context(id) ON DELETE CASCADE,
    node_id     uuid NOT NULL REFERENCES public.node(id) ON DELETE CASCADE,
    produced_by uuid REFERENCES public.transform(id) ON DELETE CASCADE,
    weight      real NOT NULL DEFAULT 1.0,
    added_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (context_id, node_id)
);
CREATE INDEX cm_context_idx  ON public.context_member (context_id);
CREATE INDEX cm_node_idx     ON public.context_member (node_id);
CREATE INDEX cm_produced_idx ON public.context_member (produced_by);

-- ---------------------------- D3 citation（复用行为事件；不参与「是否已捕获」判定）
CREATE TABLE public.citation (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    citing_node_id uuid REFERENCES public.node(id) ON DELETE CASCADE,
    cited_claim_id uuid REFERENCES public.meta_claim(id) ON DELETE CASCADE,
    produced_by    uuid REFERENCES public.transform(id) ON DELETE CASCADE,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX cit_citing_idx ON public.citation (citing_node_id);
CREATE INDEX cit_cited_idx  ON public.citation (cited_claim_id);
CREATE INDEX cit_prod_idx   ON public.citation (produced_by);

-- ---------------------------- D5 复审队列
CREATE TABLE public.review_queue (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id    uuid REFERENCES public.node(id) ON DELETE CASCADE,
    action     text NOT NULL CHECK (action IN ('distill', 'archive', 'abstain')),
    reason     text,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved   boolean NOT NULL DEFAULT false
);
CREATE INDEX rq_node_idx ON public.review_queue (node_id);
CREATE INDEX rq_open_idx ON public.review_queue (resolved) WHERE resolved = false;

-- ---------------------------- D7 interval 调整审计（append-only，带 produced_by 可整体回滚）
CREATE TABLE public.interval_adjustment (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id     uuid NOT NULL REFERENCES public.node(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('baseline', 'budget', 'feedback')),
    old_days    real,
    new_days    real NOT NULL,
    reason      text NOT NULL,
    produced_by uuid REFERENCES public.transform(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ia_node_idx ON public.interval_adjustment (node_id);
CREATE INDEX ia_prod_idx ON public.interval_adjustment (produced_by);

-- ---------------------------- D8 注意力观测埋点（budget 估计的唯一输入；外生锚）
CREATE TABLE public.attention_observation (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    day              date NOT NULL UNIQUE,
    pushed           integer NOT NULL CHECK (pushed >= 0),
    completed        integer NOT NULL CHECK (completed >= 0),
    queue_remaining  integer NOT NULL CHECK (queue_remaining >= 0),
    labeled_completed integer NOT NULL DEFAULT 0,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT labeled_le_completed CHECK (labeled_completed <= completed)
);
CREATE INDEX ao_day_idx ON public.attention_observation (day DESC);
