# Another Atom V1 架构设计

[toc]

- 文档状态：V1 实施基线
- 更新日期：2026-07-11
- 产品文档：[Another Atom V1 产品需求文档](./another-atom-v1-prd.md)
- Agent 设计：[Another Atom V1 Agent 设计](./agent-design.md)
- 参考分析：[Atoms 参考产品功能分析](../reference/atoms-reference-analysis.md)

## 1. 技术选型

V1 采用 Cloud 产品形态，但把控制面与执行面分开：React 提供可视化工作台，FastAPI 承担 API、Agent 编排和领域服务，PostgreSQL 保存业务事实，Linux Sandbox Host 承担本地 Git、Vim PTY 和受控构建。Control Plane 可通过 Docker 部署到 Railway，也可与 Sandbox Host 一起部署到同一台 Linux VM。

| 层次 | V1 选型 | 选择原因 | V1 边界 |
| --- | --- | --- | --- |
| 前端工作台 | React + TypeScript + Vite + xterm.js | 适合实现状态密集的 Studio、类型化 API、iframe Preview 和受限 Vim 终端 | 不直接访问 LLM、数据库或 Volume；xterm.js 只连接经过授权的 Editor Session |
| API 与领域服务 | Python + FastAPI + Pydantic + Uvicorn | 与 Agent/结构化输出保持同一语言栈；Pydantic 同时约束 API 和模型产物 | HTTP 请求只创建任务，不同步执行构建 |
| 身份认证 | 用户名/密码 + Argon2id 哈希 + 服务端 Session Cookie | V1 需要两个真实账号切换并验证 Project 隔离；服务端 Session 比可伪造用户头更适合作为归属事实 | V1 租户粒度为 User，不实现 Organization/Membership |
| Agent 编排 | 自有 Orchestrator + Provider Adapter（Ollama Cloud / Mock）+ Pydantic | 支持按 Run 选择模型、角色 instruction、有界重试和结构化校验 | Ollama Cloud 不提供服务端 Structured Outputs，Schema 由本地严格校验 |
| 前后端通信 | REST + SSE + WebSocket + OpenAPI | REST 承担命令，SSE 推送事件，WebSocket 只承载终端字节流，OpenAPI 同步业务类型 | WebSocket 不承载 Agent 状态或任意 RPC |
| 业务数据库 | PostgreSQL + SQLAlchemy + Alembic | 支持多用户、Session、配额事务、Job lease、版本和发布状态 | 不使用 SQLite，也不设计本地/云端双向同步 |
| 项目源码与构建 | 服务端本地 Git + Sandbox Host Persistent Disk + Node.js/npm + Deterministic Renderer | 一 Project 一仓库；Git commit 将 ProjectVersion 与可恢复源码对应；固定依赖和命令控制风险 | V1 不配置 Git remote，不执行 push，不接受模型生成的 Shell 命令 |
| 代码终端 | xterm.js + WebSocket + 隔离 PTY + 固定 Vim | 给用户真实键盘编辑体验，同时把修改限制在当前 Project 仓库 | 不启动登录 Shell；禁用 shell escape、插件、网络和仓库外路径 |
| 异步执行 | Sandbox Host 上的单并发持久化 Build Worker | V1 无需额外消息队列即可脱离 HTTP 生命周期，并通过 PostgreSQL lease 恢复 | 提高并发前必须在目标 Host 规格压测 |
| 部署 | Control Plane + PostgreSQL + Linux Sandbox Host | Control Plane 处理 Web/API/Agent；执行宿主机保存 Git 并提供 rootless Editor/Build Sandbox | Railway 可承载 Control Plane，但真实 WebIDE 必须有支持 namespace/cgroup 的 Linux Host |

### 1.1 选型原则

1. **Contract 优先**：Blueprint、ArchitectureSpec、AppSpec、Event、Error 和 Export 以 Pydantic 模型为事实来源。
2. **模型与权限分离**：LLM 只产生结构化决策，平台 Runtime 执行配额、文件、Git、构建和发布操作。
3. **状态先持久化再推送**：Run、Job 和事件先写 PostgreSQL，再通过 SSE 发送，断线后可重放。
4. **身份与归属先于资源读取**：Project、Repository、Version、Terminal 和 Job 都从服务端 Session 取得当前 User，不能信任客户端传入用户 ID。
5. **先完成纵向闭环**：V1 的 Lead 只做直接回答或固定团队二选一路由，不为 V2 动态 TaskGraph、并行或仲裁提前引入分布式组件。

## 2. 架构结论

Another Atom V1 只交付 Cloud 形态：Control Plane 可部署在 Railway，代码编辑与构建执行面部署在受控 Linux Sandbox Host；也可以通过 Docker Compose 部署到同一台 Linux VM。两种方式必须提供相同的 Auth、Repository、Sandbox 和公开 URL Contract。

用户使用用户名密码登录 React Visual Studio。Lead Agent 对每条消息只做二选一：直接回答/澄清，或启动 Product Manager → Architect → Engineer → Data Analyst 固定团队。构建产物写入 Project 绑定的服务端本地 Git 仓库；用户既可通过结构化编辑，也可通过 xterm.js 中的受限 Vim 修改源码。保存版本时平台统一校验、构建、提交 Git commit，并将 ProjectVersion 映射到 commit SHA。

```text
┌──────────────────────────── 用户交互层 ────────────────────────────┐
│                                                                  │
│                     React Visual Studio                          │
│  登录 / Lead 对话 / 风险确认 / 构建事件 / Preview / xterm+Vim    │
│                              │                                   │
└──────────────────────────────│───────────────────────────────────┘
                               │ REST + SSE + WSS
                               │ OpenAPI 类型同步
                               ▼
┌──────────────────────── Control Plane ───────────────────────────┐
│                                                                 │
│  FastAPI                                                        │
│     │                                                           │
│     ├── Auth / Project / Repository / Version / Publish         │
│     │                                                           │
│     ├── Lead Router + Sequential Team Orchestrator              │
│     │      Message → answer | clarify | fixed team              │
│     │                         │                                  │
│     │                         ▼                                  │
│     └── Build Job / Editor Session Queue                         │
└──────────────────────┬───────────────────────┬───────────────────┘
                       │                       │
                       ▼                       ▼
                PostgreSQL              Linux Sandbox Host
        用户/AuthSession/配额/Job/版本   local Git / Vim / Build / dist

External: Provider Adapter -- HTTPS --> Ollama Cloud API
```

V1 的 xterm.js 终端只提供当前 Project 仓库中的受限 Vim，不是 Terminal CLI 或 CC 式本地 Agent Runtime。V1 不实现用户电脑上的本地工作区、SQLite 同步、登录 Shell 或 `localhost` Dev Server。

## 3. 已确认的架构决策

### 3.1 V1 必须实现

#### 3.1.1 Agent 与产物 Contract

- 真实 LLM 调用，不使用预设文本替代 Blueprint 或 AppSpec。
- 结构化 Blueprint 与 AppSpec，所有模型输出都必须经过 Pydantic 校验。

#### 3.1.2 受控构建与异步执行

- 固定 React 模板、固定依赖和固定构建命令。
- 构建脱离 HTTP 请求生命周期，通过持久化异步 Job 执行。

#### 3.1.3 身份、租户、状态与配额

- 平台使用用户名和密码登录；密码只保存强哈希，浏览器使用服务端 Session Cookie，不信任客户端提交的 `X-User-ID`。
- V1 的租户边界是单个 User，不实现 Organization/Workspace；所有 Project、Session、Run、Version、Repository 和配额查询必须绑定当前登录用户。
- 用户通过退出当前账号并登录另一个账号完成切换；切换后只能看到新账号所属项目，公开发布页除外。
- PostgreSQL 持久化用户、项目、Session、Run、Job、版本、配额和附件元数据。
- Sandbox Host 持久化磁盘保存附件、Project Git 仓库和构建产物。
- 同一用户拥有多个 Session，所有 Session 共享账户配额。

#### 3.1.4 Project 与本地 Git 仓库

- 每个 Project 默认绑定一个平台服务端本地 Git 仓库，关系为一对一。
- 仓库保存在 Sandbox Host Persistent Disk 的服务端受控目录，不代表用户电脑上的本地仓库，也不连接 GitHub/GitLab remote。
- Build、Edit、Resolve 和 Restore 生成 ProjectVersion 时必须创建对应 Git commit，并把 commit SHA 写回版本记录。
- Git 初始化、文件写入、提交和恢复由平台 Repository Service 执行固定命令；Agent 不获得任意 Git/Shell 权限。

#### 3.1.5 风险确认与公开交付

- 用户明确请求构建且 Blueprint 为 supported 时可直接进入固定团队；adapted、额外预算、范围变化、破坏性仓库操作和线上变更必须通过 Risk Policy 确认。
- React Visual Studio 通过 SSE 查看 LLM、构建和验证事件。
- 公开 Preview、显式 Publish、Update 与 Unpublish。

### 3.2 V1 明确不实现

#### 3.2.1 本地执行与数据同步

- Terminal CLI、用户电脑上的本地仓库执行或 CC 式本地 Agent Runtime。
- SQLite 与 PostgreSQL 同步。

Sandbox Host Persistent Disk 内的 Project Git 仓库属于 V1 平台存储，不属于本节排除的用户本地执行。

#### 3.2.2 自由代码生成与执行沙箱

- `npm install`、动态依赖或模型生成的 Shell 命令。
- 任意技术栈、任意文件结构或任意后端生成。
- 公网多租户任意代码执行沙箱。

#### 3.2.3 Agent 与模型扩展

- 任意 Provider 或不受限的模型标识；V1 只允许从平台配置的 DeepSeek allowlist 中按 Run 选择模型。
- 真实多 Agent 自主委派与并行执行（由 V2 实现）。

#### 3.2.4 生成应用的业务后端

- 生成应用内部的数据库、认证、支付和订单系统。

#### 3.2.5 平台商业化能力

- Stripe 真实支付、Wallet、充值和发票。

## 4. 产品执行链路

```text
[1. 登录与请求路由]

用户名 + 密码
    |
    v
校验密码哈希 -> 创建 AuthSession Cookie
    |
    v
用户消息 -> Lead Agent -> LeadDecision
                    |
                    +-- answer / clarify -> 对话回复，流程结束
                    |
                    `-- team -> 创建 Project + ProjectRepository + Session
    |
    v
[2. 固定团队与必要确认]

Product Manager Agent -> Blueprint + support_level -> Pydantic 校验
    |                    |
    |                    `-- 校验失败 -> 有限重试 -> run.failed
    v
supported + 明确构建意图 -> 继续
adapted / 范围变化 / 超预算 -> approval.required -> 用户决定
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
Renderer -> Project 本地 Git worktree -> npm run build
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

用户结构化编辑或 xterm+Vim -> dirty worktree -> Save Version
    |
    v
校验 + Build -> Git commit -> ProjectVersion(commit_sha)
    |
    v
用户显式发布选定 Version
    |
    v
公开 HTTPS URL
```

`publish` 不属于 Agent Loop。Lead 不能自动发布。普通受支持构建、预览、追加 Git commit 不需要额外审批；`adapted` 范围、额外预算、删除、Restore、Publish/Update/Unpublish 等高影响动作按风险策略插入确认。

## 5. 组件设计

### 5.1 React Visual Studio

技术：React、TypeScript、Vite。

职责：

- Prompt Composer 与附件选择。
- 用户名密码登录、退出和账号切换。
- Lead 单一对话入口，以及“直接回答 / 调用团队”的可见路由结果和用户覆盖入口。
- Blueprint 展示、编辑；只有命中风险策略时显示内联 Approval。
- 构建阶段、工具事件、错误和重试入口。
- iframe 应用预览及 Desktop/Mobile 尺寸切换。
- Follow-up 修改、版本选择、Restore 和 Resolve。
- xterm.js 受限 Vim 编辑器、dirty 状态和 Save Version。
- Publish、Update 与 Unpublish。

Visual Studio 不直接访问 LLM、数据库、Volume 或工作区文件。

### 5.2 FastAPI Application Service

技术：FastAPI、Pydantic、SQLAlchemy、Alembic、Uvicorn。

职责：

- 平台用户身份与资源归属校验。
- AuthSession、Project、ProjectRepository、Session、Run、Attachment、Version 和 Deployment API。
- Plan、Quota Account 和 Usage Ledger。
- 启动 LLM Run 与创建 Build Job。
- 将持久化事件通过 SSE 推送给浏览器。
- 托管 Visual Studio 和生成应用的静态构建结果。

### 5.2.1 Auth 与用户级租户边界

- `POST /auth/register` 创建唯一 username，并使用 Argon2id 保存 `password_hash`。
- `POST /auth/login` 校验凭证，创建只在服务端可解析的随机 Session；Cookie 设置 `HttpOnly`、`Secure`、`SameSite=Lax` 和过期时间。
- `POST /auth/logout` 撤销当前 Session。切换用户等价于 logout 后 login，不允许在请求里直接指定 `user_id`。
- V1 的 tenant 等于 User；所有 owner 查询从 AuthSession 取得 `user_id`。测试环境可以保留显式依赖覆盖，但生产路由不接受 `X-User-ID` 作为身份。
- 登录、失败登录、退出和越权拒绝写入安全审计事件；日志不记录密码、Session token 或完整 Cookie。

API 只负责创建异步任务和返回状态，不在请求协程中执行 `npm run build`。

### 5.3 Lead Router 与 Sequential Team Orchestrator

技术：httpx、Ollama Cloud API、Pydantic；Mock Provider 用于自动化测试。

本节只描述 Agent 与工程 Runtime 的集成摘要。执行范式、角色 Contract、Human-in-the-loop、Context、Tool、Sandbox、验收和有限修复以 [V1 Agent 设计](./agent-design.md)为事实来源。

V1 使用一个独立 Lead Agent 和四个专业角色。Lead 只生成 `LeadDecision(route=direct|team)`：direct 负责回答或澄清，team 启动固定顺序 Pipeline。Runtime 校验路由、风险与预算；Lead 不能自由挑角色、并行、返工仲裁或发布。

```text
Lead route=team

Product Manager Agent -> Blueprint
    -> Risk Policy (only adapted/high-risk requires approval)
    -> Architect Agent -> ArchitectureSpec
    -> Engineer Agent -> AppSpec
    -> Renderer / Build
    -> deterministic Validator
         |-- pass ----------------------------> Data Analyst Agent -> DataReview -> Preview Ready
         |-- resolvable failure, attempt < 1 -> Engineer Repair -> new AppSpec -> rebuild
         `-- non-resolvable / limit reached ---> run.failed -> Needs input

Lead route=direct

Lead Agent -> direct answer or clarification -> no Team Run / no repository mutation
```

V1 路由与团队约束：

- Lead 只能 direct/team 二选一；用户可以显式覆盖为“调用团队”。
- team 内顺序固定，不由模型动态决定下一角色。
- 不并行执行，不进行 Agent 间自由讨论。
- 阶段之间只传递经过 schema 校验的显式产物，不共享隐藏长期记忆。
- 每个阶段独立记录模型、用量、尝试次数、输入产物版本和输出产物。
- Engineer/Validator 负责代码与交互级确定性校验；DataReview 检查数据并解释证据，但不能覆盖 Build/Validation 结果。
- 自动修复只能由平台 Orchestrator 根据确定性失败结果触发，V1 最多执行 1 轮；Agent 不能自行开启无限返工。
- 动态角色子集、TaskGraph、独立工具权限、并行执行、反馈循环和仲裁属于 V2 自主多 Agent。

#### 5.3.1 工程集成边界

- Agent Service 接收 Runtime 组装的阶段输入，完成 Provider 调用、Pydantic 校验、Artifact 持久化和 Usage/Trace 记录。
- Orchestrator 只根据持久化 Artifact、Approval、ValidationReport 和状态机推进，不读取模型私有推理。
- Renderer、Build Worker、Validator 和 Publish Service 是独立工程组件，不注册为 V1 Agent 可自行调用的 Tool。
- Agent 验收权、自动修复条件和失败收敛规则见 [V1 Agent 设计：Agent 错误、验收与有限修复](./agent-design.md#8-agent-错误验收与有限修复)。

LLM 只允许输出领域协议：

- `LeadDecision`
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

前端默认只展示 Lead 对话与当前结果；用户展开团队过程时，每个阶段必须绑定可检查产物：

| 阶段名称 | 实际执行 | 必须产生的产物 |
| --- | --- | --- |
| Lead | Lead Agent 判断直接回答还是调用完整团队 | `LeadDecision`、直接回复或团队摘要 |
| Product Manager | Product Manager Agent 规范化需求并判断支持范围 | `Blueprint` |
| Architect | Architect Agent 生成路由、数据、视觉和交互约束 | `ArchitectureSpec` |
| Engineer | Engineer Agent 生成应用结构，Renderer/Validator 执行构建与代码级校验 | `AppSpec`、`BuildJob`、`ValidationReport` |
| Data Analyst | Data Analyst Agent 检查产品数据并解释不可变校验证据 | `DataReview` |

团队展开视图统一使用“固定团队 · 分阶段接力”或“Sequential team pipeline”。不得使用“并行协作”“团队自主讨论”等文案。

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

V1 使用 Sandbox Host 上的持久化后台 Worker：

- `MAX_CONCURRENT_BUILDS=1` 作为初始值。
- 使用 PostgreSQL lease 防止同一 Job 重复执行。
- 服务重启后重新领取 queued 或 lease 过期的 Job。
- 使用异步子进程执行固定构建命令。
- 每个 Job 设置可配置超时、输出上限和工作区磁盘上限。
- 禁止启用多个 Uvicorn Worker 后各自无协调地消费任务。

部署前必须在 Build 并发为 1 且构建实际发生时同时观测：Build 耗时、进程 RSS/CPU、API p95、SSE keepalive 间隔和 Job 排队时间，不能只测内存与单次构建耗时。

Control Plane 与 Sandbox Host 分离后，API 不与 Vim/Build 竞争同一进程资源。若 Worker 继续扩展，仍通过 PostgreSQL lease 或明确 Job 协议协调：

```text
Control Plane ------ PostgreSQL ------ Sandbox Host Worker
        |                                     |
        |                                     v
        `---------- Artifact metadata <--- local Git / build / dist
```

Control Plane 和 Worker 通过 PostgreSQL lease 协调 Job；源码事实保存在 Sandbox Host 的 Project Git，发布 Artifact 使用 storage key/hash 引用，不能假设 Control Plane 可以直接读取执行宿主机绝对路径。

### 5.7 Repository Service

Repository Service 是 Project 与源码历史的可信所有者：

1. 创建 Project 时同步创建唯一 `ProjectRepository(status=provisioning)`。
2. 在受控 repo root 下执行固定 `git init --bare`，写入平台生成的初始模板并创建初始化 commit，随后标记 ready。
3. Build/Edit/Resolve/Restore 都从指定 base commit 导出临时 worktree；通过校验后由 Repository Service 收集 allowlist 文件并提交。
4. `ProjectVersion.git_commit_sha` 必须指向该 Project 仓库中的 commit；数据库 Version 和 Git commit 在同一业务操作中成功或进入可恢复失败状态。
5. V1 不配置 remote、credential helper 或 hook，不支持 clone 用户仓库、push GitHub、force push 或改写历史。

推荐受控目录：

```text
/srv/another-atom/
├── repos/{user_id}/{project_id}.git          trusted bare repo
├── sessions/{editor_session_id}/worktree     ephemeral, no .git
└── artifacts/{project_id}/{version_id}/      build/publish snapshot
```

路径全部由服务端根据 AuthSession 与 Project ID 生成，API 不接收绝对路径。每个 Project 同时最多一个写 lease；base commit 不匹配时保存返回冲突，不覆盖另一会话修改。

### 5.8 Terminal Service 与 Sandbox Manager

```text
xterm.js
   |
   | WSS + one-time editor token
   v
Terminal Gateway -> owner/session check -> PTY proxy
                                         |
                                         v
                                Editor Sandbox
                                fixed command: Vim
```

- `POST /projects/{id}/editor-sessions` 校验登录用户、Project owner、Repository ready 和写 lease，返回短时一次性 WebSocket token。
- WebSocket 只转发 PTY input/output、resize 和 heartbeat，不传递任意 RPC；断线后 token 失效。
- Sandbox Manager 在独立 Linux 执行宿主机上启动 rootless 容器：非 root、只读根文件系统、禁网、drop capabilities、seccomp、`no-new-privileges`、资源/时限上限。
- Sandbox 只挂载没有 `.git` 的临时 worktree，固定启动受限 Vim；不提供登录 Shell、Docker socket、Secret、平台数据库或其他用户目录。
- `:write` 只改变临时 worktree。保存版本必须通过 Repository Service，随后进入 Build Sandbox 完成固定构建和验证。
- 仅靠目录前缀、`chroot` 或 Vim restricted mode 不构成隔离；目标宿主机无法提供容器/namespace 隔离时，真实终端功能必须关闭。

## 6. JavaScript 与 Python 通信

V1 使用 **REST + SSE + OpenAPI** 处理业务状态；仅 Terminal 使用 WebSocket。

```text
React Studio ---- REST ----> FastAPI
React Studio <---- SSE ----- Run / Build / Validation Events
React Studio ---- iframe --> Generated Preview
React xterm.js <-- WSS -----> Terminal Gateway / Sandbox PTY
```

核心 API：

```text
POST /api/projects
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
POST /api/projects/{project_id}/attachments
POST /api/sessions
GET  /api/sessions/{session_id}
POST /api/sessions/{session_id}/messages
GET  /api/sessions/{session_id}/events
POST /api/runs/{run_id}/approve
POST /api/runs/{run_id}/cancel
POST /api/builds/{build_id}/retry
POST /api/projects/{project_id}/editor-sessions
POST /api/editor-sessions/{session_id}/save-version
WS   /api/editor-sessions/{session_id}/terminal
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

- 用户、AuthSession、安全审计、Plan、Subscription、Quota 和 Usage Ledger。
- Project、Session、AgentRun、AgentStageRun、Artifact、Approval、RunEvent、ProductEvent 和 BuildJob。
- ProjectRepository、EditorSession、Attachment 元数据、ProjectVersion 和 Deployment。

Sandbox Host 持久化磁盘：

- 上传附件。
- 每个 Project 的可信本地 Git bare repository。
- Editor/Build Sandbox 的临时 worktree。
- 构建日志和 `dist` 产物。
- 发布版本的不可变静态快照。

### 8.2 核心关系

```text
User
  |---- n AuthSession
  |---- n Project
  |         |---- 1 ProjectRepository ---- n EditorSession
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

- `users`：唯一 username、password hash、平台用户状态；不保存明文密码。
- `auth_sessions`：哈希后的随机 Session token、user、过期时间、撤销时间和最近活动；浏览器只持有 Cookie。
- `security_events`：登录成功/失败、退出、越权拒绝和敏感操作审计。
- `plans`：周期配额与功能边界。
- `subscriptions`：当前方案、有效期和状态；V1 可由种子数据或管理操作设置。
- `quota_accounts`：可用、预占和已结算额度。
- `usage_ledger`：每次预占、结算和释放记录。
- `projects`：项目名称、owner user、状态和当前版本。
- `project_repositories`：Project 一对一本地 Git 仓库状态、默认分支、当前 commit 和受控 storage key。
- `editor_sessions`：xterm/Vim 会话、owner、base commit、worktree key、写 lease、状态和过期时间。
- `sessions`：项目下可恢复的模型上下文。
- `agent_runs`：一次需求或修改对应的 LLM 运行。
- `agent_stage_runs`：Lead、Product Manager、Architect、Engineer、Data Analyst 各阶段的输入产物、输出产物、模型、用量、尝试次数和状态。
- `artifacts`：不可变 Blueprint、ArchitectureSpec、AppSpec、RevisionSpec、ValidationReport 和 DataReview。
- `approvals`：绑定精确 Artifact 版本与 hash 的 Human-in-the-loop 决策记录。
- `run_events`：可重放的 SSE 事件。
- `product_events`：用于价值漏斗的用户行为事件，与运行时 `run_events` 分离。
- `build_jobs`：异步构建状态、lease、attempt 和错误。
- `attachments`：附件元数据和 Volume 路径。
- `project_versions`：Blueprint、ArchitectureSpec、AppSpec、ValidationReport、构建产物引用和对应 `git_commit_sha`。
- `deployments`：公开 URL、所选版本和发布状态。

#### 8.3.1 身份与用户级租户字段

```text
users: id, username(unique), password_hash, status, created_at
auth_sessions: id, user_id, token_hash(unique), expires_at, revoked_at, last_seen_at
security_events: id, user_id?, event_type, outcome, request_id, created_at
```

所有业务查询从 AuthSession 得到当前 `user_id`。生产 API 不接受客户端指定 owner；Project、Repository、EditorSession、Version、Attachment、Run 和 Job 必须通过 owner join 或统一 Repository 层查询。V1 是 user-level tenancy，不在字段中伪装尚未实现的 org/team。

#### 8.3.2 ProjectRepository 与 ProjectVersion

```text
project_repositories:
  id, project_id(unique), user_id, provider=local_git
  default_branch, status, storage_key
  head_commit_sha, write_lease_owner, write_lease_expires_at
  created_at, updated_at

project_versions:
  ...
  git_commit_sha
  base_commit_sha
  repository_id
```

数据库不保存宿主机绝对路径，只保存由 Repository Service 解析的 `storage_key`。Git commit 成功但数据库事务失败时，通过 operation id 和 commit trailer 幂等补写；数据库成功但 commit 缺失时 Version 进入 failed，不允许发布。

#### 8.3.3 EditorSession

```text
id, user_id, project_id, repository_id
base_commit_sha, worktree_key, mode=read_write|read_only
status=starting|ready|connected|dirty|saving|closed|expired|failed
write_lease_expires_at, terminal_token_hash
created_at, last_seen_at, closed_at
```

WebSocket token 只使用一次并绑定 Session、User、Project 和过期时间。Terminal Gateway 每次连接重新校验 AuthSession 与 EditorSession；不能只凭可猜测 session id 建立 PTY。

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
route
outcome
error_code
properties_json
```

P0 漏斗事件为：`login_succeeded`、`prompt_submitted`、`lead_routed`、`scope_classified`、`blueprint_generated`、`risk_approval_requested/decided`、`repository_ready`、`role_stage_completed`、`build_succeeded`、`preview_opened`、`editor_opened`、`version_committed`、`revision_applied`、`published`、`public_app_opened`。

公开页面访问等无登录事件允许 `user_id`、`session_id` 和 `run_id` 为空。`product_events` 不保存密码、Cookie、终端输入流、完整 Prompt、附件内容或模型私有推理。没有真实用户样本前只采集基线，不预设审批率和发布转化率目标。

### 8.9 Export JSON

Export 由应用服务从已持久化 Contract 和 Git commit 元数据组装，不直接暴露 Volume 路径。最小字段以 PRD 为准，包括 `schema_version`、`exported_at`、`project`、`repository`、`blueprint`、`architecture_spec`、`app_spec`、`current_version`、`versions`、`publication` 和附件公开元数据。

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

- Gateway 只从已验证 AuthSession 建立 `user_id`，生产环境拒绝用 `X-User-ID` 冒充身份。
- 登录接口使用限速、统一失败文案和安全事件审计；密码、Session token 和 Cookie 不进入日志。
- AppSpec、RevisionSpec 和附件引用全部经过 schema 与资源归属校验。
- Project、Repository、EditorSession、Version、Job 和 Preview 必须经统一 owner 查询，不允许租户资源裸 `db.get(id)`。
- 可信 Git bare repo、临时 worktree 和发布 Artifact 使用不同根目录；Sandbox 永远看不到 bare repo 与 `.git`。
- Renderer 只写模板允许目录。
- 运行时禁止安装依赖、修改依赖清单和执行任意 Shell。
- 构建子进程使用固定命令、超时、输出和磁盘上限。
- 云端用户不能读取其他用户的 Project、Repository、附件、worktree、日志、EditorSession 或 Preview。
- Terminal WebSocket 使用短时一次性 token；PTY 固定启动 Vim，不启动宿主 Shell。
- Sandbox 非 root、禁网、无 Secret、无 Docker socket，并使用 capability/seccomp/cgroup/生命周期限制。
- LLM API Key 只存在于 Railway 服务端环境变量。
- Preview 响应设置隔离策略，不允许生成应用访问平台管理 API。
- 发布前检查文件类型、总体积和入口文件。
- 配额预占使用数据库事务。

如果未来开放任意 Shell、依赖安装或网络访问，必须升级为更强的每次运行容器/VM 策略与审批，不能在当前受限 Vim Sandbox 中逐项放宽。

## 12. 部署

```text
GitHub 仓库
     |
     | push 自动部署
     v
┌──────────── Control Plane ──────────────┐
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
│  PostgreSQL Service                    │
│  · 用户 / AuthSession / 配额 / Job / 版本 │
└───────────────┬────────────────────────┘
                │ authenticated job/editor request
                v
┌──────── Linux Sandbox Host ─────────────┐
│ Repository Service + Sandbox Manager    │
│ · trusted local Git bare repositories   │
│ · rootless Editor Sandbox / Vim / PTY   │
│ · rootless Build Sandbox                │
│ · persistent disk: repo/artifact/log    │
└───────────────┬─────────────────────────┘
                    |
                    v
              Ollama Cloud
```

用户名密码、多用户隔离和 WebIDE 可以与现有 Control Plane 共存，但真实 xterm/Vim 不能直接落在无隔离能力的共享 Web 容器中。V1 验收部署需要一台可运行 rootless container/namespace、cgroup 和持久化磁盘的 Linux Sandbox Host。Control Plane 可继续使用 Railway；若不希望维护跨服务同步，也可以把整套 V1 通过 Docker Compose 部署到同一台受控 Linux VM。

### 12.1 镜像与进程边界

镜像构建阶段：

1. 安装固定 Node.js 依赖并构建 React Studio。
2. 安装 Python API、Agent 和数据库依赖。
3. 复制固定应用模板和 Renderer。
4. 不在运行时执行依赖安装。
5. Editor/Build Sandbox 使用独立最小镜像；镜像内不包含平台数据库凭证、LLM Key 或容器管理 socket。

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

### 12.2 PostgreSQL 与持久化磁盘

Railway PostgreSQL 是独立、按资源计费的非托管服务，不是免费附赠数据库。V1 需要配置备份并验证恢复流程。

持久化磁盘保存可信 bare repo、Artifact、日志和发布快照，但不能替代 PostgreSQL 元数据。服务重启或重新部署后，数据库与磁盘中的 Repository/Version 状态必须保持一致。

V1 明确采用**单 Control Plane 实例 + 单 Sandbox Host + 单持久化磁盘**，不承诺水平扩展。临时 worktree 可回收，bare repo 是用户源码事实，发布快照是读多写少的交付物；三者必须分目录、分权限和分生命周期管理，数据库只保存 storage key 与 hash。

扩展路径：

1. 优先把发布快照和带 hash 的静态资产迁移到 S3-compatible Object Storage。
2. Worker 拆分后，再把 BuildArtifact/工作区交换迁移到对象存储或受控产物传输。
3. PostgreSQL 继续保存 Artifact 元数据、hash、对象 key 和发布指针。
4. 完成迁移前不得增加 Web/Worker 水平副本并假设 Volume 可共享。

### 12.3 平台源码 GitHub 与用户 Project Git

`github.com/eastonsuo/another-atom` 只负责平台自身源码、文档和部署触发。用户 Project 的源码保存在 Sandbox Host 的本地 Git 仓库，不配置 GitHub remote，也不使用平台仓库承载用户代码。GitHub Pages 不能运行 FastAPI、Agent、PostgreSQL、Terminal Gateway 或 Sandbox Manager。

## 13. 代码组织

```text
another-atom/
├── another_atom/
│   ├── api/              FastAPI routes and SSE
│   ├── auth/             credentials, sessions and gateway context
│   ├── agent/            Lead routing, fixed team and structured outputs
│   ├── build/            job leasing, renderer and build runner
│   ├── contracts/        Pydantic API, AppSpec and event models
│   ├── domain/           projects, sessions, quota and versions
│   ├── repository/       trusted local Git lifecycle and version commits
│   ├── terminal/         editor sessions, WSS and PTY proxy
│   ├── sandbox/          rootless editor/build sandbox manager
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

1. 定义 LeadDecision、Blueprint、ArchitectureSpec、AppSpec、DataReview、Event、Export 和 Error Contract。
2. 建立 PostgreSQL/Alembic，并实现 username/password、AuthSession Gateway 和双用户 Project 隔离测试。
3. 建立 ProjectRepository、EditorSession、ProjectVersion↔commit 模型和本地 Git Repository Service。
4. 实现 Plan、配额预占和 Usage Ledger。
5. 实现 Lead direct/team 路由、固定专业团队、风险策略、阶段持久化和配额结算。
6. 完成 AppSpec、固定 React Renderer、`build_jobs`、Worker 和持久化事件。
7. 建立 Linux Sandbox Host、rootless Editor/Build Sandbox、Terminal Gateway 与 xterm.js/Vim。
8. 实现 Visual Studio 的 Lead 对话、Artifact 检查、SSE、WebIDE 和 iframe Preview。
9. 实现附件、ProductEvent、Export、Follow-up、Resolve、Restore 和显式 Publish。
10. 完成 Control Plane + Sandbox Host 部署、备份和故障恢复。
11. 完成 API/SSE、终端并发、Sandbox 逃逸边界、CPU/RSS、构建、Git 一致性和重启恢复压测。

## 15. V1 验收

- 两个用户名密码账号可分别登录；切换账号后 Project、Repository、Version、EditorSession、事件和配额互不可见。
- Lead 对每条消息只输出 direct/team；direct 只回答或澄清，team 按 Product Manager、Architect、Engineer、Data Analyst 固定顺序执行。
- UI 默认只呈现 Lead 对话，团队过程可展开检查，不声称动态角色选择、并行或自主仲裁。
- 非商品目录输入必须进入 supported、adapted 或 unsupported；unsupported 不创建 Build Job。
- 普通 supported 且用户明确要求构建时不重复审批；adapted、额外预算、范围变化、破坏性仓库操作和线上变更必须触发风险确认。
- AppSpec 不能改变依赖、构建命令或工作区边界。
- HTTP 创建构建后立即返回，构建由异步 Worker 完成。
- 同一实例的构建并发不超过配置上限，初始为 1。
- 每个 Project 唯一绑定一个 local Git repository；Build/Edit/Resolve/Restore 版本均映射到可验证 commit SHA。
- xterm.js 只能连接当前用户当前 Project 的 Editor Sandbox；Sandbox 看不到 `.git`、Secret、宿主 Shell或其他用户路径。
- Vim 修改先形成 dirty worktree；Save Version 完成校验、Build 和 commit 后才生成 ProjectVersion，失败不移动当前版本。
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

在这些协议确定前，V1 README 和产品界面不得声称已经支持用户电脑上的本地仓库执行。V1 的服务端 local Git 与云端受限 Vim WebIDE 不等同于该方向。
