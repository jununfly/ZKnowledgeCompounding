-- 0009: 1-9 任务队列 UI（roadmap 1-9）。
-- 把观察期临时记在 TODO.md 的 zj 待办任务，以「任务卡片队列」形式落到 DB，
-- 由规则自动生成（周期/预警/一次性），UI 勾选完成并联动现有闭环（复审标注率、budget 收口）。
-- UNIQUE(day, kind) 保证「确保当日任务」幂等 upsert：已存在则保留其 status（done 不被覆盖）。
CREATE TABLE IF NOT EXISTS public.task_queue (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    day          date NOT NULL,
    category     text NOT NULL,            -- periodic | alert | once
    kind         text NOT NULL,            -- daily_review | daily_close | weekly_snapshot | orphan_spike | labeled_judgment | commit_push
    title        text NOT NULL,
    detail       text,
    due_date     date,                     -- 预警/一次性锚定日（可选）
    status       text NOT NULL DEFAULT 'open',  -- open | done
    source_rule  text,                     -- 生成它的规则标识（溯源）
    payload      jsonb,                    -- 动作相关元数据（如度量脚本、git 备注）
    created_at   timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT task_queue_status_chk CHECK (status IN ('open', 'done')),
    CONSTRAINT task_queue_category_chk CHECK (category IN ('periodic', 'alert', 'once')),
    CONSTRAINT task_queue_uq_day_kind UNIQUE (day, kind)
);
