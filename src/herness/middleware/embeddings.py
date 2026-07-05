"""OpenAI 兼容 Embeddings 客户端 — Hereness v2 向量语义检索。"""

from __future__ import annotations

from typing import Protocol

import httpx

from herness.config import Settings


class EmbeddingClient(Protocol):
    """信念向量嵌入协议（便于测试注入）。"""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]: ...


class OpenAIEmbeddingClient:
    """调用 OpenAI 兼容 /v1/embeddings 接口。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or "dummy"
        self._model = model
        self._dimensions = dimensions
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        payload: dict[str, object] = {
            "model": self._model,
            "input": texts,
        }
        if self._dimensions is not None:
            payload["dimensions"] = self._dimensions

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        items = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]


def build_embedding_client(settings: Settings) -> OpenAIEmbeddingClient:
    """根据配置构建 Embeddings 客户端（base_url / api_key 可回退到 LLM 配置）。"""
    base_url = settings.embedding_base_url or settings.llm_base_url
    api_key = settings.embedding_api_key or settings.llm_api_key
    return OpenAIEmbeddingClient(
        base_url=base_url,
        api_key=api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
