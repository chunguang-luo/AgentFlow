# AgentFlow

AgentFlow 是一个可配置的 AI Agent 执行平台。用户创建由多个 Step 组成的 Flow，平台调度 Claude CLI、Codex CLI 等 Agent 工具执行任务，并汇聚生成最终分析结果。

## 架构

```text
React SPA
   │ HTTP REST / SSE
   ▼
Python FastAPI
   ├── API
   ├── Flow Engine
   ├── Agent Dispatcher
   ├── Auth
   └── Scheduler
          │ subprocess
          ▼
   Claude CLI / Codex CLI / Mock Provider

SQLite + local artifact/log storage
```

详细设计和阶段划分见 [docs/IMPLEMENTATION_1.0.md](docs/IMPLEMENTATION_1.0.md)。

## 本地开发

要求：

- Python 3.11-3.13
- Node.js 20 或以上

安装依赖：

```bash
make install
```

启动前后端：

```bash
make dev
```

访问：

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/api/docs
- Health: http://localhost:8000/readyz

常用命令：

```bash
make test      # backend + frontend tests
make lint      # backend + frontend lint
make migrate   # run database migrations
```

## 认证与默认管理员

业务 API 需要先登录。开发与测试环境首次启动会创建：

```text
username: admin
password: agentflow-admin
```

登录后接口会同时返回 Bearer Token，并通过 `HttpOnly` Cookie 保存会话：

```bash
curl -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"agentflow-admin"}' \
  http://localhost:8000/api/auth/login
```

生产环境必须显式配置：

```bash
AGENTFLOW_BOOTSTRAP_ADMIN_USERNAME=admin
AGENTFLOW_BOOTSTRAP_ADMIN_PASSWORD=your-strong-password
```

系统内置 `admin`、`editor`、`operator`、`viewer` 四类角色，敏感操作会写入审计日志。

## Docker 部署

```bash
docker compose up --build
```

Frontend 暴露在 `http://localhost:5173`，并通过 Nginx 反向代理 `/api` 到后端。
