# Another Atom V1 受控动态源码 Context（上下文）与 Patch（补丁）执行

[toc]

- **文档状态：** V1 目标技术设计；Contract（数据契约）、动态读取循环、SourcePatchSet（源码补丁集）与隔离 apply（应用补丁）尚未实现
- **更新日期：** 2026-07-15
- **功能范围：** 已有 Project（项目）的 Engineer（工程师智能体）源码读取、Patch 生成、候选 apply、验证与恢复
- **上位设计：** [基于现有代码的对话式 AI Coding](./02-[Agent]-基于现有代码的对话式AI-Coding.md)
- **审批设计：** [Human-in-the-loop 审批机制](./05-[Agent][TODO]-Human-in-the-loop审批机制.md)
- **执行服务：** [共享独立执行服务](./08-[工程][TODO]-共享独立执行服务.md)
- **设计来源：** [20｜Project 对话路由与代码修改授权检查](../../../review/待办/20-[综合]-2026-07-14-Project对话路由与代码修改授权检查.md)

## 背景

当前 V1 会在调用 Engineer（工程师智能体）之前，由 Runtime（运行系统）一次性挑选一批源码交给模型。小项目可以发送全部源码；源码超过字符预算后，系统按固定顺序选择完整文件。这个方案已经解决了“模型完全看不到真实代码”的问题，但仍有一个关键缺口：如果第一次没有选中真正相关的文件，模型不能继续搜索或读取，只能根据不完整信息生成修改结果。

现在 `SourcePatchSet`（源码补丁集）和服务端隔离 apply（应用补丁）还没有实现，正好可以先把源码读取方式确定下来。本文将目标改为：模型先读取初始源码；信息不足时，用结构化请求说明还要查什么；Runtime 校验后补充源码；模型信息足够后再输出 Patch（代码补丁）。这样可以避免先完成“单次静态源码 → Patch”，随后又为了动态读取重做 Provider（模型适配器）、Orchestrator（编排器）、恢复和测试。

## 摘要

- **源码事实**
  - Runtime（运行系统）始终掌握基线 Git commit（Git 提交）下的完整源码清单和文件 hash（内容摘要）；模型只看到当前任务需要的源码。
- **读取方式**
  - 模型第一次拿到的信息不够时，可以返回 `NeedContext`（需要更多上下文），说明要列出、搜索或读取哪些源码；Runtime 校验后再提供结果。
- **次数边界**
  - 小项目仍可一次发送全部源码；大项目最多补充读取两轮，V1 不做无限循环、向量索引或子代理探索。
- **修改权限**
  - 模型只能修改已经完整读取的现有文件；新增文件也必须满足项目路径、文件类型和能力限制。
- **执行边界**
  - 模型最终只输出 `SourcePatchSet`（源码补丁集）；Runtime 在隔离目录应用补丁，并根据真实候选源码重新计算 `SourceDiff`（源码差异）。
- **恢复依据**
  - 系统保存每轮请求、读取结果和 `ContextReceipt`（上下文回执），Worker（后台工作器）重启后从已完成的位置继续。

## 1. 设计结论

V1 采用“**完整源码清单 + 简化仓库地图 + 有次数上限的动态读取 + 最终代码补丁**”，而不是“第一次截取一批文件后直接生成”：

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
InitialSourceContext（初始源码上下文）
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
      `-- ProducePatch（生成补丁）----> SourcePatchSet（源码补丁集）
                                  |
                                  v
                      Runtime 在隔离 worktree（候选工作区）应用补丁
                                  |
                                  v
                        Runtime 计算全仓库 SourceDiff（源码差异）
                                  |
                                  v
                         Build（构建）/ Unit Test（单元测试）/
                         Validator（校验器）
                                  |
                                  v
                        ProjectVersion（项目版本）+ Git commit（Git 提交）
```

这里的动态循环只是 Engineer（工程师智能体）阶段内部的源码读取协议，不改变 V1 固定角色顺序。Lead（团队负责人智能体）不能借此选择角色，Engineer 不能调用其他 Agent（智能体），Runtime 也不因为模型请求而开放任意 Tool（工具）。产品经理、架构师、工程师和 Runtime 仍按既定顺序执行；TaskGraph（任务图）、角色子集、并行和自主返工继续属于 V2。

## 2. 当前实现与目标差距

### 2.1 已实现的静态纵切

当前 `BaseSourceSnapshot` 保存基线 commit 下全部受控文件及内容，`build_source_context()` 按以下顺序装箱：

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

静态纵切隐含“第一次选中的源码就是 Engineer 的全部 Context”。当仓库超过预算时，这个假设无法成立：

- 路径排序不能证明文件与任务相关；
- 被省略文件可能包含入口、调用方、类型、配置或测试；
- Engineer 看得到 `omitted_files`，但不能取得其内容；
- 模型无法区分“确实无关”和“只是没被发送”；
- SourcePatchSet 即使能 apply，也可能基于错误的局部理解改变行为。

目标实现将静态 `SourceContext` 降级为迁移兼容对象，并以 `BaseSourceManifest + RepositoryMap + SourceContextReceipt` 作为长期 Contract。当前 Engineer 返回完整 AppSpec 的路径也必须由 `EngineerAction` 和 `SourcePatchSet` 替换。

## 3. 范围与明确不做

### 3.1 V1 范围

本文只解决已有 Project 中 Engineer 如何取得必要源码并生成可验证 Patch：

- 从固定基线 commit 枚举受控源码；
- 构建低分辨率 RepositoryMap；
- 生成小仓库全量或大仓库局部的 InitialSourceContext；
- 执行有界 `list_source_files / search_source / read_source_file`；
- 持久化每轮 Context Exchange 和最终 Context Receipt；
- 生成并校验 SourcePatchSet；
- 在隔离候选工作区 apply，并重算完整 SourceDiff；
- 接入现有 Build、Unit Test、Validator、版本和审批门禁。

### 3.2 V1 不做

- 不预建全仓库向量 Embedding 或引入向量数据库；
- 不依赖语义检索证明依赖完整性；
- 不开放任意正则、Shell、Git、包管理器、网络或直接写文件 Tool；
- 不允许模型自行扩大 Project、用户、基线版本或受控源码范围；
- 不引入 Explore 子代理、Planner 角色或动态任务图；
- 不允许无限读取、无限 Patch 修正或模型自行决定预算；
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
- Manifest 是 Approval、所有 Context 轮次、Patch、SourceDiff 和最终版本 CAS 的共同基线。

Runtime 可以在内部保留从基线 commit 读取全量内容的能力，但不把 Manifest 等同于“模型已经看过全部源码”。

### 4.2 RepositoryMap

RepositoryMap 是全仓库低分辨率结构，不是完整源码，也不等同于向量索引：

```text
RepositoryMap
  schema_version
  project_id
  base_git_commit
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

V1 的最低可用 RepositoryMap 只要求完整文件树、文件角色、语言、大小、hash、入口和保护状态。符号与 import 只有在 Adapter 能确定性解析时才加入；解析能力不存在时保持空值，不能由文件名或模型猜测伪造依赖图。

`web-static-v1` 可以先提供已知入口和文件角色，不要求为了本文立即引入多语言 AST。后续符号索引只能作为提高定位效率的 Adapter 能力，不能改变 Git 文件是源码事实的原则。

## 5. InitialSourceContext

Runtime 在进入 Engineer 阶段时生成初始工作集：

```text
InitialSourceContext
  base_source_manifest_ref
  repository_map_ref
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

## 6. EngineerAction Contract

Engineer 每次模型调用只返回一个互斥动作：

```text
EngineerAction = NeedContext | ProducePatch | CannotProceed
```

### 6.1 NeedContext

```text
NeedContext
  action: need_context
  summary
  requests[]: SourceReadRequest
```

它表示当前 Context 不足以安全生成 Patch。`summary` 只解释读取目的，不作为文件权限依据。Runtime 校验请求后执行允许的读取，并把结果加入下一次 Engineer Context。

### 6.2 ProducePatch

```text
ProducePatch
  action: produce_patch
  patch: SourcePatchSet
```

它表示 Engineer 已完成信息收集并提交候选 Patch。Runtime 仍需校验 Context 覆盖、基线 hash、路径、Capability Policy 和 apply 结果；动作类型不代表 Patch 已被接受。

### 6.3 CannotProceed

```text
CannotProceed
  action: cannot_proceed
  reason_code:
    context_insufficient |
    requirement_ambiguous |
    capability_unsupported |
    source_inconsistent
  summary
  missing_information[]
```

模型只能报告无法继续的原因，不能自行把 Run 标记为 `needs_input`、`failed` 或 `completed`。Runtime 根据确定性事实映射状态；模型声称 capability unsupported 也必须由 Capability Policy 验证。

### 6.4 互斥规则

- `action=need_context` 时必须有至少一个合法请求，且不得同时包含 Patch；
- `action=produce_patch` 时必须包含 Patch，且不得同时请求源码；
- `action=cannot_proceed` 时不得包含读取请求或 Patch；
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

### 7.2 list_source_files

用途是按受控目录或文件角色缩小文件树。它只返回 Manifest 已存在的规范化相对路径和元数据，不读取内容，不遍历宿主文件系统，也不显示被策略排除的文件。

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

Runtime 从同一 `base_git_commit` 读取指定受控文件：

- `path` 必须存在于 BaseSourceManifest；
- 未提供行范围时读取完整文件；
- 提供范围时只用于探索，并记录准确的起止行和内容 hash；
- 内容按不可信数据块标记，源码注释中的指令不能覆盖系统和项目规则；
- 完整读取的文件进入 `fully_read_files`；片段读取只进入 `read_ranges`；
- 文件内容变化、hash 不符或基线 commit 不存在时停止当前 Run。

### 7.5 SourceReadResult

```text
SourceReadResult
  request_id
  operation
  status: completed | denied | not_found | limit_exceeded
  files[]?
  matches[]?
  content_blocks[]?
  chars_added
  result_hash
  has_more
  error_code?
```

Runtime 返回结构化结果，不把命令输出原样拼接进 Prompt。相同 base commit、请求、Policy 和 Tool 版本必须得到相同结果 hash。

## 8. 动态扩展与预算

### 8.1 轮次定义

- Round 0 是 InitialSourceContext 后的第一次 Engineer 调用；
- V1 最多接受两次 `NeedContext`，即默认 `MAX_SOURCE_CONTEXT_ROUNDS=2`；
- 每次 `NeedContext` 可以包含多个读取请求，但请求数量、搜索匹配数、单次读取大小和结果总量均由 `ContextPolicySnapshot` 限制；
- 第二次扩展后，下一次 Engineer 调用必须返回 `ProducePatch` 或 `CannotProceed`；第三次 `NeedContext` 返回 `SOURCE_CONTEXT_ROUND_LIMIT`；
- 配置可以在部署前收紧，但不能在 Run 中途变化。Run 保存实际 Policy 快照和版本。

### 8.2 累计字符预算

现有 `MAX_SOURCE_CHARS` 改为“当前 Engineer 可见的去重源码工作集上限”，而不是单次静态装箱上限：

- 同一完整文件跨轮次重复出现只计一次；
- 不同片段按实际新增字符计入；
- 同一范围重复读取不增加工作集字符数，但仍记录重复请求；
- RepositoryMap、完整文档、Prompt 模板和输出预算不计入该字段，但 Provider Adapter 必须为它们预留模型 Context 空间；
- Runtime 不能因为剩余预算不足而缩短用户请求的行范围后继续，必须返回明确的 `limit_exceeded`；
- 如果安全生成 Patch 所需的完整目标文件无法放入预算，Engineer 必须 `CannotProceed`，Run 进入可见失败或等待用户缩小范围。

`MAX_SOURCE_CHARS` 仍是稳定、可测试的部署配置。V1 不要求为不同 Provider 动态计算 tokenizer；真实 input/output token 继续由 Provider Usage 记录。

### 8.3 为什么不用无限 Tool Loop

动态读取能纠正第一次选错文件，但会增加模型调用、延迟和恢复状态。V1 通过两轮上限取得可用性与可交付性的平衡：

- 简单修改通常在 Round 0 完成；
- 一次搜索和一次定向读取可以处理常见跨文件定位；
- 两轮仍不足说明任务范围、仓库地图或 Adapter 能力不够，继续循环只会增加成本并放大错误；
- 后续是否提高轮次必须由真实失败样本和评估证明，不能仅因模型请求继续而自动放宽。

## 9. SourceContextReceipt

最终 `SourceContextReceipt`（下文简称 ContextReceipt）证明 Engineer 实际看到了什么：

```text
SourceContextReceipt
  schema_version
  project_id
  run_id
  base_version_id
  base_git_commit
  source_manifest_hash
  repository_map_hash
  context_policy_version
  initial_context_hash
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

ContextReceipt 的作用不是声称“相关文件已经全部找到”，而是提供可检查事实：模型获得了哪些完整文件、哪些片段、做过哪些搜索、哪些请求被拒绝，以及生成 Patch 时的最终 Context hash。

约束：

- Receipt 由 Runtime 生成，模型不能提交或修改；
- `fully_read_files` 只包含基线 hash 已校验的完整文件；
- Receipt 绑定全部 Exchange，任何读取结果变化都会改变 `receipt_hash`；
- 用户可见事件只展示路径、动作、字符量和错误，不默认展示完整源码；
- SourcePatchSet 必须绑定最终 `receipt_hash`，不能复用其他 Run 或其他基线的 Receipt。

## 10. SourcePatchSet Contract

```text
SourcePatchSet
  schema_version
  project_id
  run_id
  base_version_id
  base_git_commit
  source_manifest_hash
  context_receipt_hash
  summary
  patches[]:
    path
    operation: modify | add | delete
    before_hash?
    unified_diff
```

### 10.1 Context 覆盖规则

- `modify`：目标文件必须存在于 `ContextReceipt.fully_read_files`，且 `before_hash` 与基线文件 hash 一致；
- `delete`：目标文件必须被完整读取，并提供 `before_hash`；
- `add`：目标路径不得已存在，不要求 before hash，但必须符合 Adapter、Capability Policy、目录和文件类型限制；
- rename 在 V1 中表示一条 delete 和一条 add，不增加独立操作类型；
- 只读过局部行范围的文件不得修改或删除；未来若要支持局部覆盖证明，需要单独设计 hunk 与 read range 的包含关系；
- Patch 不能修改 Manifest 标记为 protected 的文件；
- Patch 数组之外的文件在 apply 后必须保持 byte-level 相同。

### 10.2 Patch 不是最终证据

模型提供的 unified diff 只是候选指令。Runtime 不接受模型自报的 changed files、line stats、测试通过或兼容性结论。最终 SourceDiff、SourceBundle、ExecutionReport 和 ValidationReport 都必须从 apply 后真实候选工作区生成。

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
  complete ProductSpec
  complete ArchitectureDesign
  ChangeBrief / RequirementDelta
  preserve / acceptance criteria
  Capability Policy
  BaseSourceManifest
  RepositoryMap
  cumulative SourceContextReceipt draft
  actual source blocks in current working set
  previous deterministic Patch/apply error?
  ContextPolicySnapshot
```

Provider 不依赖隐藏会话记忆决定已经读过什么。每次调用都从持久化 Artifact、Context Exchange 和基线 commit 重建同一输入；`input_context_hash` 相同意味着 Provider 收到的业务输入相同。

Mock、Ollama/DeepSeek 和未来 Provider Adapter 必须共享同一 Pydantic Contract。Provider fallback 只能重试相同 Engineer Context，不能在 fallback 时改变文件范围、基线或 Policy。

## 12. Orchestrator 状态机

```text
EngineerContextPreparing
  -> EngineerRunning(round=0)
       |-- NeedContext
       |      -> SourceContextReading(round=1)
       |      -> EngineerRunning(round=1)
       |             |-- NeedContext
       |             |      -> SourceContextReading(round=2)
       |             |      -> EngineerRunning(round=2)
       |             |             |-- ProducePatch
       |             |             `-- CannotProceed / RoundLimit
       |             |-- ProducePatch
       |             `-- CannotProceed
       |-- ProducePatch
       `-- CannotProceed
  -> PatchChecking
  -> CandidateApplying
  -> SourceDiffCalculating
  -> RuntimeBuildTestValidation
  -> VersionMaterializing
  -> Completed
```

规则：

- Project 写占用在用户批准并创建 Run 时取得，动态读取期间继续持有；
- 每个模型动作先 Schema 校验并持久化，再执行对应 Runtime 分支；
- 每批 Runtime 读取完成并持久化后，才进入下一次 Provider 调用；
- `NeedContext` 不创建子 Run，也不重新执行产品或架构阶段；
- Stop/Cancel 在任何等待 Provider、读取和 apply 阶段都能终止后续动作，但不删除已持久化证据；
- Runtime 只接受当前 `run_id / round / input_context_hash` 对应的动作，迟到结果不能覆盖新状态。

Patch 格式或 hunk 定位失败时可以沿用既有“一次受控修正”原则：Runtime 把确定性 apply 错误和原 Patch 作为只读证据交给 Engineer 修正一次。该修正不增加源码读取轮次，不允许改为全量重生成；如果修正需要新的源码且读取轮次已耗尽，则失败。

## 13. 持久化、幂等与恢复

### 13.1 Context Exchange

当前 Artifact 表对 `(run_id, artifact_type)` 唯一，不适合直接保存多轮同类型动作。V1 新增顺序化持久化对象 `EngineerContextExchange`：

```text
EngineerContextExchange
  id
  run_id
  sequence
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

最终仍保存唯一的 `source_context_receipt` 和 `source_patch_set` Artifact。Exchange 保存过程证据，Artifact 保存阶段最终结果，两者不能互相替代。

### 13.2 事务边界

- Provider 返回的 EngineerAction、Schema 校验结果和对应 Usage settlement 在同一数据库事务提交；
- Runtime 读取结果、结果 hash、累计字符量和 Exchange 完成状态在同一事务提交；
- `SourcePatchSet` 与最终 ContextReceipt 在同一事务冻结，Patch 不得指向仍会变化的 Receipt draft；
- 外部 Provider 调用无法做到数据库意义上的 exactly-once。系统保证已持久化的有效动作不会因 Worker 重领而再次调用；进程在外部请求完成但本地提交前崩溃时，可能发生一次重复请求，必须通过 trace、attempt 和 Usage 记录可见，不能宣称绝对不重复计费。

### 13.3 Worker 恢复

恢复时按以下顺序判断：

1. 重新校验 Run 的 base version、base commit 和 Project 写占用；
2. 读取已完成 Exchange，按 sequence 重建 ContextReceipt draft；
3. 已记录 `NeedContext` 但读取未完成时，从相同 base commit 确定性重做 Runtime 读取并校验 result hash；
4. 已完成读取但没有下一动作时，从下一 Provider 调用继续；
5. 已冻结 SourcePatchSet 时不再调用 Engineer，直接进入 PatchChecking；
6. 已存在候选 hash、SourceDiff 或执行结果时按对应阶段 Artifact 恢复，不重复 apply、执行或创建版本。

任一已持久化 hash 无法从基线重建时进入 `SOURCE_CONTEXT_RECOVERY_MISMATCH`，不能忽略差异继续。

## 14. 隔离候选工作区与 apply

### 14.1 候选工作区

Repository Service 从 `base_git_commit` 创建当前 Run 专属临时候选 worktree。浏览器、模型和 Runtime Executor 都不获得宿主机 Project Git 路径。

```text
Project bare/local Git
      |
      `-- base_git_commit
              |
              `-- candidate worktree / run_id
```

候选 worktree 与当前 Project ref、已发布版本和其他 Run 分离。失败、取消或冲突只回收候选目录，不移动当前版本。

### 14.2 apply 顺序

1. 校验 SourcePatchSet Schema 和所有基线/Receipt hash；
2. 规范化路径并拒绝绝对路径、`..`、符号链接、submodule、文件模式和二进制 Patch；
3. 校验 modify/delete 文件已被完整读取且 before hash 匹配；
4. 校验 add/delete/modify 是否在 Approval、Adapter 和 Capability Policy 范围内；
5. 在候选 worktree 执行 `git apply --check` 或等价确定性检查；
6. apply 后重新枚举完整受控源码，确认 Patch 外文件 byte-level 未变；
7. 生成候选 SourceBundle、candidate manifest hash 和 Runtime SourceDiff；
8. 如实际 Diff 扩大批准范围，进入 pre-commit Approval，不执行版本物化；
9. 把候选 SourceBundle 交给 Runtime Executor 构建、测试和校验；
10. 全部门禁通过后进入 VersionMaterialization。

候选 apply 不在共享 Runtime Executor 中直接修改 Project Git。主服务 Repository Service 负责 Git 候选事实；Runtime Executor 只接收候选 SourceBundle，在自己的临时目录执行固定 Adapter。

## 15. SourceDiff、验证与版本

Runtime SourceDiff 必须比较完整基线与完整候选：

```text
SourceDiff
  base_version_id
  base_git_commit
  base_source_manifest_hash
  candidate_source_manifest_hash
  changed_files[]
  added_files[]
  removed_files[]
  per_file_before_hash / after_hash
  unified_diff
  line_stats
```

验证边界：

- SourceDiff 由 Runtime 生成，模型不能修改；
- Runtime Executor 固定执行 Adapter 登记的构建、Engineer 交付的单元测试和 Validator；
- 只有 `ExecutionReport.status=passed` 且 `ValidationReport.passed=true` 才能创建 ProjectVersion；
- Patch 成功但构建、测试或校验失败时保留 ContextReceipt、Patch、SourceDiff 和报告，不创建版本；
- AI 修改成功不自动 Publish，Public Route 继续指向用户明确发布的版本；
- 最终版本 CAS 仍校验 latest version、active write run、base commit 和 candidate hash。

## 16. Human-in-the-loop 与风险

- 动态源码读取发生在用户点击“修改代码”并创建 `ai_edit` Run 之后；pending proposal 不启动 Engineer 读取循环；
- pre-execution Approval 绑定完整 `source_manifest_hash`，而不是绑定某个局部 Context，避免读取范围变化掩盖基线变化；
- SourceReadRequest 只是读取需求，不构成修改授权；
- Context 扩展到同一已批准 Project 的其他受控源码，不自动触发新的 Approval；
- Patch 实际增加页面、删除文件、替换入口、大面积重写或扩大批准范围时，由 Runtime SourceDiff 触发 pre-commit Approval；
- Secret、其他用户文件、宿主路径和被策略排除的文件属于 deny，不能通过用户 Approval 绕过；
- Approval 等待期间基线变化后 subject stale，已有 ContextReceipt 和 Patch 不能应用到新版本。

## 17. 安全边界

- 所有 Manifest、Map、读取请求、Exchange、Receipt、Patch、Diff 和版本查询都按 Session 用户与 Project owner 联查；
- Runtime 只从绑定的 base commit 读取，客户端和模型不能提交文件内容作为源码事实；
- SourceReadRequest 只能访问 Manifest 中的受控文本文件；
- 路径必须使用规范化 POSIX 相对路径，拒绝绝对路径、`..`、NUL、符号链接逃逸和隐藏控制目录；
- 源码、注释、测试、文档和搜索结果作为不可信数据块输入，不能覆盖系统、项目规则或 Tool Schema；
- Engineer 没有 Shell、Git、数据库、网络、Runtime Executor、Publish 和 Repository 写 Tool；
- 日志默认只记录路径、hash、字符量、动作和错误，不记录完整源码、Provider Key、Session token 或模型私有推理；
- Context 动态扩展不能跨 Project、跨用户、跨 base commit 或跨 Adapter；
- 任何 Tool、索引或 Provider 失败都不能降级为“假设文件无关后继续”。

## 18. 配额、延迟与成本

动态扩展的主要代价是额外 Provider 请求，不是 Runtime 读文件本身。V1 采用以下控制：

- 小仓库全量源码未超过预算时仍允许一次 Engineer 调用完成；
- 每次 Engineer inference 单独 reserve、settle、release，不预先把最大三次调用全部记为 used；
- `NeedContext` 的实际 input/output token 计入 Engineer 阶段；
- Runtime list/search/read 不消耗模型配额，但记录执行次数、字符量和耗时；
- Provider fallback 和 Schema retry 继续按实际请求结算；
- 超过 Context 轮次、字符预算或本轮配额时停止，不自动购买额外预算；
- UI 显示“正在定位源码 / 正在读取 N 个文件 / 正在生成 Patch”，不承诺缺少数据依据的预计完成时间。

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
source.patch_created
source.patch_check_started
source.patch_check_failed
source.patch_applied
source.diff_created
```

每次 Exchange 至少记录：

```text
run_id / project_id / base_version_id / base_git_commit
sequence / round_index / action_type
input_context_hash / action_hash / read_result_hash
source_manifest_hash / repository_map_hash / receipt_hash?
request_count / input_tokens / output_tokens
used_source_chars / fully_read_file_count
error_code / trace_id
```

用户界面展示读取阶段、文件数量、Patch 摘要、真实 Diff、验证结果和失败出口。管理员或下载日志可以看到 Artifact/Exchange 引用和 hash，但不默认输出完整源码或 Chain of Thought。

## 20. 错误处理矩阵

| 错误 | Runtime 行为 | 对 Project 的影响 |
| --- | --- | --- |
| `BASE_SOURCE_MISMATCH` | 基线 Git、ProjectVersion 或 SourceBundle 不一致，停止 | 当前版本不变 |
| `SOURCE_CONTEXT_REQUEST_INVALID` | EngineerAction 或请求字段无效，有限 Schema retry | 不读取文件，不创建 Patch |
| `SOURCE_CONTEXT_PATH_DENIED` | 请求不在 Manifest、路径越界或文件受保护 | 记录 denied；由 Engineer 在剩余轮次内调整，否则失败 |
| `SOURCE_CONTEXT_NOT_FOUND` | 基线 commit 中不存在请求文件 | 记录确定性结果，不从 worktree 猜测 |
| `SOURCE_CONTEXT_LIMIT` | 请求会超过字符或 Tool 结果上限 | 不截断冒充成功；返回 limit_exceeded |
| `SOURCE_CONTEXT_ROUND_LIMIT` | 第二轮后仍返回 NeedContext | Run 失败或 needs input，不继续调用 |
| `SOURCE_CONTEXT_RECOVERY_MISMATCH` | 恢复重算结果与持久化 hash 不一致 | 停止恢复，当前版本不变 |
| `PATCH_CONTEXT_VIOLATION` | modify/delete 文件未完整读取或 Receipt 不匹配 | 拒绝 Patch，不进入 apply |
| `PATCH_PATH_DENIED` | Patch 路径、类型或 protected 状态越权 | 拒绝 Patch |
| `PATCH_BASE_MISMATCH` | base commit、Manifest 或 before hash 不匹配 | 拒绝 Patch，旧 Approval stale |
| `PATCH_APPLY_FAILED` | apply --check 或 apply 失败 | 保留 Patch 与错误；最多一次受控修正 |
| `EMPTY_CHANGE` | apply 后没有真实源码变化 | 不创建版本 |
| `BASE_VERSION_CONFLICT` | 最终 CAS 时当前版本已变化 | 候选不接入当前版本 |
| `EXECUTION_FAILED` | 构建或单元测试失败 | 保留候选证据，不创建版本 |
| `VALIDATION_BLOCKED` | 强制 Validator 失败 | 不允许模型或用户普通 Approval 覆盖 |

## 21. 测试与验收

### 21.1 Contract 单元测试

- EngineerAction 三种分支互斥，缺失或混合字段拒绝；
- SourceReadRequest 的 operation 与参数组合严格校验；
- BaseSourceManifest 和 RepositoryMap 对相同 commit 生成稳定 hash；
- ContextReceipt 对相同 Exchange 顺序生成稳定 receipt hash；
- modify/delete 只允许 fully_read_files，局部 read range 不足以授权修改；
- SourcePatchSet 必须绑定当前 base、Manifest 和 Receipt；
- Policy 快照在 Run 内不可变化。

### 21.2 Context 选择与 Tool 测试

- 小仓库未超过预算时 Round 0 包含全部受控源码；
- 大仓库初始只包含用户选择、准确路径、错误文件和固定入口，不按路径填满无关文件；
- list 只返回 Manifest 文件；
- search 使用字面量并正确返回 `has_more`；
- read full/range 的行号、字符量和 hash 正确；
- 重复读取不重复计算工作集字符；
- 路径穿越、Secret、二进制、受保护文件和其他用户 Project 被拒绝；
- 单个完整目标文件超过剩余预算时明确失败，不静默截断。

### 21.3 动态循环集成测试

- Engineer Round 0 直接 ProducePatch，只调用一次 Provider；
- Round 0 NeedContext 后 Runtime 读取，Round 1 ProducePatch；
- 连续两次 NeedContext 后 Round 2 ProducePatch；
- 第三次 NeedContext 返回 round limit，不创建 Patch 或版本；
- denied/not_found/limit_exceeded 结果真实进入下一轮 Context；
- Provider fallback 接收相同 input_context_hash；
- Worker 分别在 action 持久化前后、读取前后、Receipt 冻结前后重启，已经完成的轮次不重复；
- 双用户不能通过 list/search/read 获得对方路径、内容或 hash。

### 21.4 Patch 与候选测试

- Patch 修改未完整读取文件时返回 `PATCH_CONTEXT_VIOLATION`；
- before hash、base commit、Manifest 或 Receipt 不匹配时拒绝 apply；
- add/modify/delete、空 Patch、越权路径、二进制和 symlink Patch 均覆盖；
- apply 后 Patch 外文件 byte-level 相同；
- Runtime SourceDiff 与候选工作区真实差异一致；
- 实际 Diff 扩大批准范围时暂停在 pre-commit Approval；
- Build、Unit Test 或 Validator 失败不创建 ProjectVersion；
- 最终版本 CAS 冲突不覆盖新版本；
- 成功创建 `ai_edit` 版本但不移动已发布指针。

### 21.5 Railway 部署验收

- 真实 Provider 能完成“一次读取扩展后生成 Patch”的已有 Project 修改；
- Railway 单副本重启后能从 Context Exchange 恢复，不重复已持久化动作；
- 持久化 Volume 保留 Project Git、Exchange、Receipt、Patch 和版本映射；
- 主服务隔离 worktree 与 Runtime Executor 临时源码均在成功、失败、取消和超时后按设计清理；
- 浏览器刷新后仍能看到读取阶段、Patch、真实 Diff、验证结果和失败原因。

## 22. 从当前静态 SourceContext 迁移

迁移不能同时改完所有路径后一次切换。推荐顺序：

1. **[Contract]** 增加 BaseSourceManifest、RepositoryMap、EngineerAction、SourceReadRequest/Result、SourceContextReceipt 和 SourcePatchSet；保留现有 SourceContext 只读兼容。
2. **[持久化]** 增加 EngineerContextExchange 和最终 Receipt/Patch Artifact，建立 sequence 唯一性与恢复测试。
3. **[初始 Context]** 把 `build_source_context()` 改造成 InitialSourceContext builder：小仓库全量，大仓库不再按路径填充无关文件。
4. **[Provider]** 增加 `create_engineer_action()`，先接 Mock，再接 Ollama/DeepSeek；旧 `revise_app_spec()` 暂时保留用于对照。
5. **[动态循环]** Orchestrator 接入最多两轮 NeedContext、Tool Policy、累计 Receipt、逐次配额和取消恢复。
6. **[Patch]** 接入 SourcePatchSet 校验、Context 覆盖检查、候选 worktree、apply --check/apply 和 Runtime SourceDiff。
7. **[执行门禁]** 从候选工作区生成 SourceBundle，接现有 Runtime Executor Build/Test/Validation。
8. **[风险与版本]** 接 pre-commit Approval、最终 CAS 和 VersionMaterialization。
9. **[切换]** 真实 Provider 和 Railway 验收通过后，将动态模式设为默认，删除生产路径对完整候选 AppSpec 的依赖；历史 Artifact 继续可读。

部署迁移期间可以使用临时 feature flag 比较静态和动态路径，但 flag 不是长期产品模式。两条路径不得对同一 Run 同时写候选版本，也不得用静态结果作为动态路径失败时的隐式降级。

## 23. 实施完成条件

本文只有同时满足以下条件才可以移除文件名中的 `[TODO]`：

- EngineerAction、动态读取、ContextReceipt 和 SourcePatchSet Contract 已在 API、Provider、Orchestrator 和持久化层统一实现；
- SourcePatchSet 已在隔离候选工作区 apply，Runtime 能针对完整候选重算 SourceDiff；
- Context、Patch、Build、Unit Test、Validator、版本 CAS 和发布边界的自动化测试通过；
- Worker 在动态读取各检查点重启后能恢复，且不重复已持久化阶段；
- Railway 真实 Provider 完成至少一轮需要额外读取的修改并保留可检查证据；
- 现有设计、README 和实现不再把静态 `MAX_SOURCE_CHARS` 装箱描述为最终方案；
- 已知能力边界明确：没有匹配 RepositoryMap/Source Adapter 的项目不能声称支持可靠动态修改。

## 24. V2 与未来扩展

在不改变 BaseSourceManifest、ContextReceipt、SourcePatchSet、Runtime apply 和真实 SourceDiff 不变量的前提下，未来可以增加：

- AST、Tree-sitter 或 Language Server 生成的符号与引用索引；
- import、调用、测试和配置依赖图；
- 语义检索作为新的只读 SourceRead operation；
- 大文件局部读取与 Patch hunk 覆盖证明；
- 多轮候选 Patch，每轮绑定同一 candidate hash；
- Explore 子代理把搜索摘要返回主 Engineer；
- 不同项目类型的 Source、Build、Test 和 Runtime Adapter。

这些能力必须由实际仓库规模和失败样本驱动。向量索引只能改善召回，不能替代基线 hash、读取 Receipt、Patch 权限、隔离 apply、完整 Diff 和运行验证。

## 25. 参考依据

- [OpenAI：Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)：模型通过结构化 Tool Call 请求动作，Agent 执行并把结果加入后续推理输入。
- [GitHub Copilot：Repository indexing](https://docs.github.com/en/copilot/concepts/context/repository-indexing)：语义代码索引可以改善仓库级检索，但属于具体产品能力，不是本文 V1 的必要前提。
- [Aider：Repository map](https://aider.chat/docs/repomap.html)：低分辨率仓库地图可以提供文件和关键符号结构，并在需要时引导读取具体文件。

本文只吸收“多分辨率 Context、按需读取和 Agent loop”的可验证机制，不把任何外部产品的内部索引、分片或模型策略当作 Another Atom 已实现事实。
