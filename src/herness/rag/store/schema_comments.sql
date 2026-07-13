-- RAG 知识库表与字段注释（幂等，可重复执行）

COMMENT ON TABLE kb_collections IS 'RAG 知识库集合（按业务或 persona 划分）';
COMMENT ON COLUMN kb_collections.id IS '集合唯一标识';
COMMENT ON COLUMN kb_collections.name IS '集合显示名称';
COMMENT ON COLUMN kb_collections.persona IS '绑定的 persona（consumer / merchant 等，可空）';
COMMENT ON COLUMN kb_collections.created_at IS '集合创建时间';

COMMENT ON TABLE kb_chunks IS 'RAG 文档分块，支持全文与向量检索';
COMMENT ON COLUMN kb_chunks.id IS '主键';
COMMENT ON COLUMN kb_chunks.collection_id IS '所属知识库集合 ID';
COMMENT ON COLUMN kb_chunks.content IS '分块正文';
COMMENT ON COLUMN kb_chunks.metadata IS '分块元数据 JSON（标题、页码等）';
COMMENT ON COLUMN kb_chunks.source IS '原始文档来源标识或 URL';
COMMENT ON COLUMN kb_chunks.created_at IS '分块入库时间';
COMMENT ON COLUMN kb_chunks.content_tsv IS '全文检索向量（由 content 自动生成的 tsvector）';

COMMENT ON TABLE kb_entities IS 'RAG 图谱实体节点';
COMMENT ON COLUMN kb_entities.id IS '主键';
COMMENT ON COLUMN kb_entities.collection_id IS '所属知识库集合 ID';
COMMENT ON COLUMN kb_entities.name IS '实体名称';
COMMENT ON COLUMN kb_entities.entity_type IS '实体类型：concept / person / product 等';
COMMENT ON COLUMN kb_entities.chunk_ids IS '关联的分块 ID 数组';

COMMENT ON TABLE kb_edges IS 'RAG 图谱实体关系边';
COMMENT ON COLUMN kb_edges.id IS '主键';
COMMENT ON COLUMN kb_edges.collection_id IS '所属知识库集合 ID';
COMMENT ON COLUMN kb_edges.source_name IS '源实体名称';
COMMENT ON COLUMN kb_edges.target_name IS '目标实体名称';
COMMENT ON COLUMN kb_edges.relation IS '关系类型，默认 related_to';
COMMENT ON COLUMN kb_edges.chunk_id IS '支撑该关系的分块 ID（可空）';

COMMENT ON TABLE kb_communities IS 'RAG 图谱社区摘要（Graph RAG 聚类结果）';
COMMENT ON COLUMN kb_communities.id IS '主键';
COMMENT ON COLUMN kb_communities.collection_id IS '所属知识库集合 ID';
COMMENT ON COLUMN kb_communities.community_id IS '社区业务标识';
COMMENT ON COLUMN kb_communities.summary IS '社区级摘要文本';
COMMENT ON COLUMN kb_communities.entity_names IS '社区包含的实体名称列表';
COMMENT ON COLUMN kb_communities.summary_tsv IS '社区摘要全文检索向量（自动生成）';
