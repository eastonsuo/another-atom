# Another Atom V1 Agent 运行机制

[toc]

- 文档状态：V1 实施基线
- 更新日期：2026-07-13
- 产品设计：[Another Atom V1 产品范围与交互](../../产品设计/01-产品范围与交互.md)
- 工程设计：[Another Atom V1 系统架构](../工程/01-系统架构.md)
- 当前实现：[Another Atom V1 关键设计与实现 Review](../../../../review/V1/综合评审/2026-07-12-关键设计与实现检查.md)
- 整体产品：[Another Atom 整体产品目标与定位](../../../整体/产品设计/01-整体产品目标与定位.md)
- 问题整理：[多角色 Agent 设计问题整理](../../../../review/V1/Agent评审/2026-07-13-多角色Agent设计问题整理.md)
- 演进讨论：[Agent Runtime 边界与演进讨论](../../../../review/整体/Agent评审/2026-07-12-Agent-Runtime边界与演进讨论.md)
- V2 演进：[Another Atom V2 Agent 运行机制](../../../V2/技术设计/Agent/01-Agent运行机制.md)

## 1. 设计结论

V1 采用 **Lead 二选一路由 + Contract-first 固定团队**，不是经典 ReAct，也不是开放式 Autonomous Agent。

```text
用户消息
   |
   v
Lead Agent -> LeadDecision(route=direct|team)
   |
   +-- direct -> 回答或澄清，不启动团队
   |
   `-- team -> Product Manager -> Architect -> Engineer -> Data Analyst
                                                        |
                                                        v
                                     Runtime Build / Validator -> Reviewer
```

四种范式的区别：

| 范式 | V1 是否采用 | 原因 |
| --- | --- | --- |
| ReAct：模型循环执行 Action -> Observation -> Action | 否 | V1 不向模型开放 Shell、文件、构建或发布 Tool，不需要开放式工具循环 |
| 开放式 Plan-and-Execute | 否 | Lead 不能自由创建任务图、选择任意角色、决定权限、重试次数或发布 |
| Lead 二选一路由 | 是 | Lead 只决定直接回答/澄清，或调用完整固定团队；用户可以覆盖为“调用团队” |
| Contract-first Plan -> Execute -> Validate | 是 | 团队产生显式产物，平台按固定状态机执行，Validator 决定确定性结果 |

V1 把一次构建拆成三个边界清楚的步骤：

- **[Plan｜逐步明确做什么]** Product Manager 先用 Blueprint 定义产品范围，Architect 再用 ArchitectureSpec 明确页面、状态和视觉约束，Engineer 最后用 AppSpec 给出可执行源码。它不是由 Lead 一次生成完整任务图，而是三个专业角色逐层把需求收敛成代码。
- **[Execute｜平台执行已确认方案]** Agent 只提交结构化产物，不直接运行 Shell、修改宿主文件或发布。Runtime 负责保存 Artifact、写入 Project 源码、创建 Build Job，并在受控环境中完成构建。
- **[Analyze｜先明确数据事实]** Data Analyst 读取 Blueprint、ArchitectureSpec 和 AppSpec，整理应用使用的结构化数据、内容记录和浏览器本地状态，输出 DataProfile。它不负责代码验收，也不能把自己的观察写成工程通过结论。
- **[Validate｜工程证据由平台生成]** 确定性 Validator 检查源码、页面交接、能力边界和视觉约束，产生不可由模型改写的 ValidationReport。
- **[Review｜独立复核是否可交付]** Reviewer 同时读取需求、架构、实现、DataProfile 和 ValidationReport，检查交付是否一致并输出 ReviewReport。Reviewer 可以要求返工或补充输入，但不能覆盖 Validator 的失败证据。

## 2. V1 角色与 Contract

本节以当前 [Pydantic Schema](../../../../../another_atom/contracts/schemas.py) 和 [Provider 接口](../../../../../another_atom/agent/provider.py) 为硬 Contract。字段长度、枚举和数量限制来自代码；角色应做什么、不得做什么属于语义约束，由 Prompt、Orchestrator、Risk Policy 和 Validator 共同执行。

### 2.1 固定团队总览

| 角色/阶段 | 要回答的核心问题 | 当前实际输入 | 结构化输出 | 持久化位置 |
| --- | --- | --- | --- | --- |
| Lead | 用户是在询问，还是明确要求构建？ | `message`、`force_team` | `LeadDecision` | `LeadMessage` |
| Product Manager | 在 V1 能力范围内，具体要构建什么？ | `Run.prompt`、`Run.mode` | `Blueprint` | Blueprint Artifact |
| Architect | 如何把 Blueprint 落成受控浏览器架构？ | `Blueprint` | `ArchitectureSpec` | ArchitectureSpec Artifact |
| Engineer | 需要生成哪些页面元数据和可运行源码？ | 原始 Prompt、`Blueprint`、`ArchitectureSpec` | `AppSpec` | AppSpec Artifact |
| Data Analyst | 应用包含哪些数据、内容和本地状态，是否存在明显缺口？ | Prompt、`Blueprint`、`ArchitectureSpec`、`AppSpec` | `DataProfile` | DataProfile Artifact |
| Runtime Validator | AppSpec 是否符合范围、交接和源码安全规则？ | Prompt、Blueprint、ArchitectureSpec、AppSpec | `ValidationReport` | ValidationReport Artifact |
| Reviewer | 需求、架构、数据、实现和确定性证据是否一致，是否可以交付？ | Prompt、Blueprint、ArchitectureSpec、AppSpec、DataProfile、ValidationReport | `ReviewReport` | ReviewReport Artifact |

Lead 只决定是否进入团队；进入 `team` 后角色和顺序固定，不由 Lead 自由选择。Runtime Validator 不是 Agent，它位于 Data Analyst 与 Reviewer 之间：先固定工程事实，再让 Reviewer 基于完整证据做独立复核。

### 2.2 Lead：区分询问与明确构建

**职责：** Lead 是用户入口，只判断本条消息走 `direct` 还是 `team`。`direct` 返回回答或澄清；`team` 表示进入完整固定团队。它不生成 Blueprint，不选择专业角色，不执行 Tool，也不改变 Project、版本或发布状态。

**当前输入 Contract：**

| 字段 | 类型与硬约束 | 含义 |
| --- | --- | --- |
| `message` | `str`，去空白后 1–4000 字符 | 用户本条原始消息 |
| `force_team` | `bool`，默认 `false` | 用户显式选择“调用团队”；为 `true` 时直接覆盖模型路由 |
| `model` | 可选 `str`，1–100 字符 | 选择允许的 Provider 模型；它用于运行配置，不作为 LeadDecision 字段 |

当前实现没有把 Project 摘要、历史对话、能力边界或预算摘要传给 Lead。因而 Lead 只能判断当前消息，不能声称自己已经理解完整 Project Context；Project 对话线程完成后才扩展这一输入。

**输出 `LeadDecision`：**

| 字段 | 类型与硬约束 | 语义 |
| --- | --- | --- |
| `route` | `direct \| team` | 唯一路由决定 |
| `response` | `str`，1–800 字符 | 展示给用户的回答、澄清或团队交接说明 |
| `reason` | `str`，1–300 字符 | 可展示、可审计的简短路由依据，不是 Chain of Thought |

API 返回的 `LeadDecisionView` 额外包含 `message_id`、实际 `model` 和可选 `fallback_provider`。原文曾列出的 `intent_summary`、`risk_flags`、`estimated_provider_calls` 和 `clarification_question` 不在当前 Schema 中，不能作为已实现字段引用。

### 2.3 Product Manager：把请求整理成可检查 Blueprint

**职责：** Product Manager 保留用户目标，把 Prompt 整理成页面、模块、视觉和数据要求，并提出 `supported / adapted / unsupported` 范围判断。LLM 只提出 Blueprint；Risk Policy 和 Runtime 决定是否自动继续、请求确认或停止。

**当前实际输入：** `Run.prompt` 和 `Run.mode`。当前 Provider 尚未接收附件元数据、Project 历史或已存在源码，因此不能在 Blueprint 中声称检查过这些内容。

**输出 `Blueprint`：**

| 字段 | 类型与硬约束 | 语义 |
| --- | --- | --- |
| `schema_version` | 固定 `"1.0"` | Contract 版本 |
| `project_name` | `str`，1–80 字符 | 用户可识别的 Project 名称 |
| `product_type` | `str`，1–80 字符，默认 `web_application` | 产品类型标签；该字段本身不扩大 V1 验收范围 |
| `support_level` | `supported \| adapted \| unsupported` | 当前能力匹配结论 |
| `support_reasons` | `list[str]`，最多 8 项 | 范围结论的可展示依据 |
| `mapped_requirements` | `list[str]`，最多 12 项 | 已映射到受控实现的用户要求 |
| `omitted_requirements` | `list[str]`，最多 12 项 | 当前实现明确不包含的要求 |
| `rewrite_suggestion` | 可选 `str`，最多 500 字符 | 需要用户确认的替代草案；不能只写“请重新描述” |
| `capability_policy_version` | `catalog-v1 \| web-v1`，默认 `web-v1` | 生成 Blueprint 时依据的能力策略版本 |
| `pages` | `list[str]`，1–12 项，禁止空标签 | 页面或主要界面 |
| `modules` | `list[str]`，1–20 项，禁止空标签 | 功能模块与关键交互 |
| `visual_direction` | `str`，1–240 字符 | 可供 Architect 使用的视觉方向 |
| `data_requirements` | `list[str]`，最多 8 项 | 页面需要的数据或本地状态要求 |

`support_level` 的语义：

- `supported`：在当前 V1 受控范围与基础预算内可以继续。
- `adapted`：保留产品目标，但必须删减或演示化真实认证、支付、数据库写入、外部服务等能力，并等待用户确认映射。
- `unsupported`：主要目标无法由当前 Runtime 表达；原 Run 进入 `NeedsInput`，不创建 Build Job。

`rewrite_suggestion` 必须保持用户语言和原始目标，并明确替代了什么能力。接受草案会创建新 Run 并直接进入 Architect；只有用户显式选择“重新生成需求草案”时才再次调用 Product Manager。

### 2.4 Architect：把产品方案收敛为浏览器架构

**职责：** Architect 把已确认 Blueprint 转换为页面策略、本地状态实体和视觉 Token。它必须保持产品目标与页面范围，不虚构后端、网络、动态依赖或原生能力。

**当前实际输入：** 完整 `Blueprint`。Provider 输出后，Runtime 会规范化视觉 Token，再把最终 ArchitectureSpec 保存为 Artifact。

**输出 `ArchitectureSpec`：**

| 字段 | 类型与硬约束 | 语义 |
| --- | --- | --- |
| `schema_version` | 固定 `"1.0"` | Contract 版本 |
| `architecture_summary` | `str`，1–300 字符 | 整体页面、状态和运行方式摘要 |
| `page_strategy` | `list[str]`，1–8 项 | 页面/界面的组织与导航策略 |
| `data_entities` | `list[str]`，1–8 项 | 浏览器本地状态中的核心实体 |
| `primary_color` | `#RRGGBB` | 主文字或主界面颜色 |
| `accent_color` | `#RRGGBB` | 强调色 |
| `background_color` | `#RRGGBB` | 背景色 |
| `typography` | `sans \| serif`，默认 `sans` | 字体方向，不代表具体远程字体依赖 |
| `density` | `compact \| comfortable`，默认 `comfortable` | 界面信息密度 |
| `style` | `str`，1–120 字符 | Engineer 必须继承的视觉风格说明 |

当前 Contract 没有独立组件树、状态转移图或 API Schema；这些内容不能只写进自由文本后假装已被 Runtime 验证。V1 Validator 只验证已进入显式字段和源码的约束。

### 2.5 Engineer：生成 AppSpec 与自包含 Web 源码

**职责：** Engineer 将 Blueprint 和 ArchitectureSpec 实现为完整 `AppSpec`。输出必须能被 Runtime 组合为单个 sandboxed HTML 文档；不得使用远程资源、网络请求、动态 import、`eval`、包依赖、后端调用或 Shell 命令。

**当前实际输入：** 原始 Prompt、完整 `Blueprint` 和 `ArchitectureSpec`。Runtime 会强制把 AppSpec 的三项颜色对齐到 ArchitectureSpec，模型不能通过输出改变这些视觉 Token。

**输出 `AppSpec`：**

| 字段 | 类型与硬约束 | 语义 |
| --- | --- | --- |
| `schema_version` | 固定 `"1.0"` | Contract 版本 |
| `project_name` | `str` | Project 展示名，应与 Blueprint 保持一致 |
| `tagline` | `str`，1–160 字符 | 简短产品描述 |
| `hero_title` | `str`，1–120 字符 | 主标题 |
| `hero_body` | `str`，1–300 字符 | 主说明 |
| `primary_color` | `#RRGGBB` | 必须与 ArchitectureSpec 一致 |
| `accent_color` | `#RRGGBB` | 必须与 ArchitectureSpec 一致 |
| `background_color` | `#RRGGBB` | 必须与 ArchitectureSpec 一致 |
| `pages` | `list[PageSpec]`，1–12 项 | 与用户体验对应的路由和页面区块 |
| `products` | `list[ProductItem]`，最多 12 项 | 仅商品目录使用的受控数据；其他产品类型应为空 |
| `html` | `str`，最多 40,000 字符 | 不含 Markdown fence 的语义化 body fragment |
| `css` | `str`，最多 40,000 字符 | 完整本地样式 |
| `javascript` | `str`，最多 40,000 字符 | 使用浏览器 API 的本地交互逻辑 |

`PageSpec` 的字段：`route` 必须匹配 `/[a-z0-9/_-]*`，`name` 为 1–80 字符，`sections` 为 1–10 个字符串。当前 Schema 没有像 Blueprint 那样额外拒绝空白 `sections`，这仍是 Contract 加固点。

`ProductItem` 的字段：`id` 只允许小写字母、数字和连字符；同时包含 `name`、`category`、`price`、`description` 和 `image_url`。其中 `image_url` 在当前 Schema 中只是普通字符串，没有 URL 来源或离线安全校验；不能仅凭 ProductItem 通过 Pydantic 校验就声称资源边界已经满足。

### 2.6 Runtime Validator：生成不可由 Agent 改写的工程证据

**职责：** Validator 不是 LLM 角色。它读取 Prompt、Blueprint、ArchitectureSpec 和 AppSpec，检查范围映射、页面交接、源码完整性、离线边界、视觉 Token 和颜色对比度。`passed=false` 时 Reviewer 无权覆盖；只有全部失败项都属于 `app_spec + resolvable` 时，Runtime 才允许 Engineer 自动修订一次并重新执行完整校验。

**输出 `ValidationReport`：**

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `schema_version` | 固定 `"1.0"` | Contract 版本 |
| `passed` | `bool` | 所有强制门禁是否通过 |
| `checks` | `list[ValidationCheck]` | 每项确定性检查及证据 |

每个 `ValidationCheck` 包含：`check_id`、`label`、`status(pass/fail/warning)`、`root_cause(app_spec/renderer/platform/unknown)`、`resolvable` 和可选 `detail`。这些字段是有限自动修复的硬路由依据：全部失败项均为 `app_spec + resolvable` 时进入一次 Engineer 修复；任一失败项属于 Renderer、Platform、Unknown 或不可修复时直接失败，避免模型掩盖工程故障。

### 2.7 Data Analyst：整理应用的数据与本地状态

**职责：** Data Analyst 只分析应用使用的结构化数据、页面内容和浏览器本地状态，标记缺失、重复、不一致或无法判断的部分。它不审查代码质量，不解释 ValidationReport，也不决定是否通过。

**当前实际输入：** 原始 Prompt、完整 `Blueprint`、`ArchitectureSpec` 和 `AppSpec`。

**输出 `DataProfile`：**

| 字段 | 类型与硬约束 | 语义 |
| --- | --- | --- |
| `schema_version` | 固定 `"1.0"` | Contract 版本 |
| `summary` | `str` | 应用数据与本地状态的概括 |
| `sources` | `list[str]` | 已检查的数据来源，例如 AppSpec products 或浏览器本地状态 |
| `entities` | `list[str]` | 识别到的核心数据实体 |
| `checks` | `list[DataCheck]` | 数据检查结果；状态为 `pass / warning / not_applicable` |
| `insights` | `list[str]` | 基于现有数据可以确认的观察 |
| `warnings` | `list[str]` | 数据缺失、不一致或无法验证的部分 |
| `analyst_mode` | `agent_analysis \| deterministic_only` | 真实 Agent 分析或确定性降级模式 |

每个 `DataCheck` 包含 `check_id`、`label`、`status` 和可选 `detail`。DataProfile 是 Reviewer 的输入证据之一，不是质量门禁。

### 2.8 Reviewer：独立审查是否可以交付

**职责：** Reviewer 在确定性校验完成后，对需求、架构、实现、数据和证据做独立一致性检查。它负责指出问题属于需求、架构、数据、实现还是平台，并给出接受、返工或补充输入的结论；它不执行修复，不发布版本，也不能把 Validator 的失败改成通过。

**当前实际输入：** 原始 Prompt、完整 `Blueprint`、`ArchitectureSpec`、`AppSpec`、`DataProfile` 和 `ValidationReport`。

**输出 `ReviewReport`：**

| 字段 | 类型与硬约束 | 语义 |
| --- | --- | --- |
| `schema_version` | 固定 `"1.0"` | Contract 版本 |
| `summary` | `str` | 面向用户的独立复核结论 |
| `verdict` | `accept \| rework \| needs_input` | 是否接受当前交付、要求返工或需要用户补充 |
| `requirement_checks` | `list[str]` | 用户目标和 Blueprint 是否被忠实实现 |
| `engineering_checks` | `list[str]` | 对确定性工程证据的引用与解释，不得改写结果 |
| `data_findings` | `list[str]` | 对 DataProfile 的关键发现 |
| `issues` | `list[ReviewIssue]` | 带严重度、根因和证据引用的问题 |
| `warnings` | `list[str]` | 不阻断交付但需要告知的问题 |
| `suggested_actions` | `list[edit \| resolve \| retry \| accept]` | 用户或 Runtime 可采取的下一步建议 |
| `reviewer_mode` | `agent_review \| deterministic_only` | 真实 Reviewer 或确定性降级模式 |

`ReviewIssue` 的严重度为 `blocker / warning / info`，根因为 `requirements / architecture / data / implementation / platform / unknown`。当前 V1 中，`verdict != accept` 或存在 blocker 时不会创建 ProjectVersion，Run 以 `REVIEW_REJECTED` 失败。

### 2.9 固定交接链路

```text
Lead            -> LeadDecision（direct reply | fixed team）
Product Manager -> Blueprint
Architect       -> ArchitectureSpec
Engineer        -> AppSpec
Data Analyst    -> DataProfile
Runtime         -> BuildArtifact
Validator       -> ValidationReport
Reviewer        -> ReviewReport
```

每个 Agent Artifact 都先经过 Pydantic Schema 校验再持久化；下一阶段读取已保存 Artifact，而不是依赖上一角色的隐藏对话或 Chain of Thought。

### 2.10 二选一路由边界

V1 不再让用户先理解 Engineer Mode / Team Mode。默认入口只有 Lead：

```text
用户询问能力、状态或需求不完整
    -> direct -> Lead 回答或澄清

用户明确要求创建、修改、修复应用
    -> team -> 完整固定团队
```

Lead 不得在 `direct` 路径中偷偷生成 AppSpec、修改仓库或消耗团队预算。用户可以点击“调用团队”覆盖 direct 判断；Lead 判断为 team 时，UI 必须先展示可见路由摘要和预计基础调用量，但普通受支持构建不再要求第二次 Blueprint 审批。

## 3. Orchestrator 与执行状态

V1 的 Lead 是独立 Agent，但自主范围只到 `direct/team` 二选一；Runtime 校验 LeadDecision 后推进固定状态机：

```text
Created
  -> LeadRouting
       |-- DirectResponding -> Completed
       `-- TeamQueued
  -> ProductRunning
       `-- Unsupported -> NeedsInput -> PM draft confirmation -> New Run
  -> AwaitingRiskApproval        (only when policy requires)
  -> ArchitectRunning              (team route)
  -> EngineerRunning
  -> DataRunning
  -> BuildQueued
  -> Building
  -> Validating
       |-- pass -> ReviewRunning     (team route)
       |          |-- accept -> Completed / CompletedDegraded
       |          `-- rework / needs_input / blocker -> Failed
       |-- resolvable + attempt=0
       |          -> Repairing -> BuildQueued
       `-- otherwise -> Failed -> NeedsInput
```

硬规则：

- Lead 只选择 direct/team；进入 team 后下一角色由状态机决定，不由模型选择。
- 同一时刻一个 Run 只有一个主阶段；重试和修复创建新的 stage attempt。
- 每个阶段必须先持久化输入 Artifact 引用，再调用模型。
- 每个阶段必须先持久化输出，再发送 `stage.completed`。
- Approval 是否需要由确定性 Risk Policy 根据 Blueprint、预算和目标操作决定；当前 LeadDecision 不包含 risk flag，Lead 不能自行绕过或强制审批。
- Publish 不属于 Agent Run，由用户通过独立发布状态机触发。

## 4. Human-in-the-loop

### 4.1 风险驱动的必要确认

普通 `supported` 构建、固定预算内的团队调用、预览、打开 Vim、编辑 worktree 和追加保存 ProjectVersion 都不单独审批。用户明确提出“创建/修改/修复应用”已经构成本轮基础团队执行授权。

| 确认点 | 触发条件 | 用户可以做什么 | 未确认时系统行为 |
| --- | --- | --- | --- |
| Adapted 映射审批 | `support_level=adapted` | 查看映射/舍弃项后确认或拒绝 | 不继续构建 |
| 需求澄清 | Lead 无法确认用户是否要求执行，或缺少关键输入 | 补充信息或明确“调用团队” | 保持 direct，不创建 Team Run |
| 额外预算确认 | 预计调用超过基础预算、追加 retry/rework 或批量任务 | 接受本轮上限或停止 | 不预占额外额度 |
| 范围变更确认 | 修复或 Follow-up 需要改变已展示范围 | 接受新 Blueprint 或保留原范围 | 自动修改停止，进入 Needs input |
| Worktree 破坏性确认 | 丢弃未提交修改、强制重置、删除 Project | 查看影响后确认或取消 | 保留仓库和 dirty worktree |
| 当前版本切换 | Restore 会创建新版本并改变当前指针 | 确认恢复目标 | 不移动当前版本 |
| 线上变更 | Publish、Update、Unpublish | 查看目标版本/公开影响后显式执行 | Agent 和平台不改变线上状态 |

### 4.2 Approval Contract

确认必须绑定精确风险对象，而不是只保存一个布尔值：

```text
approval_id
approval_type
project_id
run_id
target_type: artifact | budget | worktree | version | deployment
target_id
target_hash
risk_level: light | destructive | public
effect_summary
requested_by_stage
decided_by_user_id
status: pending | approved | rejected | cancelled
created_at
decided_at
```

规则：

- 只有资源所属用户能审批。
- 目标 Artifact、worktree hash、预算或版本指针变化后，旧 approval 立即失效。
- 页面刷新或服务重启后，Run 从 `pending` approval 恢复，不得自动确认。
- 用户拒绝或取消后保留输入、Artifact、仓库和当前版本，但不预占新额度、不执行破坏性或公开动作。
- 显式点击带完整后果说明的 Save Version / Publish 操作本身可以构成轻确认，不再叠加无信息量的第二个弹窗；不可逆删除仍需要二次确认。

## 5. Context 管理

### 5.1 Context 不是完整聊天历史

V1 不把整个 Session 对话、所有日志和其他角色的隐藏推理直接传给下一角色。当前 Provider 输入由角色 instruction、Pydantic JSON Schema 和阶段 payload 组成：

```text
Stage Context
  = role instruction
  + current Contract JSON Schema
  + current stage payload
```

### 5.2 各阶段当前实际 Context

| 阶段 | 当前实际传入 Provider | 当前没有传入 |
| --- | --- | --- |
| Lead | 当前 `message`；`force_team=true` 时 Runtime 直接覆盖路由 | Project/Version 摘要、历史对话、源码、附件、预算摘要 |
| Product Manager | `Run.prompt`、`Run.mode` | 附件元数据、Project 历史、已有源码、旧 Build 日志 |
| Architect | 当前 `Blueprint` | 原始 Prompt、完整会话、源码、后续角色内容 |
| Engineer | 原始 Prompt、`Blueprint`、`ArchitectureSpec` | 宿主文件、密钥、未接受 Artifact、构建日志 |
| Data Analyst | 原始 Prompt、`Blueprint`、`ArchitectureSpec`、`AppSpec` | ValidationReport、私有推理、可写执行权限 |
| Reviewer | 原始 Prompt、`Blueprint`、`ArchitectureSpec`、`AppSpec`、`DataProfile`、`ValidationReport` | 私有推理、可写执行权限、发布权限 |

`RunCreate` 可以保存附件名称、大小和 content type，但当前 Product Manager Provider 尚未接收这些元数据，附件内容也不会发送给第三方模型。Project Context、Repair Context 和 Follow-up Context 属于后续对话式 AI Coding Contract，不能作为当前固定构建链路的已实现输入。

### 5.3 Context 持久化与裁剪

- Session 保存用户可恢复的交互边界；Run 保存一次构建/修改任务；StageRun 保存一次角色调用。
- Artifact 使用不可变 ID、版本和 hash 引用，下一阶段不依赖内存对象。
- 当前单实例实现以每类唯一 Artifact 作为阶段恢复检查点；成功输出与该次 Provider usage 在同一事务提交，Worker 重启后直接复用已提交 Artifact。
- 错误上下文只保留错误码、失败 check、evidence ref 和截断摘要，不把无限日志送入模型。
- 每次调用记录 `model`、`prompt_version`、`input_artifact_refs`、`output_artifact_id`、usage 和 attempt。
- 不持久化或展示模型私有 Chain of Thought；只保存结构化输出、决策摘要和可审计证据。

## 6. Tool 设计

### 6.1 V1 Agent 可见 Tool

**默认没有可执行 Tool。** Lead 与五个专业角色通过显式输入获得所需 Artifact，并只返回经 Pydantic 校验的结构化输出。Provider Adapter 不开放 Tool Calling；V1 的 Run、事件、配额和 Trace 由自有 Runtime 管理。

以下能力明确不暴露给模型：

- Shell、Python、Node、npm、Git。
- 任意文件读取或写入。
- 数据库查询与修改。
- 网络请求。
- 配额结算。
- Build、Restore、Publish、Update、Unpublish。

### 6.2 平台 Runtime 操作

下列是平台内部操作，不是 LLM 可以自行调用的 Agent Tool：

| Runtime 操作 | 调用者 | 策略 |
| --- | --- | --- |
| `load_stage_context` | Orchestrator | 按用户、Project、Run 和 Artifact 归属读取 |
| `reserve_and_settle_quota` | Agent Service | 数据库事务，按每次 Provider 调用结算 |
| `persist_artifact` | Agent Service | Pydantic 校验成功后写入不可变 Artifact |
| `enqueue_build` | Orchestrator | Lead 已路由 team、Risk Policy 已满足且 AppSpec 有效时执行 |
| `open_editor_session` | Terminal Service | 校验 AuthSession、Project owner 和单写锁后启动受限 Vim Sandbox |
| `save_project_version` | Repository Service | 收集允许路径、校验、构建、创建 Git commit 并写 ProjectVersion |
| `package_web_source` | Build Worker | 将已校验 AppSpec 物化为当前 Project 的 `index.html`、`styles.css`、`app.js` |
| `run_fixed_build` | Build Worker | 只执行平台配置的固定命令 |
| `validate_build` | Validator | 产生不可被 Agent 修改的 ValidationReport |
| `publish_version` | Publish Service | 只接受用户显式请求和合法 `version_id` |

V2 如需开放 Tool，应先引入结构化 `ToolRequest`、独立权限策略、审批和运行级沙箱；不能直接把这些 Runtime 操作注册给 V1 Agent。

当前 Validator 核对 Web 源码完整性、禁网和危险浏览器能力、Blueprint 页面交接、AppSpec 与 ArchitectureSpec 视觉 Token 一致性及颜色对比度。Preview 通过 CSP 和无同源权限的 iframe Sandbox 运行；Validator 结论不能被 Agent 改写。

当前可运行纵切仍在每次构建前显式审批 Blueprint；审批通过使用状态 CAS 防止重复排队。上文“普通 supported 不重复审批”是 Lead/Risk Policy 完成后的 V1 目标，不是当前代码已经具备的行为。

## 7. WebIDE、Sandbox 与执行边界

### 7.1 用户可编辑，但没有宿主 Shell

V1 增加 xterm.js + Vim WebIDE 后，用户可以修改当前 Project 的受控源码路径。xterm.js 只是终端渲染层，不直接连接宿主机；Terminal Service 通过一次性 WebSocket token 连接独立 Editor Sandbox，并固定启动 Vim，不启动 bash/zsh 登录 Shell。

### 7.2 Sandbox Manager

可信 Sandbox Manager 在 Linux 执行宿主机上为每个编辑/构建会话创建 rootless 容器或等价 namespace 隔离：

- 非 root UID、只读根文件系统、`no-new-privileges`、drop all capabilities、seccomp。
- 默认无网络、无平台数据库连接、无 LLM/API Secret、无 Docker socket。
- 设置 CPU、内存、磁盘、PID、输出和生命周期上限；断开后按 grace period 销毁。
- 只挂载当前会话的临时 worktree；不挂载宿主 repo root，不暴露 `.git`、其他用户目录或绝对宿主路径。
- Editor Sandbox 固定启动受限 Vim，禁用 shell escape、插件下载和仓库外文件访问。
- Build Sandbox 使用固定镜像、固定依赖和固定命令；用户不能修改 `package.json`、lockfile、构建脚本或依赖目录。

目录关系：

```text
trusted bare repo (sandbox 不可见)
        |
        | export commit snapshot
        v
ephemeral session worktree ---- mounted RW ----> Editor Sandbox / Vim
        |
        | collect allowlisted files
        v
Repository Service staging -> validate/build -> git commit -> ProjectVersion
```

### 7.3 Repository 与写入并发

- 每个 Project 同时最多一个可写 Editor Session；其他会话只读或等待。
- Vim `:write` 只修改临时 worktree，UI 显示 dirty 文件，不自动生成版本或更新线上内容。
- Save Version 是用户显式命令；Repository Service 校验 owner、base commit 和 worktree hash，防止覆盖并发修改。
- Git 元数据和 commit 只由可信 Repository Service 操作，Sandbox 内不能修改 hook、config、refs 或 remote。
- Restore 从历史 commit 导出新快照并创建新 commit，不移动或重写既有历史。

### 7.4 不能声称的能力

V1 不能声称支持：

- 用户或模型获得任意宿主 Shell。
- 动态依赖安装或不受控出网。
- 编辑 Sandbox 内使用 Git remote、SSH key 或平台凭证。
- 把受限 Vim 描述为完整 Terminal CLI 或 CC 式 Agent Runtime。

目录约束、`vim -Z` 或 `chroot` 单独都不构成强隔离。若目标部署环境不能提供 rootless container/namespace、资源限制和 Secret 隔离，则真实 Vim WebIDE 不能启用，只能退化为浏览器内文件编辑器。

## 8. Agent 错误、验收与有限修复

### 8.1 谁拥有验收权

```text
Build Worker             -> 是否成功构建
Deterministic Validator  -> mandatory checks 是否通过
Data Analyst Agent       -> 应用数据和本地状态是否完整
Reviewer Agent           -> 是否接受交付或指出待解决问题
User                     -> 是否接受、继续修改或发布
```

Engineer 不能给自己的输出直接判定通过；Reviewer 不能修改 ValidationReport。Reviewer 只在确定性校验通过后给出独立复核结论，任何修复都必须重新经过完整 Build、Validation 和 Review。

### 8.2 失败处理矩阵

| 失败类型 | 证据来源 | 自动处理 | 最终失败行为 |
| --- | --- | --- | --- |
| Provider 超时/限流/5xx | Provider error | 最多 3 次总尝试，退避 | `run.failed` / Needs input |
| Pydantic 输出无效 | validation errors | 带错误修正，最多 3 次总尝试 | `INVALID_MODEL_OUTPUT` |
| Renderer/Build 失败 | exit code + build log | 相同输入不重复构建；仅 lease 恢复可自动领取一次 | `build.failed`，保留日志 |
| mandatory validation fail，`app_spec + resolvable` | ValidationReport | Engineer 自动修订最多 1 轮 | 仍失败则 Failed，保留两轮证据 |
| mandatory validation fail，其他根因 | ValidationReport | 不调用 Agent 掩盖平台错误 | Failed / Needs input |
| 非 mandatory warning | DataProfile / ValidationReport / ReviewReport | 不伪装为全量通过 | Reviewer 接受时以 `CompletedDegraded` 完成 |
| Reviewer verdict 为 `rework` / `needs_input`，或包含 blocker | ReviewReport | 不创建 ProjectVersion | `REVIEW_REJECTED`，保留已有 Artifact |

Provider 或结构化输出达到最大尝试次数后，平台不得静默改用预设文本。Project 保留 Prompt、附件元数据、Session 和已完成 Artifact，进入 Needs input，并提供：

- Retry：创建新的 StageRun attempt，重新执行当前失败角色。
- Edit request：返回 Prompt 或 Blueprint 编辑，不自动继续旧阶段。
- Use starter Blueprint：由用户主动选择非 AI 回退，并在 Artifact 来源中明确标记。

`QUOTA_EXCEEDED` 不自动重试，也不能显示为 Provider 故障；每次实际 Provider 调用分别预占和结算用量。

`CompletedDegraded` 只表示确定性检查已通过、Reviewer 已接受，但 DataProfile 或 ReviewReport 仍包含 warning。Provider/配额失败不会伪造降级产物，而是按失败路径保留已经提交的 Artifact。

### 8.3 自动修复输入输出

```text
Input
  Blueprint + ArchitectureSpec + original AppSpec + ValidationReport
        |
        v
Engineer Agent
        |
        v
revised AppSpec（独立 Artifact，repair_attempt=1）
        |
        v
Pydantic -> full deterministic Validation -> Reviewer / Failed
```

首次 `AppSpec`、首次 `ValidationReport`、修订 `AppSpec` 和二次 `ValidationReport` 分别保存，便于查看失败原因，并使 Worker 重启时复用已完成结果。修订校验仍失败后不会循环调用 Engineer，只能进入失败状态由用户决定是否创建新 Run。自动修复不得静默改变已经向用户展示的 Blueprint 页面和模块范围；需要改变范围时，必须生成新 Blueprint，并由 Risk Policy 触发范围变更确认。

### 8.4 User Resolve 与真实 Build Error

```text
真实 Build Error
build.failed -> run.failed -> 用户 Retry Build

已成功构建后的应用问题
validation.issue_detected -> User Resolve
    -> RevisionSpec
    -> new BuildJob
    -> ProjectVersion(source=Resolve)
```

两条路径共用 Artifact、Event 和 Version 基础设施，但状态和文案不同。Resolve 处理已构建应用中的可定位问题，不能被包装成 Agent 自动修复了 Renderer、编译或资源错误；Build Worker 的工程恢复规则以 [V1 系统架构](../工程/01-系统架构.md)为准。

## 9. Prompt、版本与可观测性

每个角色拥有独立 system instruction 和 Pydantic output schema。Prompt 不写在 API route 中，由版本化配置集中管理。

每个 StageRun 至少记录：

```text
agent_role
model
prompt_version
input_artifact_refs
output_artifact_id
attempt
status
started_at / completed_at
input_tokens / output_tokens
provider_request_id
trace_id
error_code
```

事件顺序：

```text
stage.started
stage.output          artifact_id / artifact_type
stage.completed

或

stage.started
stage.retrying
stage.failed

或 Reviewer 拒收

stage.started
stage.completed       review_report_id / verdict
run.failed            REVIEW_REJECTED
```

事件先持久化，再通过 SSE 推送。浏览器重连后按 `event_id` 重放。Trace 用于工程排障，不能向用户展示 Chain of Thought。

## 10. 配额与并发

- 每个实际 Provider 调用单独预占并结算用量，包括 schema retry 和 repair。
- 成功阶段的 Artifact 与结算同事务提交；非 LLM 异常也必须结算已观测到的实际请求并释放剩余预占，不能把整笔 reservation 记为 used。
- Worker 恢复只重放尚无 Artifact 的阶段；已提交阶段、已完成 Run 和既有 Build Version 不重复执行或结算。
- Lead direct 只结算 Lead 调用；Lead team 路径中的五个专业角色顺序执行，因此一个 Run 不产生并行 LLM 预占。
- 同一账户的多个 Session 共享 Quota Account，预占必须使用数据库事务。
- `QUOTA_EXCEEDED` 默认不自动重试；Run 保留当前 Artifact，并按失败状态向用户展示当前阶段。
- 配额在任一 Agent 阶段耗尽时，用户只能编辑输入、查看/导出现有结果或等待管理员重置；系统不会伪造后续 DataProfile 或 ReviewReport。
- 用户取消 pending risk approval 时不发生新的模型调用或配额消耗。

## 11. 代码归属

```text
another_atom/agent/
├── orchestrator.py       Lead 路由校验、固定团队状态机与阶段推进
├── context.py            Stage Context 组装与裁剪
├── approvals.py          风险驱动 Human-in-the-loop Contract
├── repair.py             有限修复规则
├── roles/
│   ├── lead.py
│   ├── product_manager.py
│   ├── architect.py
│   ├── engineer.py
│   ├── data_analyst.py
│   └── reviewer.py
├── prompts/              版本化 role instruction
└── tracing.py            StageRun / usage / trace 记录
```

Pydantic Contract 仍统一放在 `another_atom/contracts/`。Agent 目录只能引用 Contract，不能再定义一套 Blueprint、AppSpec 或 ValidationReport。

## 12. V1 Agent 验收标准

- LeadDecision 只能为 direct 或 team；direct 不创建 Team Run，team 严格按 Product Manager -> Architect -> Engineer -> Data Analyst -> Validator -> Reviewer 推进。
- 用户可以把 direct 覆盖为 team；Lead 不能绕过 Runtime 风险策略，也不能替专业角色生成 Contract。
- 普通 supported 构建不设置重复 Blueprint 审批；adapted、额外预算、范围变化、破坏性 worktree 操作和线上变更必须产生有效 risk approval。
- 每个角色输出都有 Artifact ID、版本、hash、prompt version、usage 和 trace。
- 下一角色只接收显式 Artifact 与阶段最小上下文，不接收隐藏长期记忆。
- V1 Agent 没有 Shell、文件、Git、网络、数据库或 Publish Tool；用户的 Vim 运行在独立受限 Sandbox 中，不属于 Agent Tool。
- mandatory check 不能被 Reviewer 覆盖；Reviewer 拒收或给出 blocker 时不能创建 ProjectVersion。
- 正常 team route 必须同时保存 DataProfile、ValidationReport 和 ReviewReport；`CompletedDegraded` 只能由已接受交付中的 warning 触发。
- 进程重启或 SSE 重连后，Run、pending risk approval、StageRun 和事件可以恢复。
- Editor Session 只能访问当前用户当前 Project 的临时 worktree；`.git`、Secret、其他用户目录和宿主 Shell 均不可见。
- 跨用户或跨 Project 的 Context、Artifact、日志和事件泄漏数量为 0。

## 13. V1 Agent 边界与演进取舍

本节承接原 README 中的 V1 Agent 版本取舍。它们是 V1 为完成闭环而做的约束，不是整体产品的长期限制。

- **[固定完整团队]** 每个 `team` 请求固定执行 Product Manager → Architect → Engineer → Data Analyst → Reviewer，Data Analyst 与 Reviewer 之间由确定性 Validator 固定工程事实。V1 先验证专业 Contract 与产物交接是否有效，角色子集留给 V2。
- **[固定顺序执行]** V1 不并行执行 Agent，也不允许多个角色共享可写工作区，以减少部分失败、并发配额和 Artifact 合并变量。
- **[阶段级 Context]** Runtime 为每个阶段组装所需的 Blueprint、ArchitectureSpec、AppSpec 和 Evidence，不维护一段无限增长的共享聊天记录，也不实现独立 Agent 长期记忆。
- **[Runtime 控制返工]** 固定状态机、重试上限和失败出口决定是否返工；Lead 不能修改流程或无限重试。V2 才允许 Lead 提交结构化返工与仲裁建议。
- **[受控生成范围]** V1 Agent 必须保留游戏、工具、看板、目录等原始产品目标，并将 supported 需求收敛为自包含浏览器应用；不通过 Prompt 暗示任意技术栈、动态依赖、网络、Shell、后端或自动发布已经可用。
