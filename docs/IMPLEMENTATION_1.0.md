# AgentFlow 实现文档与实施阶段（版本 1.0）

## 1. 目标与范围

AgentFlow 是一个可配置的 AI Agent 执行平台。用户在前端创建和编辑 Flow，平台按 Flow 定义调度多个 Step，将任务交给 Claude CLI、Codex CLI 等 Agent 工具执行，汇聚中间结果并生成最终分析报告。

### 1.0 目标

- 提供 Flow 的创建、编辑、版本管理和执行能力。
- 支持顺序、分支、并行、汇聚等 Step 编排方式。
- 通过统一适配层调用本地 Agent CLI，隔离不同工具的命令行差异。
- 提供任务执行状态、日志、产物、耗时和错误信息的前端可视化。
- 使用 SQLite 完成单机部署下的持久化，降低安装和运维成本。
- 提供基础认证、权限控制、审计和任务调度能力。

### 非目标

- 不在 1.0 中支持分布式多节点部署。
- 不内置自有大模型推理服务，Agent 能力来自外部 CLI 或后续新增的 Provider。
- 不承诺对任意 Shell 命令的开放执行，Agent 调用必须经过受控适配层。
- 不在 1.0 中实现复杂组织架构、多租户计费和细粒度资源配额。

## 2. 总体架构

```text
React SPA
   │ HTTP REST / SSE
   ▼
Python API 服务
   ├── Auth：登录、会话、RBAC
   ├── Flow API：Flow/Step/版本管理
   ├── Run API：执行、取消、查询、日志、产物
   ├── Scheduler：手动任务、定时任务、重试任务
   ├── Flow Engine：DAG 解析、状态机、上下文传递
   ├── Agent Dispatcher：并发控制、超时、重试、取消
   └── Provider Adapter：Claude CLI / Codex CLI / 扩展 Provider
          │ subprocess
          ▼
     Agent CLI 工具

SQLite DB：用户、Flow、Run、Step Run、日志索引、调度记录、审计
Object Store(v1 为本地目录)：执行产物、报告、导入导出文件
```

### 技术选型

| 层级 | 选择 | 说明 |
| --- | --- | --- |
| 后端框架 | Python 3.11+ / FastAPI | 类型安全、异步支持、OpenAPI 文档自动生成 |
| 数据校验 | Pydantic v2 | Flow Schema 与 API DTO 统一建模 |
| 数据库访问 | SQLAlchemy 2.x + Alembic | 声明式模型和数据库迁移 |
| 数据库 | SQLite，开启 WAL | v1.0 单机部署默认方案 |
| 任务调度 | 服务内 Worker + Scheduler | 避免 Redis/RabbitMQ 等额外依赖 |
| 实时通信 | REST + SSE | 前端订阅执行事件，SSE 比 WebSocket 更易降级 |
| 前端 | React 18 + TypeScript + Vite | 管理台场景，组件生态成熟 |
| UI | 现有设计体系优先；无则使用 Ant Design | 表单、表格、流程画布需求密集 |
| 流程画布 | React Flow | 支持 DAG 节点、连线、缩放和小地图 |
| 测试 | pytest、Vitest、Playwright | 覆盖引擎、API 和关键前端流程 |
| 部署 | Docker Compose | Python 服务、静态前端、持久化卷 |

## 3. 核心概念

### Flow

Flow 是一个可版本化的任务编排定义，由元信息和 Step DAG 组成。Flow 分为 `draft` 与 `published` 状态：

- `draft`：可自由编辑，不影响历史执行。
- `published`：生成不可变版本，Run 必须绑定具体 Flow 版本。

### Step

Step 是 Flow 中的一个执行节点。1.0 支持：

| 类型 | 说明 |
| --- | --- |
| `agent` | 调用 Agent Provider，输入 Prompt 和上下文，输出文本、结构化结果或产物引用 |
| `input` | 定义 Run 输入参数，作为全局上下文入口 |
| `template` | 纯模板渲染，不调用 Agent |
| `condition` | 根据表达式选择分支 |
| `parallel` | 并行执行子 Step 或多个分支 |
| `join` | 等待前置分支完成，汇总结果 |
| `analysis` | 汇总执行结果并生成最终报告 |

### Run

Run 是一次 Flow 执行实例，绑定用户、Flow 版本、输入参数、执行状态、事件、日志和产物。Run 具有幂等的 `idempotency_key`，避免重复提交。

### StepRun

StepRun 是 Step 的一次执行记录，保存输入快照、输出、状态、错误、重试次数、开始和结束时间。引擎崩溃恢复时以数据库状态为准。

### Provider

Provider 是 Agent 工具适配器。1.0 内置：

- `claude-cli`：适配 Claude 命令行工具。
- `codex-cli`：适配 Codex 命令行工具。
- `mock`：测试与本地演示用。

Provider 配置包含可执行文件路径、默认参数、环境变量名、超时时间、输出解析方式和可用性检查命令。具体 CLI 参数不得硬编码在 Flow 中，应收敛到适配器实现和系统配置里，便于升级。

## 4. Flow 模型设计

### 4.1 Flow JSON 结构

Flow 版本保存一份完整 JSON，便于导入导出和执行回放。

```json
{
  "schemaVersion": "1.0",
  "name": "代码库调研分析",
  "description": "并行调研架构与风险，最后汇总分析",
  "inputs": [
    {
      "name": "repo_path",
      "type": "string",
      "required": true
    }
  ],
  "steps": [
    {
      "id": "architecture",
      "name": "架构分析",
      "type": "agent",
      "provider": "claude-cli",
      "dependsOn": [],
      "config": {
        "prompt": "分析 {{ inputs.repo_path }} 的架构...",
        "outputFormat": "markdown",
        "timeoutSeconds": 900,
        "maxRetries": 1
      }
    },
    {
      "id": "risk",
      "name": "风险分析",
      "type": "agent",
      "provider": "codex-cli",
      "dependsOn": [],
      "config": {
        "prompt": "评估 {{ inputs.repo_path }} 的主要风险...",
        "outputFormat": "markdown"
      }
    },
    {
      "id": "merge",
      "name": "汇总分析",
      "type": "analysis",
      "dependsOn": ["architecture", "risk"],
      "config": {
        "prompt": "综合以下结果输出最终报告：\n架构：{{ steps.architecture.output }}\n风险：{{ steps.risk.output }}"
      }
    }
  ]
}
```

### 4.2 表达式与上下文

1.0 使用受限模板表达式，不直接执行 Python 或 JavaScript：

- `{{ inputs.xxx }}`：Run 输入。
- `{{ steps.xxx.output }}`：前置 Step 输出。
- `{{ steps.xxx.json.field }}`：结构化输出字段。
- `{{ env.xxx }}`：仅允许访问 Provider 环境变量白名单。

模板引擎建议使用 Jinja2 的 `SandboxedEnvironment`，禁用危险全局函数和过滤器。渲染失败时 Step 进入 `failed` 状态，错误写入 StepRun。

### 4.3 执行状态机

Run 状态：

```text
pending → running → succeeded
                 ↘ failed
                 ↘ cancelled
                 ↘ timeout
```

StepRun 状态：

```text
pending → ready → running → succeeded
                           ↘ failed
                           ↘ skipped
                           ↘ cancelled
                           ↘ timeout
```

执行规则：

1. 发布 Flow 前必须完成 Schema 校验和 DAG 校验。
2. Run 创建后先生成全部 StepRun 的 `pending` 记录。
3. 引擎轮询依赖满足的 Step，将其置为 `ready` 后投递执行。
4. Step 成功后写入输出并触发后继节点。
5. 条件分支不满足时，下游不可达节点标记为 `skipped`。
6. 失败策略由 Step 配置决定：`fail_fast`、重试、或标记失败后继续执行不依赖它的分支。
7. 取消 Run 时，先终止正在运行的 Agent 子进程，再更新未完成 StepRun。
8. 服务重启后，处于 `running` 但无活跃进程的 Run 会进入恢复流程，可重试或标记为 `interrupted`。

## 5. 数据库设计

### 核心表

| 表 | 说明 |
| --- | --- |
| `users` | 用户、密码哈希、状态、角色 |
| `sessions` | 会话 Token、过期时间、IP、User-Agent |
| `flows` | Flow 元信息、所有者、当前状态 |
| `flow_versions` | 不可变 Flow JSON、版本号、创建者、发布时间 |
| `runs` | Run 主记录、Flow 版本、输入、状态、时间、错误 |
| `step_runs` | Step 执行记录、状态、输入输出快照、重试次数 |
| `run_events` | 执行事件流，用于 SSE 回放和进度展示 |
| `agent_logs` | Agent stdout/stderr 索引，日志文件存本地目录 |
| `artifacts` | 产物元信息、文件路径、MIME、大小、校验值 |
| `schedules` | 定时任务配置、Cron、下次触发时间、状态 |
| `audit_logs` | 登录、发布、执行、删除、配置变更审计 |
| `provider_configs` | Provider 系统配置，敏感字段只存引用 |

### 关键字段建议

```sql
flows(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL,        -- draft/published/archived
  current_version INTEGER,
  owner_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)

flow_versions(
  id TEXT PRIMARY KEY,
  flow_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  definition_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(flow_id, version)
)

runs(
  id TEXT PRIMARY KEY,
  flow_id TEXT NOT NULL,
  flow_version INTEGER NOT NULL,
  idempotency_key TEXT,
  status TEXT NOT NULL,
  input_json TEXT NOT NULL,
  error TEXT,
  started_at TEXT,
  finished_at TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
)

step_runs(
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  step_type TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  input_snapshot_json TEXT,
  output_json TEXT,
  error TEXT,
  started_at TEXT,
  finished_at TEXT
)
```

主键建议使用 ULID 或 UUIDv7，便于排序和分页。时间字段统一存储 UTC ISO-8601 字符串。

## 6. Agent 调度与 Provider 适配

### 6.1 调度器职责

- 控制全局并发、单个 Provider 并发、单用户并发。
- 为 StepRun 分配 Worker，不直接在 API Request Handler 中执行长任务。
- 管理子进程超时、取消、stdout/stderr 流式采集。
- 根据配置执行重试，重试必须递增 `attempt`。
- 记录执行耗时、退出码、超时原因和产物。

### 6.2 Provider 接口

```python
class AgentProvider(Protocol):
    name: str

    async def check_health(self) -> ProviderHealth:
        """检查可执行文件和认证状态。"""

    async def execute(self, request: AgentRequest) -> AgentResult:
        """执行 Agent 任务并返回文本、结构化数据和产物。"""

    async def cancel(self, execution_id: str) -> None:
        """取消正在执行的任务。"""
```

`AgentRequest` 包含：

- 渲染后的 Prompt。
- 工作目录，必须在平台允许的 workspace 根目录内。
- 超时和重试策略。
- 输出格式要求。
- 产物目录。
- 环境变量白名单。

`AgentResult` 包含：

- 标准输出、错误输出、退出码。
- 解析后的文本或 JSON。
- 产物列表。
- Token 或成本信息（如果 Provider 能提供）。

### 6.3 CLI 执行约束

- 使用参数数组启动子进程，禁止拼接 Shell 字符串。
- 工作目录必须通过 `resolve` 和 `realpath` 校验，不能逃逸 workspace。
- 只向子进程传入显式允许的环境变量。
- 对 stdout/stderr 做流式读取和大小限制，防止日志无限增长。
- 对执行时间、输出文件数量、产物总大小设置上限。
- Agent 输出默认视为不可信数据，展示前由前端转义，不应直接作为系统指令执行。
- Provider 不可用时返回明确错误，不影响其他 Provider 执行。

## 7. API 设计

### 7.1 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/auth/login` | 登录并创建会话 |
| `POST` | `/api/auth/logout` | 退出登录 |
| `GET` | `/api/auth/me` | 当前用户信息 |

### 7.2 Flow

| 方法 | 路径 | 说明 |
| --- |
| `GET` | `/api/flows` | Flow 列表 |
| `POST` | `/api/flows` | 创建 Flow |
| `GET` | `/api/flows/{flowId}` | Flow 详情 |
| `PUT` | `/api/flows/{flowId}` | 保存草稿 |
| `POST` | `/api/flows/{flowId}/publish` | 校验并发布新版本 |
| `GET` | `/api/flows/{flowId}/versions` | 版本列表 |
| `GET` | `/api/flows/{flowId}/versions/{version}` | 版本详情 |
| `POST` | `/api/flows/{flowId}/validate` | 校验 Flow 定义 |
| `POST` | `/api/flows/import` | 导入 Flow JSON |
| `GET` | `/api/flows/{flowId}/export` | 导出 Flow JSON |

### 7.3 Run

| 方法 | 路径 | 说明 |
| --- | --- |
| `POST` | `/api/runs` | 创建并执行 Run |
| `GET` | `/api/runs` | Run 列表和筛选 |
| `GET` | `/api/runs/{runId}` | Run 详情 |
| `POST` | `/api/runs/{runId}/cancel` | 取消执行 |
| `POST` | `/api/runs/{runId}/retry` | 重试失败 Run |
| `GET` | `/api/runs/{runId}/events` | SSE 事件流 |
| `GET` | `/api/runs/{runId}/steps` | StepRun 列表 |
| `GET` | `/api/runs/{runId}/steps/{stepRunId}` | StepRun 详情 |
| `GET` | `/api/runs/{runId}/artifacts` | 产物列表 |
| `GET` | `/api/artifacts/{artifactId}/download` | 下载产物 |

### 7.4 Provider 与调度

| 方法 | 路径 | 说明 |
| --- | --- |
| `GET` | `/api/providers` | Provider 列表与健康状态 |
| `POST` | `/api/providers/{name}/health-check` | 触发健康检查 |
| `GET` | `/api/schedules` | 定时任务列表 |
| `POST` | `/api/schedules` | 创建定时任务 |
| `PUT` | `/api/schedules/{scheduleId}` | 更新定时任务 |
| `DELETE` | `/api/schedules/{scheduleId}` | 删除定时任务 |
| `POST` | `/api/schedules/{scheduleId}/pause` | 暂停 |
| `POST` | `/api/schedules/{scheduleId}/resume` | 恢复 |

## 8. 前端设计

### 页面结构

```text
/login                 登录
/flows                 Flow 列表
/flows/new             新建 Flow
/flows/:id/edit        Flow 编辑器
/flows/:id/versions    版本管理
/runs                  执行列表
/runs/:id              执行详情
/schedules             定时任务
/settings/providers    Provider 配置
/settings/users        用户与角色（管理员）
/audit                 审计日志（管理员）
```

### Flow 编辑器

- 左侧为 Step 类型面板。
- 中间为 React Flow 画布，支持拖拽、连线、自动布局、缩放。
- 右侧为选中 Step 的配置表单。
- 顶部提供保存草稿、校验、发布、试运行操作。
- 校验错误定位到具体 Step 和字段。

### Run 详情页

- 顶部展示 Run 状态、耗时、Flow 版本、触发人、取消和重试按钮。
- 中间展示 DAG 执行视图，节点实时反映状态。
- 下方提供 Step 列表、日志、输入输出、产物和最终报告 Tab。
- SSE 断线后自动重连，并从最后事件 ID 回放。

### 关键交互

- 长任务不阻塞页面导航。
- 删除操作必须二次确认。
- 日志默认懒加载，支持按 Step 和级别筛选。
- Agent 输出中的 Markdown 可渲染，但链接和 HTML 必须安全处理。
- 表格支持状态、时间、Flow、创建者筛选。

## 9. 鉴权与权限

### 角色

| 角色 | 权限 |
| --- | --- |
| `admin` | 全部功能，包括用户、Provider、审计和系统配置 |
| `editor` | 创建、编辑、发布 Flow，创建和取消 Run |
| `operator` | 执行已有 Flow，不能修改定义 |
| `viewer` | 只读查看 Flow 和 Run |

### 实现要求

- 密码使用 Argon2id 或 bcrypt 哈希。
- 会话 Token 使用服务端生成的随机值，Cookie 设置 `HttpOnly`、`SameSite=Lax`、`Secure`（HTTPS 下）。
- CSRF 使用双提交 Cookie 或 SameSite 策略，写接口必须校验 Origin。
- API 权限在服务端强制校验，前端隐藏按钮不作为安全边界。
- 所有敏感操作写入 `audit_logs`。

## 10. 安全设计

1. **工作区隔离**：每个 Run 使用独立工作目录，路径必须位于配置的 workspace 根目录下。
2. **Prompt 输入限制**：限制输入长度、文件大小和嵌套层级。
3. **模板沙箱**：禁止模板访问文件系统、网络和任意对象属性。
4. **CLI 受控调用**：固定 Provider 支持的参数形式，不提供任意命令执行入口。
5. **输出安全**：Agent 输出不可信，不能直接作为 SQL、Shell、路径或权限判断依据。
6. **产物下载**：下载路径必须由 artifact 数据库记录推导，禁止读取用户提交路径。
7. **日志脱敏**：Token、API Key、密码和认证头不得写入日志。
8. **并发与资源限制**：限制 Run 数、Step 并发、日志大小、产物大小和执行时长。
9. **审计**：登录、发布、删除、Provider 配置变更、Run 创建和取消必须留痕。

## 11. 可观测性

- 每个 Run 生成唯一 `trace_id`，日志统一携带。
- 记录 API 请求耗时、引擎调度耗时、Agent 执行耗时、排队耗时。
- 记录 Provider 版本、退出码、超时、重试次数。
- 提供运行历史和成功率统计。
- 1.0 输出结构化日志到文件和控制台，不强制接入外部 APM。

## 12. 测试策略

| 类别 | 覆盖内容 |
| --- | --- |
| 单元测试 | Flow Schema、DAG 校验、模板沙箱、状态机、重试策略 |
| Provider 测试 | Mock CLI、超时、取消、退出码、日志截断、环境变量 |
| API 测试 | 认证、RBAC、CRUD、幂等、分页、错误响应 |
| 引擎集成测试 | 顺序、并行、条件、失败继续、失败终止、服务重启恢复 |
| 前端测试 | Flow 编辑器保存与校验、Run 进度、日志展示、登录态 |
| E2E 测试 | 登录 → 创建 Flow → 发布 → 执行 → 查看报告 |

验收标准：

- 核心模块单测覆盖率不低于 80%。
- 所有 API 错误返回稳定 JSON 结构。
- 引擎取消和超时路径有自动化测试。
- Mock Provider 可以完整跑通 E2E。
- 关键迁移可以在空库和升级库上重复执行。

## 13. 部署方案

### 目录结构

```text
AgentFlow/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── engine/
│   │   ├── providers/
│   │   ├── scheduler/
│   │   └── main.py
│   ├── alembic/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── api/
│   │   └── stores/
│   └── package.json
├── docs/
├── docker-compose.yml
└── README.md
```

### Docker Compose

服务划分：

- `backend`：FastAPI + 内置 Worker 和 Scheduler。
- `frontend`：构建 React 静态文件，由 Nginx 提供并反向代理 `/api`。

持久化卷：

- `/data/agentflow/agentflow.db`
- `/data/agentflow/workspaces/`
- `/data/agentflow/artifacts/`
- `/data/agentflow/logs/`

### 配置项

| 配置 | 说明 |
| --- | --- |
| `AGENTFLOW_DB_PATH` | SQLite 文件路径 |
| `AGENTFLOW_WORKSPACE_ROOT` | Run 工作区根目录 |
| `AGENTFLOW_ARTIFACT_ROOT` | 产物目录 |
| `AGENTFLOW_LOG_ROOT` | 日志目录 |
| `AGENTFLOW_MAX_CONCURRENT_RUNS` | 全局最大并发 Run |
| `AGENTFLOW_PROVIDER_CONFIG_PATH` | Provider 配置路径 |
| `AGENTFLOW_SESSION_TTL` | 会话有效期 |
| `AGENTFLOW_CORS_ORIGINS` | 允许的前端来源 |

## 14. 实施阶段

### 阶段 0：项目基线（0.5 周）

目标：建立可维护的工程基础。

- 初始化 monorepo：`backend/`、`frontend/`、`docs/`。
- 配置 Python、Node、格式化、Lint、pytest、Vitest。
- 配置 Docker Compose 和本地开发脚本。
- 建立数据库迁移基线。
- 定义 OpenAPI 规范和错误响应格式。

验收：`docker compose up` 可启动空服务，健康检查通过，CI 可运行测试。

### 阶段 1：数据模型与 Flow Schema（1 周）

目标：完成核心领域模型。

- 实现 users、flows、flow_versions、runs、step_runs 等表。
- 实现 Flow Schema、JSON Schema 校验、导入导出。
- 实现 DAG 校验：环路、重复 ID、缺失依赖、不可达节点。
- 实现模板沙箱和上下文解析。
- 编写领域模型单测。

验收：非法 Flow 无法保存和发布；合法 Flow 可导入导出并保持一致。

### 阶段 2：Flow 引擎与 Mock Provider（1.5 周）

目标：先跑通引擎，再接真实 Agent。

- 实现 Run 创建、StepRun 生成、状态机。
- 实现顺序、并行、条件、join、analysis。
- 实现重试、超时、取消、失败策略。
- 实现 run_events 和 SSE 事件输出。
- 实现 Mock Provider。
- 实现服务重启后的 Run 恢复策略。

验收：Mock Flow 可完整执行并生成报告；取消、失败、超时、重试路径有测试覆盖。

### 阶段 3：Agent Provider 适配（1.5 周）

目标：接入真实 CLI 工具。

- 实现 Provider 注册、配置加载、健康检查。
- 实现 Claude CLI 适配器。
- 实现 Codex CLI 适配器。
- 实现子进程流式日志、取消、超时和资源限制。
- 实现产物采集与下载。
- 编写 Provider 契约测试。

验收：真实 Provider 可执行样例任务；不可用、超时、取消、异常退出都有明确状态。

### 阶段 4：API 与鉴权（1 周）

目标：提供完整稳定的服务端接口。

- 实现登录、退出、会话管理和当前用户接口。
- 实现 RBAC 和操作级权限校验。
- 实现 Flow、Run、Provider、Artifact API。
- 实现分页、筛选、排序、幂等和统一错误结构。
- 实现审计日志。

验收：OpenAPI 文档完整；未登录和越权访问均返回 401/403；敏感操作有审计记录。

### 阶段 5：React 前端（2 周）

目标：提供可日常使用的管理台。

- 登录态、路由守卫、全局布局。
- Flow 列表、创建、编辑、版本管理。
- React Flow 画布和 Step 配置表单。
- Flow 校验、发布、导入导出。
- Run 列表、创建、详情、取消、重试。
- DAG 实时状态、日志、输入输出、产物和报告展示。

验收：用户可以通过前端完成登录到查看最终报告的完整闭环。

### 阶段 6：调度与运维能力（1 周）

目标：让平台从可演示变为可运营。

- 实现定时任务 CRUD、启停和下次触发时间计算。
- 实现错过触发补偿策略和手动立即执行。
- 实现运行历史统计和失败列表。
- 实现日志文件轮转和清理策略。
- 实现产物保留策略和存储大小限制。
- 实现备份与恢复说明。

验收：定时任务可稳定触发；日志和产物不会无限增长；备份恢复文档可执行。

### 阶段 7：安全加固与 1.0 发布（1 周）

目标：完成发布质量验证。

- 安全清单检查和依赖漏洞扫描。
- 渗透式用例测试：越权、路径穿越、CSRF、日志泄露、超大输入。
- 性能测试：并发 Run、SSE 连接、日志写入、前端大 Flow 渲染。
- Playwright E2E 覆盖主流程。
- 完善用户手册、部署手册和故障排查文档。
- 发布 1.0 版本和迁移基线。

验收：无 P0/P1 缺陷；主流程自动化测试通过；升级脚本和回滚方案验证完成。

## 15. 1.0 验收场景

1. 管理员登录后配置 Provider，健康检查通过。
2. 编辑者创建包含并行 Agent Step 和最终分析 Step 的 Flow。
3. Flow 校验通过并发布为版本 1。
4. 操作者输入参数发起执行。
5. 前端实时展示每个 Step 的状态、日志和输出。
6. 引擎调用 Claude CLI 和 Codex CLI 完成任务。
7. 最终 analysis Step 汇总结果并生成报告。
8. 用户下载产物并查看审计记录。
9. 定时任务按配置自动触发新 Run。
10. 服务重启后，历史 Run 可查询，异常 Run 可重试。

## 16. 1.0 后演进方向

- PostgreSQL 存储和多节点 Worker。
- Agent MCP 工具协议支持。
- 更丰富的 Human-in-the-loop 审批节点。
- 流式结构化输出和中间事件展示。
- 成本、Token 和质量评估报表。
- Flow 模板市场和团队共享空间。
- 更强的沙箱执行环境与网络策略。
