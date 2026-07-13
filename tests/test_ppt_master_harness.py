"""ppt-master harness 构建工具测试。"""

import json
from pathlib import Path

import pytest

from herness.agents.ppt_master_harness import build_pptx_from_source
from herness.agents.tools import WorkerToolError
from herness.config import Settings


@pytest.fixture
def harness_settings(tmp_path: Path) -> Settings:
    outputs = tmp_path / "outputs"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    outputs.mkdir()
    sample = {
        "meta": {"month": "2026-06", "region": "全渠道"},
        "kpis": {
            "gmv": 12850000,
            "orders": 84210,
            "buyers": 56120,
            "aov": 153,
            "conversion_rate": 0.031,
            "refund_rate": 0.012,
            "new_buyers": 18200,
        },
        "trend_daily": [
            {"date": "2026-06-01", "gmv": 360000, "orders": 2380},
            {"date": "2026-06-30", "gmv": 590000, "orders": 3780},
        ],
        "channel_split": [
            {"channel": "抖音", "gmv": 5620000, "orders": 35600},
            {"channel": "天猫", "gmv": 3920000, "orders": 26800},
        ],
        "top_products": [
            {"sku": "A-001", "name": "爆款A", "gmv": 2150000, "orders": 14200, "refund_rate": 0.009},
        ],
        "insights": ["测试洞察"],
        "actions_next_month": [
            {"action": "测试动作", "owner": "运营", "due": "2026-07-10"},
        ],
    }
    (data_dir / "sample.json").write_text(
        json.dumps(sample, ensure_ascii=False),
        encoding="utf-8",
    )
    return Settings(
        worker_tools_ppt_enabled=True,
        worker_tools_output_base_dir=str(outputs),
        worker_tools_file_base_dir=str(data_dir),
    )


@pytest.mark.asyncio
async def test_build_pptx_from_source_creates_file(harness_settings: Settings) -> None:
    rel_path = await build_pptx_from_source(
        source_path="sample.json",
        filename="report.pptx",
        task_id="task-123",
        settings=harness_settings,
    )
    assert rel_path == "task-123/report.pptx"
    file_path = Path(harness_settings.worker_tools_output_base_dir) / rel_path
    assert file_path.is_file()
    assert file_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_build_pptx_from_source_rejects_invalid_json(harness_settings: Settings) -> None:
    bad = Path(harness_settings.worker_tools_file_base_dir) / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    with pytest.raises(WorkerToolError, match="合法 JSON"):
        await build_pptx_from_source(
            source_path="bad.json",
            filename="bad.pptx",
            task_id="task-1",
            settings=harness_settings,
        )
