# Another Atom V1 架构设计

[toc]

- 文档状态：V1 实施基线
- 更新日期：2026-07-11
- 产品文档：[Another Atom V1 产品需求文档](./another-atom-v1-prd.md)
- 参考分析：[Atoms 参考产品功能分析](../reference/atoms-reference-analysis.md)
- 提交说明：[笔试提交说明](./submission-note.md)

## 1. 架构结论

Another Atom V1 只交付一种运行形态：**部署在 Railway 的 Cloud Demo**。

用户通过 React Visual Studio 输入需求；Python 服务调用真实 LLM 生成经过 Pydantic 校验的 Blueprint 与 AppSpec；确定性 Renderer 将 AppSpec 写入固定 React 模板；异步 Build Worker 完成构建；用户在浏览器中预览、修改、保存版本并显式发布。

```text
┌──────────────────────────── 用户交互层 ────────────────────────────┐
│                                                                  │
│                     React Visual Studio                          │
│  Prompt / Blueprint 审批 / 构建事件 / 应用预览 / 修改 / 发布       │
│                              │                                   │
└──────────────────────────────│───────────────────────────────────┘
                               │ REST + SSE
                               │ OpenAPI 类型同步
                               ▼
┌──────────────────────── Railway Web Service ─────────────────────┐
│                                                                 │
│  FastAPI                                                        │
│     │                                                           │
│     ├── Auth / Project / Session / Version / Publish            │
│     │                                                           │
│     ├── LLM Orchestrator                                        │
│     │      Prompt → Blueprint → 审批 → AppSpec                  │
│     │                         │                                  │
│     │                         ▼                                  │
│     └── Build Job Queue → Bounded Worker                         │
│                               │                                  │
│                               ▼                                  │
│                    Deterministic Renderer                        │
│                    固定模板 / 固定依赖 / 固定命令                 │
│                               │ npm run build                    │
│                               ▼                                  │
│                    Preview / Published Build                     │
└──────────────────────┬───────────────────────┬───────────────────┘
                       │                       │
                       ▼                       ▼
                PostgreSQL              Persistent Volume
        用户/Session/配额/Job/版本       附件/工作区/dist
                       │
                       ▼
                OpenAI / 其他 LLM
```

本版本不实现 Terminal CLI、本地 Agent Runtime、SQLite、本地工作区或 `localhost` Dev Server。这些能力属于 P1，不参与 V1 验收。

## 2. 已确认的架构决策

### 2.1 V1 必须实现

- 真实 LLM 调用，不使用预设文本替代 Blueprint 或 AppSpec。
- 结构化 Blueprint 与 AppSpec，所有模型输出都必须经过 Pydantic 校验。
- 用户确认 Blueprint 后才能创建 Build Job。
- 固定 React 模板、固定依赖和固定构建命令。
- 构建脱离 HTTP 请求生命周期，通过持久化异步 Job 执行。
- React Visual Studio 通过 SSE 查看 LLM、构建和验证事件。
- PostgreSQL 持久化用户、项目、Session、Run、Job、版本、配额和附件元数据。
- Railway Volume 保存附件、项目工作区和构建产物。
- 同一用户拥有多个 Session，所有 Session 共享账户配额。
- 公开 Preview、显式 Publish、Update 与 Unpublish。

### 2.2 V1 明确不实现

- Terminal CLI 或本地仓库执行。
- SQLite 与 PostgreSQL 同步。
- `npm install`、动态依赖或模型生成的 Shell 命令。
- 任意技术栈、任意文件结构或任意后端生成。
- 公网多租户任意代码执行沙箱。
- 模型选择器和真实多 Agent 并行。
- 生成应用内部的数据库、认证、支付和订单系统。
- Stripe 真实支付、Wallet、充值和发票。

## 3. 产品执行链路

```text
User Prompt
    |
    v
Authenticate User
    |
    v
Create Project + Session
    |
    v
Reserve LLM Quota
    |
    v
Planner Agent -> Blueprint + support_level -> Pydantic Validation
    |                    |
    |                    `-- invalid -> bounded retry -> run.failed
    v
User Edit / Approve
    |
    v
Designer Agent -> VisualSpec -> Pydantic Validation
    |
    v
Engineer Agent -> AppSpec -> Pydantic Validation
    |
    v
Create Build Job -> Return 202
    |
    v
Worker Lease Job
    |
    v
Renderer -> Fixed React Template -> npm run build
    |
    +-- failed -> build.failed -> run.failed
    |
    v
Deterministic ValidationReport
    |
    v
QA Agent -> QAReview -> Preview Ready
    |
    v
User Follow-up -> New AppSpec -> New Build Job -> New Version
    |
    v
User Explicitly Publishes Selected Version
    |
    v
Public HTTPS URL
```

`publish` 不属于 Agent Loop。Agent Run 在生成通过校验的 Preview Version 后结束；发布是用户显式调用平台 API 的独立状态机。

## 4. 组件设计

### 4.1 React Visual Studio

技术：React、TypeScript、Vite。

职责：

- Prompt Composer 与附件选择。
- Blueprint 展示、编辑、确认和拒绝。
- 构建阶段、工具事件、错误和重试入口。
- iframe 应用预览及 Desktop/Mobile 尺寸切换。
- Follow-up 修改、版本选择、Restore 和 Resolve。
- Publish、Update 与 Unpublish。

Visual Studio 不直接访问 LLM、数据库、Volume 或工作区文件。

### 4.2 FastAPI Application Service

技术：FastAPI、Pydantic、SQLAlchemy、Alembic、Uvicorn。

职责：

- 平台用户身份与资源归属校验。
- Project、Session、Run、Attachment、Version 和 Deployment API。
- Plan、Quota Account 和 Usage Ledger。
- 启动 LLM Run 与创建 Build Job。
- 将持久化事件通过 SSE 推送给浏览器。
- 托管 Visual Studio 和生成应用的静态构建结果。

API 只负责创建异步任务和返回状态，不在请求协程中执行 `npm run build`。

### 4.3 Sequential Role Orchestrator

技术：OpenAI Agents SDK、Pydantic Structured Output。

V1 使用四个角色配置组成固定顺序 Pipeline。每个角色是独立的 Agents SDK `Agent` 实例，拥有独立 instruction 和结构化输出，但不具备自主编排能力。

```text
Team Mode

Planner Agent -> Blueprint -> user approval
    -> Designer Agent -> VisualSpec
    -> Engineer Agent -> AppSpec
    -> Renderer / Build / deterministic ValidationReport
    -> QA Agent -> QAReview

Engineer Mode

Engineer Agent -> Blueprint -> user approval -> AppSpec
    -> Renderer / Build / deterministic ValidationReport
```

V1 角色 Pipeline 的约束：

- 顺序固定，不由模型动态决定下一角色。
- 不并行执行，不进行 Agent 间自由讨论。
- 阶段之间只传递经过 schema 校验的显式产物，不共享隐藏长期记忆。
- 每个阶段独立记录模型、用量、尝试次数、输入产物版本和输出产物。
- QAReview 可以提出问题，但不能覆盖确定性 Validator 的 Build/Validation 结果，也不能自动触发无限返工。
- 动态委派、独立工具权限、并行执行、反馈循环和结果合并属于 V2 自主多 Agent。

LLM 只允许输出领域协议：

- `Blueprint`
- `VisualSpec`
- `AppSpec`
- `RevisionSpec`
- `QAReview`

LLM 不直接拥有 Shell、文件系统或 Publish Tool。Agents SDK 用于模型调用、结构化输出、Run Hooks、Usage 和 Trace；业务 Session、配额和状态仍由应用数据库管理。

Planner 的 Blueprint 必须包含：

```text
support_level: supported | adapted | unsupported
supported_product_type: product_catalog
adaptation_summary: string[]
```

`unsupported` 不得进入 Designer 或 Build；`adapted` 必须等待用户确认映射结果。

### 4.4 阶段产物契约

前端可以展示 Planner、Designer、Engineer、QA，但每个阶段必须绑定可检查产物：

| 阶段名称 | 实际执行 | 必须产生的产物 |
| --- | --- | --- |
| Planner | Planner Agent 规范化需求并判断支持范围 | `Blueprint` |
| Designer | Designer Agent 生成视觉约束 | `VisualSpec` |
| Engineer | Engineer Agent 生成应用结构 | `AppSpec`，随后创建 `BuildJob` |
| QA | 确定性 Validator 先产出结果，QA Agent 再解释和审查 | `ValidationReport`、`QAReview` |

界面统一使用“Team Mode · 分阶段接力”或“Sequential role pipeline”。不得使用“并行协作”“团队自主讨论”等文案。

### 4.5 Deterministic Renderer

Renderer 是 V1 安全边界的核心：

- 只接受通过 schema 校验的 AppSpec。
- 只写入当前项目工作区。
- 只修改模板声明允许的配置、内容和资产文件。
- 依赖在 Docker 镜像构建阶段预装。
- 运行时禁止 `npm install` 和 `package.json` 依赖变更。
- 构建命令固定为平台配置，不接受模型提供的命令字符串。
- 同一个 AppSpec 必须产生语义一致的项目结构。

V1 的自然语言修改先生成新的 RevisionSpec/AppSpec，再由 Renderer 重新物化。模型不直接 patch 任意源码。

### 4.6 Build Job Runner

构建必须异步执行：

```text
POST build request
      |
      v
insert build_jobs(status=queued)
      |
      v
HTTP 202 + build_job_id
      |
      v
background worker leases job
      |
      v
render -> build -> validate -> persist result
```

V1 使用一个 Railway Web Service 内的持久化后台 Worker：

- `MAX_CONCURRENT_BUILDS=1` 作为初始值。
- 使用 PostgreSQL lease 防止同一 Job 重复执行。
- 服务重启后重新领取 queued 或 lease 过期的 Job。
- 使用异步子进程执行固定构建命令。
- 每个 Job 设置可配置超时、输出上限和工作区磁盘上限。
- 禁止启用多个 Uvicorn Worker 后各自无协调地消费任务。

部署前必须使用目标 Railway 规格完成并发 1 的内存和构建耗时压测。未通过时不能提高并发；具体实例内存必须由压测结果决定，当前文档不预设数值。

## 5. JavaScript 与 Python 通信

V1 使用 **REST + SSE + OpenAPI**，不使用 WebSocket。

```text
React Studio ---- REST ----> FastAPI
React Studio <---- SSE ----- Run / Build / Validation Events
React Studio ---- iframe --> Generated Preview
```

核心 API：

```text
POST /api/projects
POST /api/projects/{project_id}/attachments
POST /api/sessions
GET  /api/sessions/{session_id}
POST /api/sessions/{session_id}/messages
GET  /api/sessions/{session_id}/events
POST /api/runs/{run_id}/approve
POST /api/runs/{run_id}/cancel
POST /api/builds/{build_id}/retry
GET  /api/projects/{project_id}/versions
POST /api/projects/{project_id}/publish
POST /api/projects/{project_id}/unpublish
GET  /api/projects/{project_id}/export
```

FastAPI 的 Pydantic 模型是 API Contract 的事实来源。前端通过 OpenAPI 生成 TypeScript 类型，不手工维护第二份 Blueprint、AppSpec、Event 或 Error 定义。

### 5.1 事件协议

```json
{
  "event_id": "evt_123",
  "project_id": "project_123",
  "session_id": "session_123",
  "run_id": "run_123",
  "type": "build.started",
  "timestamp": "2026-07-11T00:00:00Z",
  "payload": {
    "build_id": "build_123"
  }
}
```

核心事件：

```text
run.started
llm.streaming
blueprint.generated
approval.required
role_stage.started
role_stage.completed
app_spec.generated
build.queued
build.started
build.failed
validation.issue_detected
validation.completed
preview.ready
run.failed
run.completed
deployment.started
deployment.completed
deployment.failed
```

事件先写入 `run_events`，再推送 SSE。浏览器断线重连后按 `event_id` 补取，不能只依赖内存广播。

## 6. 状态模型

### 6.1 Agent Run

```text
Created -> PlannerRunning -> AwaitingApproval
             |                    |
             v                    v
           Failed          DesignerRunning
                                    |
                                    v
                             EngineerRunning
                                    |
                                    v
                               BuildQueued
                                    |
                             build callback
                                    v
                                QARunning
                                    |
                                    v
                           Completed / Failed
```

### 6.2 Build Job

```text
Queued -> Leased -> Rendering -> Building -> Validating -> Succeeded
   ^         |           |           |            |
   |         +-----------+-----------+------------+--> Failed
   |
manual retry creates a new attempt
```

### 6.3 Publish

```text
Unpublished -> Publishing -> Live -> Updating -> Live
                    |                    |
                    v                    v
                  Failed               Failed

Live -> Unpublishing -> Unpublished
```

Build 成功不会自动发布。Publish 必须携带用户选择的 `version_id`。

## 7. 数据设计

### 7.1 存储分工

PostgreSQL：

- 用户、Plan、Subscription、Quota 和 Usage Ledger。
- Project、Session、AgentRun、AgentStageRun、RunEvent、ProductEvent 和 BuildJob。
- Attachment 元数据、ProjectVersion 和 Deployment。

Railway Persistent Volume：

- 上传附件。
- 每个项目的受控工作区。
- 构建日志和 `dist` 产物。
- 发布版本的不可变静态快照。

### 7.2 核心关系

```text
User
  |---- n Project
  |         |---- n Attachment
  |         |---- n Session
  |         |          `---- n AgentRun ---- n AgentStageRun
  |         |                    |---- n RunEvent
  |         |                    `---- n BuildJob
  |         |---- n ProductEvent
  |         |---- n ProjectVersion
  |         `---- n Deployment
  |
  |---- 1 Subscription ---- 1 Plan
  |---- 1 QuotaAccount
  `---- n UsageLedger
```

### 7.3 核心表

- `users`：平台用户身份和状态。
- `plans`：周期配额与功能边界。
- `subscriptions`：当前方案、有效期和状态；V1 可由种子数据或管理操作设置。
- `quota_accounts`：可用、预占和已结算额度。
- `usage_ledger`：每次预占、结算和释放记录。
- `projects`：项目名称、状态和当前版本。
- `sessions`：项目下可恢复的模型上下文。
- `agent_runs`：一次需求或修改对应的 LLM 运行。
- `agent_stage_runs`：Planner、Designer、Engineer、QA 各阶段的输入产物、输出产物、模型、用量、尝试次数和状态。
- `run_events`：可重放的 SSE 事件。
- `product_events`：用于价值漏斗的用户行为事件，与运行时 `run_events` 分离。
- `build_jobs`：异步构建状态、lease、attempt 和错误。
- `attachments`：附件元数据和 Volume 路径。
- `project_versions`：Blueprint、VisualSpec、AppSpec、ValidationReport 和构建产物引用。
- `deployments`：公开 URL、所选版本和发布状态。

### 7.4 attachments

建议字段：

```text
id
user_id
project_id
session_id
file_name
mime_type
size_bytes
storage_path
status
created_at
deleted_at
```

上传流程先创建 metadata，再写入 Volume，最后将状态改为 ready。Blueprint 只能引用 ready 附件。删除操作采用软删除并异步清理文件，避免数据库已删除但文件操作失败后无法追踪。

### 7.5 build_jobs

建议字段：

```text
id
project_id
session_id
run_id
version_id
status
attempt
lease_owner
lease_expires_at
started_at
finished_at
error_code
log_path
```

重试创建新 attempt，保留失败日志，不覆盖上一轮记录。

### 7.6 product_events

最小字段：

```text
event_id
event_name
user_id
project_id
session_id
run_id
timestamp
mode
outcome
error_code
properties_json
```

P0 漏斗事件为：`prompt_submitted`、`scope_classified`、`blueprint_generated`、`blueprint_approved`、`role_stage_completed`、`build_succeeded`、`preview_opened`、`revision_applied`、`published`、`public_app_opened`。

公开页面访问等无登录事件允许 `user_id`、`session_id` 和 `run_id` 为空。`product_events` 不保存完整 Prompt、附件内容或模型私有推理。没有真实用户样本前只采集基线，不预设审批率和发布转化率目标。

### 7.7 Export JSON

Export 由应用服务从已持久化 Contract 组装，不读取工作区源码。最小字段以 PRD 为准，包括 `schema_version`、`exported_at`、`project`、`blueprint`、`visual_spec`、`app_spec`、`current_version`、`versions`、`publication` 和附件公开元数据。

必须排除 LLM Key、用户凭证、Volume 绝对路径、原始对话和 Usage Ledger。

## 8. 配额与订阅

V1 的 Plan 与配额是真实平台能力，但支付不是。

```text
Plan -> Subscription -> Quota Account -> Usage Ledger
```

每个角色阶段及其结构化输出重试都作为独立模型请求计量：

```text
verify user and session
    -> reserve estimated quota in a database transaction
    -> call LLM
    -> read actual usage
    -> settle actual usage
    -> release unused reservation
```

调用失败也必须记录 Ledger 并释放未使用预占。不能在模型返回后才检查配额，否则同一账户的并发 Session 可以透支。

V1 不接 Stripe。未来 Stripe Webhook 只更新 Subscription，不直接修改 Session 或历史 Ledger。

## 9. 错误与重试契约

### 9.1 LLM 错误

- Provider 超时、限流或可重试 5xx：最多 3 次总尝试，采用退避等待。
- Pydantic 结构校验失败：将校验错误作为修正上下文，最多 3 次总尝试。
- 每次实际 Provider 调用分别预占和结算用量。
- 达到上限后，Agent Run 进入 `Failed`，发送 `run.failed`。
- 错误码至少区分 `LLM_PROVIDER_ERROR`、`INVALID_MODEL_OUTPUT` 和 `QUOTA_EXCEEDED`。

达到最大尝试次数后，平台不得静默使用预设结果。Project 保留 Prompt、附件和 Session，进入 Needs input，并提供：

- Retry：重新执行当前失败角色阶段。
- Edit request：返回输入或 Blueprint 编辑。
- Use starter Blueprint：用户主动选择的非 AI 回退，并在 UI 与版本来源中明确标记。

`QUOTA_EXCEEDED` 不提供自动重试，也不显示为 Provider 故障。

### 9.2 Build 错误

- 编译、资源或超时错误先写入 `build.failed`，随后将聚合 Run 标记为 Failed，错误阶段为 BUILD。
- 固定输入导致的编译失败不自动重复执行，因为相同输入不会产生不同结果。
- Worker 被终止或 lease 过期时允许自动重新领取一次；这属于执行恢复，不是构建逻辑重试。
- 用户点击 Retry 后创建新的 attempt，并保留原日志。
- 错误码至少区分 `RENDER_FAILED`、`BUILD_FAILED`、`BUILD_TIMEOUT`、`RESOURCE_LIMIT`。

### 9.3 Resolve 与真实构建失败

PRD 中的预设路由错误不是 Build Error：

```text
真实构建错误
build.failed -> run.failed -> Retry Build

预设应用问题
validation.issue_detected -> User Resolve
    -> deterministic RevisionSpec
    -> new BuildJob
    -> ProjectVersion(source=Resolve)
```

两条路径共用事件和版本基础设施，但使用不同状态与文案，不能把预设问题包装成 LLM 自动修复了真实编译错误。

## 10. 安全边界

V1 的模型没有任意执行权限。必须满足：

- AppSpec、RevisionSpec 和附件引用全部经过 schema 与资源归属校验。
- 工作区固定为 `/data/workspaces/{user_id}/{project_id}/`。
- Renderer 只写模板允许目录。
- 运行时禁止安装依赖、修改依赖清单和执行任意 Shell。
- 构建子进程使用固定命令、超时、输出和磁盘上限。
- 云端用户不能读取其他用户的附件、工作区、日志或 Preview。
- LLM API Key 只存在于 Railway 服务端环境变量。
- Preview 响应设置隔离策略，不允许生成应用访问平台管理 API。
- 发布前检查文件类型、总体积和入口文件。
- 配额预占使用数据库事务。

如果未来开放任意代码、依赖安装或网络访问，必须引入每次运行独立的容器或虚拟机沙箱，不能在当前共享容器中逐项放宽。

## 11. Railway 部署

```text
GitHub 仓库
     |
     | push 自动部署
     v
┌──────────────── Railway ────────────────┐
│                                        │
│  Docker Web Service                    │
│  · Python / FastAPI                    │
│  · OpenAI Agents SDK                   │
│  · Bounded Build Worker                │
│  · Node.js / 预装固定依赖               │
│  · React Studio 静态文件                │
│  · Preview / Publish                   │
│                                        │
│  对外提供一个 HTTPS 域名：               │
│  /                  Visual Studio       │
│  /api/*             FastAPI             │
│  /events/*          SSE                 │
│  /preview/{id}/*    预览版本             │
│  /apps/{id}/*       已发布版本           │
│                                        │
│  Persistent Volume                     │
│  · 附件 / 项目工作区 / dist / 日志       │
│                                        │
│  PostgreSQL Service                    │
│  · 用户 / Session / 配额 / Job / 版本    │
└───────────────────┬────────────────────┘
                    |
                    v
              OpenAI / 其他 LLM
```

### 11.1 Docker

镜像构建阶段：

1. 安装固定 Node.js 依赖并构建 React Studio。
2. 安装 Python API、Agent 和数据库依赖。
3. 复制固定应用模板和 Renderer。
4. 不在运行时执行依赖安装。

启动阶段：

1. 执行 Alembic migration。
2. 启动单实例 FastAPI 和持久化 Build Worker。
3. Worker 从 PostgreSQL 领取 Build Job。

### 11.2 PostgreSQL 与 Volume

Railway PostgreSQL 是独立、按资源计费的非托管服务，不是免费附赠数据库。V1 需要配置备份并验证恢复流程。

Volume 保存工作区和构建产物，但不能替代 PostgreSQL 元数据。服务重启或重新部署后，数据库与 Volume 中的必要状态必须保持一致。

### 11.3 GitHub

GitHub 负责源代码、文档、版本历史和触发 Railway 自动部署。GitHub Pages 只能托管静态内容，不能单独运行 FastAPI、Agent、PostgreSQL 或 Build Worker。

## 12. 代码组织

```text
another-atom/
├── another_atom/
│   ├── api/              FastAPI routes and SSE
│   ├── agent/            LLM orchestration and structured outputs
│   ├── build/            job leasing, renderer and build runner
│   ├── contracts/        Pydantic API, AppSpec and event models
│   ├── domain/           projects, sessions, quota and versions
│   └── storage/          PostgreSQL repositories and volume paths
├── studio/               React Visual Studio
├── templates/
│   └── react-app/        fixed dependencies and controlled template
├── migrations/
├── tests/
├── docs/
├── Dockerfile
├── README.md
└── README.zh-CN.md
```

Renderer、Build Worker 和领域服务不能直接定义第二套 AppSpec。所有层共享 `contracts` 中的 Pydantic/OpenAPI 协议。

## 13. V1 实施顺序

1. 定义 Blueprint、VisualSpec、AppSpec、QAReview、Event、Export 和 Error Contract。
2. 建立 PostgreSQL、Alembic 与用户/Project/Session 基础模型。
3. 实现 Plan、配额预占和 Usage Ledger。
4. 实现 Planner、Designer、Engineer、QA 固定顺序 Orchestrator、阶段持久化和配额结算。
5. 完成 AppSpec 与固定 React Renderer。
6. 实现 `build_jobs`、单并发 Worker 和持久化事件。
7. 实现 Visual Studio 的 Blueprint、SSE 和 iframe Preview。
8. 实现附件、ProductEvent 漏斗、Export JSON、一次 Follow-up 修改和 ProjectVersion。
9. 实现 Resolve、Restore 和显式 Publish。
10. Docker 化并部署 Railway Web Service、PostgreSQL 和 Volume。
11. 在目标 Railway 规格完成内存、构建耗时和重启恢复压测。

## 14. V1 验收

- 用户能从 Cloud Visual Studio 输入需求并获得真实 LLM 生成的 Blueprint。
- Team Mode 按 Planner、Designer、Engineer、QA 固定顺序执行，每个阶段都有独立 AgentStageRun 和可检查产物。
- UI 明确标注“分阶段接力”，不声称并行或自主多 Agent。
- 非商品目录输入必须进入 supported、adapted 或 unsupported；unsupported 不创建 Build Job。
- 未确认 Blueprint 时不会创建 Build Job。
- AppSpec 不能改变依赖、构建命令或工作区边界。
- HTTP 创建构建后立即返回，构建由异步 Worker 完成。
- 同一实例的构建并发不超过配置上限，初始为 1。
- 用户可以恢复两个不同 Session，且上下文不会串线。
- 并发模型调用不能绕过同一账户配额。
- 附件元数据与 Volume 文件状态一致。
- Build Error 与预设 Resolve 问题使用不同事件和状态。
- 用户明确选择版本后才能 Publish。
- Railway 重启后 queued Job、项目、版本和发布结果可以恢复。
- 部署后获得可公开测试的 HTTPS 地址。
- Golden Path 连续 5 次完成，产品漏斗事件完整率为 100%，跨 Session 串事件为 0。
- Export JSON 满足最小 Contract，且不包含密钥、凭证、绝对路径、原始对话和内部用量流水。

## 15. P1：CC 式本地执行

P1 的长期方向是类似 Claude Code 的本地 Agent Runtime：

```text
Terminal CLI
     |
     v
Local Python Agent Runtime
     |
     ├── 读取和修改本地项目文件
     ├── 执行受控 Shell / Git / npm
     ├── SQLite Session 与版本索引
     └── 启动 localhost Dev Server
                    |
                    v
             Local Visual Studio

Local Runtime ---- HTTPS ----> Cloud Auth / Quota / LLM Gateway
```

P1 必须重新设计：

- Python/Node 安装与跨平台打包。
- 本地权限审批和工作区信任模型。
- 本地进程、端口和 Dev Server 生命周期。
- SQLite 项目如何上传、同步或发布到云端。
- 本地项目与 Cloud Project 的冲突处理。

在这些协议确定前，V1 README 和产品界面不得声称已经支持本地仓库执行。
