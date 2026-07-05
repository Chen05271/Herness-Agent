# Herness Agent

多 Agent 协作框架：**PydanticAI 节点层 + 手写调度器 + 数据中台协议**。

> 版本：0.1.0 · Python >= 3.11 · 当前阶段：**可运行 Demo / 架构骨架**

---

## 设计定位

Herness Agent 刻意不依赖 LangGraph 等图编排框架，采用**显式状态机**驱动多 Agent 协作，并通过**中台协议**划分数据读写权限。

核心差异化：

| 概念 | 说明 |
|------|------|
| **预合成记忆** | 全局用户记忆由离线 Dreaming 管线生成，在线链路只读注入 Supervisor |
| **记忆隔离** | Worker  deliberately 不可见全局记忆，仅持有任务级上下文 |
| **Hereness 信念库** | Critic 通过信念库做事实一致性校验（当前为桩实现） |
| **审计日志** | 所有 Agent 消息经调度器流转并记录，子 Agent 禁止直连 |

---

## 架构概览

```
用户请求
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator（调度器）                 │
│  状态机 · 超时 · 轮数限制 · 循环规划检测 · 审计日志        │
└────────┬──────────────────┬──────────────────┬──────────┘
         │                  │                  │
         ▼                  ▼                  ▼
   Supervisor           Worker             Critic
   （总管/规划）         （执行）            （校验）
         │                  │                  │
         └──────────────────┴──────────────────┘
                            │
                            ▼
                   DataMiddleware（中台）
              ┌─────────────┴─────────────┐
         只读接口                    读写接口
    get_task_context            get_pre_synthesized_memory
    query_beliefs               write_task_result
                                enqueue_dreaming_job
```

### 单次任务流程

```
1. 从中台拉取预合成全局记忆 → 注入 Supervisor
2. Supervisor 决策：delegate / complete / abort
3. delegate → Worker 执行（无全局记忆）
4. needs_verification=true → Critic 校验
5. 校验通过 → 写入中台 + 投递 Dreaming 队列
6. 校验失败 → 反馈给 Supervisor 重试
7. 循环直至 complete / abort / 超时 / 超轮数
```

---

## 目录结构

```
src/herness/
├── main.py                 # CLI 入口（本地 Demo）
├── config.py               # 环境变量配置（.env）
├── agents/
│   ├── base.py             # LLM 模型工厂（vLLM / OpenAI / Anthropic 等）
│   ├── supervisor.py       # 总管 Agent — 规划、委派、汇总
│   ├── worker.py           # 执行 Agent — 只读权限，无全局记忆
│   └── critic.py           # 校验 Agent — 结构校验 + 信念库查询
├── orchestrator/
│   └── scheduler.py        # 手写调度器（核心状态机）
├── middleware/
│   ├── protocol.py         # 中台协议（ReadOnly / DataMiddleware）
│   ├── memory.py           # 预合成记忆模型
│   └── stub.py             # InMemoryMiddleware（开发/测试桩）
└── models/
    ├── task.py             # 任务生命周期、审计日志
    ├── supervisor.py       # SupervisorOutput
    ├── worker.py           # WorkerOutput
    └── critic.py           # CriticOutput
```

---

## 各模块现状

### 调度器（Orchestrator）

| 能力 | 状态 |
|------|------|
| Supervisor → Worker → Critic 闭环 | ✅ 已实现 |
| 单步 / 整任务超时 | ✅ 已实现 |
| 最大轮数限制 | ✅ 已实现 |
| 循环规划检测（plan hash） | ✅ 已实现 |
| 审计日志（TaskMessage） | ✅ 已实现 |
| 调度器层单步重试 | ❌ 未实现（仅 PydanticAI Agent retries） |
| 多 Worker 并行 | ❌ 未实现 |

### Agent 节点

| Agent | 温度 | 权限 | 状态 |
|-------|------|------|------|
| Supervisor | 0.0 | 全局记忆 + 中台读写 | ✅ 可用 |
| Worker | 0.3 | 任务级上下文（只读） | ✅ 可用 |
| Critic | 0.0 | 只读 + 信念库查询 | ✅ 可用 |

所有 Agent 输出均为 Pydantic 结构化模型，由 PydanticAI `output_type` 强制约束。

### 数据中台（Middleware）

| 接口 | 调用方 | 状态 |
|------|--------|------|
| `get_pre_synthesized_memory` | 调度器 / Supervisor | ✅ InMemory 桩 |
| `get_task_context` | Worker / Critic | ✅ InMemory 桩 |
| `query_beliefs` | Critic | ✅ 简单字符串匹配 |
| `write_task_result` | 调度器 | ✅ InMemory 桩 |
| `enqueue_dreaming_job` | 调度器 | ✅ 入队占位，无消费者 |
| Postgres + Redis 持久化 | — | ❌ 配置已占位 |

### LLM 后端

通过 `.env` 切换，无需改代码：

| 方案 | `LLM_PROVIDER` | 说明 |
|------|----------------|------|
| 本地 vLLM | `openai_compatible` | 默认，`http://localhost:8000/v1` |
| OpenAI 官方 | `openai` | `gpt-4o` 等 |
| DeepSeek / Moonshot 等 | `openai_compatible` | 改 `LLM_BASE_URL` |
| Anthropic Claude | `anthropic` | `claude-sonnet-4-6` 等 |

### 离线管线（规划中）

| 组件 | 状态 |
|------|------|
| Dreaming（记忆合成） | ❌ 仅入队占位 |
| Hereness（信念冲突消歧） | ❌ 仅简单匹配 |

---

## 快速开始

### 1. 环境要求

- Python >= 3.11
- 本地 vLLM 服务（或其他兼容 API）

### 2. 安装

```powershell
cd "d:\develop\Herness Agent"
py -3.11 -m pip install -e ".[dev]"
```

### 3. 配置

```powershell
copy .env.example .env
# 按需修改 LLM 相关变量
```

### 4. 运行 Demo

```powershell
# 使用默认问题
.\run.ps1

# 自定义问题
.\run.ps1 "介绍一下 Herness Agent 框架的架构设计"
```

或直接：

```powershell
py -3.11 -m herness.main "你的问题"
```

### 5. 预期输出

Demo 会预置演示用户的记忆与信念，运行完整调度流程，并打印：

- 任务 ID、状态、轮数、最终回答
- 各 Agent 的审计日志摘要

---

## 配置项参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `openai_compatible` | 模型后端类型 |
| `LLM_BASE_URL` | `http://localhost:8000/v1` | API 地址 |
| `LLM_API_KEY` | `dummy` | API Key |
| `LLM_MODEL` | `default` | 模型名称 |
| `SUPERVISOR_TEMPERATURE` | `0.0` | 总管温度 |
| `WORKER_TEMPERATURE` | `0.3` | 执行温度 |
| `CRITIC_TEMPERATURE` | `0.0` | 校验温度 |
| `MAX_ROUNDS` | `8` | 单任务最大轮数 |
| `STEP_TIMEOUT_SECONDS` | `120` | 单步超时（秒） |
| `TASK_TIMEOUT_SECONDS` | `600` | 整任务超时（秒） |
| `MAX_RETRIES_PER_STEP` | `2` | Agent 层重试次数 |

完整配置见 [`.env.example`](.env.example)。

---

## 权限边界设计

中台通过 Protocol 区分读写权限，在类型层面约束 Agent 能力：

```python
# Worker / Critic 只能拿到 ReadOnlyMiddleware
class WorkerDeps:
    middleware: ReadOnlyMiddleware  # 无法调用 write / enqueue

# Supervisor / 调度器 使用完整 DataMiddleware
class SupervisorDeps:
    middleware: DataMiddleware      # 可读全局记忆、写结果
```

Worker 系统 prompt 明确声明不可见全局记忆；调度器在调用 Worker 时也不传递 `PreSynthesizedMemory`。

---

## 当前限制

- **无 HTTP API**：仅 CLI Demo 入口
- **无持久化**：重启后数据丢失
- **无测试**：`tests/` 目录尚未创建
- **单 Worker 串行**：不支持并行执行或多 Worker 路由
- **信念库简陋**：字符串包含匹配，非语义检索
- **Dreaming 未实现**：记忆合成仍为手动 seed

---

## 相关文档

- [ROADMAP.md](ROADMAP.md) — 后续优化计划与优先级

---

## 许可证

待定。
