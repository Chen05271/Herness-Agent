"""从 PydanticAI 运行结果提取 Worker 工具调用记录。"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic_ai.messages import ToolReturnPart

from herness.models.worker import WorkerToolInvocation

_TOOL_ERROR_MARKERS = (
    "工具错误",
    "请求失败",
    "执行超时",
    "路径越界",
    "文件不存在",
    "文件过大",
    "未启用",
    "不支持的 URL 协议",
)

_HTTP_ERROR_RE = re.compile(r"HTTP\s+[45]\d{2}\b")
_EXIT_CODE_RE = re.compile(r"exit_code:\s*(\d+)")


def _content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def is_tool_result_error(tool_name: str, result: str) -> bool:
    """判断工具返回是否表示失败。"""
    if not result.strip():
        return True
    if any(marker in result for marker in _TOOL_ERROR_MARKERS):
        return True
    if _HTTP_ERROR_RE.search(result):
        return True
    if tool_name == "run_python_code_tool" or tool_name == "run_python_code":
        match = _EXIT_CODE_RE.search(result)
        if match and match.group(1) != "0":
            return True
    return False


def extract_tool_invocations(run_result: Any) -> list[WorkerToolInvocation]:
    """从 AgentRunResult.all_messages() 提取工具调用与返回。"""
    invocations: list[WorkerToolInvocation] = []
    all_messages = getattr(run_result, "all_messages", None)
    if all_messages is None:
        return invocations

    for message in all_messages():
        for part in getattr(message, "parts", ()):
            if not isinstance(part, ToolReturnPart):
                continue
            result_text = _content_to_str(part.content)
            invocations.append(
                WorkerToolInvocation(
                    tool_name=part.tool_name,
                    result=result_text,
                    error=is_tool_result_error(part.tool_name, result_text),
                )
            )
    return invocations
