-- 中台表与字段注释（幂等，可重复执行）

COMMENT ON TABLE memories IS '用户预合成全局记忆，由 Dreaming 管线异步更新';
COMMENT ON COLUMN memories.user_id IS '用户唯一标识';
COMMENT ON COLUMN memories.version IS '记忆版本号，每次 Dreaming 合并后递增';
COMMENT ON COLUMN memories.summary IS '面向 Supervisor 的全局记忆摘要';
COMMENT ON COLUMN memories.slices IS '分类记忆切片 JSON 数组（facts / preferences 等）';
COMMENT ON COLUMN memories.updated_at IS '记忆最后更新时间';

COMMENT ON TABLE beliefs IS 'Hereness 用户信念/事实库，支持全文与向量检索';
COMMENT ON COLUMN beliefs.id IS '主键';
COMMENT ON COLUMN beliefs.user_id IS '用户唯一标识';
COMMENT ON COLUMN beliefs.fact IS '信念或事实文本';
COMMENT ON COLUMN beliefs.source IS '来源：manual / dreaming / task 等';
COMMENT ON COLUMN beliefs.confidence IS '置信度，取值 0.0–1.0';
COMMENT ON COLUMN beliefs.created_at IS '信念创建时间';
COMMENT ON COLUMN beliefs.status IS '状态：active 参与检索，superseded 已被更新信念取代';
COMMENT ON COLUMN beliefs.fact_tsv IS '全文检索向量（由 fact 自动生成的 tsvector）';

COMMENT ON TABLE task_results IS 'Worker 任务输出持久化，供会话历史与 Dreaming 读取';
COMMENT ON COLUMN task_results.task_id IS '任务唯一标识';
COMMENT ON COLUMN task_results.user_id IS '用户唯一标识';
COMMENT ON COLUMN task_results.output IS 'Worker 结构化输出 JSON';
COMMENT ON COLUMN task_results.metadata IS '任务元数据（含 session_id、persona 等）';
COMMENT ON COLUMN task_results.created_at IS '结果写入时间';

COMMENT ON TABLE task_contexts IS '任务级读写上下文，Worker/Critic 工具链共享';
COMMENT ON COLUMN task_contexts.task_id IS '任务唯一标识';
COMMENT ON COLUMN task_contexts.user_id IS '用户唯一标识';
COMMENT ON COLUMN task_contexts.context IS '任务执行上下文 JSON';
COMMENT ON COLUMN task_contexts.updated_at IS '上下文最后更新时间';

COMMENT ON TABLE dreaming_jobs IS 'Dreaming 异步记忆提炼任务队列';
COMMENT ON COLUMN dreaming_jobs.id IS '主键';
COMMENT ON COLUMN dreaming_jobs.user_id IS '用户唯一标识';
COMMENT ON COLUMN dreaming_jobs.task_id IS '触发提炼的已完成任务 ID';
COMMENT ON COLUMN dreaming_jobs.status IS '队列状态：pending / processing / done / failed';
COMMENT ON COLUMN dreaming_jobs.created_at IS '任务入队时间';
