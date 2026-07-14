# Another Atom V1 Human-in-the-loop 审批机制

[toc]

- **文档状态：** V1 技术设计基线；持久化 HumanTask、PM 补充输入和 Blueprint adapted 审批已实现，通用 Risk Policy 适配器待扩展
- **技术范围：** 通用 Approval Contract、业务适配器、Risk Policy 接入、状态机、API、持久化、并发、恢复、事件与验收
- **合并流程基线：** [统一 Chat 与 Human-in-the-loop](../产品设计/06-统一Chat与Human-in-the-loop.md)；本文重点展开 `approval`，`input_request` 以合并流程为准
- **产品设计：** [V1 Human-in-the-loop 用户审批](../产品设计/04-[TODO]-Human-in-the-loop用户审批.md)
- **PM 专项设计：** [PM 整理产品方案并由用户确认](../产品设计/05-[TODO]-PM整理产品方案并由用户确认.md)
- **Agent 基线：** [V1 多 Agent 设计](./01-[Agent]-多Agent设计.md)
- **对话修改：** [V1 基于现有代码的对话式 AI Coding](./02-[Agent]-基于现有代码的对话式AI-Coding.md)
- **工程基线：** [V1 系统架构](./03-[工程]-系统架构.md)
- **当前实现检查：** [20｜Project 对话路由与代码修改授权检查](../../../review/待办/20-[综合]-2026-07-14-Project对话路由与代码修改授权检查.md)

## 背景

当前 V1 已在首次 Build 中实现一条最小审批纵切：supported Blueprint 自动继续，adapted Blueprint 持久化为 `awaiting_approval`，所属用户确认后通过 CAS 创建唯一 BuildJob。但现有 `Approval` 仍是“一次 Run 对应一个 Blueprint 布尔确认”，不能统一表达范围变化、额外预算、破坏性 Diff、dirty worktree、Restore 和 Deployment 等风险对象。

本文在保留当前纵切兼容性的前提下，定义可由固定工作流、Risk Policy 和显式操作共同复用的 Approval 控制面。核心问题不是增加更多弹窗，而是让不同业务共用精确对象绑定、状态 CAS、用户归属、审计和恢复机制，同时把 ProductSpec 生成、预算计算、Git 操作和 Deployment 执行留在各自业务层。

## 摘要

- **复用控制面**
  - 固定工作流、Risk Policy 和显式操作使用相同 Approval Contract；业务只提供 subject、gate source 和批准后的恢复适配器。
- **决策所有者**
  - Agent 只产出结构化事实和风险提示；业务工作流或确定性 Runtime 决定是否请求 Approval，Agent 不能自行批准或绕过。
- **两阶段判断**
  - 执行前根据范围、能力和预算判断；候选生成后根据真实 SourceDiff 再检查破坏性影响，避免只相信模型自报。
- **精确绑定**
  - Approval 绑定 subject ID、version/hash、基线版本、风险原因和预算上限，对象变化后进入 stale。
- **事务与并发**
  - 决定使用状态 CAS；决定记录、Run 推进、额度预占和恢复 Job 在同一事务中建立唯一事实，重复点击不能重复执行。
- **等待不占写锁**
  - 风险审批等待期间保留 Artifact 但不长期占用 Project 写锁；批准后重新取得写占用并校验基线。
- **可恢复证据**
  - pending、决定、Artifact 和事件持久化；成功、失败、拒绝和取消均写回 Project 对话，不保存 Chain of Thought。

## 1. 技术结论

Human-in-the-loop 由业务流程、通用 Approval Service 和业务恢复适配器组成：

```text
Business Workflow 生成 subject
           |
           v
Gate Source
  |-- workflow：固定门禁
  |-- risk_policy：风险判断
  `-- explicit_action：显式高影响操作
           |
           v
Generic Approval Service
  状态 / owner / subject hash / CAS / 事件 / 恢复
           |
           v
Business Resume Adapter
  Architect / Agent stage / Repository / Deployment
```

- **业务流程** 生成 subject 并声明触发来源。ProductSpec 固定请求确认；范围、预算和 Diff 由 Risk Policy 判断；Restore 和 Publish 由用户显式操作触发。
- **Approval Service** 保存用户对精确 subject 的决定，不生成 ProductSpec，也不直接执行 Git、预算或 Deployment 操作。
- **Resume Adapter** 在批准后重新校验 subject 与业务前置条件，并以幂等方式恢复准确阶段。

Approval 不能替代 Capability Policy、Validator、Sandbox、租户校验或版本 CAS。`deny` 结果不能通过插入 Approval 改写成允许。

### 1.1 通用控制面与业务适配器

通用层只接受一个稳定接入 Contract：

```text
ApprovalRequest
  gate_source
  gate_version
  approval_type
  subject_type / subject_id / subject_version / subject_hash
  project_id / run_id / user_id
  effect_summary / reason_codes
  resume_kind / resume_ref
```

业务适配器必须实现：

```text
build_subject()             生成服务端可信 subject
recompute_subject_hash()    决定时重新计算当前 hash
on_approved()               建立唯一恢复 operation/job
on_rejected()
on_cancelled()
```

Approval Service 不回调任意业务函数或执行 Agent Tool。`resume_kind + resume_ref` 只用于由 Runtime 选择注册过的固定适配器，不能由客户端或模型指定可执行代码。

### 1.2 V1 复用映射

| 业务 | gate source | approval type | subject | resume adapter |
| --- | --- | --- | --- | --- |
| PM ProductSpec | workflow | `product_spec` | generation：规范化 generation ID + 简介 hash + Markdown blob SHA | `resume_architect` |
| Project 代码修改 | workflow | `project_change` | ChangeBrief hash + base version/commit + Contract hashes + source manifest hash | `start_change_run` |
| 范围变化 | risk_policy | `scope_change` | ProductSpec Delta / RequirementDelta | `resume_change_run` |
| 额外预算 | risk_policy | `budget_increase` | budget version + limit | `resume_agent_stage` |
| 破坏性 Diff | risk_policy | `destructive_diff` | SourceDiff hash + base version | `resume_materialization` |
| 丢弃 worktree | explicit_action | `discard_worktree` | worktree hash | `execute_repository_operation` |
| Restore | explicit_action | `restore_version` | current/target version | `execute_repository_operation` |
| Publish/Update/Unpublish | explicit_action | deployment type | deployment target hash | `execute_deployment_operation` |

### 1.3 PM ProductSpec 与通用层的区别

PM 专项流程负责生成简介和 `docs/product-spec.md`、检测用户修改、进入 `needs_regeneration`、重新调用 PM、展示文档 Diff，并在批准后组装“简介 + 完整 Markdown”的 Architect Handoff。通用层只保存对当前 generation subject 的决定；用户修改简介或 Markdown 时，PM 流程通知通用层把旧 pending Approval 标记为 stale。

因此 ProductSpec 不得再建立自己的 `approved=true`、owner 校验、CAS 或恢复状态机；通用 Approval 也不得吸收 Markdown 读写、模型重写和 Architect Context 组装。

## 2. 当前实现与目标差距

### 2.1 当前纵切

当前实现包括：

- `RunStatus.AWAITING_APPROVAL` 和 `current_stage=blueprint_approval`；
- `approvals(run_id unique, user_id, artifact_id, approved, payload)`；
- `POST /api/runs/{run_id}/approve`；
- `awaiting_approval -> build_queued` 条件更新 CAS；
- Approval、Blueprint Artifact、BuildJob 和事件在一次数据库事务中提交；
- `build_jobs.run_id` 与 `approvals.run_id` 唯一约束；
- `approval.required / approval.confirmed` 持久化事件；
- 并发确认最多创建一个 Approval 和 BuildJob。

该纵切只覆盖 adapted Blueprint 的批准路径。pending 请求当前由 Run 状态、Blueprint Artifact 和 `approval.required` 事件表达，`Approval` 行只在用户确认时创建；当前表结构无法表达多个不同风险对象，也没有 rejected、cancelled、stale、subject hash、budget limit 和失效原因。当前 `save_artifact` 还会按 `run_id + artifact_type` 更新既有 Artifact payload，因此通用 Approval 不能直接假设现有 artifact ID 已经具备不可变版本语义。

Project 代码修改已新增一个批准前不建 Run 的专用纵切：Lead 的任务卡以 `ProjectMessage(message_type=change_proposal)` 保存 pending/approved/stale，专用 approve API 重新校验 base version，成功后才创建 `ai_edit` Run、BuildJob 和写占用，重复批准返回同一 Run。它解决了当前交互授权，但不等于通用 Approval：没有独立 subject 表、reject/cancel、统一查询或 Risk Policy，后续仍需按本文 Contract 迁移。

### 2.2 目标差距

通用化需要补齐：

- `workflow / risk_policy / explicit_action` 三种 `gate_source`；
- ProductSpec 的不可变 generation、`product_spec` Approval 和 `resume_architect` 适配器；
- 由 Runtime 固定注册、不可由客户端或模型选择任意代码的业务恢复适配器；
- 统一 `RiskDecision` 与原因码；
- Approval subject 的类型、版本和 hash；
- 一个 Run 中按阶段出现不同 Approval 的能力；
- 拒绝、取消、失效和重新请求；
- 对话修改的执行前 Gate 与提交前 Diff Gate；
- 将已实现的 Project `change_proposal` 专用 Gate 迁移为通用 `project_change` Approval subject；
- pending 等待期间的锁释放、批准后的基线重验；
- budget、worktree、version、project 和 deployment 动作适配器；
- Project 对话结果卡片和通用查询/决定 API。

## 3. Risk Policy

Risk Policy 只是通用 Approval 的一种触发来源，不负责固定工作流门禁和用户显式操作。首次 ProductSpec 是否需要确认由 PM workflow 决定，Restore、Publish 等由对应 Service 在用户发起操作后请求；只有范围、预算和实际 Diff 等条件性风险进入本节判断。

### 3.1 输入事实

Risk Policy 只读取已验证的 Contract 和 Runtime Evidence：

```text
RiskInput
  operation
  project_id / run_id / user_id
  base_version_id / base_git_commit
  blueprint / change_brief / requirement_delta refs
  subject artifact id / version / hash
  source_diff stats and removed paths?
  base budget / spent / requested increment?
  capability policy result
  ownership and concurrency facts
```

Agent 可以在 Artifact 中输出 `impact` 或 `risk_reasons`，但这些字段只作为输入。Runtime 必须独立计算 support level、预算差额、Diff 删除量、版本指针、dirty 状态和公开状态。

### 3.2 输出 Contract

```text
RiskDecision
  outcome: auto_authorize | require_approval | deny
  approval_type?
  subject_type?
  subject_id?
  subject_version?
  subject_hash?
  risk_level: light | destructive | public
  reason_codes[]
  effect_summary
  preserved_state[]
  budget_limit?
  policy_version
```

建议 V1 原因码至少包含：

```text
SCOPE_ADAPTED
SCOPE_CHANGED
BUDGET_INCREASE
DESTRUCTIVE_DIFF
CAPABILITY_UNSUPPORTED
OWNERSHIP_DENIED
BASE_VERSION_CONFLICT
VALIDATION_BLOCKED
```

后四类必须输出 `deny` 或已有错误状态，不能请求用户批准后绕过。Restore、Deployment 等显式操作不经过 Risk Policy 伪装成条件判断，由对应 Service 直接构造带当前对象和实际影响的 ApprovalRequest。

### 3.3 两阶段 Gate

对话修改不能只在一个时点判断风险：

1. **Pre-execution Gate**
   - Lead 形成 ChangeBrief 后由 workflow 固定触发，不依赖 Risk Policy 决定是否显示；
   - subject 绑定基线版本/commit、有效 Contract hash 和全量源码 manifest hash；
   - Risk Policy 在卡片上补充范围变化、能力适配和预计预算；
   - 用户点击“修改代码”前不创建 `ai_edit` Run、BuildJob 或写占用。
2. **Pre-commit Gate**
   - SourcePatchSet 在隔离候选工作区 apply，并由 Runtime 重新生成 SourceDiff 后执行；
   - 判断真实删除文件、删除行数、入口变化和关键模块替换；
   - 命中后保留候选 Artifact 和 Evidence，但不创建 ProjectVersion。

如果执行前 Approval 的 subject 已经包含明确的允许范围，且实际 Diff 未扩大，不再重复请求。实际影响扩大时必须创建新的 subject 和 Approval。

### 3.4 ProductSpec 中的能力适配

PM 必须在 ProductSpec 中写明 preserved、mapped、omitted 和验收边界，但这些内容属于 ProductSpec generation，不由 Risk Policy 重新生成。首次 ProductSpec 通过 `workflow` gate 一次性确认完整方案；如果 Capability Policy 返回 unsupported，则进入 Needs input，不能创建一个可绕过限制的 Approval。大模型翻译软件的具体产品语义见 [PM 整理产品方案并由用户确认](../产品设计/05-[TODO]-PM整理产品方案并由用户确认.md)。

## 4. Approval Contract

### 4.1 数据模型

```text
Approval
  id
  user_id
  project_id
  run_id?
  trigger_message_id?
  gate_source: workflow | risk_policy | explicit_action
  gate_version
  approval_type:
    product_spec | adapted_scope | scope_change | budget_increase
    | destructive_diff | discard_worktree | restore_version
    | delete_project | publish | update | unpublish
  subject_type: artifact | budget | worktree | version | project | deployment
  subject_id
  subject_version?
  subject_hash
  base_version_id?
  risk_level: light | destructive | public
  reason_codes[]
  effect_summary
  preserved_state[]
  budget_limit?
  requested_by_stage
  policy_version?
  resume_kind
  resume_ref
  status: pending | approved | rejected | cancelled | stale
  decided_by_user_id?
  decision_payload?
  created_at
  decided_at?
  invalidated_at?
  invalidation_reason?
```

`subject_hash` 由服务端对规范化对象计算，客户端不能指定可信 hash。可编辑 Artifact 被修改后，服务端先创建新 Artifact/version 并让对应业务适配器重新判断：ProductSpec 进入 `needs_regeneration`，风险对象重新执行 Risk Policy，显式操作重新读取当前目标；不能把编辑后的内容塞进旧 Approval。

### 4.2 唯一性

- 同一 `approval_type + subject_type + subject_id + subject_hash` 最多存在一个 pending Approval；
- 一个 Run 可以按不同阶段拥有多个历史 Approval，不能继续使用当前全局 `run_id unique`；
- 同一 Approval 只能从 pending 原子迁移到一个终态；
- approved 不代表副作用已经完成，实际动作必须另有唯一 operation/job 事实；
- 旧 subject 变化时标记 stale，不能删除历史决定后复用相同 ID。

### 4.3 决定语义

| Approval 决定 | Approval 状态 | Run / Action 结果 |
| --- | --- | --- |
| approve | approved | 重新校验并恢复精确动作 |
| reject | rejected | Run 进入 needs_input 或结束独立动作 |
| cancel | cancelled | Run/Action 取消等待，不产生额外副作用 |
| subject changed | stale | 旧决定不可用，重新执行 Risk Policy |

Run 状态与 Approval 状态是不同事实。一个 Run 可以等待 Approval，也可以在 Approval approved 后因基线变化进入 Needs input；不能把“批准”直接等同于“动作成功”。

## 5. 状态机集成

### 5.1 首次 Build

```text
ProductRunning
  -> ProductSpecGenerating
       |-- provider failed -> ProductSpecFailed
       `-- ProductSpecGenerated -> CapabilityCheck
              |-- unsupported -> NeedsInput
              `-- supported / adapted -> AwaitingProductApproval
                     |-- summary or Markdown edited
                     |      -> Approval stale -> NeedsRegeneration
                     |      -> ProductSpecRegenerating -> AwaitingProductApproval
                     |-- approved -> revalidate generation -> resume_architect
                     |-- rejected -> NeedsInput
                     `-- cancelled -> Cancelled
```

首次确认固定使用 `gate_source=workflow`，不调用 Risk Policy 决定是否显示 Approval。`resume_architect` 只接受已批准 generation 的简介与完整 ProductSpec；不能直接把编辑后、未重新生成的文档交给 Architect。当前 `/runs/{run_id}/approve` 作为 Blueprint 兼容入口保留，但内部应逐步转为“找到 pending Approval -> 决定 -> 恢复动作”的通用服务。

### 5.2 对话修改

```text
ChangeBrief + RequirementDelta
  -> PreExecutionRiskCheck
       |-- pending approval -> 不占 Project 写锁
       `-- authorized
              |
              v
       acquire Project write CAS + verify base
              |
              v
       Candidate + SourceDiff + Validation
              |
              v
       PreCommitRiskCheck
       |-- pending approval -> 保存候选并释放写锁
       `-- authorized
              |
              v
       reacquire write CAS + verify base/subject hash
              |
              v
       VersionMaterialization
```

Risk Approval 等待期间不能无限占用 `active_write_run_id`。批准后如果 Project.latest_version、base commit、dirty state 或 subject hash 已变化，Approval 标记 stale，Run 进入 Needs input 或基于新事实重新判断，不能自动 rebase 或覆盖。

### 5.3 独立用户动作

Restore、删除、丢弃 worktree 和 Deployment 不由 Agent 直接执行。对应 Service 负责：

1. 读取服务端当前对象并生成 RiskInput；
2. auto authorize 或创建 Approval；
3. 用户决定后重新读取对象；
4. 以 operation id、版本 CAS 或 Deployment CAS 执行一次；
5. 持久化结果事件并写回 Project 时间线。

## 6. API

### 6.1 当前兼容接口

```text
POST /api/runs/{run_id}/approve
  body: BlueprintApproval
```

该接口当前只允许 `awaiting_approval` Run，CAS 成功后保存 Blueprint、Approval、BuildJob 和事件。扩展期间必须保持现有 Studio 与测试可用。

### 6.2 通用接口

```text
GET /api/projects/{project_id}/approvals?status=pending
GET /api/approvals/{approval_id}

POST /api/approvals/{approval_id}/decide
  decision: approve | reject | cancel
  observed_subject_hash
```

规则：

- owner 从认证 Session 获取，不接受客户端指定；
- 查询必须通过 Approval -> Project owner 联查；
- `observed_subject_hash` 只用于发现用户决定时页面已过期，服务端仍重新计算可信 hash；
- 非 pending Approval 返回当前状态或 `APPROVAL_NOT_ALLOWED`，但绝不能再次执行副作用；
- UI 修改 Artifact 时调用对应 Artifact/Blueprint 更新接口，不通过 decide payload 偷换 subject。

## 7. 事务、并发与幂等

### 7.1 请求 Approval

创建 Approval、Run 进入 `awaiting_approval`、`approval.required` 事件必须在同一数据库事务中提交。事务失败时三者都不能表现为成功。

### 7.2 决定 Approval

批准路径使用条件更新：

```text
UPDATE approvals
SET status = approved, decided_by_user_id = :user, decided_at = :now
WHERE id = :approval_id
  AND user_id = :user
  AND status = pending
  AND subject_hash = :current_subject_hash
```

更新行数不是 1 时停止，不创建 Job 或执行动作。CAS 成功后，在同一事务中：

- 更新相关 Run/Action 状态；
- 建立唯一恢复 Job 或 operation record；
- 按批准的 budget limit 预占额外额度（如涉及）；
- 写入 `approval.confirmed` 与恢复事件。

事务提交后才通知进程内 Worker；通知丢失时由持久化 Job 扫描恢复。

### 7.3 一次副作用

- BuildJob 继续以 `run_id` 唯一；
- AI 修改提交以 Run/VersionMaterialization 唯一；
- Restore、worktree discard、delete 和 Deployment 使用独立 operation id；
- Approval ID 只证明授权来源，不替代每类操作自己的幂等键；
- 并发双击、HTTP 重放和 Worker 重领最多产生一个业务结果。

## 8. 配额

- Risk Policy 是确定性逻辑，不消耗模型额度；
- 创建、查看、拒绝或取消 Approval 不调用 Provider；
- 额外预算 Approval 绑定本轮最大增量和用途，不是账户永久额度；
- 额外额度只在批准事务成功后预占；拒绝、取消、stale 或恢复失败释放未使用 reservation；
- 已经发生的 Provider 请求按实际观测结算，用户拒绝后不能抹去已发生用量；
- subject 或预算上限变化后旧批准失效。

## 9. Artifact、对话与事件

### 9.1 Artifact 保留

Approval 不修改已有 Artifact：

- 批准前的 Blueprint、ChangeBrief、RequirementDelta、SourcePatchSet、SourceDiff 和 ValidationReport 继续保留；
- 用户编辑时创建新 Artifact/version，并通过 parent 引用保留来源；
- 失败、拒绝或取消不会删除已生成 Artifact；
- 未通过门禁的候选 Artifact 不进入 ProjectVersion，也不移动 Git/Deployment 指针；
- 不保存 Chain of Thought、Provider Secret 或完整隐私日志。

### 9.2 对话结果

首次 Build 使用 Run 时间线；已有 Project 的修改同时写入 ProjectMessage：

- `approval_requested`：风险摘要、subject 引用、用户可见影响；
- `approval_decided`：决定、决定者、决定时间、当前安全状态；
- `run_result`：成功版本或失败证据，以及关联 Approval；
- 新 attempt 通过 parent run/message 引用上一轮，不复制隐藏上下文。

### 9.3 事件

V1 事件至少包括：

```text
approval.required
approval.confirmed
approval.rejected
approval.cancelled
approval.stale
run.awaiting_approval
run.resumed
```

事件 payload 记录 `approval_id / gate_source / gate_version / approval_type / subject_type / subject_hash / reason_codes / policy_version?`，不记录完整源码和模型私有推理。事件先持久化，再通过 SSE 推送；重连只补取事件，不重新决定 Approval。

## 10. 安全边界

- 只有 Project 所属用户能读取和决定 Approval；管理员观察后台不能代批；
- subject 从服务端资源重建，不能相信客户端提供的 Project ID、hash、文件内容或预算；
- `approved` 不能绕过 Capability Policy、Validator mandatory failure、Sandbox、租户校验或 Deployment 权限；
- unsupported 能力返回 deny/Needs input，不产生可放行 Approval；
- Agent、Lead 和 Reviewer没有决定 Approval、写数据库、操作 Git 或 Publish 的 Tool；
- 公开状态改变必须由独立 Deployment Service 校验目标 Version 已通过门禁；
- Approval 和决定日志按现有用户数据生命周期保存，不在公开 URL 暴露。

## 11. 恢复与失败

- pending Approval 持久化，进程重启后保持 pending，不自动批准；
- SSE 断线不改变状态；客户端重连后读取 Approval 与事件；
- approved 与恢复 Job 在同一事务建立，Worker 重启后从持久化 Job 继续；
- approved 后发现 subject/base 已变化，标记 stale，不执行旧动作；
- Provider、Build、Validator 或 Deployment 在批准后失败，Approval 历史保持 approved，但 Run/Action 记录真实失败；
- 失败结果与已有 Artifact 回到 Project 对话，用户可以继续提出调整或创建关联 attempt；
- 重试只复用输入 hash 仍一致的 Artifact，不能因为“曾经批准”而跳过新对象的 Risk Policy。

## 12. 测试与验收

### 12.1 Risk Policy 单元测试

- 已批准 ProductSpec 下的 supported 范围 + 基础预算 -> auto_authorize；
- ProductSpec 批准后新出现的 adapted 范围、范围增删、预算增加和破坏性 Diff -> require_approval；
- unsupported、跨用户、mandatory failure、基线冲突 -> deny；
- 实际 Diff 未扩大已批准范围时不重复请求；扩大时生成新 subject；
- subject 规范化后相同输入产生稳定 hash。

### 12.2 Contract 与 API 测试

- ProductSpec 使用 `workflow + product_spec + resume_architect`，不依赖 Risk Policy；
- Restore 和 Deployment 使用 `explicit_action` 创建 Approval，不依赖 Risk Policy；
- 只有 owner 可以查询和决定；
- subject 编辑后旧 Approval 进入 stale；
- approve/reject/cancel 只能有一个终态；
- 非 pending 决定不能重复执行；
- 客户端伪造 subject hash、Project、预算或 Blueprint 不能绕过服务端重算；
- 当前 `/runs/{run_id}/approve` 兼容 adapted Blueprint 路径。

### 12.3 集成与恢复测试

- supported 与 adapted ProductSpec 均等待确认，只有批准的 generation 能进入 Architect；
- 用户编辑简介或 Markdown 后确认入口失效，重新生成后创建新的 subject 和 Approval；
- Architect Handoff 同时包含批准的简介和完整 Markdown，hash 不一致时不恢复；
- 当前兼容路径仍保证 adapted Blueprint 确认后只创建一个 BuildJob；
- 两个并发批准只有一个 CAS 成功且只产生一个业务结果；
- pending 时重启，状态和 Artifact 可恢复且没有自动执行；
- 决定事务提交后通知丢失，Worker 仍能领取持久化 Job；
- 修改 Run 等待 Pre-execution Approval 时不持有 Project 写锁；
- Project change Approval 批准前不存在修改 Run；批准事务只创建一个 Run/BuildJob，并重新校验 Contract 与全量源码 manifest hash；
- Engineer 只返回 SourcePatchSet，Runtime 在隔离候选工作区 apply；Patch 无法 apply 或越权时不写当前版本；
- Pre-commit Approval 前不创建 ProjectVersion，批准后基线变化则 stale；
- 拒绝、取消和失败都不移动 Git、当前版本与线上版本；
- 额外预算只在批准后预占并按实际请求结算；
- 双用户不能交叉读取 Approval、Artifact、事件或决定结果。

## 13. 实施顺序

1. **[Contract 统一]** 新增 `gate_source`、subject、resume adapter、通用 Approval 字段和状态；保留现有 Blueprint endpoint 兼容层。
2. **[决定服务]** 实现通用查询/决定 API、CAS、事件、固定适配器注册和持久化恢复 Job。
3. **[PM 接入]** 接入不可变 ProductSpec generation、编辑后 stale、重新生成和 `resume_architect`。
4. **[Policy 收敛]** 把范围、预算、实际 Diff 和 deny 条件集中到确定性 Risk Policy。
5. **[对话修改]** 接入 `project_change` workflow Gate、“修改代码”按钮、批准后建 Run、Pre-commit Gate、stale 处理和 ProjectMessage 结果卡片。
6. **[高影响动作]** 接入 dirty worktree、Restore、删除和 Deployment operation adapter。
7. **[验证]** 完成并发、重启、配额、双用户和 Railway 持久化验收。

不能先让各 API 自己弹窗并保存一个 `approved=true`。没有统一 gate source、subject、hash、决定状态和恢复适配器时，不同入口会形成互相不兼容的审批语义。

## 14. V1 边界与 V2 兼容

V1 Approval 只服务单用户 Project、固定 Agent 流水线和当前已接入的受控 Runtime Adapter；现阶段执行链主要是 Web Adapter。不实现组织审批、多审批人、永久授权、Tool Permission Center 或跨 Project 批量决定。

V2 可以复用 Approval 的 owner、subject version/hash、状态 CAS、事件和恢复 Contract，并扩展：

```text
subject_type += tool_request | budget_change | arbitration
```

TaskGraph、ToolRequest 和 Arbitration 可以产生 Approval，但仍不能改变以下不变量：对象变化即失效、pending 不自动批准、拒绝无副作用、批准不覆盖确定性安全门禁。
