import asyncio

from herness.agents.ppt_master_tools import export_svg_to_pptx
from herness.config import Settings


async def main() -> None:
    settings = Settings()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">'
        '<rect width="1280" height="720" fill="#0B0F1A"/>'
        '<text x="80" y="120" fill="#EAF1FF" font-family="Segoe UI, Microsoft YaHei UI, sans-serif" '
        'font-size="48" font-weight="700">ppt-master 工具联通测试</text>'
        "</svg>"
    )

    rel = await export_svg_to_pptx(
        svg=svg,
        filename="ppt_master_tool_smoke.pptx",
        task_id="local_smoke",
        settings=settings,
    )
    print(rel)


if __name__ == "__main__":
    asyncio.run(main())

