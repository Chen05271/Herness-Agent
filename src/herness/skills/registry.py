"""Skill 元数据注册表 — 将 skill 名称映射到 Worker 路由与工具依赖。"""

from __future__ import annotations

from dataclasses import dataclass

from herness.models.worker import WorkerKind

PPT_MASTER_SKILL_NAME = "ppt-master"

# 旧 skill 名仅作兼容别名，统一路由到 ppt-master
LEGACY_SKILL_ALIASES: dict[str, str] = {
    "data-analysis-ppt": PPT_MASTER_SKILL_NAME,
}

PPT_MASTER_KEYWORDS: tuple[str, ...] = (
    "ppt",
    "powerpoint",
    "幻灯片",
    "演示文稿",
    "汇报",
    "分析报告",
    "制作ppt",
    "做ppt",
    "生成ppt",
    "ppt-master",
    "ppt master",
    "pptmaster",
    "做一份ppt",
    "做一份PPT",
    "生成一份ppt",
    "生成一份PPT",
    "把这个文档做成ppt",
    "把这个文档做成PPT",
)


@dataclass(frozen=True)
class SkillBinding:
    """单个 skill 的运行时绑定信息。"""

    name: str
    worker_kind: WorkerKind
    required_tools: frozenset[str]
    auto_detect_keywords: tuple[str, ...] = ()


SKILL_BINDINGS: dict[str, SkillBinding] = {
    PPT_MASTER_SKILL_NAME: SkillBinding(
        name=PPT_MASTER_SKILL_NAME,
        worker_kind="presentation",
        required_tools=frozenset(
            {
                "read_text_file",
                "ppt_master_build_pptx",
                "ppt_master_export_project",
                "ppt_master_export_svg_to_pptx",
                "run_python_code",
            }
        ),
        auto_detect_keywords=PPT_MASTER_KEYWORDS,
    ),
}


def normalize_skill_name(name: str) -> str:
    """将旧 skill 名映射到当前 canonical 名称。"""
    stripped = name.strip()
    return LEGACY_SKILL_ALIASES.get(stripped, stripped)


def get_skill_binding(name: str) -> SkillBinding | None:
    return SKILL_BINDINGS.get(normalize_skill_name(name))
