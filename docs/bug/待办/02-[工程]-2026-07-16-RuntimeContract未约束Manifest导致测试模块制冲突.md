# Runtime Contract 未约束 Manifest 导致测试模块制冲突

[toc]

> 类型：Bug｜领域：工程｜状态：待办｜严重程度：P1｜日期：2026-07-16｜版本范围：V1

- **关联 Review：** [Engineer 项目源码 Contract 缺口](../../review/待办/22-[工程]-2026-07-14-Engineer项目源码Contract缺口.md)
- **完备性 Review：** [修改流水线设计同步与 Patch 实现检查](../../review/待办/26-[Agent]-2026-07-15-修改流水线设计同步与Patch实现检查.md)
- **既有 Design：** [通用源码与 Runtime 校验 Contract](../../design/V1/技术设计/12-[工程][TODO]-通用源码与Runtime校验Contract.md)
- **关联 Issue：** [#4](https://github.com/eastonsuo/another-atom/issues/4)

## 现象

对已有 Web 项目执行增量修改后，候选在 Node 单元测试阶段失败：项目 `package.json` 声明 `"type": "module"`，但 `tests/minesweeper.test.js` 使用 CommonJS `require()`。Node 将 `.js` 测试按 ES Module 加载并抛出 `ReferenceError: require is not defined in ES module scope`，候选因此被拒绝，已有可用版本未被覆盖。

## 既有预期与实际行为

- **预期：** Engineer、确定性预检和 Executor 使用同一 Runtime Contract；`allowed_manifest_files=[]` 表示不允许 Manifest，`package.json` 应在执行前被拒绝。其他 Contract 若显式允许 Manifest，Engineer 和测试执行必须继承其模块制语义。
- **实际：** `web-static-document@1.0` 声明 `allowed_manifest_files=[]`、`dependency_installation="forbidden"`，但预检没有检查 Manifest；Engineer Context 也没有暴露 `allowed_manifest_files`。Executor 仍物化 `package.json`，随后由 Node 按其中的 `type` 执行测试，形成上游 Contract 与真实执行语义不一致。

## 代码证据

1. `another_atom/runtime/contracts.py` 的 `web-static-document@1.0` 将 `allowed_manifest_files` 设为空列表。
2. 同文件的 `preflight_runtime()` 检查项目类型、必要文件、入口、测试、大小、Document 与网络边界，但没有校验 `allowed_manifest_files`。
3. `engineer_contract_context()` 返回依赖安装策略，但没有返回允许的 Manifest 文件集合。
4. `another_atom/runtime/artifacts.py` 会把候选文件全部写入 SourceBundle，并把 `tests/*.test.js` 标为测试；Executor 物化后使用 Node 执行，Node 会遵循 `package.json` 的模块制声明。

## 根因

Runtime Contract 已定义 Manifest 边界，但 Engineer Context、预检和 Executor 没有共同执行这项既有字段，导致同一候选在不同阶段具有不同的模块语义。这是 Contract 落地不完整的代码实现错误，不需要重新设计 Runtime Contract。

增量候选校验失败后是否进入有界 Repair，属于修改流水线完备性问题，继续由关联 Review 跟踪，不并入本 Bug 的修复范围。

## 修复边界

- 将 `allowed_manifest_files` 暴露给 Engineer Context，并在 Runtime 预检中确定性执行；
- 预检将不在 `allowed_manifest_files` 中的 Manifest 确定性拒绝，统一 Schema、Prompt、预检和测试语义；
- 如果产品后续决定允许 `package.json`，那属于 Runtime Contract 变更，应另行进入 Review/Design，不作为本 Bug 的修复；
- 不在本 Bug 中实现 CandidateRevision 或有界 Repair。

## 验收条件

1. Engineer Context 明确传递 `allowed_manifest_files=[]`；
2. 当前禁止 Manifest 的 Contract 在 Executor 前拒绝根目录或嵌套 `package.json`，错误准确指出文件与 Contract 字段；
3. 预检失败时不执行候选源码，且不覆盖已有 ProjectVersion；
4. Railway 上的真实首次生成和增量修改不再进入 `type=module` 与 CommonJS 测试冲突路径。

## 2026-07-16 Update：代码修复与本地检查

第一阶段实现已经完成：

- `engineer_contract_context()` 现在向首次生成和增量修改暴露 `allowed_manifest_files`；
- Engineer Prompt 明确空列表不得生成 `package.json`；
- `preflight_runtime()` 在执行源码前拒绝不在允许列表中的根目录或嵌套 `package.json`；
- 新增单元测试验证 Engineer Context 字段和 `package.json` 的预检拒绝结果。

本地验证通过：`tests/unit/test_runtime_contracts.py`、完整 `pytest`、`ruff check another_atom tests`、Studio lint/build。当前尚缺 Railway 上真实 Provider 生成与修改的回归证据，因此本 Bug 继续保留在`待办`。
