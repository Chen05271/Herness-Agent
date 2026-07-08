"""Re-rank — identifier 加权 + 可选 Cross-Encoder API。"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from herness.rag.grep.retrieval import grep_match_score

logger = logging.getLogger(__name__)


class RerankClient(Protocol):
    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...


class HeuristicReranker:
    """GrepRAG 式 identifier 加权 + 多信号融合精排。"""

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        scores: list[float] = []
        for doc in documents:
            scores.append(grep_match_score(query, doc))
        return scores


class CrossEncoderReranker:
    """调用 OpenAI 兼容 rerank API（如 Cohere / 自建 bge-reranker 网关）。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or "dummy"
        self._model = model
        self._timeout = timeout

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []

        payload = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/rerank",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            results = sorted(data.get("results", []), key=lambda r: r.get("index", 0))
            return [float(r.get("relevance_score", 0.0)) for r in results]
        except Exception as exc:
            logger.warning("Cross-Encoder rerank 失败，回退启发式: %s", exc)
            return await HeuristicReranker().rerank(query, documents)


class HybridReranker:
    """融合 RRF / vector / grep / 可选 cross-encoder 信号。"""

    def __init__(
        self,
        *,
        cross_encoder: RerankClient | None = None,
        cross_encoder_weight: float = 0.5,
    ) -> None:
        self._cross_encoder = cross_encoder
        self._cross_encoder_weight = cross_encoder_weight
        self._heuristic = HeuristicReranker()

    async def rerank_candidates(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        documents = [c.get("content", "") for c in candidates]
        heuristic_scores = await self._heuristic.rerank(query, documents)

        ce_scores: list[float] | None = None
        if self._cross_encoder is not None:
            ce_scores = await self._cross_encoder.rerank(query, documents)

        for idx, cand in enumerate(candidates):
            rrf = float(cand.get("rrf_score", 0.0))
            vec = float(cand.get("vector_similarity", 0.0))
            grep = float(heuristic_scores[idx])
            base = rrf * 0.35 + vec * 0.35 + grep * 0.30

            if ce_scores is not None:
                ce = float(ce_scores[idx])
                final = base * (1 - self._cross_encoder_weight) + ce * self._cross_encoder_weight
            else:
                final = base

            cand["rerank_score"] = final
            cand["grep_score"] = grep

        return sorted(candidates, key=lambda c: c.get("rerank_score", 0.0), reverse=True)
