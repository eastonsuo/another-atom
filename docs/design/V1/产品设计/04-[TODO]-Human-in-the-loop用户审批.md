# Another Atom V1 Human-in-the-loop 用户审批

[toc]

- **文档状态：** V1 产品设计基线；adapted Blueprint 审批已实现，通用 Approval 控制面仍待补齐
- **功能定位：** 为工作流确认、风险确认和显式高影响操作提供统一、可恢复的用户决定机制
- **合并流程基线：** [统一 Chat 与 Human-in-the-loop](./06-统一Chat与Human-in-the-loop.md)；本文只展开其中的 `approval` 子类型
- **产品基线：** [V1 核心产品需求与交互](./01-核心产品需求与交互.md)
- **对话修改：** [V1 通过对话修改现有项目](./03-通过对话修改现有项目.md)
- **PM 专项设计：** [PM 整理产品方案并由用户确认](./05-[TODO]-PM整理产品方案并由用户确认.md)
- **技术设计：** [V1 Human-in-the-loop 审批机制](../技术设计/05-[Agent][TODO]-Human-in-the-loop审批机制.md)
- **当前实现检查：** [20｜Project 对话路由与代码修改授权检查](../../../review/待办/20-[综合]-2026-07-14-Project对话路由与代码修改授权检查.md)

## 背景

Another Atom 的多个业务流程都需要“先暂停、让用户确认精确对象、再恢复下一步”：首次 ProductSpec 进入 Architect 前必须确认，范围和预算变化需要风险确认，Restore 与 Publish 等高影响操作需要显式确认。如果各业务分别实现布尔字段、弹窗和恢复逻辑，状态、权限、对象失效与并发语义会逐渐分叉。

本文定义可被不同业务复用的 Human-in-the-loop 产品控制面：什么是待确认对象、用户决定有哪些状态、对象变化后如何失效，以及业务如何在批准后恢复。PM 如何生成和重写产品文档、预算如何估算、Deployment 如何执行仍由各自专项设计负责。

## 摘要

- **复用控制面**
  - ProductSpec、范围变化、额外预算、破坏性 Diff、Restore 和 Deployment 共用一套 Approval 状态、权限、版本绑定、恢复和审计机制。
- **三种触发来源**
  - 固定工作流、确定性 Risk Policy 和用户显式高影响操作都可以请求 Approval，但触发条件由对应业务负责。
- **精确对象**
  - Approval 必须说明正在确认的 Project、范围或 Artifact、基线版本、实际影响和预算；对象变化后旧批准失效。
- **对话连续性**
  - pending、批准、拒绝、成功和失败都写回 Project 对话；已经生成的结构化 Artifact 与确定性证据继续保留。
- **无副作用拒绝**
  - 未批准、拒绝、取消或批准失效时，不追加预算、不移动当前版本、不丢弃未提交修改，也不改变线上内容。
- **能力边界**
  - Approval 不能把 Runtime 不支持的能力变成可执行能力，也不能覆盖 Validator、安全策略、用户归属或版本并发检查。

## 1. 产品结论

V1 将 Project 对话作为用户控制 Agent 工作的主时间线，将 Run 视为其中一次执行尝试，将 Approval 视为业务流程中的通用暂停点：

```text
Project 对话
    |
    v
业务流程形成待确认对象
    |
    v
确定触发来源
    |
    +-- workflow：ProductSpec 等固定基线确认
    +-- risk_policy：范围 / 预算 / 破坏性变化
    `-- explicit_action：Restore / Publish 等显式操作
                 |
                 v
             Approval
                 |
        +--------+---------+
        |        |         |
      批准      调整      拒绝/取消
        |        |         |
        v        v         v
    校验对象后   形成新对象  保留当前安全状态
      继续执行   重新判断
```

Approval 不负责生产业务对象，也不证明用户“看过”每个 Agent 输出。ProductSpec 工作流生成文档，Risk Policy 计算风险，Deployment Service 执行发布；通用机制只负责确认精确 subject、保存决定并可靠恢复对应业务。

## 2. 三种控制方式

### 2.1 请求本身构成准备阶段授权

用户明确要求“创建这个应用”时，已经授权 Lead 和 PM 整理产品方案，但在用户批准 ProductSpec 前还没有授权进入 Architect 和 Engineer。ProductSpec 批准后，首次构建在已确认范围和基础预算内执行不再重复确认：

- 保持已确认的产品类型、页面和核心模块范围；
- 使用 V1 已声明支持的自包含 Web Runtime；
- 使用本轮基础团队调用预算；
- 只创建新的工作版本，不改变线上版本；
- 不丢弃 dirty worktree、不删除 Project、不读取未授权外部资源。

已有 Project 的自然语言代码修改采用不同边界：用户消息只授权 Lead 回答、澄清或形成修改任务，不直接授权写代码。每个 `propose_change` 都创建一次轻量 workflow Approval，用户点击“修改代码”后才启动 `ai_edit` Run。范围变化、额外预算和其他高影响事实在同一任务卡中明确展示；实际 Diff 扩大时再创建新的精确 subject。

### 2.2 风险 Approval

系统发现下一步超出基础授权时，先生成可检查的风险对象，再等待决定。用户批准的是本次明确变化，不是对当前 Project 或 Agent 的长期放权。

### 2.3 明确操作本身构成确认

用户主动点击已经完整展示对象与后果的 Save Version、Publish 或 Update 时，该点击可以直接构成该动作的确认，不再叠加内容相同的第二个弹窗。以下情况仍需额外确认：

- 删除 Project 或丢弃未提交修改等难以恢复的动作；
- 当前页面没有展示目标版本、公开影响或被覆盖对象；
- 用户点击后目标对象已经变化，需要重新核对。

资源选择也属于显式授权：本地文件夹必须由用户通过浏览器选择，外部 Git 仓库必须由用户选择并授权。平台不能把 Approval 当成扫描用户电脑或外部账号的泛化许可。

### 2.4 三种触发来源

```text
gate_source
  workflow         固定流程必须确认，例如 ProductSpec -> Architect
  risk_policy      只有命中范围、预算或破坏性风险时确认
  explicit_action  用户主动触发 Restore、Publish 等高影响动作
```

通用机制不判断某个业务是否应该请求 Approval。业务流程提供 gate source、subject 和批准后的恢复目标；通用机制保证决定只对该 subject 生效。

### 2.5 通用机制与业务流程的边界

| 责任 | 通用 Human-in-the-loop | 业务专项设计 |
| --- | --- | --- |
| 生成对象 | 不负责 | PM 生成 ProductSpec、Runtime 生成 Diff、Deployment 生成发布目标 |
| 判断触发 | 接收结果 | Workflow 固定触发、Risk Policy 判断风险、用户发起显式操作 |
| 展示内容 | 提供状态和失效语义 | 业务卡片决定摘要、字段、文档和操作文案 |
| 保存决定 | 统一负责 | 引用 Approval 结果 |
| 并发与恢复 | 统一 CAS、持久化和恢复事件 | 实现幂等业务 operation |
| 批准后继续 | 发出精确恢复事实 | PM 流程进入 Architect，预算流程追加额度，Deployment 执行发布 |

### 2.6 V1 复用场景

| 场景 | gate source | subject | 批准后恢复 |
| --- | --- | --- | --- |
| 首次 ProductSpec | workflow | 简介 + `docs/product-spec.md` generation | Architect |
| Project 代码修改 | workflow | ChangeBrief + 基线版本 + 有效 Contract/源码 Context hash | 创建 `ai_edit` Run |
| 产品范围变化 | risk_policy | ProductSpec Delta / RequirementDelta | 修改流水线 |
| 额外预算 | risk_policy | budget change | 原 Agent stage |
| 破坏性 Diff | risk_policy | SourceDiff | VersionMaterialization |
| 丢弃 worktree / Restore | explicit_action | worktree / version | Repository operation |
| Publish / Update / Unpublish | explicit_action | deployment target | Deployment operation |

## 3. 什么时候需要 Approval

### 3.1 触发矩阵

| 风险类型 | 典型触发 | 用户需要看到 | 未批准时 |
| --- | --- | --- | --- |
| 产品基线 | PM 已生成新的 ProductSpec，准备进入 Architect | 产品简介、正式 Markdown 路径和能力限制 | 不进入技术设计 |
| Project 代码修改 | Lead 已形成 ChangeBrief，准备调用固定团队修改当前代码 | 修改目标、保持不变项、验收条件、基线版本；按钮“修改代码” | 只保留对话和任务卡，不创建修改 Run |
| 范围适配 | 首次 ProductSpec 或后续修改出现 `support_level=adapted`，部分需求被映射、替换或舍弃 | 原目标、映射项、舍弃项、可交付结果 | 首次并入 ProductSpec 确认；后续不执行新增范围 |
| 范围变化 | Follow-up 或修复新增、删除、替换页面或核心模块 | 当前范围、新范围、保持不变项 | 不执行范围变化 |
| 额外预算 | 超出基础预算，追加 retry/rework 或额外模型调用 | 已用额度、追加额度、最大上限、用途 | 不预占或消耗额外额度 |
| 破坏性代码变化 | 实际 Diff 大面积删除、删除入口或覆盖关键模块 | 基线版本、变更文件、删除量、可回退结果 | 候选 Artifact 保留但不提交版本 |
| 工作区破坏 | 丢弃 dirty worktree、强制重置、删除 Project | 会丢失或删除的对象、是否可恢复 | 原工作区和 Project 保持不变 |
| 版本切换 | Restore 改变当前工作版本 | 当前版本、目标版本、新版本语义 | 当前版本指针不变 |
| 公开状态变化 | Publish、Update、Unpublish | 目标版本、公开 URL、线上变化 | 线上版本不变 |
| 能力适配 | 当前项目类型的 Runtime Adapter 只能实现部分要求 | 能实现什么、不能实现什么、是否保持项目类型 | 不按适配方案执行；不得默认改成 Web |

`unsupported`、越权访问、跨用户资源、Validator mandatory failure 和平台安全错误不属于“用户批准即可继续”的风险。系统必须拒绝或进入 Needs input，不能生成一个 Approval 让用户替平台承担不可执行结果。

### 3.2 不触发 Approval

以下动作在对象和边界未变化时自动继续或由操作按钮直接确认：

- ProductSpec 已批准后，supported 范围内的 Architect、Engineer 和固定下游流水线；
- 已经通过“修改代码”批准的任务中，当前页面和模块范围内的文案、样式和现有交互修改；
- 已经通过“修改代码”批准的明确应用错误修复；
- 基础预算内的固定团队调用和有限 Schema retry；
- 查看 Preview、文件、Diff、Artifact、日志和版本历史；
- 打开受限 Vim、编辑临时 worktree；
- 用户显式 Save Version，且页面已展示保存对象与 Diff；
- 创建新工作版本但不改变 Public Route。

### 3.3 ProductSpec 的具体接入

首次产品方案确认复用本机制，但简介、真实 Markdown、重新生成规则和 Architect Handoff 不在通用层维护，统一见 [PM 整理产品方案并由用户确认](./05-[TODO]-PM整理产品方案并由用户确认.md)。大模型翻译软件等能力适配案例也由该专项文档说明。

## 4. Approval 卡片

### 4.1 必须展示的信息

每张 Approval 卡片必须让用户不用阅读内部日志也能回答“为什么停、批准什么、批准后发生什么”：

- 当前 Project 和触发本次暂停的用户请求；
- 风险类型和具体原因，不使用笼统的“高风险操作”；
- 当前基线版本、目标 Artifact 或目标操作；
- 将新增、删除、替换、丢弃或公开的内容；
- 明确保持不变的内容；
- 预算变化和最大上限（如涉及）；
- 批准后的下一步，以及拒绝后的安全状态；
- 对象已经变化时，显示旧批准失效原因并要求刷新。

技术 hash 用于后台绑定，不要求用户理解；界面应展示可识别的版本号、文件、页面、模块、金额或公开 URL。

### 4.2 用户动作

通用机制支持批准、拒绝和取消状态，但业务卡片不需要把它们固定渲染成同一组按钮。ProductSpec 卡片只展示简介、Markdown 提示、重新生成状态和“确认并进入技术设计”；直接编辑由通用 Markdown 功能承接。预算、Restore 和 Deployment 使用各自最容易理解的操作文案。

- **批准并继续：** 仅授权卡片中的精确对象；Runtime 重新校验对象未变后继续一次。
- **调整方案：** 回到对话或可编辑 Artifact，用户修改范围、预算或目标；修改后形成新对象并重新判断。
- **拒绝：** 明确不接受当前提案，Run 进入 Needs input 或结束本次动作，保留已有对话和 Artifact。
- **取消：** 放弃本次等待中的动作，不代表否定 Project；不产生额外模型调用和副作用。

V1 不提供“本项目以后全部允许”“始终允许这个 Agent”或跨 Project 的永久授权。

## 5. 在 Project 对话中的位置

### 5.1 首次构建

```text
Prompt -> PM -> 简介 + docs/product-spec.md
                    |-- 用户修改 -> needs_regeneration -> PM 重新生成
                    |-- 用户确认 -> ProductSpec Approval -> Architect
                    `-- unsupported -> Needs input，不进入技术设计
```

首次 ProductSpec Approval 由固定 workflow 触发，不依赖 Risk Policy 判断是否需要暂停。supported 和 adapted 方案都必须确认；adapted 的映射、遗漏项和能力限制包含在同一 ProductSpec subject 中，不再叠加第二次相同确认。用户修改简介或 Markdown 后，旧 Approval stale，必须由 PM 重新生成后才能确认。具体流程以 PM 专项设计为准。

### 5.2 对话修改现有项目

修改可能有两个不同的确认时点：

1. **执行前：** ChangeBrief 和 RequirementDelta 已经表明范围变化、能力适配或需要额外预算；此时先确认，避免无意义地继续调用下游 Agent。
2. **提交前：** 候选代码和 SourceDiff 已生成，实际删除量或影响超过执行前判断；此时保留候选 Artifact，但确认前不创建 ProjectVersion。

同一风险对象只确认一次。执行前已经准确覆盖且实际 Diff 未扩大时，不重复弹出提交前确认。

### 5.3 结果回到对话

Approval 请求与决定都写入 Project 对话和事件时间线：

- 成功后展示新 ProjectVersion、Git commit、Diff 和验证结果；
- 失败后展示失败阶段、错误证据和已生成 Artifact，不移动当前版本；
- 拒绝或取消后展示未执行的具体动作和当前安全状态；
- 用户可以继续对话，形成有关联的新 attempt。

保留的是结构化 Artifact、确定性证据和用户可见结果，不保存模型私有推理过程。

## 6. 状态语义

| Approval 状态 | 用户含义 | Run / Project 行为 |
| --- | --- | --- |
| `pending` | 正在等待用户决定 | 暂停风险动作，不视为系统故障 |
| `approved` | 精确对象已获准执行一次 | 重新校验对象后恢复；不能重复产生副作用 |
| `rejected` | 用户不接受当前方案 | 进入 Needs input 或结束动作，保留当前安全状态 |
| `cancelled` | 用户放弃本次等待 | 不继续执行，不消耗额外预算 |
| `stale` | 基线、Artifact、预算或目标已经变化 | 旧批准不可用，显示变化原因并生成新判断 |

刷新、SSE 断线或服务重启不会改变 pending 状态，也不会自动批准。长时间 pending 可以继续保留，但不能长期占用 Project 写锁；用户回来决定时必须重新校验当前基线。

## 7. 产品边界

V1 明确不做：

- 组织、团队成员、多级审批人或管理员代用户审批；
- 独立 Approval Center 和跨 Project 批量审批；
- Agent 自己批准、Reviewer 覆盖用户拒绝或自动接受超预算；
- 用 Approval 绕过身份、Capability Policy、Validator、Sandbox 或发布权限；
- 对任意 Shell、动态依赖、开放网络和用户电脑目录提供泛化永久授权；
- 因为用户批准而静默改变原始产品类型或隐藏被舍弃需求。

V2 可以在不改变“精确对象、对象变化即失效、拒绝无副作用”的前提下扩展 ToolRequest、Arbitration 和 Approval Center。

## 8. 验收路径

### 8.1 主路径

1. supported 请求先生成 ProductSpec，用户确认后进入 Architect；下游正常范围不重复审批。
2. adapted 请求在同一 ProductSpec 中展示映射与舍弃项，批准后只执行已展示方案。
3. 当前 Project 内普通修改先展示任务卡；用户点击“修改代码”后才创建修改 Run。
4. Runtime 将完整有效 Contract 与固定字符预算内的基线源码 Context 交给 Engineer；源码未超限时全量发送，超限时按文件裁剪并记录包含和省略清单。Engineer 返回 Diff，由 Runtime 在隔离候选工作区 apply。
5. 范围变化在执行前任务卡中明确展示；用户批准后基于同一基线继续。
6. 实际 Diff 出现未预期的大面积删除时在提交前暂停，批准前不创建版本。
7. Publish/Update/Unpublish 明确展示目标线上变化，由用户显式执行。

### 8.2 反路径

- 用户编辑待审批对象后，旧批准失效，不能继续旧任务。
- 用户拒绝或取消后，当前版本、dirty worktree、额度和线上版本保持不变。
- 两次点击批准最多恢复一次执行，不创建两个 BuildJob、Git commit 或 ProjectVersion。
- 页面刷新和服务重启后仍能看到相同 pending Approval 和相关 Artifact。
- 其他账号不能读取或决定当前 Approval。
- unsupported 能力、Validator mandatory failure 和版本冲突不能通过 Approval 强制放行。
- Approval 后、真正执行前基线发生变化时，系统显示 stale，不把旧结果覆盖到新版本。

## 9. 当前实现状态

当前代码已经实现：

- `supported` 与 `adapted` 产品规格（ProductSpec）都进入 `awaiting_approval / blueprint_approval`，不存在受支持方案自动批准；
- 等待状态、产品规格产物（Artifact）和事件持久化；用户确认后再写入批准（Approval）决定记录；
- 产品规格批准后，架构师与工程师固定流水线自动继续；架构设计默认不增加第二次强制确认，只有它要求改变产品边界时才退回产品规格重新确认；
- 只有 Project 所属用户可以确认；
- 状态 CAS 与唯一 BuildJob/Approval 约束阻止重复排队；
- 刷新后可恢复等待状态，确认后进入现有构建工作器（Build Worker）。
- Project 修改任务以持久化 `change_proposal` 卡片等待“修改代码”；批准前无 Run，批准时重验基线并创建 `ai_edit` Run，支持重复批准幂等和旧基线 stale。

尚未完整实现：

- 固定 `workflow`、风险 `risk_policy` 和显式操作 `explicit_action` 三种 gate source；
- 首次 ProductSpec 对 supported/adapted 均确认，以及批准后恢复 Architect 的业务适配器；
- 通用 Approval 类型、`rejected / cancelled / stale` 决定接口；
- 通用 pending Approval 的独立数据记录；Project 修改当前使用专用 ProjectMessage payload，Blueprint 仍由 Run 状态和事件表达；
- 对话修改中的范围、预算与破坏性 Diff Risk Policy；
- Approval 绑定统一 subject version/hash，以及对象变化后的失效流程；
- dirty worktree、Restore、删除和 Deployment 共用的审计 Contract；
- Approval 请求与决定作为完整结果卡片写回 Project 对话。
