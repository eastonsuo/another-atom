# Another Atom V2 产品需求文档

[toc]

- 文档状态：V2 产品实施基线草案；V1 验收完成后进入开发
- 更新日期：2026-07-11
- V1 产品基线：[Another Atom V1 产品需求文档](../v1/another-atom-v1-prd.md)
- V2 Agent 设计：[Another Atom V2 Agent 设计](./agent-design.md)
- V2 工程架构：[Another Atom V2 架构设计](./architecture-design.md)

## 1. 版本结论

V2 在 V1 可部署闭环上实现**受 Runtime 约束的自主多 Agent 协作**：Leader 根据用户目标和现有 Artifact 提出 TaskGraph，Product Manager、Architect、Designer、Engineer、QA 使用独立 Context 完成任务，通过 Handoff 交付；Engineer/QA 可以在 Run 级 Sandbox 内申请受控 Tool，失败时依据 Evidence 进行有预算的返工与收敛。

```text
V1: 固定顺序角色 Pipeline
Product Manager -> Designer -> Engineer -> QA

V2: Runtime 约束的自主多 Agent
User -> Blueprint Approval -> Leader / TaskGraph
                              |
             +----------------+----------------+
             v                v                v
         Architect         Designer        Engineer <-> QA
             |                |                |
             +------ Artifact / Handoff -------+
                              |
                       Version / Publish
```

V2 是计划实施版本，不是已经完成的能力。实施顺序固定为 V1 -> V2。

## 2. 要解决的问题

V1 的固定 Pipeline 适合验证闭环，但存在明确边界：

- 所有 Team Mode 请求都按同一顺序执行，无法根据任务复杂度调整角色和依赖。
- Agent 只产生结构化 Contract，没有文件、构建、测试和浏览器 Tool，无法处理更真实的实现与修复任务。
- 自动修复最多一轮，只能回到 Engineer，无法把规格、视觉或需求根因路由给责任角色。
- 所有角色按顺序运行，Architect/Designer 等无依赖任务也不能并行。
- V1 只有阶段级 Context，无法验证独立 Agent 的 Handoff、拒收、仲裁和预算治理。

V2 需要增加自主性，但必须保留 V1 已证明有效的 Blueprint 审批、Artifact Contract、确定性 Validator、版本历史和用户显式 Publish。

## 3. 产品目标

### 3.1 要验证的判断

1. Leader 生成的 TaskGraph 是否能比固定 Pipeline 更准确地匹配任务复杂度。
2. 独立 Context + Handoff 是否能让角色交付可检查，而不是退化为多 Agent 聊天。
3. 受控 Tool + Run 级 Sandbox 是否能提高真实实现和修复能力，同时维持隔离边界。
4. Evidence 驱动的 Rework/Arbitration 是否能在预算内收敛，而不是无限返工。
5. 并行分支、配额、部分失败和恢复是否能形成可交付的多用户系统。

### 3.2 不在 V2 P0 验证的判断

- 不默认扩展到任意应用类型。V2 P0 继续使用 V1 商品目录站作为回归和验收基线。
- 不把 CC 式本地 Agent Runtime 自动并入 V2；是否同版本交付需单独确认。
- 不实现无人审批的任意代码执行、外部依赖安装或开放网络访问。
- 不实现 Agent 自动 Publish、自动提高预算或绕过用户确认。
- 不展示模型私有 Chain of Thought。

## 4. 用户与核心价值

### 4.1 目标用户

- 需要把产品需求变成可运行网页应用，并希望检查规划、设计、实现和测试依据的用户。
- 需要在版本、预算和发布边界内持续修改，而不是只生成一次页面的用户。
- 需要验证真实多 Agent 协作、Tool 使用、返工和工程治理的评审者或开发者。

### 4.2 V2 相对 V1 的用户价值

| V1 | V2 用户可感知变化 |
| --- | --- |
| 固定角色时间线 | 可查看由真实依赖生成的 TaskGraph、并行分支和当前责任角色 |
| 阶段顺序交接 | 每次 Handoff 有 Artifact、Evidence、接受/拒绝和原因 |
| 固定模板构建 | Engineer 在隔离环境中执行受控文件、构建和测试 Tool |
| 一轮 Engineer 修复 | 问题按需求/架构/视觉/实现根因路由，并在预算内返工 |
| 单阶段配额 | 显示 Run 总预算、子任务消耗、剩余预算和停止原因 |

## 5. 产品原则

1. **自主不等于越权**：Agent 提建议和 ToolRequest，Runtime 执行权限、配额、并发和状态硬规则。
2. **交付物优先**：没有 Artifact/Evidence 的 Agent 消息不构成阶段完成。
3. **用户门禁继承 V1**：Blueprint、范围变更、越权 Tool、预算追加、破坏性操作和 Publish 必须由用户确认。
4. **确定性验收优先**：QA Agent 不能覆盖 Build/Test/Validation 的 mandatory 结果。
5. **有预算地收敛**：每个 Run 有调用、token、时间、并发和 Artifact 修订上限。
6. **V1 可回归**：V2 的数据、事件和 UI 扩展不能破坏 V1 ProjectVersion、Publish 和公开 URL 语义。

## 6. P0 功能范围

### 6.1 Autonomous Team Mode

- V2 新增 Autonomous Team Mode；V1 Engineer Mode 和 Sequential Team Mode 可作为对照与降级路径保留。
- 用户提交 Prompt 后仍先生成 Blueprint；没有用户确认不能创建执行 TaskGraph。
- Leader 基于已确认 Blueprint 生成 TaskGraph，Runtime 校验依赖、角色、预算和允许的并行组。
- TaskGraph 必须可视化，显示节点、依赖、状态、Agent、Artifact 和 Evidence，不展示私有推理。

### 6.2 Leader 与专业角色

- Leader 负责 TaskGraph、分派、Handoff 检查、回退路由和仲裁建议，不直接使用文件/Shell/Publish Tool。
- Product Manager 管理需求澄清和 Blueprint 范围。
- Architect 新增 ArchitectureSpec、数据 Contract 和可行性判断。
- Designer 负责 VisualSpec 与 InteractionSpec，不并入 Architect。
- Engineer 在 Sandbox 内执行 ImplementationPlan、文件修改、Build 和 Test Tool。
- QA 基于只读快照和确定性 Evidence 设计检查、解释失败并提出 ReworkRequest。

### 6.3 Context 与 Handoff

- 每个 Agent 使用独立 Context，只接收当前 Task 所需的 Artifact、Evidence、Tool Observation 和预算摘要。
- 角色之间只能通过 Handoff Package 交接，不共享隐藏长期记忆或原始 Chain of Thought。
- 接收方可以 Accept 或 Reject；Reject 必须包含 Contract violation、Evidence 和建议责任角色。
- Artifact 不原地覆盖，返工产生新版本并保留 parent/correlation 关系。

### 6.4 ToolRequest 与 Sandbox

- Agent 不直接执行工具，只提交结构化 ToolRequest；Runtime 校验角色权限、参数、预算、网络策略和 Sandbox。
- Engineer P0 Tool：`list_files`、`read_file`、`apply_patch`、`run_build`、`run_tests`、`request_dependency`。
- QA P0 Tool：`inspect_artifact`、`run_tests`、`browser_check`、`capture_screenshot`，默认只读。
- 每个 Engineer Task 使用独立可写快照；QA 使用对应快照的只读副本；多个 Agent 不能并发写同一目录。
- 超出 allowlist 的依赖、网络或写入范围必须等待用户确认。

### 6.5 选择性并行

- Runtime 只并行执行 TaskGraph 中无依赖冲突、无共享写入且预算已预占的节点。
- 第一条并行路径限定为 ArchitectureSpec 与 VisualSpec 中已被 Runtime 判定无数据依赖的子任务。
- UI 显示并行分支、各自状态、消耗和 Handoff；不能用同时闪动角色头像伪装并行。
- 任一分支失败不自动回滚已成功分支的 LLM 用量或 Artifact；失败分支按策略重试、降级或请求用户。

### 6.6 Rework、Arbitration 与收敛

- QA/下游角色基于 Evidence 生成 ReworkRequest，Runtime 按 root cause 路由给责任角色。
- Agent 不能点对点私聊；所有请求通过 Runtime 和持久化 Handoff。
- Leader 可以提出 ArbitrationDecision，Runtime 校验 Blueprint、权限和预算后执行。
- 达到 Artifact 修订、Agent 调用、token、时间或相同 Evidence 重复上限后停止，保留最近可用 Version。
- 需要改变 Blueprint 范围、追加预算或越权 Tool 时必须进入 Human-in-the-loop。

### 6.7 预算、配额与部分失败

- 每个 Run 在执行前创建 RunBudget，包含调用、token、deadline 和并发上限。
- 并行分支启动前，父 Run 原子预留可覆盖所有子任务的额度，再分配子预算。
- 子任务成功后按实际用量结算；失败/取消只释放未使用预留，已经发生的 Provider/Tool 用量不能回滚。
- 一支成功、一支失败时，成功 Artifact 保留为可复用输入；Leader/Runtime 决定重试失败分支、取消未启动分支或请求用户。
- UI 展示预算消耗和停止原因，但不展示内部价格推理或模型 Chain of Thought。

### 6.8 QA、版本与发布

- mandatory Build/Test/Validation Evidence 仍由确定性系统产生，QA Agent 不能改写。
- QAReview 提供用户可读摘要、Evidence 链接、warning 和 Rework 建议。
- 合并到 ProjectVersion 前，候选 Artifact 必须通过 Contract、Build、Test、安全和 mandatory checks。
- Restore、版本指针、Always Latest/Specify Version 与 V1 保持兼容。
- Publish/Update/Unpublish 仍由用户显式操作，Leader 和 Specialist 都不能自动发布。

## 7. 核心用户旅程

### 7.1 正常路径

1. 用户选择 Autonomous Team Mode，输入 Mono Market Prompt 并确认 Blueprint。
2. Leader 提交 TaskGraph，Runtime 校验后展示任务与预算。
3. Architect 与 Designer 在允许条件下并行，分别交付 ArchitectureSpec 与 VisualSpec。
4. Engineer 接收已接受的 Handoff，在 Sandbox 内修改、构建和测试。
5. QA 在只读快照上检查并交付 QAReview。
6. mandatory checks 通过后生成 ProjectVersion，用户预览并显式 Publish。

### 7.2 返工路径

1. QA Evidence 指向 implementation failure，生成 ReworkRequest。
2. Runtime 校验 root cause 和预算，路由给 Engineer。
3. Engineer 基于原 Artifact 新建修订，重新 Build/Test。
4. QA 复验；成功则合并，达到预算则停止并请求用户。

### 7.3 Human-in-the-loop 路径

出现以下任一情况时暂停：Blueprint/范围变化、越权依赖或网络、追加预算、无法仲裁冲突、Restore/Unpublish/Publish。用户批准只绑定精确 Artifact/ToolRequest/Budget version；对象变化后旧批准失效。

## 8. 工作区与界面

V2 在 V1 Studio 上增加：

- TaskGraph：任务依赖、并行分支、当前 Agent 和状态。
- Agent Inspector：role、Task、输入/输出 Artifact、ToolRequest、Usage 和 Trace 摘要。
- Handoff Panel：Accept/Reject、Contract violation 和 Evidence。
- Evidence Panel：Build/Test/Browser/Screenshot 结果，不展示 Chain of Thought。
- Approval Center：范围、Tool、预算和发布等待项。
- Budget Bar：已预留、已结算、剩余和停止原因。
- Rework/Arbitration Timeline：返工来源、责任角色、版本差异和 Leader 建议。

移动端不同时展开 TaskGraph、Inspector 和 Preview，使用单区域切换，避免压缩成不可操作的桌面布局。

## 9. 状态模型

```text
Run
Created -> AwaitingBlueprintApproval -> Planning -> Running
                                               |       |
                                               |       +-> AwaitingApproval
                                               |       +-> Reworking
                                               |       +-> PartiallyFailed
                                               v
                                          Validating -> Completed
                                               |
                                               `-> Failed / BudgetExhausted / Cancelled

Task
Pending -> Ready -> Reserved -> Running -> Completed
                    |            |          |
                    v            v          `-> ReworkRequested
                 Cancelled     Failed

Handoff
Created -> Delivered -> Accepted
                    `-> Rejected -> ReworkRequested
```

## 10. P1 候选范围

- 扩展到更多应用类型和对应 Capability Policy/Renderer。
- 多候选实现竞速与自动选择。
- 用户可配置模型 Provider 和每角色模型。
- 更复杂的并行图和多 Engineer 分支合并。
- 视觉截图自动评分和可访问性深度测试。
- CC 式本地 Runtime 与云端 TaskGraph 协同。
- 团队成员审批、评论和共享预算。

这些能力不阻塞 V2 P0，多应用类型和 Local Runtime 必须单独确认产品与安全边界。

## 11. 明确不做

- 不允许 Leader 或 Specialist 绕过 Runtime 直接执行宿主机 Shell、数据库或 Publish。
- 不在没有 Run 级隔离时执行模型或用户提供的任意代码。
- 不共享 Agent 私有 Chain of Thought，不用聊天瀑布替代 Artifact/Evidence。
- 不自动扩大 Blueprint 范围、追加预算、批准依赖或开放网络。
- 不承诺无限返工、无限 Context 或无限并发。
- 不把 V2 P0 描述为任意应用、任意技术栈的通用 Coding Agent。

## 12. 验收标准

### 12.1 功能验收

- V1 Golden Path、版本和发布策略回归通过。
- Autonomous Team Mode 真实生成并持久化 TaskGraph、Task、Artifact、Handoff、ToolRequest、Evidence 和 RunBudget。
- 至少一条无依赖分支真实并行执行，并能从事件时间与独立 Task 状态验证。
- 至少一条 Evidence 驱动 Rework 路径能路由、修订、重建、复验并收敛。
- Blueprint、范围、越权 Tool、预算追加和 Publish 的 Human-in-the-loop 均不能被 Agent 绕过。
- mandatory failure 不能被 QAReview 或 LeaderDecision 改写为通过。
- Publish 只接受已通过门禁的 ProjectVersion 和用户显式请求。

### 12.2 工程与隔离验收

- 并行分支配额预占原子执行，账户和父 Run 超额结算数量为 0。
- 部分失败时，已发生用量正确结算、未使用预留正确释放、成功 Artifact 不被误删。
- Sandbox 跨用户、跨 Project、跨 Task 的文件、Secret、网络策略和 ToolResult 泄漏数量为 0。
- 多 Agent 不共享可写工作区；冲突合并只能通过 Artifact/Patch 和 Runtime。
- 服务重启后 TaskGraph、pending Approval、Handoff、ToolRequest、预算和事件可以恢复。
- Sandbox 超时、取消或失败后被销毁，Artifact/Evidence 和资源记录仍可审计。

### 12.3 重复运行基线

- V2 Golden Path 在干净数据下连续完成 5/5。
- 预期 Task/Agent/Handoff/Tool 事件关联完整率为 100%。
- 跨 Project/Run/Agent Context 串线数量为 0。
- 达到预算或收敛上限后继续调用模型/Tool 的数量为 0。

## 13. 产品事件与价值判断

V2 在 V1 漏斗上新增：

```text
task_graph_approved
parallel_branch_started
handoff_accepted
handoff_rejected
tool_request_executed
rework_started
rework_converged
arbitration_requested
budget_exhausted
```

没有真实样本前不预设“并行更快”或“多 Agent 成功率更高”。必须先采集总完成时间、串行/并行资源消耗、Handoff 拒绝率、Rework 收敛率、每个成功 Version 的调用/token/Tool 成本，再判断 V2 是否优于 V1。

## 14. 风险与取舍

- 多 Agent 可能增加成本而不提高结果质量；必须用 Artifact/Evidence 和 V1 对照验证。
- 并行缩短墙钟时间，但会增加配额事务、部分失败和资源峰值复杂度。
- Tool 提高实现能力，同时扩大文件、依赖、网络和 Secret 风险；Run 级 Sandbox 是上线前置条件。
- Leader 可能成为新的单点推理瓶颈；Runtime 必须能拒绝无效 TaskGraph 并提供确定性降级。
- Context/Handoff 过度压缩会丢信息，过度传递又会导致成本和污染；必须记录 Artifact 版本和 Evidence。

## 15. 开发前待确认

- 具体模型供应商、Agent SDK 和 Prompt 版本策略。
- Run 级 Sandbox 采用容器、MicroVM 还是远程 Sandbox 服务。
- 网络 allowlist、依赖白名单和 Secret Broker 实现。
- 各 Agent/Artifact 修订、总调用、token、并发和 deadline 的压测上限。
- QA 是否在 P0 使用视觉截图评估，以及对应测试集。
- V2 是否扩展商品目录站以外的应用类型。
- V2 是否与 CC 式 Local Runtime 同版本交付。
