"""将 skill 解析结果写入任务 metadata。"""

from __future__ import annotations

from typing import Any

from herness.config import Settings
from herness.skills.loader import detect_skills_from_input, resolve_skills
from herness.skills.registry import get_skill_binding, normalize_skill_name


def _normalize_skill_names(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get("skills")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def enrich_metadata_with_skills(
    metadata: dict[str, Any],
    *,
    settings: Settings | None = None,
    user_input: str = "",
) -> dict[str, Any]:
    """解析 skills 列表、自动检测、合并工具白名单，写入 _resolved_skills。"""
    meta = dict(metadata or {})
    if not settings or not settings.skills_enabled:
        return meta

    explicit = _normalize_skill_names(meta)
    detected = detect_skills_from_input(user_input, settings=settings) if user_input else []
    skill_names: list[str] = []
    seen: set[str] = set()
    for name in explicit + detected:
        normalized = normalize_skill_name(name)
        if normalized not in seen:
            seen.add(normalized)
            skill_names.append(normalized)

    if not skill_names:
        return meta

    resolved_defs = resolve_skills(skill_names, settings=settings)
    resolved_payload: list[dict[str, str]] = []
    required_tools: set[str] = set()

    for skill in resolved_defs:
        binding = get_skill_binding(skill.name)
        worker_kind = binding.worker_kind if binding else "default"
        if binding:
            required_tools |= set(binding.required_tools)
        resolved_payload.append(
            {
                "name": skill.name,
                "description": skill.description,
                "content": skill.content,
                "worker_kind": worker_kind,
            }
        )

    meta["_resolved_skills"] = resolved_payload

    if required_tools:
        current = meta.get("allowed_tools")
        if isinstance(current, list):
            merged = sorted(set(str(t) for t in current) | required_tools)
            meta["allowed_tools"] = merged
        elif current is None:
            meta["allowed_tools"] = sorted(required_tools)

    return meta


def supervisor_skills_block(metadata: dict[str, Any]) -> str:
    """为 Supervisor 生成技能路由提示块。"""
    resolved = metadata.get("_resolved_skills")
    if not isinstance(resolved, list) or not resolved:
        return ""

    lines = ["## 已启用技能"]
    for item in resolved:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        description = item.get("description", "")
        worker_kind = item.get("worker_kind", "default")
        lines.append(f"- **{name}**：{description}")
        lines.append(f"  - 相关任务请委派给 `{worker_kind}` Worker")
    lines.append("- 涉及文件产物时，Worker 应将路径写入 artifacts")
    return "\n".join(lines)


def worker_skill_instructions(metadata: dict[str, Any]) -> str:
    """合并所有已启用 skill 的正文，供 Worker 注入。"""
    resolved = metadata.get("_resolved_skills")
    if not isinstance(resolved, list) or not resolved:
        return ""

    blocks: list[str] = []
    for item in resolved:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "skill")
        content = item.get("content", "")
        if content:
            blocks.append(f"### 技能：{name}\n{content}")
    return "\n\n".join(blocks)
