# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> 一个终端优先的 AI Agent：把产品想法转化为可运行的网页应用，并通过浏览器工作台展示和修改结果。

Another Atom 是一个受 Atoms 启发、但独立设计和实现的 AI 应用生成工具。用户可以在终端或浏览器中描述产品需求，检查结构化 Blueprint，然后让本地 Agent 生成、构建、预览、修改、保存版本并发布真实网页应用。

本项目同时作为公开的产品设计与工程实现案例，不依赖 Atoms 的源代码或内部基础设施。

## 产品方向

Another Atom 将终端作为主要控制面，将浏览器作为可视化工作区：

```text
Terminal CLI
    |
    v
Python Agent Runtime ---- 认证 / 配额 / LLM Gateway
    |
    +---- 项目工作区 -------- 生成的 React 应用
    |                              |
    |                              v
    `---- REST + SSE ------> Visual Studio
                                   |
                                   v
                              公网访问地址
```

V1 核心流程：

```text
需求 -> Blueprint -> 用户确认 -> 构建 -> 预览
    -> 自然语言修改 -> 保存版本 -> 发布
```

## V1 能力

- Terminal CLI 和浏览器 Prompt Composer。
- 真实 LLM 调用，以及经过校验的 Blueprint 和 AppSpec。
- 写入或修改项目文件前由用户确认方案。
- 受控的文件、构建、预览和发布工具。
- React Visual Studio，展示实时 Agent 事件和应用预览。
- 项目持久化、多 Session、运行恢复和版本管理。
- 账户级 Plan、配额预占与实际用量结算。
- 可部署到公网并提供 HTTPS 测试地址的 Cloud Demo。

V1 不向公网用户开放任意 Shell。云端 Demo 使用受限工作区和命令允许列表；任意远程代码执行需要为每次运行提供独立容器，不属于首版范围。

## 技术架构

当前实施基线：

- **Agent 与 API：** Python、FastAPI、Pydantic、OpenAI Agents SDK。
- **CLI：** Typer、Rich。
- **可视化工作台：** React、TypeScript、Vite。
- **通信：** REST 发送命令，SSE 推送 Agent 事件，OpenAPI 同步前后端协议。
- **本地状态：** 项目文件和 SQLite。
- **云端状态：** PostgreSQL 保存用户、Session、Plan、配额、用量和发布元数据。
- **部署：** Railway 上运行 Docker，并配置 PostgreSQL Service 和 Persistent Volume。

Local Mode 在用户机器上运行 Agent 和项目工作区；Cloud Demo Mode 将同一 Agent Core 运行在受控 Railway 容器中，供评审者通过公网地址测试。

## 仓库状态

当前仓库已经完成参考产品分析、V1 产品定义与架构设计，下一阶段进入应用实现和部署。

- [x] 参考产品功能分析
- [x] V1 产品范围定义
- [x] V1 架构设计
- [ ] 应用实现
- [ ] 自动化验证
- [ ] 公网部署

## 文档

- [文档索引](./docs/README.md)
- [V1 架构设计](./docs/architecture-design.md)
- [V1 产品需求文档](./docs/another-atom-v1-prd.md)
- [Atoms 参考产品功能分析](./docs/atoms-reference-analysis.md)

## 附录

- 原版产品参考：[Atoms](https://atoms.dev/)
