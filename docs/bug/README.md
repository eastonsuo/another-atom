# Another Atom Bug 文档规范与索引

[toc]

## 1. 作用

`docs/bug/` 保存能够独立复现、修复和验收的代码实现错误，回答“哪个既有预期被实现违反、如何证明它已经修复”。Bug 的预期行为必须能由现有 Design、Contract、测试或已经确认的产品行为支持；信息不足以确定预期时，先进入 Review，而不是把设计讨论写成 Bug。

Bug 修复默认不要求修改 Design。只有修复会改变既有产品行为或 Contract 时，才把对应问题升级为 Review，并先更新 [`docs/design/`](../design/README.md)。

## 2. 与 Review、Issue 的边界

- **Review**：检查某项功能是否完备，可以发现多个 Bug、设计缺口或范围问题。
- **Bug**：描述一个可独立关闭的实现错误，保存复现、根因、修复和验收证据。
- **GitHub Issue**：负责排期、负责人和执行状态；Bug 文档是仓库内的稳定证据源。

Review 发现 Bug 后链接 Bug 文档，不重复维护修复过程。Bug 可以不经 Review 直接建立。Issue 存在时双向链接；Issue 的开放或关闭状态是执行状态事实源，Bug 文档只在有验证证据时归档。

## 3. 目录与命名

```text
docs/bug/
├── README.md
├── 待办/
│   └── NN-[Tag]-YYYY-MM-DD-中文短主题.md
└── 归档/
    └── NN-[Tag]-YYYY-MM-DD-中文短主题.md
```

- `NN`：Bug 目录内的独立稳定编号，不与 Review 共用编号空间；
- `Tag`：只使用`产品`、`Agent`、`工程`、`综合`，表示主要归属领域；
- 日期：首次建立 Bug 文档的日期；
- 主题：描述实际错误，不使用泛化的“功能异常”；
- 从`待办`移入`归档`时不修改文件名。

## 4. 必备内容

每篇 Bug 至少包含：

1. 元信息：状态、严重程度、版本范围、发现日期、关联 Review/Design/Issue；
2. 现象与复现条件；
3. 既有预期与实际行为；
4. 能定位到代码、日志或部署行为的证据；
5. 根因；不能判断时明确写“不能判断”；
6. 修复边界，避免顺带改变既有 Contract；
7. 验收条件和修复后的 dated Update。

## 5. 生命周期

```text
确认实现违反既有预期
  -> 建立 待办 Bug
  -> 关联 GitHub Issue（如需执行跟踪）
  -> 修复代码
  -> 自动化测试或部署复现通过
  -> 追加 dated Update 与证据
  -> 移入 归档
```

以下情况不能归档：

- 只能说明现象，尚不能确认根因或既有预期；
- 修复尚未通过与影响范围相称的自动化或部署验证；
- 修复改变了 Contract，但相应 Review/Design 尚未完成；
- Issue 已关闭，但仓库内没有可复算的验证证据。

## 6. 当前待办

- [01｜工程｜Document Preview 丢失 ES Module 执行语义](./待办/01-[工程]-2026-07-16-DocumentPreview丢失ESModule执行语义.md)
- [02｜工程｜Runtime Contract 未约束 Manifest 导致测试模块制冲突](./待办/02-[工程]-2026-07-16-RuntimeContract未约束Manifest导致测试模块制冲突.md)

## 7. 当前归档

暂无。
