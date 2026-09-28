# Another Atom 文档导航

[toc]

从 [Feature 索引](./features/README.md) 查找具体功能的设计、实施合同和验证依据；从[设计索引](./design/README.md)查找整体产品、架构和版本共同基线。设计（Design）持续定义预期，评审（Review）保存带日期的检查，缺陷（Bug）保存违反既有预期的实现证据。

九个 Feature 已补齐独立产品说明，16 份专项正文已迁入对应目录；旧路径与现行位置见[文档归属与迁移映射](./features/文档归属与迁移映射.md)。文档整理不代表设计重新确认或功能验收完成。

## 设计

[设计文档](./design/README.md)回答“产品应该怎样工作、技术如何保证它成立”。跨 Feature 基线放在 `design/`，功能专项设计放在 `features/<稳定编号>-<中文功能名>/`；读取 Feature 入口登记的现行产品说明与技术设计。同一个合同只有一处定义。设计内容分为两类：

- `产品设计`：合并产品需求与产品层设计，定义目标、范围、用户路径、交互、用户可感知状态和验收标准；
- `技术设计`：定义如何可靠实现产品设计，再按主要问题分为 `Agent` 和 `工程`。

跨版本产品原则与参考资料保留在 `design/整体/`，外部参考不直接构成已采用合同。已完成 Feature 复用现有设计与证据，不为目录齐全补写历史设计、Code Spec 或实施计划。

## Review

[Review 文档](./review/README.md)回答“某项功能是否完备、检查到了什么”。新 Review 进入`待办`；修复、验证或完成范围决策，并把长期结论写入 Design 后，移入`归档`。Review 不再承担单个代码缺陷的当前队列；检查发现独立 Bug 时只保留检查结论并链接 Bug 文档。

Review 发现需要系统性解决的问题时，在相应 Review 中记录依据与结论；形成正式决定后同步写入 Design。解决方案本身不在 Review 中长期维护。

## Bug

[Bug 文档](./bug/README.md)回答“哪个既有预期被代码实现违反、如何复现和证明修复”。Bug 默认可以直接修改代码，不要求同步更新 Design；只有修复会改变既有 Contract 或产品行为时，才把该部分升级为 Review/Design 变更。GitHub Issue 负责执行状态，Bug 文档保留仓库内的复现、根因与验收证据。

## Feature 交付

[Feature 交付工作流](./agents/feature-delivery-workflow.md)规定从技术设计、Code Spec、代码实施到非生产验证的门禁和交接关系。

- [`superpowers/`](./superpowers/README.md)保存从已确认技术总设计派生的正式 Code Spec，以及复杂 Feature 可选的唯一 Implementation Plan。
- [Feature 入口](./features/README.md)链接当前设计、Spec、可选 Plan 和验证证据；实施合同持续更新原文件，保留来源版本和审阅依据。
- `features/<稳定编号>-<中文功能名>/10-自测方案与执行记录.md`按需保存唯一自测记录；[`validation/README.md`](./validation/README.md)只维护公共规范。
- `features/<稳定编号>-<中文功能名>/11-实施澄清记录.md`按需保存需要确认的持久工程取舍；确认结论回写相应正式依据。
- [`agents/validation-environments.md`](./agents/validation-environments.md)登记可以用于开发侧验证的环境、不可变版本口径和访问边界。

Spec、Plan 和自测记录承接已确认设计。实施澄清可以提出待决问题，但不能自行批准新的合同。GitHub Issue 管理执行待办，Feature 入口只汇总有来源的交付状态。

## 资源

已有图片保持当前路径。新增 Feature 专属资源按需放入该 Feature 的 `assets/`，共享展示资源继续放在 `docs/assets/`；截图与验证证据不得包含密钥或真实用户私密数据。
