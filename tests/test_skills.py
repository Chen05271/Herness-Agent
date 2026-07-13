"""Skill 加载与 metadata 注入测试。"""

from pathlib import Path

import pytest

from herness.config import Settings
from herness.models.task import TaskRequest
from herness.personas import prepare_task_request
from herness.skills.enrich import enrich_metadata_with_skills, supervisor_skills_block
from herness.skills.loader import detect_skills_from_input, load_skill, resolve_skills
from herness.skills.registry import normalize_skill_name


@pytest.fixture
def skill_settings(tmp_path: Path) -> Settings:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "ppt-master"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ppt-master\ndescription: 测试 PPT Master 技能\n---\n\n# 测试技能正文\n",
        encoding="utf-8",
    )
    return Settings(
        skills_enabled=True,
        skills_base_dir=str(skills_dir),
        worker_tools_ppt_enabled=True,
        worker_tools_output_base_dir=str(tmp_path / "outputs"),
    )


def test_load_skill_parses_frontmatter(skill_settings: Settings) -> None:
    skill = load_skill("ppt-master", settings=skill_settings)
    assert skill.name == "ppt-master"
    assert skill.description == "测试 PPT Master 技能"
    assert "测试技能正文" in skill.content


def test_detect_skills_from_input(skill_settings: Settings) -> None:
    names = detect_skills_from_input("请帮我做一份Q3销售分析PPT", settings=skill_settings)
    assert names == ["ppt-master"]


def test_enrich_metadata_with_skills_merges_tools(skill_settings: Settings) -> None:
    meta = enrich_metadata_with_skills(
        {"allowed_tools": ["fetch_task_context"]},
        settings=skill_settings,
        user_input="生成汇报PPT",
    )
    assert "ppt-master" in [item["name"] for item in meta["_resolved_skills"]]
    assert "ppt_master_build_pptx" in meta["allowed_tools"]
    assert "read_text_file" in meta["allowed_tools"]


def test_prepare_task_request_auto_detects_ppt_skill(skill_settings: Settings) -> None:
    request = TaskRequest(
        user_id="user-1",
        session_id="consumer-user-1:demo",
        input="根据这份数据制作分析幻灯片",
        metadata={"persona": "consumer"},
    )
    prepared = prepare_task_request(request, settings=skill_settings)
    resolved = prepared.metadata["_resolved_skills"]
    assert resolved[0]["worker_kind"] == "presentation"
    assert supervisor_skills_block(prepared.metadata)


def test_resolve_skills_deduplicates(skill_settings: Settings) -> None:
    skills = resolve_skills(
        ["ppt-master", "ppt-master"],
        settings=skill_settings,
    )
    assert len(skills) == 1


def test_legacy_skill_alias_maps_to_ppt_master() -> None:
    assert normalize_skill_name("data-analysis-ppt") == "ppt-master"
