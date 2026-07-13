# Another Atom 项目完整设计知识库

[toc]

- 文档用途：单文件项目知识库，可独立提供给大模型作为 Another Atom 的产品、Agent 与工程背景
- 更新日期：2026-07-13
- 代码分支：`main`
- 适用范围：整体产品、V1 当前实现与验收、V2 已确认设计方向
- 原则：区分愿景、交付基线、代码现状和后续规划；没有实现证据的内容不写成已完成

## 0. 如何读取这份知识库

### 0.1 状态标签

本文使用四种状态：

- **[当前实现]**：当前仓库代码、Schema、状态机或自动化测试中可以直接找到。
- **[交付基线]**：当前项目治理文件要求 V1 必须遵守的验收范围。
- **[已确认设计]**：已经进入正式设计，但尚未全部实现或验收。
- **[规划]**：V2 或后续候选能力，不能描述成当前产品能力。

### 0.2 事实优先级

回答“现在代码怎么运行”时，优先级为：

```text
当前代码与 Schema
  > 当前自动化测试
  > 当前实现 Review
  > V1 正式设计
  > README 产品概述
  > 演进讨论与 V2 规划
```

回答“V1 应如何验收”时，项目根目录 `AGENTS.md` 的 Delivery Baseline 和 Evaluation Criteria 是治理基线。回答“长期准备怎么做”时，以整体产品设计和 V2 正式设计为依据。

## 1. 产品定位

### 1.1 一句话目标

Another Atom 是一个以 Project 为中心的多智能体 Vibe Coding 工作台：用户通过自然语言表达想法，Agent 负责需求整理、技术结构、代码生成和质量解释；用户可以预览、查看和修改源码、管理版本，并自主决定何时发布。

### 1.2 与 Atoms 的关系

Another Atom 与 [Atoms](https://help.atoms.dev/en) 面向相近目标：从用户意图出发，形成可以运行、修改、管理代码并发布的软件项目。

Another Atom 使用独立品牌、交互、Contract 和工程实现，不复用 Atoms 的源代码、私有 Prompt 或未公开基础设施。对 Atoms 的借鉴主要是：多角色协作的产品表达、项目工作区、代码可见、预览和持续迭代。

### 1.3 产品交付单位

产品交付单位是持续存在的 `Project`，不是一次模型回答、一个代码片段或一张截图。

一个 Project 统一归属：

- 用户原始需求和后续修改；
- Lead 与专业 Agent 的结构化产物；
- 项目源码和 Git 历史；
- Build、Validation 和 Evidence；
- ProjectVersion 历史；
- 当前工作版本和线上发布指针；
- 后续对话、修复和恢复记录。

### 1.4 端到端产品闭环

```text
想法 / 资料 / 现有项目
          |
          v
     与 Lead 对话
          |
          v
   多智能体规划与执行
          |
          v
  可运行应用 + 项目代码
          |
    +-----+-------------------+
    |                         |
    v                         v
预览 / 视觉修改          查看 / 编辑 / 管理文件
    |                         |
    +-----------+-------------+
                v
          校验 / 修复 / 版本
                |
                v
          用户确认发布
                |
                v
         继续对话和迭代
```

## 2. 要解决的核心问题

### 2.1 从模糊想法到可运行结果

用户通常只有目标，没有完整 PRD、架构和实现步骤。系统需要补全必要信息，但不能悄悄改变用户的产品目标或伪造当前 Runtime 不具备的能力。

### 2.2 AI 过程不可检查

单次 Prompt 很难判断模型理解了什么、为什么这样实现、失败发生在哪层。Another Atom 使用明确角色和结构化 Artifact，把需求、结构、代码和验证拆开。

### 2.3 生成结果难以继续

一次性代码或静态截图无法承接后续修改。Project 必须保存源码、版本、错误和发布状态，让用户回到同一项目继续开发。

### 2.4 用户缺少代码和上线控制

Vibe Coding 不能把代码藏在平台内部，也不能让新生成结果自动覆盖线上版本。源码、Git commit、ProjectVersion 和 Deployment pointer 必须相互可追溯，同时保持独立。

## 3. 不随版本变化的设计原则

### 3.1 Project 中心

需求、Agent 产物、源码、Preview、版本和发布都归属于 Project。Chat 是交互形式，不是产品资产边界。

### 3.2 Agent 通过产物证明价值

角色不进行展示型群聊。Product Manager、Architect、Engineer、Data Analyst 和 Reviewer 分别交付 Blueprint、ArchitectureSpec、AppSpec、DataProfile 和 ReviewReport；Runtime Validator 单独提供确定性 ValidationReport。

### 3.3 Context 最小化

Runtime 只向当前角色提供完成当前任务所需的信息，不共享无限增长的聊天历史、其他角色私有推理或无关日志。

### 3.4 风险驱动 Human-in-the-loop

用户明确要求构建后，已知范围和基础预算内的正常工作自动继续。范围、预算、权限、破坏性操作或线上状态变化时才暂停确认。

### 3.5 模型与证据分离

LLM 提出需求、结构、代码和解释；确定性 Validator、Build/Test/Security Evidence 与 Runtime 状态不能由模型自行改写。

### 3.6 工作版本与发布指针分离

Build、Edit、Repair 和 Restore 可以持续创建新版本，但线上 Public Route 只读取用户最后一次明确发布的版本。

### 3.7 Runtime 控制副作用

模型不能直接改变身份、配额、数据库状态、Git 历史、Sandbox 权限或发布指针。Agent 只返回结构化结果或 ToolRequest；Runtime 执行硬规则。

### 3.8 可恢复事实优先

用户看到的进度、错误、配额、Artifact 和版本必须来自持久化事实。刷新、重试和服务重启不能重复已完成工作、重复扣费或重复创建版本。

## 4. 核心概念

### 4.1 Lead

用户的单一 Agent 入口。V1 只做 `direct/team` 二选一路由；V2 规划升级为 TaskGraph 协调者。Lead 不直接生成专业 Artifact、不执行 Tool、不代用户审批和发布。

### 4.2 Blueprint

Product Manager 输出的产品 Contract，记录产品类型、支持级别、页面、模块、需求映射、舍弃项、视觉方向和数据要求。Blueprint 是可检查的事实视图，不等于每次都必须停下审批。

### 4.3 Artifact

角色或 Runtime 产生的结构化产物。V1 主要包括：

```text
Blueprint
ArchitectureSpec
AppSpec
DataProfile
ValidationReport
ReviewReport
```

Artifact 通过 Pydantic 校验后持久化。V2 规划增加不可变版本、hash、parent/correlation、Evidence 和 Handoff 引用。

### 4.4 Run 与 BuildJob

`Run` 表示一次 Agent 构建/修改执行，保存当前阶段、状态、错误和配额。`BuildJob` 是后续 Pipeline 的可恢复后台调度记录，具有状态、attempt、lease owner 和 lease expiry。

### 4.5 ProjectVersion

一次 Build、Edit、Resolve 或 Restore 形成的不可变项目版本，保存 AppSpec、DataProfile、ValidationReport、ReviewReport 和 Git commit。Restore 创建新版本，不覆盖历史。

### 4.6 Deployment

Project 的公开发布状态，保存公开 ID、发布策略和当前公开版本。Deployment pointer 与 Project 的 latest version 分离。

### 4.7 Sandbox

执行不可信文件修改、构建、测试或受限 Vim 的隔离环境。Sandbox 不持有平台数据库凭证，无权改变配额、Project 归属和发布指针。

### 4.8 Context 与 Memory

`Context` 是一次模型调用实际看到的输入；`Memory` 是系统跨调用保存、选择和重新提供事实的机制。持久化不等于自动进入 Context。

## 5. 版本规划与边界

### 5.1 整体愿景

长期目标是围绕同一 Project 支持需求理解、多智能体协作、代码管理、视觉/代码修改、验证、版本和发布。产品目标可以开放，但每个 Runtime 版本必须明确支持的应用形态、工具、依赖、网络和安全边界。

### 5.2 V1

**[交付基线]** V1 是当前实现与验收版本，面向 Railway 云端应用；Terminal CLI 和用户本地仓库执行不进入 V1 交付基线。

V1 的核心目标：

```text
请求 -> Blueprint / 必要确认 -> 固定团队构建 -> Preview
     -> Edit / Restore -> ProjectVersion -> 显式 Publish -> Public URL
```

V1 选择：

- 固定顺序角色，不做动态委派和并行；
- 单实例或 Railway 单副本；
- 进程内 BackgroundTask + 单 Worker；
- 数据库持久化 Run/Job/Artifact/Version；
- 每 Project 一个服务端本地 Git 仓库；
- 生成代码受 Runtime 能力边界约束；
- 普通 supported 工作自动继续，风险动作确认；
- 不自动发布。

### 5.3 V2

**[规划]** V2 在 V1 的 Session、Project、Git、Artifact、Risk Policy、Version 和 Publish Contract 上增加：

- Lead 动态 TaskGraph；
- 按任务选择角色子集；
- 独立 Task Context 和 Handoff；
- Engineer/Data Analyst/Reviewer 的受控 ToolRequest；
- 任务级 Sandbox 快照；
- 无依赖、无写冲突的局部并行；
- Evidence 驱动返工、仲裁和收敛；
- 独立 Agent Worker、PostgreSQL Lease 和共享 Artifact Storage。

V2 尚未实现，不能用 V2 设计解释当前 UI 或 API 已有动态协作。

## 6. V1 用户体验

### 6.1 登录与隔离

用户通过用户名密码登录，服务端创建随机 Session，浏览器使用 HttpOnly/SameSite Cookie。Project、Run、版本、Preview、文件、日志和 Sandbox Session 查询都校验当前 User。

### 6.2 Lead 路由

Studio 先调用 Lead：

- `direct`：回答、澄清或能力说明；保存 LeadMessage，不创建 Project/Run。
- `team`：前端创建 Project、ProjectSession 和 Run，随后异步生成 Blueprint。
- 用户显式“调用团队”可以覆盖 direct，但不绕过后续范围和风险策略。

### 6.3 Blueprint 范围三态

- `supported`：在当前 Runtime 和基础预算内可以实现，自动进入 Build Job。
- `adapted`：保留产品目标，但部分后端、支付、认证、持久化或外部能力需要本地演示或舍弃，等待用户确认映射。
- `unsupported`：当前 Runtime 无法表达主要目标，原 Run 停止且不创建 Build Job；PM 可以提供保留原目标的可构建草案，用户确认后创建新 Run。

### 6.4 工作区

Workspace 展示：

- 固定角色阶段和当前状态；
- Blueprint 与结构化产物；
- 可交互 Preview；
- Project Repository 文件和本次 Run Artifact；
- 运行日志和下载；
- Edit、Version、Restore、Publish；
- 可选 restricted Vim 入口。

附件控件当前只提交名称、大小和 MIME 元数据；文件内容未形成完整上传与 Agent Context。

## 7. V1 多角色 Agent 设计

### 7.1 执行范式

V1 是 `Contract-first Fixed Pipeline`，不是开放 ReAct，也不是多 Agent 自由聊天：

```text
LeadDecision
   |
   `-- team
        -> Product Manager
        -> Architect
        -> Engineer
        -> Data Analyst
        -> Runtime Validator
        -> Reviewer
```

同一个 LLM Provider 可以承担全部角色。角色差异来自 instruction、输入 payload、输出 Pydantic Schema 和 Runtime 权限，不代表独立训练模型或长期人格。

### 7.2 Lead Contract

输入：当前用户消息和 `force_team`。

输出 `LeadDecision`：

```text
route: direct | team
response
reason
```

Lead 当前不接收 Project 历史、源码、附件内容或预算摘要，不能声称理解完整 Project Context。

### 7.3 Product Manager Contract

职责：保留用户产品目标，把 Prompt 整理成可检查范围；提出支持级别，但不创建 BuildJob。

`Blueprint` 关键字段：

```text
schema_version
project_name
product_type
support_level: supported | adapted | unsupported
support_reasons[]
mapped_requirements[]
omitted_requirements[]
rewrite_suggestion?
capability_policy_version
pages[]
modules[]
visual_direction
data_requirements[]
```

### 7.4 Architect Contract

职责：把 Blueprint 转成页面策略、本地状态实体和视觉 Token；不生成后端、远程资源、动态依赖或原生能力。

`ArchitectureSpec` 关键字段：

```text
architecture_summary
page_strategy[]
data_entities[]
primary_color / accent_color / background_color
typography: sans | serif
density: compact | comfortable
style
```

### 7.5 Engineer Contract

职责：根据 Prompt、Blueprint 和 ArchitectureSpec 生成自包含源码 Contract。

`AppSpec` 关键字段：

```text
project_name
tagline / hero_title / hero_body
primary_color / accent_color / background_color
pages[]
products[]
html
css
javascript
```

当前 Engineer 无 Shell、Git、依赖安装、网络和发布权限。代码不得使用外部 URL、fetch/XHR/WebSocket、动态 import、eval 或后端调用。

### 7.6 Runtime Validator

Validator 不是 Agent。它根据 Prompt、Blueprint、ArchitectureSpec 和 AppSpec 产生不可由模型改写的 `ValidationReport`：

```text
passed
checks[]:
  check_id
  label
  status: pass | fail | warning
  root_cause
  resolvable
  detail?
```

### 7.7 Data Analyst Contract

职责：分析 AppSpec 中的结构化数据、内容记录和本地状态模型，不执行代码审查，也不决定工程校验是否通过。

`DataProfile` 关键字段：

```text
summary
sources[]
entities[]
checks[]
insights[]
warnings[]
analyst_mode
```

### 7.8 Reviewer Contract

职责：基于 Blueprint、ArchitectureSpec、AppSpec、DataProfile 和不可变 ValidationReport 独立审查需求覆盖、工程证据和未解决问题。

`ReviewReport` 关键字段：

```text
summary
verdict: accept | rework | needs_input
requirement_checks[]
engineering_checks[]
data_findings[]
issues[]
warnings[]
suggested_actions[]
reviewer_mode
```

Reviewer 不能把 failed ValidationCheck 改成 pass；存在 blocker 或 verdict 不是 accept 时不能创建 ProjectVersion。

## 8. 结构化输出如何约束模型

系统不能保证模型第一次输出正确，但保证不符合 Contract 的结果不能保存为有效 Artifact 或进入下一角色：

```text
Pydantic Model
    -> JSON Schema
    -> Provider 结构化请求
    -> 提取 JSON
    -> model_validate_json
         |-- pass -> save Artifact -> 下游再次按类型读取
         `-- fail -> 携带校验错误修正一次
                      -> Provider error
                      -> Stage 最多重试 3 次
                      -> 持续失败则 Run failed
```

约束层次：

1. Provider 系统指令要求只返回一个 JSON 对象。
2. Ollama 请求使用完整 JSON Schema `format`。
3. DeepSeek 官方兜底使用 JSON Object mode，字段级约束仍由本地 Pydantic 执行。
4. 第一次 Pydantic 失败会把 errors 返回模型修正；再次失败抛错。
5. 只有 Pydantic 对象可以 `model_dump` 后保存 Artifact。
6. 恢复已有 Artifact 时重新执行对应 Schema 校验。
7. Prompt、Risk Policy、Validator 和 Runtime 继续处理 Schema 无法证明的语义与权限问题。

已知边界：Schema 正确不代表语义正确；Model 目前没有统一 `extra="forbid"`；Prompt version 和完整 Context refs 尚未形成独立可重放记录。

## 9. Provider 与用量

### 9.1 Provider

- `MockLLMProvider`：本地开发和自动化测试，输出确定性 Contract。
- `OllamaCloudProvider`：真实模型入口，允许配置的 DeepSeek V4 Pro/Flash。
- DeepSeek 官方 API：配置 `DEEPSEEK_API_KEY` 后作为 Ollama timeout fallback。

当前默认配置使用 Mock；真实模型通过环境变量启用。Ollama 单次请求超过 failover threshold 时才切换官方 DeepSeek；普通 HTTP 错误不等同于 timeout fallback。

### 9.2 用量与配额

每个 Provider 记录 request count、input tokens、output tokens 和 fallback provider。Runtime 在调用前预占额度，成功或失败后按已观测实际用量结算，释放剩余预留。非 LLM 异常也必须释放未结算 reservation。

## 10. Context、Memory 与 RAG

### 10.1 当前 Context

当前没有独立 Context Manager，Provider 参数直接组装输入：

```text
Lead      = 当前消息
PM        = prompt + mode
Architect = Blueprint
Engineer  = prompt + Blueprint + ArchitectureSpec
Analyst   = prompt + AppSpec + ValidationReport
```

角色不共享完整聊天、其他 Agent 私有推理和完整日志。

### 10.2 目标 Memory 模型

Memory 由“保存事实”和“选择事实”组成：

- 数据库、Artifact Storage 和 Git 保存事实；
- Context Service 根据当前 Task 选择最小输入；
- RAG 只在结构化索引不足时补充检索。

作用域：

```text
Request / Call -> 当前一次调用
Task / Run     -> 当前任务和执行过程
Project        -> 同一项目需求、代码、版本、证据和对话
User           -> 用户显式保存的跨项目偏好；默认不推断画像
```

### 10.3 短期 Memory

- 最新消息和本轮意图；
- Task Contract、role instruction、prompt version；
- 当前 Artifact 输入；
- 选中文件及 base version；
- 当前 failure Evidence 和 retry 原因；
- 本 Task Tool Observation；
- 剩余预算与 idempotency 状态。

短期内容可以持久化为 ContextEnvelope/Trace 用于审计，但不自动成为长期语义事实。

### 10.4 长期 Project Memory

- 用户原始请求、确认、拒绝和范围修改；
- 已接受 Blueprint、ArchitectureSpec 和 Capability Policy；
- ProjectVersion、Git commit、源码 hash 和修改来源；
- 发布指针和公开状态变化；
- 未解决/已解决的确定性 Evidence；
- 某次 Run 的失败、修复、结果等 Episodic Summary；
- 用户显式要求在该 Project 保留的偏好。

不进入长期 Memory：Chain of Thought、未经验证猜测、被替代草稿、完整日志、Secret、其他 Agent 私有 Context 和推断式跨项目画像。

### 10.5 Memory 状态和失效

每条可复用 Memory 至少需要：

```text
scope / kind / source_ref / project_id
base_version_id? / content_hash
status: proposed | accepted | rejected | obsolete
superseded_by? / created_by / created_at
```

旧 Blueprint、旧 ArchitectureSpec 和旧版本建议保留历史，但不能因语义相似重新覆盖当前 Contract。Restore 后，基于其他 base version 的建议必须被过滤。

### 10.6 RAG 计划

**[当前实现]** 没有 Embedding、Vector Store、Retriever 或 Reranker。

**[已确认设计]** 先实现 Project 对话、ContextEnvelope、版本关联和 Memory 失效；当单 Project 历史和代码规模使精确索引不足时，再引入 Project 内混合 RAG：

```text
当前 Task
 -> user/project/base_version/status 硬过滤
 -> 精确读取当前 Contract、版本、文件、Evidence
 -> 关键词/路径/符号 + Vector 混合检索
 -> 按版本、状态、任务相关性重排
 -> 返回带 source_ref 的有限片段
 -> Context Builder 按 token 预算组装
```

RAG 可索引 Project 对话/摘要、文档、按文件/符号切分并绑定 commit 的代码、Artifact 摘要和失败 episode。RAG 输出是候选证据，不能覆盖当前 Contract、版本指针或直接写入 Repository。

## 11. Human-in-the-loop

### 11.1 原则

用户明确请求 Build/Modify 已经授权一次受控范围、基础预算内的工作。普通 supported 工作自动继续；新增风险才确认。

### 11.2 必须确认

- adapted 能力映射；
- 无法安全推断的关键澄清；
- 相对已确认 Blueprint 的范围变化；
- 额外调用/token/deadline/Tool 预算；
- 新依赖、网络、Secret 或越权 Tool；
- 丢弃修改、强制重置、删除 Project；
- Restore 等当前版本基线变化；
- Publish、Update、Unpublish；
- V2 无法在现有 Contract 内仲裁且会改变用户目标的冲突。

### 11.3 目标 Approval Contract

```text
approval_id / approval_type
project_id / run_id / task_id?
subject_type: artifact | budget | tool_request | worktree | version | deployment
subject_id / subject_version / subject_hash
risk_level / effect_summary
requested_by_stage / decided_by_user_id
status: pending | approved | rejected | cancelled | expired
created_at / decided_at
```

Approval 必须绑定精确对象。Artifact、预算、Tool 参数、worktree hash 或版本变化后，旧批准失效。

### 11.4 暂停、恢复和并发

Risk Policy 先持久化 Approval 和 Event，再将 Run/Task 置为 pending。用户决定时 API 重新校验 owner、subject hash/version 和状态；Approve 使用 CAS 抢占推进权，并在事务内写决定和后续 Job/预算。事务提交后再派发 Worker。

Reject/Cancel 保留输入、Artifact、Evidence、仓库和当前版本，不执行目标副作用，不预占新增额度。

### 11.5 当前实现差距

当前已实现 supported 自动继续、adapted Blueprint 等待确认、Run 状态 CAS、Approval/BuildJob 唯一约束和 owner 校验。但 `Approval` 表仍是 `run_id/user_id/artifact_id/approved/payload`，统一的 subject type/version/hash、拒绝/过期状态和 Tool/Budget/Deployment Approval 尚未完整实现。

## 12. V1 Runtime 与状态机

### 12.1 主状态

```text
Lead direct -> 回答结束

team
 -> product_running
    |-- supported   -> build_queued
    |-- adapted     -> awaiting_approval -> build_queued
    `-- unsupported -> needs_input -> 新 Run 或结束
 -> architect_running
 -> engineer_running
 -> data_running
 -> building / validating
    |-- app_spec + resolvable -> engineer repair（最多一次）-> validating
    |-- 仍失败 / 其他根因 -> failed
    `-- pass -> reviewer_running
 -> completed | completed_degraded
```

当前代码实现一次受控 Engineer 自动修复，不是完整 Repairing/Resolve Loop。首次校验只有在全部失败项均为 `app_spec + resolvable` 时才进入修复；修订后仍失败或包含其他根因时结束 Run。首次与修订后的 AppSpec、ValidationReport 分开持久化，重启时不会重复调用修复阶段。

### 12.2 Blueprint 异步执行

`POST /api/runs` 创建 Project/Session/Run 和 Project Git 后立即返回。Product Manager 在 FastAPI BackgroundTask 中使用新数据库 Session 生成 Blueprint。进程启动时恢复遗留 `product_running` Run。

### 12.3 Build Worker

后续 Pipeline 由进程内轮询 Worker 领取持久化 BuildJob：

- 每个 Run 只有一个 BuildJob；
- Job 保存 queued/building/validating/succeeded/failed 等状态；
- Worker 使用 lease owner/expiry；
- lease 过期 Job 可以重领；
- 已提交 Artifact 重新校验并复用；
- 已完成 Run 不因 Job 清理中断而重放。

单副本下该模型足够直接；多 Worker 前需要 lease heartbeat、外部副作用对账和更强 fencing。

## 13. Build、Preview 与 Validation

### 13.1 当前 Build 的准确含义

当前 Build 不安装每项目依赖，也不执行任意 Shell 或完整浏览器自动化。Engineer 生成 AppSpec，Runtime 做静态/确定性校验并物化源码。

“构建成功”准确表示：

- AppSpec Schema 合法；
- 必需 HTML/CSS 存在；
- 静态能力边界检查通过；
- Blueprint 页面/模块交接满足规则；
- ArchitectureSpec 与 AppSpec 视觉 Token 对齐；
- 颜色对比度达到阈值；
- 源码能被 Preview 组合为自包含页面。

它不等价于所有交互已通过真实浏览器 E2E。

### 13.2 Preview

父 Studio 通过私有 Preview API 获取当前用户拥有的 Version AppSpec，再在 sandboxed iframe 中组合执行 HTML/CSS/JavaScript。生成代码不能读取平台 Cookie、数据库或其他用户 Project。

Validator 当前主要依靠 Schema 和字符串/确定性规则，不是完整 JavaScript 安全分析。不能把它描述成可以安全执行任意敌对代码的强隔离沙箱。

## 14. Project、Repository、版本与发布

### 14.1 Project Git

每个 Project 绑定一个服务端本地 Git 仓库。代码版本至少物化：

```text
index.html
styles.css
app.js
app-spec.json
```

Project 文件 API 隐藏 `.git` 元数据并校验 owner。

### 14.2 版本创建

Build、结构化 Edit、Vim Save 和 Restore：

1. 校验 AppSpec 和基础版本；
2. 物化源码；
3. 创建 Git commit；
4. 创建 ProjectVersion；
5. 更新 `latest_version_id`。

Restore 复制目标 AppSpec 生成新版本，不重写 Git 历史。

### 14.3 发布

Publish/Update/Unpublish 使用独立 Deployment 状态。Public Route 只读取已发布 Version，不暴露 Repository、Agent Context、Event、配额或 Sandbox Session。

API 接受 `always_latest` 和 `specify_version`，但当前 Studio 使用指定版本；新 ProjectVersion 不会自动移动已有 Deployment pointer，因此 Always Latest 语义尚未完整实现。

## 15. 整体逻辑架构

```text
用户浏览器
React Studio / Preview / 文件 / Terminal UI
                    |
              HTTPS / WSS
                    v
+------------------------------------------------------+
| Gateway / Control Plane                              |
| Session + Owner Check | Lead + Risk Policy           |
| Project + Version + Publish | Event + Quota          |
| Repository API | Durable Scheduler                   |
+---------------------------+--------------------------+
                            |
          +-----------------+------------------+
          |                 |                  |
          v                 v                  v
      State DB        Project Git/Artifact       LLM Provider
          |                 |
          v                 v
      Build Worker     Repository Service
          |
          v
      Tool Gateway
          |
          v
   Sandbox Provider / Host
```

### 15.1 Control Plane

维护可信身份、资源归属、Risk Policy、状态命令、配额、Project、版本和发布指针，不让模型或 Sandbox 直接写业务状态。

### 15.2 Agent Runtime

组装 Context、调用 Provider、校验结构化输出、保存 Artifact、推进状态和记录用量。当前与 API 同进程，V2 规划拆成独立 Agent Worker。

### 15.3 Repository Service

维护 Project Git、受控源码物化、commit/version 映射和 Sandbox worktree 合并。浏览器和模型不直接获得宿主机仓库路径。

### 15.4 Tool Gateway 与 Sandbox

Tool Gateway 检查 User、Project、Task、Agent role、路径、网络、预算和 capability。Sandbox 只接收最小输入，无平台数据库凭证和长期 Secret。

## 16. 数据模型

### 16.1 身份与租户

- `User`：用户名、密码 hash、显示名、计划和配额计数。
- `AuthSession`：token hash、过期和撤销时间。

### 16.2 项目与执行

- `LeadMessage`：一次 Lead 输入、路由、回复、原因、模型和用量；当前未关联 Project/Run/thread。
- `Project`：owner、名称、Prompt、Mode、状态、latest version、repository path/branch。
- `ProjectSession`：Project/User、标题和 active；当前没有完整 Message 模型。
- `Run`：Project/Session/User、Mode、Model、状态、阶段、Prompt、错误和配额。
- `Artifact`：Run 内按 type 唯一的 Schema payload。
- `RunEvent`：持久化阶段、消息和 payload。
- `BuildJob`：Run/Project、状态、attempt、lease 和日志路径。

### 16.3 版本与交付

- `ProjectVersion`：项目、Run、版本号、来源、AppSpec、DataProfile、ValidationReport、ReviewReport、Git commit。
- `Deployment`：Project 唯一、public ID、strategy、version 和 active。
- `Attachment`：项目、名称、大小、媒体类型和可选 storage key；当前内容上传未完成。
- `SandboxSession`：User/Project、远端 session、token、状态和过期时间。

### 16.4 配额与确认

- `UsageLedger`：User/Run/Stage、units、entry type、请求数和 token。
- `Approval`：当前为 Run 唯一的简化 Blueprint 确认记录。

数据库默认 SQLite，也接受 PostgreSQL URL。当前使用 `create_all` 和手写补列，没有完整 Alembic 迁移历史。

## 17. API 与事件

### 17.1 主要 API

- 身份：signup、login、logout、me。
- Lead：提交消息和读取可用模型。
- Run：创建、读取、Blueprint 确认、替代草案确认/重生成。
- Event：SSE、history、日志下载。
- Project：列表、详情、最新 Run、文件列表/内容、导出。
- Version：列表、Preview、Revision、Restore。
- Deployment：Publish、Unpublish、匿名 Public AppSpec。
- Sandbox：创建/关闭 Session、保存、Terminal WebSocket。

所有私有 API 必须从服务端 Session 获取当前 User，并按 Project/Run/Version/Sandbox 归属查询；Public API 只接受 opaque public ID。

### 17.2 事件

V1 主要事件包括：

```text
stage.started / stage.completed
artifact.created
approval.required / approval.confirmed
build.queued / build.started
validation.completed
agent.retry
provider.fallback
run.needs_input / run.completed / run.failed
```

SSE 传输持久化 Event；断线后可通过 history/Last-Event-ID 恢复。事件是可观测事实，不默认全部进入 Agent Context。

## 18. 身份、安全与 Sandbox

### 18.1 Session Gateway

生产身份来自用户名密码和服务端 Session Cookie，不接受客户端自报 user ID。测试环境可保留测试身份机制。

当前密码实现是 PBKDF2-HMAC-SHA256，600,000 次迭代；若文档其他位置写 Argon2id，应以代码为当前事实。

### 18.2 统一归属检查

Project、Run、Preview、Version、Repository File、Log 和 Sandbox Session 都绑定当前 User。公开 Route 独立建模，不继承私有 API 权限。

### 18.3 受限 Vim

当前实现设计为独立 Linux Sandbox Host：

- 从 Project HEAD 创建 detached worktree；
- 隐藏 `.git`；
- restricted Vim，不提供登录 Shell；
- 容器禁网、只读根文件系统、drop capabilities、`no-new-privileges`；
- PID、CPU、内存和超时限制；
- Save 后由 Control Plane 重新校验并创建 Version/commit。

**[交付边界]** Terminal CLI 和本地 Repository 执行不属于 V1；目标 Linux Sandbox Host 的真实安全验收仍不能仅由命令参数和单元测试替代。

## 19. 配额、并发、幂等与恢复

### 19.1 配额事务

调用前 reserve，调用后按真实观测 settle，剩余 release。失败只结算已发生用量；平台异常也必须释放未结算额度。Artifact 与对应 Provider usage 在同一事务提交，避免产物存在但账本缺失。

### 19.2 Approval 并发

`awaiting_approval -> build_queued` 使用条件更新 CAS；`Approval.run_id` 和 `BuildJob.run_id` 唯一约束兜底。并发确认只能有一个请求创建 Job 和 Approval。

### 19.3 Worker 恢复

- 遗留 Blueprint BackgroundTask 启动恢复；
- lease 过期 BuildJob 可重领；
- 已完成 Artifact 按 Schema 复用；
- 已存在 ProjectVersion 不重复创建；
- 失败释放未使用 reservation；
- 已完成 Run 不因清理中断重放。

### 19.4 单实例取舍

V1 只面向本地单实例或 Railway 单副本，不实现跨实例 lease-owner fencing、消息队列、独立 Worker 集群、共享对象存储或 API 水平副本。该取舍减少分布式复杂度，但要求单副本、持久化 Volume 和恢复路径得到部署验证。

## 20. 部署架构

### 20.1 V1 当前形态

```text
GitHub -> Railway 单副本 Control Plane
                |
                +-> SQLite on persistent Volume
                +-> Project Git on persistent Volume
                +-> Ollama / DeepSeek Provider
                `-> optional remote Linux Sandbox Host
```

本地默认：

- Python 3.12 + FastAPI/Uvicorn；
- React/TypeScript/Vite Studio 构建后由 FastAPI 同域服务；
- SQLite `data/another_atom.db`；
- Mock Provider；
- Project Git 位于 `data/project-repositories`。

README 声明 Railway 单副本、持久化磁盘和公开访问已验收；本知识库生成时没有重新访问线上环境，因此该项属于仓库声明，不是本次独立复验。

### 20.2 最终拆分方向

```text
Browser -> Unified Gateway / Control Plane
               |
               +-> PostgreSQL
               +-> Artifact Storage
               +-> Agent Worker
                       |
                       +-> LLM Provider
                       `-> Tool Gateway -> Sandbox Provider
               `-> Repository Service -> Project Git
```

可信 Control Plane 与不可信执行面必须保持权限分离，即使 V1 为减少部署组件而合并进程。

## 21. V2 动态 TaskGraph

### 21.1 控制分层

```text
Leader Agent
  -> TaskGraphProposal / retry / arbitration 建议

Orchestrator Runtime
  -> 校验 role、dependency、cycle、budget、policy、HITL、写冲突

Durable Scheduler
  -> 持久化 Task、计算 Ready、预留预算、签发 lease

Specialist / Sandbox
  -> 执行一个 Task Contract，产生 Artifact + Evidence + Handoff
```

Leader 有规划建议权，没有直接状态、预算、Tool 和发布权。

### 21.2 动态性

- 根据任务选择角色子集，不机械运行完整团队；
- 无数据依赖、无共享写入且可确定合并的节点可以并行；
- Validation/Handoff Reject 根据 root cause 定向返回责任角色；
- 成功分支保留，失败分支重试或重排；
- 达到预算、轮次或相同 Evidence 重复上限后停止。

### 21.3 第一条局部并行路径

```text
Accepted Blueprint
       +------------------+
       v                  v
Architect Task     Data Preparation Task
       |                  |
ArchitectureSpec      DataProfile
       +---------+--------+
                 v
             Engineer Task
                 v
        Build/Test/Validation
                 v
          Data Review Task
```

只有数据准备不依赖最终 ArchitectureSpec 时才能并行。多个 Agent 不允许并发写同一 Sandbox/worktree。

### 21.4 Handoff

Handoff 持久化发送/接收 Task、Artifact refs、Evidence refs、Contract version、hash 和状态。接收方 Accept 后 Artifact 才满足下游依赖；Reject 产生 ReworkRequest，不删除或覆盖旧 Artifact。

### 21.5 Tool 与 Sandbox

- Engineer 可申请 list/read/apply_patch/build/test/request_dependency；
- Data Analyst 默认只读 inspect/test/browser/screenshot；
- Runtime 校验角色、参数、路径、依赖、网络、预算和 idempotency；
- 每个写 Task 使用独立快照；
- Patch 通过 Merge Task 和 mandatory Evidence 后才提交 ProjectVersion。

### 21.6 并行预算和部分失败

父 RunBudget 在 ready group 启动前原子预留所有子预算。任一分支无法预留时，整个 group 不启动或缩小范围。一支成功一支失败时，成功 Artifact 保留，已发生用量结算，失败分支重试，未启动依赖释放预算。

### 21.7 收敛

Runtime 限制：总返工轮次、单 Artifact 修订次数、相同 Evidence 重复次数、Agent 调用数、token budget 和 deadline。模型不能修改这些上限。

### 21.8 当前实现状态

当前代码没有 TaskGraph/AgentTask/Handoff/RunBudget/ToolRequest 的 Pydantic Schema 和数据库表，也没有 Ready 计算、任务级 lease、图版本、动态返工和并行 UI。V2 文档已经确定控制语义，但字段级 TaskGraph Contract 仍需实现前冻结。

## 22. 已实现能力、缺口与不能宣称的内容

### 22.1 当前已经形成的主线

- 用户名密码 Session 与账号级 Project 隔离；
- Lead direct/team 路由；
- Blueprint supported/adapted/unsupported 分支；
- 固定角色 Artifact 链；
- Pydantic 结构化输出与有限重试；
- 配额 reserve/settle/release；
- 持久化 Job/lease 和阶段 Artifact 恢复；
- Project Git、Build/Edit/Restore 版本；
- 私有 Preview owner 校验；
- Project 文件和 Run Artifact 查看；
- 显式 Publish/Unpublish 和 Public URL；
- Mock Provider、Ollama Provider 和 DeepSeek timeout fallback；
- Studio 阶段、事件、日志、Preview、文件和版本展示。

### 22.2 当前关键缺口

- 完整 Project 对话线程、Follow-up Context 和统一 Memory；
- 文件选择进入 Agent Context；
- 附件内容上传与理解；
- Validation 失败后的 Retry/Repair/Resolve；
- 真实浏览器交互自动验证；
- 通用 Approval subject/hash/version Contract；
- Always Latest 自动跟随语义；
- 版本化数据库迁移；
- 目标 Linux Sandbox Host 实机安全验收；
- 动态 TaskGraph、角色子集、并行、Tool、Handoff 和仲裁。

### 22.3 不能宣称

- 当前已经是自主多 Agent 系统；
- Agent 可以执行任意 Shell、任意依赖或任意后端代码；
- 当前已经使用 RAG 或长期用户画像；
- 当前 Build 等价于完整浏览器 E2E；
- 当前 Sandbox 已证明可以安全运行任意敌对代码；
- V2 TaskGraph 已经实现；
- 新版本会自动改变线上发布指针；
- 角色之间共享长期隐藏记忆或 Chain of Thought。

## 23. 验收与评价维度

### 23.1 完成度

验收完整路径与反路径：请求、Blueprint、必要确认、Build、Preview、Edit/Resolve、Version、Publish/Public URL、失败状态、恢复和持久化。

### 23.2 工程思维

检查 Contract、状态机、配额事务、并发 CAS、Job lease、Git/Version、权限边界、Sandbox 和明确取舍。

### 23.3 用户体验

每个可见控制必须有效、说明禁用原因或明确能力边界。用户能检查关键 Artifact、错误、版本和发布对象。

### 23.4 创新性

创新证据是可检查 Artifact 链、受控角色交接、Project 代码归属、可恢复版本和发布闭环，不是 Agent 数量或动画。

### 23.5 可交付性

源码、双语 README、可复现运行步骤、在线地址、已知边界和自动化/部署验证必须一致。里程碑只有在目标环境验收通过后才完成。

## 24. 文档与源码索引

### 24.1 整体

- `README.md`：产品入口和整体架构。
- `docs/design/整体/产品设计/整体产品目标与定位.md`：跨版本产品决策。
- `docs/design/整体/参考资料/Atoms参考产品分析.md`：Atoms 参考。

### 24.2 V1

- `docs/design/V1/产品设计/产品需求.md`：V1 产品 Contract。
- `docs/design/V1/Agent设计/Agent设计.md`：V1 角色、HITL、Context、Tool 和状态机。
- `docs/design/V1/Agent设计/多角色Agent设计问答.md`：Contract、Memory/RAG、多 Agent、TaskGraph 和 HITL 解释。
- `docs/design/V1/Agent设计/对话式AI-Coding初版设计.md`：Project 对话和 ChangeProposal 初版。
- `docs/design/V1/工程设计/架构设计.md`：V1 组件、数据、安全、恢复和部署。
- `docs/design/V1/工程设计/本地运行与Railway部署.md`：配置与部署步骤。

### 24.3 V2

- `docs/design/V2/产品设计/产品需求.md`：V2 产品范围与验收。
- `docs/design/V2/Agent设计/Agent设计.md`：Leader、TaskGraph、Handoff、Tool 和收敛。
- `docs/design/V2/工程设计/架构设计.md`：Worker、PostgreSQL Lease、Object Storage 和 Sandbox。

### 24.4 当前实现入口

- `another_atom/contracts/schemas.py`：Pydantic Contract。
- `another_atom/agent/provider.py`：角色 Prompt、结构化 Provider、fallback 和 usage。
- `another_atom/agent/orchestrator.py`：固定 Pipeline、阶段重试和 Artifact 复用。
- `another_atom/build/worker.py`：BuildJob、lease 和恢复。
- `another_atom/build/renderer.py`：源码与确定性 Validator。
- `another_atom/domain/quota.py`：配额事务。
- `another_atom/domain/auth.py`：密码与 Session 相关实现。
- `another_atom/storage/models.py`：持久化模型。
- `another_atom/api/routes.py`：REST、SSE、Preview、Version、Publish 和 Sandbox API。
- `another_atom/repository/service.py`：Project Git 和版本物化。
- `studio/src/App.tsx`：Studio 主交互和状态展示。

## 25. 最终结论

Another Atom 的产品主线不是“一次生成网页”，而是把用户目标变成归属于同一 Project 的结构化需求、代码、证据、版本和发布结果，并允许用户继续检查、修改和迭代。

V1 当前通过固定多角色 Pipeline、Pydantic Artifact、Runtime 状态机、Project Git、版本和显式发布证明受控闭环；它的价值主要来自可检查、可恢复和可控制，而不是 Agent 自主性。

V2 计划在相同 Project 和权限基础上增加持久化 TaskGraph、独立 Context、Handoff、受控 Tool、局部并行和 Evidence 驱动返工。V2 的自主性必须由 Runtime 约束，不能通过放宽权限获得。

这份知识库中最重要的事实边界是：产品愿景可以宽，当前 Runtime 和 V1 验收范围必须明确；设计可以前瞻，回答“已经实现什么”时必须回到代码、Schema、测试和部署证据。
