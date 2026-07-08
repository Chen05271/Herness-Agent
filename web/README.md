# Herness Console — Vue 前端

多 Agent 智能体对话控制台，对接 Herness Agent HTTP API。

## 功能

- **C 端智能助手** (`/chat`) — consumer persona 对话
- **B 端商家运营** (`/ops`) — merchant persona，可配置商家/操作员 ID
- **SSE 实时轨迹** — 右侧面板展示 Supervisor / Worker / Critic 审计日志
- **会话持久化** — IndexedDB 本地保存对话历史
- **任务取消** — 运行中可停止 Agent 任务

## 启动

```powershell
# 1. 先启动后端 API（项目根目录）
cd "D:\develop\Herness Agent"
.\run-api.ps1

# 2. 启动前端
cd web
npm install
npm run dev
```

浏览器打开 http://localhost:5173

开发模式下 Vite 将 `/api` 代理到 `http://localhost:8090`。

## 环境变量

复制 `.env.example` 为 `.env`：

| 变量 | 说明 |
|------|------|
| `VITE_API_BASE` | API 前缀，默认 `/api`（dev 走代理） |
| `VITE_API_KEY` | 后端 `API_KEY`，留空则无鉴权 |

## 构建

```powershell
npm run build
npm run preview
```

## 技术栈

Vue 3 · Vite · TypeScript · Pinia · Vue Router · Tailwind CSS v4 · Dexie · marked
