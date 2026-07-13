"""加载 .agents/skills 下的 SKILL.md 并解析 frontmatter。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from herness.config import Settings
from herness.skills.registry import SKILL_BINDINGS, get_skill_binding

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_MAX_SKILL_BODY_CHARS = 12_000


@dataclass(frozen=True)
class SkillDefinition:
    """已解析的 Skill 定义。"""

    name: str
    description: str
    content: str
    path: Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_skills_base_dir(settings: Settings) -> Path:
    configured = (settings.skills_base_dir or "").strip()
    if configured:
        base = Path(configured)
        if not base.is_absolute():
            base = _project_root() / base
        return base.resolve()
    return (_project_root() / ".agents" / "skills").resolve()


def parse_skill_markdown(text: str) -> tuple[dict[str, str], str]:
    """解析 SKILL.md 的 YAML frontmatter 与正文。"""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()

    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        frontmatter[key.strip()] = value.strip().strip('"').strip("'")

    body = text[match.end() :].strip()
    return frontmatter, body


def _truncate_skill_body(body: str) -> str:
    if len(body) <= _MAX_SKILL_BODY_CHARS:
        return body
    return (
        body[:_MAX_SKILL_BODY_CHARS]
        + f"\n\n…（技能正文已截断，保留前 {_MAX_SKILL_BODY_CHARS} 字符）"
    )


def load_skill(name: str, *, settings: Settings) -> SkillDefinition:
    """按名称加载单个 skill。"""
    base_dir = resolve_skills_base_dir(settings)
    skill_path = base_dir / name / "SKILL.md"
    if not skill_path.is_file():
        raise FileNotFoundError(f"Skill 不存在：{name!r}（路径 {skill_path}）")

    raw = skill_path.read_text(encoding="utf-8")
    frontmatter, body = parse_skill_markdown(raw)
    return SkillDefinition(
        name=frontmatter.get("name", name),
        description=frontmatter.get("description", ""),
        content=_truncate_skill_body(body),
        path=skill_path,
    )


def list_available_skills(*, settings: Settings) -> list[dict[str, str]]:
    """列出 skills 目录下所有可用 skill（仅返回已注册绑定的）。"""
    if not settings.skills_enabled:
        return []

    base_dir = resolve_skills_base_dir(settings)
    if not base_dir.is_dir():
        return []

    items: list[dict[str, str]] = []
    for binding_name in sorted(SKILL_BINDINGS):
        skill_path = base_dir / binding_name / "SKILL.md"
        if not skill_path.is_file():
            continue
        try:
            skill = load_skill(binding_name, settings=settings)
        except OSError:
            continue
        binding = get_skill_binding(binding_name)
        items.append(
            {
                "name": skill.name,
                "description": skill.description,
                "worker_kind": binding.worker_kind if binding else "default",
            }
        )
    return items


def detect_skills_from_input(user_input: str, *, settings: Settings) -> list[str]:
    """根据用户输入关键词自动匹配 skill。"""
    if not settings.skills_enabled or not user_input.strip():
        return []

    lower = user_input.lower()
    matched: list[str] = []
    for binding in SKILL_BINDINGS.values():
        if any(keyword in lower for keyword in binding.auto_detect_keywords):
            matched.append(binding.name)
    return matched


def resolve_skills(
    skill_names: list[str],
    *,
    settings: Settings,
) -> list[SkillDefinition]:
    """加载并去重 skill 列表。"""
    if not settings.skills_enabled or not skill_names:
        return []

    seen: set[str] = set()
    resolved: list[SkillDefinition] = []
    for name in skill_names:
        normalized = name.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(load_skill(normalized, settings=settings))
    return resolved
