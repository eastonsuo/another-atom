# Another Atom V1 Agent 设计

[toc]

- 文档状态：V1 实施基线
- 更新日期：2026-07-11
- 产品文档：[Another Atom V1 产品需求文档](./another-atom-v1-prd.md)
- 工程架构：[Another Atom V1 架构设计](./architecture-design.md)
- V2 演进：[Another Atom V2 Agent 设计](../v2/agent-design.md)

## 1. 设计结论

V1 采用 **Contract-first 的 Plan -> Execute -> Validate**，不是经典 ReAct，也不是由模型自行规划和执行的 Autonomous Agent。

```text
用户需求
   |
   v
角色 Agent 生成结构化 Contract
   |
   v
Human-in-the-loop 审批
   |
   v
平台 Runtime 执行 Renderer / Build
   |
   v
Deterministic Validator 验收
   |
   +-- pass -> QAReview -> Preview
   |
   `-- fail -> 有限修复或 Needs input
```

三种范式的区别：

| 范式 | V1 是否采用 | 原因 |
| --- | --- | --- |
| ReAct：模型循环执行 Action -> Observation -> Action | 否 | V1 不向模型开放 Shell、文件、构建或发布 Tool，不需要开放式工具循环 |
| 模型主导的 Plan-and-Execute | 否 | 模型不能决定执行顺序、权限、重试次数或是否发布 |
| Contract-first Plan -> Execute -> Validate | 是 | Agent 产生显式产物，平台按固定状态机执行，Validator 决定确定性结果 |

这里的 “Plan” 不是一次生成完整任务图，而是 Blueprint、VisualSpec、AppSpec 逐层收敛；“Execute” 由平台完成；“Validate” 先由确定性 Validator 执行，再由 QA Agent 解释。

## 2. V1 角色与 Contract

### 2.1 Team Mode

| 角色 | 输入上下文 | 结构化输出 | 可决定 | 不可决定 |
| --- | --- | --- | --- | --- |
| Product Manager | Prompt、附件元数据、平台能力范围 | `Blueprint` | 需求字段、`support_level`、适配说明 | 不确认 Blueprint，不创建 Build Job |
| Designer | 已确认 Blueprint、允许的视觉 token | `VisualSpec` | 布局、视觉和交互约束 | 不增加 Blueprint 未批准的页面或模块 |
| Engineer | Blueprint、VisualSpec、Renderer Capability Contract | `AppSpec`；修复时为 `RevisionSpec + AppSpec` | 在固定 Renderer 能力内定义应用结构 | 不写任意源码，不选择依赖或 Shell 命令 |
| QA | AppSpec、不可变 ValidationReport | `QAReview` | 解释问题、引用证据、提出修复建议 | 不修改 mandatory check，不宣布失败结果通过 |

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

QAReview 至少包含：

```text
summary
mandatory_checks[]       mirrors ValidationReport
warnings[]
evidence_refs[]
suggested_actions[]      edit | resolve | retry | accept
qa_mode: agent_review | deterministic_only
```

固定交接链路：

```text
Product Manager -> Blueprint -> 用户确认
Designer        -> VisualSpec
Engineer        -> AppSpec
Runtime         -> BuildArtifact
Validator       -> ValidationReport
QA              -> QAReview
```

### 2.2 Engineer Mode

Engineer Mode 不创建另一套领域协议。Engineer Agent 使用组合 instruction，先输出 Blueprint 等待用户确认，再输出 AppSpec：

```text
Prompt -> Engineer Agent -> Blueprint -> 用户确认
       -> Engineer Agent -> AppSpec -> Build -> ValidationReport -> Preview
```

Engineer Mode 省略 Product Manager、Designer 和 QA 的独立展示与模型调用，但不能跳过 Blueprint 审批、Pydantic 校验、确定性 Build/Validation 或用户发布门。

## 3. Orchestrator 与执行状态

Orchestrator 是平台状态机，不是 Leader Agent。它只依据持久化状态和确定性规则推进：

```text
Created
  -> ProductRunning / EngineerPlanning
  -> AwaitingBlueprintApproval
  -> DesignerRunning              (Team Mode)
  -> EngineerRunning
  -> BuildQueued
  -> Building
  -> Validating
       |-- pass -> QAReviewing     (Team Mode)
       |          |-- review success -> Completed
       |          `-- Provider/Quota unavailable -> CompletedDegraded
       |-- resolvable + attempt=0
       |          -> Repairing -> BuildQueued
       `-- otherwise -> Failed -> NeedsInput
```

硬规则：

- 下一角色由状态机决定，不由模型选择。
- 同一时刻一个 Run 只有一个主阶段；重试和修复创建新的 stage attempt。
- 每个阶段必须先持久化输入 Artifact 引用，再调用模型。
- 每个阶段必须先持久化输出，再发送 `stage.completed`。
- Publish 不属于 Agent Run，由用户通过独立发布状态机触发。

## 4. Human-in-the-loop

### 4.1 必须等待用户的节点

| 审批点 | 触发条件 | 用户可以做什么 | 未审批时系统行为 |
| --- | --- | --- | --- |
| Blueprint 审批 | Product Manager/Engineer 生成 Blueprint | 编辑、确认、返回修改 Prompt | 不创建 Build Job，不进入后续角色 |
| Adapted 映射审批 | `support_level=adapted` | 查看映射/舍弃项后确认或拒绝 | 不继续构建 |
| 范围变更审批 | 修复需要增删已确认页面或模块 | 接受新 Blueprint 或保留原范围 | 自动修复停止，进入 Needs input |
| 破坏性操作确认 | Delete、Restore、Unpublish | 二次确认或取消 | 不执行操作 |
| 发布确认 | Publish 或 Update | 选择发布策略和 `version_id` | Agent 和平台都不自动发布 |

### 4.2 Approval Contract

审批必须绑定精确 Artifact，而不是只保存一个布尔值：

```text
approval_id
approval_type
project_id
run_id
artifact_type
artifact_id
artifact_version
artifact_hash
requested_by_stage
decided_by_user_id
status: pending | approved | rejected | cancelled
created_at
decided_at
```

规则：

- 只有资源所属用户能审批。
- Blueprint 被再次修改后，旧 approval 立即失效，必须对新 hash 重新审批。
- 页面刷新或服务重启后，Run 从 `pending` approval 恢复，不得自动确认。
- 用户拒绝或取消后保留输入和 Artifact，但不预占新的模型或构建额度。

## 5. Context 管理

### 5.1 Context 不是完整聊天历史

V1 不把整个 Session 对话、所有日志和其他角色的隐藏推理直接传给下一角色。Runtime 按阶段组装最小上下文：

```text
Stage Context
  = role instruction + prompt version
  + current user request snapshot
  + approved upstream Artifact references
  + platform capability contract
  + bounded failure evidence (only on retry/repair)
```

### 5.2 各阶段上下文

| 阶段 | 必须包含 | 明确不包含 |
| --- | --- | --- |
| Product Manager | 当前 Prompt、附件名称/大小、支持范围 | 附件二进制、其他用户数据、旧 Build 日志 |
| Designer | 已确认 Blueprint、视觉 token 范围 | 原始完整会话、Engineer/QA 内容 |
| Engineer | 已确认 Blueprint、VisualSpec、Renderer Capability Contract | 任意宿主文件、密钥、未批准需求 |
| QA | AppSpec、ValidationReport、evidence refs | 私有 Chain of Thought、可写执行权限 |
| Repair | 当前 AppSpec、失败 ValidationReport、QAReview、repair attempt | 无关历史版本、完整构建日志、范围外需求 |
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

**默认没有可执行 Tool。** 四个角色通过显式输入获得所需 Artifact，并只返回 Pydantic 结构化输出。使用 Agents SDK 不等于必须开放 Tool Calling；V1 使用 SDK 的 Agent 配置、Run、Structured Output、Usage 和 Trace 能力。

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
| `enqueue_build` | Orchestrator | 仅在 Blueprint 已审批、AppSpec 有效时执行 |
| `render_app` | Build Worker | 只允许固定 Renderer 和当前项目工作区 |
| `run_fixed_build` | Build Worker | 只执行平台配置的固定命令 |
| `validate_build` | Validator | 产生不可被 Agent 修改的 ValidationReport |
| `publish_version` | Publish Service | 只接受用户显式请求和合法 `version_id` |

V2 如需开放 Tool，应先引入结构化 `ToolRequest`、独立权限策略、审批和运行级沙箱；不能直接把这些 Runtime 操作注册给 V1 Agent。

## 7. Sandbox 与执行边界

### 7.1 V1 不是任意代码沙箱

V1 的安全来自“不让模型生成并执行任意代码”，而不是把不可信代码放进一个强沙箱。Engineer 输出 AppSpec，Deterministic Renderer 只把允许字段物化到固定模板。

V1 的隔离措施：

- 工作区固定为 `/data/workspaces/{user_id}/{project_id}/`。
- Renderer 只写模板允许的配置、内容和资产路径。
- Node 依赖在 Docker 镜像构建阶段预装，运行时禁止修改 `package.json` 或执行 `npm install`。
- Build Worker 只执行平台固定命令，并设置超时、输出和磁盘上限。
- 数据库、Volume、日志和 Preview 都校验用户/Project 归属。
- Preview 不能访问平台管理 API，也不能读取服务端密钥。

### 7.2 不能声称的能力

Railway 单 Web Service + Volume 不是面向敌意代码的强多租户沙箱。V1 不能声称支持：

- 用户或模型提供的任意 Shell/代码。
- 动态依赖安装。
- 不受控出网。
- 每个 Run 独立容器、VM、内核或网络命名空间。

如果后续开放这些能力，必须改为每个 Run 独立容器或 VM，并增加只读基础镜像、临时文件系统、网络策略、CPU/内存/磁盘限制、Secret 隔离和销毁流程。

## 8. Agent 错误、验收与有限修复

### 8.1 谁拥有验收权

```text
Build Worker             -> 是否成功构建
Deterministic Validator  -> mandatory checks 是否通过
QA Agent                 -> 解释问题和建议修复
User                     -> 是否接受、继续修改或发布
```

Agent 不能给自己的输出直接判定通过。QAReview 不能修改 ValidationReport，Engineer Repair 也必须重新经过完整 Build 和 Validation。

### 8.2 失败处理矩阵

| 失败类型 | 证据来源 | 自动处理 | 最终失败行为 |
| --- | --- | --- | --- |
| Provider 超时/限流/5xx | Provider error | 最多 3 次总尝试，退避 | `run.failed` / Needs input |
| Pydantic 输出无效 | validation errors | 带错误修正，最多 3 次总尝试 | `INVALID_MODEL_OUTPUT` |
| Renderer/Build 失败 | exit code + build log | 相同输入不重复构建；仅 lease 恢复可自动领取一次 | `build.failed`，保留日志 |
| mandatory validation fail，`app_spec + resolvable` | ValidationReport | Engineer 自动修订最多 1 轮 | 仍失败则 Needs input |
| mandatory validation fail，其他根因 | ValidationReport | 不调用 Agent 掩盖平台错误 | Failed / Needs input |
| 非 mandatory warning | ValidationReport + QAReview | 不阻塞 Preview | 用户决定修改或发布 |
| mandatory checks 已通过，但 QA Agent Provider/配额失败 | ValidationReport + Provider/Quota error | 不重试到无限；使用 deterministic_only | `CompletedDegraded`，展示明确提示 |

Provider 或结构化输出达到最大尝试次数后，平台不得静默改用预设文本。Project 保留 Prompt、附件元数据、Session 和已完成 Artifact，进入 Needs input，并提供：

- Retry：创建新的 StageRun attempt，重新执行当前失败角色。
- Edit request：返回 Prompt 或 Blueprint 编辑，不自动继续旧阶段。
- Use starter Blueprint：由用户主动选择非 AI 回退，并在 Artifact 来源中明确标记。

`QUOTA_EXCEEDED` 不自动重试，也不能显示为 Provider 故障；每次实际 Provider 调用分别预占和结算用量。

`CompletedDegraded` 只适用于确定性 mandatory checks 已全部通过后的 QA 摘要阶段。UI 必须显示“AI QA 未执行，仅完成确定性校验”，不能创建伪造 QAReview。用户可以预览和发布，但 V1 Golden Path 验收不允许使用该降级路径。

### 8.3 自动修复输入输出

```text
Input
  AppSpec + ValidationReport + QAReview + repair_attempt=0
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

自动修复不得改变已审批 Blueprint 的页面和模块范围。需要改变范围时，必须生成新 Blueprint 并重新进入 Human-in-the-loop。

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

或 QA 降级

stage.started
qa.degraded           reason / validation_report_id
run.completed_degraded
```

事件先持久化，再通过 SSE 推送。浏览器重连后按 `event_id` 重放。Trace 用于工程排障，不能向用户展示 Chain of Thought。

## 10. 配额与并发

- 每个实际 Provider 调用单独预占并结算用量，包括 schema retry 和 repair。
- Team Mode 的角色顺序执行，因此一个 Run 不产生并行 LLM 预占。
- 同一账户的多个 Session 共享 Quota Account，预占必须使用数据库事务。
- `QUOTA_EXCEEDED` 默认不自动重试；Run 保留当前 Artifact 并进入 Needs input，只有下一条定义的 QA 摘要阶段例外。
- 配额在 Product Manager/Designer/Engineer 阶段耗尽时，用户只能编辑输入、查看/导出现有结果或等待管理员重置；不能继续 Build。
- 配额仅在确定性 Validation 已通过后的 QA 摘要阶段耗尽时，允许进入 `CompletedDegraded`。
- 用户取消 pending approval 时不发生新的模型调用或配额消耗。

## 11. 代码归属

```text
another_atom/agent/
├── orchestrator.py       固定状态机与阶段推进
├── context.py            Stage Context 组装与裁剪
├── approvals.py          Human-in-the-loop Contract
├── repair.py             有限修复规则
├── roles/
│   ├── product_manager.py
│   ├── designer.py
│   ├── engineer.py
│   └── qa.py
├── prompts/              版本化 role instruction
└── tracing.py            StageRun / usage / trace 记录
```

Pydantic Contract 仍统一放在 `another_atom/contracts/`。Agent 目录只能引用 Contract，不能再定义一套 Blueprint、AppSpec 或 ValidationReport。

## 12. V1 Agent 验收标准

- Team Mode 严格按 Product Manager -> Designer -> Engineer -> QA 推进，同一时刻只有一个主阶段。
- Engineer Mode 仍执行 Blueprint 审批、结构化校验、Build 和 Validation。
- 未审批或已失效的 Blueprint approval 不能创建 Build Job。
- 每个角色输出都有 Artifact ID、版本、hash、prompt version、usage 和 trace。
- 下一角色只接收显式 Artifact 与阶段最小上下文，不接收隐藏长期记忆。
- V1 Agent 没有 Shell、文件、网络、数据库或 Publish Tool。
- mandatory check 不能被 QAReview 覆盖；自动修复最多 1 轮并完整重建、复验。
- 正常 Team Mode 的 QAReview 包含摘要、warning、Evidence 和可执行建议；`CompletedDegraded` 必须明确标注且不能用于 Golden Path 验收。
- 进程重启或 SSE 重连后，Run、pending approval、StageRun 和事件可以恢复。
- 跨用户或跨 Project 的 Context、Artifact、日志和事件泄漏数量为 0。
