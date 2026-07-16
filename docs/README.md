# Another Atom 文档导航

[toc]

项目文档分为 Design、Review 和 Bug 三类。已经确认的方案进入 Design；带日期的功能完备性检查和阶段结论进入 Review；违反既有设计或 Contract、能够独立复现和验收的代码实现错误进入 Bug。图片等非文档资源保存在 `assets/`。

## 设计

[设计文档](./design/README.md)回答“产品应该怎样工作、技术如何保证它成立”，是持续维护的实现依据。设计只分为两类：

- `产品设计`：合并产品需求与产品层设计，定义目标、范围、用户路径、交互、用户可感知状态和验收标准；
- `技术设计`：定义如何可靠实现产品设计，再按主要问题分为 `Agent` 和 `工程`。

跨版本外部分析放入 `整体/参考资料`，不直接构成已采用 Contract。版本目录不再设置重复 README，全部设计入口由 `docs/design/README.md` 统一维护。

## Review

[Review 文档](./review/README.md)回答“某项功能是否完备、检查到了什么”。新 Review 进入`待办`；修复、验证或完成范围决策，并把长期结论写入 Design 后，移入`归档`。Review 不再承担单个代码缺陷的当前队列；检查发现独立 Bug 时只保留检查结论并链接 Bug 文档。

Review 发现需要系统性解决的问题时，在相应 Review 中记录依据与结论；形成正式决定后同步写入 Design。解决方案本身不在 Review 中长期维护。

## Bug

[Bug 文档](./bug/README.md)回答“哪个既有预期被代码实现违反、如何复现和证明修复”。Bug 默认可以直接修改代码，不要求同步更新 Design；只有修复会改变既有 Contract 或产品行为时，才把该部分升级为 Review/Design 变更。GitHub Issue 负责执行状态，Bug 文档保留仓库内的复现、根因与验收证据。

## 资源

`assets/` 保存 README、Design、Review 和 Bug 引用的图片，不参与文档分类。
