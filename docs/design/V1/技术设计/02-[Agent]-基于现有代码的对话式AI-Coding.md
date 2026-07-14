# Another Atom V1 基于现有代码的对话式 AI Coding

[toc]

- **文档状态：** V1 技术设计基线；Project 路由和静态源码 Context 已完成本地实现；当前模型 raw Patch 路径需迁移为 `SourceFileChangeSet`，受控动态读取、CandidateRevision、Repair ChangeSet、恢复与 Railway 验收尚未完成
- **功能范围：** 已有 Project 中的 Lead 对话、增量修改、校验、版本与恢复
- **合并流程基线：** [统一 Chat 与 Human-in-the-loop](../产品设计/06-统一Chat与Human-in-the-loop.md)
- **产品设计：** [V1 通过对话修改现有项目](../产品设计/03-通过对话修改现有项目.md)
- **Agent 基线：** [V1 多 Agent 设计](./01-[Agent]-多Agent设计.md)
- **工程基线：** [V1 系统架构](./03-[工程]-系统架构.md)
- **源码 Context 与 Patch 基线：** [受控动态源码 Context 与 Patch 执行](./09-[Agent][TODO]-受控动态源码Context与Patch执行.md)
- **当前实现检查：** [20｜Project 对话路由与代码修改授权检查](../../../review/待办/20-[综合]-2026-07-14-Project对话路由与代码修改授权检查.md)
- **角色链路修订来源：** [23｜多角色职责与交付边界检查](../../../review/待办/23-[综合]-2026-07-14-多角色职责与交付边界检查.md)
- **设计同步与 Patch 检查：** [26｜修改流水线设计同步与 Patch 实现检查](../../../review/待办/26-[Agent]-2026-07-15-修改流水线设计同步与Patch实现检查.md)
- **文件变更 Contract 修订：** [29｜模型生成 Unified Diff 可靠性检查](../../../review/待办/29-[工程]-2026-07-15-模型生成UnifiedDiff可靠性检查.md)

## 背景

当前 V1 已能在用户批准后读取基线源码，并由 Runtime（运行系统）构建、测试和校验候选。但已实现的 Engineer raw unified diff 路径在简单改名中因 hunk 计数错误终止，说明模型输出 Interface 仍包含不必要的 Git Patch 编码不确定性。V1 的源码变更 Contract 因此修订为 `SourceFileChangeSet`：Engineer 返回被修改文件的完整最终内容，Runtime 物化候选并本地计算 Diff。大仓库动态补读和基于真实错误的有界修正仍是后续范围。

## 摘要

- **Project 对话**
  - 新增 Project 级消息、线程和 Lead 路由，使 ask、clarify 与 modify 共享可恢复的对话上下文。
- **修改基线**
  - 每轮修改绑定 ProjectVersion、Git commit、Project Context、ChangeBrief 和 BaseSourceSnapshot。
- **阶段协作**
  - Runtime 将完整有效 Contract、全量源码 Manifest、低分辨率 RepositoryMap 和初始源码工作集交给 Engineer；Engineer 在有界轮次内读取并返回受控文件变更集，根据 Runtime 验证反馈生成 Repair ChangeSet。
- **Diff 与质量证据**
  - 每次 ChangeSet 物化后，Runtime 都生成增量/累计 SourceDiff，并执行 Build、Unit Test 和 Validator；最多三次变更尝试全部结束后，只把最终通过的 CandidateRevision 写成一个版本和 Git commit。
- **并发与版本写回**
  - Project 单写 CAS、最终版本 CAS 和 VersionMaterialization 保证 Git commit 与 ProjectVersion 幂等对应。
- **失败恢复**
  - Worker 按 Artifact hash 恢复已完成阶段，冲突、取消和失败不移动当前版本；重试、额外预算与发布继续受 Runtime 控制。

## 1. 技术结论

这项功能不让 Agent 彼此直接聊天，也不让 Lead 直接调用 Engineer。Agent 之间通过 Runtime 顺序调度和不可变 Artifact 协作：

```text
Project Message
      |
      v
Runtime 组装 Project Context
      |
      v
Lead(ProjectContextSnapshot) -> ProjectLeadDecision
      |
      +-- answer / clarify -> ConversationMessage -> End
      |
      `-- propose_change -> ChangeBrief -> project_change Approval
                                      |
                                用户批准“修改代码”
                                      |
                                      v
                         创建 ai_edit Run + 写占用
                                      |
                         V1 固定下游流水线
                                      |
                         Requirement / Design Delta
                                      |
                                      v
                   ModificationContextPackage -> EngineerAction
                                                      |
                               NeedContext <----------+----------> SourceFileChangeSet
                                    |                                |
                                    `-- Runtime 受控读取              v
                                                      Runtime 隔离物化 + 重算 SourceDiff
                                      |
                                      v
                              Runtime Build / Test
                                      |
                                      v
                              Runtime Validator
                                      |
                       +--------------+--------------+
                       |                             |
                       v                             v
                    全部通过                    可修复代码失败
                       |                             |
                       v                             v
             ProjectVersion + Git commit    RepairContext -> EngineerAction
                                             -> Repair ChangeSet -> 下一候选 revision
                                             -> 重新完整验证（总尝试最多三次）
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
- 基于已有代码的增量阶段输入和有界动态读取；
- Runtime 计算的文件 Diff；
- Project 单写任务、版本 CAS 和 Git 幂等物化；
- 修改失败后按 Artifact 恢复，而不是整轮重跑。

## 2. 当前实现与剩余差距

`GET/POST /api/projects/{project_id}/messages` 已将对话和执行拆开。POST 先持久化用户消息，组装 Project Context，再调用 `route_project_message` 返回 `answer | clarify | propose_change`。前两种只写回 Chat；第三种写入 pending `change_proposal` ProjectMessage。`POST /projects/{project_id}/change-proposals/{proposal_id}/approve` 重新校验基线，成功后才创建 Run、BuildJob 和 Project 写占用。

当前 `team` 路径绑定 `base_version_id`，顺序生成 ChangeBrief、RequirementDelta、ArchitectureSpec 和完整修订后的 ArchitectureDesign。现有代码已经从完整候选 AppSpec 输出迁移为静态 SourceContext 下的 raw `SourcePatchSet`，但 [Review 29](../../../review/待办/29-[工程]-2026-07-15-模型生成UnifiedDiff可靠性检查.md) 已证明该 Interface 仍不可靠。目标路径改为 `SourceFileChangeSet`：Runtime 在隔离候选目录写入声明文件，再从真实文件重建兼容 AppSpec、SourceBundle、SourceDiff、ExecutionReport 和 ValidationReport，最后创建 `ai_edit` 版本。静态 ChangeSet 仍是过渡态，后续继续迁移全量 Manifest、RepositoryMap、受控动态读取、ContextReceipt、CandidateRevision 和有界 Repair ChangeSet。

已实现的正确性边界包括 Project 单写占用、最终基线检查、阶段 Artifact 复用、阶段配额、失败释放、用户归属校验和发布指针不变。

关键差距：

- Project 消息路由仍在同步 HTTP 请求内执行，尚无独立 ConversationJob、lease、重启恢复和消息幂等键；
- Project Context 的完整内容只进入 Provider，请求后持久化的是 hash、有效文档类型、对话条数、源码 manifest 及包含/省略清单；尚无独立 ContextEnvelope 表；
- `change_proposal` 当前复用 ProjectMessage payload 保存 pending/approved/stale，并由专用批准 API 恢复；通用 Approval subject、reject/cancel 和风险策略尚未接入；
- 完整 ChangeBrief 仍在批准后的 Run 内生成，批准前卡片只有 Lead 的 `change_summary`；
- 当前修改生产路径仍由 Engineer 输出 raw `SourcePatchSet` 并执行 `git apply`；目标 Contract 已修订为 `SourceFileChangeSet` 和 Runtime 隔离文件物化，代码尚未迁移；`EngineerAction`、受控动态读取、ContextReceipt、CandidateRevision、ChangeAttempt 和 Repair ChangeSet 也尚未实现；
- Risk Policy 尚未根据范围、破坏性 Diff 和额外预算扩充 Approval；
- SourceDiff 已持久化并可从文件面板查看，但尚未形成独立结果卡片；
- 外部 GitHub/本地目录导入和 Git/数据库之间的 VersionMaterialization 记录尚未实现。

现有实现没有把 follow-up 拼接进原始 Prompt。基线 commit、源码快照和真实 Diff 都是独立持久化事实。

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
| 工程阶段 | `ModificationContextPackage`：前述 Delta、完整有效 Contract、全量 Manifest、RepositoryMap、初始源码工作集与累计 ContextReceipt | `EngineerAction`，最终为 `SourceFileChangeSet` | 使用 starter template、越权读取、执行 Shell/Git、直接写 Repository |
| 运行系统构建/测试（Runtime Build/Test） | 应用变更（apply）后的候选源码包（SourceBundle）、应用规格（AppSpec）和固定适配器（Adapter） | 执行报告（`ExecutionReport`） | 接受工程师（Engineer）自报的通过结论、执行任意命令 |
| 运行系统校验器（Runtime Validator） | 基线、候选源码包、源码差异（SourceDiff）、执行报告、有效产品与架构文档 | 校验报告（`ValidationReport`） | 接受模型自报的通过结论 |

### 3.3 为什么仍用固定流水线

V1 继续固定执行的原因是现有 Artifact、配额、状态和恢复均按顺序阶段建立。小改动也运行完整阶段，延迟和成本更高，但避免在本功能中同时引入角色选择、TaskGraph、并行和 Artifact 合并。

V1 仍不允许团队负责人（Lead）按任务动态挑选角色。三个专业角色保持固定顺序；数据分析师（Data Analyst）和质量评审员（Reviewer）是版本基线中明确停用，不是每个运行（Run）由团队负责人临时跳过。

## 4. 新增 Contract

本节同时保留最终 Contract 方向和当前实现。已经落地的 Pydantic Contract 位于 `another_atom/contracts/schemas.py`；尚未落地的字段会明确标注，不能在 API、Provider 和 Worker 中分别定义三套结构。

### 4.1 ConversationMessage

当前以数据库 `ProjectMessage` 和 API `ProjectMessageView` 落地 `project_id / session_id / user_id / run_id / role / message_type / content / payload / created_at`。`message_type` 已包含 `answer / clarification / change_proposal / change_brief / result / error`；proposal 的 status 和 context refs 暂存在 payload。消息级 `idempotency_key` 尚未实现。

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

已实现独立于首页 `LeadDecision(direct|team)` 的 Project Contract：

```text
intent: answer | clarify | propose_change
response
reason
change_summary?
```

首页 `LeadDecision(route=direct|team)` 不直接复用。`answer / clarify` 不创建 Run；`propose_change` 只代表建议修改，并产生带基线和 Context hash 的任务卡。当前 `ProjectLeadDecision` 返回 `change_summary`，完整 ChangeBrief 在批准后的 PM 阶段生成。

### 4.3 ChangeBrief

当前已实现 `schema_version / original_request / goal / preserve / acceptance_criteria`。基线版本和 commit 保存在 Run 与 BaseSourceSnapshot 中；`context_refs / impact / risk_reasons` 等 Risk Policy 字段尚未实现。

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

当前已实现 `change_summary / changed_requirements / preserved_requirements / acceptance_criteria`。页面增删、support_level 和 Capability Policy 组合仍沿用基线 Blueprint，范围变化识别待 Risk Policy 补充。

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

当前没有单独保存 DesignDelta。Architect 接收基线 ArchitectureSpec、ChangeBrief 和 RequirementDelta，返回完整的新 ArchitectureSpec。独立 DesignDelta 是减少无关重写的后续收敛方向。

```text
changed_pages[]
changed_interactions[]
changed_data_entities[]
changed_visual_tokens[]
preserved_design_constraints[]
implementation_notes[]
```

无设计变化时输出空 `changed_*` 和明确的保留项，不生成无意义重构。Runtime 组合基线设计 Contract 与 DesignDelta，形成当前 Run 的有效设计快照。

#### 4.5.1 ArchitectureDesign 的完整同步修订

`ArchitectureSpec` 只覆盖架构摘要、页面策略、数据实体和视觉 Token，不能代表完整的 `ArchitectureDesign`。已有 Project 的变更 Run 在得到新版 `ArchitectureSpec` 后，必须把以下完整输入再次交给 Architect：

- 当前有效 `ProductSpec` 与 `Blueprint`；
- 基线版本的完整 `ArchitectureDesign`；
- 本轮 `ChangeBrief` 与 `RequirementDelta`；
- 已修订并通过 Contract 校验的 `ArchitectureSpec`。

Architect 返回一份完整的新 `ArchitectureDesignDraft`。这里的“完整”是 Artifact Contract 的完整，不表示从零重写：Prompt 必须要求保留未受变更影响的目标平台、Runtime Adapter、组件职责、状态与数据流、接口、目录和测试约束，并同步修订所有受影响的页面/组件、交互、数据流、接口、测试策略和验收映射。Runtime 最后强制以新版 `ArchitectureSpec` 覆盖 `visual_tokens`，再渲染并持久化新的 `docs/architecture-design.md`。

截至 2026-07-15，该完整同步修订已接入修改流水线。旧版本缺少 `ArchitectureDesign` 时仍走一次迁移生成；已有文档时不得再只复制旧文档并替换视觉 Token。此处采用完整结构化文档输出，是为了维护设计 Artifact 的一致性；它不等于 Engineer 的源码输出策略。Engineer 的源码输出目标是 `SourceFileChangeSet`，执行边界见下一节和[静态源码 Context 与受控文件变更执行](./10-[Agent][TODO]-静态源码Context与Patch执行.md)。

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

`BaseSourceSnapshot` 是当前实现 Contract。目标实现将“全量基线证明”“当前候选源码”和“实际交给模型的源码内容”拆成 `BaseSourceManifest / CandidateRevision / RepositoryMap / InitialSourceContext / SourceContextReceipt`：Runtime 仍能从基线 commit 和已冻结候选 revision 读取完整受控源码，但模型只获得当前 attempt 所需的工作集。字段、读取协议和迁移规则以[受控动态源码 Context 与 Patch 执行](./09-[Agent][TODO]-受控动态源码Context与Patch执行.md)为准。

### 4.7 SourceFileChangeSet 与 SourceDiff

Engineer 的源码输出 Contract 修订为 `SourceFileChangeSet`。它绑定当前候选 revision、变更 attempt 和 ContextReceipt，但不包含模型生成的 hunk、行号或 unified diff：

```text
SourceFileChangeSet
  schema_version
  project_id
  run_id
  change_attempt_id
  change_attempt_index
  change_kind: initial | repair
  base_version_id
  base_git_commit
  base_source_manifest_hash
  input_source_revision
  input_candidate_revision_hash
  input_source_manifest_hash
  context_receipt_hash
  repair_context_hash?
  repairs_failure_code?
  summary
  changes[]:
    path
    operation: modify | add | delete
    before_hash?
    replacement_content?
```

modify/add 返回目标文件的完整最终内容；delete 不返回内容。Runtime 只允许 Project 内规范化相对路径，并验证 `base_git_commit / input_source_revision / input_candidate_revision_hash / input_source_manifest_hash / context_receipt_hash / before_hash`。修改或删除现有文件前，目标文件必须以当前 revision 的完整内容进入 ContextReceipt；只读过搜索摘录、局部行范围或旧 revision 不构成修改权限。模型没有 Git、Shell 或写 Repository Tool，只能通过受控 `list/search/read` 请求取得当前候选源码。

Runtime 从当前 input revision 的完整 SourceBundle 创建隔离候选工作区，对每次 ChangeSet 执行：

1. Schema、路径、文件类型、内容大小和 Capability Policy 预检；
2. 按 operation 在隔离候选工作区确定性写入、添加或删除文件；
3. 证明 `changes[]` 外文件相对输入 revision 保持 byte-level 相同；
4. 从真实候选文件生成下一 CandidateRevision、相对 parent 的增量 Diff 和相对原始基线的累计 Diff；
5. 校验 `app-spec.json` 与 HTML/CSS/JavaScript 的 Runtime Contract；
6. 执行 Runtime Build、Unit Test 和 Validator；可修复代码失败在剩余预算内生成 RepairContext，重新进入 Engineer；
7. 最多三次变更尝试全部结束后，只有最终候选完整通过才物化一个 ProjectVersion 和 Git commit。

模型提供的是受控文件下一状态，不是 Diff。Runtime 为每个候选 revision 同时保存 IncrementalSourceDiff 和 CumulativeSourceDiff；用户最终看到和版本绑定的是相对原始基线的累计 Diff：

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

模型可以解释 Diff，但不能提供或修改最终 SourceDiff 事实。ChangeSet 无法物化或验证失败时，只有 Runtime 判定为可修复且仍有 attempt/Context/配额时才生成 RepairContext；越权、平台错误、歧义、能力缺口和范围扩大不进入自动修正。任何失败都不能回退 raw diff 或整包 AppSpec 重生成覆盖当前代码。

当前 SourceDiff 已实现 `base_version_id / changed_files / added_files / removed_files / line_additions / line_deletions / unified_diff`，并作为 Runtime Evidence 存入通用 Artifact 表。`candidate_hash` 和逐文件前后 hash 尚未加入 SourceDiff Contract。

## 5. Context 如何组装和传递

### 5.1 Project Context Snapshot

当前 V1 为避免再次出现“界面显示历史但 Provider 没有 Context”的问题，每条消息都由 Runtime 生成以下 Project Context：

```text
ProjectContextSnapshot
  project name / status
  current version / git commit
  current ProductSpec / Blueprint / ArchitectureSpec
  current AppSpec metadata
  基线 commit 下按 MAX_SOURCE_CHARS 装箱的受控源码
  selected files
  当前 Project 用户可见对话
  unresolved failure summary
  capability policy version
```

Project Context 带确定性 hash。Provider 接收完整 Context；ProjectMessage payload 只保存 hash、有效文档类型、对话条数、源码 manifest hash、字符预算和包含/省略清单，避免在消息表重复保存源码。当前只有源码受 `MAX_SOURCE_CHARS` 限制；文档和 Project 对话没有另行摘要或检索。源码或对话继续增长后的多级 Context 策略不在本纵切内。

### 5.2 修改执行 Context Package

用户批准“修改代码”后，Runtime 从 Approval 绑定的基线版本和服务端可信资源组装不可变 `ModificationContextPackage`：

```text
ModificationContextPackage
  project_id / base_version_id / base_git_commit
  approved_product_spec: path + content + hash
  blueprint: artifact ref + hash
  architecture_spec: artifact ref + hash
  app_spec: artifact ref + hash
  change_brief / requirement_delta refs + hashes
  base_source_manifest: full controlled file metadata + hashes
  repository_map: low-resolution file structure + hash
  initial_source_context: selected complete source files
  source_context_receipt: cumulative read evidence
  selected page / file / error
  previous_failure?
  context_hash
```

“完整文档加代码”在这里有明确边界：完整文档是当前有效且已批准的产品与技术 Contract，不包括 `docs/review`、无关历史 Run、旧日志或过期 Artifact；代码是基线 Git commit 下 Runtime Adapter 允许的受控源码，不包括 `.git`、Secret、依赖缓存、宿主路径或其他用户文件。

V1 始终发送完整 ProductSpec、Blueprint、ArchitectureDesign、ChangeBrief 和验收条件。源码总量未超过 `MAX_SOURCE_CHARS` 时，InitialSourceContext 可以包含全部受控源码；超过预算时只优先包含用户选择、消息准确路径、错误证据和 Adapter 固定入口，不再用路径升序填入无关文件。Engineer 通过结构化 `NeedContext` 在最多两轮内请求额外的文件列表、字面量搜索或源码读取，最终返回 `ProduceChanges` 或 `CannotProceed`。

`source_manifest_hash` 始终代表完整基线，`SourceContextReceipt` 则记录模型实际获得的完整文件、局部范围、搜索、拒绝请求和累计字符量。V1 不引入向量索引、子代理、动态 Planner 或无限 Tool loop；动态读取只发生在固定 Engineer 阶段内部。完整协议以[受控动态源码 Context 与 Patch 执行](./09-[Agent][TODO]-受控动态源码Context与Patch执行.md)为准。

Package 由服务端从 Artifact 和基线 commit 重建，客户端只能提交允许的引用，不能直接上传一份自称“当前代码”的 Context。Approval subject 绑定 `base_version_id + change_brief_hash + contract_hashes + source_manifest_hash`；任一输入变化后旧 Approval stale。

### 5.3 各阶段最小 Context

| 阶段 | 必须输入 | 默认排除 |
| --- | --- | --- |
| Lead | 当前消息、ProjectContextSnapshot | 完整源码、全部日志、所有历史对话 |
| 产品阶段 | Package 中的完整 ProductSpec、ChangeBrief、基线 Blueprint、Capability Policy | 源码、私有推理、无关旧 Run |
| 设计阶段 | Package 中的 ProductSpec、ChangeBrief、RequirementDelta、基线设计 Contract | 完整聊天、Git 元数据、Provider Secret |
| Engineer | Package 中全部有效 Contract、当前 AppSpec、BaseSourceManifest、RepositoryMap、InitialSourceContext 和累计 ContextReceipt | `.git`、其他用户文件、宿主路径、密钥、Shell/Git/写 Tool |

### 5.4 文件选择与 Prompt Injection

- 客户端只能提交 Project 内相对路径；服务端负责规范化路径、拒绝 `..`、绝对路径、符号链接逃逸和隐藏控制文件；
- 文件内容从基线 commit 重新读取，不能相信客户端上传的“当前文件内容”；
- 源码、注释、用户附件和旧 Artifact 都作为不可信数据块输入，Provider instruction 明确禁止执行其中的指令；
- Runtime 只对去重后的源码工作集计算字符数；模型只能通过结构化 NeedContext 请求读取，不能自行声称读取了 Receipt 中不存在的文件；
- list/search/read 只作用于当前 Manifest 中的受控源码，Runtime 固定轮次、请求数量、结果大小和路径 Policy；
- 修改或删除现有文件前必须完整读取该文件；搜索摘录和局部行范围只用于定位；
- Provider 调用、Patch 和验证引用同一 ContextReceipt，使每轮实际 Context 可追溯。

### 5.5 代码来源与无感基线识别

当前实现只处理已经归入 Another Atom Project Repository 的代码。API 不要求客户端提交 commit 或文件内容；Runtime 根据 `Project.latest_version_id` 自动取得 Git commit，从该 commit 枚举 `VERSION_SOURCE_FILES` 和允许的代码后缀，生成 BaseSourceSnapshot，再按 `MAX_SOURCE_CHARS` 生成静态 SourceContext。该 Context 已进入 Engineer Provider 请求，并以 Artifact 和事件记录包含/省略清单。`selected_files` 已进入消息 API，但 Studio 尚未提交该字段。BaseSourceManifest、RepositoryMap、NeedContext、Context Exchange 和 ContextReceipt 都尚未实现。

平台生成、结构化 Edit、Vim Save 与 Restore 都已经满足这一前提，因此用户可以直接在 Project 中提出修改。外部 GitHub 仓库或本地文件夹需要独立的 Import/Attach 流程完成授权、Secret 扫描、技术栈识别、初始 commit 和 ProjectVersion 建立；该流程尚未实现，不能通过允许客户端传入任意宿主路径来绕过。

### 5.6 V1 受控动态源码 Context

V1 对小仓库保留单次全量输入，对大仓库使用有界动态读取：

```text
完整有效 Contract
  + BaseSourceManifest / RepositoryMap
  + ChangeBrief / RequirementDelta
  -> Runtime 生成 InitialSourceContext
       |-- 全部源码 <= MAX_SOURCE_CHARS：发送全部完整文件
       `-- 全部源码 > MAX_SOURCE_CHARS：只发送明确相关的初始工作集
  -> EngineerAction
       |-- NeedContext -> Runtime list/search/read -> 再调用 Engineer（initial 最多两轮）
       |-- CannotProceed -> NeedsInput / Failed
       `-- ProduceChanges -> SourceFileChangeSet(attempt 1, revision 0)
  -> 隔离候选工作区物化声明文件
  -> CandidateRevision / Runtime SourceDiff / Build / Unit Test / Validator
       |-- passed -> 一个 ProjectVersion + Git commit
       `-- repairable failure
             -> RepairContext
             -> EngineerAction（repair 最多补读一轮）
             -> Repair Patch（总 Patch 最多三次）
             -> 下一 CandidateRevision 后完整复验
```

- 每个源码文件和搜索结果使用明确路径和边界标记，内容作为不可信数据而非 Prompt 指令；
- `MAX_SOURCE_CHARS` 控制去重后的累计源码工作集，不控制全量 Manifest；
- Runtime 按 source revision 生成 ContextReceipt，Provider 请求记录 `phase / change_attempt_index / source_revision / input_context_hash / source_manifest_hash / repository_map_hash / receipt_hash / used_source_chars`；
- modify/delete Patch 只能作用于当前 revision Receipt 中已经完整读取且 before hash 匹配的文件；
- Runtime 对 apply、Build、Unit Test 和 Validator 失败分类；只有可修复代码失败进入 Repair Patch，平台错误、歧义、能力缺口和范围扩大不进入；
- 多个 Patch 只形成隔离 CandidateRevision，不逐次 commit；失败、取消或达到上限时丢弃候选；
- V1 不按 Provider 动态计算 tokenizer，不做向量索引，也不开放 Shell、Git 或直接写文件 Tool；
- 字段、轮次、持久化、恢复和错误语义统一由[受控动态源码 Context 与 Patch 执行](./09-[Agent][TODO]-受控动态源码Context与Patch执行.md)定义。

## 6. Provider 接口如何扩展

现有 `LLMProvider` 保留首次 Build 方法，当前项目修改纵切新增以下方法：

```python
create_change_brief(
    request: str,
    blueprint: Blueprint,
    app_spec: AppSpec,
) -> ChangeBrief

create_requirement_delta(
    change_brief: ChangeBrief,
    blueprint: Blueprint,
) -> RequirementDelta

revise_architecture_spec(
    blueprint: Blueprint,
    architecture_spec: ArchitectureSpec,
    change_brief: ChangeBrief,
    requirement_delta: RequirementDelta,
) -> ArchitectureSpec

create_engineer_action(
    context: EngineerContext,
) -> EngineerAction
```

`create_change_brief / create_requirement_delta / revise_architecture_spec / revise_architecture_design` 已接入 Mock 与 Ollama/DeepSeek Provider。现有 `create_source_patch_set` 是待替换兼容路径；目标 `create_source_file_change_set` 返回静态 Context 下的受控文件最终内容与 AppSpec 元数据 Delta，Runtime 负责隔离物化、候选重建和本地 Diff。`revise_app_spec` 只保留历史兼容，不再是已有 Project 的正式修改入口。动态阶段的目标接口 `create_engineer_action` 尚未实现；它将返回互斥的 `NeedContext | ProduceChanges | CannotProceed`，并复用同一文件变更执行 Module。

当前 Project Lead 输出 answer、clarify 或带 `change_summary` 的 propose_change；批准后 PM 再生成完整 ChangeBrief。Project 对话已具备同步可用纵切，但尚未达到下节定义的异步 ConversationJob、租约恢复和消息幂等语义。

不能把修改实现成 `create_app_spec(original_prompt + follow_up)` 或继续只传旧 AppSpec，因为它们没有完整基线代码和保留约束，容易退化成全量重生成。

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

当前兼容接口为同步 `POST /api/projects/{project_id}/messages -> 200 ProjectMessageResult`。它先提交用户消息，再等待 Lead 返回；进程在 Provider 调用期间退出时只能保留用户消息，不能自动领取并完成这次路由。异步目标不能在实现前写成当前能力。

消息由持久化 `ConversationJob` 或等价 Job 处理，不能只依赖一个没有数据库事实的 `asyncio.create_task`。进程重启后，`queued/routing` 消息必须可重新领取。

### 7.2 消息状态

```text
queued -> routing
           |-- answered -> completed
           |-- clarification_needed -> completed
           `-- change_brief_ready
                    `-- awaiting_project_change_approval
                              |-- approved -> linked_to_run -> completed
                              |-- rejected -> completed（无 Run）
                              `-- stale -> completed（基线已变化）

routing / downstream failure -> failed
user stop before Run -> cancelled
```

### 7.3 修改 Run 状态

```text
CreatedAfterApproval(base_version, approval_id, modification_context_hash)
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

Project 代码修改先经过固定 workflow Gate，再由确定性 Risk Policy 扩充风险信息。Lead 只能形成修改提案，不能批准执行。

```text
ProjectLeadDecision(propose_change)
  -> ChangeBrief + ModificationContextPackage hashes
  -> workflow Approval(project_change)
  -> 用户点击“修改代码”
  -> 校验 subject / base version
  -> 创建 ai_edit Run
```

这一执行前 Gate 对普通修改和高风险修改都存在。普通修改只展示目标、保持不变项、验收条件和基线版本；Risk Policy 命中范围、能力或预算变化时，在同一 subject 中增加风险说明。执行后出现未包含在已批准 subject 中的破坏性 Diff 时，再进入提交前 Approval。

Risk Policy 输入仍为：

```text
risk_input
  = ChangeBrief
  + RequirementDelta
  + base/candidate file stats
  + dirty worktree state
  + quota estimate
  + publication state
```

执行前 workflow Approval 已批准后，当前页面/模块内的文案、样式、现有交互和明确错误修复可以在该 subject 范围内自动完成，不重复弹出相同确认。

范围增删、核心模块替换、额外预算和 dirty worktree 处理必须在执行前卡片中明确；大面积删除/重写和实际影响扩大在 SourceDiff 形成后触发提交前确认；版本冲突直接 stale/deny，发布变化使用独立 Deployment Approval。

Approval 必须绑定：

```text
project_id + run_id + base_version_id
+ change_brief_hash + requirement_delta_hash
+ risk_summary + budget_limit
```

任一 hash、基线版本、Contract、源码清单或预算变化后旧 Approval 失效。所有自然语言代码修改都进入 `awaiting_project_change_approval`；已批准 subject 内的正常执行不再重复确认。

## 9. 源码、Diff 与候选版本

Agent 不直接写 Project Repository。工程阶段输出 SourceFileChangeSet 后：

1. Runtime 校验 ChangeSet Schema、基线 hash、相对路径、文件类型、内容大小和操作范围；
2. Repository Service 从 ChangeSet 绑定的 input CandidateRevision 创建隔离候选工作区；
3. 按 add/modify/delete 确定性物化声明文件，不解释 raw diff；
4. Runtime 冻结下一 CandidateRevision，并生成相对 parent 的增量 Diff 与相对原始基线的累计 Diff；
5. Capability Policy 检查新增/删除文件和危险能力；
6. 从候选工作区读取并校验 AppSpec 与实际 Web 源码 Contract，再运行 Build、Unit Test 和完整 Validator；
7. 可修复代码失败生成 RepairContext 并在剩余 attempt 内回到 Engineer；每个新 revision 都完整复验；
8. 只有最终 revision 的全部门禁通过才进入版本物化，并将一个最终 commit 接入当前 Project。

未在 `changes[]` 声明的文件必须相对输入 revision 保持 byte-level 相同。Runtime 不允许格式化全部文件制造噪声，也不允许 ChangeSet 修改未声明文件。

用户看到的“修改了 3 个文件”来自 SourceDiff；Agent 的文字摘要只用于解释。

## 10. 并发和版本一致性

### 10.1 Project 单写任务

V1 单实例仍需要数据库 CAS，不能只用进程内锁。Project 消息路由和 pending `project_change` Approval 不占写锁；用户批准后，服务端重新校验 subject 与基线，创建修改 Run 时执行：

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

- Lead 项目路由单独预占和结算；answer/clarify 不预占下游团队用量；
- modify 在 Risk Policy 通过后按阶段预占，不一次把整轮全部记为 used；
- Schema retry、Provider fallback 和 Engineer repair 都按实际请求结算；
- 非 LLM 失败结算已经观测到的请求并释放剩余预占；
- `quota_limit` 不参与运行授权；追加 retry/rework 是否需要 Approval 只由对应风险策略决定。

### 12.2 阶段恢复

产品、架构和最终结果仍使用每个 Run 唯一的阶段 Artifact：

```text
change_brief
requirement_delta
effective_blueprint
design_delta
effective_design
base_source_manifest
source_patch_chain
final_source_bundle
cumulative_source_diff
execution_report
validation_report
```

Engineer 阶段的 `ContextExchange / ContextReceipt / ChangeAttempt / CandidateRevision` 是有顺序的多条记录，不能塞进 `(run_id, artifact_type)` 唯一约束，也不再使用 `repair_app_spec`。Worker 重启后按 sequence、attempt 和 revision 恢复：已经提交的模型动作、读取、候选物化、Diff 和验证不重复；只有不存在合法检查点的阶段才继续执行。

### 12.3 失败后的新 Run

当前 Run 内的可修复代码失败先按 PatchPolicy 在最多三次 Patch 中处理，不创建子 Run。只有修正耗尽、需要用户补充要求或用户在失败后显式选择“继续修复”时，才创建子 Run：

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
| Project 已有写任务 | `PROJECT_WRITE_BUSY` | 当前任务继续，消息保留为草稿 |
| 基线版本已变化 | `BASE_VERSION_CHANGED` / `BASE_VERSION_CONFLICT` | 不覆盖新版本 |
| 基线源码不一致 | `BASE_SOURCE_MISMATCH` | 停止修改，保留当前版本 |
| 初始源码超过 `MAX_SOURCE_CHARS` | Runtime 提供 Manifest、RepositoryMap 和明确相关初始工作集 | Engineer 可在有界轮次内请求额外源码；当前版本不受影响 |
| 动态读取超过字符或轮次上限 | `SOURCE_CONTEXT_LIMIT` / `SOURCE_CONTEXT_ROUND_LIMIT` | 不继续猜测或生成越权 ChangeSet，当前版本不变 |
| ChangeSet 修改未完整读取的文件 | `SOURCE_CHANGE_CONTEXT_VIOLATION` | 拒绝物化，保留 ContextReceipt 和 ChangeSet 证据 |
| ChangeSet 包含越权路径或错误基线 hash | `SOURCE_CHANGE_PATH_FORBIDDEN` / `SOURCE_CHANGE_BASE_MISMATCH` | 拒绝物化，当前版本不变 |
| replacement content 无效或超限 | `SOURCE_CHANGE_CONTENT_INVALID` / `SOURCE_CHANGE_OUTPUT_TOO_LARGE` | 不生成新 revision；当前版本不变 |
| 变更尝试达到三次仍未通过 | `SOURCE_CHANGE_ATTEMPT_LIMIT` | 丢弃候选，不创建版本 |
| Provider 输出无效 | 有限 Schema retry，耗尽后失败 | 已提交 Artifact 可复用 |
| Build/Test/Validator 可修复代码失败 | Engineer 在剩余 attempt 内生成 Repair ChangeSet 并完整复验 | 未通过前不创建版本 |
| Validator 或 Executor 平台/未知失败 | 不调用 Agent 掩盖平台问题 | 当前版本不变 |
| Git 已提交、DB 未完成时崩溃 | VersionMaterialization 恢复并复用 commit | 不重复 commit/version |
| Publish 状态存在 | 仅提示线上/工作版本差异 | 线上版本不自动变化 |

## 16. 测试与验收

### 16.1 Contract 与单元测试

- ProjectLeadDecision 的 `answer | clarify | propose_change` 三种 intent 互斥；
- ChangeBrief 的基线字段只能由 Runtime 注入；
- RequirementDelta 不能绕过 Capability Policy；
- ProjectContextSnapshot 包含当前产品事实和有界对话；ModificationContextPackage 包含全部有效 Contract、BaseSourceManifest、RepositoryMap、InitialSourceContext 和 Context Policy；相同基线、请求、选中文件和配置得到相同初始 Context；
- EngineerAction 的 NeedContext、ProduceChanges 和 CannotProceed 三种分支互斥；相同读取请求从相同 source revision 得到稳定 result hash；
- ContextReceipt 准确记录 source revision、完整文件、局部范围、搜索、拒绝请求和累计字符量；
- SourceFileChangeSet 绑定 attempt、input revision、CandidateRevision hash、Manifest、Receipt 和逐文件 before hash；
- IncrementalSourceDiff 与 parent/child 候选一致，CumulativeSourceDiff 与原始基线/当前候选一致；
- 普通修改创建 `project_change` workflow Approval；范围/预算风险扩充执行前 subject，破坏性 Diff 扩大时请求提交前确认。

### 16.2 集成测试

- ask 只产生对话消息，不创建 Run、BuildJob、Git commit 或 ProjectVersion；
- propose_change 只产生 ChangeBrief 和 pending Approval；批准前不创建 Run、BuildJob 或写占用；
- 批准“修改代码”后只创建一个绑定原 Project 和 base version 的 Run，完整经过固定下游流水线并创建 `ai_edit` 版本；
- Engineer 输入包含完整 ProductSpec、有效 Contract、preserve/acceptance 条件、全量 Manifest、RepositoryMap 和实际源码工作集；超限时可在最多两轮内请求额外源码，并最终输出 SourceFileChangeSet 或明确 CannotProceed；
- modify/delete 只作用于当前 revision ContextReceipt 中完整读取的文件，超出 NeedContext、ChangeSet 或字符上限均明确失败；
- 初始 ChangeSet 验证失败后，结构化 RepairContext 能驱动 Repair ChangeSet；每次成功物化后从 Build 起完整复验；
- 最多三次变更尝试，无论经历几次候选 revision，成功 Run 只创建一个 ProjectVersion 和 Git commit；
- 平台错误、需求歧义、能力缺口、越权和范围扩大不进入自动修正；
- 未变文件 hash 保持一致，changed_files 与真实 Diff 一致；
- 两个并发修改只有一个取得 Project 写占用；
- 结构化 Edit/Vim Save 与 AI 修改冲突时不能互相覆盖；
- 基线变化后旧候选不能提交；
- Worker 在每个阶段重启后不重复已提交 Artifact、Provider 结算、Git commit 或版本；
- 运行系统构建（Runtime Build）、单元测试（Unit Test）或校验器（Validator）门禁失败不创建版本；
- 新版本不改变已发布指针；
- 双用户不能读取对方消息、Context、Diff、文件或版本。

### 16.3 部署验收

- Railway 单副本重启后 queued/routing 消息与修改 Run 可恢复；
- 持久化 Volume 同时保留 SQLite、Project Git 和候选物化状态；
- 真实 Provider 完成一轮已有店铺代码修改，日志能追溯各阶段输入 Artifact 与用量；
- 浏览器刷新后对话、修改任务、阶段、Diff、失败和结果版本仍可见。

## 17. 实施状态与后续顺序

已完成 ProjectMessage、ProjectLeadDecision、Project Context 组装与 hash、answer/clarify 无 Run、pending change proposal、独立“修改代码”按钮、批准后建 Run/占写锁、Run trigger/base、ChangeBrief、RequirementDelta、完整 ArchitectureSpec 修订、基于旧版完整 ArchitectureDesign 的同步修订、BaseSourceSnapshot、`MAX_SOURCE_CHARS` 确定性静态源码装箱、SourceContext Artifact、Project 单写占用、最终基线检查和 `ai_edit` 版本，以及问答、澄清、批准幂等、旧提案失效、并发、失败和双用户测试。raw SourcePatchSet、隔离 `git apply` 与 Runtime 重建链虽已实现，但因 [Review 29](../../../review/待办/29-[工程]-2026-07-15-模型生成UnifiedDiff可靠性检查.md) 不再作为目标基线；需迁移为 SourceFileChangeSet 和隔离文件物化。

后续按以下顺序完成：

1. **[异步可靠性]** ConversationJob、lease、重启恢复和消息 idempotency key。
2. **[通用授权]** 将专用 change proposal 迁移到通用 Approval subject，并补 reject/cancel、风险对象和批准前完整 ChangeBrief。
3. **[文件变更 Contract 迁移]** 先按[静态源码 Context 与受控文件变更执行](./10-[Agent][TODO]-静态源码Context与Patch执行.md)把 raw SourcePatchSet 替换为 SourceFileChangeSet、隔离文件物化和 Runtime 本地 Diff。
4. **[动态 Context 与有界修正]** 再按[受控动态源码 Context 与 Patch 执行](./09-[Agent][TODO]-受控动态源码Context与Patch执行.md)扩展 BaseSourceManifest、RepositoryMap、EngineerAction、ContextReceipt、CandidateRevision、ChangeAttempt、增量/累计 Diff 和 RepairContext；复用新的文件变更 Module，不回退 raw diff 或完整 AppSpec。
5. **[风险确认]** impact/risk Contract、范围与破坏性 Diff 判断、提交前 Approval。
6. **[结果证据]** 独立 Diff/验收结果卡片和候选 hash。
7. **[提交恢复]** VersionMaterialization，收窄 Git commit 成功而数据库事务未完成的窗口。
8. **[接入与部署]** GitHub/本地目录首次导入，以及 Railway 真实 Provider、进程重启和 Volume 验收。

不能先做一个只把 follow-up 拼进原 Prompt 的按钮再补数据模型。那样表面上有“继续对话”，但无法满足基线版本、代码归属、Diff、恢复和并发正确性。

## 18. 与现有实现的兼容关系

- 首页首次构建（Build）的目标链路使用 `LeadDecision -> ProductSpec approval -> ArchitectureDesign -> Engineer -> Build/Test/Validation`；即团队负责人决策→产品规格审批→架构设计→工程师→构建/测试/校验。当前 `Blueprint -> 五角色固定团队` 只是待迁移实现。
- 结构化 Revision 继续服务标题、正文和颜色的快速编辑，但必须接入同一 Project 写占用和最终版本 CAS；
- 受限 Vim 继续由用户直接编辑临时 worktree，与 Agent 修改共享 base commit 冲突检查；
- Restore 和 Publish 仍是独立用户动作，不由项目对话 Agent 自动触发；
- 旧 Project 没有对话历史时，从当前 ProjectVersion 开始新线程，不伪造过去消息；
- V2 可以在保留 ConversationMessage、ChangeBrief、BaseSourceSnapshot、SourceDiff 和 VersionMaterialization 的前提下，将固定流水线替换为 TaskGraph。
