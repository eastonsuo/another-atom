# Another Atom V1 基于现有代码的对话式 AI Coding

[toc]

- **文档状态：** V1 技术设计基线；Project 路由、源码 Context 与批准后建 Run 已实现，SourcePatchSet 隔离 apply 尚未实现
- **功能范围：** 已有 Project 中的 Lead 对话、增量修改、校验、版本与恢复
- **合并流程基线：** [统一 Chat 与 Human-in-the-loop](../产品设计/06-统一Chat与Human-in-the-loop.md)
- **产品设计：** [V1 通过对话修改现有项目](../产品设计/03-通过对话修改现有项目.md)
- **Agent 基线：** [V1 多 Agent 设计](./01-[Agent]-多Agent设计.md)
- **工程基线：** [V1 系统架构](./03-[工程]-系统架构.md)
- **当前实现检查：** [20｜Project 对话路由与代码修改授权检查](../../../review/待办/20-[综合]-2026-07-14-Project对话路由与代码修改授权检查.md)
- **角色链路修订来源：** [23｜多角色职责与交付边界检查](../../../review/待办/23-[综合]-2026-07-14-多角色职责与交付边界检查.md)

## 背景

当前固定团队的已实现工程师（Engineer）仍主要接收提示词（Prompt）、产品蓝图（Blueprint）和架构规格（ArchitectureSpec），但 [V1 多智能体（Agent）设计](./01-[Agent]-多Agent设计.md) 已将目标链路修订为产品规格（ProductSpec）、架构设计（ArchitectureDesign）、项目源码与单元测试。本文定义基于现有代码继续修改所需的增量闭环；凡涉及角色集合、交付契约（Contract）和最终验收权的表述，均以主智能体设计为准。

## 摘要

- **Project 对话**
  - 新增 Project 级消息、线程和 Lead 路由，使 ask、clarify 与 modify 共享可恢复的对话上下文。
- **修改基线**
  - 每轮修改绑定 ProjectVersion、Git commit、Project Context、ChangeBrief 和 BaseSourceSnapshot。
- **阶段协作**
  - Runtime 将完整有效 Contract 和固定字符预算内的基线源码交给 Engineer；源码未超限时全量发送，超限时按文件裁剪。Engineer 输出结构化代码 Diff，Runtime 在隔离候选工作区 apply。
- **Diff 与质量证据**
  - 源码差异（SourceDiff）由运行系统（Runtime）比较基线与候选代码确定性生成，运行系统在沙箱（Sandbox）中执行构建（Build）和单元测试（Unit Test），校验器（Validator）基于真实证据决定是否可创建版本。
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
                   ModificationContextPackage -> Engineer -> SourcePatchSet
                                                      |
                                                      v
                                         Runtime 隔离 apply + 重算 SourceDiff
                                      |
                                      v
                              Runtime Build / Test
                                      |
                                      v
                              Runtime Validator
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

## 2. 当前实现与剩余差距

`GET/POST /api/projects/{project_id}/messages` 已将对话和执行拆开。POST 先持久化用户消息，组装 Project Context，再调用 `route_project_message` 返回 `answer | clarify | propose_change`。前两种只写回 Chat；第三种写入 pending `change_proposal` ProjectMessage。`POST /projects/{project_id}/change-proposals/{proposal_id}/approve` 重新校验基线，成功后才创建 Run、BuildJob 和 Project 写占用。

当前已实现 `team` 路径会绑定 `base_version_id`，并顺序生成变更摘要（ChangeBrief）、需求差异（RequirementDelta）、架构规格（ArchitectureSpec）、候选应用规格（AppSpec）、源码差异（SourceDiff）、数据分析（DataProfile）、校验报告（ValidationReport）和质量评审报告（ReviewReport），最后创建 `ai_edit` 版本。这是待迁移现状，不是目标链路：目标实现使用有效产品规格（ProductSpec）、架构设计（ArchitectureDesign）、候选源码包（SourceBundle）、运行系统源码差异（Runtime SourceDiff）、执行报告（ExecutionReport）和校验报告（ValidationReport），不调用数据分析师（Data Analyst）与质量评审员（Reviewer）。运行系统（Runtime）已从基线提交（commit）枚举受控源码，按 `MAX_SOURCE_CHARS` 生成确定性源码上下文阶段产物（SourceContext Artifact）；后续迁移必须将它与通用源码包对齐。

已实现的正确性边界包括 Project 单写占用、最终基线检查、阶段 Artifact 复用、阶段配额、失败释放、用户归属校验和发布指针不变。

关键差距：

- Project 消息路由仍在同步 HTTP 请求内执行，尚无独立 ConversationJob、lease、重启恢复和消息幂等键；
- Project Context 的完整内容只进入 Provider，请求后持久化的是 hash、有效文档类型、对话条数、源码 manifest 及包含/省略清单；尚无独立 ContextEnvelope 表；
- `change_proposal` 当前复用 ProjectMessage payload 保存 pending/approved/stale，并由专用批准 API 恢复；通用 Approval subject、reject/cancel 和风险策略尚未接入；
- 完整 ChangeBrief 仍在批准后的 Run 内生成，批准前卡片只有 Lead 的 `change_summary`；
- Engineer 仍输出完整候选 AppSpec；SourcePatchSet、隔离候选工作区 apply 与 apply 后真实 Diff 尚未实现；
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
| 工程阶段 | `ModificationContextPackage`：前述 Delta、完整有效 Contract、固定字符预算内的基线源码与裁剪清单 | `SourcePatchSet` | 使用 starter template、执行 Tool、直接写 Repository |
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

### 4.7 SourcePatchSet 与 SourceDiff

Engineer 不再输出完整 CandidateAppSpec，而是基于 `ModificationContextPackage` 返回绑定基线的结构化代码 Diff：

```text
SourcePatchSet
  schema_version
  base_version_id
  base_git_commit
  source_manifest_hash
  summary
  patches[]:
    path
    operation: modify | add | delete
    before_hash?
    unified_diff
```

Runtime 只允许 Project 内规范化相对路径，并验证 `base_git_commit / source_manifest_hash / before_hash`。模型没有文件、Git 或 Shell Tool，不能直接 apply 或写入 Repository。

Runtime 从基线 commit 创建隔离候选工作区，对 Patch 执行：

1. Schema、路径、文件类型和 Capability Policy 预检；
2. `git apply --check` 或等价确定性检查；
3. 在隔离候选工作区 apply；
4. 从 apply 后真实文件重新计算 SourceDiff；
5. 校验 `app-spec.json` 与 HTML/CSS/JavaScript 的 Runtime Contract；
6. 运行系统构建（Runtime Build）、单元测试（Unit Test）和校验器（Validator）的强制检查（mandatory check）全部通过后才物化项目版本（ProjectVersion）。

模型返回的 Diff 是候选修改指令，不是最终 Evidence。最终 SourceDiff 必须由 Runtime 比较基线 commit 与 apply 后候选工作区重新生成：

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

模型可以解释 Diff，但不能提供或修改最终 SourceDiff 事实。Patch 无法 apply、上下文不匹配、越权路径或 apply 后 Contract 不一致时，Run 失败并保留 Patch 与错误证据，不能回退为整包重生成覆盖当前代码。

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
  base_source_snapshot: source manifest + controlled file contents + hashes
  selected page / file / error
  previous_failure?
  context_hash
```

“完整文档加代码”在这里有明确边界：完整文档是当前有效且已批准的产品与技术 Contract，不包括 `docs/review`、无关历史 Run、旧日志或过期 Artifact；代码是基线 Git commit 下 Runtime Adapter 允许的受控源码，不包括 `.git`、Secret、依赖缓存、宿主路径或其他用户文件。

V1 始终发送完整 ProductSpec、Blueprint、ArchitectureSpec、AppSpec、ChangeBrief 和验收条件。代码库容量只用一个配置项 `MAX_SOURCE_CHARS` 控制：Runtime 读取基线 commit 下全部受控源码，源码总字符数未超过预算时全部发送；超过预算时按完整文件装箱后继续调用 Engineer。不计算模型 token，不裁剪文档，不引入检索、依赖分析、摘要、Planner、分包或多轮 Patch。

文件顺序固定为：用户在界面明确选中的文件、用户消息中出现准确相对路径的文件、其余文件。前两组保持用户引用顺序并去重，其余文件按规范化相对路径升序排列。Runtime 从前向后检查每个完整文件：加入后不超过 `MAX_SOURCE_CHARS` 就包含，超过则省略并继续检查后续文件；不截断单个文件，也不因一个大文件装不下就停止。`source_manifest_hash` 始终代表完整基线，裁剪记录只保存 `max_source_chars / used_source_chars / included_files / omitted_files / trimming_applied`。

Package 由服务端从 Artifact 和基线 commit 重建，客户端只能提交允许的引用，不能直接上传一份自称“当前代码”的 Context。Approval subject 绑定 `base_version_id + change_brief_hash + contract_hashes + source_manifest_hash`；任一输入变化后旧 Approval stale。

### 5.3 各阶段最小 Context

| 阶段 | 必须输入 | 默认排除 |
| --- | --- | --- |
| Lead | 当前消息、ProjectContextSnapshot | 完整源码、全部日志、所有历史对话 |
| 产品阶段 | Package 中的完整 ProductSpec、ChangeBrief、基线 Blueprint、Capability Policy | 源码、私有推理、无关旧 Run |
| 设计阶段 | Package 中的 ProductSpec、ChangeBrief、RequirementDelta、基线设计 Contract | 完整聊天、Git 元数据、Provider Secret |
| Engineer | Package 中全部有效 Contract、当前 AppSpec、`MAX_SOURCE_CHARS` 内的 BaseSourceSnapshot 源码与裁剪清单 | `.git`、其他用户文件、宿主路径、密钥 |
| 数据/质量分析 | 基线和 apply 后候选源码、Runtime SourceDiff、验收项 | 可写 Repository、发布权限 |
| 最终复核 | 所有已接受 Artifact、Diff、ValidationReport | Chain of Thought、可写 Tool |

### 5.4 文件选择与 Prompt Injection

- 客户端只能提交 Project 内相对路径；服务端负责规范化路径、拒绝 `..`、绝对路径、符号链接逃逸和隐藏控制文件；
- 文件内容从基线 commit 重新读取，不能相信客户端上传的“当前文件内容”；
- 源码、注释、用户附件和旧 Artifact 都作为不可信数据块输入，Provider instruction 明确禁止执行其中的指令；
- Runtime 只对源码计算字符数；只有全部受控源码超过 `MAX_SOURCE_CHARS` 时才按固定文件顺序装箱，模型不能自行选择或声称读取了未包含文件；
- Provider 调用、Patch 和后续 Review 引用同一包含/省略文件清单，使裁剪范围可追溯。

### 5.5 代码来源与无感基线识别

当前实现只处理已经归入 Another Atom Project Repository 的代码。API 不要求客户端提交 commit 或文件内容；Runtime 根据 `Project.latest_version_id` 自动取得 Git commit，从该 commit 枚举 `VERSION_SOURCE_FILES` 和允许的代码后缀，生成 BaseSourceSnapshot，再按 `MAX_SOURCE_CHARS` 生成 SourceContext。该 Context 已进入 Engineer Provider 请求，并以 Artifact 和事件记录包含/省略清单。`selected_files` 已进入消息 API，但 Studio 尚未提交该字段；当前 UI 请求主要依赖消息中的准确相对路径和剩余路径升序。

平台生成、结构化 Edit、Vim Save 与 Restore 都已经满足这一前提，因此用户可以直接在 Project 中提出修改。外部 GitHub 仓库或本地文件夹需要独立的 Import/Attach 流程完成授权、Secret 扫描、技术栈识别、初始 commit 和 ProjectVersion 建立；该流程尚未实现，不能通过允许客户端传入任意宿主路径来绕过。

### 5.6 V1 源码字符预算与裁剪

V1 只解决代码库过大问题：

```text
完整有效 Contract（不裁剪）
  + base commit 全量受控源码
  + ChangeBrief / RequirementDelta
  -> Runtime 计算源码字符数
       |-- <= MAX_SOURCE_CHARS：全量发送
       `-- > MAX_SOURCE_CHARS：按完整文件顺序装箱
  -> 单次 Engineer Provider 调用
  -> SourcePatchSet
  -> 隔离候选工作区 apply --check / apply
  -> Runtime SourceDiff / Build / Unit Test / Validator
```

- 每个源码文件使用明确路径和边界标记，文件内容作为不可信数据而非 Prompt 指令；
- Provider 请求记录 `context_hash / source_manifest_hash / max_source_chars / used_source_chars / included_files / omitted_files / input_artifact_refs`；
- Patch hunk 绑定 `before_hash`，不允许在不同基线模糊套用；
- 第一次 Patch 因格式或 hunk 定位失败时，Runtime 可以把确定性 apply 错误返回 Engineer 修正一次；不能改为整包重生成，也不能循环重试；
- `MAX_SOURCE_CHARS` 是部署配置，不按 Provider 动态计算 token；配置值需要为固定文档、Prompt 和 Diff 输出留下余量；
- 裁剪只解决源码过大，不改变“模型只给 Patch、Runtime 在隔离环境 apply、真实 Diff 由 Runtime 重算”的执行边界。

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

create_source_patch(
    context: ModificationContextPackage,
) -> SourcePatchSet
```

`create_change_brief / create_requirement_delta / revise_architecture_spec / revise_app_spec` 已接入 Mock 与 Ollama/DeepSeek Provider；`create_source_patch` 是替换现有 `revise_app_spec` 修改路径的目标接口，尚未实现。它继续使用 Pydantic 结构化输出、Provider fallback 和阶段用量结算，但输出仅是候选 Patch，不具有写仓库权限。

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

Agent 不直接写 Project Repository。工程阶段输出 SourcePatchSet 后：

1. Runtime 校验 Patch Schema、基线 hash、相对路径、文件类型和操作范围；
2. Repository Service 从 `base_git_commit` 创建隔离候选工作区；
3. 先执行 `git apply --check`，通过后才在候选工作区 apply；
4. Runtime 比较基线 commit 与 apply 后实际文件，生成可信 SourceDiff；
5. Capability Policy 检查新增/删除文件和危险能力；
6. 从候选工作区读取并校验 AppSpec 与实际 Web 源码 Contract，再运行完整 Validator；
7. 通过后执行质量复核；
8. 只有全部门禁通过才进入版本物化，并将候选 commit 接入当前 Project。

未被 Patch 修改的文件必须保持 byte-level 相同。模型 Diff 只描述必要变化；Runtime 不允许格式化全部文件制造噪声，也不允许 Patch 修改未在 `patches[]` 声明的文件。

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
| Project 已有写任务 | `PROJECT_WRITE_BUSY` | 当前任务继续，消息保留为草稿 |
| 基线版本已变化 | `BASE_VERSION_CHANGED` / `BASE_VERSION_CONFLICT` | 不覆盖新版本 |
| 基线源码不一致 | `BASE_SOURCE_MISMATCH` | 停止修改，保留当前版本 |
| 全部受控源码超过 `MAX_SOURCE_CHARS` | Runtime 按固定文件顺序装箱并记录包含/省略清单 | Engineer 只基于实际发送源码生成 Patch；当前版本不受影响 |
| Patch 包含越权路径或错误基线 hash | `PATCH_PATH_DENIED` / `PATCH_BASE_MISMATCH` | 拒绝 apply，当前版本不变 |
| Patch 无法应用 | `PATCH_APPLY_FAILED` | 保留 Patch 与错误；最多允许一次受控修正 |
| Provider 输出无效 | 有限 Schema retry，耗尽后失败 | 已提交 Artifact 可复用 |
| Validator 可修复失败 | Engineer 最多修复一次并完整复验 | 未通过前不创建版本 |
| Validator 平台/未知失败 | 不调用 Agent 掩盖平台问题 | 当前版本不变 |
| 最终复核拒收 | Needs input/Failed | 候选和 Evidence 保留，不创建版本 |
| Git 已提交、DB 未完成时崩溃 | VersionMaterialization 恢复并复用 commit | 不重复 commit/version |
| Publish 状态存在 | 仅提示线上/工作版本差异 | 线上版本不自动变化 |

## 16. 测试与验收

### 16.1 Contract 与单元测试

- ProjectLeadDecision 的 `answer | clarify | propose_change` 三种 intent 互斥；
- ChangeBrief 的基线字段只能由 Runtime 注入；
- RequirementDelta 不能绕过 Capability Policy；
- ProjectContextSnapshot 包含当前产品事实和有界对话；ModificationContextPackage 包含全部有效 Contract，以及按 `MAX_SOURCE_CHARS` 生成的源码 Context；相同基线、请求、选中文件和配置得到相同包含/省略清单；
- SourceDiff 与实际候选文件一致；
- 普通修改创建 `project_change` workflow Approval；范围/预算风险扩充执行前 subject，破坏性 Diff 扩大时请求提交前确认。

### 16.2 集成测试

- ask 只产生对话消息，不创建 Run、BuildJob、Git commit 或 ProjectVersion；
- propose_change 只产生 ChangeBrief 和 pending Approval；批准前不创建 Run、BuildJob 或写占用；
- 批准“修改代码”后只创建一个绑定原 Project 和 base version 的 Run，完整经过固定下游流水线并创建 `ai_edit` 版本；
- Engineer 输入包含完整 ProductSpec、有效 Contract、preserve/acceptance 条件，以及未超限的全量源码或超限后按文件裁剪的源码；输入与包含/省略清单一致，并输出 SourcePatchSet；
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

已完成 ProjectMessage、ProjectLeadDecision、Project Context 组装与 hash、answer/clarify 无 Run、pending change proposal、独立“修改代码”按钮、批准后建 Run/占写锁、Run trigger/base、ChangeBrief、RequirementDelta、完整 ArchitectureSpec 修订、BaseSourceSnapshot、`MAX_SOURCE_CHARS` 确定性源码装箱、SourceContext Artifact、完整 ProductSpec/有效 Contract/实际源码进入 Engineer、候选 AppSpec、Runtime SourceDiff、Project 单写占用、最终基线检查、`ai_edit` 版本，以及问答、澄清、批准幂等、旧提案失效、并发、失败和双用户测试。

后续按以下顺序完成：

1. **[异步可靠性]** ConversationJob、lease、重启恢复和消息 idempotency key。
2. **[通用授权]** 将专用 change proposal 迁移到通用 Approval subject，并补 reject/cancel、风险对象和批准前完整 ChangeBrief。
3. **[Patch 执行]** 接入 `create_source_patch`，实现隔离候选工作区 apply，并由 Runtime 重算真实 Diff。
4. **[风险确认]** impact/risk Contract、范围与破坏性 Diff 判断、提交前 Approval。
5. **[结果证据]** 独立 Diff/验收结果卡片和候选 hash。
6. **[提交恢复]** VersionMaterialization，收窄 Git commit 成功而数据库事务未完成的窗口。
7. **[接入与部署]** GitHub/本地目录首次导入，以及 Railway 真实 Provider、进程重启和 Volume 验收。

不能先做一个只把 follow-up 拼进原 Prompt 的按钮再补数据模型。那样表面上有“继续对话”，但无法满足基线版本、代码归属、Diff、恢复和并发正确性。

## 18. 与现有实现的兼容关系

- 首页首次构建（Build）的目标链路使用 `LeadDecision -> ProductSpec approval -> ArchitectureDesign -> Engineer -> Build/Test/Validation`；即团队负责人决策→产品规格审批→架构设计→工程师→构建/测试/校验。当前 `Blueprint -> 五角色固定团队` 只是待迁移实现。
- 结构化 Revision 继续服务标题、正文和颜色的快速编辑，但必须接入同一 Project 写占用和最终版本 CAS；
- 受限 Vim 继续由用户直接编辑临时 worktree，与 Agent 修改共享 base commit 冲突检查；
- Restore 和 Publish 仍是独立用户动作，不由项目对话 Agent 自动触发；
- 旧 Project 没有对话历史时，从当前 ProjectVersion 开始新线程，不伪造过去消息；
- V2 可以在保留 ConversationMessage、ChangeBrief、BaseSourceSnapshot、SourceDiff 和 VersionMaterialization 的前提下，将固定流水线替换为 TaskGraph。
