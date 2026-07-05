"""Worker 外部工具 — HTTP、文件读取、受限 Python 执行。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

from herness.config import Settings


class WorkerToolError(Exception):
    """Worker 工具执行失败。"""


def resolve_safe_path(base_dir: str, path: str) -> Path:
    """解析路径并确保落在 base_dir 内，防止目录穿越。"""
    base = Path(base_dir).resolve()
    target = (base / path).resolve()
    if base != target and base not in target.parents:
        raise WorkerToolError(f"路径越界：{path!r} 不在允许目录 {base} 内")
    return target


async def http_request(
    url: str,
    *,
    method: str = "GET",
    body: str | None = None,
    headers: dict[str, str] | None = None,
    settings: Settings,
) -> str:
    """发起 HTTP 请求，返回响应体文本（超长截断）。"""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WorkerToolError(f"不支持的 URL 协议：{parsed.scheme!r}")

    max_bytes = settings.worker_tools_http_max_bytes
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.request(
            method.upper(),
            url,
            content=body.encode() if body else None,
            headers=headers,
        )

    text = response.text
    if len(text.encode()) > max_bytes:
        text = text[:max_bytes] + f"\n…（截断，上限 {max_bytes} 字节）"
    return f"HTTP {response.status_code}\n{text}"


async def read_text_file(path: str, *, settings: Settings) -> str:
    """读取 base_dir 内的文本文件。"""
    base_dir = settings.worker_tools_file_base_dir.strip()
    if not base_dir:
        raise WorkerToolError("文件工具未启用（WORKER_TOOLS_FILE_BASE_DIR 未配置）")

    target = resolve_safe_path(base_dir, path)
    if not target.is_file():
        raise WorkerToolError(f"文件不存在：{path!r}")

    max_bytes = settings.worker_tools_file_max_bytes
    data = target.read_bytes()
    if len(data) > max_bytes:
        raise WorkerToolError(f"文件过大（{len(data)} 字节，上限 {max_bytes}）")
    return data.decode(errors="replace")


async def run_python_code(code: str, *, settings: Settings) -> str:
    """在子进程中执行 Python 代码片段，返回 stdout/stderr。"""
    if not settings.worker_tools_code_enabled:
        raise WorkerToolError("代码执行工具未启用（WORKER_TOOLS_CODE_ENABLED=false）")

    timeout = settings.worker_tools_code_timeout_seconds
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise WorkerToolError(f"代码执行超时（{timeout}s）") from exc

    parts: list[str] = []
    if stdout:
        parts.append(f"stdout:\n{stdout.decode(errors='replace')}")
    if stderr:
        parts.append(f"stderr:\n{stderr.decode(errors='replace')}")
    parts.append(f"exit_code: {proc.returncode}")
    return "\n".join(parts)
