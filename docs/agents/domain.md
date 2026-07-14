# 领域文档

本文规定工程技能探索代码库时如何读取本仓库的领域文档。

## 探索前读取

- 根目录的 `CONTEXT.md`；或
- 如果根目录存在 `CONTEXT-MAP.md`，根据其中的指引读取与当前任务相关的各上下文 `CONTEXT.md`；
- `docs/adr/` 中与当前工作区域相关的架构决策记录（Architecture Decision Record，ADR）。

如果这些文件尚不存在，直接继续，不报告缺失，也不预先建议创建。`/domain-modeling` 技能会在术语或架构决策实际确定后按需创建。

## 文件结构

本仓库采用单上下文结构：

    /
    ├── CONTEXT.md
    ├── docs/adr/
    │   ├── 0001-event-sourced-orders.md
    │   └── 0002-postgres-for-write-model.md
    └── src/

如果以后转为多上下文结构，则在根目录使用 `CONTEXT-MAP.md`，并由它指向各上下文的 `CONTEXT.md`：

    /
    ├── CONTEXT-MAP.md
    ├── docs/adr/
    └── src/
        ├── ordering/
        │   ├── CONTEXT.md
        │   └── docs/adr/
        └── billing/
            ├── CONTEXT.md
            └── docs/adr/

## 使用词汇表中的术语

当输出内容命名领域概念时，包括议题标题、重构提案、假设和测试名称，应使用 `CONTEXT.md` 定义的术语，不要改用词汇表明确排除的同义词。

如果所需概念尚未出现在词汇表中，应先判断它是偏离项目既有语言，还是确实存在领域术语缺口；后者交由 `/domain-modeling` 处理。

## 标明与架构决策的冲突

如果输出内容与现有 ADR 冲突，应明确指出，不能静默覆盖。例如：

> 与 ADR-0007（事件溯源订单）冲突，但值得重新讨论，因为……
