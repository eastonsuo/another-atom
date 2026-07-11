# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> 把产品想法转化为可检查、可修改、可管理版本并可发布的网页原型。

## 1. 产品定位

Another Atom 是一个通过自然语言创建网页产品原型的 AI Agent 工作台。用户可以从一次对话开始，经过需求整理、设计、构建、校验、源码修改、版本管理和显式发布，得到可实际操作和继续迭代的商品目录站。

本项目受 [Atoms](https://atoms.dev/) 启发，但采用独立的产品与技术设计。它延续多角色协作的产品表达，不复用 Atoms 的源代码、私有 Prompt 或内部基础设施，也不是 Atoms 的复刻或分支。

- **当前范围：** V1 只支持受控的商品展示和商品目录站，包括 Home、Catalog、Product 页面；不宣称可以生成任意应用。

- **模型接入：** 后端已实现 Ollama Cloud 和确定性 Mock Provider。真实模型默认配置为 DeepSeek V4 Pro，也允许选择 V4 Flash；真实网络调用仍需完成最终验收。

- **本地状态：** Lead 路由、固定专业团队、风险审批、Session Gateway、用户隔离、Project Git、版本、发布路由和 Sandbox Gateway 已有本地实现与自动化测试。

- **线上状态：** Railway 公网部署和目标 Linux Sandbox Host 的实机安全验收尚未完成，因此当前没有可交付的在线 Demo 地址。

## 2. 当前边界摘要

> **Agent 边界：** Lead 对每条消息只做 `direct/team` 二选一路由；`team` 固定执行 Product Manager → Architect → Engineer → Data Analyst。`supported` Blueprint 在受控范围和基础预算内自动继续，`adapted` 或新增风险才请求确认。动态角色子集、局部并行、返工仲裁和独立 Agent Context 属于 V2。
>
> **工程边界：** V1 Control Plane 只面向本地单实例或 Railway 单副本，使用进程内调度、单 Worker 和 PostgreSQL 持久化检查点。浏览器通过统一 Gateway 访问 Control Plane；Vim/Terminal 代理到独立 Linux Sandbox Host。
>
> **安全边界：** 生产身份来自用户名密码和服务端 Session Cookie，不接受客户端自报 `user_id`；`X-User-ID` 只在测试环境保留。Project、Run、Preview、Git 和 Sandbox Session 都绑定当前用户。
>
> **交付边界：** Build、Edit、Vim Save 和 Restore 形成新的 ProjectVersion 与 Git commit，但不会自动改变线上发布指针。Publish、Update 和 Unpublish 必须由用户显式触发。

## 3. 版本规划

| 版本 | 产品目标 | Agent 组织方式 | 当前状态 |
| --- | --- | --- | --- |
| **V1** | 交付有登录隔离、代码归属、可恢复版本和公开分享能力的完整链路 | Lead 选择 `direct`，或调用完整的 Product Manager → Architect → Engineer → Data Analyst 团队 | 本地纵切已实现；Linux Sandbox 与 Railway 待实机验收 |
| **V2** | 增加动态任务图、角色子集、局部并行、结构化返工和仲裁 | Lead 在 Runtime 约束下动态协调 Product Manager、Architect、Engineer、Data Analyst | 已完成产品、架构与 Agent 设计，待 V1 验收后实施 |

- **实施顺序：** 项目按 V1 → V2 推进。V1 是当前实现与验收基线，V2 是明确计划实施的下一版本，不是泛化的远期愿景。

- **角色延续：** V2 不新增没有定义的展示型角色，而是升级 Lead 的协调能力，并让现有四个专业 Agent 按真实依赖执行。

- **详细设计：** V1 的具体取舍见 [`docs/v1/`](./docs/v1/)，V2 的 TaskGraph、Context、Tool、Sandbox 和预算设计见 [`docs/v2/`](./docs/v2/)。

## 4. V1 用户体验

- **登录与隔离：** 用户通过用户名密码登录；切换账号后，只能看到当前账号拥有的 Project、Run、Preview、版本和 Sandbox Session。

- **对话与路由：** 用户始终从 Lead 入口表达需求。询问、能力确认或澄清走 `direct`；明确构建请求走 `team`，用户也可以主动选择 Call team。

- **范围与确认：** Product Manager 将请求整理成 Blueprint。`supported` 工作自动进入固定团队，`adapted` 会展示映射和省略内容并等待确认，`unsupported` 在构建前停止。

- **设计与实现：** Architect 产生 ArchitectureSpec，Engineer 产生 AppSpec；确定性 Renderer 和 Validator 负责真正构建与校验，不执行模型临时生成的 Shell 命令。

- **质量解释：** ValidationReport 保存不可由 Agent 改写的工程证据，Data Analyst 基于 AppSpec 和校验结果生成 DataReview，不把失败检查解释成成功。

- **预览与修改：** 用户可以实际操作 Home、Catalog、Product 页面，通过结构化 Edit 或 xterm.js + restricted Vim 修改当前 Project 的 `app-spec.json`。

- **版本与恢复：** Build、Edit、Vim Save 和 Restore 都创建新的 ProjectVersion 与 Git commit；Restore 只新增恢复版本，不删除或重写历史。

- **发布与分享：** 用户选择一个 ProjectVersion 后显式 Publish 或 Update；公开 URL 只读取已确认的发布指针，新工作版本不会自动上线。

## 5. V1 能力地图

```text
产品链路：Login -> Lead direct | team -> Blueprint -> Build -> Preview

协作链路：Product Manager -> Architect -> Engineer -> Data Analyst
              |                 |            |              |
          Blueprint    ArchitectureSpec   AppSpec       DataReview

源码链路：Project -> local Git -> Sandbox worktree -> Vim Save -> commit

版本链路：Build / Edit / Restore -> ProjectVersion -> explicit Publish -> Public URL

保障链路：Session isolation | Quota | Job recovery | Validation | Audit events
```

- **可检查：** Blueprint、ArchitectureSpec、AppSpec、ValidationReport 和 DataReview 都是持久化 Contract，不依赖不可见的 Agent 私有推理解释结果。

- **可操作：** Preview 是可交互页面，不是静态截图；Studio 中可见的构建、编辑、版本、恢复和发布控件都对应真实后端行为。

- **可恢复：** Run、Job、Artifact、配额和版本状态持久化；刷新或 Worker 重启不会要求用户从头重新生成已完成阶段。

- **可归属：** 每个 Project 绑定当前用户和一个服务端本地 Git 仓库，每个保存版本都能定位到 commit。

- **可控制：** LLM 只能提交结构化决策；身份、配额、状态推进、仓库写入、Sandbox 和发布权限由 Runtime 掌握。

## 6. 设计亮点与关键取舍

Another Atom 的核心不是让多个 Agent 同时说话，而是把多角色协作、结构化 Context、风险驱动的人机协同、源码归属、版本恢复和隔离执行组合成一条可检查、可控制、可交付的产品链。本章描述最终产品应长期保持的设计原则；V1 因范围和部署条件做出的暂时收敛，放在下一章单独说明。

### 6.1 多角色协作由职责和产物证明

Another Atom 延续 Atoms 的多角色产品表达，但不把角色价值建立在头像、状态动画或聊天消息数量上。每个角色负责消除一种不同的不确定性，并用正式产物完成交接。

- **Lead：** 判断用户是在询问/澄清，还是明确要求系统执行；进入执行后负责协调建议，不直接拥有文件、Shell 或发布权限。

- **Product Manager：** 将用户目标映射为 Blueprint，明确支持范围、页面、模块、视觉方向、映射需求和省略需求。

- **Architect：** 将 Blueprint 转换为 ArchitectureSpec，定义路由、数据实体、视觉 Token 和 Renderer 边界。

- **Engineer：** 将已确认的产品与架构 Contract 转换为 AppSpec，并对真实构建和校验证据负责。

- **Data Analyst：** 检查数据完整性并解释 ValidationReport，不取代确定性工程校验，也不设置独立 Designer 或 QA 展示角色。

- **关键取舍：** 角色数量服从职责边界，不为制造“多 Agent 感”增加角色。新增角色必须回答它消除了哪类独立不确定性，以及交付什么可验证 Contract。

### 6.2 Context 通过结构化 Contract 交接

```text
User message -> LeadDecision -> Blueprint -> ArchitectureSpec -> AppSpec
                                                   |             |
                                                   `-> ValidationReport -> DataReview
                                                                          |
                                                                          v
                                                                    ProjectVersion
```

Agent Context 不是一段无限增长的共享聊天记录。Runtime 根据当前角色和任务组装最小输入，并通过版本化 Artifact、Evidence 和 Handoff 传递必要信息。

- **显式输入：** 每个阶段只接收当前任务需要的上游 Contract、用户确认事实、Evidence 和预算摘要，避免无关历史污染判断。

- **显式输出：** Agent 输出必须通过 Pydantic Schema 校验后才能持久化、进入下一阶段或触发 ToolRequest。

- **错误归因：** 结构化交接可以区分问题来自需求映射、架构边界、实现结果、Renderer 还是数据解释，而不是把所有失败归为“模型没做好”。

- **恢复能力：** 已提交 Artifact 是恢复检查点；Worker 重启时复用已完成阶段，不依赖恢复某个进程内对话对象。

- **关键取舍：** Context 追求最小、可审计和可重建，而不是最大化信息量。长期记忆只有在具备来源、裁剪、保留和删除规则后才进入 Runtime。

### 6.3 Human-in-the-loop 按风险变化介入

用户明确要求 Build，已经授权系统在受控商品目录范围和基础预算内完成一次构建。因此正常工作不应在每个中间 Artifact 上重复请求确认。

```text
User message -> LeadDecision
                 |-- direct -> answer / clarify
                 `-- team -> Product Manager -> Blueprint -> Risk Policy
                                                       |-- supported + base budget -> continue
                                                       `-- adapted / new risk -> Approval
```

- **正常直通：** `supported` Blueprint 保持在受控商品目录范围和基础预算内，生成后自动进入后续团队，不再重复询问用户是否开始构建。

- **风险确认：** `adapted`、额外预算、后续范围变化、破坏性源码操作、版本发布指针变化和公开访问变化需要用户确认。

- **Contract 保留：** Blueprint 仍然持久化、可检查并参与后续 Validator，只是不再充当所有构建的统一审批门。

- **纠偏窗口：** 取消固定 Gate 会失去默认的“构建前编辑 Blueprint”停顿；系统用 Artifact Inspector、Follow-up、Edit 和新版本承接后续纠偏。

- **关键取舍：** Human-in-the-loop 应匹配不可逆性、成本扩大和授权变化，而不是匹配 Agent 阶段数量。

### 6.4 Artifact、Git、版本和发布指针相互分离

```text
Agent Artifact -> editable source -> Git commit -> ProjectVersion -> Publish pointer
```

模型运行成功、源码已经保存、平台形成版本和用户决定上线，是四个不同事实，不能用一个 `completed` 状态替代。

- **源码事实：** Project Repository 保存可编辑源码 Contract；当前受控 Renderer 使用 `app-spec.json` 作为 Project 的事实源。

- **版本事实：** Build、Edit、Vim Save 和 Restore 都创建新的 Git commit 与 ProjectVersion，数据库版本保存对应 commit SHA。

- **恢复事实：** Restore 从目标历史版本创建新的恢复 commit，不执行 `git reset`，也不删除后续历史。

- **发布事实：** 新 ProjectVersion 只更新工作版本；线上版本必须通过显式 Publish/Update 改变，Agent 和 Restore 都不能自动发布。

- **关键取舍：** 可追溯性和可恢复性优先于“永远自动最新”。工作版本与公开版本允许不同步，但这种差异必须在界面中可见。

### 6.5 统一 Gateway 隔离可信控制面与不可信执行面

浏览器只连接一个 HTTPS/WSS Gateway，但统一入口不意味着所有能力运行在同一权限边界。身份和业务状态属于可信 Control Plane，文件修改和构建属于独立 Sandbox Runtime。

- **统一入口：** REST、SSE、Preview、Public Route 和 Terminal WebSocket 都从同一产品域名进入，浏览器不直接获得 Sandbox Host 地址、内部 token 或宿主机路径。

- **可信控制面：** Session、资源归属、Risk Policy、配额事务、Job 状态、Repository commit 和 Publish pointer 由 Control Plane 管理。

- **隔离执行面：** Sandbox 只接收当前 User/Project/Task 的最小输入，在临时 worktree 或快照中运行固定 Tool，不获得平台数据库凭证和 Provider 密钥。

- **受限 WebIDE：** xterm.js 连接 restricted Vim，而不是登录 Shell；Sandbox 隐藏 `.git`，禁止网络，使用非 root 用户、只读根文件系统、默认 seccomp、丢弃 capabilities 和资源/时限约束。

- **关键取舍：** 统一产品体验与执行隔离同时成立。不能为了减少部署组件，把不可信 Tool 放回 Web/API 进程。

### 6.6 可恢复 Runtime 是产品 Contract

用户看到的进度、额度、版本和错误必须对应可持久化事实。无论 Runtime 以后是单实例还是多 Worker，这组不变量都不能改变。

- **状态推进：** Run、Task、Job 和 Approval 使用受约束状态转换；并发请求不能绕过前置状态或重复创建业务副作用。

- **幂等恢复：** 已提交 Artifact、结算和版本在重试时复用；恢复只继续未完成工作，不重复生成 Build Version 或移动发布指针。

- **配额事务：** Provider 调用前预占额度，调用后按实际请求和 token 结算，未发生的阶段和未使用预占必须释放。

- **失败收敛：** LLM、平台、Worker、Sandbox 和 Validator 失败都必须留下明确状态、Evidence 和可执行出口，不能显示虚假进度。

- **确定性证据：** Validator 检查 Blueprint 页面覆盖、mapped requirement 证据、ArchitectureSpec/AppSpec 视觉 Token、一致性和颜色对比度；Agent 不能修改失败结果。

- **关键取舍：** 先定义可恢复、可结算、可审计的不变量，再选择单实例、队列或多 Worker 的具体部署方式。

## 7. V1 边界与演进取舍

V1 的目标是用最小实现证明完整产品闭环，不提前引入只有在水平扩展或自主多 Agent 下才需要的复杂度。这里记录的是版本取舍，不是最终架构的长期限制。

### 7.1 Agent 取舍

- **固定完整团队：** 每个 `team` 请求按 Product Manager → Architect → Engineer → Data Analyst 顺序执行，不根据任务动态删除或增加角色。V1 先验证专业 Contract 是否真正改善结果，V2 再引入角色子集。

- **固定顺序执行：** V1 不并行执行 Agent，也不允许多个角色共享可写工作区。这样减少部分失败、并发配额和 Artifact 合并变量；V2 只对无依赖、无共享写入的节点开启局部并行。

- **阶段级 Context：** V1 Runtime 按阶段组装 Blueprint、ArchitectureSpec、AppSpec 等最小输入，不实现独立 Agent 长期记忆。V2 将阶段 Context 升级为 Task Context 和 Handoff Package。

- **Runtime 控制返工：** V1 使用固定状态机、重试上限和失败出口，不让 Lead 自主修改流程或无限返工。V2 允许 Lead 提交返工和仲裁建议，但最终规则仍由 Runtime 校验。

- **受控生成范围：** V1 只生成商品目录 AppSpec，LLM 不能安装依赖、修改构建命令、执行 Shell 或自动发布。扩大技术栈前必须同步扩充 Renderer、Validator、Tool Policy 和 Sandbox 验收。

### 7.2 工程取舍

- **单副本 Control Plane：** V1 只面向本地单实例或 Railway 单 Pod，所以不实现 API/Worker 水平副本、跨实例分布式锁或 lease-owner fencing。需要水平扩展时，再按 V2 架构拆分服务身份和并发控制。

- **进程内调度：** Blueprint 和 Build 由进程内任务与单 Worker 调度，持久化 Job/Lease 负责恢复；V1 不引入独立消息队列或 PostgreSQL LISTEN/NOTIFY。

- **数据库轮询事件：** SSE 复用一个读取 Session 轮询持久化事件，避免为单副本引入消息总线。多实例事件广播属于部署扩展问题，不改变 Event Contract。

- **服务端 Session：** V1 使用用户名密码、随机 Session、HttpOnly/SameSite Cookie 和用户级 Project 隔离，不实现 JWT/OAuth、Organization、Membership 或共享 Project 权限。

- **服务端 local Git：** V1 一 Project 一仓库并映射 commit/version，不实现 GitHub/GitLab OAuth、remote、push/pull、SSH key 或操作用户电脑仓库。

- **独立 Sandbox Host：** V1 按编辑会话创建临时 worktree 和 restricted Vim 容器，不实现多租户 Sandbox 池、容量调度或 MicroVM。rootless Runtime、磁盘限制和逃逸路径仍需在目标 Linux Host 实机验收。

- **应用内配额：** V1 记录 Provider 请求和 token 并防止并发透支，不实现 Stripe、Wallet、充值、发票；Edit/Restore 的独立计费策略等真实使用数据后再决定。

## 8. V2 目标与演进取舍

V2 是 V1 验收后的下一实施版本。它不推翻 V1 的 Session、Project、Git、Artifact、Risk Policy 和 Sandbox Contract，而是在同一基础上增加受 Runtime 约束的自主多 Agent 协作。

### 8.1 Agent 演进

- **动态 TaskGraph：** Lead 从 `direct/team` 二选一路由升级为 TaskGraph 协调者，提交任务、依赖、角色、并行组和预算建议；Runtime 拒绝环、未知角色和越权计划。

- **角色子集：** Product Manager、Architect、Engineer、Data Analyst 根据实际 TaskGraph 参与，不要求每个任务机械运行完整团队。

- **独立 Context：** 每个 Agent 只接收当前 Task 所需的 Artifact、Evidence、Tool Observation 和预算摘要，通过 Handoff Package 传递结果，不共享隐藏记忆或 Chain of Thought。

- **选择性并行：** Runtime 只并行执行无依赖冲突、无共享写入且预算已原子预留的节点；首条目标路径是 Architect 与 Data Analyst 的独立数据准备工作。

- **结构化返工：** Handoff 可以基于 Contract 和 Evidence 拒收，Lead 可以建议返工目标和仲裁方案；Runtime 负责预算、次数、状态收敛和最终执行决定。

- **受控 Tool：** Agent 只提交 ToolRequest，不直接执行工具。Tool Gateway 校验角色、参数、路径、网络、预算和 Sandbox，再返回可审计 ToolResult。

- **关键取舍：** V2 的自主性来自可验证 TaskGraph、Handoff 和 Tool，而不是放宽 Runtime 权限。没有真实数据前，不预设多 Agent 一定更快或成功率更高。

### 8.2 工程演进

- **服务拆分：** Web/Control Plane 只处理身份、命令、状态和事件；独立 Agent Worker 负责模型调用与 Task 生命周期，Sandbox Provider 执行文件和构建 Tool。

- **持久化调度：** V2 初期继续使用 PostgreSQL Task/Lease 和独立 Worker Service，不额外引入消息队列；Task、预算和幂等保持在同一事务边界。

- **共享 Artifact Storage：** S3-compatible Object Storage 保存多 Worker 共享的不可变输入、Patch、BuildArtifact、Evidence 和发布快照，不依赖单实例 Volume。

- **任务级 Sandbox：** Engineer Task 使用独立可写快照，Data Analyst 使用相应只读视图；具体采用强化容器、MicroVM 或远程 Sandbox Provider 由 ADR 和隔离测试决定。

- **并行预算：** 父 RunBudget 在启动 ready group 前原子预留子任务总额度；部分失败保留已接受 Artifact，释放未启动和未使用预算。

- **多 Worker 恢复：** Task lease、attempt、idempotency key 和 Evidence 防止重复副作用；Web、Agent Worker 和 Sandbox 使用不同服务身份与最小权限。

- **关键取舍：** V2 增加并行能力，同时接受配额事务、部分失败、资源峰值和部署成本上升；是否继续扩展并行度由压测与真实成本数据决定。

- **详细设计：** 产品目标见 [V2 PRD](./docs/v2/another-atom-v2-prd.md)，组件与调度见 [V2 架构设计](./docs/v2/architecture-design.md)，角色、Context、Handoff 和 Tool 行为见 [V2 Agent 设计](./docs/v2/agent-design.md)。

## 9. 技术设计

本章描述 Another Atom 的最终逻辑架构，不等同于当前 V1 的单实例部署。V1 和 V2 都实现这套 Contract 的不同子集，具体裁剪分别记录在 `docs/v1/` 和 `docs/v2/`。

### 9.1 整体逻辑架构

```text
User Browser
  React Studio / Preview / xterm.js
                    |
                 HTTPS/WSS
                    v
+-----------------------------------------------------------+
| Unified Gateway / Control Plane                           |
| Session + Authorization | Lead + Risk Policy              |
| Project + Version + Publish | Event + Quota + Audit       |
| Context + Artifact + Repository | Durable Scheduler       |
+---------------------------+-------------------------------+
                            |
          +-----------------+-------------------+
          |                 |                   |
          v                 v                   v
     PostgreSQL       Artifact Storage      LLM Providers
  state/lease/budget   evidence/release      structured calls
          |
          v
   Agent Worker Service
          |
          v
      Tool Gateway
          |
          v
   Sandbox Provider / Workers
  worktree/snapshot/build/test/vim
```

- **Control Plane：** 维护可信身份、资源归属、状态命令、Risk Policy、配额、版本和发布指针，不执行不可信文件 Tool。

- **Durable Scheduler：** 持久化 Run、Task、Job、Lease、Attempt、Approval 和 Budget，决定哪些工作可以开始、恢复或停止。

- **Agent Worker：** 为角色组装最小 Context、调用模型、校验结构化输出并保存 Artifact；不直接绕过 Tool Gateway 操作宿主机。

- **Repository Service：** 维护 Project 源码历史、commit/version 映射和受控 worktree，不把宿主机仓库路径暴露给浏览器或模型。

- **Artifact Storage：** 保存不可变输入、Evidence、Patch、BuildArtifact 和发布快照；V1 可使用单实例持久化存储，V2 使用共享对象存储实现多 Worker 访问。

- **Tool Gateway：** 根据 User、Project、Run、Task、Agent role、Capability、路径、网络和预算校验 ToolRequest，再为 Sandbox 签发最小临时能力。

- **Sandbox Provider：** 提供文件系统、Build、Test、Browser 或 Vim 的隔离执行环境；Sandbox 无权改变业务状态和发布指针。

### 9.2 Agent 与 Runtime 执行链

```text
User Message
    |
    v
LeadDecision ---- direct ----> Answer / Clarification
    |
   team
    v
Blueprint -> Risk Policy -> TaskGraph / Fixed Pipeline
                              |
                              v
                  Agent Context + Artifact Handoff
                              |
                              v
                    ToolRequest -> Sandbox
                              |
                              v
                Validation + Evidence + DataReview
                              |
                              v
                   Git commit + ProjectVersion
                              |
                     explicit Publish/Update
                              |
                              v
                         Public Route
```

- **规划与执行分离：** Lead 可以建议 direct、team 或 TaskGraph，但 Runtime 校验角色、依赖、预算、Approval 和 Tool 权限。

- **模型与证据分离：** Agent 产生结构化判断，Renderer、Test、Validator 和 ToolResult 提供不可由模型自行改写的执行证据。

- **工作与发布分离：** Agent Run 和 ProjectVersion 可以持续推进，Public Route 只响应用户最后一次明确确认的发布指针。

### 9.3 部署与分享架构

这里区分两件事：开发者部署 Another Atom 平台；用户在平台内发布和分享某个 ProjectVersion。前者创建可信服务边界，后者只改变产品内发布指针。

```text
平台部署

Developer -- git push --> GitHub
                           |
                +----------+-----------+
                |                      |
                v                      v
        Control Plane             Agent Workers
        Railway / Linux           Railway / Linux
                |                      |
                +----------+-----------+
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
     PostgreSQL      Artifact Storage   Sandbox Provider
                                           Linux Host
                           |
                           v
                      LLM Provider

用户访问与分享

Browser -- HTTPS/WSS --> Unified Gateway
                              |
               +--------------+--------------+
               |                             |
               v                             v
        Authenticated Studio          Published Route
        Project / Edit / Vim          selected Version
               |                             |
               `-- explicit Publish ---------'
                                             |
                                             v
                                      Stable Public URL
```

- **统一公网入口：** Browser 只访问 Control Plane 的 HTTPS/WSS 域名；Agent Worker、数据库、对象存储和 Sandbox Provider 不直接向终端用户公开。

- **部署边界：** Railway 可以承载 Control Plane 和 Agent Worker，但真实 Sandbox 需要支持 rootless container、namespace、cgroup 和网络策略的 Linux Host 或等价远程 Provider。

- **分享边界：** Public Route 只读取已发布版本，不开放 Project Repository、Agent Context、内部 Event、配额或 Sandbox Session。

- **版本实现：** V1 可将 Control Plane 与 Worker 合并为单实例，并用本地持久化 Git；V2 按最终架构拆分 Agent Worker、Artifact Storage 和 Sandbox Provider。

## 10. 当前实现状态

状态只对应计划交付的核心能力，不重复列文档、评估材料或装饰性工作。

### 10.1 Agent

| 关键词 | 状态 | 详情与证据 |
| --- | --- | --- |
| **真实 LLM Provider** | 部分完成 | Ollama Cloud 结构化调用、模型 allowlist、token 用量和修复重试已实现并有 Mock HTTP 单测；真实网络调用待最终确认 |
| **Lead `direct/team`** | 已完成 | 能力询问走 direct 且不创建 Project；明确 Build 走 team；结果和用量持久化 |
| **风险驱动 Approval** | 已完成 | supported 自动创建 BuildJob 且无 Approval；adapted 进入 awaiting_approval；并发确认由状态 CAS 和唯一约束保护 |
| **固定专业团队** | 已完成 | Product Manager、Architect、Engineer、Data Analyst 依次生成结构化 Artifact |
| **Contract Validator** | 已完成 | 校验页面覆盖、mapped requirement 证据、视觉 Token、一致性和颜色对比度 |
| **V2 TaskGraph Runtime** | 待实施 | PRD、架构和 Agent 设计已完成；动态角色、并行、Handoff、ToolRequest、返工和仲裁尚未进入代码 |

### 10.2 工程

| 关键词 | 状态 | 详情与证据 |
| --- | --- | --- |
| **Session Gateway** | 已完成 | 用户名密码、PBKDF2 哈希、随机服务端 Session、HttpOnly/SameSite Cookie 和 Logout 已实现 |
| **用户级隔离** | 已完成 | Project、Run、Preview 和 Sandbox Session 按当前用户校验；双用户集成测试通过 |
| **Project Git** | 已完成 | 创建 Project 时初始化服务端仓库；Build、Edit、Vim Save、Restore 映射独立 commit SHA |
| **版本与发布分离** | 已完成 | 新版本和 Restore 不自动移动线上指针；Publish/Update 由显式接口执行 |
| **恢复与配额** | 已完成 | Blueprint 后台恢复、Job Lease、阶段 Artifact 复用、实际用量结算、剩余预占释放和并发 Approval 测试通过 |
| **xterm.js + Sandbox Gateway** | 部分完成 | Studio、Control Plane WSS 代理、独立 Sandbox Host、restricted Vim 镜像和保存版本链已实现；Linux 实机隔离待验收 |
| **自动化测试** | 已完成 | 当前后端单元/集成测试 47 项通过，包含 Golden Path、反路径、恢复、并发、身份、Git 和 Sandbox 保存 |
| **Railway 公网部署** | 待完成 | Dockerfile 和 Railway 配置已存在，尚无 PostgreSQL/持久化存储环境下完成验收的公网地址 |

## 11. 后续验收目标

这里只列仍准备完成的目标，不重复已经通过的能力，也不写通用评估维度。

### 11.1 Agent

- **真实 Lead 调用｜待完成：** 使用 `.env` 中配置的 Ollama Cloud 凭证执行最小真实请求，确认模型、结构化 LeadDecision 和 token 用量，不输出密钥。

- **真实范围分类｜待完成：** 分别验证真实模型对 supported、adapted、unsupported 请求的 Blueprint 分类与 Risk Policy 状态推进。

- **真实固定团队｜待完成：** 使用真实模型完成一次 Product Manager → Architect → Engineer → Data Analyst 全链路，并核对每阶段 Artifact、Usage Ledger 和最终版本。

- **V2 实施入口｜V1 后开始：** 先实现持久化 TaskGraph、Task、Handoff、RunBudget 和顺序多 Agent，再开启第一条可证明的局部并行路径。

### 11.2 工程

- **Linux Sandbox｜待完成：** 在目标 Linux Host 构建镜像，验证 rootless Runtime、禁网、只读根文件系统、capability/seccomp、CPU/内存/PID/时限和 worktree 清理。

- **Sandbox 安全｜待完成：** 验证跨用户、跨 Project、`.git`、Secret、宿主网络和容器 Runtime 的不可访问性，并确认异常销毁不会遗留可复用环境。

- **Railway 部署｜待完成：** 部署 Control Plane、PostgreSQL 和持久化存储，配置真实 Provider 与 Sandbox Host，记录资源规格和必要环境变量。

- **重启恢复｜待完成：** 在部署环境验证 Blueprint、Build Job、阶段 Artifact、配额和 ProjectVersion 在进程重启后的幂等恢复。

- **浏览器验收｜待完成：** 从两个干净账号验证 Project 隔离，再从无登录浏览器打开明确发布的 Public URL。

- **剩余 V1 交互｜待完成：** 完成 Resolve、项目重命名/删除和附件文件实际上传；所有新增入口同步补 owner 校验、状态、错误和自动化测试。

## 12. 相关链接

- **源码仓库：** [github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)

- **在线版本：** 尚未部署；完成 Railway 和 Sandbox 实机验收后补充公开地址。

- **V1 产品：** [V1 产品需求](./docs/v1/another-atom-v1-prd.md)

- **V1 工程：** [V1 架构设计](./docs/v1/architecture-design.md)

- **V1 Agent：** [V1 Agent 设计](./docs/v1/agent-design.md)

- **V1 部署：** [本地运行与 Railway 部署说明](./docs/v1/local-run-and-railway-deployment.md)

- **V1 Review：** [V1 实现 Review](./review/2026-07-11-v1-implementation-review.md)

- **V2 产品：** [V2 产品需求](./docs/v2/another-atom-v2-prd.md)

- **V2 工程：** [V2 架构设计](./docs/v2/architecture-design.md)

- **V2 Agent：** [V2 Agent 设计](./docs/v2/agent-design.md)

- **参考分析：** [Atoms 参考分析](./docs/reference/atoms-reference-analysis.md)
