# Another Atom V1 架构设计

[toc]

- 文档状态：V1 实施基线
- 更新日期：2026-07-10
- 产品文档：[Another Atom V1 产品需求文档](./another-atom-v1-prd.md)
- 参考分析：[Atoms 参考产品功能分析](./atoms-reference-analysis.md)

## 1. 架构结论

Another Atom V1 定位为一个 **终端优先、本地执行、浏览器可视化、云端控制与发布** 的 AI 应用生成工具。

终端不是 Web 产品的附属入口，而是 Agent 的主要控制面；浏览器 Visual Studio 用于展示 Blueprint、构建事件、应用预览和版本。真实 LLM 负责把自然语言需求转换成结构化 Blueprint 与 AppSpec，受控工具负责写入项目、执行构建并产生可运行结果。

```text
                         Another Atom V1

┌──────────────────────────── 用户交互层 ────────────────────────────┐
│                                                                  │
│  Terminal CLI（主入口）                  React Visual Studio      │
│  Python + Typer/Rich                     浏览器可视化工作台         │
│  · 输入需求                              · Blueprint 审批          │
│  · 恢复 Session                          · 构建过程                 │
│  · 确认/取消操作                          · 应用预览与修改            │
│         │                                      │                  │
└─────────│──────────────────────────────────────│──────────────────┘
          │ Python 调用                          │ REST + SSE
          │                                      │ OpenAPI 类型同步
          ▼                                      ▼
┌──────────────────── Python 本地 Agent Runtime ────────────────────┐
│                      FastAPI Local Daemon                         │
│                                                                  │
│  ┌────────────────── OpenAI Agents SDK ──────────────────────┐   │
│  │ Agent Loop                                                │   │
│  │ 需求 → Blueprint → 用户审批 → AppSpec → 执行 → 修改        │   │
│  │                                                           │   │
│  │ Tools                                                     │   │
│  │ · 读取/写入项目文件     · Shell 命令                       │   │
│  │ · Git/版本管理          · 启停 npm Dev Server              │   │
│  └───────────────────────────────────────────────────────────┘   │
│             │                              │                     │
│             ▼                              ▼                     │
│  ┌────────────────────┐        ┌────────────────────────────┐    │
│  │ SQLite             │        │ 本地项目工作区              │    │
│  │ · Projects         │        │ · React 项目源码            │    │
│  │ · Sessions         │        │ · 生成文件                  │    │
│  │ · Runs/Events      │        │ · Git 版本                  │    │
│  │ · Versions         │        └─────────────┬──────────────┘    │
│  └────────────────────┘                      │ npm run dev        │
└──────────────────────────────────────────────│───────────────────┘
                                               ▼
                                  ┌─────────────────────────┐
                                  │ 生成应用 Dev Server      │
                                  │ localhost:动态端口       │
                                  │                         │
                                  │ Visual Studio 通过       │
                                  │ iframe 展示真实应用       │
                                  └────────────┬────────────┘
                                               │ publish
                                               ▼
                                  ┌─────────────────────────┐
                                  │ 公网部署                  │
                                  │ 可测试的在线访问地址       │
                                  └─────────────────────────┘


┌────────────────────────── 云端控制面 ─────────────────────────────┐
│                                                                  │
│  用户认证        配额预占/结算       订阅状态       LLM Gateway    │
│      │                │                │               │          │
│      └────────────────┴────────────────┴───────┬───────┘          │
│                                               ▼                  │
│                                      PostgreSQL                  │
│                              Users / Plans / Usage Ledger         │
│                                               │                  │
└───────────────────────────────────────────────│──────────────────┘
                                                ▼
                                      OpenAI / 其他 LLM
```

V1 同时提供两种运行形态：

1. **Local Mode**：CLI、Agent 和工作区运行在用户机器上，Visual Studio 通过 localhost 打开。这是长期产品的核心形态。
2. **Cloud Demo Mode**：同一套 Agent Core 运行在 Railway 的受控容器中，提供公开可测试链接。这是挑战验收与产品展示形态。

Cloud Demo Mode 只允许受控文件操作与构建命令，不向公网用户开放任意 Shell。完整远程编码沙箱不属于 V1。

## 2. 设计目标与约束

### 2.1 V1 必须实现

- 真实调用 LLM，不使用预设文本伪装生成结果。
- 从终端或 Visual Studio 创建项目并获得结构化 Blueprint。
- 用户确认 Blueprint 后才进入文件生成和构建阶段。
- 生成真实可运行的 React Web 应用，而不是静态截图。
- 在 Visual Studio 中查看实时构建事件和应用预览。
- 支持至少一次自然语言增量修改。
- 保存项目、Session、运行记录和版本。
- 支持同一用户拥有多个 Session，并能恢复其中任意一个。
- 在调用 LLM 前校验用户、方案和剩余配额。
- 将生成结果发布为可公开访问的 HTTPS 地址。

### 2.2 V1 不实现

- 面向公网开放任意 Shell、系统路径或网络访问。
- 为每个远程任务创建独立虚拟机或 Kubernetes 沙箱。
- 任意技术栈和任意后端应用生成。
- 真实多 Agent 并行协作；Planner、Designer、Engineer、QA 在 V1 中是阶段语义。
- 完整 Stripe 结算。V1 建立 Plan、Subscription 和 Usage Ledger 模型并执行配额，订阅状态可由种子数据或管理接口设置。
- 高可用、多区域和水平扩容。

## 3. 核心工作流

```text
User Prompt
    |
    v
Authenticate User -----> Load Plan and Remaining Quota
    |                              |
    |                         insufficient
    |                              v
    |                         Reject Request
    v
Reserve Quota
    |
    v
LLM -> Blueprint (validated Pydantic model)
    |
    v
User Edit / Approve
    |
    v
LLM -> AppSpec + File Change Plan
    |
    v
Controlled Tools -> Write Workspace -> npm build
    |                                      |
    |                                 build failed
    |                                      v
    |                              repair or report error
    v
Preview Ready -> Visual Studio iframe
    |
    v
Follow-up Change -> New Run -> New Version
    |
    v
Publish -> Public URL
```

一次 LLM 调用的配额处理必须遵循：

```text
verify session
    -> reserve estimated quota in a database transaction
    -> call model
    -> read actual token usage
    -> settle actual usage and release unused reservation
    -> release reservation on failure
```

不能在 LLM 返回后才检查配额，否则并发 Session 可以同时透支同一账户。

## 4. 组件设计

### 4.1 Terminal CLI

技术：Python、Typer、Rich。

职责：

- 创建或打开项目工作区。
- 输入 Prompt、显示流式输出和构建状态。
- 展示 Blueprint 摘要并接受确认、修改或取消。
- 继续最近 Session，或按 Session ID 恢复。
- 启动本地 Agent Daemon 和 Visual Studio。
- 将命令转换成与 Web Studio 相同的应用层请求。

目标命令形态：

```text
another-atom
another-atom "build a product catalog"
another-atom --continue
another-atom --resume <session-id>
another-atom studio
```

具体参数在 CLI 实现阶段确认，架构不依赖参数名称。

### 4.2 Visual Studio

技术：React、TypeScript、Vite。

职责：

- 提供 Prompt Composer 作为终端之外的等价入口。
- 展示和编辑 Blueprint。
- 展示 Agent Run、阶段状态、工具事件和错误。
- 通过 iframe 加载生成应用。
- 提供桌面与移动预览、版本列表和发布状态。
- 发送增量修改、审批、取消和恢复命令。

Visual Studio 不直接访问数据库、LLM 或工作区文件，所有操作通过 FastAPI 完成。

### 4.3 Python API / Local Daemon

技术：FastAPI、Pydantic、Uvicorn。

职责：

- 为 CLI 和 Visual Studio 提供统一应用接口。
- 校验身份、Session、项目归属和请求参数。
- 启动 Agent Run 并维护状态机。
- 将运行事件以 SSE 推送给前端。
- 托管生产构建后的 Visual Studio 静态文件。
- 在 Cloud Demo Mode 中托管生成应用的静态构建结果。

Local Mode 默认只监听 `127.0.0.1`，不暴露到局域网。

### 4.4 Agent Runtime

技术：OpenAI Agents SDK、Pydantic Structured Output。

V1 使用单一主 Agent，通过明确阶段完成任务，不在首版引入复杂 Agent Graph：

```text
understand -> blueprint -> approval -> plan changes
           -> execute tools -> validate -> publish
```

Agents SDK 负责：

- Agent Loop。
- LLM Tool Calling。
- 结构化输出。
- 模型会话上下文。
- Run Hooks、Usage 和 Trace。
- 审批后的中断恢复。

业务系统仍然负责：

- 用户与 Session 归属。
- Project、Run、Version 和 Deployment 状态。
- 配额预占与结算。
- 工作区和 Shell 权限。
- SSE 事件协议。

Agents SDK 的 Session 不能替代业务数据库。

如果后续明确要求 OpenAI、Anthropic、Gemini 多供应商平等切换，再评估 PydanticAI；V1 不为尚未确认的多模型需求增加框架层。

### 4.5 Tool Layer

V1 工具集合：

- `inspect_workspace`：读取目录结构和允许的文本文件。
- `write_files`：按变更计划创建或覆盖项目文件。
- `apply_patch`：对现有文件执行受控增量修改。
- `run_build`：只执行预定义构建命令。
- `start_preview`：本地模式启动开发预览。
- `publish_build`：发布生产构建产物。
- `git_snapshot`：记录版本快照，可在 V1 后半段实现。

工具必须执行以下公共检查：

- 解析后的路径必须位于当前项目工作区内。
- 命令必须来自允许列表，不能直接执行模型返回的任意字符串。
- 子进程必须设置超时、输出上限和退出回收。
- 每次工具调用必须产生 started、completed 或 failed 事件。
- 破坏性操作必须要求用户审批。

### 4.6 Project Workspace 与 Preview

工作区是生成应用的事实来源：

```text
data/workspaces/{user_id}/{project_id}/
├── package.json
├── src/
├── public/
├── dist/
└── .another-atom/
    ├── blueprint.json
    ├── app-spec.json
    └── project.json
```

Local Mode：

- 使用 `npm run dev` 启动动态端口。
- Python 通过 `preview.ready` 事件返回 URL。
- Visual Studio iframe 加载该 localhost URL。

Cloud Demo Mode：

- 不为每个项目暴露随机公网端口。
- 执行 `npm run build` 生成 `dist`。
- FastAPI 通过 `/preview/{project_id}/{version}/` 提供静态结果。
- V1 生成应用如果需要数据持久化，调用受控平台 API，不能自行启动任意后端。

## 5. Python 与 JavaScript 通信

V1 使用 **REST + SSE + OpenAPI**，不使用 WebSocket。

```text
React Studio ---- REST ----> FastAPI
React Studio <---- SSE ----- FastAPI / Agent Events
React Studio ---- iframe --> Generated App
```

REST 负责命令和查询：

```text
POST /api/sessions
GET  /api/sessions/{session_id}
POST /api/sessions/{session_id}/messages
GET  /api/sessions/{session_id}/events
POST /api/runs/{run_id}/approve
POST /api/runs/{run_id}/cancel
GET  /api/projects/{project_id}/versions
POST /api/projects/{project_id}/publish
```

SSE 负责服务端单向事件推送：

```json
{
  "event_id": "evt_123",
  "session_id": "session_123",
  "run_id": "run_123",
  "type": "tool.started",
  "timestamp": "2026-07-10T12:00:00Z",
  "payload": {
    "tool": "write_files"
  }
}
```

核心事件类型：

```text
run.started
llm.streaming
blueprint.generated
approval.required
tool.started
tool.completed
preview.ready
run.failed
run.completed
```

Pydantic 模型是 API Contract 的事实来源。FastAPI 生成 OpenAPI，前端通过 `openapi-typescript` 生成 TypeScript 类型，避免手工维护两份 Blueprint、Session 和 Event 定义。

## 6. 数据与 Session 设计

### 6.1 存储分工

Local Mode：

- 项目文件：本地文件系统。
- Session、Run、Event、Version 索引：SQLite。
- 登录、Plan、共享配额和云端 Usage Ledger：云端 PostgreSQL。

Cloud Demo Mode：

- 用户、项目、Session、Run、版本元数据：PostgreSQL。
- 项目工作区与构建结果：Railway Persistent Volume。
- LLM 密钥：Railway 环境变量，只在服务端读取。

### 6.2 核心关系

```text
User
  | 1
  |---- n Project
  |         | 1
  |         |---- n Session
  |         |          | 1
  |         |          |---- n AgentRun
  |         |                     |---- n RunEvent
  |         |
  |         |---- n ProjectVersion
  |         `---- n Deployment
  |
  |---- 1 Subscription ---- 1 Plan
  `---- n UsageLedger
```

核心表：

- `users`：用户身份和状态。
- `plans`：方案、周期配额和功能边界。
- `subscriptions`：用户当前方案和有效期。
- `quota_accounts`：可用、预占和已消费额度。
- `usage_ledger`：每次预占、结算和释放记录。
- `projects`：项目名称、工作区和当前版本。
- `sessions`：同一项目下可恢复的对话上下文。
- `agent_runs`：一次用户指令对应的运行。
- `run_events`：面向 CLI 和 Studio 的事件流。
- `project_versions`：Blueprint、AppSpec 和构建产物版本。
- `deployments`：公开 URL、版本和发布状态。

SQLite 和 PostgreSQL 使用相同领域模型，但不要求 V1 自动双向同步全部本地项目。

## 7. 身份、配额与订阅

### 7.1 身份

- Cloud Demo 通过 Web 登录获得 Session/JWT。
- Local CLI 通过设备登录或 Personal Token 获得账户身份；具体登录交互在实现阶段确定。
- 每个 API 请求校验 `user_id` 与目标 Project/Session 的归属。

### 7.2 多 Session

- 一个用户可以同时拥有多个项目和多个 Session。
- `session_id` 是上下文恢复标识，不是用户身份。
- 每次 Agent Run 同时绑定 `user_id`、`project_id` 和 `session_id`。
- 同一账户下的所有 Session 共享订阅配额。

### 7.3 订阅

V1 建立 Free/Demo Plan 与付费 Plan 的数据结构，但不要求接入真实支付：

```text
Plan -> Subscription -> Quota Account -> Usage Ledger
```

以后接入 Stripe 时，Webhook 只负责更新 Subscription，不直接修改 Agent Session。Agent 在每次运行前读取统一的 Quota Account。

## 8. 部署设计

### 8.1 Railway 拓扑

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
│  · Node.js / npm                       │
│  · React Studio 静态文件                │
│  · Agent 工具执行                       │
│                                        │
│  对外提供一个 HTTPS 域名：               │
│  /                  Visual Studio       │
│  /api/*             FastAPI             │
│  /events/*          SSE                 │
│  /preview/{id}/*    生成应用             │
│                                        │
│  Persistent Volume                     │
│  · 项目工作区                           │
│  · 生成文件                             │
│                                        │
│  PostgreSQL                            │
│  · 用户 / Session / 配额 / 用量 / 订阅   │
└───────────────────┬────────────────────┘
                    |
                    v
              OpenAI / 其他 LLM
```

Web Service 只暴露一个 Railway HTTP 端口：

```text
/                         React Visual Studio
/api/*                    FastAPI REST
/api/sessions/*/events    SSE
/preview/*                Generated static builds
```

### 8.2 Docker 构建

Docker 镜像需要同时包含 Python Runtime 和 Node.js Runtime：

1. 前端阶段安装依赖并构建 React Studio。
2. Python 阶段安装 API、Agent 和数据库依赖。
3. 复制 Studio 构建结果和应用模板。
4. 启动时执行数据库迁移，然后启动 Uvicorn/Gunicorn。

生产数据库使用 Railway PostgreSQL。Railway 的 PostgreSQL 模板是独立、按资源计费的非托管服务；V1 可以使用，但需要配置备份并避免把它描述成免费附赠数据库。

### 8.3 GitHub 的职责

GitHub 只负责：

- 源代码和文档。
- Pull Request 与版本历史。
- 触发 Railway 自动部署。

GitHub Pages 不能运行 FastAPI、Agent Runtime、PostgreSQL 或持久工作区，因此不能单独承载 Another Atom。

## 9. 安全边界

V1 的主要风险不是 LLM 输出质量，而是模型驱动工具在共享环境中的权限。

必须满足：

- 云端用户只能访问自己的工作区前缀。
- 不把 LLM API Key 返回给浏览器或生成应用。
- 所有数据库查询带用户归属条件。
- Shell 使用固定命令模板与参数校验。
- 禁止访问宿主机敏感目录、Docker Socket 和其他项目目录。
- 限制构建时长、并发数、输出大小和磁盘占用。
- 发布前对生成静态文件执行大小和类型检查。
- 对配额预占使用数据库事务，避免并发透支。

V1 的共享 Railway 容器只适合受控 Demo。如果产品要开放任意代码、依赖安装和网络访问，必须引入每次运行独立的容器或虚拟机沙箱，不能在当前容器上逐步放宽权限。

## 10. 代码组织

```text
another-atom/
├── another_atom/
│   ├── api/              FastAPI routes and SSE
│   ├── agent/            agent definitions and run orchestration
│   ├── cli/              Typer commands
│   ├── contracts/        Pydantic API and event models
│   ├── domain/           projects, sessions, quota, versions
│   ├── storage/          SQLite/PostgreSQL repositories
│   └── tools/            workspace, build, preview, publish tools
├── studio/               React Visual Studio
├── templates/
│   └── react-app/        controlled V1 application template
├── migrations/           database migrations
├── tests/
├── docs/
├── Dockerfile
├── README.md
└── README.zh-CN.md
```

领域逻辑不能直接依赖 FastAPI 路由、Typer 命令或具体数据库驱动。CLI 和 Studio 只是同一应用服务的两个适配器。

## 11. V1 实施顺序

1. 定义 Blueprint、AppSpec、Session、RunEvent 和 Usage 模型。
2. 建立 FastAPI、SQLite 和基础 REST/SSE。
3. 接入真实 LLM，完成 Blueprint 结构化生成。
4. 实现审批状态和 Session 恢复。
5. 实现受控工作区工具和 React 模板生成。
6. 启动本地 Preview，并在 Studio iframe 展示。
7. 实现一次增量修改和 ProjectVersion。
8. 实现用户、Plan、配额预占和 Usage Ledger。
9. Docker 化并部署 Railway Web Service、PostgreSQL 和 Volume。
10. 实现生产构建发布和公开 Preview URL。

## 12. 验收条件

- 新用户能通过 CLI 或 Web 输入需求并获得真实 LLM 生成的 Blueprint。
- 未确认 Blueprint 时不会写入或构建项目。
- 构建事件可以同时被 CLI 与 Studio 正确消费。
- 生成应用能真实交互并在刷新后恢复项目状态。
- 用户可以恢复两个不同 Session，且上下文不会串线。
- 并发请求不能绕过同一账户的配额限制。
- 云端用户无法读取其他用户工作区。
- Railway 重启或重新部署后，数据库和挂载卷中的必要数据仍然存在。
- 发布后得到可从公网打开的 HTTPS 地址。
- LLM、构建或发布失败时，Run 进入明确失败状态并释放未使用配额。

## 13. 待实施阶段确认

以下细节不影响当前架构，但需要在实现时用测试结果确定：

- CLI 的最终安装方式与设备登录交互。
- V1 选用的具体 OpenAI 模型和单次配额换算规则。
- Railway 实例所需的最低内存；当前不能仅凭设计文档准确估算。
- 生成应用的数据持久化范围是平台 API 还是仅限 Demo 数据模型。
- 是否在 V1 接入 Git 快照，或只保存应用层 ProjectVersion。
