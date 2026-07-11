# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> 把产品想法转化为可检查、可修改、可管理版本并可发布的网页原型。

Another Atom 设计为一个通过自然语言创建网页产品原型的 AI Agent 工作台。用户描述想法后，可以先检查系统整理的产品方案，再继续完成设计、构建、校验、修改和发布。

本项目受 [Atoms](https://atoms.dev/) 启发，但采用独立的产品与技术设计。它不是 Atoms 的复刻或分支，也不依赖 Atoms 的源代码和内部基础设施。

> **当前状态：** 已完成支持 Ollama Cloud 与 Mock Provider 的 V1 本地可运行纵切版本。真实模型默认使用 DeepSeek V4 Pro，每个 Run 可切换 V4 Flash；生成、预览、编辑、版本、发布路由、持久化、配额和自动化测试均可运行。Railway 公网部署尚未完成。

> **当前 Runtime 边界：** 可运行纵切版本只支持单实例。Blueprint 已移出 `POST /api/runs` 请求链，由进程内后台任务生成；审批使用数据库状态 CAS；已提交的阶段 Artifact、配额结算、Build Job 和构建版本在 Worker 重启后可幂等恢复。当前纵切仍要求显式审批 Blueprint；只在风险点确认仍是 Lead/Risk Policy 落地后的目标设计。生产环境不再根据未知 `X-User-ID` 自动创建账户，但真实 Session Gateway 尚未实现，因此该请求头仍只是临时 Demo 身份机制，不是生产认证。

> **已确认、尚未落地的 V1 设计扩展：** 用户名密码 Session Gateway 与用户级 Project 隔离；Lead 对每条消息做 `direct/team` 二选一路由；每个 Project 绑定服务端 local Git repository；xterm.js + 受限 Vim WebIDE 运行在独立 Linux Sandbox Host。

> **设计基线：** [V1 工程架构](./docs/v1/architecture-design.md) · [V1 Agent 设计](./docs/v1/agent-design.md)

## 版本规划

| 版本 | 目标 | 角色模式 | 当前状态 |
| --- | --- | --- | --- |
| **V1** | 交付有登录隔离、代码归属和公开测试能力的应用生成链路 | Lead 选择 direct 或完整的 Product Manager → Architect → Engineer → Data Analyst 团队 | 现有纵切可运行；Gateway/Git/WebIDE/Sandbox 待实现 |
| **V2** | 增加动态任务图、角色子集、并行、返工和仲裁 | Lead 在 Runtime 约束下动态协调专业 Agent | V1 完成后实施 |

项目按 **V1 -> V2** 顺序实施。V1 是当前开发和验收基线；V2 已进入版本规划，待 V1 云端验收通过后实施。

## V1 要交付的体验

1. 用户使用用户名密码登录；切换账号后只能看到新账号所属 Project。
2. 用户与 Lead 对话；Lead 直接回答/澄清，或调用完整固定团队。
3. Product Manager 生成 Blueprint；普通 supported 构建不重复审批，范围适配、额外预算、破坏性仓库操作和线上变更才请求确认。
4. Architect、Engineer 生成 ArchitectureSpec/AppSpec，Data Analyst 解释不可变校验证据。
5. 每个 Project 拥有一个服务端 local Git repository，Build/Edit/Resolve/Restore 版本映射 Git commit。
6. 用户通过结构化控件或 xterm.js + 受限 Vim WebIDE 修改源码；PTY 运行在隔离 Sandbox。
7. Save Version 通过校验和构建后才提交 commit；用户随后预览并显式发布选定版本。

### A. 应用生成与开发

#### 步骤 1：登录与路由

```text
用户名密码 -> 已认证用户上下文
    |
    v
[Lead] -> 直接回答 / 澄清
    |
    `----> 需要执行时调用固定团队
```

#### 步骤 2：设计与构建

```text
Product Manager -> Blueprint -> Risk Policy
    |
    v
[Architect] -> ArchitectureSpec
    |
    v
[Engineer] -> AppSpec
    |
    v
平台受控构建 -> local Git commit
```

#### 步骤 3：质量校验

```text
构建结果 -> 确定性工程 ValidationReport
    |
    v
[Data Analyst] -> DataReview
    |
    v
可交互预览 / xterm.js + 受限 Vim
```

### B. 预览、版本与发布

```text
可交互预览
    |
    +-- 修改或 Resolve -> 保存新版本 -> 再次校验
    |
    +-- Restore --------> 创建恢复版本，保留原历史
    |
    `-- 选择版本 -------> Publish / Update
                                  |
                                  v
                            稳定公网地址
```

Lead 是用户默认面对的单一对话入口。Lead 选择 `team` 后，专业角色按**固定顺序**接力；V1 不动态挑选角色子集、不并行，也不自主仲裁返工。

## V1 能力地图

V1 不是十几个分散功能的集合，而是一条从想法到公网结果的完整链路：

```text
主链路：登录 -> Lead direct | 固定团队 -> Project -> Blueprint -> Build -> Preview
代码链路：Project -> local Git -> xterm/Vim Sandbox -> Save Version -> commit
变更链路：Preview -> 结构化 Edit / Vim / Resolve / Restore -> ProjectVersion
发布链路：ProjectVersion -> Publish / Update -> Public URL

目标保障：用户隔离 | 持久化 | 配额 | Git 可追溯 | Sandbox | 错误恢复
```

### 1. 发起：从一个想法直接创建项目

- **你要做的：** 登录后在 Home 直接告诉 Lead 想构建什么，不需要先经过营销页或理解模式选择器。
- **系统会做的：** Lead 只做一个可见判断：自己回答/澄清，或者调用完整固定团队。用户也可以把 direct 结果覆盖为“调用团队”。
- **会留下的：** team 路径会创建真实 Project 和服务端本地 Git 仓库；需求、附件元数据、最近进展和源码历史都归属于当前登录用户。

### 2. 范围：让关键决策可见，但不要求每步审批

- **你会看到：** Product Manager 把需求整理成一份可以直接修改的 Blueprint，写清项目名称、页面、模块、视觉方向和数据需求。
- **系统怎么判断：** Ollama Cloud 或确定性 Mock Provider 判断需求是 `supported`（支持）、`adapted`（调整后支持）还是 `unsupported`（不支持）；结果必须通过同一套 Pydantic 校验后才能改变 Run 状态。
- **怎么往下走：** 普通 `supported` 需求不再重复审批，直接由固定团队接力；`adapted` 范围、额外预算、破坏性仓库操作、Restore 指针变化和公开发布变化才插入风险确认。
- **失败了怎么办：** 模型多次尝试仍失败时，Project 和输入都会保留。用户可以 Retry、修改需求后重试，或选择不依赖 AI 的 Starter Blueprint 继续。

### 3. 构建：过程看得见，结果点得动

- **真实执行：** AppSpec 进入受控 React Renderer；异步 Build Worker 只使用固定模板和预装依赖，不执行模型临时生成的命令。
- **过程透明：** Studio 通过 SSE 实时显示当前角色、构建进度和错误；刷新页面后仍能恢复之前的状态。
- **结果可用：** Viewer 可以切换 Desktop/Mobile；Home、Catalog、Product 页面和核心交互都能实际打开和操作，而不是静态截图。
- **还能继续改：** 文字、按钮、颜色和商品图片都可以修改；xterm.js + 受限 Vim 只暴露当前 Project 的临时 worktree，并运行在 rootless Sandbox 中，不提供登录 Shell。

### 4. 交付：让每次生成都成为可管理的版本

- **每一步都形成版本：** Build、Edit、Resolve、Restore 都会生成 ProjectVersion，并映射到该 Project 服务端本地 Git 仓库中的 commit。Restore 创建新的恢复 commit 和版本，不改写原历史。
- **发布由用户决定：** Publish、Update、Unpublish 都需要用户显式触发，并可以选择 Always Latest 或 Specify Version；Agent 不会自动发布。
- **发布结果可验证：** Public URL 在无登录、无本地状态的新浏览器中，也能打开正确版本。
- **数据可以带走：** Export 输出带版本信息的 JSON，并排除密钥、绝对路径、原始对话和内部配额流水。

### 5. 保障：让多用户和公开访问真正成立

- **身份可信：** 用户名密码登录后创建服务端 Session Cookie；资源归属来自 Session，不接受客户端自报 `user_id`。换账号后只显示新账号的 Project。
- **状态不会丢：** PostgreSQL 保存身份、Project、Session、配额、Job、事件和版本；Sandbox Host 持久化可信本地 Git 仓库和不可变构建产物。
- **用量不会透支：** Plan 和 Usage Ledger 在调用 LLM 前预占额度、调用后结算；多个并发 Session 不能绕过账户配额。
- **额度彼此独立：** Another Atom 的演示单位按 Provider 请求计数，用于产品内控制，不与 Codex 额度共用；Ollama Cloud 账户限制仍由 Provider 独立管理。
- **额度用完有出口：** V1 不提供自助充值；项目和已有结果会保留，用户可以继续查看/导出，并等待演示账户由管理员重置。
- **执行有隔离：** Terminal 和 Build 在 Linux Sandbox Host 的非 root 容器中运行，禁网、无密钥、根文件系统只读，并配置 capabilities、seccomp、CPU、内存、磁盘、PID 和时限约束。
- **统一产品入口：** 浏览器只访问一个 HTTPS Control Plane。Railway 可以承载 Control Plane，但真实 WebIDE/Build 需要 Linux Sandbox Host；V1 也可以把两层部署到同一台 Linux VM。
- **边界不遮掩：** Cloud、Integrations 和 Growth 在 V1 只说明当前能力边界，不触发尚未接通的授权、支付或第三方费用。

> **V1 能做到什么程度：** 当前专注于受控的商品展示/商品目录站。`unsupported` 需求在构建前停止；`adapted` 需求先展示哪些内容被映射或舍弃，经过用户确认后再继续。

## V1 交付里程碑

| 里程碑 | 可交付结果 | 阶段验收 | 状态 |
| --- | --- | --- | --- |
| **M0 设计基线** | PRD、架构、角色契约和双语 README | V1/V2 边界一致，关键状态、数据和错误契约可追踪 | 已完成 |
| **M1 Runtime 基础** | React 工作台、FastAPI、持久化、配额、事件和带 lease 的 Build Job | 可创建并重新打开 Project；持久化 Job 可在重启后恢复 | 本地已实现 |
| **M2 Agent 链路** | 真实 Lead `direct/team` 路由、固定专业团队、结构化产物和风险策略 | direct 不修改仓库；team 每阶段有可检查产物；只在风险事件阻塞 | Lead/风险策略待实现，当前固定 Pipeline 可运行 |
| **M3 身份与源码归属** | Session Gateway、用户隔离、Project 本地 Git 仓库、commit/version 映射 | 两个用户不能互读资源；每个保存版本都能定位到 Project commit | 设计完成，待实现 |
| **M4 Studio 与 Sandbox** | Preview、结构化编辑、xterm.js + Vim、保存/构建/校验和 Restore | Terminal 只能看到租约 worktree；逃逸/禁网/资源测试通过；源码可恢复 | Preview/编辑已实现，WebIDE/Sandbox 待实现 |
| **M5 公开交付** | Publish/Unpublish、稳定路由、Export、自动化测试和云部署 | 主路径与反路径通过；干净浏览器打开指定公开版本 | 路由/测试已实现，公网部署待完成 |

### 最终验收基线

#### 1. 功能闭环

- Golden Path 在干净数据下连续执行 5 次，完整成功 5/5。
- 公开地址可从干净浏览器访问，并准确遵守 Always Latest 与 Specify Version 的版本指针。

#### 2. 稳定性与数据隔离

- 5 次刷新恢复测试中，Project、Session、版本和发布状态恢复 5/5。
- 跨用户、跨 Project 或跨 Session 的资源/事件泄漏数量为 0。

#### 3. 响应速度与状态可见性

- 创建 Run/Build Job 的 API 在 1 秒内返回标识，接受请求后 2 秒内出现第一条用户可见事件。
- Lead 路由、必要风险确认、输入不受支持、配额不足、LLM 失败、构建失败和排队状态都有明确反馈，不产生虚假进度。

#### 4. 用户体验

- 所有可见控件都有真实行为、禁用原因或能力边界。
- 桌面端和移动端不存在阻塞操作的内容或控件重叠。

#### 5. 数据契约与安全

- Export JSON 字段符合约定。
- 导出结果不得包含密钥、凭证、绝对路径、原始对话和内部配额流水。
- 每个 ProjectVersion 都能定位到所属 Project 仓库的 commit；Sandbox worktree 不能访问 `.git`、其他 Project、凭证、宿主机网络或容器 Runtime。

## 设计理念

### 1. 产品层：单一 Lead，只在真实风险处确认

用户始终只面对 Lead。Lead 自己回答/澄清，或调用完整团队。Blueprint 仍是可检查的产品契约，但不再是统一审批门；只有范围适配、额外预算、破坏性源码操作、版本指针变化和公开发布变化才要求确认。

### 2. 协作层：角色必须通过产物交接

Lead、Product Manager、Architect、Engineer、Data Analyst 的意义不在于展示多个角色名称，而在于逐步收敛不同类型的不确定性：

```text
协调层  用户消息             -> LeadDecision        直接回答或调用固定团队
产品层  Prompt               -> Blueprint           确认要构建什么
架构层  Blueprint            -> ArchitectureSpec    定义路由、数据和呈现边界
工程层  ArchitectureSpec     -> AppSpec + Report    构建并验证平台行为
数据层  AppSpec + Report     -> DataReview          检查数据并解释证据
交付层  DataReview           -> ProjectVersion      保存、恢复和发布结果
```

每个专业角色交接产物都要通过 Schema 校验、持久化并在界面中可检查。V1 Lead 是真实 Agent，但权限刻意收窄为 `direct` 或 `team`；风险检查、状态推进、重试和失败收敛由 Runtime 控制。

### 3. 执行层：模型负责判断，平台掌握权限

LLM 负责需求理解和结构化决策，但不能安装依赖、修改构建命令、执行任意 Shell 或自动发布。身份、仓库、Renderer、Build Worker、Sandbox、配额事务和发布服务由平台控制；WebIDE 只在受限 worktree 中启动固定 Vim，不提供通用 Shell。

### 4. 状态层：运行、版本和发布相互分离

一次 Agent Run 失败不应损坏已有版本；一次编辑不应自动改变指定的线上版本；Restore 也不应删除历史。因此 Project、Run、ProjectVersion、Git commit 和 Publish 指针分别建模，所有源码和发布变化都能追踪和恢复。

### 5. 演进层：V1 先证明闭环，V2 再增加自治

V1 验证用户隔离、Lead 路由、固定团队、风险确认、源码编辑、构建、版本和发布能否形成可用闭环。V2 沿用相同 Contract，并把 Lead 升级为动态 TaskGraph、角色子集、并行执行、返工和仲裁。

## 实现思路与关键取舍

| 取舍 | 为什么这样做 | 得到什么 | 代价与边界 |
| --- | --- | --- | --- |
| 真实 LLM + 结构化 Contract + 确定性 Renderer | 既要证明模型真实理解需求，又要控制共享云环境中的执行风险 | Blueprint/AppSpec 会真实受输入影响，构建结果可校验 | V1 不支持任意技术栈或自由代码执行 |
| 用户名密码 Session Gateway + 用户级租户 | Project 归属必须来自可信身份，不能依赖客户端请求头 | 切换账号即可验证 Project 隔离 | V1 不实现 Organization、成员关系或共享 Project 权限 |
| 每个 Project 一个服务端本地 Git 仓库 | Project 需要持久、可检查的源码归属 | ProjectVersion 能映射 commit，无需先接 GitHub OAuth | V1 不配置 remote，不支持 push/pull 或用户电脑仓库 |
| xterm.js + rootless Sandbox 中的固定 Vim | 用户需要源码级编辑，但不能获得宿主机 Shell | 保留终端编辑体验，同时限制文件系统和资源 | 需要 Linux Sandbox Host；不是 Claude Code 式 Terminal Agent |
| 异步 Build Job + 固定模板和依赖 | 构建不能阻塞 HTTP 请求，也不能执行模型临时生成的命令 | Job 可恢复，资源和失败范围可控制 | 生成范围受模板能力限制，初始构建并发为 1 |
| 当前纵切使用单 API 进程 + 单进程内 Worker | 本地/Railway V1 先保证持久化正确性，再考虑水平扩展 | PostgreSQL Job/Artifact 检查点无需队列集群也能重启恢复 | V1 不支持水平副本、独立 Worker 集群、LISTEN/NOTIFY 或消息队列 |
| 真实 Plan/Quota/Ledger，暂不接支付 | 多用户、多 Session 必须共享并正确结算账户额度 | 并发请求不能透支，模型用量可以审计 | V1 不实现 Stripe、Wallet、充值或发票 |

## 当前单实例决策清单

### 当前纵切已实现

- `POST /api/runs` 提交后即返回，Blueprint 由使用新数据库 Session 的进程内后台任务生成；启动时会恢复中断的 `product_running` Run。
- Blueprint 审批使用 `awaiting_approval -> build_queued` 状态 CAS，Approval 和 BuildJob 唯一约束防止重复排队。
- 成功 Agent 阶段把 Artifact 与 Provider 用量结算放在同一事务提交；Worker 恢复复用已提交阶段、只对齐已完成 Job，不重放 Pipeline，并复用既有 Build Version。
- 失败只结算已观测到的 Provider 请求并释放剩余预占；非 LLM 异常也会清空未结算 reservation。
- Preview 通过 Project owner 联查校验归属；非测试环境遇到未知 `X-User-ID` 返回 401，不再自动创建满配额账户。
- Validator 校验 Blueprint 页面覆盖、受控 mapped requirement 的确定性证据、ArchitectureSpec/AppSpec 视觉 Token 一致性和颜色对比度。
- SSE 在单实例基线下继续轮询数据库，但每个连接复用一个读取 Session。

### V1 验收前仍必须完成

- 用用户名密码 Session Gateway 替换临时身份请求头，并完成双用户隔离验收。当前拒绝未知 ID 只是加固，不是完整认证。
- 实现每 Project 源码物化、commit/version 映射，以及按用户/Project 隔离的 rootless Sandbox；完成前不能开放 xterm.js/Vim 或真实项目构建。
- 完成 Railway 部署，在 PostgreSQL 与持久化存储上验证重启恢复，并从干净浏览器验收公开 URL。

### 明确后置，不进入单实例 V1

- 超出 V1 服务端 Session Gateway 的完整 Token/JWT/OAuth 认证平台。
- PostgreSQL LISTEN/NOTIFY 或消息队列式 SSE、独立持久化队列、独立 Worker 集群、跨实例 lease-owner fencing 和分布式乐观并发控制。
- API/Worker 水平副本，以及为此配套的共享对象存储架构。

### 后续可以优化，但不是当前正确性工作

- 多租户 Sandbox 池化、容量调度、更强容器/MicroVM 隔离，以及把不可变发布 Artifact 迁移到对象存储。
- Provider 支持时引入幂等键，收窄“外部响应已返回、Artifact 事务尚未提交”之间的崩溃窗口。
- Edit/Restore 计费策略、Export 分页/流式输出和 SPA fallback 404 加固。

完整组件、状态、数据、安全和部署设计见 [V1 架构设计](./docs/v1/architecture-design.md)；执行范式、Human-in-the-loop、Context、Tool、Sandbox 和验收修复见 [V1 Agent 设计](./docs/v1/agent-design.md)。

## V1 部署与访问架构

这里区分两件事：**开发者部署 Another Atom 平台**；**用户在平台内发布生成应用的某个版本**。前者需要可信 Control Plane 与 Sandbox Host，后者只是改变产品内发布指针。

```text
平台部署链路

开发者 -- git push --> GitHub
                         |
                         +--> Railway 或 Linux VM：Control Plane
                         |
                         `--> Linux Sandbox Host：Git / Vim / Build

用户访问与应用发布链路

用户浏览器 -- HTTPS/WSS --> Control Plane 公网域名
                         |
             +-----------+----------------+
             | React Visual Studio        |
             | FastAPI REST + SSE + WSS   |----> Ollama Cloud / Mock
             | Session Gateway + Lead     |
             | Repository Service         |
             | Preview / Published Routes |
             +-----------+----------------+
                         |
                +--------+----------------+
                |                  |
                v                  v
          PostgreSQL        Linux Sandbox Host
       用户 / Session /     local Git / worktree /
       Project / 配额 /     Vim PTY / Build / Artifact
       Job / Version

用户选择 ProjectVersion -- Publish / Update --> Published Route
                                                    |
                                                    v
                                               稳定公网地址
```

Railway 可以承载 Control Plane，但不假设 Railway 单独提供 Terminal 所需的隔离能力。真实 WebIDE 和 Build Sandbox 需要支持 rootless container、namespace、cgroup 的 Linux Host；V1 也可部署在一台 Linux VM 上，但权限和网络边界仍须分开。

## V1 不包含

- Terminal CLI、登录 Shell，或操作用户电脑上的本地仓库。
- GitHub/GitLab remote、push/pull、SSH Key 或仓库共享。
- 运行时安装依赖或任意代码执行。
- 任意技术栈和生成式后端。
- 自主或并行的多 Agent 协作（计划在 V2 实现）。
- 任意 Provider 或不受限模型标识；V1 只开放配置中的 DeepSeek allowlist。
- 生成应用内部的认证、数据库、交易或支付系统。
- Stripe 付费订阅、Wallet、充值和发票。

## 版本实施计划

### V2：自主多 Agent（计划实施）

V2 是 V1 之后的下一实施版本，不是可选展示方向。它把 V1 的二选一路由 Lead 升级为动态 TaskGraph、独立专业角色上下文、角色子集、选择性并行、结构化返工、仲裁和 Run 级预算。产品、工程和行为基线分别见 [V2 PRD](./docs/v2/another-atom-v2-prd.md)、[V2 架构设计](./docs/v2/architecture-design.md)和 [V2 Agent 设计](./docs/v2/agent-design.md)。

### 未归属版本：本地 Agent Runtime

类似 Claude Code 的本地 Runtime 可以在后续操作本地文件、Git、Shell、npm 和 localhost Visual Studio。该方向尚未实现，也尚未确定归属版本。

## 项目状态

已完成：

- [x] Atoms 公开功能分析
- [x] V1 产品需求和验收标准
- [x] V1 架构与部署设计
- [x] V2 PRD、架构与 Agent 设计草案
- [x] 双语 README、评估说明和项目实施约束
- [x] FastAPI API、SQLAlchemy 持久化、配额账本、事件、版本和发布路由
- [x] React Studio、可交互受控 Renderer、Desktop/Mobile 预览、编辑和 Restore
- [x] Mock 角色 Pipeline、Schema 校验和有限失败重试
- [x] Ollama Cloud Provider、DeepSeek 模型切换、Provider 用量账本和有限重试
- [x] 带数据库 lease 恢复的单并发持久化 Build Worker
- [x] 审批 CAS、阶段检查点幂等恢复、配额释放/结算、Preview 归属、异步 Blueprint 和契约化 Validator 测试
- [x] 单元/集成测试，包括连续五轮 Golden Path
- [x] Dockerfile 与 Railway 配置

尚未完成：

- [ ] 每个项目独立物化源码并执行 `npm run build`；当前生成应用由共享 React Runtime 渲染已校验 AppSpec
- [ ] 用户名密码 Session Gateway 与双用户隔离验收
- [ ] 真实 Lead `direct/team` 路由和风险驱动的内联确认
- [ ] ProjectRepository 初始化与 ProjectVersion/commit 映射
- [ ] xterm.js + 受限 Vim、Terminal Gateway 和 rootless Sandbox Host
- [ ] Resolve、项目重命名/删除和附件文件上传
- [ ] Railway 部署和公开在线地址
- [ ] V2 Sandbox/模型 ADR、压测预算和安全基线确认
- [ ] V2 自主多 Agent 实现、测试和部署

### 提交前检查

- 在 README 和笔试结果回收处填写在线 Demo URL。
- 确认 GitHub 仓库保持 Public，并从干净浏览器走通 Golden Path。
- 写明是否需要演示账号；若不需要账号，也要明确说明。
- 更新完成/未完成状态，不把计划功能写成已经实现。
- 记录已知边界、失败场景、Railway 资源规格和压测结果。

## 与评估维度的对应

| 评估维度 | README 与实现需要提供的证据 |
| --- | --- |
| 完成度 | Golden Path、反路径、持久化恢复、公开 Preview/Publish 和自动化测试结果 |
| 工程思维 | 技术选型、Contract、异步 Build、配额事务、安全边界和明确取舍 |
| 用户体验 | 单一 Lead 入口、风险驱动确认、实时状态、可交互 Preview/WebIDE、可恢复版本和可操作错误 |
| 创新性 | 可检查产物链、用户隔离的本地 Git 源码归属、受限终端编辑和版本化发布闭环 |
| 可交付性 | GitHub 源码、双语 README、可复现运行步骤、Railway 在线地址和已知边界 |

## 相关链接

- 源代码仓库：[github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- 在线版本：尚未部署
- [V1 产品需求](./docs/v1/another-atom-v1-prd.md)
- [V1 架构设计](./docs/v1/architecture-design.md)
- [V1 Agent 设计](./docs/v1/agent-design.md)
- [本地运行与 Railway 部署说明](./docs/v1/local-run-and-railway-deployment.md)
- [V1 实现 Review](./review/2026-07-11-v1-implementation-review.md)
- [V2 产品需求](./docs/v2/another-atom-v2-prd.md)
- [V2 架构设计](./docs/v2/architecture-design.md)
- [V2 Agent 设计](./docs/v2/agent-design.md)
- [Atoms 参考分析](./docs/reference/atoms-reference-analysis.md)

## 附录

- 原版产品参考：[Atoms](https://atoms.dev/)
