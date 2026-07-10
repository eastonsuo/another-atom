# Another Atom V1 架构设计

[toc]

- 文档状态：V1 实施基线
- 更新日期：2026-07-11
- 产品文档：[Another Atom V1 产品需求文档](./another-atom-v1-prd.md)
- Agent 设计：[Another Atom V1 Agent 设计](./agent-design.md)
- 参考分析：[Atoms 参考产品功能分析](../reference/atoms-reference-analysis.md)

## 1. 技术选型

V1 采用单一 Cloud 执行面：React 提供可视化工作台，FastAPI 承担 API、Agent 编排和领域服务，PostgreSQL 保存业务事实，受控 Worker 负责构建，整体通过 Docker 部署到 Railway。

| 层次 | V1 选型 | 选择原因 | V1 边界 |
| --- | --- | --- | --- |
| 前端工作台 | React + TypeScript + Vite | 适合实现状态密集的 Studio、类型化 API 和 iframe Preview | 不直接访问 LLM、数据库或工作区文件 |
| API 与领域服务 | Python + FastAPI + Pydantic + Uvicorn | 与 Agent/结构化输出保持同一语言栈；Pydantic 同时约束 API 和模型产物 | HTTP 请求只创建任务，不同步执行构建 |
| Agent 编排 | 自有 Orchestrator + Provider Adapter（Ollama Cloud / Mock）+ Pydantic | 支持按 Run 选择模型、角色 instruction、有界重试和结构化校验 | Ollama Cloud 不提供服务端 Structured Outputs，Schema 由本地严格校验 |
| 前后端通信 | REST + SSE + OpenAPI | REST 承担命令，SSE 推送可恢复事件，OpenAPI 生成 TypeScript 类型 | 不引入 V1 不需要的 WebSocket 双向协议 |
| 业务数据库 | PostgreSQL + SQLAlchemy + Alembic | 支持多用户、Session、配额事务、Job lease、版本和发布状态 | 不使用 SQLite，也不设计本地/云端双向同步 |
| 文件与构建 | Railway Persistent Volume + Node.js/npm + Deterministic Renderer | Volume 保存工作区和 dist；固定 Renderer、依赖和命令便于控制资源与风险 | 运行时不执行 `npm install`，不接受模型生成的 Shell 命令 |
| 异步执行 | FastAPI 服务内的单并发持久化 Build Worker | V1 无需额外消息队列即可脱离 HTTP 生命周期，并通过 PostgreSQL lease 恢复 | 提高并发前必须在目标 Railway 规格压测 |
| 部署 | Docker + Railway Web Service + Railway PostgreSQL + Volume | 一个 GitHub 仓库即可自动部署公开 HTTPS 服务，并同时支持 API、SSE、Preview 和发布路由 | Railway 资源规格和成本以实际压测与账单为准 |

### 1.1 选型原则

1. **Contract 优先**：Blueprint、ArchitectureSpec、AppSpec、Event、Error 和 Export 以 Pydantic 模型为事实来源。
2. **模型与权限分离**：LLM 只产生结构化决策，平台 Runtime 执行配额、文件、构建和发布操作。
3. **状态先持久化再推送**：Run、Job 和事件先写 PostgreSQL，再通过 SSE 发送，断线后可重放。
4. **先完成纵向闭环**：V1 不为自主多 Agent、本地 Runtime 或任意代码执行提前引入分布式组件。

## 2. 架构结论

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

External: Provider Adapter -- HTTPS --> Ollama Cloud API
```

本版本不实现 Terminal CLI、本地 Agent Runtime、SQLite、本地工作区或 `localhost` Dev Server。这些能力尚未归属具体版本，不参与 V1 验收。

## 3. 已确认的架构决策

### 3.1 V1 必须实现

#### 3.1.1 Agent 与产物 Contract

- 真实 LLM 调用，不使用预设文本替代 Blueprint 或 AppSpec。
- 结构化 Blueprint 与 AppSpec，所有模型输出都必须经过 Pydantic 校验。

#### 3.1.2 受控构建与异步执行

- 固定 React 模板、固定依赖和固定构建命令。
- 构建脱离 HTTP 请求生命周期，通过持久化异步 Job 执行。

#### 3.1.3 状态、存储与配额

- PostgreSQL 持久化用户、项目、Session、Run、Job、版本、配额和附件元数据。
- Railway Volume 保存附件、项目工作区和构建产物。
- 同一用户拥有多个 Session，所有 Session 共享账户配额。

#### 3.1.4 用户审批与公开交付

- 用户确认 Blueprint 后才能创建 Build Job。
- React Visual Studio 通过 SSE 查看 LLM、构建和验证事件。
- 公开 Preview、显式 Publish、Update 与 Unpublish。

### 3.2 V1 明确不实现

#### 3.2.1 本地执行与数据同步

- Terminal CLI 或本地仓库执行。
- SQLite 与 PostgreSQL 同步。

#### 3.2.2 自由代码生成与执行沙箱

- `npm install`、动态依赖或模型生成的 Shell 命令。
- 任意技术栈、任意文件结构或任意后端生成。
- 公网多租户任意代码执行沙箱。

#### 3.2.3 Agent 与模型扩展

- 模型选择器。
- 真实多 Agent 自主委派与并行执行（由 V2 实现）。

#### 3.2.4 生成应用的业务后端

- 生成应用内部的数据库、认证、支付和订单系统。

#### 3.2.5 平台商业化能力

- Stripe 真实支付、Wallet、充值和发票。

## 4. 产品执行链路

```text
[1. 请求与资源准备]

用户提交 Prompt
    |
    v
校验用户身份
    |
    v
创建 Project + Session
    |
    v
预占 LLM 配额
    |
    v
[2. Blueprint 生成与审批]

Product Manager Agent -> Blueprint + support_level -> Pydantic 校验
    |                    |
    |                    `-- 校验失败 -> 有限重试 -> run.failed
    v
用户编辑 / 确认 Blueprint
    |
    v
[3. 设计与应用规格]

Architect Agent -> ArchitectureSpec -> Pydantic 校验
    |
    v
Engineer Agent -> AppSpec -> Pydantic 校验
    |
    v
[4. 异步构建]

创建 Build Job -> API 返回 202
    |
    v
Worker 获取 Job lease
    |
    v
Renderer -> 固定 React 模板 -> npm run build
    |
    +-- 构建失败 -> build.failed -> run.failed
    |
    v
[5. 校验与预览]

确定性校验 -> ValidationReport
    |
    v
Data Analyst Agent -> DataReview -> Preview 就绪
    |
    v
[6. 修改、版本与发布]

用户 Follow-up -> 新 AppSpec -> 新 Build Job -> 新 Version
    |
    v
用户显式发布选定 Version
    |
    v
公开 HTTPS URL
```

`publish` 不属于 Agent Loop。Agent Run 在生成通过校验的 Preview Version 后结束；发布是用户显式调用平台 API 的独立状态机。

## 5. 组件设计

### 5.1 React Visual Studio

技术：React、TypeScript、Vite。

职责：

- Prompt Composer 与附件选择。
- Blueprint 展示、编辑、确认和拒绝。
- 构建阶段、工具事件、错误和重试入口。
- iframe 应用预览及 Desktop/Mobile 尺寸切换。
- Follow-up 修改、版本选择、Restore 和 Resolve。
- Publish、Update 与 Unpublish。

Visual Studio 不直接访问 LLM、数据库、Volume 或工作区文件。

### 5.2 FastAPI Application Service

技术：FastAPI、Pydantic、SQLAlchemy、Alembic、Uvicorn。

职责：

- 平台用户身份与资源归属校验。
- Project、Session、Run、Attachment、Version 和 Deployment API。
- Plan、Quota Account 和 Usage Ledger。
- 启动 LLM Run 与创建 Build Job。
- 将持久化事件通过 SSE 推送给浏览器。
- 托管 Visual Studio 和生成应用的静态构建结果。

API 只负责创建异步任务和返回状态，不在请求协程中执行 `npm run build`。

### 5.3 Sequential Role Orchestrator

技术：httpx、Ollama Cloud API、Pydantic；Mock Provider 用于自动化测试。

本节只描述 Agent 与工程 Runtime 的集成摘要。执行范式、角色 Contract、Human-in-the-loop、Context、Tool、Sandbox、验收和有限修复以 [V1 Agent 设计](./agent-design.md)为事实来源。

V1 使用 Team Leader + 四个专业角色组成固定顺序 Pipeline。Team Leader 由确定性 Orchestrator 实现；四个专业阶段拥有独立 instruction 和结构化输出，但不具备自主编排能力。

```text
Team Mode

Product Manager Agent -> Blueprint -> user approval
    -> Architect Agent -> ArchitectureSpec
    -> Engineer Agent -> AppSpec
    -> Renderer / Build
    -> deterministic Validator
         |-- pass ----------------------------> Data Analyst Agent -> DataReview -> Preview Ready
         |-- resolvable failure, attempt < 1 -> Engineer Repair -> new AppSpec -> rebuild
         `-- non-resolvable / limit reached ---> run.failed -> Needs input

Engineer Mode

Engineer Agent -> Blueprint -> user approval -> AppSpec
    -> Renderer / Build -> deterministic Validator
         |-- pass ----------------------------> Preview Ready
         |-- resolvable failure, attempt < 1 -> Engineer Repair -> new AppSpec -> rebuild
         `-- non-resolvable / limit reached ---> run.failed -> Needs input
```

V1 角色 Pipeline 的约束：

- 顺序固定，不由模型动态决定下一角色。
- 不并行执行，不进行 Agent 间自由讨论。
- 阶段之间只传递经过 schema 校验的显式产物，不共享隐藏长期记忆。
- 每个阶段独立记录模型、用量、尝试次数、输入产物版本和输出产物。
- Engineer/Validator 负责代码与交互级确定性校验；DataReview 检查数据并解释证据，但不能覆盖 Build/Validation 结果。
- 自动修复只能由平台 Orchestrator 根据确定性失败结果触发，V1 最多执行 1 轮；Agent 不能自行开启无限返工。
- 动态委派、独立工具权限、并行执行、反馈循环和结果合并属于 V2 自主多 Agent。

#### 5.3.1 工程集成边界

- Agent Service 接收 Runtime 组装的阶段输入，完成 Provider 调用、Pydantic 校验、Artifact 持久化和 Usage/Trace 记录。
- Orchestrator 只根据持久化 Artifact、Approval、ValidationReport 和状态机推进，不读取模型私有推理。
- Renderer、Build Worker、Validator 和 Publish Service 是独立工程组件，不注册为 V1 Agent 可自行调用的 Tool。
- Agent 验收权、自动修复条件和失败收敛规则见 [V1 Agent 设计：Agent 错误、验收与有限修复](./agent-design.md#8-agent-错误验收与有限修复)。

LLM 只允许输出领域协议：

- `Blueprint`
- `ArchitectureSpec`
- `AppSpec`
- `RevisionSpec`
- `DataReview`

LLM 不直接拥有 Shell、文件系统或 Publish Tool。Provider Adapter 只负责模型调用和响应提取；Pydantic 校验、事件、重试、业务 Session、配额和状态由应用 Runtime 与数据库管理。

Product Manager 的 Blueprint 必须包含：

```text
support_level: supported | adapted | unsupported
supported_product_type: product_catalog
adaptation_summary: string[]
```

`unsupported` 不得进入 Architect 或 Build；`adapted` 必须等待用户确认映射结果。

### 5.4 阶段产物契约

前端可以展示 Team Leader、Product Manager、Architect、Engineer、Data Analyst，但每个阶段必须绑定可检查产物：

| 阶段名称 | 实际执行 | 必须产生的产物 |
| --- | --- | --- |
| Product Manager | Product Manager Agent 规范化需求并判断支持范围 | `Blueprint` |
| Team Leader | 确定性 Orchestrator 校验状态、配额和交接门 | `StageDecision` / 进度事件 |
| Architect | Architect Agent 生成路由、数据、视觉和交互约束 | `ArchitectureSpec` |
| Engineer | Engineer Agent 生成应用结构，Renderer/Validator 执行构建与代码级校验 | `AppSpec`、`BuildJob`、`ValidationReport` |
| Data Analyst | Data Analyst Agent 检查产品数据并解释不可变校验证据 | `DataReview` |

界面统一使用“Team Mode · 分阶段接力”或“Sequential role pipeline”。不得使用“并行协作”“团队自主讨论”等文案。

### 5.5 Deterministic Renderer

Renderer 是 V1 安全边界的核心：

- 只接受通过 schema 校验的 AppSpec。
- 只写入当前项目工作区。
- 只修改模板声明允许的配置、内容和资产文件。
- 依赖在 Docker 镜像构建阶段预装。
- 运行时禁止 `npm install` 和 `package.json` 依赖变更。
- 构建命令固定为平台配置，不接受模型提供的命令字符串。
- 同一个 AppSpec 必须产生语义一致的项目结构。

V1 的自然语言修改先生成新的 RevisionSpec/AppSpec，再由 Renderer 重新物化。模型不直接 patch 任意源码。

### 5.6 Build Job Runner

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

部署前必须在 Build 并发为 1 且构建实际发生时同时观测：Build 耗时、进程 RSS/CPU、API p95、SSE keepalive 间隔和 Job 排队时间，不能只测内存与单次构建耗时。

V1 同进程 Web + Worker 是刻意降低部署复杂度的基线，不是长期扩展方案。若构建期间 API/首事件响应不再满足验收基线、SSE keepalive 明显延迟或实例发生资源退出，必须先拆分 Worker，而不是提高同进程并发：

```text
Railway Web Service ------ PostgreSQL ------ Railway Build Worker Service
        |                                            |
        |                                            v
        `---------------- Artifact Store <------ build / dist
```

拆分后 Web 和 Worker 继续通过 PostgreSQL lease 协调 Job；工作区与 BuildArtifact 需要迁移到两服务都可访问的对象存储或明确的产物传输协议，不能假设两个 Service 共享同一个本地 Volume。

## 6. JavaScript 与 Python 通信

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

### 6.1 事件协议

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
build.queue_updated
build.started
build.cancelled
build.failed
validation.issue_detected
validation.completed
qa.degraded
preview.ready
run.failed
run.completed
run.completed_degraded
deployment.started
deployment.completed
deployment.failed
```

每条 SSE 消息使用数据库 `event_id` 作为原生 SSE `id`：

```text
id: evt_123
event: build.started
data: { ... }
```

事件先写入 `run_events`，再推送 SSE。浏览器断线重连时由 EventSource 发送 `Last-Event-ID`，服务端校验用户/Session/Run 归属后，从该游标之后补发；不能只依赖内存广播，也不能因重连重新触发 Agent 或 Build。

- 没有业务事件时，服务端默认每 15 秒发送 SSE comment keepalive；keepalive 不写入 `run_events`。
- V1 默认保留详细 `run_events` 30 天，保留天数通过配置管理；Run 终态、Artifact、Version 和错误摘要按 Project 生命周期保留。
- 清理任务只能删除超过窗口且所属 Run 已终止的详细事件，不删除运行中的游标范围。
- `Last-Event-ID` 已超出保留窗口时，服务端发送 `stream.reset`，前端先通过 Run/Build snapshot API 恢复当前状态，再从新游标继续。

## 7. 状态模型

### 7.1 Agent Run

```text
Created -> ProductRunning -> AwaitingApproval
             |                    |
             v                    v
           Failed          ArchitectRunning
                                    |
                                    v
                             EngineerRunning
                                    |
                                    v
                               BuildQueued
                                    |
                                    v
                                Building
                             |            |
                             v            v
                           Failed      Validating
                                      |          |
                                      v          v
                               Repairing/Failed DataRunning
                                                 |       |
                                                 v       v
                                          Completed  CompletedDegraded
```

### 7.2 Build Job

```text
Queued -> Leased -> Rendering -> Building -> Validating -> Succeeded
   ^         |           |           |            |
   |         +-----------+-----------+------------+--> Failed
   |
manual retry creates a new attempt
```

### 7.3 Publish

```text
Unpublished -> Publishing -> Live -> Updating -> Live
                    |                    |
                    v                    v
                  Failed               Failed

Live -> Unpublishing -> Unpublished
```

Build 成功不会自动发布。Publish 必须携带用户选择的 `version_id`。

公开访问与缓存约束：

- `public_id` 使用不可预测的随机标识，不暴露顺序 Project/Deployment ID；`/apps/{public_id}/*` 查不到或已 Unpublish 时统一返回 404。
- 发布快照不可变，Update 通过数据库事务切换 stable public route 指针，不原地覆盖旧快照。
- 公开入口 HTML 和发布元数据使用 `Cache-Control: no-store`；带 content hash 的静态资产可以使用 immutable cache。
- Unpublish 先原子更新 Deployment 状态并撤销路由，再异步清理快照；即使文件尚未删除，公开入口也不能继续命中。
- V1 不接 CDN。未来增加 CDN 时，Publish/Update/Unpublish 必须包含 purge/invalidation 结果，不能只修改数据库指针。
- Link Only 页面增加 `noindex`，但不可预测 ID 不能被描述为完整访问控制；带 token 和过期时间的访问控制属于未归属版本的后续候选。

## 8. 数据设计

### 8.1 存储分工

PostgreSQL：

- 用户、Plan、Subscription、Quota 和 Usage Ledger。
- Project、Session、AgentRun、AgentStageRun、Artifact、Approval、RunEvent、ProductEvent 和 BuildJob。
- Attachment 元数据、ProjectVersion 和 Deployment。

Railway Persistent Volume：

- 上传附件。
- 每个项目的受控工作区。
- 构建日志和 `dist` 产物。
- 发布版本的不可变静态快照。

### 8.2 核心关系

```text
User
  |---- n Project
  |         |---- n Attachment
  |         |---- n Artifact
  |         |---- n Approval
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

### 8.3 核心表

- `users`：平台用户身份和状态。
- `plans`：周期配额与功能边界。
- `subscriptions`：当前方案、有效期和状态；V1 可由种子数据或管理操作设置。
- `quota_accounts`：可用、预占和已结算额度。
- `usage_ledger`：每次预占、结算和释放记录。
- `projects`：项目名称、状态和当前版本。
- `sessions`：项目下可恢复的模型上下文。
- `agent_runs`：一次需求或修改对应的 LLM 运行。
- `agent_stage_runs`：Team Leader、Product Manager、Architect、Engineer、Data Analyst 各阶段的输入产物、输出产物、模型、用量、尝试次数和状态。
- `artifacts`：不可变 Blueprint、ArchitectureSpec、AppSpec、RevisionSpec、ValidationReport 和 DataReview。
- `approvals`：绑定精确 Artifact 版本与 hash 的 Human-in-the-loop 决策记录。
- `run_events`：可重放的 SSE 事件。
- `product_events`：用于价值漏斗的用户行为事件，与运行时 `run_events` 分离。
- `build_jobs`：异步构建状态、lease、attempt 和错误。
- `attachments`：附件元数据和 Volume 路径。
- `project_versions`：Blueprint、ArchitectureSpec、AppSpec、ValidationReport 和构建产物引用。
- `deployments`：公开 URL、所选版本和发布状态。

### 8.4 artifacts

建议字段：

```text
id
user_id
project_id
run_id
stage_run_id
artifact_type
schema_version
version
parent_artifact_id
content_json
content_hash
created_at
```

Artifact 创建后不可原地修改。修订必须创建新 Artifact，并通过 `parent_artifact_id` 保留来源关系；ProjectVersion 和 Approval 只保存 Artifact 引用。

### 8.5 approvals

建议字段：

```text
id
user_id
project_id
run_id
approval_type
artifact_id
artifact_version
artifact_hash
requested_by_stage
status
decided_by_user_id
created_at
decided_at
```

Approval 只对指定 Artifact hash 有效。Artifact 发生修订后，旧 pending/approved 记录不能用于推进新版本；服务重启后从持久化 pending 状态恢复。

### 8.6 attachments

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

### 8.7 build_jobs

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

### 8.8 product_events

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

### 8.9 Export JSON

Export 由应用服务从已持久化 Contract 组装，不读取工作区源码。最小字段以 PRD 为准，包括 `schema_version`、`exported_at`、`project`、`blueprint`、`architecture_spec`、`app_spec`、`current_version`、`versions`、`publication` 和附件公开元数据。

必须排除 LLM Key、用户凭证、Volume 绝对路径、原始对话和 Usage Ledger。

## 9. 配额与订阅

V1 的 Plan 与配额是真实平台能力，但支付不是。

```text
Plan -> Subscription -> Quota Account -> Usage Ledger
```

每个角色阶段及其结构化输出重试都作为独立模型请求计量：

```text
verify user and session
    -> reserve estimated quota in a database transaction
    -> call LLM
    -> read actual Provider request count and token usage
    -> settle actual usage
    -> release unused reservation
```

调用失败也必须记录实际发生的 Provider 请求并释放未使用预占。计费单位为 Provider 请求次数，输入/输出 token 作为审计字段保存。不能在模型返回后才检查配额，否则同一账户的并发 Session 可以透支。

V1 不接 Stripe。未来 Stripe Webhook 只更新 Subscription，不直接修改 Session 或历史 Ledger。

## 10. 工程错误与恢复

Agent Provider、结构化输出、Stage retry、Validation repair 和 Rework 的语义归 [V1 Agent 设计](./agent-design.md)管理。本章只定义 Build Worker、持久化、事件和发布基础设施如何失败与恢复。

### 10.1 Build 执行错误

- 编译、资源或超时错误先写入 `build.failed`，随后将聚合 Run 标记为 Failed，错误阶段为 BUILD。
- 固定输入导致的编译失败不自动重复执行，因为相同输入不会产生不同结果。
- Worker 被终止或 lease 过期时允许自动重新领取一次；这属于执行恢复，不是构建逻辑重试。
- 用户点击 Retry 后创建新的 attempt，并保留原日志。
- 错误码至少区分 `RENDER_FAILED`、`BUILD_FAILED`、`BUILD_TIMEOUT`、`RESOURCE_LIMIT`。

### 10.2 持久化与事件恢复

- 创建 Run、StageRun、Artifact、Approval、BuildJob 和 Event 的状态迁移必须使用数据库事务；事务失败不能发送成功事件。
- SSE 断线不改变 Run 状态；客户端按 `event_id` 重连并补取持久化事件，不重新触发 Agent 或 Build。
- Worker 只能领取 queued 或 lease 已过期的 Job；V1 通过审批行锁与 `build_jobs.run_id` 唯一约束防止同一 Run 创建重复执行。
- PostgreSQL 元数据与 Volume 产物不一致时，状态进入 Failed/Needs input，不允许 Agent 猜测或重新生成路径。
- Publish/Update 失败保留上一个 Live Version，不能让稳定公开 URL 指向不完整产物。

### 10.3 错误归属边界

| 错误类型 | 事实来源 | 处理所有者 |
| --- | --- | --- |
| Provider、Prompt、Pydantic 输出 | Agent StageRun / Provider response | Agent Runtime，见 V1 Agent 设计 |
| AppSpec 可修复校验问题 | ValidationReport | Agent Orchestrator，见 V1 Agent 设计 |
| Renderer、编译、超时、资源 | Build Worker / process exit | 工程 Runtime |
| Worker 中断、lease 过期 | PostgreSQL lease | Build Worker 恢复逻辑 |
| 数据库、Volume、SSE、Publish | 服务与存储状态 | API/Storage/Publish Service |

Agent 只能消费工程 Runtime 产生的错误证据，不能修改错误码、伪造成功事件或决定基础设施重试。

## 11. 安全边界

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

## 12. Railway 部署

```text
GitHub 仓库
     |
     | push 自动部署
     v
┌──────────────── Railway ────────────────┐
│                                        │
│  Docker Web Service                    │
│  · Python / FastAPI                    │
│  · Ollama Cloud / Mock Provider        │
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
              Ollama Cloud
```

### 12.1 Docker

镜像构建阶段：

1. 安装固定 Node.js 依赖并构建 React Studio。
2. 安装 Python API、Agent 和数据库依赖。
3. 复制固定应用模板和 Renderer。
4. 不在运行时执行依赖安装。

依赖锁定与升级：

- Node 模板和 Studio 提交 lockfile，镜像构建使用 lockfile 的冻结安装模式；lockfile 与声明不一致时构建失败。
- Python 运行依赖同样锁定精确版本，镜像不能在构建时解析浮动最新版本。
- 模板依赖升级使用独立变更：更新 lockfile -> 安全检查 -> Golden Path 构建/交互回归 -> 镜像压测 -> 合并。
- 常规依赖更新在计划窗口执行；高危漏洞可以进入紧急升级，但同样不能跳过构建与 Golden Path 回归。
- ProjectVersion 记录 `template_version`，旧版本恢复仍能定位其对应模板，不能静默改用不兼容的新模板。

启动阶段：

1. 执行 Alembic migration。
2. 启动单实例 FastAPI 和持久化 Build Worker。
3. Worker 从 PostgreSQL 领取 Build Job。

### 12.2 PostgreSQL 与 Volume

Railway PostgreSQL 是独立、按资源计费的非托管服务，不是免费附赠数据库。V1 需要配置备份并验证恢复流程。

Volume 保存工作区和构建产物，但不能替代 PostgreSQL 元数据。服务重启或重新部署后，数据库与 Volume 中的必要状态必须保持一致。

V1 明确采用**单 Web Service 实例 + 单 Volume**，不承诺水平扩展。Volume 中的工作区是短期构建状态，发布快照是读多写少的不可变交付物；两者必须通过 Artifact Contract 区分，不能只保存绝对文件路径。

扩展路径：

1. 优先把发布快照和带 hash 的静态资产迁移到 S3-compatible Object Storage。
2. Worker 拆分后，再把 BuildArtifact/工作区交换迁移到对象存储或受控产物传输。
3. PostgreSQL 继续保存 Artifact 元数据、hash、对象 key 和发布指针。
4. 完成迁移前不得增加 Web/Worker 水平副本并假设 Volume 可共享。

### 12.3 GitHub

GitHub 负责源代码、文档、版本历史和触发 Railway 自动部署。GitHub Pages 只能托管静态内容，不能单独运行 FastAPI、Agent、PostgreSQL 或 Build Worker。

## 13. 代码组织

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

## 14. V1 实施顺序

1. 定义 Blueprint、ArchitectureSpec、AppSpec、DataReview、Event、Export 和 Error Contract。
2. 建立 PostgreSQL、Alembic 与用户/Project/Session 基础模型。
3. 实现 Plan、配额预占和 Usage Ledger。
4. 实现 Team Leader、Product Manager、Architect、Engineer、Data Analyst 固定顺序 Orchestrator、阶段持久化和配额结算。
5. 完成 AppSpec 与固定 React Renderer。
6. 实现 `build_jobs`、单并发 Worker 和持久化事件。
7. 实现 Visual Studio 的 Blueprint、SSE 和 iframe Preview。
8. 实现附件、ProductEvent 漏斗、Export JSON、一次 Follow-up 修改和 ProjectVersion。
9. 实现 Resolve、Restore 和显式 Publish。
10. Docker 化并部署 Railway Web Service、PostgreSQL 和 Volume。
11. 在目标 Railway 规格完成构建期 API p95、SSE keepalive、队列等待、CPU/RSS、构建耗时和重启恢复压测。

## 15. V1 验收

- 用户能从 Cloud Visual Studio 输入需求并获得真实 LLM 生成的 Blueprint。
- Team Mode 按 Team Leader、Product Manager、Architect、Engineer、Data Analyst 固定顺序执行，每个阶段都有独立 AgentStageRun 和可检查产物。
- UI 明确标注“分阶段接力”，不声称并行或自主多 Agent。
- 非商品目录输入必须进入 supported、adapted 或 unsupported；unsupported 不创建 Build Job。
- 未确认 Blueprint 时不会创建 Build Job。
- AppSpec 不能改变依赖、构建命令或工作区边界。
- HTTP 创建构建后立即返回，构建由异步 Worker 完成。
- 同一实例的构建并发不超过配置上限，初始为 1。
- 构建运行期间，异步创建/查询 API p95 仍满足 1 秒返回基线，首条用户可见事件在 2 秒内到达，SSE keepalive 间隔不超过配置值。
- 压测报告记录队列等待、CPU、RSS 和构建耗时；若单进程方案不满足基线，部署必须改为独立 Worker Service。
- 用户可以恢复两个不同 Session，且上下文不会串线。
- 并发模型调用不能绕过同一账户配额。
- 附件元数据与 Volume 文件状态一致。
- Build Error 与预设 Resolve 问题使用不同事件和状态。
- 用户明确选择版本后才能 Publish。
- Railway 重启后 queued Job、项目、版本和发布结果可以恢复。
- SSE 使用 `Last-Event-ID` 补取；游标过期时通过 snapshot resync 恢复，不重复执行 Run。
- Unpublish 后原公开入口返回 404，Specify/Latest 指针与缓存策略不会继续暴露旧入口。
- 部署后获得可公开测试的 HTTPS 地址。
- Golden Path 连续 5 次完成，产品漏斗事件完整率为 100%，跨 Session 串事件为 0。
- Export JSON 满足最小 Contract，且不包含密钥、凭证、绝对路径、原始对话和内部用量流水。

## 16. 未归属版本：CC 式本地执行

该独立方向是类似 Claude Code 的本地 Agent Runtime，当前不占用 V1 或 V2 的版本定义：

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

后续实现必须重新设计：

- Python/Node 安装与跨平台打包。
- 本地权限审批和工作区信任模型。
- 本地进程、端口和 Dev Server 生命周期。
- SQLite 项目如何上传、同步或发布到云端。
- 本地项目与 Cloud Project 的冲突处理。

在这些协议确定前，V1 README 和产品界面不得声称已经支持本地仓库执行。
