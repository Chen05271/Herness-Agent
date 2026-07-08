"""文档分块 — 字符窗口 + 语义边界优先，保留重叠。"""

from __future__ import annotations

import re

_MARKDOWN_HEADER = re.compile(r"(?m)^(#{1,6}\s.+)$")
# 分块时优先在以下位置截断（越靠前优先级越高）
_BREAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\n\n+"),       # 段落
    re.compile(r"\n"),          # 换行
    re.compile(r"[。！？；]"),   # 中文句末
    re.compile(r"[.!?;]\s"),    # 英文句末
)


def _markdown_sections(text: str) -> list[str]:
    """按 Markdown 标题拆成段落，标题与正文保持在同一段。"""
    parts = _MARKDOWN_HEADER.split(text)
    if len(parts) == 1:
        return [text]

    sections: list[str] = []
    preamble = parts[0].strip()
    if preamble:
        sections.append(preamble)

    for idx in range(1, len(parts), 2):
        header = parts[idx]
        body = parts[idx + 1] if idx + 1 < len(parts) else ""
        section = f"{header}\n{body}".strip()
        if section:
            sections.append(section)
    return sections


def _find_soft_break(text: str, start: int, target: int, *, min_ratio: float = 0.5) -> int:
    """在 [start, target] 窗口内向后找最佳截断点；找不到则硬切 target。"""
    if target >= len(text):
        return len(text)

    min_pos = start + max(1, int((target - start) * min_ratio))
    window = text[start:target]

    for pattern in _BREAK_PATTERNS:
        last_match: re.Match[str] | None = None
        for match in pattern.finditer(window):
            pos = start + match.end()
            if pos >= min_pos:
                last_match = match
        if last_match is not None:
            return start + last_match.end()

    return target


def _chunk_segment(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """对单段文本做边界感知滑动窗口切分。"""
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        target = min(start + chunk_size, len(text))
        end = _find_soft_break(text, start, target)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        next_start = end - chunk_overlap
        start = max(start + 1, next_start)
    return chunks


def chunk_text(
    text: str,
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[str]:
    """将长文本切分为重叠块；优先在段落/换行/句末截断，Markdown 按标题分段。"""
    cleaned = text.strip()
    if not cleaned:
        return []

    sections = _markdown_sections(cleaned)
    if len(sections) == 1 and len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    for section in _markdown_sections(cleaned):
        section = section.strip()
        if not section:
            continue
        chunks.extend(
            _chunk_segment(section, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        )
    return chunks
