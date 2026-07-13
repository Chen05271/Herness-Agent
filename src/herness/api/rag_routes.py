"""RAG 知识库 HTTP 路由 — 入库与检索。"""

from fastapi import APIRouter, Depends, HTTPException, Request

from herness.api.schemas import (
    RagGraphCommunityResponse,
    RagGraphEdgeResponse,
    RagGraphEntityResponse,
    RagGraphResponse,
    RagHitResponse,
    RagIngestRequest,
    RagIngestResponse,
    RagSearchRequest,
    RagSearchResponse,
)
from herness.api.security import require_api_key
from herness.middleware.embeddings import build_embedding_client
from herness.rag.ingest import build_community_summaries, ingest_text

router = APIRouter(
    prefix="/v1/rag",
    tags=["rag"],
    dependencies=[Depends(require_api_key)],
)


def _get_middleware(request: Request) -> object:
    return request.app.state.middleware


def _resolve_kb(middleware: object) -> object | None:
    inner = getattr(middleware, "_inner", middleware)
    store = getattr(inner, "knowledge_store", None)
    if store is not None:
        return store
    return getattr(inner, "_kb_store", None)


@router.post("/ingest", response_model=RagIngestResponse)
async def rag_ingest(body: RagIngestRequest, request: Request) -> RagIngestResponse:
    settings = request.app.state.settings
    if not settings.rag_enabled:
        raise HTTPException(status_code=503, detail="RAG 未启用（RAG_ENABLED=false）")

    middleware = _get_middleware(request)
    store = _resolve_kb(middleware)
    if store is None:
        raise HTTPException(status_code=503, detail="当前中台不支持 RAG 知识库")

    embedding_client = None
    if settings.rag_vector_enabled:
        embedding_client = build_embedding_client(settings)

    collection_name = body.collection_name or body.collection_id
    chunk_ids = await ingest_text(
        store,
        collection_id=body.collection_id,
        collection_name=collection_name,
        text=body.text,
        source=body.source,
        settings=settings,
        embedding_client=embedding_client,
        persona=body.persona,
        user_id=body.user_id,
    )

    communities = 0
    if body.build_communities:
        communities = await build_community_summaries(store, collection_id=body.collection_id)

    return RagIngestResponse(
        chunk_ids=chunk_ids,
        collection_id=body.collection_id,
        communities_built=communities,
    )


@router.post("/search", response_model=RagSearchResponse)
async def rag_search(body: RagSearchRequest, request: Request) -> RagSearchResponse:
    settings = request.app.state.settings
    if not settings.rag_enabled:
        raise HTTPException(status_code=503, detail="RAG 未启用（RAG_ENABLED=false）")

    middleware = _get_middleware(request)
    search = getattr(middleware, "search_knowledge_base", None)
    if search is None:
        inner = getattr(middleware, "_inner", middleware)
        search = getattr(inner, "search_knowledge_base", None)
    if search is None:
        raise HTTPException(status_code=503, detail="当前中台不支持 RAG 检索")

    result = await search(
        body.query,
        collection_id=body.collection_id,
        user_id=body.user_id,
    )
    hits = [
        RagHitResponse(
            chunk_id=hit.chunk_id,
            content=hit.content,
            score=hit.score,
            source=hit.source,
            retrieval_channel=hit.retrieval_channel,
        )
        for hit in result.hits
    ]
    return RagSearchResponse(
        query=result.query,
        collection_id=result.collection_id,
        hits=hits,
        coarse_count=result.coarse_count,
        fine_count=result.fine_count,
    )


@router.get("/graph", response_model=RagGraphResponse)
async def rag_graph(
    request: Request,
    collection_id: str = "default",
) -> RagGraphResponse:
    settings = request.app.state.settings
    if not settings.rag_enabled:
        raise HTTPException(status_code=503, detail="RAG 未启用（RAG_ENABLED=false）")

    middleware = _get_middleware(request)
    store = _resolve_kb(middleware)
    if store is None:
        raise HTTPException(status_code=503, detail="当前中台不支持 RAG 知识库")

    entities = await store.list_entities(collection_id)
    edges = await store.list_edges(collection_id)
    communities = await store.list_communities(collection_id)

    return RagGraphResponse(
        collection_id=collection_id,
        entities=[
            RagGraphEntityResponse(
                name=item["name"],
                entity_type=item.get("entity_type", "concept"),
                chunk_ids=[int(x) for x in (item.get("chunk_ids") or [])],
            )
            for item in entities
        ],
        edges=[
            RagGraphEdgeResponse(
                source=item["source"],
                target=item["target"],
                relation=item.get("relation", "related_to"),
                chunk_id=item.get("chunk_id"),
            )
            for item in edges
        ],
        communities=[
            RagGraphCommunityResponse(
                community_id=item["community_id"],
                summary=item["summary"],
                entity_names=list(item.get("entity_names") or []),
            )
            for item in communities
        ],
        entity_count=len(entities),
        edge_count=len(edges),
        community_count=len(communities),
    )
