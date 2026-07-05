"""Worker 外部工具单元测试。"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from herness.agents.tools import (
    WorkerToolError,
    http_request,
    read_text_file,
    resolve_safe_path,
    run_python_code,
)
from herness.config import Settings


@pytest.fixture
def tool_settings(tmp_path: Path) -> Settings:
    return Settings(
        worker_tools_http_max_bytes=1024,
        worker_tools_file_base_dir=str(tmp_path),
        worker_tools_file_max_bytes=4096,
        worker_tools_code_enabled=True,
        worker_tools_code_timeout_seconds=5.0,
    )


def test_resolve_safe_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(WorkerToolError, match="路径越界"):
        resolve_safe_path(str(tmp_path), "../outside.txt")


@pytest.mark.asyncio
async def test_read_text_file_success(tool_settings: Settings, tmp_path: Path) -> None:
    sample = tmp_path / "note.txt"
    sample.write_text("hello worker", encoding="utf-8")
    assert await read_text_file("note.txt", settings=tool_settings) == "hello worker"


@pytest.mark.asyncio
async def test_read_text_file_missing(tool_settings: Settings) -> None:
    with pytest.raises(WorkerToolError, match="文件不存在"):
        await read_text_file("missing.txt", settings=tool_settings)


@pytest.mark.asyncio
async def test_http_request_success(tool_settings: Settings) -> None:
    mock_response = MagicMock()
    mock_response.text = '{"ok": true}'
    mock_response.status_code = 200
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("herness.agents.tools.httpx.AsyncClient", return_value=mock_client):
        body = await http_request("https://example.com/api", settings=tool_settings)
    assert "HTTP 200" in body
    assert '"ok": true' in body


@pytest.mark.asyncio
async def test_http_request_rejects_non_http(tool_settings: Settings) -> None:
    with pytest.raises(WorkerToolError, match="不支持的 URL 协议"):
        await http_request("file:///etc/passwd", settings=tool_settings)


@pytest.mark.asyncio
async def test_run_python_code_success(tool_settings: Settings) -> None:
    output = await run_python_code("print(2 + 2)", settings=tool_settings)
    assert "stdout:" in output
    assert "4" in output
    assert "exit_code: 0" in output


@pytest.mark.asyncio
async def test_run_python_code_disabled() -> None:
    settings = Settings(worker_tools_code_enabled=False)
    with pytest.raises(WorkerToolError, match="未启用"):
        await run_python_code("print(1)", settings=settings)
