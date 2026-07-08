"""RAG 知识库单元测试。"""

import pytest

from herness.config import Settings
from herness.middleware.stub import InMemoryMiddleware
from herness.rag.collections import resolve_kb_collection
from herness.rag.grep.retrieval import extract_identifiers, grep_match_score
from herness.rag.graph.extractor import (
    expand_subgraph_chunk_ids,
    extract_entities_from_text,
    extract_relations_from_text,
    link_query_entities,
)
from herness.rag.ingest import build_community_summaries, ingest_text
from herness.rag.pipeline import RagPipeline
from herness.rag.fusion import reciprocal_rank_fusion
from herness.rag.rerank import HeuristicReranker, HybridReranker
from herness.rag.store.memory import InMemoryKnowledgeStore
from tests.fake_embeddings import FakeEmbeddingClient


@pytest.fixture
def rag_settings() -> Settings:
    return Settings(
        rag_enabled=True,
        rag_vector_enabled=True,
        rag_grep_enabled=True,
        rag_graph_enabled=True,
        rag_community_enabled=True,
        rag_rerank_enabled=True,
        rag_coarse_top_k=20,
        rag_fine_top_k=10,
        rag_final_top_k=3,
        rag_vector_min_similarity=0.5,
        embedding_dimensions=3,
    )


@pytest.fixture
async def rag_middleware(rag_settings: Settings) -> InMemoryMiddleware:
    mw = InMemoryMiddleware(rag_enabled=True)
    mw.configure_rag(rag_settings, embedding_client=FakeEmbeddingClient(dimensions=3))
    return mw


async def test_ingest_and_fts_search(rag_settings: Settings) -> None:
    store = InMemoryKnowledgeStore()
    await ingest_text(
        store,
        collection_id="default",
        collection_name="默认",
        text="Herness Agent 是多 Agent 协作框架，支持 RAG 知识库检索。",
        source="test",
        settings=rag_settings,
    )
    hits = await store.fts_search("default", "RAG 知识库", limit=5, min_rank=0.01)
    assert len(hits) >= 1
    assert "RAG" in hits[0]["content"]


async def test_grep_identifier_scoring() -> None:
    score = grep_match_score(
        "查询 OrderService 接口",
        "OrderService 负责处理订单创建与查询。",
        fts_rank=0.1,
    )
    assert score > 0.1


def test_extract_identifiers() -> None:
    ids = extract_identifiers("调用 getOrderById 查询 SKU-ABC-001")
    assert "getOrderById" in ids or any("SKU" in i for i in ids)


async def test_graph_entity_extraction_and_expansion() -> None:
    entities = extract_entities_from_text("「蓝莓」属于浆果类商品", chunk_id=1)
    assert any(e.name == "蓝莓" for e in entities)

    relations = extract_relations_from_text("蓝莓属于浆果类", chunk_id=1)
    assert len(relations) >= 1

    markdown_entities = extract_entities_from_text(
        "[洛川苹果] --产自--> [陕西洛川]",
        chunk_id=2,
    )
    assert any(e.name == "洛川苹果" for e in markdown_entities)
    assert any(e.name == "陕西洛川" for e in markdown_entities)

    markdown_relations = extract_relations_from_text(
        "[洛川苹果] --产自--> [陕西洛川]",
        chunk_id=2,
    )
    assert len(markdown_relations) == 1
    assert markdown_relations[0].source == "洛川苹果"
    assert markdown_relations[0].target == "陕西洛川"
    assert markdown_relations[0].relation == "产自"

    sample_graph = """
洛川苹果产自陕西洛川。
[洛川苹果] --产自--> [陕西洛川]
[订单A1024] --包含--> [洛川苹果]
[demo-shop商家] --销售--> [洛川苹果]
[订单A1024] --属于--> [demo-shop商家]
"""
    sample_relations = extract_relations_from_text(sample_graph, chunk_id=3)
    assert len(sample_relations) >= 4

    entity_dicts = [{"name": "蓝莓", "chunk_ids": [1]}, {"name": "浆果类", "chunk_ids": [1]}]
    edges = [{"source": "蓝莓", "target": "浆果类", "relation": "related_to"}]
    linked = link_query_entities("蓝莓商品", [e["name"] for e in entity_dicts])
    assert "蓝莓" in linked

    chunk_scores = expand_subgraph_chunk_ids(["蓝莓"], entity_dicts, edges)
    assert 1 in chunk_scores


async def test_rag_pipeline_end_to_end(rag_middleware: InMemoryMiddleware) -> None:
    store = rag_middleware.knowledge_store
    settings = Settings(
        rag_enabled=True,
        rag_vector_enabled=True,
        rag_grep_enabled=True,
        rag_graph_enabled=True,
        rag_coarse_top_k=20,
        rag_fine_top_k=10,
        rag_final_top_k=2,
        rag_vector_min_similarity=0.5,
        embedding_dimensions=3,
    )
    client = FakeEmbeddingClient(dimensions=3)
    await ingest_text(
        store,
        collection_id="consumer",
        collection_name="C端",
        text="消费者可在 App 中查询订单状态与物流信息。",
        source="faq",
        settings=settings,
        embedding_client=client,
        persona="consumer",
    )
    await ingest_text(
        store,
        collection_id="consumer",
        collection_name="C端",
        text="「订单追踪」功能支持实时查看配送进度。",
        source="faq",
        settings=settings,
        embedding_client=client,
    )

    pipeline = RagPipeline(store, settings, embedding_client=client)
    result = await pipeline.search("订单追踪", collection_id="consumer")
    assert result.hits
    assert any("订单" in hit.content for hit in result.hits)


async def test_rrf_fusion() -> None:
    scores = reciprocal_rank_fusion([[3, 1, 2], [2, 3, 1]])
    # chunk 3 在两路中分别排第 1、2 位，综合分最高
    assert scores[3] > scores[2] > scores[1]


async def test_heuristic_reranker() -> None:
    reranker = HybridReranker()
    candidates = [
        {"id": 1, "content": "无关内容", "rrf_score": 0.5, "vector_similarity": 0.1},
        {"id": 2, "content": "OrderService 处理订单", "rrf_score": 0.3, "vector_similarity": 0.2},
    ]
    ranked = await reranker.rerank_candidates("OrderService 订单", candidates)
    assert ranked[0]["id"] == 2


async def test_community_summaries(rag_settings: Settings) -> None:
    store = InMemoryKnowledgeStore()
    await ingest_text(
        store,
        collection_id="default",
        collection_name="默认",
        text="实体A与实体B在同一文档块。实体C属于实体D。",
        settings=rag_settings,
    )
    count = await build_community_summaries(store, collection_id="default", min_entities=2)
    assert count >= 0


async def test_middleware_search_knowledge_base(rag_middleware: InMemoryMiddleware) -> None:
    store = rag_middleware.knowledge_store
    await ingest_text(
        store,
        collection_id="default",
        collection_name="默认",
        text="RAG 检索支持粗检索与细检索以及 Re-rank。",
        settings=Settings(rag_enabled=True, rag_vector_enabled=False),
    )
    result = await rag_middleware.search_knowledge_base("粗检索 Re-rank")
    assert result.hits
    assert "RAG" in result.hits[0].content


def test_resolve_kb_collection_by_persona() -> None:
    assert resolve_kb_collection("consumer") == "consumer"
    assert resolve_kb_collection("merchant") == "merchant"
    assert resolve_kb_collection("consumer", collection="custom") == "custom"


async def test_grep_search_channel(rag_settings: Settings) -> None:
    store = InMemoryKnowledgeStore()
    await ingest_text(
        store,
        collection_id="default",
        collection_name="默认",
        text="def fetch_task_context(): pass",
        settings=rag_settings,
    )
    hits = await store.grep_search("default", "fetch_task_context", limit=5)
    assert hits
    assert "fetch_task_context" in hits[0]["content"]


async def test_list_graph_snapshot(rag_settings: Settings) -> None:
    store = InMemoryKnowledgeStore()
    await ingest_text(
        store,
        collection_id="consumer",
        collection_name="消费者",
        text="Herness Agent 支持 RAG 知识库。订单 ORD-001 由仓库发货。",
        settings=rag_settings,
    )
    await build_community_summaries(store, collection_id="consumer", min_entities=1)

    entities = await store.list_entities("consumer")
    edges = await store.list_edges("consumer")
    communities = await store.list_communities("consumer")

    assert entities
    assert all("name" in e and "entity_type" in e for e in entities)
    assert isinstance(edges, list)
    assert isinstance(communities, list)
