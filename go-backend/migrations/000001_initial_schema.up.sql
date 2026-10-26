-- 000001_initial_schema.up.sql
-- Go 业务后端独有表（users / tasks / reports / profiles / feedback）。
-- Python 的表由 python-ai/app/factory/repository.py 的 init_tables() 管理。

-- ── 用户与租户 ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    nickname      TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_tenant ON users (tenant_id);

-- ── 研究任务 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY,          -- 同时也是 LangGraph thread_id
    tenant_id       UUID NOT NULL,
    user_id         UUID NOT NULL REFERENCES users(id),
    client_task_id  TEXT NOT NULL,             -- 幂等键
    status          TEXT NOT NULL DEFAULT 'intake',
    image_keys      JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, user_id, client_task_id)
);

CREATE INDEX idx_tasks_tenant_user ON tasks (tenant_id, user_id);

-- ── 研究报告 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reports (
    id                UUID PRIMARY KEY,
    task_id           UUID NOT NULL REFERENCES tasks(id),
    version           INT NOT NULL,              -- 同一 task 内递增
    knowledge_version TEXT NOT NULL,             -- 复现依据
    content           JSONB NOT NULL,            -- 结构化报告
    status            TEXT NOT NULL DEFAULT 'draft',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (task_id, version)
);

CREATE INDEX idx_reports_task ON reports (task_id);

-- ── 用户个人健康档案（字段级 KMS 加密）────────────────────────

CREATE TABLE IF NOT EXISTS profiles (
    id            UUID PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id),
    kind          TEXT NOT NULL,                 -- basic / condition / medication / allergy / goal / exercise
    content_enc   BYTEA NOT NULL,               -- KMS 密文
    source        TEXT NOT NULL DEFAULT 'user_stated',
    confidence    REAL,
    version       INT NOT NULL DEFAULT 1,
    superseded_at TIMESTAMPTZ,
    deleted_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_profiles_user ON profiles (user_id);

-- ── 纠错反馈 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS feedback (
    id          UUID PRIMARY KEY,
    user_id     UUID NOT NULL,
    report_id   UUID NOT NULL REFERENCES reports(id),
    claim_id    TEXT NOT NULL,
    issue_type  TEXT NOT NULL,                   -- wrong_citation / unsupported / outdated / other
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_feedback_report ON feedback (report_id);
