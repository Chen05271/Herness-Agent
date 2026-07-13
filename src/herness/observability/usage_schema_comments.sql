-- Token 用量表与字段注释（幂等，可重复执行）

COMMENT ON TABLE usage_events IS 'LLM Token 用量事件，按任务记录、按 session/user 汇总';
COMMENT ON COLUMN usage_events.id IS '主键';
COMMENT ON COLUMN usage_events.task_id IS '关联任务 ID';
COMMENT ON COLUMN usage_events.user_id IS '用户唯一标识';
COMMENT ON COLUMN usage_events.session_id IS '会话 ID（与 TaskRequest.session_id 一致）';
COMMENT ON COLUMN usage_events.source IS '用量来源：orchestrator / dreaming / rag 等';
COMMENT ON COLUMN usage_events.status IS '任务终态：completed / failed / cancelled 等';
COMMENT ON COLUMN usage_events.input_tokens IS '输入 Token 数';
COMMENT ON COLUMN usage_events.output_tokens IS '输出 Token 数';
COMMENT ON COLUMN usage_events.total_tokens IS '总 Token 数（input + output）';
COMMENT ON COLUMN usage_events.requests IS 'LLM 请求次数';
COMMENT ON COLUMN usage_events.tool_calls IS '工具调用次数';
COMMENT ON COLUMN usage_events.created_at IS '用量记录时间';
