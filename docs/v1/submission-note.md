# Another Atom 笔试提交说明

[toc]

- 文档状态：随项目进度持续更新
- 更新日期：2026-07-11
- GitHub 源代码：[eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- 在线 Demo：尚未部署，完成后在此处和笔试结果回收文档中补充

## 1. 项目目标

Another Atom V1 要完成一个可公开测试的 AI 应用生成 Demo：用户输入产品需求，真实 LLM 生成可编辑 Blueprint 与 AppSpec，受控构建系统将其转换为可交互 React 应用，用户可以预览、修改、保存版本并显式发布。

本版本只交付 Railway Cloud Demo。类似 Claude Code 的 Terminal CLI、本地 Agent Runtime 和本地仓库执行不属于 V1 完成范围。

## 2. 实现思路与关键取舍

### 2.1 真实 LLM，但不开放任意代码执行

V1 真实调用 LLM 生成 Blueprint、VisualSpec 和 AppSpec，不用预设文本冒充 AI 结果；但模型不直接生成并执行 Shell 命令，也不能修改依赖。

```text
Natural-language Prompt
        ↓
Editable Blueprint
        ↓
Validated AppSpec
        ↓
Deterministic Renderer
        ↓
Fixed React Template
        ↓
Runnable Preview
```

这样选择的原因是：笔试需要证明 AI 理解与产品闭环，同时又必须在共享云容器中控制安全和稳定性。

优势：生成结果真实受 LLM 输入影响，且构建范围可以验证。

代价：不能声称支持任意技术栈或任意代码生成。

适用边界：适合验证从需求到可运行应用的主链路，不用于证明通用 Coding Agent 能力。

### 2.2 Cloud Demo 是唯一 P0 执行面

V1 的 Agent、PostgreSQL、工作区、构建和发布全部运行在 Railway。浏览器 Visual Studio 是唯一 P0 用户入口。

没有同时实现 Local Mode，原因是本地模式还需要解决 Python/Node 安装、权限审批、端口管理、SQLite 同步和本地项目发布协议；这些工作不会直接提高本次在线 Demo 的验收完整度。

优势：只维护一套 Session、Preview、持久化和 Publish 链路。

代价：V1 还不能操作用户本地仓库，也不具备 Claude Code 式本地执行。

适用边界：满足公开在线验收；长期产品需要在 P1 增加本地 Runtime。

### 2.3 异步构建与受控模板

模型输出 AppSpec 后，API 创建持久化 Build Job 并立即返回；后台 Worker 使用固定模板、固定依赖和固定命令执行构建。

- 运行时不执行 `npm install`。
- 不允许模型修改 `package.json`。
- 初始构建并发为 1。
- Build Job 使用 PostgreSQL lease，服务重启后可以恢复。
- 构建耗时、内存和超时阈值在目标 Railway 规格上压测后确定。

这个取舍牺牲了自由度，但避免将长时间构建放在 HTTP 请求链路中，也避免共享容器直接运行用户生成命令。

### 2.4 平台配额真实执行，支付暂不接入

不同用户可以拥有多个 Session，但同一账户下的 Session 共享 Plan 和 Quota Account。每次 LLM 请求先事务性预占配额，再按实际 token 结算并释放剩余额度。

V1 不接 Stripe、Wallet、充值或发票。Subscription 状态由种子数据或管理操作设置，避免把支付接入与核心生成链路混在一起。

## 3. 创新性

### 3.1 核心创新：Blueprint 驱动的受控生成链路

本项目的创新点不是“使用了 LLM”或“显示多个 Agent 角色”，而是把不可控的聊天生成转换成一条可编辑、可校验、可追踪的生产链路：

```text
用户意图
   ↓
Blueprint：用户可编辑和审批的产品契约
   ↓
AppSpec：机器可校验的应用契约
   ↓
Renderer：确定性执行边界
   ↓
ProjectVersion：可恢复、可比较的结果
```

这一设计解决的是生成式产品中的控制问题：用户不是等模型直接给出不可解释结果，而是在关键语义层确认“要构建什么”，系统再在明确边界内执行。

优势：需求确认、生成执行和最终产物之间存在可验证因果关系。

代价：需要设计和维护 Blueprint/AppSpec schema，首版生成范围比自由代码生成更窄。

适用边界：这是产品与系统设计创新，不是新模型、新算法或通用代码生成能力。

### 3.2 固定角色接力，而不是多 Agent 表演

Product Manager、Designer、Engineer、QA 是独立 instruction 与结构化输出的角色 Agent，但由平台按固定顺序编排。每个阶段必须绑定实际产物：

- Product Manager -> Blueprint
- Designer -> VisualSpec
- Engineer -> AppSpec + BuildJob
- QA -> ValidationReport

V1 不动态委派、不并行执行、不进行 Agent 间自由讨论。前端标注“分阶段接力”，评审者可以直接检查每个阶段是否改变了后续状态，避免用角色头像和进度动画替代真实执行。

### 3.3 版本化发布闭环

生成结果不是一次性 Preview。Build、Edit、Resolve 和 Restore 都形成 ProjectVersion；Publish 必须由用户选择明确版本触发，Agent 不会自动发布。

这使产品验证对象从“模型是否生成了一个页面”提升为“用户是否能持续控制一个在线产品”。

### 3.4 可扩展潜力

Blueprint/AppSpec 把模型推理与执行环境隔离后，可以在不改用户流程的前提下扩展：

1. 增加不同 Renderer，支持更多应用类型。
2. 将固定模板执行迁移到独立容器沙箱。
3. 增加本地 Agent Runtime，使同一协议可以驱动用户本地仓库。
4. 增加多模型 Provider，但保持 Blueprint/AppSpec Contract 不变。

这些是协议带来的扩展路径，不代表 V1 已经实现。

## 4. 当前完成程度

截至 2026-07-11：

### 4.1 已完成

- Atoms 官方公开功能分析。
- Another Atom V1 产品范围和验收标准。
- Cloud Demo 架构、数据模型、配额事务、安全边界和错误契约。
- 英文默认 README、中文 README 和文档目录。
- GitHub 公开仓库。

### 4.2 尚未完成

- React Visual Studio 实现。
- FastAPI、PostgreSQL 和数据库 migration。
- 真实 LLM 与结构化输出接入。
- Deterministic Renderer 和固定 React 模板。
- 异步 Build Worker、Preview 和版本管理。
- 用户认证、Session、配额与 Usage Ledger 实现。
- Railway 部署和在线 Demo URL。
- 自动化测试、资源压测和部署恢复验证。

本文档不能作为“功能已经完成”的证明。完成状态将在代码、测试和部署实际落地后更新。

## 5. 继续投入时的扩展与优先级

### Priority 0：完成可验收 Cloud 纵切

- Prompt -> Blueprint -> Approval -> AppSpec。
- 异步 Build -> Preview -> Follow-up 修改。
- Session、配额、版本和 Publish。
- Railway 部署、公开 URL 和基本自动化验证。

原因：这些能力共同决定本次 Demo 是否可运行、可测试和可交付。

### Priority 1：CC 式 Terminal 与本地 Agent Runtime

- Terminal CLI。
- 本地文件、Git、Shell 和 npm 工具。
- SQLite Session 与项目索引。
- localhost Visual Studio 和 Dev Server。
- 本地项目上传、同步或发布到云端的协议。

原因：这是 Another Atom 从在线生成 Demo 走向长期开发工具的核心扩展，但不是本次在线验收的必要条件。

### Priority 2：V2 自主多 Agent

- Supervisor 动态拆解和委派任务。
- Agent 独立上下文和工具权限。
- 并行执行、反馈循环、冲突处理和结果合并。
- Agent 级预算、超时和终止条件。

原因：V1 固定角色接力先验证阶段 Contract；只有 Contract 和可观测性稳定后，自主编排才有可检查的输入、输出和成本边界。

### Priority 3：隔离执行与更自由的生成

- 每次运行独立容器或虚拟机。
- 动态依赖、受控网络和任意项目文件。
- 更完整的代码 diff、测试和 Git 工作流。

原因：只有建立运行级隔离后，才能安全放宽固定模板和命令允许列表。

### Priority 4：平台商业化与外部集成

- Stripe 订阅与支付。
- Supabase、GitHub 和 Analytics 集成。
- 多模型 Provider 和模型选择。
- 团队 Workspace、权限和协作。

原因：这些能力依赖稳定的核心生成和执行链路，提前接入会增加外部系统成本，但不能证明主产品成立。

## 6. 与评估维度的对应

| 评估维度 | 本项目提供的检查证据 |
| --- | --- |
| 完成度 | Golden Path、真实持久化、公开 Preview/Publish 和部署恢复测试 |
| 工程思维 | Cloud 单执行面、结构化 Contract、异步 Build、配额事务和受控执行 |
| 用户体验 | Blueprint 审批、实时事件、可交互 Preview、版本恢复和明确错误状态 |
| 创新性 | Blueprint/AppSpec/Renderer 受控生成链路、固定角色接力、阶段产物和版本化发布 |
| 可交付性 | GitHub 仓库、双语 README、Railway 在线地址、完成/未完成清单 |

## 7. 最终提交前检查

- 在本文和笔试结果回收文档中填写在线 Demo URL。
- 确认 GitHub 仓库为 public。
- 使用干净浏览器验证在线 Demo。
- 更新当前完成程度，不把未实现能力保留为已完成描述。
- 写明演示账号要求；若不需要账号，明确标注。
- 记录已知边界、失败场景和资源限制。
