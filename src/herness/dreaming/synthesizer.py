"""Dreaming 记忆合成 — LLM 提炼任务结果并增量合并记忆。"""

from __future__ import annotations

from typing import Protocol

from dataclasses import dataclass

from pydantic_ai import Agent

from herness.agents.base import build_model
from herness.config import Settings
from herness.dreaming.merge import merge_memory
from herness.middleware.memory import PreSynthesizedMemory
from herness.models.dreaming import DreamingOutput, NewBelief
from herness.models.worker import WorkerOutput

_DREAMING_SYSTEM = """\
你是 Herness 系统的 Dreaming 记忆合成器（离线管线）。
职责：根据已完成的任务结果，增量更新用户的预合成全局记忆。

规则：
1. 只提炼与用户长期相关的信息（偏好、身份、重要事实、近期上下文）
2. 不要重复已有记忆切片中的内容
3. updated_summary 应简洁，覆盖用户画像与近期重点
4. new_beliefs 仅包含可客观验证的事实，不要写入主观推测
5. 若任务结果无值得记忆的内容，保持 updated_summary 与现有摘要相近，new_slices/new_beliefs 可为空
"""


def build_dreaming_agent(settings: Settings) -> Agent[None, DreamingOutput]:
    """构建 Dreaming 合成 Agent。"""
    model = build_model(settings, temperature=settings.dreaming_temperature)
    return Agent(
        model,
        output_type=DreamingOutput,
        system_prompt=_DREAMING_SYSTEM,
        retries=settings.max_retries_per_step,
    )


def _build_prompt(
    current: PreSynthesizedMemory,
    task_result: WorkerOutput,
    task_id: str,
) -> str:
    return (
        f"## 当前预合成记忆 (v{current.version})\n"
        f"{current.to_prompt_block()}\n\n"
        f"## 已完成任务 (task_id={task_id})\n"
        f"摘要：{task_result.summary}\n"
        f"内容：{task_result.content}\n\n"
        "请输出增量更新后的记忆（DreamingOutput）。"
    )


class SynthesizerBackend(Protocol):
    async def run(self, prompt: str) -> DreamingOutput: ...


class AgentSynthesizerBackend:
    """基于 pydantic-ai Agent 的合成后端。"""

    def __init__(self, agent: Agent[None, DreamingOutput]) -> None:
        self._agent = agent

    async def run(self, prompt: str) -> DreamingOutput:
        result = await self._agent.run(prompt)
        return result.output


@dataclass
class SynthesisResult:
    """合成结果 — 记忆与待写入信念。"""

    memory: PreSynthesizedMemory
    new_beliefs: list[NewBelief]


class MemorySynthesizer:
    """读取任务结果 + 现有记忆，产出合并后的 PreSynthesizedMemory。"""

    def __init__(self, backend: SynthesizerBackend) -> None:
        self._backend = backend

    @classmethod
    def from_settings(cls, settings: Settings) -> MemorySynthesizer:
        return cls(AgentSynthesizerBackend(build_dreaming_agent(settings)))

    async def synthesize(
        self,
        *,
        current: PreSynthesizedMemory,
        task_result: WorkerOutput,
        task_id: str,
    ) -> SynthesisResult:
        prompt = _build_prompt(current, task_result, task_id)
        output = await self._backend.run(prompt)
        return SynthesisResult(
            memory=merge_memory(current, output),
            new_beliefs=output.new_beliefs,
        )
