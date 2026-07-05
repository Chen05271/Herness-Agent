# Herness Agent

多 Agent 协作框架：**PydanticAI 节点层 + 手写调度器 + 数据中台协议**。

> 版本：0.1.0 · Python >= 3.11 · 当前阶段：**可运行 Demo + HTTP API + Postgres/Redis 持久化**

---

## 设计定位

Herness Agent 刻意不依赖 LangGraph 等图编排框架，采用**显式状态机**驱动多 Agent 协作，并通过**中台协议**划分数据读写权限。

核心差异化：

| 概念 | 说明 |
|------|------|
| **预合成记忆** | 全局用户记忆由离线 Dreaming 管线生成，在线链路只读注入 Supervisor |
| **记忆隔离** | Worker deliberately 不可见全局记忆，仅持有任务级上下文 |
| **Hereness 信念库** | Critic 通过信念库做事实一致性校验 |
| **审计日志** | 所有 Agent 消息经调度器流转并记录，子 Agent 禁止直连 |

---

## 架构概览

```
用户请求（CLI / HTTP API）
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator（调度器）                 │
│  状态机 · 超时 · 轮数限制 · 并行 Worker · 审计日志        │
└────────┬──────────────────┬──────────────────┬──────────┘
         │                  │                  │
         ▼                  ▼                  ▼
   Supervisor           Worker(s)          Critic
   （总管/规划）         （执行，可并行）      （校验）
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
                            │
              ┌─────────────┴─────────────┐
         Postgres（持久化）          Redis（缓存/队列）
    memories / beliefs /          记忆热缓存
    task_results / contexts       Dreaming 队列
                                  API 任务状态
```

### 单次任务流程

```
1. 从中台拉取预合成全局记忆 → 注入 Supervisor
2. Supervisor 决策：delegate / complete / abort
3. delegate → Worker 执行（无全局记忆，支持多 Worker 并行）
4. needs_verification=true → Critic 校验
5. 校验通过 → 写入 Postgres + Dreaming 入 Redis 队列
6. 校验失败 → 反馈给 Supervisor 重试
7. 循环直至 complete / abort / 超时 / 超轮数
```

---

## 目录结构

```
src/herness/
├── main.py                     # CLI 入口（本地 Demo）
├── config.py                   # 环境变量配置（.env）
├── agents/
│   ├── base.py                 # LLM 模型工厂
│   ├── registry.py             # Agent 注册表
│   ├── supervisor.py           # 总管 Agent
│   ├── worker.py               # 执行 Agent
│   └── critic.py               # 校验 Agent
├── api/
│   ├── app.py                  # FastAPI 应用
│   ├── routes.py               # /v1/tasks 路由
│   ├── schemas.py              # 请求/响应模型
│   └── store.py                # 任务状态（内存 / Redis）
├── orchestrator/
│   └── scheduler.py            # 手写调度器（核心状态机）
├── middleware/
│   ├── protocol.py             # 中台协议
│   ├── memory.py               # 预合成记忆模型
│   ├── beliefs.py              # 信念匹配逻辑
│   ├── stub.py                 # InMemoryMiddleware
│   ├── postgres.py             # Postgres 持久化
│   ├── redis_augment.py        # Redis 增强层
│   ├── factory.py              # 中台工厂
│   └── schema.sql              # Postgres 表结构
├── redis/
│   ├── queue.py                # Dreaming 队列
│   └── cache.py                # 记忆 / 任务缓存
└── observability/
    └── logging.py              # 结构化日志
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
| 调度器层单步重试 | ✅ 已实现 |
| 多 Worker 并行 | ✅ 已实现 |

### HTTP API

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /v1/tasks` | 提交任务（202，后台异步执行） |
| `GET /v1/tasks/{id}` | 查询任务状态与结果 |
| `GET /v1/tasks/{id}/messages` | 查询审计日志 |

任务状态存储：配置 `REDIS_URL` 后自动切换为 Redis，否则使用进程内内存。

### 数据中台（Middleware）

| 接口 | 存储 | 状态 |
|------|------|------|
| `get_pre_synthesized_memory` | Postgres + Redis 缓存 | ✅ |
| `get_task_context` | Postgres | ✅ |
| `query_beliefs` | Postgres + 字符串匹配 | ✅ |
| `write_task_result` | Postgres | ✅ |
| `enqueue_dreaming_job` | Redis List | ✅ |
| InMemory 回退（无 DSN） | 内存 | ✅ |

配置 `POSTGRES_DSN` 启用 Postgres；配置 `REDIS_URL` 启用 Redis 队列与缓存。两者可组合使用。

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
| Dreaming（记忆合成） | ⚠️ 队列入 Redis，消费者待实现 |
| Hereness（信念冲突消歧） | ❌ 仅简单字符串匹配 |

---

## 快速开始

### 1. 环境要求

- Python >= 3.11
- LLM 后端（本地 vLLM 或云端 API）
- PostgreSQL（可选，持久化）
- Redis 5.x+（可选，队列与缓存）

### 2. 安装

```powershell
cd "d:\develop\Herness Agent"
py -3.11 -m pip install -e ".[dev,postgres,redis]"
```

### 3. 配置

```powershell
copy .env.example .env
```

关键变量：

```env
# LLM（按需修改）
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:8000/v1

# Postgres — 留空则用内存中台
POSTGRES_DSN=postgresql://postgres:your_password@localhost:5432/herness

# Redis — 留空则 Dreaming 队列入内存、任务状态存进程内
REDIS_URL=redis://localhost:6379
```

首次连接 Postgres 时会自动执行 `schema.sql` 建表。

### 4. 运行 CLI Demo

```powershell
.\run.ps1
# 或
py -3.11 -m herness.main "介绍一下 Herness Agent 框架的架构设计"
```

### 5. 运行 HTTP API

```powershell
.\run-api.ps1
# 或
py -3.11 -m herness.api.app
```

默认监听 `http://0.0.0.0:8080`。

**提交任务：**

```powershell
curl -X POST http://localhost:8080/v1/tasks `
  -H "Content-Type: application/json" `
  -d '{"user_id":"u1","input":"你好"}'
```

**查询状态：**

```powershell
curl http://localhost:8080/v1/tasks/{task_id}
```

### 6. 运行测试

```powershell
py -3.11 -m pytest
```

集成测试（可选，需本地服务）：

```powershell
$env:POSTGRES_TEST_DSN="postgresql://postgres:your_password@localhost:5432/herness"
$env:REDIS_TEST_URL="redis://localhost:6379"
py -3.11 -m pytest tests/test_middleware_postgres.py tests/test_middleware_redis_integration.py -v
```

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
| `MAX_RETRIES_PER_STEP` | `2` | 单步最大重试次数 |
| `MAX_PARALLEL_WORKERS` | `4` | 单轮并行 Worker 上限 |
| `API_HOST` | `0.0.0.0` | API 监听地址 |
| `API_PORT` | `8080` | API 监听端口 |
| `POSTGRES_DSN` | （空） | PostgreSQL 连接串 |
| `REDIS_URL` | （空） | Redis 连接地址 |
| `REDIS_MEMORY_TTL_SECONDS` | `3600` | 记忆缓存 TTL |
| `REDIS_TASK_TTL_SECONDS` | `86400` | 任务状态 TTL |

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

- **Dreaming 消费者未实现**：任务已入 Redis 队列，离线合成逻辑待开发
- **信念库简陋**：字符串包含匹配，非语义/向量检索
- **Redis 5.x 需 RESP2**：客户端已适配，无需额外配置
- **单进程 API**：多实例部署需依赖 Redis 任务存储

---

## 相关文档

- [ROADMAP.md](ROADMAP.md) — 后续优化计划与优先级

---

## 许可证

待定。
