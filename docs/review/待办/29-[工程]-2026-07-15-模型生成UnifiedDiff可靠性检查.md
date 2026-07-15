# 模型生成 Unified Diff 可靠性检查

[toc]

> 类型：工程检查｜状态：待办｜日期：2026-07-15｜版本范围：V1｜代码基线：`d280b77`

- **问题来源：** Run `1c36c375-f800-4ef8-8b2d-d4392ed68f9b` 的 Debug Log
- **相关设计：** [静态源码 Context 与 Patch 执行](../../design/V1/技术设计/10-[Agent][TODO]-静态源码Context与Patch执行.md)
- **上位设计：** [基于现有代码的对话式 AI Coding](../../design/V1/技术设计/02-[Agent]-基于现有代码的对话式AI-Coding.md)
- **后续设计：** [受控动态源码 Context 与 Patch 执行](../../design/V1/技术设计/09-[Agent][TODO]-受控动态源码Context与Patch执行.md)

## 背景

用户在已有 Project 中提交“调整毛玻璃翻译为‘我要翻译’”。Engineer 正确识别了需要修改的标题和主标题，也返回了绑定固定基线、Context hash 和 `before_hash` 的 `SourcePatchSet`，但 Run 在进入构建前以 `PATCH_CHECK_FAILED` 终止。

这次失败不是业务代码错误，也不是源码 Context 缺失，而是模型生成的 unified diff 自身语法不合法。它暴露出当前接口把“决定文件内容”和“精确编码 Git Patch”同时交给模型，导致简单修改也可能被纯格式错误阻断。

## 摘要

- **[P0｜简单修改被 Patch 语法阻断]** Engineer 的修改意图和代码内容正确，但第一个 hunk 把实际 `6→6` 的行数写成 `7→7`，`git apply --check` 稳定返回 `error: corrupt patch at line 11`。
- **[根因｜Seam 放置错误]** `SourcePatchOperation` 只校验路径、operation、`before_hash` 和文件 header；hunk 语法依赖 `git apply` 才暴露。模型因此同时承担语义修改和确定性 Patch 编码，接口不必要地放大了失败概率。
- **[设计决策]** V1 不再以模型生成的 raw unified diff 作为源码修改 Contract。Engineer 改为返回受控 `SourceFileChangeSet`，其中只包含变更路径、操作、基线 hash 和 add/modify 后的完整文件内容；Runtime 在隔离候选目录物化文件并本地计算真实 `SourceDiff`。
- **[范围边界]** 这不是整库重写。模型只返回本轮声明修改的文件；未声明文件必须保持 byte-level 相同。大文件或变更集超过 Provider/Contract 上限时明确失败，不回退 raw diff。
- **[当前状态]** 设计已修订，代码尚未迁移，因此本文保持待办；暂不创建 GitHub Issue。

## 1. 证据

Debug Log 的稳定事实如下：

- Run：`1c36c375-f800-4ef8-8b2d-d4392ed68f9b`
- Project：`43abe4e7-82e4-4bb2-b52e-1a0b74e2abc8`
- Model：`deepseek-v4-pro`
- Prompt：`调整毛玻璃翻译为“我要翻译”`
- 最终状态：`failed / engineer`
- 错误：`PATCH_CHECK_FAILED / error: corrupt patch at line 11`
- 配额消耗：5 units

事件链显示：

1. `#1748 agent.output.validated` 把模型输出判定为通过 Contract；
2. `#1749 source.patch_created` 保存了 `index.html` 的候选 Patch；
3. `#1750 source.patch_check_started` 开始本地检查；
4. `#1751 source.patch_failed` 立即报 `corrupt patch at line 11`；
5. Run 终止，没有进入 Build、Unit Test 或 Validator。

出错 hunk 的 header 声明为：

```diff
@@ -4,7 +4,7 @@
```

但该 hunk 正文中，旧文件和新文件各自都只有 6 行。将同一 hunk 单独送入 `git apply --check -`，仍稳定得到：

```text
error: corrupt patch at line 11
```

因此可以排除业务源码、流式分片、编码和后续 Validator；失败由 raw diff 的 hunk 计数错误直接造成。

## 2. 为什么现有修补方向不够稳

### 2.1 只增强 Prompt

Prompt 可以提醒模型输出标准 unified diff，但不能把字符级格式变成确定性行为。本次模型已经得到“标准 header”要求，仍生成了错误行数。

### 2.2 Contract 失败后重新请求模型

增加 hunk 语法校验并触发 Provider retry 可以降低单次失败率，但会增加延迟和配额，而且下一次仍可能出现 start line、context 或多 hunk 错误。它保留了错误的职责分配。

### 2.3 Runtime 自动修 hunk

Runtime 可以重算 hunk count，但仍需处理起始行、上下文缺失、转义、换行和多文件 Patch。自动改写模型 Artifact 还需要额外记录原始值、规范化值和恢复一致性，接口复杂度没有消失。

## 3. 修订后的接口

Engineer 输出 `SourceFileChangeSet`：

```text
SourceFileChangeSet
  baseline/context bindings
  summary
  app_spec_delta
  changes[]
    path
    operation: modify | add | delete
    before_hash?
    replacement_content?
```

约束：

- `modify`：必须完整读过当前 revision 文件，提供匹配的 `before_hash` 和完整 `replacement_content`；
- `add`：目标不存在，提供完整 `replacement_content`，不提供 `before_hash`；
- `delete`：提供匹配的 `before_hash`，不提供 `replacement_content`；
- 未出现在 `changes[]` 的文件保持不变；
- 模型不返回 hunk、行号、line stats 或最终 Diff。

Runtime 隐藏以下实现：

1. 校验基线、Context、路径、hash、文件类型和大小；
2. 从固定 revision 建立隔离候选目录；
3. 按 `changes[]` 写入、添加或删除文件；
4. 重新枚举并校验候选源码；
5. 从真实文件本地计算增量/累计 `SourceDiff`；
6. 执行 Build、Unit Test、Validator、版本 CAS 和 Git commit。

该 Module 的外部 Interface 更小：Engineer 不再理解 Git Patch 语法，调用方和测试也不再分别处理模型 Patch、规范化 Patch 和实际 Diff。复杂度集中在 Runtime 的候选物化实现中。

## 4. 实现影响

代码迁移至少涉及：

- `SourcePatchSet / SourcePatchOperation` Contract 替换为 `SourceFileChangeSet / SourceFileChange`；
- Provider 方法和 Prompt 改为返回受控完整文件内容；
- Repository Service 删除模型 Patch header/hunk 与 `git apply` 路径，改为隔离目录内的确定性文件物化；
- Orchestrator、Artifact、事件和恢复检查点改用 ChangeSet 语义；
- `SourceDiff` 继续由 Runtime 从候选文件计算，不改变其证据地位；
- 历史 `source_patch_set` Artifact 保持只读可查看，新 Run 不再产生该类型；
- Mock、Provider Contract、add/modify/delete、越权、hash 冲突、空修改、恢复和端到端修改测试同步迁移。

## 5. 验收标准

1. 同一“修改项目名称”的输入不再要求模型生成 unified diff，能够通过受控文件替换完成候选物化。
2. modify/delete 的 `before_hash` 不匹配时拒绝修改，当前版本和发布指针不变。
3. 未在 `changes[]` 声明的文件相对输入 revision 保持 byte-level 相同。
4. Runtime 生成的 `SourceDiff` 能准确展示 changed/added/removed files、行数和 unified diff。
5. 超过文件数、单文件大小或 Provider 输出上限时返回稳定错误，不静默裁剪，不回退到 raw diff 或完整 AppSpec。
6. Build、Unit Test、Validator 未全部通过时不创建 ProjectVersion 和 Git commit。
7. Railway 真实 Provider 至少完成一次 modify、一次 add/delete 和一次失败不污染基线的验收。

## Update 2026-07-15（静态文件变更链已本地实现）

- 新修改 Run 已切换到 `create_source_file_change_set() -> SourceFileChangeSet`。Mock 与 Ollama/DeepSeek Provider 不再生成 hunk、行号或 unified diff；modify/add 返回声明文件的完整最终内容，delete 只返回路径和基线 hash。
- Repository Service 已删除新链路的 Patch header/hunk 校验和 `git apply`，改为在临时隔离目录校验绑定、Context、路径、`before_hash`、内容规则和大小后确定性写入、添加或删除文件；未声明文件保持不变，`SourceDiff` 仍由真实候选文件本地计算。
- Orchestrator、Artifact、事件、文件面板和 Studio 已切换到 `source_file_change_set`、`source_change_apply_report` 与 `source.change_*`。旧 Patch Artifact/Event 保留只读展示；未完成旧 Patch Run 不跨协议续接。
- 自动化证据：`tests/unit/test_source_change.py` 覆盖 modify、add/delete、Context 缺失、hash 冲突、受保护路径、输出超限、未声明文件不变和最终版本提交；Project Chat 集成测试覆盖成功修改及失败不创建版本。完整后端测试为 `157 passed`；`.venv/bin/ruff check another_atom tests` 通过；Studio `npm run lint` 与 `npm run build` 通过，Vite 仅保留既有大 chunk 警告。
- 本 Review 继续保留在`待办`：尚未用真实 Provider 在 Railway 完成 modify、add/delete、失败不污染基线、Debug Log 导出和 Worker 重启恢复验收。

## Update 2026-07-15（Runtime-managed HTML 外壳误判修正）

Railway 的真实 Provider 修改“毛玻璃翻译”项目名称时，已生成合法 `SourceFileChangeSet`，但 `index.html` 的 doctype、`body` 边界或入口脚本格式没有逐字复刻 Runtime 模板，候选在 Build 前以 `CANDIDATE_CONTRACT_INVALID / index.html changed the Runtime-managed document shell` 终止。该失败仍不是业务修改错误，而是新 Contract 把 Runtime 自己拥有的外壳格式精度留给了模型。

Repository Service 现只从 Engineer 候选中识别唯一应用正文和本地 `app.js` 入口，随后由 Runtime 重新生成规范 doctype、`head`、`body` 和入口脚本外壳。外部脚本、多个或嵌套文档边界仍返回 `CANDIDATE_CONTRACT_INVALID`；应用正文、`styles.css`、去除 Guard 后的 `app.js` 和 `AppSpec` 仍须一致。单元测试覆盖无害外壳格式变化可规范化、外部入口脚本仍被拒绝；完整后端测试和静态检查通过。Railway 同一修改场景仍待新部署复验，因此本文保持待办。
