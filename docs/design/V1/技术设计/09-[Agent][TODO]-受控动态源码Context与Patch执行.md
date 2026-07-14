# Another Atom V1 受控动态源码 Context（上下文）与 Patch（补丁）执行

[toc]

- **文档状态：** V1 目标技术设计；静态 SourcePatchSet 与隔离 apply 已完成本地实现，动态读取、候选 revision、Repair Patch、恢复与 Railway 验收尚未实现
- **更新日期：** 2026-07-15
- **功能范围：** 已有 Project（项目）的 Engineer（工程师智能体）源码读取、Patch 生成、候选 apply、验证与恢复
- **上位设计：** [基于现有代码的对话式 AI Coding](./02-[Agent]-基于现有代码的对话式AI-Coding.md)
- **审批设计：** [Human-in-the-loop 审批机制](./05-[Agent][TODO]-Human-in-the-loop审批机制.md)
- **执行服务：** [共享独立执行服务](./08-[工程][TODO]-共享独立执行服务.md)
- **设计来源：** [20｜Project 对话路由与代码修改授权检查](../../../review/待办/20-[综合]-2026-07-14-Project对话路由与代码修改授权检查.md)
- **实现状态复核：** [26｜修改流水线设计同步与 Patch 实现检查](../../../review/待办/26-[Agent]-2026-07-15-修改流水线设计同步与Patch实现检查.md)
- **第一阶段实现：** [静态源码 Context 与 Patch 执行](./10-[Agent][TODO]-静态源码Context与Patch执行.md)

## 背景

当前 V1 会在调用 Engineer（工程师智能体）之前，由 Runtime（运行系统）一次性挑选一批源码交给模型。小项目可以发送全部源码；源码超过字符预算后，系统按固定顺序选择完整文件。这个方案已经解决了“模型完全看不到真实代码”的问题，但仍有两个缺口：第一次没有选中真正相关的文件时，模型不能继续读取；第一次 Patch（代码补丁）应用或验证失败时，模型也不能基于真实错误继续修正。

本文把目标确定为一条有边界的完整闭环：模型先读取初始源码，信息不足时结构化申请补充；信息足够后生成小范围 Patch；Runtime 在隔离候选工作区应用并立即执行构建、单元测试和校验；属于代码问题且仍有预算时，把结构化错误和当前候选源码重新交给 Engineer 生成 Repair Patch（修复补丁）。所有候选修正通过后才创建 ProjectVersion（项目版本）和 Git commit（Git 提交），失败或达到上限时直接丢弃候选，不影响当前版本。

“静态源码 Context → 单次 Patch → 隔离 apply”第一阶段已经完成本地实现，但不是终态。终态 Contract 仍需补齐候选 revision（候选修订号）、Patch attempt（补丁尝试）、ContextReceipt（上下文回执）和验证反馈，才能支持动态读取与有界 Repair Patch，且不推翻已经完成的 Patch 校验和 apply 链。

## 摘要

- **源码事实**
  - Runtime 始终掌握基线和当前候选 revision 的完整源码 Manifest（清单）与文件 hash（内容摘要）；模型只看到当前任务需要的源码工作集。
- **渐进读取**
  - 初次信息不足时，Engineer 返回 `NeedContext`（需要更多上下文），由 Runtime 受控执行列出、字面量搜索或读取；小项目仍可一次发送全部源码。
- **小步修改**
  - Engineer 只输出绑定当前候选 revision、Manifest、ContextReceipt 和逐文件 `before_hash` 的 `SourcePatchSet`；修改或删除现有文件前必须完整读取该 revision 的文件内容。
- **即时验证**
  - 每次 Patch 成功应用后，Runtime 都重新计算真实 Diff，并依次执行 Build（构建）、Unit Test（单元测试）和 Validator（校验器）；模型不能自报通过。
- **有界修正**
  - V1 默认最多三次 Patch 尝试：一次初始 Patch、最多两次 Repair Patch；初始读取最多补充两轮，每次修复最多补充一轮，不允许无限 Agent loop（智能体循环）。
- **提交与回滚**
  - 多次 Patch 只形成隔离候选 revision，不逐次 Git commit；全部验证通过后才创建一个项目版本。失败、取消或达到上限时丢弃候选，当前版本和已发布版本不变。
- **恢复依据**
  - 系统保存每次模型动作、读取结果、Patch attempt、候选 revision、真实 Diff 和验证报告；Worker（后台工作器）重启后从最后一个已完成检查点继续。

## 1. 设计结论

V1 采用“**完整源码清单 + 简化仓库地图 + 有次数上限的动态读取 + 小步 Patch + 每步验证 + 有界修正**”，而不是“第一次截取一批文件后一次性生成并结束”：

```text
用户批准修改代码
      |
      v
Runtime（运行系统）绑定基线版本和 Git 提交
      |
      v
BaseSourceManifest（基线源码清单：全量路径、hash 和大小）
      +
RepositoryMap（仓库地图：文件结构和少量关键元数据）
      +
完整有效 ProductSpec（产品规格）
      +
ArchitectureDesign（架构设计）
      +
ChangeBrief（本轮修改说明）
      |
      v
InitialSourceContext（初始源码上下文，candidate revision 0）
      |
      v
Engineer（工程师智能体）-> EngineerAction（工程师动作）
      |
      +-- NeedContext（需要更多上下文）
      |        |
      |        `-----------> Runtime 执行列出 / 搜索 / 读取源码
      |                            |
      |                            v
      |                     ContextReceipt（上下文回执）更新
      |                            |
      |                            `----> Engineer（最多两轮额外读取）
      |
      +-- CannotProceed（无法继续）---> 等待补充信息 / 失败
      |
      `-- ProducePatch（生成补丁）----> SourcePatchSet（源码补丁集，attempt 1）
                                          |
                                          v
                              Runtime 在隔离 worktree（候选工作区）
                              校验并应用 Patch
                                          |
                                          v
                              CandidateRevision（候选修订）1
                              + 全仓库 SourceDiff（源码差异）
                                          |
                                          v
                              Build（构建）/ Unit Test（单元测试）/
                              Validator（校验器）
                                          |
                  +-----------------------+-----------------------+
                  |                                               |
                  v                                               v
               全部通过                                  可修复的代码失败
                  |                                               |
                  v                                               v
      ProjectVersion（项目版本）                   RepairContext（修复上下文：
      + 一个 Git commit                           错误证据 + 当前候选源码）
                                                                  |
                                                                  v
                                               EngineerAction（每次修复最多补读一轮）
                                                                  |
                                                                  v
                                               Repair Patch（attempt 2 / 3）
                                                                  |
                                                                  `----> 应用到当前候选 revision，
                                                                         再次完整验证

不可修复、取消或达到 Patch 上限
      |
      `---> 丢弃候选工作区；当前版本和发布指针不变
```

### 1.1 2026-07-15 实现状态校正

静态第一阶段已在本地完成：修改生产路径调用 `create_source_patch_set(...) -> SourcePatchSet`，Runtime 校验基线、静态 Context hash、路径和 `before_hash`，执行 `git apply --check` 与隔离 apply，再从 apply 后文件重建 AppSpec、SourceBundle 和 SourceDiff。旧 `revise_app_spec(...) -> AppSpec` 只保留兼容用途，正式修改路径和验证失败路径都不再回退到完整 AppSpec。

本节的动态与修正目标仍未完成：当前没有 `EngineerAction`、`NeedContext`、RepositoryMap、Context Exchange、ContextReceipt、CandidateRevision 或 Repair Patch。因此可以表述为“静态 Context 下模型产出 Patch、本地校验并 apply”，不能表述为“动态 Context 与有界修正已实现”。Railway 真实 Provider 与重启恢复也仍需验收。

这里的循环只发生在固定 Engineer（工程师智能体）阶段内部，包括受控读取、生成 Patch、接收确定性验证反馈和生成 Repair Patch，不改变 V1 固定角色顺序。Lead（团队负责人智能体）不能借此选择角色，Engineer 不能调用其他 Agent（智能体），Runtime 也不因为模型请求而开放任意 Tool（工具）。产品经理、架构师、工程师和 Runtime 仍按既定顺序执行；TaskGraph（任务图）、角色子集、并行和跨角色自主返工继续属于 V2。

## 2. 当前实现与目标差距

### 2.1 已实现的静态纵切

当前 `BaseSourceSnapshot` 保存基线 commit 下全部受控文件及内容，`build_source_context()` 按以下顺序装箱，并把 Runtime 管理的 `app-spec.json` 排除在模型可修改 Context 之外：

1. 用户明确选择的文件；
2. 用户消息中出现准确相对路径的文件；
3. 其他文件按规范化相对路径升序。

每个文件要么完整加入，要么省略；累计内容不超过 `MAX_SOURCE_CHARS`。结果保存为唯一 `source_context` Artifact，Engineer Provider 接收其中的 `included_files`，事件和消息只展示包含/省略清单。

该实现的合理部分继续保留：

- 源码只从基线 commit 读取；
- 全量 `source_manifest_hash` 不因裁剪而变化；
- 用户选择和准确路径引用优先；
- 单个文件不被静默截断；
- Source Context 具备稳定 hash 和恢复依据。

### 2.2 需要替换的假设

静态纵切隐含“第一次选中的源码就是 Engineer 的全部 Context”；单次 Patch 方案还隐含“第一次修改必然能够 apply 并通过验证”。这两个假设都无法稳定成立：

- 路径排序不能证明文件与任务相关；
- 被省略文件可能包含入口、调用方、类型、配置或测试；
- Engineer 看得到 `omitted_files`，但不能取得其内容；
- 模型无法区分“确实无关”和“只是没被发送”；
- SourcePatchSet 即使能 apply，也可能基于错误的局部理解改变行为；
- unified diff 可能因上下文不匹配而无法 apply；
- Patch 即使成功 apply，也可能产生语法、构建、单元测试或验收失败；
- 如果验证错误不能回到 Engineer，系统只能终止，不能利用已经取得的确定性反馈修正候选。

目标实现将静态 `SourceContext` 降级为迁移兼容对象，并以 `BaseSourceManifest + CandidateRevision + RepositoryMap + SourceContextReceipt + PatchAttempt` 作为长期 Contract。完整 AppSpec 修改路径已经由静态 `SourcePatchSet` 替换；下一步是用 `EngineerAction` 接入动态读取，并把单个 Patch Artifact 扩展为可恢复的候选 revision 与 Patch attempt 链。

## 3. 范围与明确不做

### 3.1 V1 范围

本文只解决已有 Project 中 Engineer 如何取得必要源码、生成小步 Patch，并根据 Runtime 的确定性反馈进行有界修正：

- 从固定基线 commit 枚举受控源码；
- 构建低分辨率 RepositoryMap；
- 生成小仓库全量或大仓库局部的 InitialSourceContext；
- 执行有界 `list_source_files / search_source / read_source_file`；
- 持久化每轮 Context Exchange 和最终 Context Receipt；
- 生成并校验绑定当前 candidate revision 的 SourcePatchSet；
- 在隔离候选工作区 apply，形成不可混用的 CandidateRevision；
- 每次成功 apply 后重算增量 Diff 和相对原始基线的完整 SourceDiff；
- 接入现有 Build、Unit Test 和 Validator，并对可修复代码失败生成 RepairContext；
- 在固定 Patch 次数和 Context 预算内生成 Repair Patch；
- 全部验证通过后只创建一个 ProjectVersion 和 Git commit；失败时丢弃候选。

### 3.2 V1 不做

- 不预建全仓库向量 Embedding 或引入向量数据库；
- 不依赖语义检索证明依赖完整性；
- 不开放任意正则、Shell、Git、包管理器、网络或直接写文件 Tool；
- 不允许模型自行扩大 Project、用户、基线版本或受控源码范围；
- 不引入 Explore 子代理、Planner 角色或动态任务图；
- 不允许无限读取、无限 Patch 修正或模型自行决定预算；
- 不允许模型直接调用 `run_command`、`git_diff`、`git_checkout` 或操作候选 Git；
- 不为每个小 Patch 创建 ProjectVersion 或 Git commit；
- 不把平台故障、基线冲突、需求歧义或能力缺口交给 Engineer 反复修改掩盖；
- 不在 Lead 普通问答中启动完整 Engineer 读取循环；
- 不把非 Web 项目改写成 Web 项目来适配现有 Runtime。

## 4. 基线与仓库地图 Contract

### 4.1 BaseSourceManifest

`BaseSourceSnapshot` 当前同时承担“全量基线证明”和“把文件内容交给模型”两种职责。目标 Contract 将两者拆开：

```text
BaseSourceManifest
  schema_version
  project_id
  base_version_id
  base_git_commit
  adapter_id
  files[]:
    path
    sha256
    size_bytes
    language?
    role: source | test | config | documentation
    generated: bool
    protected: bool
  source_manifest_hash
```

约束：

- Manifest 覆盖基线 commit 下 Runtime Adapter 允许进入 AI Coding 的全部受控文本文件；
- `source_manifest_hash` 按规范化路径和内容 hash 确定性计算；
- Manifest 不包含 `.git`、Secret、依赖缓存、构建产物、二进制、宿主路径和其他用户文件；
- `generated/protected` 由 Adapter 或平台策略给出，模型不能改写；
- BaseSourceManifest 是 Approval、CumulativeSourceDiff 和最终版本 CAS 的原始基线；revision 1 之后的读取与 Patch 另绑定对应 CandidateRevision Manifest。

Runtime 可以在内部保留从基线 commit 读取全量内容的能力，但不把 Manifest 等同于“模型已经看过全部源码”。

### 4.2 RepositoryMap

RepositoryMap 是全仓库低分辨率结构，不是完整源码，也不等同于向量索引：

```text
RepositoryMap
  schema_version
  project_id
  base_git_commit
  source_revision
  candidate_revision_hash
  source_manifest_hash
  adapter_id
  entries[]:
    path
    language?
    role
    size_bytes
    content_hash
    symbols[]?
    imports[]?
    entrypoint: bool
    protected: bool
  map_version
  map_hash
```

V1 的最低可用 RepositoryMap 只要求当前 revision 的完整文件树、文件角色、语言、大小、hash、入口和保护状态。符号与 import 只有在 Adapter 能确定性解析时才加入；解析能力不存在时保持空值，不能由文件名或模型猜测伪造依赖图。

`web-static-v1` 可以先提供已知入口和文件角色，不要求为了本文立即引入多语言 AST。后续符号索引只能作为提高定位效率的 Adapter 能力，不能改变 Git 文件是源码事实的原则。

### 4.3 CandidateRevision

小步 Patch 不逐次写入 Project Git，而是在同一隔离候选工作区形成单调递增的候选 revision（候选修订）：

```text
CandidateRevision
  run_id
  revision                     # 0 为基线；成功 apply 后依次为 1、2、3
  parent_revision?
  base_version_id
  base_git_commit
  source_bundle_ref
  source_manifest_hash
  repository_map_hash
  produced_by_patch_attempt_id?
  incremental_source_diff_ref? # 相对 parent revision
  cumulative_source_diff_ref?  # 相对原始基线
  execution_report_ref?
  validation_report_ref?
  status:
    baseline |
    applied |
    validation_failed |
    passed
  candidate_revision_hash
```

约束：

- revision 0 映射 `base_git_commit`，不是一次新 Git commit；
- Patch 只有通过 Schema、路径、hash 和 apply 检查后才生成下一个 revision；apply 失败时 revision 不前进；
- 每个 revision 都有完整 SourceBundle、Manifest 和 RepositoryMap，Repair Patch 必须绑定它实际读取和修改的 revision；
- 新 revision 的源码事实由 Runtime 从隔离工作区重新枚举，不由模型声明；
- CandidateRevision 只属于当前 Run，不能作为其他 Run 的基线或发布对象；
- 中间 revision 不创建 ProjectVersion，也不移动 Git ref 或发布指针；
- Worker 可以从基线和已接受 Patch 链重建 revision，并用持久化 SourceBundle/hash 校验结果。

`BaseSourceManifest` 始终用于绑定用户批准的原始基线；`CandidateRevision.source_manifest_hash` 用于绑定当前 Patch 输入。两者不能用同一个字段含混表达。

## 5. InitialSourceContext

Runtime 在进入 Engineer 阶段时生成初始工作集：

```text
InitialSourceContext
  base_source_manifest_ref
  repository_map_ref
  source_revision: 0
  complete_contract_refs[]
  selected_files[]
  mentioned_files[]
  failure_evidence_refs[]
  provided_source_units[]
  max_source_chars
  used_source_chars
  context_policy_version
  initial_context_hash
```

选择规则：

1. ProductSpec、ArchitectureDesign、ChangeBrief、preserve、acceptance criteria 和 Capability Policy 继续完整提供，不与源码竞争同一裁剪顺序；
2. 若全部受控源码字符数不超过 `MAX_SOURCE_CHARS`，初始工作集包含全部完整文件，Engineer 可以第一轮直接产生 Patch；
3. 若源码超过预算，初始工作集只优先加入用户明确选择的文件、消息中的准确相对路径、错误证据明确指向的文件和 Adapter 固定入口；
4. 大仓库模式不再用“其余路径升序”填满剩余预算；未选文件通过 RepositoryMap 保持可发现，再由 Engineer 请求读取；
5. 任一文件加入后必须完整计入 Receipt；放不下时明确列为 `not_provided`，不能截断后冒充完整文件；
6. 用户选择只是优先级信号，不是越权许可。Runtime 仍按 owner、Project、基线和 Adapter 重新读取。

小仓库仍全量发送并不违背“非全量源码”方向：非全量是系统具备按需读取的能力，不是为了形式上局部而强行遗漏可以低成本完整提供的源码。

### 5.1 RepairContext

Patch apply 或验证失败后，Runtime 不把无界终端日志直接塞回 Prompt，而是生成结构化 RepairContext（修复上下文）：

```text
RepairContext
  run_id
  patch_attempt_index
  source_revision
  candidate_revision_hash
  input_source_manifest_ref
  repository_map_ref
  previous_patch_ref
  incremental_source_diff_ref?
  cumulative_source_diff_ref?
  failure_stage:
    patch_check |
    patch_apply |
    build |
    unit_test |
    validation
  failure_code
  failure_summary
  diagnostics[]:
    tool
    path?
    line?
    message
    excerpt?
  automatically_provided_files[]
  carried_context_receipt_ref
  remaining_patch_attempts
  remaining_context_rounds
  repair_context_hash
```

生成规则：

- apply 检查失败时没有新 revision，RepairContext 继续绑定原输入 revision，并包含失败 hunk、路径和确定性错误；
- Build、Unit Test 或 Validator 失败时已经存在新的候选 revision，RepairContext 绑定该失败 revision；
- Runtime 自动把上一 Patch 实际改变的文件以当前 revision 的完整内容加入修复工作集；内容过大无法加入时明确失败，不把旧内容冒充当前内容；
- 先前完整读取且在新 revision 中 hash 未变化的文件可以按 hash 继承读取证明；hash 已变化的文件必须以当前内容重新进入 Receipt；
- diagnostics 只保留修复所需的有界错误、路径、行号和摘录，不包含 Secret、宿主路径、无界日志或模型私有推理；
- Runtime 决定失败是否可修复。Engineer 只能基于已接受的 RepairContext 生成动作，不能把平台错误自行改判为代码错误。

## 6. EngineerAction Contract

Engineer 每次模型调用只返回一个互斥动作：

```text
EngineerAction = NeedContext | ProducePatch | CannotProceed

common fields
  phase: initial | repair
  patch_attempt_index
  source_revision
  source_manifest_hash
  input_context_hash
```

`phase=initial` 时 `source_revision=0`；`phase=repair` 时必须绑定 Runtime 指定的当前候选 revision。模型不能自行选择回到旧 revision，也不能跳过 attempt 序号。

### 6.1 NeedContext

```text
NeedContext
  action: need_context
  phase
  patch_attempt_index
  source_revision
  input_context_hash
  summary
  requests[]: SourceReadRequest
```

它表示当前 revision 的 Context 不足以安全生成 Patch。`summary` 只解释读取目的，不作为文件权限依据。Runtime 校验请求后从同一 revision 执行允许的读取，并把结果加入下一次 Engineer Context。修复阶段不能借 `NeedContext` 切换回原始基线或读取另一个候选 revision。

### 6.2 ProducePatch

```text
ProducePatch
  action: produce_patch
  phase
  patch_attempt_index
  source_revision
  input_context_hash
  patch: SourcePatchSet
```

它表示 Engineer 已完成当前 attempt 的信息收集并提交候选 Patch。Runtime 仍需校验 Context 覆盖、输入 revision、Manifest hash、路径、Capability Policy 和 apply 结果；动作类型不代表 Patch 已被接受，也不代表构建或测试已经通过。

### 6.3 CannotProceed

```text
CannotProceed
  action: cannot_proceed
  phase
  patch_attempt_index
  source_revision
  input_context_hash
  reason_code:
    context_insufficient |
    requirement_ambiguous |
    capability_unsupported |
    source_inconsistent |
    repair_not_safe
  summary
  missing_information[]
```

模型只能报告无法继续的原因，不能自行把 Run 标记为 `needs_input`、`failed` 或 `completed`。Runtime 根据确定性事实映射状态；模型声称 capability unsupported 也必须由 Capability Policy 验证。

### 6.4 互斥规则

- `action=need_context` 时必须有至少一个合法请求，且不得同时包含 Patch；
- `action=produce_patch` 时必须包含 Patch，且不得同时请求源码；
- `action=cannot_proceed` 时不得包含读取请求或 Patch；
- action 的 `phase / patch_attempt_index / source_revision / input_context_hash` 必须与当前 Orchestrator 状态完全一致；
- Schema retry 只修复结构化输出，不增加源码读取轮次；
- 模型返回自然语言“我还需要某文件”但没有结构化 `NeedContext` 时，视为无效输出，不由 Runtime 猜测其请求。

## 7. SourceReadRequest 与 Runtime 读取 Tool

### 7.1 SourceReadRequest

```text
SourceReadRequest
  request_id
  operation:
    list_source_files |
    search_source |
    read_source_file
  purpose
  path_prefix?
  path?
  query?
  start_line?
  end_line?
```

`request_id` 在当前 Run 内唯一。`purpose` 用于审计和后续评估，不授予额外权限。

`SourceReadRequest` 不允许模型填写 revision。Runtime 从当前 `EngineerAction.source_revision` 注入并校验读取 revision，避免模型读取旧 revision 后把 Patch 应用到新候选。

### 7.2 list_source_files

用途是按受控目录或文件角色缩小文件树。它只返回当前 revision Manifest 已存在的规范化相对路径和元数据，不读取内容，不遍历宿主文件系统，也不显示被策略排除的文件。

### 7.3 search_source

V1 只支持受控源码中的字面量文本搜索：

- `query` 必须是有界非空文本；
- 可选 `path_prefix` 必须是规范化 Project 相对路径；
- Runtime 固定最大匹配数、单条摘录长度和总返回字符数；
- 结果包含 `path / line / excerpt / content_hash` 和 `has_more`；
- 不接受模型提交任意正则、Shell 参数或搜索命令；
- 搜索结果用于定位，不表示对应文件已被完整读取。

语义检索未来可以作为新的 `operation` 加入，但不得悄悄替换字面量搜索或改变 Context Receipt 语义。

### 7.4 read_source_file

Runtime 从当前 `source_revision` 对应的不可变 SourceBundle 读取指定受控文件：

- `path` 必须存在于当前 revision 的 SourceManifest；
- 未提供行范围时读取完整文件；
- 提供范围时只用于探索，并记录准确的起止行和内容 hash；
- 内容按不可信数据块标记，源码注释中的指令不能覆盖系统和项目规则；
- 完整读取的文件进入 `fully_read_files`；片段读取只进入 `read_ranges`；
- 文件内容、Manifest hash 或 candidate revision hash 不一致时停止当前 Run。

### 7.5 SourceReadResult

```text
SourceReadResult
  request_id
  operation
  source_revision
  source_manifest_hash
  status: completed | denied | not_found | limit_exceeded
  files[]?
  matches[]?
  content_blocks[]?
  chars_added
  result_hash
  has_more
  error_code?
```

Runtime 返回结构化结果，不把命令输出原样拼接进 Prompt。相同 candidate revision hash、请求、Policy 和 Tool 版本必须得到相同结果 hash。

## 8. 动态扩展与预算

### 8.1 轮次定义

- 初始阶段 Round 0 是 InitialSourceContext 后的第一次 Engineer 调用；
- 初始阶段最多接受两次 `NeedContext`，即默认 `MAX_INITIAL_CONTEXT_ROUNDS=2`；
- 每次 RepairContext 后最多接受一次 `NeedContext`，即默认 `MAX_REPAIR_CONTEXT_ROUNDS=1`；
- 每次 `NeedContext` 可以包含多个读取请求，但请求数量、搜索匹配数、单次读取大小和结果总量均由 `ContextPolicySnapshot` 限制；
- 对应阶段的扩展次数耗尽后，下一次 Engineer 调用必须返回 `ProducePatch` 或 `CannotProceed`；继续返回 `NeedContext` 时产生 `SOURCE_CONTEXT_ROUND_LIMIT`；
- 配置可以在部署前收紧，但不能在 Run 中途变化。Run 保存实际 Policy 快照和版本。

### 8.2 累计字符预算

现有 `MAX_SOURCE_CHARS` 改为“当前 Engineer 在一个 source revision 上可见的去重源码工作集上限”，而不是单次静态装箱上限：

- 同一完整文件跨轮次重复出现只计一次；
- 不同片段按实际新增字符计入；
- 同一范围重复读取不增加工作集字符数，但仍记录重复请求；
- revision 变化后，hash 未变化的完整文件可以继承读取证明且不重复计入；hash 变化的文件按当前完整内容重新计入；
- RepositoryMap、完整文档、Prompt 模板和输出预算不计入该字段，但 Provider Adapter 必须为它们预留模型 Context 空间；
- Runtime 不能因为剩余预算不足而缩短用户请求的行范围后继续，必须返回明确的 `limit_exceeded`；
- 如果安全生成 Patch 所需的完整目标文件无法放入预算，Engineer 必须 `CannotProceed`，Run 进入可见失败或等待用户缩小范围。

`MAX_SOURCE_CHARS` 仍是稳定、可测试的部署配置。V1 不要求为不同 Provider 动态计算 tokenizer；真实 input/output token 继续由 Provider Usage 记录。

### 8.3 Patch 尝试预算

V1 默认 `MAX_PATCH_ATTEMPTS=3`，包括一次 initial Patch 和最多两次 Repair Patch：

- `NeedContext` 和 Schema retry 不增加 Patch attempt；只有通过 Schema 的 `ProducePatch` 才占用一次；
- Patch check/apply 失败不生成新 revision，但已经消耗本次 Patch attempt；
- Patch 成功 apply 后无论验证通过与否都会生成一个新 CandidateRevision；
- 只有 Runtime 判定为可修复的代码失败、仍有 Patch attempt、配额和 Context 预算时才进入下一次修复；
- 第三次 Patch 后仍未通过时返回 `PATCH_ATTEMPT_LIMIT`，不再调用 Engineer；
- Run 保存 `PatchPolicySnapshot`，至少包含 Patch 次数、每次修复读取轮次、Patch 文件数、变更行数、单文件大小、验证超时和实际 Provider 配额上限；
- 部署可以收紧默认值，但不能在同一 Run 中途放宽。

“三次”是 V1 的交付上限，不是模型权利：Runtime 可以因不可修复错误、范围扩大、用户取消、基线冲突或配额不足提前停止。

### 8.4 为什么不用无限 Tool Loop

动态读取和验证修正都能提高成功率，但会增加模型调用、延迟、候选状态和恢复复杂度。V1 通过读取轮次与 Patch 次数双重上限取得可用性与可交付性的平衡：

- 简单修改通常在 Round 0 完成；
- 一次搜索和一次定向读取可以处理常见跨文件定位；
- 验证失败后的修复必须针对确定性错误，不允许无新证据重复生成；
- 读取或 Patch 上限仍不足，说明任务范围、仓库地图、测试反馈或 Adapter 能力不够，继续循环只会增加成本并放大错误；
- 后续是否提高上限必须由真实失败样本和评估证明，不能仅因模型请求继续而自动放宽。

## 9. SourceContextReceipt

每次 `ProducePatch` 对应一个冻结的 `SourceContextReceipt`（下文简称 ContextReceipt），证明 Engineer 在该 source revision 上实际看到了什么：

```text
SourceContextReceipt
  schema_version
  project_id
  run_id
  base_version_id
  base_git_commit
  phase: initial | repair
  patch_attempt_index
  source_revision
  candidate_revision_hash
  input_source_manifest_hash
  repository_map_hash
  context_policy_version
  starting_context_type: initial | repair
  starting_context_hash
  exchanges[]:
    sequence
    input_context_hash
    action_hash
    read_request_refs[]
    read_result_refs[]
  fully_read_files[]:
    path
    content_hash
    size_bytes
  read_ranges[]:
    path
    start_line
    end_line
    content_hash
  searched_queries[]
  not_provided_files[]
  denied_requests[]
  used_source_chars
  final_context_hash
  receipt_hash
```

ContextReceipt 的作用不是声称“相关文件已经全部找到”，而是提供可检查事实：模型在指定 revision 获得了哪些完整文件、哪些片段、做过哪些搜索、哪些请求被拒绝，以及生成本次 Patch 时的最终 Context hash。

约束：

- Receipt 由 Runtime 生成，模型不能提交或修改；
- `fully_read_files` 只包含当前 revision hash 已校验的完整文件；
- 从上一 revision 继承的完整读取证明必须同时满足路径和内容 hash 不变；上一 Patch 改过的文件由 Runtime 以当前完整内容刷新；
- Receipt 绑定全部 Exchange，任何读取结果变化都会改变 `receipt_hash`；
- 用户可见事件只展示路径、动作、字符量和错误，不默认展示完整源码；
- SourcePatchSet 必须绑定同一 `patch_attempt_index / source_revision` 的 `receipt_hash`，不能复用其他 Run、其他 revision 或更早 Patch 的 Receipt。

## 10. SourcePatchSet Contract

```text
SourcePatchSet
  schema_version: 2.0
  project_id
  run_id
  patch_attempt_id
  patch_attempt_index
  patch_kind: initial | repair
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
  patches[]:
    path
    operation: modify | add | delete
    before_hash?
    unified_diff
```

### 10.1 Context 覆盖规则

- `modify`：目标文件必须存在于当前 revision 的 `ContextReceipt.fully_read_files`，且 `before_hash` 与 `input_source_manifest_hash` 对应文件 hash 一致；
- `delete`：目标文件必须被完整读取，并提供 `before_hash`；
- `add`：目标路径不得在输入 revision 中存在，不要求 before hash，但必须符合 Adapter、Capability Policy、目录和文件类型限制；
- `patch_kind=initial` 时不得包含 repair 字段；`patch_kind=repair` 时 `repair_context_hash / repairs_failure_code` 必须与当前 RepairContext 一致；
- rename 在 V1 中表示一条 delete 和一条 add，不增加独立操作类型；
- 只读过局部行范围的文件不得修改或删除；未来若要支持局部覆盖证明，需要单独设计 hunk 与 read range 的包含关系；
- Patch 不能修改输入 revision Manifest 标记为 protected 的文件；
- Patch 数组之外的文件在 apply 后必须保持 byte-level 相同。

### 10.2 小步修改规则

- 每个 Patch attempt 只处理当前失败假设直接涉及的文件和代码块；Runtime 根据 `PatchPolicySnapshot` 校验文件数、变更行数、单文件大小和实际 SourceDiff；
- Repair Patch 必须通过结构化字段绑定上一轮 RepairContext 和 failure code，并在 `summary` 中解释修复目标；无新增错误证据时不得重复提交等价 Patch；
- 如果实际修改超过已批准范围或大改阈值，Runtime 暂停并进入 pre-commit Approval，不能因为还有 repair attempt 就自动继续；
- 对同一文件的全量替换不是默认策略。确有必要时仍须通过 before hash、Diff 大小和风险策略检查；
- 多个 Patch attempt 共同形成一个候选 Patch chain，不分别创建 Git commit；最终 SourceDiff 始终相对原始基线计算。

### 10.3 Patch 不是最终证据

模型提供的 unified diff 只是候选指令。Runtime 不接受模型自报的 changed files、line stats、测试通过或兼容性结论。每个 CandidateRevision 的 SourceDiff、SourceBundle、ExecutionReport 和 ValidationReport 都必须从 apply 后真实候选工作区生成。

## 11. Provider 接口

目标接口不再把“读取源码”和“生成 Patch”拆成互不相干的 Provider 方法，而是统一为一个带判别字段的动作：

```python
create_engineer_action(
    context: EngineerContext,
) -> EngineerAction
```

`EngineerContext` 每轮由 Runtime 确定性重建：

```text
EngineerContext
  phase / patch_attempt_index
  source_revision / candidate_revision_hash
  complete ProductSpec
  complete ArchitectureDesign
  ChangeBrief / RequirementDelta
  preserve / acceptance criteria
  Capability Policy
  BaseSourceManifest
  RepositoryMap
  cumulative SourceContextReceipt draft
  actual source blocks in current working set
  RepairContext?
  ContextPolicySnapshot
  PatchPolicySnapshot
```

Provider 不依赖隐藏会话记忆决定已经读过什么或当前修改到哪一步。每次调用都从持久化 Artifact、Context Exchange、CandidateRevision 和验证报告重建同一输入；`input_context_hash` 相同意味着 Provider 收到的业务输入相同。

Mock、Ollama/DeepSeek 和未来 Provider Adapter 必须共享同一 Pydantic Contract。初始修改和验证修复调用同一个 `create_engineer_action()`，通过 `phase` 与 RepairContext 区分，不再保留一个绕开 Patch Contract 的 `repair_app_spec()`。Provider fallback 只能重试相同 Engineer Context，不能在 fallback 时改变文件范围、source revision、attempt 或 Policy。

## 12. Orchestrator 状态机

```text
CandidateRevision(0 = base)
  -> EngineerContextPreparing(phase=initial, attempt=1)
  -> EngineerRunning
       |-- NeedContext -> SourceContextReading -> EngineerRunning
       |-- CannotProceed -> NeedsInput / Failed
       `-- ProducePatch
              |
              v
         PatchChecking(attempt=N, input_revision=R)
              |
              +-- check/apply 失败且可修复、N < 3
              |      -> RepairContext(input_revision=R)
              |      -> EngineerRunning(phase=repair, attempt=N+1)
              |
              `-- apply 成功
                     -> CandidateRevision(R+1)
                     -> IncrementalSourceDiff(R -> R+1)
                     -> CumulativeSourceDiff(base -> R+1)
                     -> RuntimeBuildTestValidation
                            |
                            +-- passed
                            |      -> Risk / Approval Check
                            |      -> VersionMaterializing
                            |      -> Completed
                            |
                            +-- repairable code failure、N < 3
                            |      -> RepairContext(input_revision=R+1)
                            |      -> EngineerRunning(phase=repair, attempt=N+1)
                            |
                            `-- non-repairable / limit / cancel
                                   -> CandidateDiscarded
                                   -> NeedsInput / Failed / Cancelled
```

规则：

- Project 写占用在用户批准并创建 Run 时取得，动态读取期间继续持有；
- 每个模型动作先 Schema 校验并持久化，再执行对应 Runtime 分支；
- 每批 Runtime 读取完成并持久化后，才进入下一次 Provider 调用；
- `NeedContext` 不创建子 Run，也不重新执行产品或架构阶段；
- Patch check/apply 失败不生成新 revision；Build/Test/Validator 只有在 apply 成功并冻结新 revision 后才执行；
- 每次 apply 成功后都执行完整验证阶梯，不因为它是 Repair Patch 而只运行失败过的单项；
- Runtime 根据错误来源决定 `repairable`，模型不能自行要求进入下一轮；
- 修复始终基于最新成功 apply 的 candidate revision。模型不能选择任意旧 revision，也不能直接操作 Git 回退；
- Stop/Cancel 在任何等待 Provider、读取、apply 和验证阶段都能终止后续动作，但不删除已持久化证据；
- Runtime 只接受当前 `run_id / phase / patch_attempt_index / source_revision / input_context_hash` 对应的动作，迟到结果不能覆盖新状态；
- 达到 Patch、Context、配额或时间上限后停止，不能回退到完整 AppSpec 重生成，也不能创建未经验证的版本。

### 12.1 验证失败分类

Runtime 只把以下确定性代码问题标为可修复：

- unified diff header、hunk 或当前文件上下文不匹配；
- 候选源码语法、类型或固定构建检查失败；
- 项目单元测试失败，且报告能够定位到当前候选源码；
- Validator 给出明确、可操作且仍在已批准范围内的失败项。

以下情况不进入 Repair Patch：

- Provider、数据库、Artifact Storage、Runtime Executor 或网络基础设施故障；
- base version、Git commit、Manifest、CandidateRevision 或写占用冲突；
- Secret、越权路径、跨租户访问或受保护文件修改；
- 需求存在关键歧义、目标能力不受支持或修复会扩大已批准范围；
- 无新增诊断证据的重复失败。

平台故障按原阶段重试/失败策略处理；需求歧义进入 `needs_input`；范围扩大进入 Approval。三者都不能通过让 Engineer 继续改代码来掩盖。

## 13. 持久化、幂等与恢复

### 13.1 Context Exchange

当前 Artifact 表对 `(run_id, artifact_type)` 唯一，不适合直接保存多轮同类型动作。V1 新增顺序化持久化对象 `EngineerContextExchange`：

```text
EngineerContextExchange
  id
  run_id
  sequence
  phase
  patch_attempt_index
  source_revision
  round_index
  input_context_hash
  action_type
  action_payload
  action_hash
  read_result_payload?
  read_result_hash?
  status: action_recorded | reading | completed | failed
  error_code?
  created_at / updated_at

UNIQUE(run_id, sequence)
```

一次 Run 会有多个 Patch 和多个候选 revision，不能继续把唯一 `(run_id, artifact_type)` 的 `source_patch_set` Artifact 当成全部事实。V1 增加顺序化 `EngineerPatchAttempt`：

```text
EngineerPatchAttempt
  id
  run_id
  attempt_index
  phase: initial | repair
  input_source_revision
  input_candidate_revision_hash
  input_source_manifest_hash
  context_receipt_hash
  repair_context_hash?
  engineer_action_ref
  patch_payload
  patch_hash
  status:
    patch_recorded |
    check_failed |
    apply_failed |
    applied |
    validation_failed |
    passed
  output_source_revision?
  output_candidate_revision_hash?
  incremental_source_diff_ref?
  cumulative_source_diff_ref?
  execution_report_ref?
  validation_report_ref?
  error_code?
  created_at / updated_at

UNIQUE(run_id, attempt_index)
```

每个成功 apply 的 attempt 同时建立一条 CandidateRevision 记录，其 SourceBundle 放入 Artifact Storage 并由 hash 引用。Run 完成后可额外生成唯一 `source_patch_chain` Artifact，列出所有 attempt、revision 和最终通过的候选；它是聚合索引，不替代过程记录。

### 13.2 事务边界

- Provider 返回的 EngineerAction、Schema 校验结果和对应 Usage settlement 在同一数据库事务提交；
- Runtime 读取结果、结果 hash、累计字符量和 Exchange 完成状态在同一事务提交；
- `SourcePatchSet`、对应 ContextReceipt 与 PatchAttempt 的 `patch_recorded` 状态在同一事务冻结，Patch 不得指向仍会变化的 Receipt draft；
- apply 后 SourceBundle、两个 SourceDiff、CandidateRevision 和 PatchAttempt 输出字段在同一事务建立引用；
- Build/Test/Validator 报告与 PatchAttempt 的 `passed / validation_failed` 状态在同一事务提交；
- 外部 Provider 调用无法做到数据库意义上的 exactly-once。系统保证已持久化的有效动作不会因 Worker 重领而再次调用；进程在外部请求完成但本地提交前崩溃时，可能发生一次重复请求，必须通过 trace、attempt 和 Usage 记录可见，不能宣称绝对不重复计费。

### 13.3 Worker 恢复

恢复时按以下顺序判断：

1. 重新校验 Run 的 base version、base commit 和 Project 写占用；
2. 读取已完成 Exchange、PatchAttempt 和 CandidateRevision，按 sequence/attempt 重建当前 revision 与 ContextReceipt draft；
3. 已记录 `NeedContext` 但读取未完成时，从同一 CandidateRevision SourceBundle 确定性重做 Runtime 读取并校验 result hash；
4. 已完成读取但没有下一动作时，从当前 phase/attempt 的下一 Provider 调用继续；
5. 已冻结 SourcePatchSet 但尚无 apply 结果时，从 input revision 的持久化 SourceBundle 创建干净临时目录并重新执行 check/apply；不在残留 worktree 上猜测；
6. 已存在 CandidateRevision 和 SourceDiff 时不重复 apply；已有 ExecutionReport/ValidationReport 时不重复对应验证；
7. 已记录可修复失败但下一 attempt 未开始时，从 RepairContext 继续；
8. 最终通过 revision 已物化版本时复用现有 ProjectVersion/Git 映射，不重复 commit。

任一已持久化 SourceBundle、revision、Receipt、Patch、Diff 或报告 hash 无法重建时进入 `CANDIDATE_RECOVERY_MISMATCH`，不能忽略差异继续。

## 14. 隔离候选工作区与 apply

### 14.1 候选工作区

Repository Service 从 revision 0 的 `base_git_commit` 创建当前 Run 专属临时候选 worktree；恢复时也可以从持久化 CandidateRevision SourceBundle 重建。浏览器、模型和 Runtime Executor 都不获得宿主机 Project Git 路径。

```text
Project bare/local Git
      |
      `-- base_git_commit
              |
              `-- candidate worktree / run_id
                      |-- revision 0: base
                      |-- revision 1: initial Patch applied
                      |-- revision 2: Repair Patch applied
                      `-- revision 3: final Repair Patch applied
```

revision 是 Runtime 的候选快照编号，不是 Git commit。候选 worktree 与当前 Project ref、已发布版本和其他 Run 分离。失败、取消或冲突只回收候选目录，不移动当前版本；过程 Artifact 按保留策略继续用于审计和恢复。

### 14.2 apply 顺序

1. 校验 SourcePatchSet Schema、attempt、输入 revision、CandidateRevision、Manifest 和 Receipt hash；
2. 规范化路径并拒绝绝对路径、`..`、符号链接、submodule、文件模式和二进制 Patch；
3. 校验 modify/delete 文件已在输入 revision 被完整读取且 before hash 匹配；
4. 校验 add/delete/modify 是否在 Approval、Adapter 和 Capability Policy 范围内；
5. 从输入 CandidateRevision 的完整 SourceBundle 建立干净候选目录，执行 `git apply --check` 或等价确定性检查；
6. apply 后重新枚举完整受控源码，确认 Patch 外文件相对输入 revision 保持 byte-level 相同；
7. 生成下一 CandidateRevision、SourceBundle、candidate manifest hash、相对 parent 的 IncrementalSourceDiff 和相对原始基线的 CumulativeSourceDiff；
8. 如实际 Diff 扩大批准范围，进入 pre-commit Approval，不执行版本物化；
9. 把本 revision 的候选 SourceBundle 交给 Runtime Executor 构建、测试和校验；
10. 全部门禁通过后进入 VersionMaterialization；可修复失败则生成 RepairContext 并基于当前 revision 开始下一 Patch attempt。

候选 apply 不在共享 Runtime Executor 中直接修改 Project Git。主服务 Repository Service 负责 Git 候选事实；Runtime Executor 只接收候选 SourceBundle，在自己的临时目录执行固定 Adapter。

## 15. SourceDiff、验证、修正与版本

Runtime 为每个成功 apply 的 CandidateRevision 生成两类 Diff：

```text
IncrementalSourceDiff
  parent_source_revision
  candidate_source_revision
  parent_source_manifest_hash
  candidate_source_manifest_hash
  changed_files[] / added_files[] / removed_files[]
  per_file_before_hash / after_hash
  unified_diff
  line_stats

CumulativeSourceDiff
  base_version_id
  base_git_commit
  base_source_manifest_hash
  candidate_source_revision
  candidate_source_manifest_hash
  changed_files[] / added_files[] / removed_files[]
  per_file_before_hash / after_hash
  unified_diff
  line_stats
```

IncrementalSourceDiff 用于解释本次小 Patch 做了什么；CumulativeSourceDiff 用于风险判断、最终展示和创建版本。两者都由 Runtime 根据完整文件生成，不能由模型提供。

### 15.1 每次 Patch 后的验证阶梯

成功 apply 并冻结 CandidateRevision 后，Runtime 依次执行：

1. 候选 Manifest、必要入口、文件类型、大小和 protected 路径检查；
2. Adapter 固定的语法、类型或 Build 检查；
3. 项目 Unit Test；
4. Runtime Validator 根据 ProductSpec、ArchitectureDesign、ChangeBrief 和验收条件检查结果；
5. CumulativeSourceDiff 的风险与 Approval 检查。

前一层失败后可以停止更昂贵的后续层，但下一次 Repair Patch apply 成功后必须从第 1 层重新完整执行，不能只重跑上次失败的命令。Runtime 将每层结果写成结构化 ExecutionReport/ValidationReport，并只把有界、可修复的诊断放入 RepairContext。

项目内测试文件可以在授权范围内随源码一起修改，但其变化必须进入 CumulativeSourceDiff。平台自有验证规则、受保护测试和 Runtime Validator 不进入可写 Manifest；删除或弱化项目测试本身不能被视为修复成功，最终仍须满足独立验收条件。

### 15.2 修正与终止

验证边界：

- Runtime Executor 固定执行 Adapter 登记的构建、项目单元测试和 Validator；Engineer 不能选择跳过或替换命令；
- 对可修复代码失败，下一次 Repair Patch 以失败 CandidateRevision 为输入，不能仍按最初基线生成替换整包；
- Patch check/apply 失败时没有新 revision，下一次 Repair Patch 仍以相同输入 revision 和最新错误为依据；
- Repair Patch 可以修复或显式撤销上一 Patch 的部分变化，但仍必须满足当前 revision 的 before hash 和 Context 覆盖；
- 平台错误、需求歧义、能力缺口、越权、基线冲突和范围扩大不进入自动修正；
- 修正次数耗尽后保留全部过程证据，Run 失败或等待用户输入，不创建版本；
- 只有 `ExecutionReport.status=passed` 且 `ValidationReport.passed=true` 才能创建 ProjectVersion；
- 最终创建版本时只物化最后一个通过 CandidateRevision 的 SourceBundle，并相对原始基线保存 CumulativeSourceDiff；
- 一次 Run 无论经历多少 Patch attempt，最多创建一个 ProjectVersion 和一个 Git commit；
- AI 修改成功不自动 Publish，Public Route 继续指向用户明确发布的版本；
- 最终版本 CAS 仍校验 latest version、active write run、base commit 和 candidate hash。

### 15.3 回滚语义

V1 不向 Engineer 提供 `git_checkout` 或可写 Git Tool。所谓回滚分为两层：

- **候选内修正**：Engineer 基于当前失败 revision 生成反向或补偿 Patch，Runtime 仍按普通 Patch 校验、apply 和验证；
- **Run 级放弃**：取消、不可修复、达到上限或最终 CAS 冲突时，Runtime 丢弃候选工作区，不创建 ProjectVersion；当前工作版本和已发布版本天然保持不变。

中间 CandidateRevision 可以作为过程证据保留，但不能被用户直接发布，也不能在没有完整验证的情况下提升为当前版本。

## 16. Human-in-the-loop 与风险

- 动态源码读取发生在用户点击“修改代码”并创建 `ai_edit` Run 之后；pending proposal 不启动 Engineer 读取循环；
- pre-execution Approval 绑定完整 `source_manifest_hash`，而不是绑定某个局部 Context，避免读取范围变化掩盖基线变化；
- SourceReadRequest 只是读取需求，不构成修改授权；
- Context 扩展到同一已批准 Project 的其他受控源码，不自动触发新的 Approval；
- 每个 CandidateRevision 都用 CumulativeSourceDiff 检查范围；Patch 实际增加页面、删除文件、替换入口、大面积重写或扩大批准范围时，立即暂停并触发 pre-commit Approval，批准前不继续 repair；
- Secret、其他用户文件、宿主路径和被策略排除的文件属于 deny，不能通过用户 Approval 绕过；
- Approval 等待期间基线变化后 subject stale，已有 ContextReceipt、Patch chain 和 CandidateRevision 不能应用到新版本。

## 17. 安全边界

- 所有 Manifest、Map、读取请求、Exchange、Receipt、Patch、Diff 和版本查询都按 Session 用户与 Project owner 联查；
- Runtime 初始只从绑定的 base commit 读取，修复阶段只从已冻结的 CandidateRevision SourceBundle 读取；客户端和模型不能提交文件内容作为源码事实；
- SourceReadRequest 只能访问当前 revision Manifest 中的受控文本文件；
- 路径必须使用规范化 POSIX 相对路径，拒绝绝对路径、`..`、NUL、符号链接逃逸和隐藏控制目录；
- 源码、注释、测试、文档和搜索结果作为不可信数据块输入，不能覆盖系统、项目规则或 Tool Schema；
- Engineer 没有 Shell、Git、数据库、网络、Runtime Executor、Publish 和 Repository 写 Tool；
- 日志默认只记录路径、hash、字符量、动作和错误，不记录完整源码、Provider Key、Session token 或模型私有推理；
- Context 动态扩展不能跨 Project、跨用户、跨 Run、跨 source revision 或跨 Adapter；
- 任何 Tool、索引或 Provider 失败都不能降级为“假设文件无关后继续”。

## 18. 配额、延迟与成本

动态扩展与验证修正的主要代价是额外 Provider 请求和重复 Build/Test/Validation。V1 采用以下控制：

- 小仓库全量源码未超过预算时仍允许一次 Engineer 调用完成；
- 在默认上限下，正常动作链最多包含初始阶段 3 次 Engineer 调用和两次修复各 2 次调用，共 7 次；Schema retry/Provider fallback 另按现有策略受限并可见；
- 每次 Engineer inference 单独 reserve、settle、release，不预先把最大调用数全部记为 used；
- `NeedContext` 的实际 input/output token 计入 Engineer 阶段；
- Runtime list/search/read 不消耗模型配额，但记录执行次数、字符量和耗时；
- 每个 CandidateRevision 的 Build/Test/Validation 记录 CPU、内存、持续时间和状态，不因为是修复轮次而隐藏资源消耗；
- Provider fallback 和 Schema retry 继续按实际请求结算；
- 超过 Context、Patch、时间、字符或配额上限时停止，不自动购买额外预算；
- UI 显示“正在定位源码 / 正在生成 Patch 1/3 / 正在验证候选 revision 1 / 正在根据测试失败修复 1/2”，不承诺缺少数据依据的预计完成时间。

后续是否增加 RepositoryMap 解析或语义检索，应比较“减少的无效 Provider 轮次”和“新增索引成本、陈旧风险、存储与隐私成本”，不能只因行业产品使用索引就直接加入 V1。

## 19. 事件与可观测性

新增持久化事件：

```text
engineer.context_initialized
engineer.action_started
engineer.action_completed
source.context_requested
source.context_read_started
source.context_read_completed
source.context_request_denied
source.context_round_limit
source.context_receipt_frozen
source.patch_attempt_started
source.patch_created
source.patch_check_started
source.patch_check_failed
source.patch_applied
source.candidate_revision_created
source.diff_created
source.validation_started
source.validation_failed
source.validation_passed
source.repair_context_created
source.patch_attempt_limit
source.candidate_discarded
```

每次 Exchange 至少记录：

```text
run_id / project_id / base_version_id / base_git_commit
sequence / phase / patch_attempt_index / source_revision / round_index / action_type
input_context_hash / action_hash / read_result_hash
base_source_manifest_hash / input_source_manifest_hash
candidate_revision_hash / repository_map_hash / receipt_hash?
request_count / input_tokens / output_tokens
used_source_chars / fully_read_file_count
incremental_diff_hash / cumulative_diff_hash
execution_report_hash / validation_report_hash
error_code / trace_id
```

用户界面展示读取阶段、当前 Patch attempt、候选 revision、Patch 摘要、真实 Diff、验证结果、剩余修正次数和失败出口。管理员或下载日志可以看到 Artifact/Exchange/Attempt/Revision 引用和 hash，但不默认输出完整源码或 Chain of Thought。

## 20. 错误处理矩阵

| 错误 | Runtime 行为 | 对 Project 的影响 |
| --- | --- | --- |
| `BASE_SOURCE_MISMATCH` | 基线 Git、ProjectVersion 或 SourceBundle 不一致，停止 | 当前版本不变 |
| `SOURCE_CONTEXT_REQUEST_INVALID` | EngineerAction 或请求字段无效，有限 Schema retry | 不读取文件，不创建 Patch |
| `SOURCE_CONTEXT_PATH_DENIED` | 请求不在 Manifest、路径越界或文件受保护 | 记录 denied；由 Engineer 在剩余轮次内调整，否则失败 |
| `SOURCE_CONTEXT_NOT_FOUND` | 当前 source revision 中不存在请求文件 | 记录确定性结果，不从其他 revision 猜测 |
| `SOURCE_CONTEXT_LIMIT` | 请求会超过字符或 Tool 结果上限 | 不截断冒充成功；返回 limit_exceeded |
| `SOURCE_CONTEXT_ROUND_LIMIT` | 当前 initial/repair 阶段超过对应 NeedContext 上限 | Run 失败或 needs input，不继续读取 |
| `CANDIDATE_RECOVERY_MISMATCH` | 恢复重算的 revision、Receipt、Patch、Diff 或报告 hash 不一致 | 停止恢复，当前版本不变 |
| `PATCH_CONTEXT_VIOLATION` | modify/delete 文件未完整读取或 Receipt 不匹配 | 拒绝 Patch，不进入 apply |
| `PATCH_PATH_DENIED` | Patch 路径、类型或 protected 状态越权 | 拒绝 Patch |
| `PATCH_BASE_MISMATCH` | base、input revision、Manifest、Receipt 或 before hash 不匹配 | 拒绝 Patch；不得套用到其他 revision |
| `PATCH_APPLY_FAILED` | apply --check 或 apply 失败 | 不生成新 revision；有预算时生成 RepairContext |
| `PATCH_ATTEMPT_LIMIT` | 第三次 Patch 后仍未通过 | 丢弃候选，不再调用 Engineer |
| `EMPTY_CHANGE` | apply 后没有真实源码变化 | 不创建版本 |
| `BASE_VERSION_CONFLICT` | 最终 CAS 时当前版本已变化 | 候选不接入当前版本 |
| `EXECUTION_FAILED` | 构建或单元测试出现可定位代码失败 | 有预算时进入 Repair Patch；否则不创建版本 |
| `EXECUTION_PLATFORM_FAILED` | Executor、存储、租约、超时或平台依赖失败 | 不让 Engineer 猜测修复，按平台恢复/失败处理 |
| `VALIDATION_BLOCKED` | Validator 给出可操作代码失败 | 有预算且未扩大范围时进入 Repair Patch |
| `REPAIR_SCOPE_EXPANDED` | Repair Patch 的累计 Diff 超出已批准范围 | 暂停并请求 Approval，不自动继续 |

## 21. 测试与验收

### 21.1 Contract 单元测试

- EngineerAction 三种分支互斥，缺失或混合字段拒绝；
- SourceReadRequest 的 operation 与参数组合严格校验；
- BaseSourceManifest 对相同 commit、RepositoryMap 对相同 source revision 生成稳定 hash；
- CandidateRevision 对相同 parent、Patch 和候选 SourceBundle 生成稳定 hash；
- ContextReceipt 对相同 source revision 与 Exchange 顺序生成稳定 receipt hash；
- modify/delete 只允许 fully_read_files，局部 read range 不足以授权修改；
- SourcePatchSet 必须绑定当前 patch attempt、source revision、candidate hash、Manifest 和 Receipt；
- PatchAttempt 状态、input/output revision 和报告引用组合严格校验；
- Policy 快照在 Run 内不可变化。

### 21.2 Context 选择与 Tool 测试

- 小仓库未超过预算时 Round 0 包含全部受控源码；
- 大仓库初始只包含用户选择、准确路径、错误文件和固定入口，不按路径填满无关文件；
- list 只返回 Manifest 文件；
- search 使用字面量并正确返回 `has_more`；
- read full/range 的行号、字符量和 hash 正确；
- Repair 阶段 list/search/read 只读取当前 CandidateRevision，不读取原始基线或其他 revision；
- 重复读取不重复计算工作集字符；
- revision 变化后 hash 未变文件继承读取证明，已变文件必须刷新完整内容；
- 路径穿越、Secret、二进制、受保护文件和其他用户 Project 被拒绝；
- 单个完整目标文件超过剩余预算时明确失败，不静默截断。

### 21.3 动态循环集成测试

- initial Round 0 直接 ProducePatch，只调用一次 Provider；
- initial Round 0 NeedContext 后 Runtime 读取，下一轮 ProducePatch；
- initial 连续两次 NeedContext 后 ProducePatch，第三次返回 round limit；
- RepairContext 后允许一次 NeedContext 再 ProducePatch，第二次 NeedContext 返回 repair round limit；
- denied/not_found/limit_exceeded 结果真实进入下一轮 Context；
- Provider fallback 接收相同 input_context_hash；
- Worker 分别在 action 持久化前后、读取前后、Receipt 冻结前后重启，已经完成的调用和读取不重复；
- 双用户不能通过 list/search/read 获得对方路径、内容或 hash。

### 21.4 Patch 与候选测试

- Patch 修改当前 revision 未完整读取文件时返回 `PATCH_CONTEXT_VIOLATION`；
- before hash、attempt、source revision、candidate hash、Manifest 或 Receipt 不匹配时拒绝 apply；
- add/modify/delete、空 Patch、越权路径、二进制和 symlink Patch 均覆盖；
- apply 失败不生成 CandidateRevision；apply 成功后 revision 单调递增；
- apply 后 Patch 外文件相对 parent revision byte-level 相同；
- IncrementalSourceDiff 与 parent/child 差异一致，CumulativeSourceDiff 与原始基线/当前候选差异一致；
- 初始 Patch 一次验证通过，只创建一个版本和 commit；
- 初始 Patch 构建失败后 Repair Patch 修复并通过，两次 Patch 仍只创建一个版本和 commit；
- Patch check 失败后基于同一 revision 修正；测试失败后基于新的失败 revision 修正；
- RepairContext 自动包含上一 Patch 改变文件的当前完整内容和结构化诊断；
- 平台失败、需求歧义、能力缺口和无新证据重复失败不进入 repair；
- 第三次 Patch 仍失败返回 `PATCH_ATTEMPT_LIMIT`，候选被丢弃且当前版本不变；
- 实际 Diff 扩大批准范围时暂停在 pre-commit Approval；
- 每个成功 apply 的 revision 都从 Build 起完整复验；
- 最终版本 CAS 冲突不覆盖新版本；
- 成功创建 `ai_edit` 版本但不移动已发布指针。

### 21.5 Railway 部署验收

- 真实 Provider 能完成“一次读取扩展后生成 Patch”和“一次测试失败后生成 Repair Patch”的已有 Project 修改；
- Railway 单副本分别在 Patch、apply、CandidateRevision 和验证报告检查点重启后恢复，不重复已持久化动作；
- 持久化 Volume 保留 Project Git、Exchange、Receipt、PatchAttempt、CandidateRevision 和版本映射；
- 主服务隔离 worktree 与 Runtime Executor 临时源码均在成功、失败、取消和超时后按设计清理；
- 浏览器刷新后仍能看到读取阶段、Patch attempt、候选 revision、真实 Diff、验证结果、剩余修正次数和失败原因。

## 22. 从当前静态 SourceContext 迁移

迁移不能同时改完所有路径后一次切换。推荐顺序：

第一阶段已按[静态源码 Context 与 Patch 执行](./10-[Agent][TODO]-静态源码Context与Patch执行.md)完成本地代码与自动化测试：`SourcePatchSet -> 隔离 apply -> 真实 Diff -> Build/Test/Validation` 已接入，省略文件不可修改且 Context 不足时明确失败。Railway 真实 Provider 和重启恢复尚未验收。

第一阶段不能成为另一套长期协议。它在迁移时必须被归入终态 Contract 的受限子集：

- 当前静态 SourceContext 生成 revision 0 的只读 ContextReceipt；没有 `NeedContext` Exchange；
- 首个 Patch 固定 `patch_attempt_index=1 / patch_kind=initial / input_source_revision=0`；
- apply 成功后生成 CandidateRevision 1、Incremental/Cumulative SourceDiff 和 PatchAttempt 记录；
- 迁移完成前可以把部署策略收紧为 `MAX_PATCH_ATTEMPTS=1`，验证失败明确终止；后续只放开 RepairContext 和 attempt 上限，不再次替换 Patch 字段；
- 省略文件不可修改且 Context 不足时明确失败，不能回退到完整 AppSpec。

后续顺序：

1. **[终态 Contract 骨架]** 增加 BaseSourceManifest、CandidateRevision、EngineerAction、SourceReadRequest/Result、SourceContextReceipt、扩展后的 SourcePatchSet、EngineerPatchAttempt 和两类 SourceDiff；保留现有 SourceContext 只读兼容。
2. **[静态 Patch 对齐]** 将当前 `source_context_hash` 迁移为 revision 0 ContextReceipt，并把现有单次 apply 映射为 PatchAttempt 1 和 CandidateRevision 1。
3. **[初始动态 Context]** 增加 RepositoryMap，把 `build_source_context()` 改造成 InitialSourceContext builder：小仓库全量，大仓库不再按路径填充无关文件。
4. **[Provider 动作接口]** 增加 `create_engineer_action()`，先接 Mock，再接 Ollama/DeepSeek；删除生产路径对 `revise_app_spec()` 和 `repair_app_spec()` 的依赖。
5. **[动态读取]** Orchestrator 接入 initial 最多两轮 NeedContext、Tool Policy、累计 Receipt、逐次配额和取消恢复。
6. **[候选持久化]** 接入 CandidateRevision SourceBundle、PatchAttempt、增量/累计 Diff 和各检查点恢复；不依赖临时 worktree 常驻。
7. **[验证反馈]** 对 apply、Build、Unit Test 和 Validator 失败分类，生成有界 RepairContext；平台错误、歧义和范围扩大不进入 repair。
8. **[有界修正]** 放开最多三次 Patch attempt、每次 repair 最多一轮 NeedContext，并在每个成功 apply 的 revision 后完整复验。
9. **[风险与版本]** 接每轮 CumulativeSourceDiff 风险检查、pre-commit Approval、最终 CAS 和 VersionMaterialization；整个 Run 只创建一个版本和 commit。
10. **[切换]** 真实 Provider 和 Railway 的动态读取、测试失败修复及重启恢复验收通过后，将终态路径设为默认；历史 Artifact 继续可读。

部署迁移期间可以使用临时 feature flag 比较静态单次 Patch 与终态循环，但 flag 不是长期产品模式。两条路径不得对同一 Run 同时写候选版本，也不得用静态结果或完整 AppSpec 作为动态/修复路径失败时的隐式降级。

## 23. 实施完成条件

本文只有同时满足以下条件才可以移除文件名中的 `[TODO]`：

- EngineerAction、动态读取、ContextReceipt、CandidateRevision、PatchAttempt 和 SourcePatchSet Contract 已在 API、Provider、Orchestrator 和持久化层统一实现；
- SourcePatchSet 已在隔离候选工作区按 revision apply，Runtime 能生成增量/累计 SourceDiff；
- apply、Build、Unit Test 或 Validator 的可修复失败能够形成 RepairContext，并在上限内生成 Repair Patch 后完整复验；
- Context、Patch、Build、Unit Test、Validator、版本 CAS 和发布边界的自动化测试通过；
- Worker 在动态读取、Patch、apply、CandidateRevision 和验证各检查点重启后能恢复，且不重复已持久化阶段；
- Railway 真实 Provider 完成至少一轮需要额外读取的修改和一轮测试失败后的修复，并保留可检查证据；
- 现有设计、README 和实现不再把静态 `MAX_SOURCE_CHARS` 装箱描述为最终方案；
- 已知能力边界明确：没有匹配 RepositoryMap/Source Adapter 的项目不能声称支持可靠动态修改。

## 24. V2 与未来扩展

在不改变 BaseSourceManifest、CandidateRevision、ContextReceipt、SourcePatchSet、Runtime apply 和真实 SourceDiff 不变量的前提下，未来可以增加：

- AST、Tree-sitter 或 Language Server 生成的符号与引用索引；
- import、调用、测试和配置依赖图；
- 语义检索作为新的只读 SourceRead operation；
- 大文件局部读取与 Patch hunk 覆盖证明；
- Explore 子代理把搜索摘要返回主 Engineer；
- 不同项目类型的 Source、Build、Test 和 Runtime Adapter。

这些能力必须由实际仓库规模和失败样本驱动。向量索引只能改善召回，不能替代基线 hash、读取 Receipt、Patch 权限、隔离 apply、完整 Diff 和运行验证。

## 25. 参考依据

- [OpenAI：Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)：模型通过结构化 Tool Call 请求动作，Agent 执行并把结果加入后续推理输入。
- [GitHub Copilot：Repository indexing](https://docs.github.com/en/copilot/concepts/context/repository-indexing)：语义代码索引可以改善仓库级检索，但属于具体产品能力，不是本文 V1 的必要前提。
- [Aider：Repository map](https://aider.chat/docs/repomap.html)：低分辨率仓库地图可以提供文件和关键符号结构，并在需要时引导读取具体文件。

本文只吸收“多分辨率 Context、按需读取和 Agent loop”的可验证机制，不把任何外部产品的内部索引、分片或模型策略当作 Another Atom 已实现事实。
