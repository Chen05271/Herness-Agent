"""Harness 侧 ppt-master 一键构建 — 从 JSON 数据生成完整 PPTX。"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from herness.agents.tools import WorkerToolError, resolve_safe_path
from herness.config import Settings

_PYTHON = "py"
_PYTHON_VERSION = "-3.11"

_COLORS = {
    "bg": "#F7F6F2",
    "secondary_bg": "#FFFFFF",
    "primary": "#1B2A41",
    "accent": "#D04A02",
    "success": "#2E7D32",
    "text": "#111827",
    "text_secondary": "#374151",
    "text_tertiary": "#6B7280",
    "border": "#D6D3CE",
}

_TITLE_FONT = "Georgia, SimSun, serif"
_BODY_FONT = "Microsoft YaHei, Arial, sans-serif"


def _now_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _skill_dir() -> Path:
    return (_repo_root() / ".agents" / "skills" / "ppt-master").resolve()


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _wan(value: int) -> str:
    return f"{value / 10000:.1f}万"


def _fmt_int(value: int) -> str:
    return f"{value:,}"


async def _run(cmd: list[str], *, cwd: Path, timeout_s: int = 600) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise WorkerToolError(f"ppt-master 执行超时（{timeout_s}s）") from exc
    return (
        proc.returncode,
        (stdout or b"").decode(errors="replace"),
        (stderr or b"").decode(errors="replace"),
    )


def _write_spec_lock(project_dir: Path) -> None:
    text = f"""## canvas
- viewBox: 0 0 1280 720
- format: PPT 16:9

## mode
- mode: pyramid

## visual_style
- visual_style: data-journalism

## colors
- bg: {_COLORS['bg']}
- secondary_bg: {_COLORS['secondary_bg']}
- primary: {_COLORS['primary']}
- accent: {_COLORS['accent']}
- secondary_accent: {_COLORS['success']}
- text: {_COLORS['text']}
- text_secondary: {_COLORS['text_secondary']}
- text_tertiary: {_COLORS['text_tertiary']}
- border: {_COLORS['border']}
- success: {_COLORS['success']}
- warning: {_COLORS['accent']}

## typography
- font_family: Microsoft YaHei, Arial, sans-serif
- title_family: Georgia, SimSun, serif
- body_family: Microsoft YaHei, Arial, sans-serif
- emphasis_family: {_TITLE_FONT}
- code_family: Consolas, "Courier New", monospace
- body: 24
- title: 42
- subtitle: 32
- lead: 30
- cover_title: 76
- hero_number: 56
- annotation: 18
- chart_annotation: 16
- footnote: 16

## page_rhythm
- P01: anchor
- P02: dense
- P03: dense
- P04: dense
- P05: dense
- P06: breathing
- P07: anchor

## pptx_structure
- mode: flat

## page_charts
- P02: kpi_cards
- P03: line_chart
- P04: column_chart
- P05: consulting_table
- P07: project_schedule_table

## forbidden
- Mixing icon libraries
- mask, <style>, class, external CSS, <foreignObject>, textPath, @font-face, <animate*>, <set>, <script>, event attributes, <iframe>
- HTML named entities in text
"""
    (project_dir / "spec_lock.md").write_text(text, encoding="utf-8")


def _svg_header() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
        'width="1280" height="720">\n'
        f'  <rect x="0" y="0" width="1280" height="720" fill="{_COLORS["bg"]}"/>\n'
    )


def _svg_footer(page: str) -> str:
    return (
        f'  <text x="1232" y="672" text-anchor="end" font-family="{_BODY_FONT}" '
        f'font-size="16" fill="{_COLORS["text_tertiary"]}">{page}</text>\n'
        "</svg>\n"
    )


def _page_title(y: int, title: str, lead: str = "") -> str:
    lines = [
        f'  <text x="48" y="{y}" font-family="{_TITLE_FONT}" font-size="42" '
        f'fill="{_COLORS["primary"]}">{_escape_xml(title)}</text>\n'
    ]
    if lead:
        lines.append(
            f'  <text x="48" y="{y + 34}" font-family="{_BODY_FONT}" font-size="30" '
            f'fill="{_COLORS["text_secondary"]}">{_escape_xml(lead)}</text>\n'
        )
    return "".join(lines)


def _build_cover(data: dict[str, Any]) -> str:
    meta = data["meta"]
    kpis = data["kpis"]
    month = meta["month"]
    return (
        _svg_header()
        + f'  <rect x="48" y="88" width="1184" height="2" fill="{_COLORS["primary"]}" opacity="0.9"/>\n'
        + _page_title(128, f"{month} 全渠道经营月报", "快速复盘 · 渠道拆解 · 商品与行动")
        + f'  <text x="48" y="260" font-family="{_BODY_FONT}" font-size="18" fill="{_COLORS["text_tertiary"]}">GMV（元）</text>\n'
        + f'  <text x="48" y="332" font-family="{_TITLE_FONT}" font-size="76" fill="{_COLORS["text"]}">{_fmt_int(kpis["gmv"])}</text>\n'
        + f'  <rect x="48" y="352" width="520" height="1" fill="{_COLORS["border"]}"/>\n'
        + f'  <text x="48" y="476" font-family="{_BODY_FONT}" font-size="16" fill="{_COLORS["text_tertiary"]}">订单</text>\n'
        + f'  <text x="48" y="520" font-family="{_TITLE_FONT}" font-size="56" fill="{_COLORS["primary"]}">{_fmt_int(kpis["orders"])}</text>\n'
        + f'  <text x="420" y="476" font-family="{_BODY_FONT}" font-size="16" fill="{_COLORS["text_tertiary"]}">买家</text>\n'
        + f'  <text x="420" y="520" font-family="{_TITLE_FONT}" font-size="56" fill="{_COLORS["primary"]}">{_fmt_int(kpis["buyers"])}</text>\n'
        + f'  <text x="792" y="476" font-family="{_BODY_FONT}" font-size="16" fill="{_COLORS["text_tertiary"]}">新客</text>\n'
        + f'  <text x="792" y="520" font-family="{_TITLE_FONT}" font-size="56" fill="{_COLORS["success"]}">{_fmt_int(kpis["new_buyers"])}</text>\n'
        + _svg_footer("P01")
    )


def _build_kpi_page(data: dict[str, Any]) -> str:
    kpis = data["kpis"]
    cards = [
        ("GMV", _wan(kpis["gmv"])),
        ("订单", _fmt_int(kpis["orders"])),
        ("买家", _fmt_int(kpis["buyers"])),
        ("客单价", f"{kpis['aov']} 元"),
        ("转化率", _pct(kpis["conversion_rate"])),
        ("退款率", _pct(kpis["refund_rate"])),
        ("新客", _fmt_int(kpis["new_buyers"])),
    ]
    body = _svg_header() + _page_title(96, "KPI 总览", "6 月核心指标一眼扫全局")
    x_positions = [48, 360, 672, 984]
    y_positions = [180, 380]
    idx = 0
    for row in range(2):
        for col in range(4):
            if idx >= len(cards):
                break
            label, value = cards[idx]
            x = x_positions[col]
            y = y_positions[row]
            body += (
                f'  <rect x="{x}" y="{y}" width="280" height="150" fill="{_COLORS["secondary_bg"]}" '
                f'stroke="{_COLORS["border"]}"/>\n'
                f'  <text x="{x + 20}" y="{y + 40}" font-family="{_BODY_FONT}" font-size="18" '
                f'fill="{_COLORS["text_tertiary"]}">{_escape_xml(label)}</text>\n'
                f'  <text x="{x + 20}" y="{y + 100}" font-family="{_TITLE_FONT}" font-size="42" '
                f'fill="{_COLORS["primary"]}">{_escape_xml(value)}</text>\n'
            )
            idx += 1
    body += _svg_footer("P02")
    return body


def _build_trend_page(data: dict[str, Any]) -> str:
    trend = data["trend_daily"]
    values = [item["gmv"] for item in trend]
    vmax = max(values)
    vmin = min(values)
    chart_left, chart_top, chart_width, chart_height = 80, 200, 1080, 360
    points: list[str] = []
    labels: list[str] = []
    for i, item in enumerate(trend):
        x = chart_left + int(i * chart_width / max(len(trend) - 1, 1))
        ratio = (item["gmv"] - vmin) / max(vmax - vmin, 1)
        y = chart_top + chart_height - int(ratio * chart_height)
        points.append(f"{x},{y}")
        labels.append((x, item["date"][5:], _wan(item["gmv"])))
    polyline = " ".join(points)
    body = (
        _svg_header()
        + _page_title(96, "日趋势（GMV）", "大促周附近峰值明显，月末继续上行")
        + f'  <line x1="{chart_left}" y1="{chart_top + chart_height}" x2="{chart_left + chart_width}" '
        f'y2="{chart_top + chart_height}" stroke="{_COLORS["border"]}" stroke-width="2"/>\n'
        + f'  <polyline points="{polyline}" fill="none" stroke="{_COLORS["primary"]}" stroke-width="4"/>\n'
    )
    for x, label, value in labels:
        body += (
            f'  <text x="{x}" y="{chart_top + chart_height + 28}" text-anchor="middle" '
            f'font-family="{_BODY_FONT}" font-size="16" fill="{_COLORS["text_secondary"]}">{label}</text>\n'
            f'  <text x="{x}" y="{chart_top + chart_height + 52}" text-anchor="middle" '
            f'font-family="{_BODY_FONT}" font-size="16" fill="{_COLORS["text_tertiary"]}">{value}</text>\n'
        )
    body += _svg_footer("P03")
    return body


def _build_channel_page(data: dict[str, Any]) -> str:
    channels = data["channel_split"]
    vmax = max(item["gmv"] for item in channels)
    chart_left, chart_bottom, chart_width, chart_height = 120, 560, 900, 320
    body = _svg_header() + _page_title(96, "渠道拆分", "抖音贡献最高，私域更适合承接复购")
    bar_width = 140
    gap = 60
    for i, item in enumerate(channels):
        x = chart_left + i * (bar_width + gap)
        height = int(item["gmv"] / vmax * chart_height)
        y = chart_bottom - height
        body += (
            f'  <rect x="{x}" y="{y}" width="{bar_width}" height="{height}" fill="{_COLORS["primary"]}"/>\n'
            f'  <text x="{x + bar_width / 2:.0f}" y="{chart_bottom + 28}" text-anchor="middle" '
            f'font-family="{_BODY_FONT}" font-size="18" fill="{_COLORS["text"]}">{_escape_xml(item["channel"])}</text>\n'
            f'  <text x="{x + bar_width / 2:.0f}" y="{y - 12}" text-anchor="middle" '
            f'font-family="{_BODY_FONT}" font-size="16" fill="{_COLORS["text_secondary"]}">{_wan(item["gmv"])}</text>\n'
        )
    body += _svg_footer("P04")
    return body


def _build_products_page(data: dict[str, Any]) -> str:
    products = data["top_products"]
    body = _svg_header() + _page_title(96, "TOP 商品", "爆款A贡献最大，新品C退款率需关注")
    headers = ["SKU", "商品", "GMV", "订单", "退款率"]
    col_x = [48, 180, 420, 620, 860]
    row_y = 180
    for i, header in enumerate(headers):
        body += (
            f'  <text x="{col_x[i]}" y="{row_y}" font-family="{_BODY_FONT}" font-size="18" '
            f'fill="{_COLORS["text_tertiary"]}">{header}</text>\n'
        )
    body += f'  <rect x="48" y="190" width="1184" height="1" fill="{_COLORS["border"]}"/>\n'
    for r, item in enumerate(products, start=1):
        y = row_y + 40 * r
        values = [
            item["sku"],
            item["name"],
            _wan(item["gmv"]),
            _fmt_int(item["orders"]),
            _pct(item["refund_rate"]),
        ]
        for i, value in enumerate(values):
            body += (
                f'  <text x="{col_x[i]}" y="{y}" font-family="{_BODY_FONT}" font-size="20" '
                f'fill="{_COLORS["text"]}">{_escape_xml(str(value))}</text>\n'
            )
    body += _svg_footer("P05")
    return body


def _build_insights_page(data: dict[str, Any]) -> str:
    insights = data["insights"]
    body = _svg_header() + _page_title(120, "关键洞察", "峰值来源 · 渠道风险 · 私域机会")
    y = 220
    for insight in insights:
        body += (
            f'  <rect x="48" y="{y - 24}" width="8" height="32" fill="{_COLORS["accent"]}"/>\n'
            f'  <text x="72" y="{y}" font-family="{_BODY_FONT}" font-size="24" '
            f'fill="{_COLORS["text"]}">{_escape_xml(insight)}</text>\n'
        )
        y += 72
    body += _svg_footer("P06")
    return body


def _build_actions_page(data: dict[str, Any]) -> str:
    actions = data["actions_next_month"]
    body = _svg_header() + _page_title(96, "7 月行动计划", "把洞察落到可执行动作")
    headers = ["动作", "负责人", "截止日期"]
    col_x = [48, 760, 980]
    row_y = 180
    for i, header in enumerate(headers):
        body += (
            f'  <text x="{col_x[i]}" y="{row_y}" font-family="{_BODY_FONT}" font-size="18" '
            f'fill="{_COLORS["text_tertiary"]}">{header}</text>\n'
        )
    body += f'  <rect x="48" y="190" width="1184" height="1" fill="{_COLORS["border"]}"/>\n'
    for r, item in enumerate(actions, start=1):
        y = row_y + 48 * r
        values = [item["action"], item["owner"], item["due"]]
        for i, value in enumerate(values):
            body += (
                f'  <text x="{col_x[i]}" y="{y}" font-family="{_BODY_FONT}" font-size="22" '
                f'fill="{_COLORS["text"]}">{_escape_xml(str(value))}</text>\n'
            )
    body += _svg_footer("P07")
    return body


def _write_svgs(project_dir: Path, data: dict[str, Any]) -> None:
    svg_dir = project_dir / "svg_output"
    pages = [
        ("01_cover.svg", _build_cover(data)),
        ("02_kpi.svg", _build_kpi_page(data)),
        ("03_trend.svg", _build_trend_page(data)),
        ("04_channels.svg", _build_channel_page(data)),
        ("05_products.svg", _build_products_page(data)),
        ("06_insights.svg", _build_insights_page(data)),
        ("07_actions.svg", _build_actions_page(data)),
    ]
    for name, content in pages:
        (svg_dir / name).write_text(content, encoding="utf-8")


def _write_notes(project_dir: Path, data: dict[str, Any]) -> None:
    month = data["meta"]["month"]
    notes = project_dir / "notes" / "total.md"
    notes.write_text(
        "\n".join(
            [
                f"# {month} 经营月报",
                "",
                "## P01 封面",
                f"- 本月 GMV {_fmt_int(data['kpis']['gmv'])} 元。",
                "",
                "## P02 KPI",
                "- 展示订单、买家、转化、退款等核心指标。",
                "",
                "## P03 趋势",
                "- 解读大促周与月末峰值。",
                "",
                "## P04 渠道",
                "- 对比抖音、天猫、京东、私域贡献。",
                "",
                "## P05 商品",
                "- 聚焦 TOP 商品与退款率。",
                "",
                "## P06 洞察",
                "- 总结三条关键洞察。",
                "",
                "## P07 行动",
                "- 明确下月动作、负责人与截止日期。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _validate_monthly_report_json(data: dict[str, Any]) -> None:
    required = ("meta", "kpis", "trend_daily", "channel_split", "top_products", "insights", "actions_next_month")
    missing = [key for key in required if key not in data]
    if missing:
        raise WorkerToolError(f"数据 JSON 缺少字段：{', '.join(missing)}")


async def build_pptx_from_source(
    *,
    source_path: str,
    filename: str,
    task_id: str,
    settings: Settings,
) -> str:
    """读取 JSON 源文件，走 ppt-master 导出链路生成 PPTX。"""
    if not settings.worker_tools_ppt_enabled:
        raise WorkerToolError("PPT 工具未启用（WORKER_TOOLS_PPT_ENABLED=false）")

    base_dir = settings.worker_tools_output_base_dir.strip()
    if not base_dir:
        raise WorkerToolError("PPT 输出目录未配置（WORKER_TOOLS_OUTPUT_BASE_DIR）")

    file_base = settings.worker_tools_file_base_dir.strip()
    if not file_base:
        raise WorkerToolError("文件工具未启用（WORKER_TOOLS_FILE_BASE_DIR 未配置）")

    skill_dir = _skill_dir()
    if not skill_dir.is_dir():
        raise WorkerToolError("未找到 ppt-master skill 目录：.agents/skills/ppt-master")

    source_file = resolve_safe_path(file_base, source_path)
    if not source_file.is_file():
        raise WorkerToolError(f"源文件不存在：{source_path!r}")

    try:
        data = json.loads(source_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkerToolError(f"源文件不是合法 JSON：{exc}") from exc

    if not isinstance(data, dict):
        raise WorkerToolError("源文件 JSON 顶层必须是对象")

    _validate_monthly_report_json(data)

    task_dir = resolve_safe_path(base_dir, task_id)
    projects_root = task_dir / "ppt_master_projects"
    projects_root.mkdir(parents=True, exist_ok=True)

    project_name = f"harness_{_now_stamp()}"
    init_cmd = [
        _PYTHON,
        _PYTHON_VERSION,
        str(skill_dir / "scripts/project_manager.py"),
        "init",
        project_name,
        "--format",
        "ppt169",
        "--dir",
        str(projects_root),
    ]
    code, stdout, stderr = await _run(init_cmd, cwd=_repo_root())
    if code != 0:
        raise WorkerToolError(f"ppt-master 项目初始化失败：{(stderr or stdout).strip()}")

    match = re.search(r"Project created:\s*(.+)", stdout)
    if match:
        project_dir = Path(match.group(1).strip())
    else:
        candidates = sorted(projects_root.glob(f"{project_name}_ppt169_*"))
        if not candidates:
            raise WorkerToolError("ppt-master 项目初始化成功但未找到项目目录")
        project_dir = candidates[-1]

    import_cmd = [
        _PYTHON,
        _PYTHON_VERSION,
        str(skill_dir / "scripts/project_manager.py"),
        "import-sources",
        str(project_dir),
        str(source_file),
        "--copy",
    ]
    code, stdout, stderr = await _run(import_cmd, cwd=_repo_root())
    if code != 0:
        raise WorkerToolError(f"ppt-master 导入源文件失败：{(stderr or stdout).strip()}")

    _write_spec_lock(project_dir)
    _write_svgs(project_dir, data)
    _write_notes(project_dir, data)

    for script_name in ("total_md_split.py", "finalize_svg.py"):
        cmd = [_PYTHON, _PYTHON_VERSION, str(skill_dir / f"scripts/{script_name}"), str(project_dir)]
        code, stdout, stderr = await _run(cmd, cwd=skill_dir)
        if code != 0:
            raise WorkerToolError(f"ppt-master {script_name} 失败：{(stderr or stdout).strip()}")

    out_path = resolve_safe_path(str(task_dir), filename)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    export_cmd = [
        _PYTHON,
        _PYTHON_VERSION,
        str(skill_dir / "scripts/svg_to_pptx.py"),
        str(project_dir),
        "-o",
        str(out_path),
        "-t",
        "fade",
        "-a",
        "none",
    ]
    code, stdout, stderr = await _run(export_cmd, cwd=skill_dir)
    if code != 0:
        raise WorkerToolError(f"ppt-master 导出失败：{(stderr or stdout).strip()}")

    rel = out_path.resolve().relative_to(Path(base_dir).resolve())
    return str(rel).replace("\\", "/")


async def export_project_to_pptx(
    *,
    project_path: str,
    filename: str,
    task_id: str,
    settings: Settings,
) -> str:
    """导出已有 ppt-master 项目目录为 PPTX。"""
    if not settings.worker_tools_ppt_enabled:
        raise WorkerToolError("PPT 工具未启用（WORKER_TOOLS_PPT_ENABLED=false）")

    base_dir = settings.worker_tools_output_base_dir.strip()
    if not base_dir:
        raise WorkerToolError("PPT 输出目录未配置（WORKER_TOOLS_OUTPUT_BASE_DIR）")

    skill_dir = _skill_dir()
    if not skill_dir.is_dir():
        raise WorkerToolError("未找到 ppt-master skill 目录")

    project_dir = Path(project_path)
    if not project_dir.is_absolute():
        project_dir = (_repo_root() / project_path).resolve()
    if not (project_dir / "spec_lock.md").is_file():
        raise WorkerToolError(f"不是有效的 ppt-master 项目：{project_path}")

    task_dir = resolve_safe_path(base_dir, task_id)
    out_path = resolve_safe_path(str(task_dir), filename)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    for script_name in ("total_md_split.py", "finalize_svg.py"):
        cmd = [_PYTHON, _PYTHON_VERSION, str(skill_dir / f"scripts/{script_name}"), str(project_dir)]
        code, stdout, stderr = await _run(cmd, cwd=skill_dir)
        if code != 0:
            raise WorkerToolError(f"ppt-master {script_name} 失败：{(stderr or stdout).strip()}")

    export_cmd = [
        _PYTHON,
        _PYTHON_VERSION,
        str(skill_dir / "scripts/svg_to_pptx.py"),
        str(project_dir),
        "-o",
        str(out_path),
    ]
    code, stdout, stderr = await _run(export_cmd, cwd=skill_dir)
    if code != 0:
        raise WorkerToolError(f"ppt-master 导出失败：{(stderr or stdout).strip()}")

    rel = out_path.resolve().relative_to(Path(base_dir).resolve())
    return str(rel).replace("\\", "/")
