# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> 一个部署在云端的 AI 应用生成工具：把产品意图转换为经过确认的 Blueprint、受控 AppSpec 和可运行网页应用。

Another Atom 是一个受 Atoms 启发、但独立设计和实现的产品 Demo。它将真实 LLM 推理与确定性 React Renderer 结合，让用户在系统生成、校验、保存版本和发布应用之前，先确认“将要构建什么”。

本项目同时作为公开的产品设计与工程实现案例，不依赖 Atoms 的源代码或内部基础设施。

## V1 流程

```text
需求 -> 可编辑 Blueprint -> 用户确认 -> 经过校验的 AppSpec
    -> 异步构建 -> 可交互预览 -> 修改 -> 版本
    -> 用户显式发布 -> 公网地址
```

V1 只有一条交付和执行链路：部署在 Railway、通过 React Visual Studio 访问的 Cloud Demo。

```text
React Visual Studio
        |
        | REST + SSE
        v
FastAPI / LLM Orchestrator
        |
        +---- PostgreSQL：用户、Session、配额、Job、版本
        |
        `---- Build Worker -> 固定 React 模板 -> Preview/Publish
```

## 关键决策

- **真实 LLM：** Blueprint 与 AppSpec 由真实模型生成，并通过 Pydantic 校验。
- **受控执行：** 模型不能安装依赖、修改构建命令或直接执行任意 Shell 输入。
- **确定性 Renderer：** AppSpec 通过固定 React 模板落地，依赖在 Docker 镜像中预装。
- **异步构建：** 持久化 Build Job 脱离 HTTP 请求执行，初始并发上限为 1。
- **事务性配额：** 每次模型调用前预占配额，调用后按实际用量结算。
- **显式发布：** Agent 只生成通过校验的 Preview Version，用户选择版本后才能 Publish。

## 创新性

项目的主要创新点不是“使用 LLM”，而是把不可检查的聊天生成过程转换成可验证的生产契约：

```text
用户意图
    -> Blueprint：用户可编辑的产品契约
    -> AppSpec：机器可校验的应用契约
    -> Renderer：确定性执行边界
    -> ProjectVersion：可检查、可恢复的结果
```

Planner、Designer、Engineer、QA 是同一受控流程的可见阶段，不代表多个 Agent 并行运行。每个阶段都必须产生可供评审检查的产物。

## V1 范围

包含：

- React Visual Studio 与 Prompt Composer。
- 真实 LLM 调用和结构化输出校验。
- Blueprint 审批、AppSpec 生成和受控 React 渲染。
- 项目、多 Session、附件、Run、Event 和版本持久化。
- Plan、配额预占、用量结算和账户级限制。
- 异步构建、Preview、修改、Resolve、Restore 和 Publish。
- Docker、Railway PostgreSQL 和 Persistent Volume 部署。

不包含：

- Terminal CLI 或本地仓库执行。
- SQLite 与本地项目到云端的同步。
- 运行时依赖安装和任意代码执行。
- 模型选择器和真实多 Agent 并行。
- 生成应用内部的认证、数据库、商业或支付系统。
- Stripe 付费订阅、Wallet、充值和发票。

## 本地 Agent 方向

类似 Claude Code 的本地 Runtime 是 Cloud Demo 之后最高优先级的扩展：

```text
Terminal CLI -> Local Agent -> 本地文件 / Git / shell / npm
                         -> localhost Visual Studio
                         -> 云端认证 / 配额 / LLM Gateway
```

该能力未在 V1 实现，也不属于本次验收范围。

## 项目状态

已完成：

- [x] Atoms 公开功能分析
- [x] V1 产品需求文档
- [x] Cloud 架构与部署设计
- [x] 笔试提交说明和双语 README

尚未完成：

- [ ] React 与 FastAPI 实现
- [ ] 真实 LLM、Renderer、Build Worker 和持久化
- [ ] 自动化验证和资源压测
- [ ] Railway 部署和在线 Demo URL

## 提交信息

- 源代码仓库：[github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- 在线 Demo：尚未部署
- 实现取舍、完成程度、创新性和后续优先级：[笔试提交说明](./docs/submission-note.md)

## 文档

- [文档索引](./docs/README.md)
- [V1 架构设计](./docs/architecture-design.md)
- [V1 产品需求文档](./docs/another-atom-v1-prd.md)
- [Atoms 参考产品功能分析](./docs/atoms-reference-analysis.md)
- [笔试提交说明](./docs/submission-note.md)

## 附录

- 原版产品参考：[Atoms](https://atoms.dev/)
