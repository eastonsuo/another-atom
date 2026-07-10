# Another Atom V1 Agent 设计

[toc]

- 文档状态：V1 实施基线
- 更新日期：2026-07-11
- 产品文档：[Another Atom V1 产品需求文档](./another-atom-v1-prd.md)
- 工程架构：[Another Atom V1 架构设计](./architecture-design.md)
- V2 演进：[Another Atom V2 Agent 设计](../v2/agent-design.md)

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
   `-- team -> Product Manager -> Architect -> Engineer
                    |
                    v
             Runtime Build / Validator -> Data Analyst
```

三种范式的区别：

| 范式 | V1 是否采用 | 原因 |
| --- | --- | --- |
| ReAct：模型循环执行 Action -> Observation -> Action | 否 | V1 不向模型开放 Shell、文件、构建或发布 Tool，不需要开放式工具循环 |
| 开放式 Plan-and-Execute | 否 | Lead 不能自由创建任务图、选择任意角色、决定权限、重试次数或发布 |
| Lead 二选一路由 | 是 | Lead 只决定直接回答/澄清，或调用完整固定团队；用户可以覆盖为“调用团队” |
| Contract-first Plan -> Execute -> Validate | 是 | 团队产生显式产物，平台按固定状态机执行，Validator 决定确定性结果 |

这里的 “Plan” 不是一次生成完整任务图，而是 Blueprint、ArchitectureSpec、AppSpec 逐层收敛；“Execute” 由平台完成；“Validate” 先由确定性 Validator 执行，再由 Data Analyst Agent 解释。

## 2. V1 角色与 Contract

### 2.1 Lead 与固定团队

| 角色 | 输入上下文 | 结构化输出 | 可决定 | 不可决定 |
| --- | --- | --- | --- | --- |
| Lead | 用户消息、当前 Project 摘要、能力边界、基础预算 | `LeadDecision`、直接回复或团队摘要 | `direct` / `team` 二选一路由；direct 内回答或提出澄清 | 不自由挑选角色，不创建动态任务图，不执行 Tool，不代替专业角色生成 Contract，不发布 |
| Product Manager | Prompt、附件元数据、平台能力范围 | `Blueprint` | 需求字段、`support_level`、适配说明 | 不确认 Blueprint，不创建 Build Job |
| Architect | 当前 Blueprint、Renderer Capability Contract | `ArchitectureSpec` | 页面策略、数据实体、布局、视觉和交互约束 | 不擅自扩大 Blueprint 范围，不选择任意技术栈 |
| Engineer | Blueprint、ArchitectureSpec、Renderer Capability Contract | `AppSpec`；修复时为 `RevisionSpec + AppSpec` | 在固定 Renderer 能力内定义应用结构 | 不写任意源码，不选择依赖或 Shell 命令 |
| Data Analyst | AppSpec、不可变 ValidationReport | `DataReview` | 检查数据完整性，解释工程校验，引用证据并提出建议 | 不修改 engineering check，不宣布失败结果通过 |

Product Manager 的 Blueprint 范围判定至少包含：

```text
support_level: supported | adapted | unsupported
support_reasons[]
mapped_requirements[]
omitted_requirements[]
rewrite_suggestion
capability_policy_version
```

LLM 提出判定，Runtime 使用固定 Capability Policy 校验允许的产品类型、页面、模块和后端能力。同一 Policy 版本必须维持一致的允许/拒绝边界；模型不能为了继续执行把主要目标不受支持的请求标为 `adapted`。

DataReview 至少包含：

```text
summary
data_checks[]
engineering_checks[]     mirrors ValidationReport
warnings[]
suggested_actions[]      edit | resolve | retry | accept
analyst_mode: agent_review | deterministic_only
```

`LeadDecision` 最小 Contract：

```text
route: direct | team
intent_summary
reason_summary
risk_flags[]
estimated_provider_calls
clarification_question?   only when route=direct
```

固定交接链路：

```text
Lead            -> direct reply | fixed team
Product Manager -> Blueprint
Architect       -> ArchitectureSpec
Engineer        -> AppSpec
Runtime         -> BuildArtifact
Validator       -> ValidationReport
Data Analyst    -> DataReview
```

### 2.2 二选一路由边界

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
  -> AwaitingRiskApproval        (only when policy requires)
  -> ArchitectRunning              (team route)
  -> EngineerRunning
  -> BuildQueued
  -> Building
  -> Validating
       |-- pass -> DataReviewing     (team route)
       |          |-- review success -> Completed
       |          `-- Provider/Quota unavailable -> CompletedDegraded
       |-- resolvable + attempt=0
       |          -> Repairing -> BuildQueued
       `-- otherwise -> Failed -> NeedsInput
```

硬规则：

- Lead 只选择 direct/team；进入 team 后下一角色由状态机决定，不由模型选择。
- 同一时刻一个 Run 只有一个主阶段；重试和修复创建新的 stage attempt。
- 每个阶段必须先持久化输入 Artifact 引用，再调用模型。
- 每个阶段必须先持久化输出，再发送 `stage.completed`。
- Approval 是否需要由确定性 Risk Policy 决定，Lead 只能提交 risk flag，不能自行绕过或强制审批。
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

V1 不把整个 Session 对话、所有日志和其他角色的隐藏推理直接传给下一角色。Runtime 按阶段组装最小上下文：

```text
Stage Context
  = role instruction + prompt version
  + current user request snapshot
  + accepted upstream Artifact references
  + platform capability contract
  + bounded failure evidence (only on retry/repair)
```

### 5.2 各阶段上下文

| 阶段 | 必须包含 | 明确不包含 |
| --- | --- | --- |
| Lead | 当前消息、Project/Version 摘要、能力边界、基础预算 | 其他用户项目、完整源码、密钥、专业角色隐藏推理 |
| Product Manager | 当前 Prompt、附件名称/大小、支持范围 | 附件二进制、其他用户数据、旧 Build 日志 |
| Architect | 当前 Blueprint、视觉 token 范围 | 原始完整会话、Engineer/Data Analyst 内容 |
| Engineer | 当前 Blueprint、ArchitectureSpec、Renderer Capability Contract | 任意宿主文件、密钥、未接受需求 |
| Data Analyst | AppSpec、ValidationReport、evidence refs | 私有 Chain of Thought、可写执行权限 |
| Repair | 当前 AppSpec、失败 ValidationReport、DataReview、repair attempt | 无关历史版本、完整构建日志、范围外需求 |
| Follow-up | 当前 ProjectVersion Artifact、用户最新修改请求 | 从项目创建开始的全部原始消息 |

附件在 V1 只向 Agent 提供名称、类型和大小等元数据，不把附件内容上传给第三方模型。

### 5.3 Context 持久化与裁剪

- Session 保存用户可恢复的交互边界；Run 保存一次构建/修改任务；StageRun 保存一次角色调用。
- Artifact 使用不可变 ID、版本和 hash 引用，下一阶段不依赖内存对象。
- 错误上下文只保留错误码、失败 check、evidence ref 和截断摘要，不把无限日志送入模型。
- 每次调用记录 `model`、`prompt_version`、`input_artifact_refs`、`output_artifact_id`、usage 和 attempt。
- 不持久化或展示模型私有 Chain of Thought；只保存结构化输出、决策摘要和可审计证据。

## 6. Tool 设计

### 6.1 V1 Agent 可见 Tool

**默认没有可执行 Tool。** Lead 与四个专业角色通过显式输入获得所需 Artifact，并只返回经 Pydantic 校验的结构化输出。Provider Adapter 不开放 Tool Calling；V1 的 Run、事件、配额和 Trace 由自有 Runtime 管理。

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
| `render_app` | Build Worker | 只允许固定 Renderer 和当前 Project 临时快照 |
| `run_fixed_build` | Build Worker | 只执行平台配置的固定命令 |
| `validate_build` | Validator | 产生不可被 Agent 修改的 ValidationReport |
| `publish_version` | Publish Service | 只接受用户显式请求和合法 `version_id` |

V2 如需开放 Tool，应先引入结构化 `ToolRequest`、独立权限策略、审批和运行级沙箱；不能直接把这些 Runtime 操作注册给 V1 Agent。

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
Data Analyst Agent                 -> 解释问题和建议修复
User                     -> 是否接受、继续修改或发布
```

Agent 不能给自己的输出直接判定通过。DataReview 不能修改 ValidationReport，Engineer Repair 也必须重新经过完整 Build 和 Validation。

### 8.2 失败处理矩阵

| 失败类型 | 证据来源 | 自动处理 | 最终失败行为 |
| --- | --- | --- | --- |
| Provider 超时/限流/5xx | Provider error | 最多 3 次总尝试，退避 | `run.failed` / Needs input |
| Pydantic 输出无效 | validation errors | 带错误修正，最多 3 次总尝试 | `INVALID_MODEL_OUTPUT` |
| Renderer/Build 失败 | exit code + build log | 相同输入不重复构建；仅 lease 恢复可自动领取一次 | `build.failed`，保留日志 |
| mandatory validation fail，`app_spec + resolvable` | ValidationReport | Engineer 自动修订最多 1 轮 | 仍失败则 Needs input |
| mandatory validation fail，其他根因 | ValidationReport | 不调用 Agent 掩盖平台错误 | Failed / Needs input |
| 非 mandatory warning | ValidationReport + DataReview | 不阻塞 Preview | 用户决定修改或发布 |
| mandatory checks 已通过，但 Data Analyst Agent Provider/配额失败 | ValidationReport + Provider/Quota error | 不重试到无限；使用 deterministic_only | `CompletedDegraded`，展示明确提示 |

Provider 或结构化输出达到最大尝试次数后，平台不得静默改用预设文本。Project 保留 Prompt、附件元数据、Session 和已完成 Artifact，进入 Needs input，并提供：

- Retry：创建新的 StageRun attempt，重新执行当前失败角色。
- Edit request：返回 Prompt 或 Blueprint 编辑，不自动继续旧阶段。
- Use starter Blueprint：由用户主动选择非 AI 回退，并在 Artifact 来源中明确标记。

`QUOTA_EXCEEDED` 不自动重试，也不能显示为 Provider 故障；每次实际 Provider 调用分别预占和结算用量。

`CompletedDegraded` 只适用于确定性 mandatory checks 已全部通过后的 Data Analyst 摘要阶段。UI 必须显示“AI Data Analyst 未执行，仅完成确定性校验”，不能创建伪造 DataReview。用户可以预览和发布，但 V1 Golden Path 验收不允许使用该降级路径。

### 8.3 自动修复输入输出

```text
Input
  AppSpec + ValidationReport + DataReview + repair_attempt=0
        |
        v
Engineer Agent
        |
        v
RevisionSpec + revised AppSpec
        |
        v
Pydantic -> Renderer -> Build -> full Validation
```

自动修复不得静默改变已经向用户展示的 Blueprint 页面和模块范围。需要改变范围时，必须生成新 Blueprint，并由 Risk Policy 触发范围变更确认。

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

两条路径共用 Artifact、Event 和 Version 基础设施，但状态和文案不同。Resolve 处理已构建应用中的可定位问题，不能被包装成 Agent 自动修复了 Renderer、编译或资源错误；Build Worker 的工程恢复规则以 [V1 架构设计](./architecture-design.md)为准。

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

或 Data Analyst 降级

stage.started
qa.degraded           reason / validation_report_id
run.completed_degraded
```

事件先持久化，再通过 SSE 推送。浏览器重连后按 `event_id` 重放。Trace 用于工程排障，不能向用户展示 Chain of Thought。

## 10. 配额与并发

- 每个实际 Provider 调用单独预占并结算用量，包括 schema retry 和 repair。
- Lead direct 只结算 Lead 调用；Lead team 路径中的四个专业角色顺序执行，因此一个 Run 不产生并行 LLM 预占。
- 同一账户的多个 Session 共享 Quota Account，预占必须使用数据库事务。
- `QUOTA_EXCEEDED` 默认不自动重试；Run 保留当前 Artifact 并进入 Needs input，只有下一条定义的 Data Analyst 摘要阶段例外。
- 配额在 Product Manager/Architect/Engineer 阶段耗尽时，用户只能编辑输入、查看/导出现有结果或等待管理员重置；不能继续 Build。
- 配额仅在确定性 Validation 已通过后的 Data Analyst 摘要阶段耗尽时，允许进入 `CompletedDegraded`。
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
│   └── data_analyst.py
├── prompts/              版本化 role instruction
└── tracing.py            StageRun / usage / trace 记录
```

Pydantic Contract 仍统一放在 `another_atom/contracts/`。Agent 目录只能引用 Contract，不能再定义一套 Blueprint、AppSpec 或 ValidationReport。

## 12. V1 Agent 验收标准

- LeadDecision 只能为 direct 或 team；direct 不创建 Team Run，team 严格按 Product Manager -> Architect -> Engineer -> Data Analyst 推进。
- 用户可以把 direct 覆盖为 team；Lead 不能绕过 Runtime 风险策略，也不能替专业角色生成 Contract。
- 普通 supported 构建不设置重复 Blueprint 审批；adapted、额外预算、范围变化、破坏性 worktree 操作和线上变更必须产生有效 risk approval。
- 每个角色输出都有 Artifact ID、版本、hash、prompt version、usage 和 trace。
- 下一角色只接收显式 Artifact 与阶段最小上下文，不接收隐藏长期记忆。
- V1 Agent 没有 Shell、文件、Git、网络、数据库或 Publish Tool；用户的 Vim 运行在独立受限 Sandbox 中，不属于 Agent Tool。
- mandatory check 不能被 DataReview 覆盖；自动修复最多 1 轮并完整重建、复验。
- 正常 team route 的 DataReview 包含摘要、warning、Evidence 和可执行建议；`CompletedDegraded` 必须明确标注且不能用于 Golden Path 验收。
- 进程重启或 SSE 重连后，Run、pending risk approval、StageRun 和事件可以恢复。
- Editor Session 只能访问当前用户当前 Project 的临时 worktree；`.git`、Secret、其他用户目录和宿主 Shell 均不可见。
- 跨用户或跨 Project 的 Context、Artifact、日志和事件泄漏数量为 0。
