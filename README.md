# Herness Agent

多 Agent 协作框架：**PydanticAI 节点层 + 手写调度器 + 数据中台协议**。

> 版本：0.1.0 · Python >= 3.11 · 当前阶段：**可运行 Demo + HTTP API + Postgres/Redis 持久化 + Dreaming + Hereness v2 + 会话多轮 + Worker 工具链 + 农业电商 BFF 集成**

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
                            │
                            ▼
                   Dreaming Worker（独立进程）
              读 task_result → LLM 合成 → 写回 memories / beliefs
```

### 单次任务流程

```
1. 从中台拉取预合成全局记忆 → 注入 Supervisor
2. Supervisor 决策：delegate / complete / abort
3. delegate → Worker 执行（无全局记忆，支持多 Worker 并行）
4. needs_verification=true → Critic 校验
5. 校验通过 → 写入 Postgres + Dreaming 入队（Redis / Postgres）
6. 校验失败 → 反馈给 Supervisor 重试
7. 循环直至 complete / abort / 超时 / 超轮数
8. Dreaming Worker 异步消费队列 → 更新用户记忆（version +1）
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
│   ├── critic.py               # 校验 Agent
│   ├── critic_validation.py    # Critic 后校验（信念库对齐）
│   ├── tools.py                # Worker 外部工具实现
│   ├── tool_policy.py          # 工具权限策略（三层交集）
│   └── tool_trace.py           # 工具调用记录提取
├── api/
│   ├── app.py                  # FastAPI 应用
│   ├── routes.py               # /v1/tasks 路由
│   ├── schemas.py              # 请求/响应模型
│   ├── store.py                # 任务状态（内存 / Redis）
│   ├── security.py             # API Key 鉴权与 rate limit
│   └── live.py                 # SSE 实时消息中心
├── orchestrator/
│   ├── scheduler.py            # 手写调度器（核心状态机）
│   └── cancellation.py         # 任务取消令牌
├── middleware/
│   ├── protocol.py             # 中台协议
│   ├── memory.py               # 预合成记忆模型
│   ├── beliefs.py              # 信念匹配逻辑
│   ├── embeddings.py           # Hereness v2 向量嵌入
│   ├── session.py              # 会话历史读写
│   ├── stub.py                 # InMemoryMiddleware
│   ├── postgres.py             # Postgres 持久化
│   ├── redis_augment.py        # Redis 增强层
│   ├── factory.py              # 中台工厂
│   └── schema.sql              # Postgres 表结构
├── integrations/
│   └── agri_commerce/          # 智慧农业电商 BFF（mock / HTTP）
│       ├── protocol.py         # 客户端协议
│       ├── mock_client.py      # 本地样例数据
│       ├── http_client.py      # 真实 API 对接
│       ├── tools.py            # Worker 只读工具
│       └── openapi.yaml        # BFF 接口规范
├── redis/
│   ├── queue.py                # Dreaming 队列
│   └── cache.py                # 记忆 / 任务缓存
├── dreaming/
│   ├── app.py                  # Dreaming Worker 入口
│   ├── worker.py               # 队列消费者
│   ├── synthesizer.py          # LLM 记忆合成
│   └── merge.py                # 增量合并逻辑
└── observability/
    ├── logging.py              # 结构化日志 + trace_id
    └── metrics.py              # 运行时指标注册表
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
| `GET /health` | 健康检查（无需鉴权） |
| `GET /metrics` | 运行时指标快照（无需鉴权） |
| `POST /v1/tasks` | 提交任务（202，后台异步执行） |
| `GET /v1/tasks/{id}` | 查询任务状态与结果 |
| `GET /v1/tasks/{id}/messages` | 查询审计日志 |
| `GET /v1/tasks/{id}/stream` | SSE 流式推送审计日志（长任务实时观测） |
| `DELETE /v1/tasks/{id}` | 取消 PENDING / RUNNING 任务 |

任务状态存储：配置 `REDIS_URL` 后自动切换为 Redis，否则使用进程内内存。

| 安全能力 | 状态 |
|------|------|
| API Key 鉴权（`Authorization: Bearer` / `X-API-Key`） | ✅ 已实现 |
| 用户级 rate limit（`POST /v1/tasks`） | ✅ 已实现 |
| 输入/output 内容审核钩子 | ❌ 待实现 |

配置 `API_KEY` 后 `/v1/*` 路由需携带密钥；留空则开发模式无鉴权。`RATE_LIMIT_PER_USER` 按请求体中的 `user_id` 限流（0 表示不限）。

### Worker 专业化路由

| Worker 类型 | 用途 |
|-------------|------|
| `default` | 通用执行 |
| `research` | 调研与信息归纳 |
| `code` | 代码编写与解释 |
| `summary` | 摘要压缩 |

Supervisor 可通过 `worker_types` 与 `task_instructions` 并行路由；调度器受 `MAX_PARALLEL_WORKERS` 限制。

### Worker 外部工具

| 工具 | 配置开关 | 说明 |
|------|----------|------|
| `fetch_task_context` | 始终可用 | 从中台只读任务上下文 |
| `http_request` | `WORKER_TOOLS_HTTP_ENABLED` | HTTP/HTTPS 请求，响应体可截断 |
| `read_text_file` | `WORKER_TOOLS_FILE_ENABLED` + `WORKER_TOOLS_FILE_BASE_DIR` | 读取指定目录内文本文件（防目录穿越） |
| `run_python_code` | `WORKER_TOOLS_CODE_ENABLED` | 子进程执行 Python 片段（生产环境谨慎开启） |

文件与代码工具默认关闭；HTTP 工具默认开启。工具错误以文本形式返回给 LLM，不中断调度。

工具权限由 **全局 Settings → 中台 metadata → 任务 metadata** 三层交集决定（`tool_policy.py`）；Critic 可校验 Worker 工具调用结果（`tool_trace.py`）。

### 智慧农业电商 BFF 集成

可选集成模块，为 Worker 提供果园/电商只读查询能力；`mock` 模式内置样例数据，无需外部服务。

| 工具 | 说明 |
|------|------|
| `get_order` / `list_orders` | 订单查询 |
| `get_order_timeline` | 订单履约时间线 |
| `get_lot` / `trace_batch` | 批次与溯源 |
| `search_produce` / `get_availability` | 商品搜索与库存 |
| `get_live_inventory_hint` | 直播间库存提示 |

启用方式：

```env
AGRI_COMMERCE_ENABLED=true
AGRI_COMMERCE_MODE=mock          # mock | http
# AGRI_COMMERCE_BASE_URL=http://localhost:9000/v1
# AGRI_COMMERCE_API_KEY=
```

`mock` 模式下会自动注入农业领域信念种子（`beliefs_seed.json`），便于 Hereness 校验演示。对接真实 API 时切换为 `http` 并配置 `AGRI_COMMERCE_BASE_URL`。

### 数据中台（Middleware）

| 接口 | 存储 | 状态 |
|------|------|------|
| `get_pre_synthesized_memory` | Postgres + Redis 缓存 | ✅ |
| `get_task_context` | Postgres | ✅ |
| `query_beliefs` | Postgres FTS + 词项匹配 | ✅ |
| `write_task_result` | Postgres | ✅ |
| `enqueue_dreaming_job` | Redis List / Postgres | ✅ |
| `get_session_history` | Postgres `task_results.metadata` | ✅ |
| `get_task_result` / `save_pre_synthesized_memory` | Postgres | ✅ |
| InMemory 回退（无 DSN） | 内存 | ✅ |

配置 `POSTGRES_DSN` 启用 Postgres；配置 `REDIS_URL` 启用 Redis 队列与缓存。两者可组合使用。

### Dreaming 离线管线

| 能力 | 状态 |
|------|------|
| 任务完成后入队 | ✅ 已实现 |
| 独立 Worker 消费队列 | ✅ 已实现 |
| LLM 增量合成记忆（version +1） | ✅ 已实现 |
| 提炼事实写入 beliefs 表 | ✅ 已实现 |
| Redis 记忆缓存失效 | ✅ 已实现 |
| 失败重试（可配置次数与退避） | ✅ 已实现 |

队列来源：配置 `REDIS_URL` 时使用 Redis List（`BRPOP`）；否则回退到 Postgres `dreaming_jobs` 表轮询出队。**Dreaming Worker 需配置 `POSTGRES_DSN`** 以跨进程读写 `task_results` 与 `memories`。

### LLM 后端

通过 `.env` 切换，无需改代码：

| 方案 | `LLM_PROVIDER` | 说明 |
|------|----------------|------|
| 本地 vLLM | `openai_compatible` | 默认，`http://localhost:8000/v1` |
| OpenAI 官方 | `openai` | `gpt-4o` 等 |
| DeepSeek / Moonshot 等 | `openai_compatible` | 改 `LLM_BASE_URL` |
| Anthropic Claude | `anthropic` | `claude-sonnet-4-6` 等 |

### Hereness 信念库

| 组件 | 状态 |
|------|------|
| 字符串匹配检索（`HERENESS_ENABLED=false`） | ✅ 已实现 |
| 全文检索 + 词项 ILIKE（Postgres `tsvector`） | ✅ 已实现 |
| 启发式矛盾检测（极性相反） | ✅ 已实现 |
| Critic 后校验对齐 `FactCheckItem` | ✅ 已实现 |
| 调度器强制信念库查询（不依赖 LLM tool） | ✅ 已实现 |
| 向量语义检索（pgvector + Embeddings API） | ✅ 已实现 |
| 冲突消歧与置信度衰减 | ✅ 已实现 |

- **Hereness 校验**：`HERENESS_ENABLED=true` 时，调度器在 Critic LLM 返回后**强制**查询信念库并对齐 `fact_checks`；LLM 是否调用 `check_beliefs` tool 不影响最终结果

### 会话多轮（Session）

| 能力 | 状态 |
|------|------|
| `session_id` 关联前序任务 | ✅ 已实现 |
| `get_session_history` 中台接口 | ✅ 已实现 |
| Supervisor 注入会话历史 | ✅ 已实现 |
| 任务完成写入 session 元数据 | ✅ 已实现 |

同一对话请在 API 请求中传递相同的 `session_id`；Supervisor 会自动读取最近 N 条前序任务摘要（默认 5，见 `SESSION_HISTORY_LIMIT`）。

### 可观测性

| 能力 | 状态 |
|------|------|
| JSON 结构化日志 + `trace_id` | ✅ 已实现 |
| 任务终态 / 轮数 / 耗时指标 | ✅ 已实现 |
| Critic 驳回率 / 单步重试计数 | ✅ 已实现 |
| Dreaming 成功/失败计数 | ✅ 已实现 |
| `GET /metrics` 指标端点 | ✅ 已实现 |
| OpenTelemetry span 集成 | ❌ 待实现 |

设置 `STRUCTURED_LOGGING=true` 后，调度链路日志以纯 JSON 行输出，便于 ELK / Loki 采集。`trace_id` 等于 `task_id`，贯穿 Orchestrator 与 Dreaming Worker。

---

## 快速开始

### 1. 环境要求

- Python >= 3.11
- LLM 后端（本地 vLLM 或云端 API）
- PostgreSQL（Dreaming 与持久化推荐；API 生产环境建议启用）
- Redis 5.x+（可选，Dreaming 队列与记忆缓存）

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

# Redis — 留空则 Dreaming 队列入 Postgres / 内存，任务状态存进程内
REDIS_URL=redis://localhost:6379

# Dreaming 离线记忆合成
DREAMING_ENABLED=true

# Hereness 信念库深度校验
HERENESS_ENABLED=true
# Hereness v2 向量语义检索（需 Postgres 安装 pgvector）
# HERENESS_VECTOR_ENABLED=true
# EMBEDDING_MODEL=text-embedding-3-small
# EMBEDDING_DIMENSIONS=1536

# 智慧农业电商 BFF（可选）
# AGRI_COMMERCE_ENABLED=true
# AGRI_COMMERCE_MODE=mock
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
  -H "Authorization: Bearer your-api-key" `
  -d '{"user_id":"u1","session_id":"s1","input":"你好"}'
```

生产环境请设置 `API_KEY`；开发模式留空则无需携带密钥。

连续对话时保持 `session_id` 不变，Supervisor 会读取同 session 的前序任务摘要。

**查询状态：**

```powershell
curl http://localhost:8080/v1/tasks/{task_id}
```

**SSE 流式观测（长任务）：**

```powershell
curl -N http://localhost:8080/v1/tasks/{task_id}/stream
```

每条 `data:` 行为 JSON 审计消息；任务结束时额外推送 `{"event":"task_finished","status":"..."}`。

**取消任务：**

```powershell
curl -X DELETE http://localhost:8080/v1/tasks/{task_id}
```

仅 `pending` / `running` 可取消；已终态返回 409。

### 6. 运行 Dreaming Worker

在 API 服务之外，**另开终端**启动离线记忆合成消费者：

```powershell
.\run-dreaming.ps1
# 或
py -3.11 -m herness.dreaming.app
```

典型部署：**终端 1** 跑 API，**终端 2** 跑 Dreaming Worker。任务校验通过后，Worker 会从队列取出 job，读取 `task_results`，经 LLM 合成后更新 `memories`（version +1）并写入新 `beliefs`。

验证记忆是否更新（需 Postgres）：

```powershell
# 提交任务并完成后再查 memories 表
# SELECT user_id, version, summary FROM memories WHERE user_id = 'u1';
```

### 7. 运行测试

```powershell
py -3.11 -m pytest
# 当前 123 个用例；7 个 Postgres/Redis 集成测试需本地服务
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
| `SESSION_HISTORY_LIMIT` | `5` | Supervisor 注入的同 session 前序任务条数 |
| `API_HOST` | `0.0.0.0` | API 监听地址 |
| `API_PORT` | `8080` | API 监听端口 |
| `API_KEY` | （空） | API Key；留空则不鉴权 |
| `RATE_LIMIT_PER_USER` | `0` | 每 user_id 窗口内最大提交数；0 不限 |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | rate limit 窗口（秒） |
| `POSTGRES_DSN` | （空） | PostgreSQL 连接串 |
| `REDIS_URL` | （空） | Redis 连接地址 |
| `REDIS_MEMORY_TTL_SECONDS` | `3600` | 记忆缓存 TTL |
| `REDIS_TASK_TTL_SECONDS` | `86400` | 任务状态 TTL |
| `DREAMING_ENABLED` | `false` | 是否启用 Dreaming（Worker 可独立启动） |
| `DREAMING_TEMPERATURE` | `0.2` | Dreaming 记忆合成温度 |
| `DREAMING_POLL_TIMEOUT_SECONDS` | `5` | 队列阻塞出队超时（秒） |
| `DREAMING_MAX_RETRIES` | `3` | 单条 Dreaming 任务失败后最大重试次数 |
| `DREAMING_RETRY_BACKOFF_SECONDS` | `2.0` | 重试间隔基数（秒），按 attempt 线性递增 |
| `WORKER_TOOLS_HTTP_ENABLED` | `true` | Worker HTTP 工具开关 |
| `WORKER_TOOLS_HTTP_MAX_BYTES` | `65536` | HTTP 响应体上限（字节） |
| `WORKER_TOOLS_FILE_ENABLED` | `false` | Worker 文件读取工具开关 |
| `WORKER_TOOLS_FILE_BASE_DIR` | （空） | 文件工具允许读取的根目录 |
| `WORKER_TOOLS_FILE_MAX_BYTES` | `65536` | 单文件读取上限（字节） |
| `WORKER_TOOLS_CODE_ENABLED` | `false` | Worker Python 代码执行开关 |
| `WORKER_TOOLS_CODE_TIMEOUT_SECONDS` | `10` | 代码执行超时（秒） |
| `HERENESS_ENABLED` | `false` | Hereness 信念库深度校验 |
| `HERENESS_VECTOR_ENABLED` | `false` | Hereness v2 pgvector 语义检索 |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings 模型 |
| `EMBEDDING_DIMENSIONS` | `1536` | 向量维度（须与 DB 列一致） |
| `EMBEDDING_BASE_URL` | （空） | Embeddings API；留空沿用 `LLM_BASE_URL` |
| `EMBEDDING_API_KEY` | （空） | Embeddings Key；留空沿用 `LLM_API_KEY` |
| `HERENESS_VECTOR_TOP_K` | `10` | 向量检索条数上限 |
| `HERENESS_VECTOR_MIN_SIMILARITY` | `0.5` | 余弦相似度阈值 |
| `HERENESS_CONFLICT_DECAY_FACTOR` | `0.5` | 矛盾信念置信度衰减系数 |
| `HERENESS_SUPERSEDED_THRESHOLD` | `0.3` | 低于此置信度的信念标记为 superseded |
| `STRUCTURED_LOGGING` | `false` | 纯 JSON 行日志（配合 log_event） |
| `METRICS_ENABLED` | `true` | 是否采集运行时指标 |
| `AGRI_COMMERCE_ENABLED` | `false` | 农业电商 BFF 工具开关 |
| `AGRI_COMMERCE_MODE` | `mock` | `mock` 本地样例 / `http` 对接真实 API |
| `AGRI_COMMERCE_BASE_URL` | （空） | BFF 根地址 |
| `AGRI_COMMERCE_API_KEY` | （空） | BFF Bearer Token |
| `AGRI_COMMERCE_TIMEOUT_SECONDS` | `30` | BFF HTTP 超时（秒） |

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

- **内容审核与记忆加密**：输入/output 审核钩子、敏感记忆字段加密尚未实现
- **Dreaming 依赖 Postgres**：跨进程读写任务结果与记忆；纯内存模式仅适合单进程调试
- **Redis 5.x 需 RESP2**：客户端已适配，无需额外配置
- **单进程 API**：多实例部署需依赖 Redis 任务存储

### 重试语义

- **Agent 层**（PydanticAI `retries`）：LLM 结构化输出格式错误时自动重试
- **调度器层**（Orchestrator `_run_step_with_retry`）：网络、超时等瞬时错误时重试
- 两者共用 `MAX_RETRIES_PER_STEP` 配置，职责不同、互不替代

---

## 相关文档

- [ROADMAP.md](ROADMAP.md) — 后续优化计划与优先级

---

## 许可证

待定。
