# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> 把产品想法转化为可检查、可修改、可管理版本并可发布的网页原型。

Another Atom 设计为一个通过自然语言创建网页产品原型的 AI Agent 工作台。用户描述想法后，可以先检查系统整理的产品方案，再继续完成设计、构建、校验、修改和发布。

本项目受 [Atoms](https://atoms.dev/) 启发，但采用独立的产品与技术设计。它不是 Atoms 的复刻或分支，也不依赖 Atoms 的源代码和内部基础设施。

> **当前状态：** 产品与架构设计已经完成；应用实现和公开部署尚未完成。

## 版本规划

| 版本 | 目标 | 角色模式 | 当前状态 |
| --- | --- | --- | --- |
| **V1** | 交付一条完整、可公开测试的应用生成链路 | Product Manager、Designer、Engineer、QA 固定顺序接力 | 当前实施版本 |
| **V2** | 增加自主协作、动态分派、返工和仲裁 | Leader 协调 Product Manager、Architect、Designer、Engineer、QA | 仅完成方向设计 |

V1 是当前唯一的实施和验收基线。V2 文档只描述后续方向，不代表已经完成。

## V1 要交付的体验

1. 用户描述产品需求，并可上传参考附件。
2. Product Manager（产品经理）生成 **Blueprint**：一份可编辑的产品方案，包含页面、模块、视觉方向和数据需求。
3. 用户检查并确认 Blueprint；没有用户确认，系统不能开始构建。
4. Designer 生成 **VisualSpec**：结构化的视觉和交互规则。
5. Engineer 生成 **AppSpec**：经过机器校验、用于生成应用的结构化指令。
6. 平台在受限环境中构建 React 应用，QA 检查路由和核心交互。
7. 用户预览结果、提出修改、恢复历史版本、导出项目数据，并发布选定版本。

```text
[输入] 产品需求
   |
   v
[角色] Product Manager
   |
   v
[产物] Blueprint
   |
   v
[用户] 检查并确认
   |
   v
[角色] Designer
   |
   v
[产物] VisualSpec
   |
   v
[角色] Engineer
   |
   v
[产物] AppSpec
   |
   v
[平台] 受控 React 构建
   |
   v
[角色] QA
   |
   v
[结果] 可交互预览
   |
   v
[用户] 修改、恢复或发布版本
   |
   v
[结果] 公网地址
```

Team Mode 是一条**固定顺序的角色接力流程**。V1 中角色不并行执行，也不会动态分派任务。每次角色交接都必须产生用户或评审者可以检查的产物。

## V1 计划功能

- 自然语言需求输入和参考附件。
- 可编辑 Blueprint，以及明确的用户确认门。
- Product Manager、Designer、Engineer、QA 阶段时间线。
- 真实 LLM 调用和结构化输出校验。
- 实时进度事件与桌面/移动端交互预览。
- 自然语言修改、问题修复、版本恢复和版本历史。
- 多 Session 与账户级用量限制。
- 版本化 JSON 导出。
- 由用户控制的发布、更新、下线和稳定公开地址。
- Railway、PostgreSQL 和持久化项目存储。

V1 的范围限定为受控的商品展示/商品目录站结构。不支持的需求会在构建前停止；可以映射的相关需求，必须先由用户确认映射结果。

## 为什么这样设计

从聊天输入直接跳到生成结果，会让中间决策难以检查。Another Atom 在中间增加了三层结构化检查点：

```text
用户意图
    -> Blueprint：确认“要构建什么”
    -> VisualSpec：约束“产品如何呈现和交互”
    -> AppSpec：定义“构建系统需要生成什么”
    -> ProjectVersion：保存可检查、可恢复的结果
```

这样可以让生成过程更容易理解和验证。V1 由真实 LLM 生成这些结构化检查点，再由固定 React 模板和平台控制的构建流程生成可运行结果。

## V1 如何运行

V1 只有一条执行链路：部署在 Railway 的云端应用。

```text
浏览器
  |
  v
React Visual Studio
  |
  | REST 命令 + SSE 进度事件
  v
FastAPI
  |
  +---- 固定顺序角色编排 --------> OpenAI
  |
  +---- PostgreSQL
  |       用户 / 项目 / Session / 配额 / Job / 版本
  |
  `---- 异步 Build Worker
          固定 React 模板 / 预装依赖
                         |
                         v
                    Preview 与发布应用
```

模型不能安装依赖、修改构建命令、直接执行任意 Shell 输入或自动发布。构建由有并发上限的异步 Worker 在固定模板内完成。

## V1 不包含

- Terminal CLI 或本地仓库执行。
- 运行时安装依赖或任意代码执行。
- 任意技术栈和生成式后端。
- 自主或并行的多 Agent 协作。
- 模型选择器。
- 生成应用内部的认证、数据库、交易或支付系统。
- Stripe 付费订阅、Wallet、充值和发票。

## 后续方向

### V2：自主多 Agent

V2 将增加 Leader Agent、独立专业角色上下文、选择性并行、结构化返工、仲裁和 Run 级预算。具体见 [V2 角色与编排设计](./docs/v2/role-orchestration-design.md)。

### 本地 Agent Runtime

类似 Claude Code 的本地 Runtime 可以在后续操作本地文件、Git、Shell、npm 和 localhost Visual Studio。该方向尚未实现，也尚未确定归属版本。

## 项目状态

已完成：

- [x] Atoms 公开功能分析
- [x] V1 产品需求和验收标准
- [x] V1 架构与部署设计
- [x] V2 角色与编排设计
- [x] 笔试提交说明和双语文档

尚未完成：

- [ ] React Visual Studio 与 FastAPI 实现
- [ ] LLM 接入、Renderer、Build Worker 和持久化
- [ ] 自动化测试与 Railway 资源验证
- [ ] 公网部署和在线地址

## 相关链接

- 源代码仓库：[github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- 在线版本：尚未部署
- [V1 产品需求](./docs/v1/another-atom-v1-prd.md)
- [V1 架构设计](./docs/v1/architecture-design.md)
- [V1 笔试提交说明](./docs/v1/submission-note.md)
- [V2 方向说明](./docs/v2/overview.md)
- [V2 角色与编排设计](./docs/v2/role-orchestration-design.md)
- [Atoms 参考分析](./docs/reference/atoms-reference-analysis.md)

## 附录

- 原版产品参考：[Atoms](https://atoms.dev/)
