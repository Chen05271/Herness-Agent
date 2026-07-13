"""PPT Master 工具封装 — 将 SVG 通过 ppt-master 导出为 PPTX。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from herness.agents.tools import WorkerToolError, resolve_safe_path
from herness.config import Settings


def _now_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _skill_dir() -> Path:
    # repo-root/.agents/skills/ppt-master
    # 这里不要读环境变量，保持项目内确定性路径（skill 由 skills 安装到 .agents/skills）
    return Path(".agents/skills/ppt-master").resolve()


def _write_min_spec_lock_md(project_dir: Path) -> None:
    # 按 templates/spec_lock_reference.md 的可解析格式写一个最小 flat 项目锁
    # 目的：让 svg_to_pptx.py 识别这是“新格式 flat 项目”，而不是 legacy baseline
    text = """\
## canvas
- viewBox: 0 0 1280 720
- format: PPT 16:9

## mode
- mode: briefing

## visual_style
- visual_style: swiss-minimal

## colors
- bg: #0B0F1A
- secondary_bg: #0D142B
- primary: #7C3AED
- accent: #22D3EE
- text: #EAF1FF
- text_secondary: #A9B7DD
- border: #26365F

## typography
- font_family: "Segoe UI", "Microsoft YaHei UI", Arial, sans-serif
- body: 24
- title: 42
- subtitle: 32
- annotation: 18
- footnote: 16

## page_rhythm
- P01: anchor

## pptx_structure
- mode: flat

## forbidden
- `mask`, `<style>`, `class`, external CSS, `<foreignObject>`, `textPath`, `@font-face`, `<animate*>`, `<set>`, `<script>` / event attributes, `<iframe>`
- HTML named entities in text; write raw Unicode and escape XML reserved characters
"""
    (project_dir / "spec_lock.md").write_text(text, encoding="utf-8")


async def _run(cmd: list[str], *, cwd: Path, timeout_s: int) -> tuple[int, str, str]:
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
    return proc.returncode, (stdout or b"").decode(errors="replace"), (stderr or b"").decode(errors="replace")


async def export_svg_to_pptx(
    *,
    svg: str,
    filename: str,
    task_id: str,
    settings: Settings,
) -> str:
    """将单页 SVG 导出为 PPTX，返回相对产物目录的路径。"""
    if not settings.worker_tools_ppt_enabled:
        raise WorkerToolError("PPT 工具未启用（WORKER_TOOLS_PPT_ENABLED=false）")

    base_dir = settings.worker_tools_output_base_dir.strip()
    if not base_dir:
        raise WorkerToolError("PPT 输出目录未配置（WORKER_TOOLS_OUTPUT_BASE_DIR）")

    skill_dir = _skill_dir()
    if not skill_dir.is_dir():
        raise WorkerToolError("未找到 ppt-master skill 目录：.agents/skills/ppt-master（请先安装 skills）")

    task_dir = resolve_safe_path(base_dir, task_id)
    project_dir = resolve_safe_path(str(task_dir), f"ppt_master_{_now_stamp()}")

    svg_output = project_dir / "svg_output"
    _ensure_dir(svg_output)

    # 仅做最小导出：1 页
    (svg_output / "01_slide.svg").write_text(svg, encoding="utf-8")
    _write_min_spec_lock_md(project_dir)

    out_path = resolve_safe_path(str(task_dir), filename)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "py",
        "-3.11",
        str((skill_dir / "scripts/svg_to_pptx.py").resolve()),
        str(project_dir),
        "-o",
        str(out_path),
        "--pptx-structure",
        "flat",
        "-t",
        "fade",
        "-a",
        "none",
    ]
    code, stdout, stderr = await _run(cmd, cwd=skill_dir, timeout_s=600)
    if code != 0:
        msg = (stderr or stdout).strip()
        raise WorkerToolError(f"ppt-master 导出失败（exit_code={code}）：{msg}")

    base = Path(base_dir).resolve()
    rel = out_path.resolve().relative_to(base)
    return str(rel).replace("\\", "/")

