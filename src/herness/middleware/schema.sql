-- Herness Agent 中台表结构（PostgresMiddleware 启动时自动执行）

CREATE TABLE IF NOT EXISTS memories (
    user_id TEXT PRIMARY KEY,
    version INT NOT NULL DEFAULT 1,
    summary TEXT NOT NULL DEFAULT '',
    slices JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS beliefs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    fact TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_beliefs_user_id ON beliefs (user_id);

CREATE TABLE IF NOT EXISTS task_results (
    task_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    output JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_results_user_id ON task_results (user_id);

CREATE TABLE IF NOT EXISTS task_contexts (
    task_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dreaming_jobs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dreaming_jobs_status ON dreaming_jobs (status);
