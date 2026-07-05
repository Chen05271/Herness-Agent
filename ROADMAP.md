# Herness Agent — 优化路线图

本文档描述框架从当前 **Demo / 架构骨架** 演进到 **可用 MVP** 及后续版本的优化计划。

> 当前基线：v0.1.0 · CLI + HTTP API + Postgres/Redis + Dreaming + Hereness v2 + 会话多轮 + Worker 工具链 + SSE/取消 + 农业电商 BFF · 123 测试

---

## 优先级总览

| 阶段 | 目标 | 预估工作量 |
|------|------|-----------|
| **P0** | 质量基线：测试 + Git + 文档完善 | 1–2 天 |
| **P1** | 可用 MVP：API + 持久化中台 | 3–5 天 |
| **P2** | 核心差异化：Dreaming + Hereness | 5–10 天 |
| **P3** | 生产增强：观测、并行、扩展 | 持续迭代 |

---

## P0 — 质量基线（立即推进）

> 目标：让现有骨架可维护、可回归、可协作。

### P0-1 · 单元测试与集成测试 ✅

**现状**：`tests/` 已覆盖调度器、API、中台、Dreaming、Hereness、Worker 工具、农业电商 BFF 等；123 个用例通过，7 个 Postgres/Redis 集成测试需本地服务。

**待覆盖**：

```
tests/
├── test_orchestrator.py      # 调度器状态流转（mock Agent）
├── test_orchestrator_loop.py # 循环规划检测
├── test_orchestrator_timeout.py
├── test_middleware_stub.py   # InMemoryMiddleware 读写边界
├── test_memory.py            # PreSynthesizedMemory.to_prompt_block
└── conftest.py               # 共享 fixture（FakeMiddleware、FakeAgent）
```

**关键点**：

- Agent 调用层用 mock，避免测试依赖真实 LLM
- 覆盖 `COMPLETED / FAILED / TIMEOUT / ABORTED` 四种终态
- 验证 Worker/Critic deps 类型为 `ReadOnlyMiddleware`

**验收标准**：`pytest` 全绿，核心调度路径覆盖率 > 80%。

---

### P0-2 · 初始化 Git 仓库 ✅

**现状**：已初始化 git 仓库并纳入 `.gitignore`。

**待做**：

- `git init` + `.gitignore`（`.env`、`__pycache__`、`.venv` 等）
- 首次 commit：当前骨架代码
- 可选：关联远程仓库

---

### P0-3 · 调度器层单步重试 ✅

**现状**：Orchestrator 已在 `_run_supervisor / _run_worker / _run_critic` 外包重试逻辑。

**待做**：

- 在 `_run_supervisor / _run_worker / _run_critic` 外包一层重试逻辑
- 区分「LLM 格式错误」（可重试）与「逻辑失败」（不重试）
- 重试次数写入审计日志

---

## P1 — 可用 MVP（短期目标）

> 目标：脱离 Demo，可作为后端服务被前端或其他系统调用。

### P1-1 · HTTP API 层

**建议方案**：FastAPI

```
POST /v1/tasks          # 提交任务，返回 task_id
GET  /v1/tasks/{id}     # 查询任务状态与结果
GET  /v1/tasks/{id}/messages  # 审计日志
```

**待做**：

- 新增 `src/herness/api/` 模块
- 请求/响应复用现有 `TaskRequest` / `TaskResult` 模型
### API 体验（部分完成）

- **SSE 流式推送** — `GET /v1/tasks/{id}/stream` 实时看审计日志 ✅
- **任务取消** — `DELETE /v1/tasks/{id}` 中断 RUNNING 任务 ✅
- **Webhook 回调** — 任务完成时 POST 通知 — 待实现
- `uvicorn` 启动脚本

**验收标准**：curl 可提交任务并拿到结构化结果。

---

### P1-2 · PostgresMiddleware

**现状**：`postgres_dsn` 配置已占位，`InMemoryMiddleware` 为唯一实现。

**待实现接口**（对齐 `DataMiddleware` Protocol）：

| 方法 | 存储方案 |
|------|----------|
| `get_pre_synthesized_memory` | Postgres `memories` 表 |
| `get_task_context` | Postgres `task_contexts` 表 |
| `query_beliefs` | Postgres `beliefs` 表 + 全文/向量检索 |
| `write_task_result` | Postgres `task_results` 表 |
| `enqueue_dreaming_job` | Redis List / Stream |

**表结构草案**：

```sql
-- memories: user_id, version, summary, slices (JSONB), updated_at
-- beliefs:  user_id, fact, source, confidence, created_at
-- task_results: task_id, user_id, output (JSONB), created_at
```

**验收标准**：重启服务后记忆与信念数据不丢失。

---

### P1-3 · Redis 缓存层

**用途**：

- Dreaming 任务队列（替代内存 list）
- 预合成记忆热缓存（减少 Postgres 读取）
- 任务状态短期缓存（RUNNING 态查询）

**验收标准**：`enqueue_dreaming_job` 写入 Redis，独立 worker 可消费。

---

## P2 — 核心差异化（中期目标）

> 目标：实现 Herness 相对通用 Agent 框架的独有能力。

### P2-1 · Dreaming 离线记忆合成管线

**设计意图**：在线链路不阻塞，任务完成后异步提炼用户记忆。

**流程**：

```
任务完成 → enqueue_dreaming_job
              │
              ▼
        Dreaming Worker（独立进程）
              │
              ├─ 读取 task_result
              ├─ LLM 提炼新事实 / 偏好 / 上下文
              ├─ 合并到 PreSynthesizedMemory（version +1）
              └─ 更新 beliefs 表
```

**待做**：

- `src/herness/dreaming/worker.py` — 队列消费者
- `src/herness/dreaming/synthesizer.py` — 记忆合成逻辑
- 配置项 `DREAMING_ENABLED=true` 时启动 worker
- 合成 prompt 模板与增量合并策略

**验收标准**：完成一次任务后，下次同用户请求的 Supervisor 可见更新后的记忆。

---

### P2-2 · Hereness 信念库增强

**现状**：`query_beliefs` 为简单字符串 `in` 匹配。

**演进路径**：

| 阶段 | 方案 |
|------|------|
| v1 | 关键词 + 全文检索（Postgres `tsvector`） | ✅ |
| v2 | 向量语义检索（pgvector / 外部向量库） | ✅ |
| v3 | 冲突检测与消歧（矛盾信念标记 + 置信度衰减） | ✅ |

**Critic 增强**：

- 结构化 `FactCheckItem` 输出与信念库结果自动对齐
- `contradicted` 时自动生成可执行 feedback
- 配置项 `HERENESS_ENABLED=true` 控制是否启用深度校验

---

### P2-3 · 会话与多轮对话 ✅

**现状**：`session_id` 已关联历史任务；Supervisor 注入前序摘要。

**已实现**：

- `get_session_history(session_id)` 中台只读接口
- Supervisor 动态注入会话历史
- 任务完成时写入 `task_results.metadata`（含 session_id / input / final_answer）
- 配置项 `SESSION_HISTORY_LIMIT` 控制注入条数

---

## P3 — 生产增强（长期迭代）

### P3-1 · 多 Worker 与并行执行 ✅

- Supervisor 输出支持多任务指令（`task_instructions: list[str]`）✅
- 调度器并行 dispatch，Critic 逐条或批量校验 ✅
- Worker 专业化路由（research / code / summary 等）✅

### P3-2 · 工具链扩展（部分完成）

- Worker 注册外部工具（HTTP、文件、受限 Python 执行）✅
- 农业电商 BFF 只读工具（mock / HTTP 双模式）✅
- 工具权限三层交集管控（Settings + 中台 + 任务 metadata）✅
- 工具调用结果纳入 Critic 校验范围 ✅
- 工具权限与中台读写权限统一管控 — 待完善

### P3-3 · 可观测性

- 结构化日志（JSON）+ trace_id 贯穿调度链路 ✅
- 运行时指标：`GET /metrics`（任务终态、轮数、Critic 驳回、重试、Dreaming）✅
- OpenTelemetry 集成（span per Agent step）— 待实现

### P3-4 · 安全与配额

- 用户级 rate limit ✅
- API Key 鉴权 ✅
- 输入/output 内容审核钩子 — 待实现
- 敏感记忆字段加密存储 — 待实现

---

## 技术债务清单

| 项目 | 位置 | 说明 |
|------|------|------|
| ~~Supervisor 无输出字段校验~~ | `models/supervisor.py` | ✅ 已加 action 必填字段校验 |
| ~~`get_settings()` 每次重新解析~~ | `config.py` | ✅ 已改为 lru_cache 单例 |
| ~~Agent 重试 vs 调度器重试职责不清~~ | `config.py` / README | ✅ 已在 README 与 Field description 文档化 |
| ~~Critic 未强制调用 `check_beliefs` tool~~ | `agents/critic_validation.py` | ✅ 调度器后校验强制查询信念库，覆盖 LLM 漏检 |
| ~~`fact_terms` 未使用~~ | `middleware/beliefs.py` | ✅ 已改为 Jaccard + 子串回退匹配 |
| ~~Dreaming 失败无重试~~ | `dreaming/worker.py` | ✅ 已加可配置重试与退避 |
| 无依赖版本锁定 | `pyproject.toml` | 生产环境建议 `uv lock` 或 requirements.lock |

---

## 建议实施顺序

```
Week 1
├── P0-1 测试套件
├── P0-2 Git 初始化
└── P0-3 调度器重试

Week 2
├── P1-1 FastAPI 入口
└── P1-2 PostgresMiddleware（ beliefs + task_results 先落地）

Week 3
├── P1-3 Redis 队列
└── P2-1 Dreaming Worker（最小可用版）

Week 4+
├── P2-2 Hereness 向量检索（下一优先级）
├── P3-3 可观测性
└── P3 按需求优先级选取
```

---

## 里程碑定义

| 里程碑 | 标志 |
|--------|------|
| **M1 — 可维护** | 测试全绿 + Git + README 完善 |
| **M2 — 可部署** | HTTP API + Postgres 持久化 |
| **M3 — 有记忆** | Dreaming 自动更新用户记忆 |
| **M4 — 可信赖** | Hereness 语义事实校验 + 冲突消歧 |
| **M5 — 可扩展** | 多 Worker 并行 + 工具链 + 可观测性 |

---

## 如何贡献

1. 从 [P0](#p0--质量基线立即推进) 开始，优先测试与 API
2. 新 Middleware 实现必须满足 `DataMiddleware` Protocol
3. 新 Agent 角色需明确读写权限边界
4. 所有调度路径变更需补充对应测试

如有疑问，参考 [README.md](README.md) 中的架构说明与权限边界设计。
