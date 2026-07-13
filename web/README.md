# Herness Console — Vue 前端

多 Agent 智能体对话控制台，对接 Herness Agent HTTP API。

## 功能

- **C 端智能助手** (`/chat`) — consumer persona 对话
- **B 端商家运营** (`/ops`) — merchant persona，身份在设置页配置
- **RAG 知识库** (`/rag`) — 文档入库与知识图谱
- **设置** (`/settings`) — 连接、身份、用量配额、界面偏好与本地数据管理
- **SSE 实时轨迹** — 右侧面板展示 Supervisor / Worker / Critic 审计日志
- **Token 用量** — 审计面板逐步展示；聊天气泡、侧边栏与设置页展示 session / 用户累计
- **配额预警** — 用量达 80% 时在输入框上方提示；429 返回专用文案
- **会话持久化** — IndexedDB 本地保存对话历史
- **任务取消** — 运行中可停止 Agent 任务
- **确认弹窗** — 清空/删除对话时使用应用内毛玻璃对话框

## 启动

```powershell
# 1. 先启动后端 API（项目根目录）
cd "D:\develop\Herness Agent"
.\run-api.ps1

# 2. 启动前端
.\run-web.ps1
# 或
cd web
npm install
npm run dev
```

浏览器打开 http://localhost:5173

开发模式下 Vite 将 `/api` 代理到 `http://localhost:8090`（见 `vite.config.ts`）。

## 环境变量

复制 `.env.example` 为 `.env`：

| 变量 | 说明 |
|------|------|
| `VITE_API_BASE` | API 前缀，默认 `/api`（dev 走代理） |
| `VITE_API_KEY` | 后端 `API_KEY`，留空则无鉴权 |

可在 **设置 → 连接与服务** 中运行时覆盖 API 地址与 Key（写入 `localStorage`），无需重新构建。

## 设置页

路由 `/settings`，侧边栏底部齿轮入口。分区如下：

| 分区 | 内容 |
|------|------|
| 连接与服务 | API 地址 / Key、连接测试、在线状态 |
| 身份与角色 | C 端用户 ID、B 端商家/操作员 ID、合成 user_id 预览 |
| 用量与配额 | C/B 用户累计、当前会话用量、配额进度条、手动刷新 |
| 界面与体验 | 轨迹面板、侧边栏、Token 显示、自动滚动、消息密度、配额预警开关 |
| 数据与隐私 | 导出全部会话、清空 C/B 端本地对话 |
| 关于 | 前端版本、LLM 模型、能力开关、配额上限（来自 `GET /v1/config/public`） |

Ops 页顶栏商家信息为只读摘要，点击「编辑身份」跳转设置页。

## 构建与生产部署

```powershell
cd web
npm run build
```

产物在 `web/dist/`。推荐与 API 同域部署，由反向代理统一入口：

```nginx
# 示例：API 8090 + 静态前端
server {
    listen 80;
    server_name agent.example.com;

    location / {
        root /var/www/herness-console/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8090/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Authorization $http_authorization;
        proxy_buffering off;  # SSE /v1/tasks/{id}/stream
    }
}
```

生产构建时设置：

```env
VITE_API_BASE=/api
VITE_API_KEY=your-production-api-key
```

后端 `.env` 同步设置 `API_KEY`，并配置 `API_PORT=8090`（或与反代一致）。

本地预览构建结果：

```powershell
npm run preview
```

## Token 用量与配额

| 位置 | 说明 |
|------|------|
| 侧边栏底部 | 当前 session 累计 tokens |
| 聊天气泡 | 单条回复的任务用量 |
| 审计面板 | 每步 Agent 用量 + 本次任务合计 |
| 设置页 | C/B 用户累计、当前会话、配额进度条 |
| 输入框上方 | 配额接近 / 用尽预警（可在设置中关闭） |
| API | `GET /v1/sessions/{session_id}/usage?user_id=...` |
| API | `GET /v1/users/{user_id}/usage` |
| API | `GET /v1/config/public`（模型、能力开关、`TOKEN_BUDGET_*`） |

后端在 `.env` 中配置：

```env
TOKEN_BUDGET_PER_USER=0
TOKEN_BUDGET_PER_SESSION=0
```

`0` 表示不限；超限后新任务返回 429，前端显示对应提示。

## 技术栈

Vue 3 · Vite · TypeScript · Pinia · Vue Router · Tailwind CSS v4 · Dexie · marked
