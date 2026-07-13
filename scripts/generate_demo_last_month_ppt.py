import asyncio
import json
from pathlib import Path

from herness.agents.ppt_master_harness import build_pptx_from_source
from herness.config import Settings


def main() -> None:
    settings = Settings()
    data_path = Path("outputs/demo_last_month.json")
    if not data_path.is_file():
        raise SystemExit(f"缺少数据文件：{data_path}")

    # 确保文件工具可读
    settings.worker_tools_file_base_dir = str(data_path.parent.resolve())
    settings.worker_tools_output_base_dir = str(Path("outputs").resolve())
    settings.worker_tools_ppt_enabled = True

    rel = asyncio.run(
        build_pptx_from_source(
            source_path=data_path.name,
            filename="demo_last_month_report.pptx",
            task_id="demo_last_month",
            settings=settings,
        )
    )
    print(rel)


if __name__ == "__main__":
    main()
