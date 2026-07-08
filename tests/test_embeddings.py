"""Embeddings 客户端单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from herness.config import Settings
from herness.middleware.embeddings import OpenAIEmbeddingClient, build_embedding_client


@pytest.mark.asyncio
async def test_openai_embedding_client_parses_response() -> None:
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "data": [
            {"index": 0, "embedding": [0.1, 0.2, 0.3]},
            {"index": 1, "embedding": [0.4, 0.5, 0.6]},
        ]
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    client = OpenAIEmbeddingClient(
        base_url="http://embed.test/v1",
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=3,
    )

    with patch("herness.middleware.embeddings.httpx.AsyncClient", return_value=mock_client):
        vectors = await client.embed(["hello", "world"])

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["json"] == {
        "model": "text-embedding-3-small",
        "input": ["hello", "world"],
        "dimensions": 3,
    }


def test_build_embedding_client_falls_back_to_llm_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        llm_base_url="http://llm.test/v1",
        llm_api_key="llm-key",
        dashscope_api_key="",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )
    client = build_embedding_client(settings)
    assert client._base_url == "http://llm.test/v1"
    assert client._api_key == "llm-key"
    assert client._model == "text-embedding-3-small"
    assert client._dimensions == 1536
