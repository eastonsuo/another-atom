# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> 把产品想法转化为可检查、可修改、可管理版本并可发布的网页原型。

Another Atom 设计为一个通过自然语言创建网页产品原型的 AI Agent 工作台。用户描述想法后，可以先检查系统整理的产品方案，再继续完成设计、构建、校验、修改和发布。

本项目受 [Atoms](https://atoms.dev/) 启发，但采用独立的产品与技术设计。它不是 Atoms 的复刻或分支，也不依赖 Atoms 的源代码和内部基础设施。

> **当前状态：** V1 产品与架构设计、V2 角色编排设计已经完成；两个版本的应用实现和公开部署尚未完成。

## 版本规划

| 版本 | 目标 | 角色模式 | 当前状态 |
| --- | --- | --- | --- |
| **V1** | 交付一条完整、可公开测试的应用生成链路 | Product Manager、Designer、Engineer、QA 固定顺序接力 | 当前实施版本 |
| **V2** | 增加自主协作、动态分派、返工和仲裁 | Leader 协调 Product Manager、Architect、Designer、Engineer、QA | V1 完成后实施 |

项目按 **V1 -> V2** 顺序实施。V1 是当前开发和验收基线；V2 已进入版本规划，待 V1 验收通过后实施。两个版本目前都没有完成应用实现。

## V1 要交付的体验

1. 用户描述产品需求，并可上传参考附件。
2. Product Manager（产品经理）生成 **Blueprint**：一份可编辑的产品方案，包含页面、模块、视觉方向和数据需求。
3. 用户检查并确认 Blueprint；没有用户确认，系统不能开始构建。
4. Designer 生成 **VisualSpec**：结构化的视觉和交互规则。
5. Engineer 生成 **AppSpec**：经过机器校验、用于生成应用的结构化指令。
6. 平台在受限环境中构建 React 应用，QA 检查路由和核心交互。
7. 用户预览结果、提出修改、恢复历史版本、导出项目数据，并发布选定版本。

### A. 应用生成与开发

#### 步骤 1：需求确认

```text
用户 Prompt
    |
    v
[Product Manager]
    |
    v
Blueprint
    |
    v
用户检查并确认
```

#### 步骤 2：设计与构建

```text
已确认的 Blueprint
    |
    v
[Designer] -> VisualSpec
    |
    v
[Engineer] -> AppSpec
    |
    v
平台受控 React 构建
```

#### 步骤 3：质量校验

```text
构建结果
    |
    v
[QA] -> ValidationReport / QAReview
    |
    v
可交互预览
```

### B. 预览、版本与发布

```text
可交互预览
    |
    +-- 修改或 Resolve -> 保存新版本 -> 再次校验
    |
    +-- Restore --------> 创建恢复版本，保留原历史
    |
    `-- 选择版本 -------> Publish / Update
                                  |
                                  v
                            稳定公网地址
```

Team Mode 是一条**固定顺序的角色接力流程**。V1 中角色不并行执行，也不会动态分派任务。每次角色交接都必须产生用户或评审者可以检查的产物。

## V1 能力地图

V1 不是十几个分散功能的集合，而是一条从想法到公网结果的完整链路：

```text
主链路：Prompt + 附件 -> Project -> Blueprint -> 用户确认 -> 角色接力 -> Preview
变更链路：Preview -> Edit / Resolve / Restore -> ProjectVersion
发布链路：ProjectVersion -> Publish / Update -> Public URL

全程保障：持久化状态 | 配额控制 | SSE 事件 | 错误恢复 | Railway 部署
```

### 1. 发起：把一个想法变成可恢复的项目

- **用户要做什么：** 在 Home 直接输入多行需求、添加参考附件，并选择 Engineer Mode 或 Team Mode，不需要先经过营销页。
- **系统如何响应：** Prompt 为空、附件处理中或提交失败时，Build 显示明确状态；可提交后创建 Project，而不是只保留一段临时对话。
- **留下什么：** Prompt、附件元数据和最近状态随 Project 保存；用户可以从 Projects 重新打开、重命名或删除它。

### 2. 确认：先对齐要构建什么

- **用户看到什么：** Product Manager 将需求整理为可编辑 Blueprint，列出项目名称、页面、模块、视觉方向和数据需求。
- **系统如何判断：** 真实 LLM 同时给出 `supported`、`adapted` 或 `unsupported`；结构化结果必须通过 Schema 校验。
- **如何进入下一步：** 用户确认后，Designer、Engineer、QA 才依次生成 VisualSpec、AppSpec 和 QAReview；没有确认或没有真实产物，流程不能假装完成。
- **失败怎么办：** 多次模型失败后保留原项目和输入，用户可以 Retry、Edit request，或明确选择非 AI 的 Starter Blueprint。

### 3. 构建：让过程和结果都能被检查

- **真实执行：** AppSpec 进入受控 React Renderer；异步 Build Worker 只使用固定模板和预装依赖，不接受模型生成的任意命令。
- **过程可见：** Studio 通过 SSE 展示角色阶段、构建进度和错误；刷新页面后仍能恢复当前状态。
- **结果可用：** Viewer 可以切换 Desktop/Mobile，并实际访问 Home、Catalog、Product 页面和核心交互。
- **可以继续修改：** 用户可编辑文字、按钮、颜色和商品图片；Console 提供可定位错误，Resolve 会形成修复记录。

### 4. 交付：把一次生成变成可管理版本

- **版本原则：** Build、Edit、Resolve、Restore 都生成 ProjectVersion；Restore 创建新的恢复版本，不覆盖原历史。
- **发布原则：** 用户显式执行 Publish、Update 或 Unpublish，并选择 Always Latest 或 Specify Version，不由 Agent 自动发布。
- **最终结果：** 稳定 Public URL 能在无登录、无本地状态的新浏览器中打开正确版本。
- **可带走的数据：** Export 输出版本化 JSON，但排除密钥、绝对路径、原始对话和内部配额流水。

### 5. 保障：让多用户和公开部署真正成立

- **状态不丢：** PostgreSQL 保存用户、Project、Session、配额、Build Job、事件和版本；Railway 进程重启后可以恢复。
- **用量不透支：** Plan 与 Usage Ledger 在 LLM 调用前预占、调用后结算，并发 Session 不能绕过账户配额。
- **部署可访问：** Railway 承载 Web 服务、异步构建和发布结果，用户通过统一 HTTPS 域名使用 Studio 和访问公开应用。
- **边界不伪装：** Cloud、Integrations 和 Growth 在 V1 只说明能力边界，不触发未接通的授权、支付或第三方费用。

V1 的生成范围限定为受控的商品展示/商品目录站。`unsupported` 在构建前停止；`adapted` 必须展示需求映射和舍弃项，并由用户确认后才能继续。

## V1 交付里程碑

| 里程碑 | 可交付结果 | 阶段验收 | 状态 |
| --- | --- | --- | --- |
| **M0 设计基线** | PRD、架构、角色契约和提交说明 | V1/V2 边界一致，关键状态、数据和错误契约可追踪 | 已完成 |
| **M1 云端基础** | React 工作台、FastAPI、PostgreSQL、Project/Session/Quota 基础模型 | 可创建并重新打开项目；刷新和进程重启后基础状态不丢失 | 未开始 |
| **M2 生成链路** | Prompt、附件、Blueprint 审批、四角色顺序执行、异步构建 | 未确认 Blueprint 不构建；每阶段有真实产物；失败可见且可重试 | 未开始 |
| **M3 Studio 闭环** | Desktop/Mobile 预览、编辑、Resolve、版本与 Restore | 核心路由和交互可用；Build/Edit/Resolve/Restore 均形成可恢复版本 | 未开始 |
| **M4 发布与加固** | Publish/Update/Unpublish、稳定公开地址、Export、自动化测试和 Railway 部署 | 主路径、反路径、恢复、配额和公开访问达到最终验收基线 | 未开始 |

### 最终验收基线

#### 1. 功能闭环

- Golden Path 在干净数据下连续执行 5 次，完整成功 5/5。
- 公开地址可从干净浏览器访问，并准确遵守 Always Latest 与 Specify Version 的版本指针。

#### 2. 稳定性与数据隔离

- 5 次刷新恢复测试中，Project、Session、版本和发布状态恢复 5/5。
- 跨 Project 或 Session 串事件数量为 0。

#### 3. 响应速度与状态可见性

- 创建 Run/Build Job 的 API 在 1 秒内返回标识，接受请求后 2 秒内出现第一条用户可见事件。
- Blueprint 未确认、输入不受支持、配额不足、LLM 失败和构建失败都有明确状态，不产生虚假进度。

#### 4. 用户体验

- 所有可见控件都有真实行为、禁用原因或能力边界。
- 桌面端和移动端不存在阻塞操作的内容或控件重叠。

#### 5. 数据契约与安全

- Export JSON 字段符合约定。
- 导出结果不得包含密钥、凭证、绝对路径、原始对话和内部配额流水。

## 设计理念

### 1. 产品层：先确认目标，再消耗构建资源

自然语言输入可能模糊，也可能超出 V1 能力。Blueprint 把模型理解转成用户可以修改和批准的产品方案；用户确认既是产品决策门，也是创建 Build Job 前的硬约束。

### 2. 协作层：角色必须通过产物交接

Product Manager、Designer、Engineer、QA 的意义不在于展示多个角色名称，而在于逐步收敛不同类型的不确定性：

```text
需求层  Prompt       -> Blueprint      确认要构建什么
设计层  Blueprint    -> VisualSpec     约束如何呈现和交互
工程层  VisualSpec   -> AppSpec        定义构建系统需要生成什么
验证层  Build Result -> QAReview       判断结果是否满足约定
交付层  QAReview     -> ProjectVersion 保存、恢复和发布结果
```

每个交接产物都要通过 Schema 校验、持久化并在界面中可检查。没有产物变化的角色消息不算阶段完成。

### 3. 执行层：模型负责判断，平台掌握权限

LLM 负责需求理解和结构化决策，但不能安装依赖、修改构建命令、执行任意 Shell 或自动发布。Renderer、Build Worker、配额事务和发布服务由平台控制，使真实 LLM 调用不会扩大为任意代码执行。

### 4. 状态层：运行、版本和发布相互分离

一次 Agent Run 失败不应损坏已有版本；一次编辑不应自动改变指定的线上版本；Restore 也不应删除历史。因此 Project、Run、ProjectVersion 和 Publish 指针分别建模，所有变化都能追踪和恢复。

### 5. 演进层：V1 先证明闭环，V2 再增加自治

V1 用固定顺序验证“输入、审批、构建、预览、修改、版本、发布”是否真正可用。V2 沿用相同产物和事件契约，再增加 Leader、独立上下文、动态委派和返工仲裁，避免为了多 Agent 展示提前引入无法验收的复杂度。

## V1 部署与访问架构

这里区分两件事：**开发者把 Another Atom 平台部署到 Railway**；**用户在平台内发布生成应用的某个版本**。前者是平台部署，后者是产品功能。

```text
平台部署链路

开发者 -- git push --> GitHub
                         |
                         v
                  Railway 自动部署
                         |
                         v
              Another Atom 云端服务

用户访问与应用发布链路

用户浏览器 -- HTTPS --> Railway 公网域名
                         |
             +-----------+----------------+
             | React Visual Studio        |
             | FastAPI REST + SSE         |----> OpenAI
             | 固定顺序角色编排            |
             | 异步 Build Worker          |
             | Preview / Published Routes |
             +-----------+----------------+
                         |
                +--------+---------+
                |                  |
                v                  v
          PostgreSQL        Persistent Volume
       用户 / Project /      工作区 / 构建产物
       Session / 配额 /
       Job / Version

用户选择 ProjectVersion -- Publish / Update --> Published Route
                                                    |
                                                    v
                                               稳定公网地址
```

模型不能安装依赖、修改构建命令、直接执行任意 Shell 输入或自动发布。构建由有并发上限的异步 Worker 在固定模板内完成。

## V1 不包含

- Terminal CLI 或本地仓库执行。
- 运行时安装依赖或任意代码执行。
- 任意技术栈和生成式后端。
- 自主或并行的多 Agent 协作（由 V2 实现）。
- 模型选择器。
- 生成应用内部的认证、数据库、交易或支付系统。
- Stripe 付费订阅、Wallet、充值和发票。

## 版本实施计划

### V2：自主多 Agent（计划实施）

V2 是 V1 之后的下一实施版本，不是可选展示方向。它将增加 Leader Agent、独立专业角色上下文、选择性并行、结构化返工、仲裁和 Run 级预算。具体产品范围、部署规格和量化验收将在 V2 开发前补齐；角色与编排基线见 [V2 角色与编排设计](./docs/v2/role-orchestration-design.md)。

### 未归属版本：本地 Agent Runtime

类似 Claude Code 的本地 Runtime 可以在后续操作本地文件、Git、Shell、npm 和 localhost Visual Studio。该方向尚未实现，也尚未确定归属版本。

## 项目状态

已完成：

- [x] Atoms 公开功能分析
- [x] V1 产品需求和验收标准
- [x] V1 架构与部署设计
- [x] V2 角色与编排设计
- [x] 笔试提交说明和双语文档

尚未完成：

- [ ] V1 React Visual Studio、FastAPI、LLM、Renderer、Build Worker 和持久化
- [ ] V1 自动化测试、Railway 部署和公开在线地址
- [ ] V2 完整 PRD、技术设计、部署规格和验收基线
- [ ] V2 自主多 Agent 实现、测试和部署

## 相关链接

- 源代码仓库：[github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- 在线版本：尚未部署
- [V1 产品需求](./docs/v1/another-atom-v1-prd.md)
- [V1 架构设计](./docs/v1/architecture-design.md)
- [V1 笔试提交说明](./docs/v1/submission-note.md)
- [V2 实施规划](./docs/v2/overview.md)
- [V2 角色与编排设计](./docs/v2/role-orchestration-design.md)
- [Atoms 参考分析](./docs/reference/atoms-reference-analysis.md)

## 附录

- 原版产品参考：[Atoms](https://atoms.dev/)
