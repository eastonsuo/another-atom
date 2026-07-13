# Another Atom V1 基于现有代码的对话式 AI Coding

[toc]

- **文档状态：** V1 技术设计草案，待评审
- **功能范围：** 已有 Project 中的 Lead 对话、增量修改、校验、版本与恢复
- **产品设计：** [V1 通过对话修改现有项目](../产品设计/03-通过对话修改现有项目.md)
- **Agent 基线：** [V1 多 Agent 设计](./01-[Agent]-多Agent设计.md)
- **工程基线：** [V1 系统架构](./03-[工程]-系统架构.md)

## 背景

当前固定团队面向首次 Build，Engineer 只接收原始 Prompt、Blueprint 和 ArchitectureSpec；已有 Project 的代码、版本和历史修改尚未形成可供 Agent 使用的增量 Contract。本文定义基于现有代码继续修改所需的技术闭环。

## 摘要

Runtime 为每轮修改组装 Project Context、ChangeBrief 和基线源码快照，再按固定流水线生成候选 AppSpec，由平台计算文件 Diff、执行校验，并以版本 CAS 和 Git commit 写回同一 Project。Agent 不直接互聊、不自行决定下一个角色，也不能绕过权限、配额、重试上限或发布控制。

## 1. 技术结论

这项功能不让 Agent 彼此直接聊天，也不让 Lead 直接调用 Engineer。Agent 之间通过 Runtime 顺序调度和不可变 Artifact 协作：

```text
Project Message
      |
      v
Runtime 组装 Project Context
      |
      v
Lead -> ProjectLeadDecision
      |
      +-- answer / clarify -> ConversationMessage -> End
      |
      `-- modify -> ChangeBrief -> Risk Policy
                                      |
                                      v
                         V1 固定下游流水线
                                      |
                         Requirement / Design Delta
                                      |
                                      v
                   BaseSourceSnapshot -> Engineer -> Candidate AppSpec
                                      |
                                      v
                         Runtime Source Diff + Validator
                                      |
                                      v
                              Quality Review
                                      |
                                      v
                       ProjectVersion + Git commit
```

每个角色只接收当前阶段需要的 Contract；它的输出先经过 Schema 校验并持久化，下一角色再读取该 Artifact。角色看不到其他角色的隐藏推理，也不能自行决定下一个角色、重试次数、仓库写入或发布。

现有 Runtime 可以复用的部分：

- Provider Adapter 和 Pydantic 结构化输出；
- Orchestrator 固定阶段推进；
- Artifact 阶段检查点；
- 阶段级配额预占与结算；
- BuildJob Lease 与 Worker 恢复；
- Validator、ProjectVersion 和本地 Git。

必须新增的部分：

- Project 对话消息与异步 Lead 处理；
- 修改任务和基线版本 Contract；
- 基于已有代码的增量阶段输入；
- Runtime 计算的文件 Diff；
- Project 单写任务、版本 CAS 和 Git 幂等物化；
- 修改失败后按 Artifact 恢复，而不是整轮重跑。

## 2. 当前实现与目标差距

当前首页 `POST /api/lead/messages` 只接收单条消息，`LeadMessage` 只绑定用户，不绑定 Project、Session、Run 或 Version。Lead 只能判断 `direct/team`，无法回答“在当前 v3 上改什么”。

当前结构化 Revision 直接修改 AppSpec 的标题、正文和主色，不调用 Agent；现有固定团队只支持首次 Build。Engineer 的输入是原始 Prompt、Blueprint 和 ArchitectureSpec，没有基线 Git commit、已有源码或修改任务。

因此不能通过给现有 Prompt 前面拼一句“基于已有代码修改”来实现。这样无法证明：

- 模型读到的是哪个版本；
- 未要求变化的代码是否被保留；
- 变更文件和 Diff 是否真实；
- 执行期间版本变化后谁覆盖谁；
- Worker 重启后应复用哪个阶段；
- 新版本是否对应正确 Git commit。

## 3. 协作模型：Agent 不互调，Runtime 传递 Handoff

### 3.1 调用原则

Provider 仍是普通结构化调用接口。Orchestrator 决定顺序：

```text
output_A = provider.call_A(context_A)
artifact_A = validate_and_persist(output_A)

context_B = assemble(base_snapshot, artifact_A)
output_B = provider.call_B(context_B)
artifact_B = validate_and_persist(output_B)
```

Agent A 不持有 Agent B 的地址，也不发送消息给 Agent B。所谓“交接”是 Runtime 将 A 的已验证 Artifact ID 放入 B 的 Context。这样可以单独重试 B、复用 A，并在失败后判断哪个 Contract 仍有效。

### 3.2 修改流水线

本功能不改变 V1 的固定团队，只把首次生成的全量 Contract 改成基于基线的增量 Contract。当前代码中的具体角色名称继续以 [V1 多 Agent 设计](./01-[Agent]-多Agent设计.md) 为准，本篇只定义修改语义：

| 阶段 | 核心输入 | 输出 | 不允许做的事 |
| --- | --- | --- | --- |
| Lead | 用户消息、Project 摘要、基线版本、选中对象 | `ProjectLeadDecision`、可选 `ChangeBrief` | 直接改代码、选择跳过角色、发布 |
| 产品阶段 | `ChangeBrief`、当前 Blueprint | `RequirementDelta` | 重写整个产品、扩大 Runtime 能力 |
| 设计阶段 | `ChangeBrief`、`RequirementDelta`、当前设计/架构 Contract | `DesignDelta` | 无依据重构、修改未授权范围 |
| 工程阶段 | 前述 Delta、`BaseSourceSnapshot`、当前 AppSpec | `CandidateAppSpec` | 使用 starter template、执行 Tool、写 Repository |
| 数据/质量分析 | 候选 AppSpec、基线与候选 Diff | 增量数据/质量 Artifact | 修改候选代码、覆盖确定性证据 |
| Runtime Validator | 基线、候选源码、有效需求与设计 Contract | `ValidationReport` | 接受模型自报的通过结论 |
| 最终复核 | 全部 Artifact、Diff、ValidationReport | 接受、返工或需要输入 | 覆盖 Validator 失败、创建版本、发布 |

### 3.3 为什么仍用固定流水线

V1 继续固定执行的原因是现有 Artifact、配额、状态和恢复均按顺序阶段建立。小改动也运行完整阶段，延迟和成本更高，但避免在本功能中同时引入角色选择、TaskGraph、并行和 Artifact 合并。

按任务跳过设计或数据阶段属于 V2。V1 可以让某个阶段输出“无变化，沿用基线”，但不能悄悄不执行该阶段。

## 4. 新增 Contract

以下是目标 Contract，不是当前已实现字段。正式实现时放入 `another_atom/contracts/`，不能在 API、Provider 和 Worker 中分别定义三套结构。

### 4.1 ConversationMessage

```text
id
project_id
session_id
user_id
role: user | lead | system
message_type: text | clarification | change_brief | result | error
content
intent: ask | clarify | modify | retry
run_id?
base_version_id?
context_refs[]
status: queued | routing | completed | failed | cancelled
idempotency_key
created_at / updated_at
```

约束：

- `project_id / user_id` 在写入时由 Session 和 URL 归属校验确定，不接受客户端自报用户；
- 同一用户、Project 和 `idempotency_key` 唯一，防止重复点击创建两条消息或两次修改；
- `context_refs` 只保存允许的页面、元素、文件、错误和版本引用，不保存任意宿主路径；
- 消息保存用户可见内容，不保存 Chain of Thought。

### 4.2 ProjectLeadDecision

```text
intent: answer | clarify | modify
response
reason
change_brief?
```

首页 `LeadDecision(route=direct|team)` 不直接复用。项目对话需要区分“回答”和“缺少关键条件的澄清”，并在 `modify` 时提供结构化 `ChangeBrief`。

### 4.3 ChangeBrief

```text
schema_version
original_request
goal
preserve[]
acceptance_criteria[]
context_refs[]
base_version_id
base_git_commit
impact: scope_preserving | scope_change | destructive
risk_reasons[]
```

硬规则：

- `base_version_id` 和 `base_git_commit` 由 Runtime 注入，模型不能改写；
- `original_request` 保留用户原文，不能只保存 Lead 改写后的任务；
- `preserve[]` 和 `acceptance_criteria[]` 进入所有下游 Context；
- Risk Policy 不只相信 `impact`，还要比较 RequirementDelta、变更文件和操作类型。

### 4.4 RequirementDelta

```text
added_requirements[]
changed_requirements[]
removed_requirements[]
preserved_requirements[]
effective_pages[]
effective_modules[]
support_level
support_reasons[]
```

它描述本轮相对当前 Blueprint 的变化，不覆盖历史 Blueprint。Runtime 将基线 Blueprint、RequirementDelta 和 Capability Policy 组合成当前 Run 的 `EffectiveBlueprint` 快照，供后续阶段和 Validator 使用。

### 4.5 DesignDelta

```text
changed_pages[]
changed_interactions[]
changed_data_entities[]
changed_visual_tokens[]
preserved_design_constraints[]
implementation_notes[]
```

无设计变化时输出空 `changed_*` 和明确的保留项，不生成无意义重构。Runtime 组合基线设计 Contract 与 DesignDelta，形成当前 Run 的有效设计快照。

### 4.6 BaseSourceSnapshot

```text
project_id
base_version_id
base_git_commit
files[]:
  path
  sha256
  size
  content
source_manifest_hash
```

V1 只读取受控源码文件，例如 `index.html`、`styles.css`、`app.js` 和 `app-spec.json`。Snapshot 必须从 `base_git_commit` 读取，不能从可能存在未保存修改的 worktree 读取。

如果 Git 文件、ProjectVersion.app_spec 和物化出的 AppSpec hash 不一致，Run 进入 `BASE_SOURCE_MISMATCH`，不能由 Runtime 猜测哪个版本正确。

### 4.7 CandidateAppSpec 与 SourceDiff

Engineer 继续输出完整、可校验的 `CandidateAppSpec`，不直接返回任意 Patch。Runtime 将它物化为候选源码，再与 BaseSourceSnapshot 计算：

```text
SourceDiff
  base_version_id
  candidate_hash
  changed_files[]
  added_files[]
  removed_files[]
  per_file_before_hash / after_hash
  unified_diff
  line_stats
```

Diff 是 Runtime Evidence，不是 Agent Artifact。模型可以解释 Diff，但不能提供或修改最终 Diff 事实。

## 5. Context 如何组装和传递

### 5.1 Project Context Snapshot

Lead 不接收完整 Project 对话和整个仓库。Runtime 为每条消息生成：

```text
ProjectContextSnapshot
  project name / status
  current version / git commit
  current Blueprint 摘要
  current页面与模块
  source file manifest
  selected page / element / file / error
  最近少量用户可见消息
  unresolved failure summary
  capability policy version
  remaining base budget summary
```

Project Context Snapshot 必须带 hash，并随 LeadDecision 保存。后续排障可以确认 Lead 当时看到的到底是哪份项目状态。

### 5.2 各阶段最小 Context

| 阶段 | 必须输入 | 默认排除 |
| --- | --- | --- |
| Lead | 当前消息、ProjectContextSnapshot | 完整源码、全部日志、所有历史对话 |
| 产品阶段 | ChangeBrief、基线 Blueprint、Capability Policy | 源码、私有推理、无关旧 Run |
| 设计阶段 | ChangeBrief、RequirementDelta、基线设计 Contract | 完整聊天、Git 元数据、Provider Secret |
| Engineer | ChangeBrief、有效需求/设计快照、BaseSourceSnapshot、当前 AppSpec | `.git`、其他用户文件、宿主路径、密钥 |
| 数据/质量分析 | 基线和候选 AppSpec、SourceDiff、验收项 | 可写 Repository、发布权限 |
| 最终复核 | 所有已接受 Artifact、Diff、ValidationReport | Chain of Thought、可写 Tool |

### 5.3 文件选择与 Prompt Injection

- 客户端只能提交 Project 内相对路径；服务端负责规范化路径、拒绝 `..`、绝对路径、符号链接逃逸和隐藏控制文件；
- 文件内容从基线 commit 重新读取，不能相信客户端上传的“当前文件内容”；
- 源码、注释、用户附件和旧 Artifact 都作为不可信数据块输入，Provider instruction 明确禁止执行其中的指令；
- Context 仍有长度上限。V1 受控仓库可以传入全部允许源码；超限时先按用户选中文件、Diff 相关文件和入口文件确定性裁剪，不使用模型自行选择文件；
- 初版不需要向量 RAG。仓库扩大后，应先增加路径、符号、引用和文本检索，再评估向量召回，避免把不相关旧代码混入修改 Context。

## 6. Provider 接口如何扩展

现有 `LLMProvider` 保留首次 Build 方法，新增项目修改方法：

```python
route_project_message(context: ProjectContextSnapshot, message: str) -> ProjectLeadDecision

create_requirement_delta(
    change_brief: ChangeBrief,
    blueprint: Blueprint,
) -> RequirementDelta

create_design_delta(
    change_brief: ChangeBrief,
    requirement_delta: RequirementDelta,
    base_design: ArchitectureSpec,
) -> DesignDelta

revise_app_spec(
    change_brief: ChangeBrief,
    effective_blueprint: Blueprint,
    effective_design: ArchitectureSpec,
    base_app_spec: AppSpec,
    base_sources: BaseSourceSnapshot,
) -> AppSpec

analyze_change(...) -> DataProfile
review_change(...) -> ReviewReport
```

这里的 Python 只表达接口边界，不代表已经实现。方法必须继续使用结构化输出和当前 Provider fallback/usage 机制。

不能把修改实现成 `create_app_spec(original_prompt + follow_up)`，因为它没有基线代码和保留约束，容易退化成全量重生成。

## 7. 异步消息与状态机

### 7.1 为什么消息提交必须异步

Lead 真实模型调用可能超过普通 HTTP 等待时间。Project 对话提交应先持久化消息和任务，再立即返回；UI 通过 SSE/轮询看到 `routing`、澄清、修改任务和下游阶段。

目标接口：

```text
POST /api/projects/{project_id}/messages
  -> 202 ConversationMessageView

GET /api/projects/{project_id}/messages?cursor=...
  -> Project conversation history

GET /api/projects/{project_id}/messages/{message_id}
  -> message status / linked run / result version
```

消息由持久化 `ConversationJob` 或等价 Job 处理，不能只依赖一个没有数据库事实的 `asyncio.create_task`。进程重启后，`queued/routing` 消息必须可重新领取。

### 7.2 消息状态

```text
queued -> routing
           |-- answered -> completed
           |-- clarification_needed -> completed
           `-- change_brief_ready
                    |-- awaiting_risk_approval
                    `-- linked_to_run -> completed

routing / downstream failure -> failed
user stop before Run -> cancelled
```

### 7.3 修改 Run 状态

```text
Created(base_version)
  -> ProductDeltaRunning
  -> RiskCheck
       |-- awaiting approval
       `-- continue
  -> DesignDeltaRunning
  -> EngineerRevisionRunning
  -> CandidateMaterialized
  -> DataAnalysis
  -> Validating
       |-- resolvable -> EngineerRepair (最多一次)
       |-- failed -> NeedsInput / Failed
       `-- passed
  -> Reviewing
       |-- rejected -> NeedsInput / Failed
       `-- accepted
  -> VersionMaterializing
  -> Completed(new_version)
```

Run 保存 `intent=modify`、`trigger_message_id`、`base_version_id`、`base_git_commit` 和可选 `parent_run_id`。首次 Build 现有状态保持兼容，不用修改成同一套文案。

## 8. Human-in-the-loop 与 Risk Policy

Lead 的风险判断只是输入，最终由确定性 Risk Policy 决定。

```text
risk_input
  = ChangeBrief
  + RequirementDelta
  + base/candidate file stats
  + dirty worktree state
  + quota estimate
  + publication state
```

自动继续：当前页面/模块内的文案、样式、现有交互和明确错误修复，且在基础预算内，只创建可恢复工作版本。

必须确认：范围增删、核心模块替换、大面积删除/重写、额外预算、dirty worktree 丢弃、版本冲突和任何发布变化。

Approval 必须绑定：

```text
project_id + run_id + base_version_id
+ change_brief_hash + requirement_delta_hash
+ risk_summary + budget_limit
```

任一 hash、基线版本或预算变化后旧 Approval 失效。正常修改不进入统一 `awaiting_change_approval`，这修正了旧提案中“所有 ChangeProposal 都确认”的固定 Gate。

## 9. 源码、Diff 与候选版本

Agent 不直接写 Project Repository。工程阶段输出 CandidateAppSpec 后：

1. Runtime 执行 Pydantic 校验；
2. Renderer 在候选目录物化受控源码；
3. Runtime 比较 BaseSourceSnapshot，生成 SourceDiff；
4. Capability Policy 检查新增/删除文件和危险能力；
5. Validator 运行完整确定性检查；
6. 通过后执行质量复核；
7. 只有全部门禁通过才进入版本物化。

未变化的文件应保持 byte-level 相同。若 Renderer 会格式化所有文件，Diff 会产生噪声，因此候选物化必须采用稳定格式，或只写入确实变化的文件。

用户看到的“修改了 3 个文件”来自 SourceDiff；Agent 的文字摘要只用于解释。

## 10. 并发和版本一致性

### 10.1 Project 单写任务

V1 单实例仍需要数据库 CAS，不能只用进程内锁。Project 增加可空的 `active_write_run_id`，创建修改 Run 时执行：

```text
UPDATE projects
SET active_write_run_id = :run_id
WHERE id = :project_id
  AND active_write_run_id IS NULL
  AND latest_version_id = :base_version_id
```

更新行数不是 1 时返回 `PROJECT_WRITE_BUSY` 或 `BASE_VERSION_CHANGED`。Ask/Clarify 消息不占写锁；结构化 Edit、Vim Save、Resolve、Restore 和 AI 修改共享同一个 Project 写边界。

Run 进入 completed/failed/cancelled/needs_input 后释放写占用。启动恢复时发现 owner Run 已终止则清理；不能因为 Worker 崩溃永久锁住 Project。

### 10.2 最终版本 CAS

模型调用可能持续几十秒，最终提交前必须再次确认：

- Project.latest_version_id 仍等于 Run.base_version_id；
- Project.active_write_run_id 仍属于当前 Run；
- base Git commit 与 ProjectVersion 记录一致；
- candidate hash 与已通过校验的 Artifact 相同。

任一条件不满足时不创建当前版本，Run 进入 `BASE_VERSION_CONFLICT`。不能自动把旧候选覆盖到新版本，也不在 V1 中自动 rebase。

## 11. Git 与数据库的幂等物化

Git commit 和数据库事务无法天然原子提交。当前首次 Build 通过“同一 Run 复用既有 Build Version”缩小重复版本风险；AI 修改还需要显式 `VersionMaterialization` 记录：

```text
id
run_id                 unique
project_id
base_version_id
candidate_hash
version_id?
git_commit?
status: pending | git_committed | completed | conflicted | failed
```

推荐顺序：

1. 已通过门禁的 Candidate Artifact 和 hash 先持久化；
2. 创建唯一 `VersionMaterialization(run_id)`；
3. Repository Service 从 base commit 创建候选 commit，并在 commit metadata 中记录 `run_id + candidate_hash`；
4. 保存 `git_commit`，再用数据库 CAS 创建 ProjectVersion、更新 latest_version_id；
5. 将 Project 的受控 Git ref 幂等对齐到已提交 ProjectVersion；
6. 标记 materialization completed，释放 Project 写占用。

如果进程在第 3、4 步之间崩溃，恢复逻辑按 `run_id + candidate_hash` 查找既有 commit 并复用，不重复 commit。若最终 CAS 冲突，候选 commit 不成为 Project 当前版本，可由后续清理回收。

`ProjectVersion` 新增版本来源 `ai_edit`。只对 `source=ai_edit` 建立 `run_id` 唯一约束，避免 Worker 重领后创建两个 AI 修改版本；不能直接对所有 `(run_id, source)` 加唯一约束，因为当前结构化 Edit 会复用原 Build Run，并允许同一 Run 产生多个 Edit 版本。

Git ref 更新失败不影响已经完成的数据库事实和 ProjectVersion 预览；恢复任务根据 latest ProjectVersion 的 commit 重新对齐受控 ref。不能反过来只看 Git HEAD 推断平台当前版本。

## 12. 配额、重试与恢复

### 12.1 配额

- Lead 项目路由单独预占和结算；answer/clarify 不预占下游团队额度；
- modify 在 Risk Policy 通过后按阶段预占，不一次把整轮全部记为 used；
- Schema retry、Provider fallback 和 Engineer repair 都按实际请求结算；
- 非 LLM 失败结算已经观测到的请求并释放剩余预占；
- 追加 retry/rework 超过基础预算时进入 Approval，不自动透支。

### 12.2 阶段恢复

每个修改 Run 的 Artifact 类型唯一：

```text
change_brief
requirement_delta
effective_blueprint
design_delta
effective_design
candidate_app_spec
source_diff
data_profile
validation_report
repair_app_spec?
repair_validation_report?
review_report
```

Worker 重启后按 Artifact 恢复：已经提交的阶段不重新调用 Provider；SourceDiff 可以由相同 base/candidate hash 确定性重算；只有不存在合法 Artifact 的阶段才继续执行。

### 12.3 失败后的新 Run

用户补充要求或选择“继续修复”时创建子 Run：

```text
parent_run_id = failed_run
base_version_id = 原安全版本
input_evidence = failed checks + candidate diff + 用户补充
```

如果 ChangeBrief 和 RequirementDelta 没变，可以复用产品阶段；如果用户改变范围，则下游全部重新生成。不能仅按“上一次执行到第几步”判断复用，必须比较输入 Artifact hash。

## 13. 安全边界

- 所有消息、版本、Artifact、文件和 Run 查询都按 Session 用户与 Project owner 联查；
- Agent 仍没有 Shell、Git、数据库、网络和 Publish Tool；
- BaseSourceSnapshot 不包含 `.git`、Secret、日志、宿主路径和其他用户文件；
- 候选代码仍受离线 Web Capability Policy、CSP 和 sandboxed Preview 约束；
- 文件删除、页面删除和大面积重写先进入 Risk Policy；
- 日志记录路径和 hash，不默认记录完整源码或用户可能输入的敏感内容；
- Public Route 只读取用户明确发布的 ProjectVersion。AI 修改成功不自动 Publish/Update。

## 14. 事件与可观测性

新增用户可见事件：

```text
conversation.message_created
conversation.routing_started
conversation.answered
conversation.clarification_requested
change.brief_created
change.risk_approval_requested
change.run_created
change.stage_started / completed / failed
change.diff_created
change.validation_completed
change.version_created
change.base_conflict
```

每次 Agent Stage 至少记录：

```text
run_id / project_id / trigger_message_id
base_version_id / base_git_commit
agent_role / stage / attempt
prompt_version / model / provider
input_artifact_refs / input_context_hash
output_artifact_id / output_hash
request_count / input_tokens / output_tokens
error_code / trace_id
```

用户日志展示阶段、摘要、Diff 和失败检查；下载日志补充 Artifact 引用和错误详情，但不包含 Chain of Thought、Session token、Provider Key 或完整源码。

## 15. 错误处理矩阵

| 错误 | 系统行为 | 对已有 Project 的影响 |
| --- | --- | --- |
| Lead Provider 失败 | 消息 failed，可重试同一 idempotency key | 无 Run、无版本变化 |
| 需求仍有歧义 | clarification，等待用户补充 | 无写锁、无版本变化 |
| 配额不足 | 保存消息和 ChangeBrief，显示额度错误 | 不启动下游 |
| Project 已有写任务 | `PROJECT_WRITE_BUSY` | 当前任务继续，消息保留为草稿 |
| 基线版本已变化 | `BASE_VERSION_CHANGED` / `BASE_VERSION_CONFLICT` | 不覆盖新版本 |
| 基线源码不一致 | `BASE_SOURCE_MISMATCH` | 停止修改，保留当前版本 |
| Provider 输出无效 | 有限 Schema retry，耗尽后失败 | 已提交 Artifact 可复用 |
| Validator 可修复失败 | Engineer 最多修复一次并完整复验 | 未通过前不创建版本 |
| Validator 平台/未知失败 | 不调用 Agent 掩盖平台问题 | 当前版本不变 |
| 最终复核拒收 | Needs input/Failed | 候选和 Evidence 保留，不创建版本 |
| Git 已提交、DB 未完成时崩溃 | VersionMaterialization 恢复并复用 commit | 不重复 commit/version |
| Publish 状态存在 | 仅提示线上/工作版本差异 | 线上版本不自动变化 |

## 16. 测试与验收

### 16.1 Contract 与单元测试

- ProjectLeadDecision 三种 intent 互斥；
- ChangeBrief 的基线字段只能由 Runtime 注入；
- RequirementDelta 不能绕过 Capability Policy；
- Context 只包含允许 Artifact 和基线源码；
- SourceDiff 与实际候选文件一致；
- Risk Policy 对普通修改自动继续，对范围/破坏性/预算/发布变化请求确认。

### 16.2 集成测试

- ask 只产生对话消息，不创建 Run、BuildJob、Git commit 或 ProjectVersion；
- modify 绑定原 Project 和 base version，完整经过固定下游流水线并创建 `ai_edit` 版本；
- Engineer 输入包含基线代码和 preserve/acceptance 条件；
- 未变文件 hash 保持一致，changed_files 与真实 Diff 一致；
- 两个并发修改只有一个取得 Project 写占用；
- 结构化 Edit/Vim Save 与 AI 修改冲突时不能互相覆盖；
- 基线变化后旧候选不能提交；
- Worker 在每个阶段重启后不重复已提交 Artifact、Provider 结算、Git commit 或版本；
- Validator/质量门禁失败不创建版本；
- 新版本不改变已发布指针；
- 双用户不能读取对方消息、Context、Diff、文件或版本。

### 16.3 部署验收

- Railway 单副本重启后 queued/routing 消息与修改 Run 可恢复；
- 持久化 Volume 同时保留 SQLite、Project Git 和候选物化状态；
- 真实 Provider 完成一轮已有店铺代码修改，日志能追溯各阶段输入 Artifact 与用量；
- 浏览器刷新后对话、修改任务、阶段、Diff、失败和结果版本仍可见。

## 17. 实施顺序

1. **[对话基础]** ConversationMessage、ConversationJob、项目消息接口和历史 UI；先完成 ask/clarify，不修改代码。
2. **[基线与协作]** Run 增加 trigger/base 字段，加入 ChangeBrief、RequirementDelta、DesignDelta 和修改 Provider 方法。
3. **[候选与证据]** BaseSourceSnapshot、CandidateAppSpec、稳定物化和 Runtime SourceDiff。
4. **[安全提交]** Project 单写 CAS、Risk Policy、VersionMaterialization、`ai_edit` 版本和 Git 恢复。
5. **[恢复与验收]** 阶段级重启、配额、冲突、双用户和 Railway 持久化测试。

不能先做一个只把 follow-up 拼进原 Prompt 的按钮再补数据模型。那样表面上有“继续对话”，但无法满足基线版本、代码归属、Diff、恢复和并发正确性。

## 18. 与现有实现的兼容关系

- 首页首次 Build 继续使用现有 `LeadDecision -> Blueprint -> 固定团队`；
- 结构化 Revision 继续服务标题、正文和颜色的快速编辑，但必须接入同一 Project 写占用和最终版本 CAS；
- 受限 Vim 继续由用户直接编辑临时 worktree，与 Agent 修改共享 base commit 冲突检查；
- Restore 和 Publish 仍是独立用户动作，不由项目对话 Agent 自动触发；
- 旧 Project 没有对话历史时，从当前 ProjectVersion 开始新线程，不伪造过去消息；
- V2 可以在保留 ConversationMessage、ChangeBrief、BaseSourceSnapshot、SourceDiff 和 VersionMaterialization 的前提下，将固定流水线替换为 TaskGraph。
