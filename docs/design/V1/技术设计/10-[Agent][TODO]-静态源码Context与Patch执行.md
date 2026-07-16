# Another Atom V1 静态源码 Context 与受控文件变更执行

[toc]

- **文档状态：** V1 本地实现基线；`SourceFileChangeSet`、隔离文件物化、Runtime 本地 Diff、静态 Context 下有界 Repair 与自动化测试已完成，真实 Provider、Worker 修复检查点恢复与 Railway 验收仍待完成
- **功能范围：** 已有 Project 修改时的一次性源码 Context、受控文件变更、隔离候选、真实 Diff、最多两次验证修复与现有执行门禁
- **上位设计：** [基于现有代码的对话式 AI Coding](./02-[Agent]-基于现有代码的对话式AI-Coding.md)
- **后续终态：** [受控动态源码 Context 与 Patch 执行](./09-[Agent][TODO]-受控动态源码Context与Patch执行.md)
- **检查来源：** [29｜模型生成 Unified Diff 可靠性检查](../../../review/待办/29-[工程]-2026-07-15-模型生成UnifiedDiff可靠性检查.md)

## 背景

V1 第一阶段曾把 Engineer 从完整 `AppSpec` 重生成迁移为模型输出 `SourcePatchSet`，Runtime 再执行 `git apply --check` 和隔离 apply。该路径已经具备基线、Context、路径和 `before_hash` 约束，但仍要求模型精确生成 unified diff 的 hunk 行数、起始位置和上下文。

Run `1c36c375-f800-4ef8-8b2d-d4392ed68f9b` 证明这个接口不够可靠：模型正确完成了“毛玻璃翻译”到“我要翻译”的内容修改，却因 hunk 把实际 `6→6` 写成 `7→7` 而在构建前失败。该错误与业务语义无关，继续在 raw diff 上叠加 Prompt、重试或自动修复会扩大接口和恢复状态。

本文将 V1 seam 调整为 `SourceFileChangeSet`。Engineer 只声明受控文件应变成什么；Runtime 负责候选物化、本地 Diff、执行门禁和版本写回。模型不再生成 raw unified diff。

## 摘要

- **Engineer Interface**
  - Engineer 返回绑定固定基线和静态 Context 的 `SourceFileChangeSet`；modify/add 携带本轮变更文件的完整最终内容，delete 只声明删除。
- **Runtime Implementation**
  - Runtime 校验路径、Context、`before_hash`、大小和能力策略，在隔离候选目录确定性写入或删除文件；不再执行模型提供的 `git apply`。
- **范围边界**
  - 模型只返回 `changes[]` 中的文件，不返回整个代码库；未声明文件必须保持 byte-level 相同。超限时明确失败，不回退 raw diff 或完整 `AppSpec`。
- **最终证据**
  - `SourceDiff` 仍由 Runtime 从输入 revision 和真实候选文件本地计算。模型不提供 hunk、line stats 或最终 Diff。
- **有界修复**
  - 初始 ChangeSet 的 Build、Unit Test 或 Validator 出现 Runtime 判定为可修复的代码失败时，系统最多再请求两次 Repair ChangeSet；每次都从当前失败候选继续，并重新执行完整 Build/Test/Validation。
- **阶段边界**
  - 本文仍使用静态 Context；尚未实现 `NeedContext`、`ContextReceipt`、RepositoryMap 和按需读取。当前 Repair 是动态终态的受限子集，不等于完整 CandidateRevision/Context 协议已落地。

## 1. 技术结论

修改链路调整为：

```text
BaseSourceSnapshot
  -> build_source_context()
  -> create_source_file_change_set(...) -> SourceFileChangeSet
  -> Runtime binding / path / hash / content preflight
  -> isolated candidate file materialization
  -> rebuild compatible AppSpec + SourceBundle
  -> Runtime calculate SourceDiff from real files
  -> Build / Unit Test / Validation
  -> resolvable failure? -> bounded RepairContext -> Repair ChangeSet -> full revalidation
  -> version CAS + Git commit
```

以下事实保持不变：

- 源码从批准时绑定的 `base_git_commit` 读取；
- Agent 没有 Git、Shell 或 Repository 写权限；
- 只有完整进入 Context 的现有文件可以 modify/delete；
- Runtime 管理文件和受保护路径不能修改；
- 最终 Diff、Build、测试和校验报告必须来自真实候选；
- 失败、取消或冲突不创建版本，不移动 latest/published 指针。

替换的只有 Engineer 与 Runtime 之间的源码变更 Interface：从模型编码 raw diff，改为模型返回受控文件最终内容。

## 2. 范围与明确不做

### 2.1 本期范围

- 复用 `BaseSourceSnapshot`、确定性 `SourceContext` 和现有 Context hash；
- 新增 `SourceFileChangeSet`、`SourceFileChange` 和 AppSpec 元数据 Delta Contract；
- 校验 Project、Run、版本、commit、Manifest、Context 和 `before_hash`；
- 在隔离目录执行 add/modify/delete 的确定性文件物化；
- 从候选真实文件重建兼容 `AppSpec`、`app-spec.json` 和 `SourceBundle`；
- 本地计算 `SourceDiff`，接入现有 Build、Unit Test、Validator、版本 CAS 和 Git commit；
- 保存 ChangeSet、候选物化报告、真实 Diff 和稳定失败事件；
- 历史 `source_patch_set` Artifact 只读兼容。

### 2.2 明确不做

- 不要求模型生成或修复 unified diff；
- 不在 Runtime 中重算模型 hunk、纠正行号或猜测 Patch 意图；
- 不让模型返回整个代码库，只返回声明修改的文件；
- 不静默截断大文件，不自动切回 raw diff；
- 不回退到完整 `AppSpec` 重生成；
- 本阶段不实现 `NeedContext`、RepositoryMap、CandidateRevision、ChangeAttempt 链或验证反馈修正；
- 不扩展到 `web-static-v1` 以外的通用 Source Adapter。

## 3. 静态 Context 与修改权限

`build_source_context()` 继续按用户选择、消息准确路径、规范化路径的确定性顺序装箱。每个文件要么完整加入，要么完全省略，不允许把局部片段当作完整写权限。

规则：

- `modify`：目标必须存在于输入 Snapshot，也必须完整存在于 `included_files`；
- `delete`：规则同 modify，且必要入口文件不可删除；
- `add`：目标在输入 Snapshot 中不存在，路径、后缀、数量和大小符合 Source Adapter 与 Capability Policy；
- 省略文件不能修改；需要该文件时返回 `CONTEXT_INSUFFICIENT`；
- `app-spec.json`、`.git/**`、`.another-atom/**`、绝对路径、反斜线和含 `.` / `..` 的路径始终禁止；
- `index.html`、`styles.css`、`app.js` 不能删除；候选必须保留至少一个 `tests/*.test.js`；
- 未在 `changes[]` 中声明的文件相对输入 Snapshot 必须 byte-level 相同。

## 4. SourceFileChangeSet Contract

```text
SourceFileChangeSet
  schema_version: 1.0
  project_id
  run_id
  base_version_id
  base_git_commit
  source_manifest_hash
  source_context_hash
  summary
  app_spec_delta
    project_name?
    tagline?
    hero_title?
    hero_body?
    pages?
    products?
  changes[]
    path
    operation: modify | add | delete
    before_hash?
    replacement_content?
```

字段约束：

- `modify`：必须提供当前输入文件的 SHA-256 `before_hash` 和完整 `replacement_content`；
- `add`：必须提供完整 `replacement_content`，不得提供 `before_hash`；
- `delete`：必须提供 `before_hash`，不得提供 `replacement_content`；
- 同一路径在一个 ChangeSet 中只能出现一次；
- `replacement_content` 是 UTF-8 文本，不包含 Base64、Patch header 或 Markdown fence；
- 模型不提供 `after_hash`。Runtime 从候选内容计算；
- 文件数、单文件字符数和序列化 ChangeSet 大小使用配置上限；超过上限返回明确错误；
- `source_context_hash` 绑定模型实际获得的完整静态 Context，不能复用其他 Run 或基线。

该 Interface 的含义是“这些受控文件的下一状态”，不是“请 Runtime 猜测如何应用一段文本补丁”。

## 5. AppSpec 与真实源码的一致性

现有 `web-static-v1` 同时保存真实源码和兼容 `app-spec.json`。ChangeSet 只修改真实 HTML、CSS、JavaScript 与测试文件；模型不得修改 `app-spec.json`。

Runtime 在候选物化后：

1. 从候选 `index.html` 识别唯一 `<body>` 和本地 `app.js` 入口，只提取应用正文；模型输出中的 doctype、`head`、`body` 边界格式和入口脚本格式不直接进入候选；
2. 从 `styles.css` 读取 CSS；
3. 从 `app.js` 去除 Runtime 注入且不可修改的网络 Guard；
4. 将上述代码字段与 `app_spec_delta` 合并到基线 `AppSpec`；
5. 视觉 Token 继续以修订后的 `ArchitectureSpec` 为准；
6. 调用 `render_version_files()` 重新生成 Runtime 管理的规范 `index.html` 外壳；`styles.css`、`app.js` 和提取后的应用正文仍必须与重建后的 `AppSpec` 一致；
7. 生成新的 `app-spec.json`，再形成候选 `SourceBundle`。

这一规则不允许 Engineer 修改文档外壳，也不要求模型逐字复刻换行、缩进、doctype 大小写和脚本标签格式。Runtime 只规范化自己拥有的外壳，不猜测或改写应用正文。无法识别唯一正文边界、本地 `app.js` 入口，或正文与 `AppSpec` 不一致时返回 `CANDIDATE_CONTRACT_INVALID`。

## 6. Provider Interface

当前生产路径使用：

```text
create_source_file_change_set(
  run_id,
  BaseSourceSnapshot,
  SourceContext,
  ProductSpec,
  Blueprint,
  ArchitectureDesign,
  ArchitectureSpec,
  ChangeBrief,
  RequirementDelta,
  base AppSpec
) -> SourceFileChangeSet
```

Provider Prompt 必须明确：

- 只修改 `included_files` 中完整提供的现有文件；
- modify/add 返回该文件完整最终内容，不返回 diff；
- delete 只声明路径与 `before_hash`；
- 保留未受需求影响的源码、交互和测试；
- 不复制未修改文件，不猜测 omitted files；
- `app_spec_delta` 只包含确实变化且不能从源码稳定推导的元数据；
- 超过输出能力时返回结构化 `CannotProceed` 或稳定错误，不截断内容。

结构化输出失败可以使用现有有限 Provider retry。合法 ChangeSet 在本地 Build、Unit Test 或 Validator 失败时，Runtime 只对 `resolvable=true` 且根因属于受控源码、AppSpec 或 Renderer 的失败构建有界 `SourceRepairContext`。`EXECUTION_BLOCKED`、安全策略、平台错误、能力缺口和不可解决失败保持终态，不通过重复调用 Engineer 掩盖。

## 7. Runtime 候选物化

Runtime 按以下顺序执行：

1. 校验 ChangeSet 的 Project、Run、base version、base commit、Manifest 和 Context hash；
2. 校验变更数量、唯一路径、规范化相对路径、文件类型、受保护路径和 Capability Policy；
3. 校验 modify/delete 已完整进入 Context，且 `before_hash` 与输入 Snapshot 一致；
4. 校验 operation 与 `replacement_content` 的存在规则、UTF-8 表达和大小上限；
5. 从输入 Snapshot 在干净临时目录物化全部受控文件；
6. modify 使用 `replacement_content` 覆盖目标，add 创建目标，delete 删除目标；
7. 拒绝符号链接、非普通文件、必要入口缺失和越权文件；
8. 重新枚举候选，证明 ChangeSet 外文件 byte-level 未变化；
9. 按第 5 节提取应用正文、重建 `AppSpec`，并由 Runtime 生成规范 `index.html` 外壳、`app-spec.json` 和 `SourceBundle`；
10. 从输入与候选真实文件确定性计算 `SourceDiff`；
11. 将候选交给 Runtime Executor 执行 Build、Unit Test 和 Validator；
12. 全部门禁通过并完成最终 CAS 后，才创建 ProjectVersion 和 Git commit。

Repository Service 是深 Module：调用方只提交 `SourceFileChangeSet` 并接收候选结果或稳定错误；临时目录、写入顺序、候选清单、hash、Diff 与清理属于其 Implementation，不扩散到 Orchestrator 或 Provider。

## 8. Artifact、事件与恢复

新 Run 使用：

- `source_file_change_set`：模型返回并通过结构化 Contract 的受控文件变更；
- `source_change_apply_report`：Runtime 校验、候选物化结果、实际文件清单和 candidate hash；
- `source_change_attempt_ledger`：按顺序保存初始变更和最多两次修复尝试，包括 ChangeSet hash、当前候选 hash、失败代码、验证与执行证据；
- `app_spec`、`source_bundle`、`source_diff`：均由候选真实文件生成。

目标事件：

- `source.change_created`；
- `source.change_check_started`；
- `source.change_applied`；
- `source.diff_created`；
- `source.change_failed`。
- `source.repair_started`；
- `source.repair_change_created`；
- `source.repair_applied`；
- `source.repair_validation_completed`；
- `source.repair_failed`。

历史 `source.patch_*` 事件和 `source_patch_set` Artifact 保持只读展示，不转换成新 ChangeSet，也不在恢复时混用。迁移切换后，一个 Run 只能走一种源码变更路径。

Worker 恢复时：

1. 已保存 ChangeSet 但没有 apply report：从固定输入 Snapshot 重新确定性物化候选；
2. 已有 apply report、AppSpec、SourceBundle 与 SourceDiff：校验 hash 后从下一门禁继续；
3. 任一候选 hash 不一致：返回恢复错误，不重新调用 Engineer，不读取残留 worktree 猜测；
4. 已创建版本：复用现有 ProjectVersion/Git 映射，不重复 commit。

修复路径会先持久化 `source_change_attempt_ledger` 再进入下一次 Provider 调用。如果已经存在与 attempt、candidate hash、failure code 和 `repair_context_hash` 一致的 Repair ChangeSet，Worker 恢复时复用它并重跑确定性门禁，不再次请求模型。当前自动化尚未覆盖该修复检查点的真实进程重启，因此不把它记为已完成部署验收。

## 9. 错误语义

- `CONTEXT_INSUFFICIENT`：modify/delete 目标未完整进入静态 Context；
- `SOURCE_CHANGE_BASE_MISMATCH`：Project、Run、版本、commit、Manifest 或 Context hash 不一致；
- `SOURCE_CHANGE_PATH_FORBIDDEN`：路径、类型、Runtime 保留文件或操作越权；
- `SOURCE_CHANGE_HASH_MISMATCH`：`before_hash` 与固定输入文件不一致；
- `SOURCE_CHANGE_CONTENT_INVALID`：operation 与 content 不匹配或内容不能进入受控文本 Contract；
- `SOURCE_CHANGE_OUTPUT_TOO_LARGE`：文件数、单文件内容或序列化 ChangeSet 超过配置上限；
- `CANDIDATE_CONTRACT_INVALID`：候选入口、Runtime shell/Guard、AppSpec 或 SourceBundle 无法一致重建；
- `EMPTY_CHANGE`：候选与输入 Snapshot 没有真实变化；
- `EXECUTION_FAILED` / `VALIDATION_BLOCKED`：构建、测试或 Validator 未通过。

迁移后的新 Run 不再产生 `PATCH_CHECK_FAILED` 或 `PATCH_APPLY_FAILED`；这两个错误只用于历史 raw Patch Run。所有失败都释放 Project 写占用，不创建版本，不移动发布指针。

## 10. SourceDiff 与验证

模型不返回 Diff。Runtime 比较输入 Snapshot 与候选文件，生成：

```text
SourceDiff
  base_version_id
  candidate_hash
  changed_files[]
  added_files[]
  removed_files[]
  per_file_before_hash / after_hash
  unified_diff
  line_additions / line_deletions
```

`unified_diff` 只存在于 Runtime Evidence，不进入 Engineer 输出。用户审批、风险判断、版本详情和发布前检查均读取该真实 Diff。

候选依次执行固定 Adapter 的 Build、Unit Test 和 Validator。可修复代码失败进入静态 Context 下的有界修复：第一次失败候选被冻结为 repair input revision，Runtime 只传递去除临时宿主路径的结构化诊断、当前候选中已变更文件的完整内容和剩余次数。Repair ChangeSet 必须绑定当前 candidate manifest、attempt index、source revision、`repair_context_hash` 和 failure code。每次成功物化后均从 Build 起完整复验，不只重跑上次失败项。

最多两次 Repair 均未通过时，Run 以最后一次确定性错误结束；候选不创建 ProjectVersion，Project 当前版本和发布指针不变。任意修复尝试成功时，累计 SourceDiff 仍相对最初批准基线计算，整个 Run 只创建一个版本和 Git commit。

## 11. 配额、并发和安全

- Provider 调用继续按阶段预占、结算和释放；Runtime 候选物化与 Diff 不计模型请求；
- 单个 Project 同时只有一个代码修改 Run 持有写占用；
- 最终写回前重新检查 current version 仍等于批准基线；
- replacement content 始终按数据处理，不解释为 Shell、Git 命令或模板指令；
- Source Adapter 决定允许路径、文件类型、必要入口和 Runtime 管理文件；
- 失败候选只存在于隔离临时目录和持久化 Artifact，不写共享 Project worktree。

## 12. 迁移计划

1. **已完成：** 新增 `SourceFileChangeSet / SourceFileChange / SourceChangeApplyReport` Contract 和单元测试；
2. **已完成：** Mock、Ollama、DeepSeek Provider 改为 `create_source_file_change_set()`；
3. **已完成：** Repository Service 增加确定性文件物化 Module，以接口级测试覆盖 add/modify/delete、hash、权限、超限和未声明文件不变；
4. **已完成：** Orchestrator 切换 Artifact、事件、恢复检查点和错误语义；
5. **已完成：** 新 Run 不再依赖 `create_source_patch_set()`、hunk/header 校验和 `git apply`；
6. **已完成：** 旧 Artifact/Event 只读展示；检测到旧 Patch Artifact 的未完成 Run 时明确拒绝跨协议恢复；
7. **已完成：** 完整后端测试、Studio lint/build 通过；
8. **已完成：** 静态 Context 下的 `SourceRepairContext`、最多两次 Repair ChangeSet、attempt ledger、可修复失败分类和每次完整复验；
9. **已完成：** 覆盖一次修复成功、两次修复耗尽、安全拦截不进入修复的集成测试；
10. **待办：** `NeedContext`、RepositoryMap、ContextReceipt、按需读取和候选物化失败的受控修复；
11. **待办：** Debug Log 实际导出，以及 Railway 真实 Provider 的 modify、add/delete、修复、失败不污染基线和 Worker 修复检查点重启恢复验收；
12. **待办：** 部署验收通过后更新 Review 29 和 Review 26，再决定是否归档。

迁移期间可以用 feature flag 选择旧 Run 或新 Run 的创建路径，但同一 Run 不允许双写两类候选，不允许新路径失败后隐式回退 raw diff。

## 13. 验收标准

- “只修改项目名称”能够通过 `SourceFileChangeSet` 完成，不依赖模型 Patch 语法；
- modify/add/delete 都生成正确候选和 Runtime `SourceDiff`；
- `before_hash`、Context、路径、大小和 Capability Policy 冲突均稳定拒绝；
- 未声明文件保持 byte-level 相同；
- replacement content 超限时明确失败，不截断、不回退；
- Build、Unit Test、Validator 未全部通过时不创建版本；
- 可修复语法或测试失败能由一次 Repair ChangeSet 修正，并且只创建一个最终版本；
- 最多两次 Repair 耗尽后任务明确失败、保留完整 attempt ledger、释放写占用且不改变原版本；
- `EXECUTION_BLOCKED`、安全策略、平台与不可解决失败不调用 Repair Provider；
- Worker 在 ChangeSet、候选物化和验证检查点恢复时不重复 Provider 调用或版本提交；
- Railway 真实 Provider 与 Studio 可见状态完成部署验收；
- Review 29 写入代码、测试和部署证据后才能归档。
