"""Persona → 知识库集合映射。"""

from __future__ import annotations

from typing import Literal

Persona = Literal["consumer", "merchant"]

DEFAULT_KB_COLLECTION = "default"

PERSONA_KB_COLLECTIONS: dict[Persona, str] = {
    "consumer": "consumer",
    "merchant": "merchant",
}


def resolve_kb_collection(
    persona: Persona | str | None = None,
    *,
    collection: str | None = None,
) -> str:
    """解析检索目标集合；显式 collection 优先，否则按 persona 映射。"""
    if collection and collection.strip():
        return collection.strip()
    if persona in PERSONA_KB_COLLECTIONS:
        return PERSONA_KB_COLLECTIONS[persona]  # type: ignore[index]
    return DEFAULT_KB_COLLECTION
