# Agent Runtime 边界与演进讨论

[toc]

- 文档状态：待收敛讨论，不构成 V1/V2 实施基线
- 讨论日期：2026-07-12
- 版本范围：整体
- 产品总纲：[整体产品目标与定位](../../整体/产品设计/整体产品目标与定位.md)
- 正式设计：[V1 Agent 设计](Agent设计.md) · [V1 架构设计](../工程设计/架构设计.md) · [V2 Agent 设计](../../V2/Agent设计/Agent设计.md)
- 实现证据：[V1 关键设计与实现 Review](../../../review/V1/综合评审/2026-07-12-关键设计与实现检查.md)

本文保留 Context、Memory、TaskGraph 和 Sandbox 的演进推理，用于比较方案与边界。已确认 Contract 只在对应 V1/V2 Design 中维护；本文中的“建议”“未来”和优化顺序不表示已经实现或已经拍板。

## 1. 核心判断：从受控生成走向持续 Vibe Coding

Another Atom 当前采用受控的 Vibe Coding 形态：用户描述一个产品目标，系统把它推进成可预览、可修改、可版本化、可发布的浏览器应用；模型能力逐步开放，但代码、版本和发布始终受 Runtime 约束。

这决定了 Agent Runtime 的重点不是尽可能开放模型能力，而是控制四件事：

1. **把模糊产品意图逐步变成显式 Contract；**
2. **把模型推理与代码执行、副作用和上线权限分开；**
3. **保留一个能跨 Run 延续、但不会污染后续生成的项目状态；**
4. **在需要更强工程能力时，逐步增加 Tool 和 Sandbox，而不是直接开放宿主机。**

因此，V1 采用固定角色接力是合理的。它牺牲了一部分自主协作能力，换来范围可控、Artifact 可检查、失败位置明确和发布权不落到模型手中。对当前产品阶段，这比先实现“会自由拆任务的多 Agent”更重要。

## 2. 这个场景的特殊性

### 2.1 同时存在两套代码

系统自身的 FastAPI、React、数据库和 Worker 是**平台代码**；Engineer 生成的 HTML/CSS/JavaScript 是**用户项目代码**。二者的可信级别、生命周期和发布方式不同：

```text
平台代码
  -> 可信 Control Plane
  -> 决定身份、配额、状态、版本、发布和权限

生成代码
  -> 不可信 Project Artifact
  -> 只能进入 Preview / Project Repository / Sandbox
  -> 必须经过校验和版本化后才能成为可发布结果
```

如果不区分这两层，最容易出现两个问题：一是把 Agent 生成的文本当成已经执行成功的代码；二是为了让 Agent“更像工程师”，把平台文件、Shell、密钥或发布权限一起暴露给模型。

### 2.2 产品需求和代码实现之间有一段不可省略的收敛过程

普通 Coding Agent 往往面对已有仓库、Issue 和测试，任务边界相对明确。Another Atom 的输入可能只有“做一个扫雷”“做一个任务看板”，页面、状态、交互、错误反馈和能力边界都没有写全。

所以 Product Manager 和 Architect 不是装饰性角色。它们承担的是把不完整自然语言变成 Engineer 可执行约束：

```text
用户目标
  -> Blueprint：产品范围和能力映射
  -> ArchitectureSpec：页面、状态和视觉约束
  -> AppSpec：可运行 Web 源码
```

这里的关键不是角色名称，而是每次收敛都产生新的、可确认的 Artifact。若把三个阶段合成一条长 Prompt，短期调用更少，但需求改变、视觉走样或能力越界时，很难判断问题发生在哪一层。

### 2.3 结果需要“可继续”，而不只是“生成成功”

一次性的网页生成只需要返回一份代码。持续 Vibe Coding 产品还要处理：用户编辑、旧版本恢复、失败后继续、再次调用 Agent、线上版本不被新草稿覆盖。

这意味着 Memory 不能只等同于聊天历史。真正决定项目能否继续的是：当前接受了什么需求、正在基于哪个版本修改、哪些检查已通过、线上指针指向哪里。聊天可以丢失部分措辞，这些事实不能丢。

### 2.4 用户和 Agent 都会修改同一个项目

Another Atom 同时存在三类写入者：

- Agent 生成新的 AppSpec；
- 用户通过结构化表单修改 AppSpec；
- 用户通过 Vim 修改项目文件。

因此，项目工作区不能被当成一个始终可覆盖的目录。每次写入都需要明确 base version、校验结果、版本来源和 Git commit；未来多 Agent 并行时，还需要独立快照和合并策略。

## 3. 当前 V1 Agent Runtime

### 3.1 控制权分层

V1 把控制权分成三层：

```text
LLM
  负责：路由建议、需求结构化、架构说明、应用源码、结果解释
  不负责：数据库、Git、配额、Job、Sandbox、发布

Orchestrator / Runtime
  负责：状态推进、Context 组装、Schema 校验、重试、Artifact、事件
  不负责：替模型补产品决策

Domain Services
  负责：Auth、Quota、Repository、Version、Deployment、Sandbox Session
  不接受模型直接调用
```

这一分层的本质是：模型可以提出内容，Runtime 决定内容是否满足 Contract，领域服务决定是否允许发生副作用。

### 3.2 当前调度模型

Lead 与团队 Run 分开：Lead 先做 `direct/team` 二选一路由；进入 team 后，平台按固定状态机调度 Product Manager、Architect、Engineer、Data Analyst、Validator、Reviewer。

```text
Lead
  |-- direct -> 保存回答，结束
  `-- team
       -> Product Manager
       -> supported：自动排队
       -> adapted：等待用户确认
       -> unsupported：等待用户接受或重写 Web 草案
       -> Architect
       -> Engineer
       -> Data Analyst
       -> Validator
       -> Reviewer
       -> ProjectVersion
```

下一角色由 Runtime 决定，不由上一个 Agent 自由选择。当前也没有 Agent-to-Agent 自然语言对话；handoff 就是经过 Schema 校验的 Artifact。

### 3.3 为什么 V1 不需要真正的动态多 Agent

V1 的任务依赖基本是线性的：需求范围没有确认前，架构并行价值有限；架构 Token 未确定前，Engineer 提前生成只会增加返工；ValidationReport 产生前，Data Analyst 没有可信工程证据。

固定顺序的优势：

- 调用量和最长路径可估算；
- 每个阶段只有一个明确输入和输出；
- Artifact 可以作为恢复点；
- 用户知道系统为什么暂停；
- 同一个项目只有一个主写入者，不需要先解决复杂合并。

代价也很明确：

- Agent 不能根据任务复杂度跳过或增加角色；
- Engineer 失败后不能自动请求 Architect 修改约束；
- Data Analyst 发现问题后不能形成结构化返工；
- 即使任务很简单，也会经过完整团队链路。

在 V1 闭环尚未完全验收前，这些代价可接受。过早开放动态调度，会把当前能定位的阶段失败变成 TaskGraph、并发、预算和合并问题。

## 4. Context 管理

### 4.1 Context 不是 Memory

Context 是**一次模型调用此刻能看到的输入**；Memory 是**系统跨调用保存、选择和重新提供事实的机制**。把两者混为一谈，常见结果是把所有历史都塞回 Prompt，既增加成本，也把已经被新版本替代的信息重新带入决策。

V1 代码目前没有独立 Context Service。上下文由 Provider 方法参数直接组装：

```text
Lead      = 当前消息
PM        = 当前 prompt + mode
Architect = Blueprint
Engineer  = prompt + Blueprint + ArchitectureSpec
Analyst   = prompt + AppSpec + ValidationReport
```

这套设计已经做对了一件关键事情：角色之间传递显式 Artifact，不共享完整对话和隐藏推理。但它还不是完整的 Context Contract。

### 4.2 当前 Context 设计的优势和代价

优势：

- 输入小，模型注意力集中；
- 上游事实经过 Pydantic 校验；
- 不会把其他用户、其他项目或无关日志带入模型；
- 中断恢复时可以从 Artifact 重建阶段输入。

代价：

- 没有记录本次调用具体使用了哪些 Artifact ID 和版本；
- Prompt instruction 没有独立 `prompt_version`；
- 用户确认后的修改与原始 prompt 之间缺少统一 request snapshot；
- retry 只知道当前 operation，缺少标准化的 failure evidence envelope；
- Follow-up 修改没有统一的 Context 组装规则。

### 4.3 建议引入 ContextEnvelope

下一步不需要先上向量数据库，而应先把每次调用的输入变成可持久化 Contract：

```text
ContextEnvelope
  context_id
  user_id / project_id / run_id / task_id
  role
  prompt_version
  request_snapshot_id
  base_version_id
  accepted_artifact_refs[]
  evidence_refs[]
  capability_policy_version
  budget_remaining
  retry_summary?
  created_at
```

Runtime 先生成 ContextEnvelope，再由 Provider Adapter 转成具体模型消息。这样可以回答三个工程问题：模型当时看到了什么、为什么看到这些、同一输入能否重放。

### 4.4 Context 裁剪顺序

项目型 Vibe Coding 的 Context 超限时，不应平均压缩所有内容。建议固定优先级：

1. 用户最新明确请求和已确认范围；
2. 当前 base version 与目标状态；
3. 本阶段必需的上游 Artifact；
4. 未解决的 Validation failure 和 Tool evidence；
5. 最近一次失败摘要；
6. 更早的过程日志和对话摘要。

不能被摘要替代的内容是 Contract、版本指针和失败 check；可以被摘要的是解释性对话、重复日志和已经关闭的问题。

## 5. Memory 设计

### 5.1 当前已经保存了什么

V1 虽然没有名为 Memory Service 的组件，但已经存在多种持久化记忆：

| 当前存储 | 保存的事实 | 是否应进入 Agent Context |
| --- | --- | --- |
| Project | 项目归属、名称、原始 prompt、当前版本 | 只取当前任务需要的摘要 |
| Run | 本次执行状态、阶段、模型、错误、配额 | 当前 Run 必需 |
| Artifact | Blueprint 到 ReviewReport 的结构化结果 | 按阶段显式引用 |
| ProjectVersion + Git | 可恢复源码快照和版本来源 | 修改任务必须指定 base version |
| RunEvent | 可重放进度和操作事实 | 默认不整段进入模型 |
| LeadMessage | 项目前路由消息 | 当前没有和 Run 串成对话 |
| UsageLedger | 调用和 token 事实 | 只向调度器提供预算摘要 |

这里最重要的判断是：Artifact、Version 和 Git 才是项目的长期事实；Event 和聊天主要是可观测性与解释材料，不应自动成为长期语义记忆。

### 5.2 建议的 Memory 分层

```text
L0  Request Memory
    用户本轮原始请求、确认和拒绝；不可被 Agent 自行改写

L1  Contract Memory
    当前已接受 Blueprint、ArchitectureSpec、Capability Policy

L2  Project State Memory
    当前版本、线上版本、源码 hash、未解决 check、dirty 状态

L3  Episodic Memory
    某次 Run 为什么失败、采取了什么修复、结果如何

L4  Retrieval Memory
    从较长历史中按任务检索相关片段；只有确有规模需求时再引入
```

V1 当前覆盖了 L0 的一部分、L1、L2 和原始事件，但没有形成 L3 的标准摘要，也没有 L4。对当前规模，优先补 L0-L3 比引入 embedding 更有价值。

### 5.3 Memory 写入规则

不是所有 Agent 输出都值得长期保存。建议只有以下内容可以成为可复用 Memory：

- 用户显式接受的需求或能力映射；
- 通过 Schema 和确定性校验的 Artifact；
- 已创建的 ProjectVersion、Git commit 和发布指针；
- 有 evidence 的失败原因和最终处理结果；
- 用户明确要求项目长期保留的偏好。

以下内容默认不写入长期 Memory：

- Chain of Thought；
- 模型的未经验证猜测；
- 已被新 Contract 替代的中间草稿；
- 完整构建日志；
- 其他 Agent 的私有上下文；
- 跨 Project 推断出的用户偏好。

### 5.4 Memory 失效比检索更重要

项目型 Vibe Coding 的主要风险不是“记不住”，而是“记住了已经失效的设计”。每条可复用 Memory 至少需要：

```text
scope: user | project | run | task
source_ref
base_version_id
created_at
superseded_by?
status: proposed | accepted | rejected | obsolete
```

例如用户恢复旧版本后，基于新版本生成的修改建议不能继续作为当前事实；Blueprint 被用户编辑后，旧 ArchitectureSpec 应标记为可能失效，而不是因为语义相似又被检索回来。

### 5.5 不建议过早做全局用户画像

当前产品需要的是项目连续性，不是跨项目揣测用户。全局偏好记忆会引入误判、隐私和可解释性成本。除非有明确的用户设置和关闭入口，否则视觉偏好、技术偏好或产品倾向应限制在 Project 范围。

## 6. 多 Agent 调度的演进

### 6.1 从固定 Pipeline 到持久化 TaskGraph

V2 不应直接把“下一步交给谁”完全交给 Leader。更稳妥的分层是：

```text
Leader Agent
  -> 提交 TaskGraph / retry / escalation 建议

Runtime Policy
  -> 校验依赖、角色权限、预算、写冲突和最大深度

Scheduler
  -> 持久化 Task，领取 lease，分配 Worker / Sandbox

Specialist Agent
  -> 只完成一个 Task Contract，输出 Artifact + Evidence
```

Leader 拥有规划权，不拥有执行权和越权权。Runtime 必须能拒绝循环依赖、无限返工、越预算、并发写同一基线或要求未授权 Tool 的计划。

### 6.2 Handoff 应传 Artifact，不传聊天

建议的 Handoff Package：

```text
Handoff
  from_task_id / to_task_id
  objective
  accepted_artifact_refs[]
  base_version_id
  evidence_refs[]
  unresolved_checks[]
  constraints[]
  budget
  expected_output_schema
```

它解决的是责任边界：接收者知道要完成什么、基于什么、哪些事实可信、什么算完成。把前一个 Agent 的完整聊天传给下一个 Agent，会把建议、猜测和事实混在一起，也让 Context 成本随协作轮次持续增长。

### 6.3 什么时候值得并行

并行必须同时满足：任务没有数据依赖、没有共享可写工作区、结果有确定合并方式。

适合早期并行的任务：

- Architect 对已确认 Blueprint 做布局方案，同时 Data Analyst 准备静态数据完整性规则；
- 多个只读 Reviewer 检查同一 AppSpec 的不同维度；
- 对同一失败生成多个候选修复，但只选择一个进入写入阶段。

不适合直接并行：

- 两个 Engineer 修改同一 AppSpec 和 worktree；
- Blueprint 尚未确认时同时生成正式 ArchitectureSpec 和代码；
- 多个 Agent 都可以移动当前版本或发布指针。

V2 第一阶段应先实现“持久化顺序 TaskGraph”，再开放只读并行，最后才处理多写入者合并。

### 6.4 返工必须有收敛机制

多 Agent 最容易失控的不是首次执行，而是互相退回。建议把返工设计成有界状态机：

```text
Validation fail
  -> 按 root_cause 路由到 PM / Architect / Engineer / Platform
  -> 只携带失败 check 和 evidence
  -> 每条回退边有 max_attempts
  -> 相同根因连续失败则停止并请求用户
```

需要记录的是 root cause、修改的 Artifact、check 是否变化，而不是让 Agent 用自然语言争论“谁的问题”。

### 6.5 调度器的工程事实

当前 BuildJob 已经具备 queue、attempt、lease owner、lease expiry 和 Artifact 复用，可以作为调度器的最小原型。但升级到 TaskGraph 前还需要：

- Task 和 Run 分离，一个 Run 可以有多个 Task；
- Task 输入引用不可变 Artifact 和 base version；
- lease heartbeat，而不仅是固定过期时间；
- cancel/deadline 和未使用预算释放；
- 同一 base version 的单写锁；
- Task 级 idempotency key；
- Worker crash 后的副作用对账；
- Handoff 和 Evidence 持久化。

## 7. Sandbox 设计

### 7.1 三种 Sandbox 不能混为一个

Another Atom 实际需要三种不同隔离：

| Sandbox | 执行什么 | 当前状态 | 主要风险 |
| --- | --- | --- | --- |
| Preview Sandbox | 生成的浏览器 HTML/CSS/JS | 已实现 sandboxed iframe + CSP | 浏览器能力绕过、资源滥用 |
| Editor Sandbox | 用户通过 Vim 修改 AppSpec | 有独立 Host 和 Docker 实现，部署证据不足 | 宿主路径、Git、网络、资源逃逸 |
| Agent Task Sandbox | Agent 文件、构建、测试 Tool | V1 未实现 | 任意代码、Secret、供应链和跨任务污染 |

Preview Sandbox 不能替代 OS 级 Sandbox；Editor Sandbox 也不应通过逐项放权直接变成 Agent Shell。三者的输入、权限和生命周期不同。

### 7.2 当前 Preview Sandbox

生成 WebCode 通过 `iframe sandbox="allow-scripts"` 和 CSP 运行，没有同源权限。Validator 同时拒绝明显的外部 URL、网络 API、iframe 和动态执行入口。

这足以构成 V1 的受控离线 Preview，但字符串扫描不是完整安全证明。未来如果允许外部图片、API 或 package，需要把能力声明、CSP 和网络策略变成一致的 Capability Contract，而不是只删掉某几个禁用字符串。

### 7.3 当前 Editor Sandbox

Sandbox Host 为 Project HEAD 创建 detached worktree，移除 `.git` 指针，只把 worktree 挂入只读根文件系统的 Docker 容器；固定启动 restricted Vim，并配置禁网、drop capabilities、`no-new-privileges`、PID/内存/CPU 上限。

保存不是把 worktree 直接合入主仓库。Control Plane 读取 AppSpec，重新校验，再由可信 Repository Service 创建版本和 Git commit。这个设计正确地区分了“用户可以编辑”和“用户可以直接操作项目 Git”。

当前边界：

- `--user` 继承 Sandbox Host 进程 UID/GID，Host 必须以非 root 运行；
- Session 注册表在 Host 内存中，Host 重启后的清理和恢复没有完整协议；
- 当前只编辑 `app-spec.json`，不是完整多文件 Coding Workspace；
- Docker daemon、namespace、cgroup 和禁网尚缺目标环境验收证据。

### 7.4 未来 Agent Task Sandbox

当 Engineer 获得文件、构建或测试 Tool 后，每个 Task 应拥有独立快照：

```text
accepted base Artifact / Git commit
  -> create task snapshot
  -> mount only task files
  -> inject short-lived Tool capability
  -> run fixed or policy-approved command
  -> collect patch + test evidence + resource usage
  -> destroy Sandbox
  -> Runtime validates and merges
```

最低要求：非 root、禁用 Docker socket、默认禁网、Secret 不进入文件和日志、路径 allowlist、CPU/内存/PID/磁盘/时间限制、可证明销毁、Patch 和 Evidence 可追踪。

在需要依赖安装或受控网络前，应单独做 Sandbox Provider ADR，比较强化容器、MicroVM 和远程 Sandbox 的隔离、启动延迟、成本和销毁可靠性。当前材料不足以预先判断哪一种一定合适。

## 8. 建议的优化顺序

### 8.1 第一阶段：先把 V1 的隐式规则变成 Contract

优先实现：

- `ContextEnvelope` 和 `prompt_version`；
- Project 当前 accepted Blueprint / ArchitectureSpec 指针；
- base version 和 request snapshot；
- 标准化 failure evidence；
- LeadMessage、Run 和后续修改的统一项目时间线；
- 文档与代码中的 Auth、Approval、Build、Sandbox 口径一致。

这一阶段不增加 Agent 自主性，主要提高可复现性和后续演进安全性。

### 8.2 第二阶段：补顺序返工闭环

在固定团队内增加：

- Validation root cause 分类；
- Engineer 单次自动 repair；
- 范围变化时回到用户确认；
- 相同错误的停止条件；
- 用户可见的 retry/resolve 操作。

这会直接改善 V1 完整性，也能验证 Handoff 和 Memory 设计是否够用。

### 8.3 第三阶段：抽象持久化 Task Runtime

把当前 Run 阶段拆成 Task、Handoff、Evidence、Budget，不改变初始执行顺序。先证明 Worker crash、取消、重试和恢复正确，再引入动态 TaskGraph。

### 8.4 第四阶段：开放有限多 Agent 调度

先允许 Leader选择已批准的任务模板和只读并行；所有写 Task 使用独立快照并串行合并。不要一开始允许 Leader创建任意角色、任意 Tool 或无限回退边。

### 8.5 第五阶段：按需要增加长期检索 Memory

只有当单个 Project 的 Run 和 Artifact 已多到无法通过结构化索引定位时，再增加摘要或向量检索。检索结果必须带 source、scope、base version 和失效状态，不能直接覆盖当前 Contract。

## 9. 如何判断优化是否有效

Agent 系统的效果不应只看“模型回答看起来更聪明”。这个场景至少要看：

- **需求保持率**：生成结果是否保留用户的产品身份和已确认范围；
- **Artifact 一致性**：Blueprint、ArchitectureSpec、AppSpec 和实现检查是否互相对应；
- **一次通过率**：每个阶段首次通过 Schema 和 Validation 的比例；
- **有效修复率**：repair 后失败 check 是否减少，而不是只改变措辞；
- **恢复正确率**：重启、超时和 retry 是否重复调用、重复扣费或重复创建版本；
- **Context 成本**：每阶段 token、重复内容比例和被裁剪的事实类型；
- **版本安全**：Agent/用户写入是否基于正确 base version，线上指针是否被意外移动；
- **Sandbox 证据**：逃逸、跨项目读取、Secret 泄漏和销毁失败必须为零；
- **用户介入质量**：系统暂停时，用户是否能看懂原因、影响和下一步。

多 Agent 优化只有在相同需求质量下减少时延、提高修复率或降低人工介入成本，才算产生价值。Agent 数量、并行度和 Tool 数量本身不是效果指标。

## 10. 最终结论

Another Atom 的 Agent 设计主线应该继续保持：**Artifact 是协作语言，Runtime 是控制中心，Memory 保存经过确认的项目事实，Sandbox 承担不可信执行。**

当前 V1 的固定 Pipeline 并不落后，它适合先证明 Vibe Coding 的最小闭环：需求被正确收敛，生成代码可以检查，用户修改不会破坏历史，发布仍由用户决定。

下一步最有价值的不是立刻增加更多 Agent，而是补齐 ContextEnvelope、Memory 失效、失败 Handoff 和 Sandbox 证据。等这些控制面稳定后，再把固定阶段抽象成持久化 TaskGraph，逐步开放局部并行和受控 Tool。这样 V2 增加的是可用的工程能力，而不是更难解释的模型行为。
