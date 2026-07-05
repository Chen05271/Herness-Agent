"""Postgres Hereness v2 向量检索测试辅助。"""

from __future__ import annotations


class FakeEmbeddingClient:
    """确定性低维向量，用于集成测试（无需真实 Embeddings API）。"""

    def __init__(self, dimensions: int = 3) -> None:
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_one(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        lower = text.lower()
        if self._dimensions == 3:
            if "python" in lower:
                return [0.92, 0.08, 0.0]
            if "java" in lower:
                return [0.08, 0.92, 0.0]
            return [0.0, 0.0, 1.0]

        base = [0.0] * self._dimensions
        for index, char in enumerate(lower[: self._dimensions]):
            base[index] = (ord(char) % 97) / 97.0
        return base
