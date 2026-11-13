-- 0007_llm_call_score · 轻量 LLM 调用度量表（蒸馏结构化接线，替代 Langfuse）
--
-- 用途：Langfuse 提供 trace/score/eval 全家桶但自带 ClickHouse+Redis+Node 栈，
-- 对单人 MVP 太重（调研 distill-llm-2026-10-29-draft.md §101）。本表只记
-- 「一次蒸馏 LLM 调用」的最小事实：延迟、解析成败、重试成本、产物规模、错误，
-- 外加 human_verdict 可空列 = 蒸馏质量 rubric 的人工打分入口（复审流回填）。
--
-- 落库点：zkc.expiry.apply_distill（成功与失败都记——失败行的 error 是
-- 接线质量的第一手观测）。operation 走 CHECK 白名单，后续扩算子走新增迁移
-- 扩 CHECK（同 0004→0006 proposal_log_kind 先例）。

CREATE TABLE public.llm_call_score (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    operation      text NOT NULL CHECK (operation IN ('distill')),
    node_id        uuid,
    model          text,
    latency_ms     real,
    parse_ok       boolean NOT NULL,
    attempts       integer,
    n_claims       integer,
    n_citations    integer,
    error          text,
    human_verdict  text CHECK (human_verdict IN ('good', 'bad'))
);

CREATE INDEX lcs_operation_created_idx ON public.llm_call_score (operation, created_at DESC);
CREATE INDEX lcs_node_idx ON public.llm_call_score (node_id);
