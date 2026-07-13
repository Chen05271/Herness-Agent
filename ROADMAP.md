# Herness Agent — 优化路线图

本文档描述框架从当前 **Demo / 架构骨架** 演进到 **可用 MVP** 及后续版本的优化计划。

> 当前基线：v0.1.0 · CLI + HTTP API + **Web 控制台** + Postgres/Redis + Dreaming + Hereness v2 + RAG + 会话多轮 + **Token 用量追踪/持久化** + Worker 工具链 + **ppt-master PPT 生成** + SSE/取消 + 农业电商 BFF · **170+ 测试**

---

## 优先级总览

| 阶段 | 目标 | 状态 |
|------|------|------|
| **P0** | 质量基线：测试 + Git + 文档完善 | ✅ 基本完成 |
| **P1** | 可用 MVP：API + 持久化中台 + Web 控制台 | ✅ 已实现 |
| **P2** | 核心差异化：Dreaming + Hereness + RAG | ✅ 已实现 |
| **P3** | 生产增强：观测、安全、扩展 | 🔄 进行中 |

---

## 已完成（近期）

| 能力 | 说明 |
|------|------|
| Web 控制台 | Vue 3 · Chat / Ops / RAG · SSE 审计 · IndexedDB 会话 |
| RAG 知识库 | 分块入库 · Grep/向量/Graph 检索 · Worker 工具 |
| Token 用量 | 按 Agent 步骤审计 · 任务汇总 · `/metrics` · Postgres `usage_events` |
| Session 用量 API | `GET /v1/sessions/{id}/usage` · 前端侧边栏展示 |
| 自定义确认弹窗 | 替换浏览器原生 `confirm` |
| Persona 隔离 | consumer / merchant 工具白名单与路由 |
| ppt-master PPT | `presentation` Worker · Skill 注入 · `ppt_master_build_pptx` · 产物下载 API |

---

## P3 — 生产增强（长期迭代）

### P3-1 · 多 Worker 与并行执行 ✅

- Supervisor 多任务指令 · 并行 dispatch · 专业化 Worker 路由

### P3-2 · 工具链扩展（部分完成）

- Worker HTTP / 文件 / 代码工具 ✅
- ppt-master PPT 工具链（Harness 一键出片 + 项目导出）✅
- 农业电商 BFF（mock / HTTP）✅
- 工具权限三层交集 ✅
- Critic 工具结果校验 ✅
- 工具权限与中台读写权限统一管控 — 待完善

### P3-3 · 可观测性（部分完成）

| 能力 | 状态 |
|------|------|
| JSON 结构化日志 + trace_id | ✅ |
| `/metrics` 运行时指标 + Token 累计 | ✅ |
| 按任务 / session Token 持久化 | ✅ |
| Web 控制台用量展示 | ✅ |
| OpenTelemetry span 集成 | ✅ |
| Dreaming / RAG / Embedding 用量计入 | ✅ |

### P3-4 · 安全与配额

| 能力 | 状态 |
|------|------|
| API Key 鉴权 | ✅ |
| 用户级 rate limit | ✅ |
| 输入/output 内容审核钩子 | ❌ 待实现 |
| 敏感记忆字段加密存储 | ❌ 待实现 |
| Token 预算配额（超限拒绝） | ❌ 待实现 |

### P3-5 · API 体验

| 能力 | 状态 |
|------|------|
| SSE 流式审计 | ✅ |
| 任务取消 | ✅ |
| Webhook 任务完成回调 | ❌ 待实现 |

---

## 技术债务清单

| 项目 | 说明 |
|------|------|
| 无依赖版本锁定 | 生产环境建议 `uv lock` 或 requirements.lock |
| Settings 测试隔离 | 含 `.env` 的字段需 `_env_file=None` 或 monkeypatch |
| ROADMAP 与 README 同步 | 随版本迭代维护 |

---

## 里程碑定义

| 里程碑 | 标志 |
|--------|------|
| **M1 — 可维护** | 测试全绿 + Git + README 完善 |
| **M2 — 可部署** | HTTP API + Postgres + Web 控制台 |
| **M3 — 有记忆** | Dreaming 自动更新用户记忆 |
| **M4 — 可信赖** | Hereness 语义事实校验 + 冲突消歧 |
| **M5 — 可扩展** | 多 Worker + RAG + Token 可观测 |

---

## 如何贡献

1. 新 Middleware 实现必须满足 `DataMiddleware` Protocol
2. 新 Agent 角色需明确读写权限边界
3. 所有调度路径变更需补充对应测试

如有疑问，参考 [README.md](README.md) 中的架构说明与权限边界设计。
