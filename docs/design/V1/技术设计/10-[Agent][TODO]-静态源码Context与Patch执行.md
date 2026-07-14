# Another Atom V1 静态源码 Context 与 Patch 执行

[toc]

- **文档状态：** V1 第一阶段技术设计；本地代码与自动化测试已完成，Railway 真实 Provider 和重启恢复验收完成前保持 `[TODO]`
- **功能范围：** 已有 Project 修改时的一次性源码 Context、结构化 Patch、隔离 apply、真实 Diff 与现有执行门禁
- **上位设计：** [基于现有代码的对话式 AI Coding](./02-[Agent]-基于现有代码的对话式AI-Coding.md)
- **后续终态：** [受控动态源码 Context 与 Patch 执行](./09-[Agent][TODO]-受控动态源码Context与Patch执行.md)
- **检查来源：** [26｜修改流水线设计同步与 Patch 实现检查](../../../review/待办/26-[Agent]-2026-07-15-修改流水线设计同步与Patch实现检查.md)

## 背景

本次改造前，已有 Project 的修改 Run 会一次性生成确定性 `SourceContext`，但 Engineer 返回完整新版 `AppSpec`，随后 Runtime 才从完整候选计算 `SourceDiff`。这使模型输出仍以完整文档为单位，不能约束到本轮实际修改的文件和代码区间，也不能在 apply 前验证基线、路径和文件 hash。

动态 Context 终态还需要 `NeedContext`、多轮受控读取和 `ContextReceipt`，实现范围较大。本文先完成可独立验收的第一阶段：保留当前一次性静态 Context，模型改为输出结构化 Patch；Runtime 在隔离候选目录检查并 apply，再从真实候选源码重建兼容 Contract、计算 Diff 并执行现有 Build/Test/Validation。

## 摘要

- **模型输出**
  - 修改 Run 的 Engineer 输出由完整 `AppSpec` 改为绑定基线和静态 Context 的 `SourcePatchSet`；源码变更使用 unified diff，非源码 AppSpec 字段只允许用结构化 Delta 表达。
- **Context 边界**
  - 修改或删除已有文件时，该文件必须完整存在于本轮 `SourceContext.included_files`；省略文件不可修改，Context 不足时明确失败。
- **Runtime 权限**
  - Agent 不写仓库。Runtime 校验项目、Run、基线 commit、源码 Manifest、Context hash、路径和 `before_hash`，然后在临时目录执行 `git apply --check` 和 apply。
- **单一事实**
  - 模型修改真实 HTML/CSS/JavaScript 与测试文件；`app-spec.json` 是 Runtime 生成的兼容 Contract 文件，模型不得直接 Patch，避免同时维护两份代码事实。
- **最终证据**
  - Runtime 从 apply 后真实文件重建兼容 `AppSpec` 和 `SourceBundle`，再计算 `SourceDiff`；模型 Patch 只是候选指令，不能替代最终 Diff。
- **阶段边界**
  - 本期不实现 `NeedContext`、候选 revision 或验证失败后的 Repair Patch。终态在复用现有 Patch 校验/apply 基础上，同时扩展 Patch 前的动态读取和 Patch 后的有界验证修正。

## 1. 当前实现与替换点

改造前的修改链路为：

```text
BaseSourceSnapshot
  -> build_source_context()
  -> revise_app_spec(...) -> 完整 AppSpec
  -> render_version_files(AppSpec)
  -> calculate_source_diff(...)
  -> SourceBundle
  -> Build / Test / Validation
```

本文替换为：

```text
BaseSourceSnapshot
  -> build_source_context()
  -> create_source_patch_set(...) -> SourcePatchSet
  -> Runtime Contract / path / hash preflight
  -> isolated git apply --check / apply
  -> rebuild compatible AppSpec + SourceBundle
  -> Runtime calculate SourceDiff from applied files
  -> Build / Test / Validation
```

旧 `revise_app_spec()` 可以暂时保留给历史兼容和未迁移测试，但已有 Project 的正式修改路径不得再调用它，也不得在 Patch 失败时隐式回退到完整 AppSpec。

## 2. 本期范围与明确不做

### 2.1 本期实现

- 复用现有 `BaseSourceSnapshot` 和确定性 `SourceContext`；
- 新增 `SourcePatchSet`、文件 Patch 和 AppSpec 元数据 Delta Contract；
- 新增 `source_patch_set` 与 `source_patch_apply_report` Artifact；
- 校验 Patch 与 Project、Run、基线版本、commit、Manifest 和 Context hash 的绑定；
- 校验 modify/delete 文件已完整进入 Context 且 `before_hash` 一致；
- 在隔离临时目录执行 `git apply --check` 和 apply；
- 从真实候选文件重建兼容 `AppSpec` 和 `SourceBundle`；
- 从 apply 后文件计算 `SourceDiff`，接入现有 Build/Test/Validation、版本 CAS 与 Git commit；
- Patch 结构错误、越权、冲突、空修改和候选 Contract 不一致均形成明确错误。

### 2.2 本期不做

- `NeedContext` 和多轮 list/search/read；
- RepositoryMap、动态 Context Exchange 和最终 ContextReceipt；
- CandidateRevision、PatchAttempt 链、RepairContext 和验证反馈修正；
- 向量检索、语义索引、Agent 自主探索或 Shell Tool；
- 非 `web-static-v1` 项目的通用 Patch Adapter；
- 把模型 Patch 直接写入 Project 主工作树；
- 用完整 AppSpec 作为 Patch 失败时的隐式降级。

## 3. 静态 Context 与修改权限

`build_source_context()` 的确定性顺序保持不变：用户明确选择文件优先，其次是消息准确提及的路径，最后按规范化路径排序。在字符预算内每个文件要么完整加入，要么完全省略。

本阶段的写权限规则为：

- `modify` / `delete`：目标文件必须存在于基线 Snapshot，也必须完整存在于 `included_files`；
- 基线存在但本轮被省略的文件：返回 `CONTEXT_INSUFFICIENT`；
- `add`：路径必须通过规范化、文件类型、数量和大小策略，且基线中不存在；
- `app-spec.json`、`.another-atom/**`、绝对路径、反斜线和包含 `.` / `..` 的路径始终禁止；
- `index.html`、`styles.css`、`app.js` 不能删除；候选必须保留至少一个 `tests/*.test.js`。

本阶段不允许模型追加读取。模型判断信息不足时应停止生成修改；如果它仍引用省略文件，Runtime 以 `CONTEXT_INSUFFICIENT` 拒绝，而不是猜测或自动扩大 Context。

## 4. SourcePatchSet Contract

```text
SourcePatchSet
  schema_version
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
  patches[]
    path
    operation: modify | add | delete
    before_hash?
    unified_diff
```

`source_context_hash` 由 Runtime 对完整 `SourceContext` 的规范化 JSON 计算。模型必须原样回传，Runtime 不接受缺失或不同基线的 Patch。

每个 Patch 只允许包含一个文件的标准 unified diff：

- modify：`--- a/path` 与 `+++ b/path`；
- add：`--- /dev/null` 与 `+++ b/path`；
- delete：`--- a/path` 与 `+++ /dev/null`。

modify/delete 必须携带 Snapshot 中该文件的原始 SHA-256；add 不携带 `before_hash`。同一路径在一个 PatchSet 中只能出现一次。

### 4.1 与终态 Contract 的兼容

当前已实现的是 `SourcePatchSet schema_version=1.0`，绑定 `source_context_hash` 和原始基线。进入[受控动态源码 Context 与 Patch 执行](./09-[Agent][TODO]-受控动态源码Context与Patch执行.md)前，Runtime 必须完成以下规范化迁移：

- 把静态 SourceContext 转换为 revision 0 的只读 ContextReceipt；
- 把当前 SourcePatchSet 包装为 `patch_attempt_index=1 / patch_kind=initial / input_source_revision=0` 的 PatchAttempt；
- apply 成功后建立 CandidateRevision 1，并分别保存相对 revision 0 的 IncrementalSourceDiff 和相对原始基线的 CumulativeSourceDiff；
- 动态 Provider 输出升级为绑定 `input_candidate_revision_hash / input_source_manifest_hash / context_receipt_hash` 的终态 SourcePatchSet；
- `schema_version=1.0` 只允许在静态迁移路径读取，不能用于 Repair Patch，也不能套用到 revision 1 之后的候选源码。

这样可以保留当前已实现的 Patch 校验和 apply 代码，同时明确现有 `source_context_hash` 不是终态修复循环的充分绑定。

## 5. AppSpec 与真实源码的一致性

当前 `web-static-v1` 同时保存 `app-spec.json` 和由它渲染出的 `index.html`、`styles.css`、`app.js`。为了避免要求模型同步修改重复事实，本阶段规定：

1. 模型 Patch 只能修改真实源码和测试，不得修改 `app-spec.json`；
2. Runtime 从候选 `index.html` 中提取受控 `<body>` 内容，从 `styles.css` 读取 CSS，从 `app.js` 去除 Runtime 注入且不可修改的网络 Guard；
3. Runtime 把上述代码字段与 `app_spec_delta` 合并到基线 `AppSpec`；视觉 Token 始终以修订后的 `ArchitectureSpec` 为准；
4. Runtime 重新调用 `render_version_files()`，要求重新渲染出的 `index.html`、`styles.css`、`app.js` 与 apply 后候选逐字一致；不一致返回 `CANDIDATE_CONTRACT_INVALID`；
5. Runtime 用重建后的 AppSpec 生成新的 `app-spec.json`，覆盖候选目录中的旧兼容文件；
6. `SourceBundle` 和最终 `SourceDiff` 都从这组真实、已对齐的候选文件生成。

`app_spec_delta` 只覆盖不适合从源码稳定推导的产品元数据。代码字段和视觉 Token 不允许通过 Delta 修改，避免同一字段存在两个输入来源。

## 6. Provider Contract

修改路径新增：

```text
create_source_patch_set(
  project_id,
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
) -> SourcePatchSet
```

Provider Prompt 必须明确：

- 只根据本轮完整 Contract 和 `included_files` 修改；
- 只输出结构化 PatchSet，不返回完整 AppSpec 或完整候选文件包；
- 不修改 Runtime shell、网络 Guard 或 `app-spec.json`；
- 不确定时不猜测省略文件；
- Patch 必须保留未被变更要求影响的行为和测试；
- `app_spec_delta` 只包含确实变化的元数据。

结构化输出失败继续使用现有 Provider 重试与配额结算。Patch 通过 Schema 但本地无法 apply 时，不允许降级到完整 AppSpec；本阶段先形成明确失败。终态修复使用当前 input revision、ContextReceipt 和错误证据生成 Repair Patch，不再使用“始终绑定相同原始基线的替换 Patch”。

## 7. Runtime 校验与隔离 apply

Runtime 按以下顺序执行：

1. 校验 PatchSet 的 Project、Run、base version、base commit、Manifest 和 Context hash；
2. 校验 Patch 数量、唯一路径、规范化相对路径、允许后缀和 Runtime 保留文件；
3. 校验 modify/delete 的 Context 完整读取权限与 `before_hash`；
4. 校验 unified diff 的单文件 header 与声明 operation/path 一致；
5. 从 `BaseSourceSnapshot` 在临时目录物化候选基线，不使用 Project 当前 worktree；
6. 执行 `git apply --check --whitespace=nowarn`；
7. 检查通过后执行 `git apply --whitespace=nowarn`；
8. 拒绝符号链接、非 UTF-8、超大小、越权新增文件和必要入口缺失；
9. 按第 5 节重建 AppSpec、`app-spec.json` 与 SourceBundle；
10. 从 apply 后完整候选文件确定性计算 SourceDiff。

Agent 没有 Git、Shell 或 Repository 写权限。临时目录在成功和失败后都清理；正式 Project 仓库只在现有 `_create_version()` 通过最终 CAS 后写入新版本。

## 8. Artifact、事件与恢复

新增 Artifact：

- `source_patch_set`：模型返回并通过 Pydantic Contract 的原始候选 Patch；
- `source_patch_apply_report`：Runtime 校验/apply 结果、实际文件清单与候选 Manifest；
- 现有 `app_spec`：Runtime 从 apply 后源码重建的兼容 Contract，不再是修改模型的直接输出；
- 现有 `source_bundle`、`source_diff`：均来自 apply 后真实候选。

恢复时如果 PatchSet、apply report、AppSpec、SourceBundle 与 SourceDiff 均已存在且 hash 相互一致，Worker 复用候选并从 Build 阶段继续；不得重复调用 Engineer。任一候选 Artifact 缺失或 hash 不一致时，从固定基线重新执行 apply，不读取主工作树的未提交状态。

关键事件至少包括：

- `source.patch_created`；
- `source.patch_check_started`；
- `source.patch_applied`；
- `source.diff_created`；
- 对应失败事件和稳定错误码。

## 9. 错误码

- `CONTEXT_INSUFFICIENT`：Patch 引用基线存在但未完整进入静态 Context 的文件；
- `PATCH_BASE_MISMATCH`：Project、Run、版本、commit、Manifest 或 Context hash 不一致；
- `PATCH_PATH_FORBIDDEN`：路径、类型、Runtime 保留文件或操作越权；
- `PATCH_HASH_MISMATCH`：`before_hash` 与固定基线不一致；
- `PATCH_CHECK_FAILED`：unified diff 格式或上下文无法在基线应用；
- `PATCH_APPLY_FAILED`：检查通过后实际 apply 失败；
- `CANDIDATE_CONTRACT_INVALID`：候选入口、Runtime shell/Guard、AppSpec 或 SourceBundle 无法一致重建；
- `EMPTY_CHANGE`：apply 后与基线无真实变化。

所有失败都释放 Project 写占用，不创建 ProjectVersion，不移动 latest/published 指针，并在项目对话和日志中展示稳定错误原因。

## 10. Build/Test/Validation 与版本写回

Patch apply 成功后继续使用现有独立 Runtime Executor：

```text
SourceBundle
  -> node --check
  -> node --test
  -> deterministic Validator
  -> final base-version CAS
  -> ProjectVersion + Git commit
```

最终提交使用 apply 后 `SourceBundle` 原样物化，不允许再次从模型输出重生成代码。任何门禁失败都不创建版本。本阶段验证失败直接终止，不能调用旧 `repair_app_spec()`；终态由 Runtime 生成 RepairContext，并要求下一 Patch 绑定当前失败 CandidateRevision，而不是原始基线。

## 11. 自动化验收

### 11.1 单元测试

- SourceContext hash 稳定；
- Mock Provider 返回只含 Patch 与元数据 Delta 的结构化输出；
- modify/add/delete header、路径和 `before_hash` 校验；
- 已包含文件可修改，省略文件返回 `CONTEXT_INSUFFICIENT`；
- `app-spec.json`、路径穿越、重复路径和 Runtime shell/Guard 修改被拒绝；
- apply 后 AppSpec、SourceBundle 与真实文件一致；
- SourceDiff 与 apply 后文件一致。

### 11.2 集成测试

- 已有 Project 标题修改通过 Patch 创建 `ai_edit` 版本；
- Run 保存 SourcePatchSet、apply report、Runtime 重建 AppSpec、SourceBundle 和 SourceDiff；
- 修改路径不调用 `revise_app_spec()`；
- Patch 失败、Context 不足、基线/hash 冲突和空修改不创建版本并释放写锁；
- Build/Test/Validation 失败不回退完整 AppSpec；
- Worker 恢复不重复已持久化 Engineer 调用；
- 最终 Git 文件、SourceBundle、AppSpec、预览和 SourceDiff 一致；
- 用户归属、发布指针和并发写入边界保持不变。

### 11.3 部署验收

- Railway 真实 Provider 至少完成一次已有 Project 的 Patch 修改；
- 日志可见 Context 准备、Patch 生成、检查、apply、Diff、Build/Test/Validation；
- 进程重启后可从已保存 Patch/候选 Artifact 恢复；
- 持久化 Volume 中的新版本 Git commit 与页面预览一致。

## 12. 向动态 Context 迁移

动态版本在 `create_source_patch_set()` 前增加：

```text
EngineerAction
  +-- NeedContext -> Runtime list/search/read -> ContextReceipt -> Engineer
  +-- CannotProceed
  `-- ProducePatch -> SourcePatchSet
```

迁移分为两条连续扩展：

1. **Patch 前动态读取**：`source_context_hash` 规范化为 revision 0 的 `context_receipt_hash`，modify/delete 权限从静态 `included_files` 改为当前 revision Receipt 中完整读取的文件；
2. **Patch 后有界修正**：每次成功 apply 生成 CandidateRevision、增量/累计 Diff 和验证报告；可修复失败生成 RepairContext，下一 SourcePatchSet 绑定当前失败 revision，最多执行终态设计规定的 Patch attempt。

现有路径、before hash、隔离 apply、AppSpec/SourceBundle 重建、Runtime 验证和最终版本 CAS 继续复用，但 Contract 绑定从“原始基线 + 单个 Patch”扩展为“输入 revision + PatchAttempt + CandidateRevision”。无论经历多少 Patch，整个 Run 最终只创建一个 ProjectVersion 和 Git commit。

## 13. 完成条件

### Update 2026-07-15

本地实现已经完成以下纵切：修改 Provider 输出 `SourcePatchSet`；Runtime 校验基线、Context、路径和 `before_hash` 后在隔离候选目录执行 `git apply --check` 与 apply；`app-spec.json` 由 Runtime 从 apply 后源码和结构化元数据 Delta 重建；SourceBundle、SourceDiff、Build/Test/Validation 和最终版本均以 apply 后真实文件为准。PatchSet 与 apply report 已保存为 Artifact，修改路径不再调用 `revise_app_spec()`，验证失败也不回退 `repair_app_spec()`。Studio 已增加 Patch 生成、检查、应用和真实 Diff 的可见事件说明。

自动化覆盖成功修改、add/delete、Context 省略、`before_hash` 冲突、失败不建版本和写锁释放。本文仍保留 `[TODO]`，因为 Railway 真实 Provider、进程重启恢复和部署环境一致性尚未验收。

本文保留 `[TODO]`，直到同时满足：

- 修改生产路径不再调用 `revise_app_spec()` 或 `repair_app_spec()`；
- SourcePatchSet 和 apply report 已成为可恢复 Artifact；
- Patch 权限、隔离 apply、候选重建、真实 Diff 和错误码自动化测试通过；
- 完整后端测试、前端 lint/build 通过；
- Railway 真实 Provider 和重启恢复验收完成；
- [26｜修改流水线设计同步与 Patch 实现检查](../../../review/待办/26-[Agent]-2026-07-15-修改流水线设计同步与Patch实现检查.md)追加验证证据并满足归档条件。
