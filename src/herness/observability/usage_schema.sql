-- LLM token 用量（按任务记录，按 session / user 汇总）
CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'orchestrator',
    status TEXT NOT NULL DEFAULT '',
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    requests INT NOT NULL DEFAULT 0,
    tool_calls INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (task_id, source)
);

CREATE INDEX IF NOT EXISTS idx_usage_events_session ON usage_events (session_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_user ON usage_events (user_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_user_session ON usage_events (user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_created ON usage_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_events_source ON usage_events (source);
