# Another Atom V1 Human-in-the-loop 用户审批

[toc]

- **文档状态：** V1 产品设计基线；adapted Blueprint 审批已实现，统一风险审批仍待补齐
- **功能定位：** 在 Agent 或 Runtime 即将改变已确认范围、预算、工作状态或公开状态时，让用户基于明确对象决定是否继续
- **产品基线：** [V1 核心产品需求与交互](./01-核心产品需求与交互.md)
- **对话修改：** [V1 通过对话修改现有项目](./03-通过对话修改现有项目.md)
- **技术设计：** [V1 Human-in-the-loop 审批机制](../技术设计/05-[Agent]-Human-in-the-loop审批机制.md)

## 背景

Another Atom 会替用户生成和修改代码，但用户已经提出“创建、修改或修复应用”时，这个请求本身已经授权正常范围内的执行。如果每个 Blueprint、角色交接和版本保存都再次确认，Approval 会变成没有新增信息的流程阻塞；如果完全不确认，范围适配、额外预算、破坏性修改和线上变化又可能超出用户本轮授权。

本文集中定义 V1 在什么情况下自动继续、什么情况下暂停、用户需要看到什么，以及批准、拒绝、取消和对象变化后的产品语义。Approval 保护的是具体副作用，不是让用户替 Agent 审核每一步推理。

## 摘要

- **默认授权**
  - 用户明确要求创建或修改应用后，普通 supported 构建、当前范围内修改和基础预算内执行自动继续，不设置固定 Blueprint 审批门。
- **风险触发**
  - adapted 映射、产品范围变化、额外预算、破坏性代码或工作区操作、版本切换及公开状态变化必须由用户确认。
- **精确对象**
  - Approval 必须说明正在确认的 Project、范围或 Artifact、基线版本、实际影响和预算；对象变化后旧批准失效。
- **对话连续性**
  - pending、批准、拒绝、成功和失败都写回 Project 对话；已经生成的结构化 Artifact 与确定性证据继续保留。
- **无副作用拒绝**
  - 未批准、拒绝、取消或批准失效时，不追加预算、不移动当前版本、不丢弃未提交修改，也不改变线上内容。
- **能力边界**
  - Approval 不能把 Runtime 不支持的能力变成可执行能力，也不能覆盖 Validator、安全策略、用户归属或版本并发检查。

## 1. 产品结论

V1 将 Project 对话作为用户控制 Agent 工作的主时间线，将 Run 视为其中一次执行尝试，将 Approval 视为某个风险动作前的暂停点：

```text
Project 对话
    |
    v
用户提出创建 / 修改 / 修复
    |
    v
Runtime 判断是否仍在本轮授权范围
    |
    +-- 正常范围 ----------------------> 自动继续
    |
    `-- 范围 / 预算 / 破坏性 / 公开变化
                 |
                 v
           内联 Approval 卡片
                 |
        +--------+---------+
        |        |         |
      批准      调整      拒绝/取消
        |        |         |
        v        v         v
    校验对象后   形成新对象  保留当前安全状态
      继续执行   重新判断
```

Approval 不用于证明用户“看过”每个 Agent 输出。Blueprint、Diff、ValidationReport 和 ReviewReport 始终可以检查；只有下一步将超出已有授权或产生高影响副作用时才暂停。

## 2. 三种控制方式

### 2.1 请求本身构成基础授权

用户明确要求“创建这个应用”“在当前项目中增加筛选”“修复这个报错”时，已经授权系统在以下边界内完成一次执行：

- 保持已确认的产品类型、页面和核心模块范围；
- 使用 V1 已声明支持的自包含 Web Runtime；
- 使用本轮基础团队调用预算；
- 只创建新的工作版本，不改变线上版本；
- 不丢弃 dirty worktree、不删除 Project、不读取未授权外部资源。

在这些边界内再次显示“是否允许 Agent 工作”没有新增决策价值，因此自动继续。

### 2.2 风险 Approval

系统发现下一步超出基础授权时，先生成可检查的风险对象，再等待决定。用户批准的是本次明确变化，不是对当前 Project 或 Agent 的长期放权。

### 2.3 明确操作本身构成确认

用户主动点击已经完整展示对象与后果的 Save Version、Publish 或 Update 时，该点击可以直接构成该动作的确认，不再叠加内容相同的第二个弹窗。以下情况仍需额外确认：

- 删除 Project 或丢弃未提交修改等难以恢复的动作；
- 当前页面没有展示目标版本、公开影响或被覆盖对象；
- 用户点击后目标对象已经变化，需要重新核对。

资源选择也属于显式授权：本地文件夹必须由用户通过浏览器选择，外部 Git 仓库必须由用户选择并授权。平台不能把 Approval 当成扫描用户电脑或外部账号的泛化许可。

## 3. 什么时候需要 Approval

### 3.1 触发矩阵

| 风险类型 | 典型触发 | 用户需要看到 | 未批准时 |
| --- | --- | --- | --- |
| 范围适配 | `support_level=adapted`，部分需求被映射、替换或舍弃 | 原目标、映射项、舍弃项、可交付结果 | 不进入构建 |
| 范围变化 | Follow-up 或修复新增、删除、替换页面或核心模块 | 当前范围、新范围、保持不变项 | 不执行范围变化 |
| 额外预算 | 超出基础预算，追加 retry/rework 或额外模型调用 | 已用额度、追加额度、最大上限、用途 | 不预占或消耗额外额度 |
| 破坏性代码变化 | 实际 Diff 大面积删除、删除入口或覆盖关键模块 | 基线版本、变更文件、删除量、可回退结果 | 候选 Artifact 保留但不提交版本 |
| 工作区破坏 | 丢弃 dirty worktree、强制重置、删除 Project | 会丢失或删除的对象、是否可恢复 | 原工作区和 Project 保持不变 |
| 版本切换 | Restore 改变当前工作版本 | 当前版本、目标版本、新版本语义 | 当前版本指针不变 |
| 公开状态变化 | Publish、Update、Unpublish | 目标版本、公开 URL、线上变化 | 线上版本不变 |
| 能力适配 | 当前 Runtime 只能用受限 Web 方式实现部分要求 | 能实现什么、不能实现什么、替代方式 | 不按适配方案执行 |

`unsupported`、越权访问、跨用户资源、Validator mandatory failure 和平台安全错误不属于“用户批准即可继续”的风险。系统必须拒绝或进入 Needs input，不能生成一个 Approval 让用户替平台承担不可执行结果。

### 3.2 不触发 Approval

以下动作在对象和边界未变化时自动继续或由操作按钮直接确认：

- supported Blueprint 的首次构建；
- 当前页面和模块范围内的文案、样式和现有交互修改；
- 明确应用错误的受限修复；
- 基础预算内的固定团队调用和有限 Schema retry；
- 查看 Preview、文件、Diff、Artifact、日志和版本历史；
- 打开受限 Vim、编辑临时 worktree；
- 用户显式 Save Version，且页面已展示保存对象与 Diff；
- 创建新工作版本但不改变 Public Route。

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

- **批准并继续：** 仅授权卡片中的精确对象；Runtime 重新校验对象未变后继续一次。
- **调整方案：** 回到对话或可编辑 Artifact，用户修改范围、预算或目标；修改后形成新对象并重新判断。
- **拒绝：** 明确不接受当前提案，Run 进入 Needs input 或结束本次动作，保留已有对话和 Artifact。
- **取消：** 放弃本次等待中的动作，不代表否定 Project；不产生额外模型调用和副作用。

V1 不提供“本项目以后全部允许”“始终允许这个 Agent”或跨 Project 的永久授权。

## 5. 在 Project 对话中的位置

### 5.1 首次构建

```text
Prompt -> Blueprint -> Risk Policy
                       |-- supported -> 自动进入固定团队
                       |-- adapted   -> Approval -> 固定团队
                       `-- unsupported -> Needs input，不创建 Build Job
```

Blueprint 始终可查看和编辑，但只有 adapted 或其他明确风险命中时才成为阻塞卡片。用户编辑 Blueprint 后，系统以编辑后的内容重新判断，不能沿用编辑前的批准。

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

1. supported 请求展示 Blueprint 后自动继续，不出现无信息量 Approval。
2. adapted 请求展示映射与舍弃项，批准后只执行已展示方案。
3. 当前 Project 内普通修改自动继续，成功后新版本和 Diff 回到对话。
4. 范围变化在执行前暂停；用户批准后基于同一基线继续。
5. 实际 Diff 出现未预期的大面积删除时在提交前暂停，批准前不创建版本。
6. Publish/Update/Unpublish 明确展示目标线上变化，由用户显式执行。

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

- supported Blueprint 自动进入构建；
- adapted Blueprint 进入 `awaiting_approval / blueprint_approval`；
- 等待状态、Blueprint Artifact 和事件持久化；用户确认后再写入 Approval 决定记录；
- 只有 Project 所属用户可以确认；
- 状态 CAS 与唯一 BuildJob/Approval 约束阻止重复排队；
- 刷新后可恢复等待状态，确认后进入现有 Build Worker。

尚未完整实现：

- 通用 Approval 类型、`rejected / cancelled / stale` 决定接口；
- pending Approval 的独立数据记录；当前等待事实仍由 Run 状态和事件表达；
- 对话修改中的范围、预算与破坏性 Diff Risk Policy；
- Approval 绑定统一 subject version/hash，以及对象变化后的失效流程；
- dirty worktree、Restore、删除和 Deployment 共用的审计 Contract；
- Approval 请求与决定作为完整结果卡片写回 Project 对话。
