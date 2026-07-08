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

-- Hereness v3 冲突消歧：superseded 信念不参与检索
ALTER TABLE beliefs
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

CREATE INDEX IF NOT EXISTS idx_beliefs_user_status ON beliefs (user_id, status);

-- Hereness 全文检索（启动时幂等迁移）
ALTER TABLE beliefs
    ADD COLUMN IF NOT EXISTS fact_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(fact, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_beliefs_fact_tsv ON beliefs USING GIN (fact_tsv);

-- Hereness v2 向量扩展与列由 PostgresMiddleware._ensure_vector_schema 按需创建

CREATE TABLE IF NOT EXISTS task_results (
    task_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    output JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_results_user_id ON task_results (user_id);

CREATE INDEX IF NOT EXISTS idx_task_results_session_id ON task_results ((metadata->>'session_id'));

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

-- RAG 知识库表由 PostgresKnowledgeStore.ensure_schema 按需创建（见 rag/store/postgres.py）

CREATE INDEX IF NOT EXISTS idx_dreaming_jobs_status ON dreaming_jobs (status);

-- LLM token 用量（按任务记录，按 session / user 汇总）
CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    requests INT NOT NULL DEFAULT 0,
    tool_calls INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_events_session ON usage_events (session_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_user ON usage_events (user_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_created ON usage_events (created_at DESC);
