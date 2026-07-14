# Engineer 项目源码 Contract 缺口

[toc]

> 类型：工程检查｜状态：待办｜日期：2026-07-14｜版本范围：V1｜基线：`AppSpec`、Engineer Prompt、Repository Packager 与 Preview Adapter

- **产品设计：** [V1 核心产品需求与交互](../../design/V1/产品设计/01-核心产品需求与交互.md)
- **Agent 设计：** [V1 多 Agent 设计](../../design/V1/技术设计/01-[Agent]-多Agent设计.md)
- **工程设计：** [V1 系统架构](../../design/V1/技术设计/03-[工程]-系统架构.md)

## 背景

工程阶段界面显示“工程师正在生成 HTML、CSS 和 JavaScript”。检查确认这不是单纯文案问题：当前 `AppSpec` 只包含 HTML body、CSS、JavaScript 和页面元数据，Repository Packager 固定物化 `index.html`、`styles.css`、`app.js` 与 `app-spec.json`。因此 Engineer 的实际生成边界仍是自包含 Web 应用，而不是通用 Project 源码。

## 摘要

- **[P0｜实现与产品边界冲突]** 产品基线要求保留用户请求的项目类型；Preview 只是一种项目类型能力，不能反向限定生成边界。但当前 Engineer Contract 会把所有可构建请求收敛为 Web `AppSpec`。
- **[P1｜Repository 不是 Engineer 的原生输出]** 当前项目文件由 Packager 从三个字符串派生，Engineer 不能表达多文件目录、配置、依赖声明、测试、README、服务端代码或非 Web 源码。
- **[P1｜Runtime Adapter 与源码 Contract 耦合]** 浏览器 Preview、Validator 和 Engineer 输出共享同一个 Web Contract，导致“暂时没有运行适配器”和“不能生成该类项目”无法区分。

## 证据

1. `another_atom/contracts/schemas.py` 的 `AppSpec` 以 `html`、`css`、`javascript` 为核心源码字段。
2. `another_atom/agent/provider.py` 要求 Engineer 返回可在单个 Sandbox HTML 文档中运行的完整 Web `AppSpec`。
3. `another_atom/repository/service.py` 固定物化四个版本文件，未接收通用文件清单。
4. `another_atom/build/renderer.py` 直接对浏览器源码和 Web Sandbox 能力执行门禁。
5. `docs/design/V1/产品设计/01-核心产品需求与交互.md` 明确 Preview 是项目类型能力，不是生成边界。

## 影响

- 非 Web 请求即使可以生成源码，也只能被拒绝、改写或伪装成网页。
- Web 全栈项目无法诚实表达服务端、依赖和配置，只能生成浏览器演示层。
- 把界面文案改为“生成项目代码”会扩大承诺，但不会改变实际交付物，因此不能作为修复。

## 后续处理要求

本 Review 只落库问题，不在本次进度可观察性修改中重构生成边界。进入实现前需新增或修订正式技术设计，至少确定：

1. 通用项目源码 Contract（例如文件清单、项目类型、入口、构建与运行元数据）的字段和大小边界。
2. Engineer 如何生成完整文件集，Repository 如何原样保存并建立 Artifact/Git/ProjectVersion 对应关系。
3. Web Preview、静态校验以及未来其他 Runtime 如何作为 Adapter 消费项目源码，而不是定义源码形态。
4. 没有 Runtime Adapter 时，如何仍然交付源码、文档、校验和导出，并明确“不支持在线预览”。
5. 从现有 `AppSpec` 与历史 ProjectVersion 迁移和兼容的方式。

在上述设计进入 `docs/design/V1/技术设计/`、实现完成且 Web 与至少一种无 Preview 项目路径通过验收前，本 Review 保持`待办`。
