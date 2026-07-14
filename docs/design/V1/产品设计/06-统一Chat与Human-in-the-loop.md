# Another Atom V1 统一 Chat 与 Human-in-the-loop

[toc]

- **文档状态：** V1 合并需求设计基线；Project 默认对话、修改授权与 Context 传递存在实现偏差，见 Review 20
- **功能定位：** 用一条 Project Chat 承接问答、PM 需求澄清、用户确认、构建、失败继续和已有代码修改
- **产品基线：** [V1 核心产品需求与交互](./01-核心产品需求与交互.md)
- **相关详细设计：** [对话修改现有项目](./03-通过对话修改现有项目.md) · [Human-in-the-loop 审批](./04-[TODO]-Human-in-the-loop用户审批.md) · [PM 产品方案](./05-[TODO]-PM整理产品方案并由用户确认.md) · [常驻流式对话与执行期间输入控制](./07-常驻流式对话与执行期间输入控制.md)
- **相关检查：** [19｜统一 Chat 与 HITL 核心纵切检查](../../../review/归档/19-[综合]-2026-07-14-统一Chat与HITL核心纵切检查.md) · [20｜Project 对话路由与代码修改授权检查](../../../review/待办/20-[综合]-2026-07-14-Project对话路由与代码修改授权检查.md) · [24｜首次需求结构化澄清检查](../../../review/待办/24-[产品]-2026-07-14-首次需求结构化澄清.md)

## 背景

现有 V1 已经分别具备 Project 修改对话、Blueprint 确认和失败重试的部分能力，但它们仍是三条分散链路：Lead 问答不进入 Project 时间线，PM 缺少信息时只能结束 Run，确认和补充输入也没有共享统一的持久化暂停与恢复语义。

本文将这些需求合并成一个 V1 功能：用户始终通过同一条 Project Chat 与 AI 团队沟通，内部由 Lead 接收并路由消息；如果需要团队执行，PM 可以先补齐需求；缺少信息或遇到真实风险时，Runtime 持久化暂停并等待用户；用户回复后恢复原 Run，不重新创建一次无关构建。

## 摘要

- **统一对话**
  - 首次创建、已有项目修改、失败后继续都写入 Project Chat，消息、Run、产物和版本可以相互追溯。
- **首次结构化澄清**
  - 首次入口区分回答、结构化澄清和进入团队；模糊构建意图先由用户完成关键单选项，再把原始需求和选择交给 PM。
- **先对话再执行**
  - Project 消息先由带 Project Context 的 Lead 回答、澄清或提出修改；提出修改不等于执行，用户确认“修改代码”后才创建 Run。
- **PM 对话式澄清**
  - 信息足够时生成 Blueprint 并继续；信息不足时在 Chat 中提出一个聚焦问题，用户回复后恢复原 Run 的 PM 阶段。
- **通用 Human-in-the-loop**
  - 补充输入和风险确认共用归属、状态、并发、失效、恢复和审计机制，但保留不同的产品语义。
- **基于现有代码继续**
  - 已有 Project 的修改以当前 ProjectVersion 和 Git commit 为基线，默认保留未要求变化的内容。
- **失败不丢失上下文**
  - 失败 Run 保留已生成 Artifact、确定性证据和错误摘要；用户可在原 Project Chat 中继续，新尝试从上一个成功版本开始。

## 1. 本合并需求覆盖什么

本功能同时覆盖七个已提出的需求：

1. **[统一 Chat]** 用户不再分别面对首页输入、PM 补充页、失败重试和项目修改入口；这些交互统一投影到 Project Chat。
2. **[Lead 路由]** 首次创建入口使用 `direct | clarify | team`；`clarify` 只收集会实质改变交付结果的结构化选择，不创建 Run。已有 Project Chat 使用 `answer | clarify | propose_change`，前两者只写回对话，后者先形成待确认修改任务。
3. **[PM 澄清]** PM 有责任判断构建所需信息是否足够；不足时不擅自补设定，而是向用户提问。
4. **[通用 HITL]** 用户补充信息和用户批准风险是两种不同 Human Task，但共用同一套持久化暂停、权限校验、CAS 决策和幂等恢复。
5. **[方案确认]** 产品规格（ProductSpec）是可检查的产品契约（Contract）。`supported` 与 `adapted` 都必须由用户确认产品规格后才能进入架构和工程阶段；架构设计默认不增加强制确认，只有其要求改变已确认产品边界时才退回产品规格重新确认。额外预算和破坏性操作仍需要绑定具体对象的批准（Approval）。
6. **[已有项目修改]** 用户可继续通过 Project Chat 与 AI 团队沟通，内部由 Lead 处理消息；团队基于现有代码而不是原 Prompt 重建，成功后形成新版本。
7. **[失败后继续]** 生成或校验失败后保留 Artifact 和错误证据；用户可继续对话、补充或修改要求，不强制回到首页重新建项目。

## 2. 用户主链路

首次创建入口先经过独立的 Lead 判断：

```text
首次消息
   |
   v
 Lead
   |-- direct  --> 回答问题，不创建 Project / Run
   |-- clarify --> 结构化单选问题 --> 用户完成选择 --> 下一步
   |                                             |
   `-- team -------------------------------------'
                                                 v
                                   创建 Project / 首次 Run
                                                 |
                                                 v
                                    PM 整理 ProductSpec
```

`clarify` 每轮包含一至四个问题，每题二至六个互斥选项；界面额外提供“暂不确定”。未完成全部选择时不能进入下一步。下一步只授权进入 PM 产品整理阶段，不能跳过 ProductSpec 确认，也不能直接进入 Architect 或 Engineer。

```text
统一 Project Chat
        |
        v
     Lead 路由（含 Project Context）
        |
        +-- answer / clarify --> Lead 回答 / 意图澄清，不创建 Run
        |
        `-- propose_change --> 修改任务卡 + “修改代码”
                                    |
                                用户批准
                                    |
                                  PM 整理需求
                          |
                          +-- 信息不足
                          |      |
                          |      v
                          |  补充输入任务（Input Request）
                          |      |
                          |   用户回复
                          |      |
                          |      `----> 恢复原 Run 的 PM 阶段
                          |
                          `-- 信息足够 --> Blueprint / 需求差量
                                                   |
                                             Risk Policy
                                                   |
                                             |
                                             v
                                   ProductSpec Approval
                                             |
                                             v
                   产品经理（PM）-> 架构师（Architect）-> 工程师（Engineer）
                                  -> 运行系统构建 / 测试 / 校验（Runtime Build / Test / Validator）
                                             |
                                  +----------+-----------+
                                  |                      |
                                成功                    失败
                                  |                      |
                           新 ProjectVersion      保留 Artifact / Evidence
                                  |                      |
                                  `----------> 回到同一 Chat <---'
```

## 3. Human Task 是什么

Human Task 是 Runtime 中一个可持久化的“等待用户”对象，不是一个仅存在于前端的弹窗。V1 先实现两种：

- **[补充输入 `input_request`]** 缺少必要信息时，记录问题、缺失项、所属 Run 和应恢复的阶段。用户提供的是信息，不是“批准风险”。
- **[风险确认 `approval`]** 下一步会改变已确认范围、追加预算或产生高影响副作用时，记录被确认对象、风险、对象版本和批准后恢复点。

它们共用以下不变量：

1. Human Task 绑定 `user_id / project_id / run_id`，只允许归属用户查看和处理。
2. Human Task 和 Run 的状态迁移在同一事务内分别使用数据库 CAS；只有两者都成功，决策才生效，approve/reject、重复回复和并发请求不能留下半决状态。
3. 用户回复、决策和恢复结果都写入 Project Chat 和 Run Event。
4. 依赖的 Blueprint、代码基线或预算对象变化后，旧任务进入 `stale`，对应 Run 进入带明确错误码的终态，不能继续使用旧决定。
5. Runtime 重启后能从持久化 Human Task 判断 Run 正在等待谁、等待什么，不依赖内存回调。
6. 相同回复的幂等重试不仅返回原 Run；如果上次提交已落库但执行派发丢失，Runtime 会按 Run 的 `trigger` 和当前阶段重新派发。
7. 首次构建的 `product_running` 由 Blueprint recovery 恢复；`ai_edit` 的恢复只依赖持久化 BuildJob 和 Worker，不得重放首次 Blueprint 流水线。

## 4. PM 澄清规则

PM 只在缺少会实质改变交付结果的信息时提问。能从用户原话和已有 Project Context 得出的信息，不要再问一次。

一次只提一个能推进结果的聚焦问题。如果有多个缺失项，合并成用户可一次回答的问题，不转成问卷。

用户回复后：

1. 回复追加到原 Run 的可见 Context；
2. 原 `input_request` 原子变为 `answered`；
3. 同一 Run 回到 PM 阶段重新判断；
4. 信息仍不足时可以创建下一个 Input Request，但不允许无上限自动循环；
5. 信息足够后创建 Blueprint 或 RequirementDelta，再进入 Risk Policy 和下游执行。

## 5. 首次构建、现有项目和失败继续

### 5.1 首次构建

用户明确要构建后创建 Project 和 Run。若 Lead 判断用户已有构建意图但缺少关键产品选择，先返回结构化澄清；用户完成选择后，原始需求和选择结果按固定格式组成首次 Run Prompt。PM 可以直接产出 Blueprint，也可以对尚未确定的关键事实暂停等待补充。这一阶段不创建 Build Version。

### 5.2 修改现有项目

每条 Project 消息先经过 Lead：

- `answer / clarify` 只在 Chat 中返回结果，不创建 Run、BuildJob，不获取 Project 写锁；
- Lead 路由必须接收当前产品身份、有效 ProductSpec/Contract 摘要、版本、源码清单和最近可见对话；
- `propose_change` 先形成 ChangeBrief 和绑定当前基线的 pending `project_change` Approval；
- 用户点击“修改代码”后才创建 `ai_edit` Run，由 PM 检查修改目标和保留项，必要时通过 Input Request 补充；
- 批准事务重新验证基线，成功后才原子获取 Project 单写占用；
- 修改始终以提交消息时的 ProjectVersion 为基线。如果等待补充期间基线已改变，原任务进入 `stale`，用户需要基于新版本重新发起。

### 5.3 失败后继续

失败不等于删除本轮工作。系统保留：

- 已成功阶段的 Artifact；
- 运行系统构建、测试与校验器（Runtime Build / Test / Validator）的证据（Evidence）和错误代码；
- Provider 用量与已结算配额；
- 本轮原始要求、PM 补充和失败摘要；
- 上一个可用 ProjectVersion。

用户可以在 Chat 中说“按照这个错误修复”或调整需求。新的执行 attempt 引用上一次失败摘要，但以上一个成功版本为代码基线；不得将未通过校验的候选代码冒充当前版本。

## 6. 状态与用户可见行为

```text
Project Chat message
  |-- answer / clarify --> completed message（无 Run）
  `-- propose_change --> pending project_change approval
                              |-- approve --> create ai_edit Run
                              `-- reject / stale --> 保持当前版本

ai_edit Run
  |-- 等待补充 --> needs_input + pending input_request
  |                         |-- 用户回复 --> running（原 Run）
  |                         `-- 基线变化 --> cancelled + stale + BASE_VERSION_CHANGED
  |
  |-- 等待确认 --> awaiting_approval + pending approval
  |                         |-- approve --> running（原 Run）
  |                         `-- reject  --> cancelled / needs_input
  |
  |-- 成功 --> completed / completed_degraded
  `-- 失败 --> failed（保留 Artifact，Chat 可继续）
```

界面必须展示：

- 当前是 Lead、PM 还是下游团队在工作；
- 系统正在等待用户补充信息，还是等待批准某个对象；
- PM 的具体问题、Approval 的对象与影响；
- 用户回复后是否已恢复原 Run；
- 当前修改的基线版本；
- 失败后已保留什么，用户可以怎样继续。

## 7. 当前实现边界

当前代码已经完成以下 V1 纵切：

1. 持久化 Human Task，实现 `input_request` 和 `approval` 的共享状态与归属校验；
2. PM 可以返回 `ready` 或 `needs_input`，后者在 Project Chat 中显示问题；
3. 用户回复 Input Request 后幂等恢复原 Run，不创建新项目；
4. 首次构建和已有 Project 修改都把用户消息、PM 问题和回复写入 Project Chat；
5. 失败页不再把 `ai_edit` 重试错路由为首次 Build，用户可以基于已保留结果继续对话；
6. 修复 Project 写占用、等待阶段和恢复之间的并发边界；
7. 增加主链、重复回复、越权、持久化恢复、已有代码修改和失败继续测试。
8. stale 时同步终结 Run、记录系统消息并引导用户基于当前版本重发；`ai_edit` 重启恢复不会进入首次 Blueprint 流水线。
9. 已有 Project 消息先组装 Project Context，再由 `ProjectLeadDecision(answer|clarify|propose_change)` 路由；answer/clarify 不创建 Run。
10. `propose_change` 形成持久化修改任务卡；点击“修改代码”后才创建执行 Run、BuildJob 和写占用；重复批准返回同一 Run，旧基线任务进入 stale。
11. Project Lead Context 包含当前有效文档、Project 对话与按固定源码字符预算装箱的基线源码，并保存 Context hash 和源码清单供排障。

当前与目标设计不一致、必须修复的部分：

- Project Lead 路由仍为同步 HTTP 调用，缺少可重启恢复的 ConversationJob 和消息 idempotency key；
- 修改任务卡尚未使用通用 Approval subject；当前专用 proposal 状态支持 pending、approved、stale 和幂等批准，但不支持独立 reject/cancel；
- 批准前只有 Lead change summary，完整 ChangeBrief 在批准后的 Run 内产生；
- 工程师（Engineer）已接收完整产品规格（ProductSpec）、有效契约（Contract）和按固定字符预算装箱的基线源码；但仍返回完整网页应用规格（Web AppSpec），架构设计（ArchitectureDesign）、通用源码包（SourceBundle）、单元测试和隔离构建/测试（Build/Test）尚未实现；

本轮也不将以下能力暗示为已完成：

- V2 动态 TaskGraph、角色子集和并行执行；
- 长期 Agent Memory 或基于向量检索的 RAG；
- 外部 Git 或用户本地代码的无授权读取；
- 任意 Shell、动态依赖安装或绕过 Sandbox 的执行；
- ProductSpec 已能写入 `docs/product-spec.md` 并作为 adapted 确认页的查看对象；完整 generation、编辑失效、重新生成和显式 Architect Handoff 仍待完成，当前 PM 的下游可执行 Contract 仍是同源 Blueprint。
- 通用 Stop/Cancel API、富 Diff 消息卡片和所有风险类型的业务适配器。

## 8. 验收标准

1. 首次模糊构建意图返回结构化单选问题，不再以 `direct` 自由文本和“调用团队”混合表达；完成选择前不创建 Project 或 Run。
2. 首次结构化选择完成后只创建一个 Run，Prompt 同时包含原始需求和按问题顺序组成的选择结果；PM 和 ProductSpec 确认仍然执行。
3. 详细构建要求不被无意义地追问，信息确实不足时才创建 Input Request。
4. Input Request 刷新页面和重启服务后仍存在，用户可继续回复。
5. 同一 Input Request 并发回复只有一次生效，原 Run 只恢复一次。
6. 非归属用户无法读取或处理 Human Task。
7. 已有 Project 在等待 PM 补充时不长期占用写锁；真正开始代码写入前必须重新检查基线版本。
8. `answer / clarify` 不创建 Run、BuildJob、写占用或 ProjectVersion；批准后的修改成功才创建新版本，且不改变线上发布指针。
9. Lead 路由和直接回答能引用当前 Project 的产品身份、版本、有效方案与最近对话；跨 Project Context 不得混入。
10. `propose_change` 只创建修改任务与 pending Approval；用户点击“修改代码”后才创建一个 `ai_edit` Run。
11. 工程师（Engineer）修改输入包含完整有效产品规格（ProductSpec）、架构设计（ArchitectureDesign）、应用规格（AppSpec）清单，以及固定字符预算内的基线源码包（SourceBundle）；源码未超限时全量发送，超限时按文件裁剪，并记录包含和省略清单。
12. 失败后 Artifact、错误和上一成功版本均可见，后续 Chat 不会把失败候选代码当成已发布或已成功版本。
