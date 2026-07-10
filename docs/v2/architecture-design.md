# Another Atom V2 架构设计

[toc]

- 文档状态：V2 工程实施基线草案；V1 验收完成后进入开发
- 更新日期：2026-07-11
- 产品文档：[Another Atom V2 产品需求文档](./another-atom-v2-prd.md)
- Agent 设计：[Another Atom V2 Agent 设计](./agent-design.md)
- V1 架构基线：[Another Atom V1 架构设计](../v1/architecture-design.md)

## 1. 技术选型

V2 延续 V1 的 React/FastAPI/PostgreSQL Contract，但将 Web、Agent Worker、Tool/Sandbox 和 Artifact Storage 拆成明确边界。

| 层次 | V2 选型 | 原因与边界 |
| --- | --- | --- |
| Studio | React + TypeScript + Vite | 复用 V1 Studio、OpenAPI 类型和 SSE；增加 TaskGraph、Handoff、Tool、Budget UI |
| API/Control Plane | Python + FastAPI + Pydantic + Uvicorn | 负责身份、HITL、TaskGraph 命令、状态查询和事件入口；不运行 Agent/Build 重任务 |
| Agent Runtime | OpenAI Agents SDK 作为首个 Agent Adapter + Pydantic Structured Output | 单 Agent 调用继续使用 SDK；TaskGraph、预算、权限和状态由自有 Runtime 管理，避免绑定框架内部状态 |
| Durable Scheduler | PostgreSQL Task/Lease + 独立 Agent Worker Service | V2 初期不额外引入消息队列；Task、lease、预算和幂等在同一事务边界内 |
| 数据库 | PostgreSQL + SQLAlchemy + Alembic | 保存 TaskGraph、Artifact、Approval、Handoff、ToolRequest、SandboxRun、Budget 和 Ledger |
| Artifact Storage | S3-compatible Object Storage | 多 Worker 共享不可变输入、Patch、BuildArtifact、Evidence 和发布快照；不依赖单实例 Volume |
| Tool Gateway | Pydantic ToolRequest/ToolResult + Role Policy | Agent 只能请求 Tool；Gateway 统一校验权限、预算、参数、网络和 Sandbox |
| Sandbox | `SandboxProvider` 接口，Run/Task 级容器、MicroVM 或远程 Sandbox | 具体 Provider 开发前通过 ADR 确认；未满足隔离语义不得开放写文件、依赖、网络和执行 Tool |
| 前端事件 | REST + SSE + OpenAPI | 沿用 V1 `Last-Event-ID` 恢复；增加 agent/handoff/tool/rework/arbitration/budget 事件 |
| 部署 | Railway Web Service + Agent Worker Service + PostgreSQL + Object Storage + Sandbox Provider | Web 与 CPU/内存尖峰型 Agent/Build 隔离；Sandbox 可为外部受控服务 |

### 1.1 选型原则

1. **Runtime 是最终控制面**：Leader、Specialist 和 Agent SDK 都不能绕过状态、预算、权限和 HITL。
2. **持久化先于调度**：Task、Reservation、ToolRequest、Handoff 和 Event 先落 PostgreSQL，再执行副作用。
3. **不可变 Artifact 交接**：Agent 不共享可写目录，通过 Object Storage Artifact/Patch/Evidence 协作。
4. **隔离先于权限**：Sandbox 未达到要求时，不通过功能开关逐项放宽 V1 共享容器。
5. **V1 Contract 向后兼容**：Project、Version、Publish、Approval 和基础事件继续可读。

## 2. 总体架构

```text
User Browser
     |
     | REST + SSE
     v
Railway Web Service
React Studio + FastAPI Control Plane
     |
     +-------- PostgreSQL -----------------------------------+
     |         TaskGraph / Task / Approval / Budget / Event  |
     |                                                       |
     +----> Orchestrator Runtime                              |
                |                                            |
                | lease ready Task                           |
                v                                            |
       Railway Agent Worker Service                          |
                |                                            |
                +---- Agent Adapter ----> OpenAI / LLM       |
                |                                            |
                +---- Tool Gateway                           |
                          |                                  |
                          v                                  |
                   Sandbox Provider                          |
                   isolated Task workspace                   |
                          |                                  |
                          v                                  |
              Build / Test / Browser Evidence                |
                          |                                  |
                          v                                  |
                 S3-compatible Object Storage <--------------+
                 Artifact / Patch / Evidence / Published App
```

V2 不在 Web Service 内执行 Agent、Build 或 Browser Tool。Web 只处理短请求、SSE 和状态查询；Agent Worker 负责模型调用和 Task 生命周期；Sandbox 执行不可信程度更高的文件与构建操作。

## 3. 组件职责

### 3.1 FastAPI Control Plane

- 身份、Project、Run、Approval、Version 和 Publish API。
- 创建 RunBudget 和初始 TaskGraph 请求。
- 接收用户审批、取消、预算追加和发布命令。
- 通过 SSE 推送持久化状态，不执行 Agent 或 Sandbox Tool。

### 3.2 Orchestrator Runtime

- 校验 Leader 提交的 TaskGraph 和 LeaderDecision。
- 计算 ready Task、依赖、并发组和责任 Agent。
- 在派发前完成预算预占、权限与 HITL 检查。
- 处理 Handoff、Rework、Arbitration、取消和收敛。
- Runtime 使用确定性规则写状态；Leader 不能直接更新数据库状态。

### 3.3 Agent Worker

- 通过 PostgreSQL lease 领取 ready AgentTask。
- 组装最小 Context，调用角色 Agent，校验结构化输出。
- 持久化 AgentRun/Artifact/Usage/Trace，再提交 Handoff 或 ToolRequest。
- Worker 崩溃后只重新领取 lease 过期且副作用可幂等恢复的 Task。

### 3.4 Tool Gateway

- 校验 Agent role、Task、Project、Tool schema、Capability、Budget 和 idempotency key。
- 决定直接拒绝、等待用户审批或在 Sandbox 中执行。
- 将 ToolResult 转成不可变 Evidence/Artifact，不把宿主机句柄暴露给 Agent。

### 3.5 Sandbox Manager

- 从 Base Artifact/Image 创建 Task 级可写快照。
- 应用 CPU、内存、磁盘、进程、时间、网络和 Secret 策略。
- 执行 allowlisted 文件、Build、Test、Browser Tool。
- 产出 Patch、BuildArtifact、Evidence 和资源计量后销毁环境。

### 3.6 Artifact Service

- PostgreSQL 保存 Artifact 元数据、hash、schema、parent/correlation 和对象 key。
- Object Storage 保存不可变内容；数据库不保存绝对本地路径。
- 合并前验证 hash、来源 Task、Sandbox 和 mandatory Evidence。
- 发布快照与构建中间产物使用不同生命周期策略。

## 4. TaskGraph 与调度

TaskGraph 由 Leader 建议、Runtime 校验并持久化：

```text
Blueprint approved
      |
      v
Leader -> TaskGraphProposal
      |
      v
Runtime validates
role / dependency / cycle / budget / policy / HITL
      |
      v
Persist TaskGraph + Tasks
      |
      v
Scheduler selects Ready Tasks
      |
      +-- reserve budget
      +-- acquire concurrency slot
      `-- create lease
```

调度约束：

- TaskGraph 必须是无环图；Runtime 拒绝环和未知角色。
- Task 只有在依赖 Artifact 已 Accepted、预算已预占、Approval 有效时进入 Ready。
- 同一 Sandbox/Artifact 基线最多一个写 Task；只读任务可以并行。
- 并行组受账户、Run、角色、Worker 和 Sandbox 并发上限共同约束。
- Task lease、attempt 和 idempotency key 防止重复执行；成功副作用不能因 Worker 重领而执行两次。

## 5. 并行配额与部分失败

### 5.1 事务边界

并行分支不能各自独立读取“剩余额度”后再调用。Runtime 在派发 ready group 前执行：

```text
BEGIN
  lock quota_account + run_budget
  verify parent remaining budget
  create child reservations for every branch
  decrement parent available reservation
  mark Tasks Reserved
COMMIT
```

- 任一子预算无法预留时，整个 ready group 不启动；Runtime 可以缩小并行组或请求用户追加预算。
- 每个 Provider/Tool 调用从所属 child reservation 结算，不跨 Task 借用。
- 成功 Task 结算实际用量并释放剩余预留。
- 失败/取消 Task 结算已经发生的用量，只释放未使用预留；真实用量不能回滚。
- 父 Run 的 `reserved + settled + available` 必须在事务后守恒。

### 5.2 部分失败补偿

```text
Branch A completed -> Artifact A accepted
Branch B failed
       |
       +-- retry B within child budget
       +-- cancel not-started dependents and release reservations
       +-- use accepted A in revised TaskGraph
       `-- request user budget/scope decision
```

V2 不做“数据库回滚式”撤销成功 Agent 成本或 Artifact。补偿语义是取消未开始副作用、释放未用预算、保留成功 Artifact、为失败分支创建新 attempt，并让 Runtime/Leader 决定后续图。

必须先通过以下测试才能开启并行：

- 同账户多 Run 并发预占不透支。
- 同 Run 多分支原子预留，不出现只启动一半但无状态记录。
- 一支成功一支失败时，用量、Artifact 和依赖 Task 状态正确。
- Cancel、deadline、Worker crash 和 Sandbox crash 后未用预算正确释放。
- 重放同一 idempotency key 不产生重复 Provider/Tool 结算。

## 6. Artifact、Handoff 与合并

### 6.1 Handoff Package

```text
handoff_id
from_task / from_agent
to_task / to_agent
artifact_refs[]
evidence_refs[]
contract_version
content_hashes[]
status: delivered | accepted | rejected
rejection_reason
correlation_id
```

- 接收方 Accept 后，Artifact 才能满足下游 Task 依赖。
- Reject 只创建 ReworkRequest，不修改或删除上游 Artifact。
- Runtime 验证 schema、hash、Project/Run 归属和 Agent role。

### 6.2 写入与合并

- Engineer Task 从指定 Base Artifact 创建独立 Sandbox 快照。
- ToolResult 形成 PatchArtifact，不直接写主 ProjectVersion。
- 多分支合并由 Runtime 创建 Merge Task；冲突必须产生 Evidence 并路由 Engineer/Leader。
- 合并候选通过 Build/Test/Security/Validation 后，才创建新的 ProjectVersion。

## 7. Tool Gateway 与 Sandbox

### 7.1 Tool 执行链路

```text
Agent -> ToolRequest -> Policy Check
                       |-- deny -> ToolResult(error)
                       |-- approval required -> pending Approval
                       `-- allow -> Sandbox execution
                                      |
                                      v
                              ToolResult + Evidence
```

Policy 输入包括 Agent role、Task type、Project owner、Tool schema、目标路径、Capability、依赖、网络域名、预算和 Sandbox 状态。Policy 决定不能由 Leader 覆盖。

### 7.2 Sandbox 生命周期

```text
Requested -> Provisioning -> Ready -> Running -> Collecting -> Destroyed
                      |          |          |
                      `-> Failed `-> TimedOut/Cancelled
```

- Sandbox 使用随机 ID，不暴露宿主机路径。
- 默认无网络、无平台数据库凭证、无长期 Secret。
- Secret 由 Gateway 按 Tool 临时注入，Tool 完成后撤销。
- QA 只读快照不能申请写 Tool。
- Sandbox 销毁失败是平台安全错误，阻止同 Worker 继续领取新任务并触发告警。

### 7.3 Provider 决策门

V2 技术设计必须通过 ADR 选择容器、MicroVM 或远程 Sandbox Provider，并验证：启动延迟、隔离级别、网络策略、资源限制、文件快照、日志脱敏、销毁可靠性和 Railway 集成成本。未完成 ADR 和隔离测试时，Engineer 退化为 V1 Contract-only 模式。

## 8. Human-in-the-loop

V2 复用 V1 Approval Contract，并扩展 `subject_type`：

```text
artifact
tool_request
budget_change
arbitration
deployment
```

- Approval 绑定 subject ID、version 和 hash；对象变化后旧批准失效。
- pending Approval 持久化，重启后不自动批准。
- 预算追加在事务成功后才恢复 Task；拒绝后进入 BudgetExhausted/Needs input。
- 越权 Tool 被拒绝时，Agent 只能修改计划或请求用户，不能换 Tool 名规避策略。
- Publish/Update 继续走独立 Deployment 状态机，不成为 Leader Tool。

## 9. Context 与 Agent Adapter

Context Service 按 Task 组装：role instruction、Task Contract、已接受 Artifact、Evidence 摘要、Tool Observation 和剩余预算。原始跨 Agent 对话、其他 Task 私有日志和 Chain of Thought 不进入 Context。

Agent Adapter 负责：

- 将 Runtime Context 转成具体 SDK/Provider 输入。
- 强制 Pydantic Structured Output 或 ToolRequest schema。
- 记录 model、prompt version、provider request ID、usage 和 trace。
- 把 Provider error 归一化为平台错误码。

Orchestrator 数据模型不能依赖某个 Agent SDK 的内部 Session；更换 Provider 不应改变 Task、Artifact、Handoff 和 Budget Contract。

## 10. 事件与可观测性

V2 复用 V1 SSE `id` / `Last-Event-ID` / snapshot resync，并新增：

```text
task_graph.created
task.ready / task.reserved / task.started / task.completed / task.failed
agent.started / agent.completed / agent.failed
handoff.delivered / handoff.accepted / handoff.rejected
tool.requested / tool.approval_required / tool.started / tool.completed / tool.failed
sandbox.provisioned / sandbox.destroyed / sandbox.failed
budget.reserved / budget.settled / budget.exhausted
rework.started / rework.completed
arbitration.requested / arbitration.decided
```

每条事件必须包含 `run_id`、`task_id`（如适用）、`agent_instance_id`（如适用）、`correlation_id` 和 Artifact/Evidence 引用。事件先持久化再推送，用户 UI 不展示私有 Prompt 或 Chain of Thought。

## 11. 数据模型

V2 复用 V1 users/projects/sessions/artifacts/approvals/versions/deployments/quota/ledger，并新增：

- `task_graphs`：Run 的图版本、状态、Leader proposal 和 Runtime validation。
- `agent_tasks`：角色、依赖、并发组、attempt、lease、deadline 和状态。
- `agent_instances`：role、model、prompt version 和 Tool Policy。
- `handoffs`：Artifact/Evidence 交付、接受、拒绝和 correlation。
- `tool_requests` / `tool_results`：参数、Policy 结果、Observation、资源和错误。
- `sandbox_runs`：Provider、base snapshot、limits、network policy、状态和销毁时间。
- `run_budgets` / `task_reservations`：父预算、子预留、结算、释放和 deadline。
- `arbitrations` / `rework_requests`：冲突、根因、Evidence、决定和收敛状态。

关键约束：

- Artifact、ToolResult 和 Handoff 使用不可变 ID/hash。
- Task 状态迁移、预算预留和 lease 获取在同一事务内完成。
- Sandbox/对象存储 key 不能作为用户可控路径；所有读取验证 user/project/run 归属。
- V1 ProjectVersion 和 Deployment schema 保持向后兼容。

## 12. 错误、恢复与补偿

Agent Provider、Handoff、Rework 和收敛语义以 [V2 Agent 设计](./agent-design.md)为准；工程 Runtime 负责：

| 失败 | 工程处理 |
| --- | --- |
| Agent Worker crash | lease 过期后重领；已有 Provider 结果通过 idempotency/trace 对账，避免重复结算 |
| Sandbox provisioning fail | ToolRequest failed，不调用 Agent 伪造结果；释放未用 Tool 预算 |
| Sandbox timeout/cancel | 收集已有日志/Evidence，销毁环境，结算已发生资源 |
| Object Storage 写失败 | Artifact 不进入 accepted；数据库事务不提交可用引用 |
| 并行部分失败 | 保留成功 Artifact，释放未启动预算，创建失败分支 attempt/decision |
| SSE 断线 | `Last-Event-ID` 补取；不重启 Task |
| Publish/Update 失败 | 保留上一个 Live Version 和稳定 URL 指针 |

补偿动作必须可审计，不能通过删除失败记录恢复“看起来成功”的状态。

## 13. 安全边界

- Control Plane、Agent Worker 和 Sandbox 使用不同服务身份与最小权限。
- Agent Worker 无宿主机 Docker socket、生产数据库写 SQL 或 Object Storage 全桶权限。
- Tool Gateway 只向 Sandbox 签发当前 Task/Artifact 前缀的短期访问能力。
- 默认拒绝网络；allowlist 同时约束 DNS/域名、协议、端口和重定向。
- Tool 参数、Patch 路径、依赖名和输出均经过 schema、路径与大小校验。
- 日志、Evidence 和 Trace 脱敏 Secret、Cookie、Authorization 和用户隐私字段。
- Sandbox 逃逸、跨租户读取、销毁失败属于 blocker，停止相关 Worker 池。
- 公开 App 的 opaque ID、缓存和 Unpublish 语义沿用 V1。

## 14. 部署与容量

```text
GitHub
  |
  +--> Railway Web Service
  +--> Railway Agent Worker Service
  |
  +--> PostgreSQL
  +--> S3-compatible Object Storage
  `--> Sandbox Provider / Sandbox Workers
```

- Web 与 Agent Worker 必须独立扩缩容；Worker 并发受 RunBudget 和 Sandbox capacity 双重约束。
- Web 不挂载 V1 共享 Build Volume；发布与 Evidence 从 Object Storage 读取。
- Scheduler 用 PostgreSQL lease 支持多 Worker，但必须完成重复领取、脑裂和事务压测。
- 容量报告至少包含 API/SSE、Agent 调用、Sandbox 启动、Tool 时长、并行预算、对象存储和数据库锁等待。
- 未得到压测数据前不写死生产 Worker 数、并行数或 RunBudget 数值。

## 15. 实施顺序

1. 冻结 V1 Artifact、Approval、Version、Deployment 和 Event Contract。
2. 建立 V2 TaskGraph、Task、Handoff、Tool、Sandbox 和 Budget 数据模型。
3. 将 V1 Sequential Orchestrator 抽象为持久化 Runtime，先运行顺序多 Agent Handoff。
4. 拆分 Web 与 Agent Worker，接入 Object Storage。
5. 完成父/子预算原子预占、部分失败补偿和并发测试。
6. 选择 Sandbox Provider，完成 Tool Gateway、隔离和销毁测试。
7. 上线 Engineer/QA Tool，再开启单条 Architect/Designer 并行路径。
8. 实现 Rework、Arbitration、收敛和 Human-in-the-loop。
9. 完成 V1 回归、V2 Golden Path、故障恢复、安全和容量测试。

## 16. 架构验收

- Web、Agent Worker 和 Sandbox 资源隔离，Agent/Build 峰值不阻塞 API/SSE 基线。
- TaskGraph、Task、Handoff、ToolRequest、SandboxRun、Budget 和 Event 可持久化恢复。
- 并行预占原子化，账户/Run 超额结算为 0；部分失败补偿符合第 5 节。
- 多 Agent 不共享可写工作区，跨用户/Project/Task Artifact、Secret 和 Context 泄漏为 0。
- ToolRequest 未通过 Policy/Approval 时不能执行；Agent 不能直接获得宿主 Shell。
- Sandbox 超时、取消、失败和销毁路径均有 Evidence、资源结算和告警。
- mandatory Evidence 不能被 Leader/QA 改写；ProjectVersion 只引用通过门禁的 Artifact。
- V1 Version/Publish/公开 URL 回归通过，V2 不自动 Publish。
- V2 Golden Path 5/5，通过重启、并行部分失败、预算耗尽和 SSE 重连测试。
