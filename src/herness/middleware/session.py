"""会话历史 — 同 session 内前序任务摘要，注入 Supervisor。"""

from datetime import datetime

from pydantic import BaseModel, Field


class SessionHistoryEntry(BaseModel):
    """单条会话历史记录。"""

    task_id: str
    input: str = Field(default="", description="用户当次输入")
    answer: str = Field(default="", description="任务最终答复或 Worker 摘要")
    created_at: datetime | None = None


def format_session_history(entries: list[SessionHistoryEntry]) -> str:
    """转为可注入 Supervisor prompt 的文本块（按时间正序）。"""
    if not entries:
        return "（本会话暂无历史任务）"

    lines = ["## 会话历史（同 session 内前序任务）"]
    for index, entry in enumerate(entries, start=1):
        lines.append(f"### 前序任务 {index}")
        if entry.input:
            lines.append(f"用户：{entry.input}")
        if entry.answer:
            lines.append(f"答复：{entry.answer}")
    return "\n".join(lines)
