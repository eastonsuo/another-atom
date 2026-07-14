# Another Atom V1 统一 Chat 与 Human-in-the-loop

[toc]

- **文档状态：** V1 合并需求设计基线；核心纵切已实现，通用风险适配器与 Stop/Cancel 待完成
- **功能定位：** 用一条 Project Chat 承接问答、PM 需求澄清、用户确认、构建、失败继续和已有代码修改
- **产品基线：** [V1 核心产品需求与交互](./01-核心产品需求与交互.md)
- **相关详细设计：** [对话修改现有项目](./03-通过对话修改现有项目.md) · [Human-in-the-loop 审批](./04-[TODO]-Human-in-the-loop用户审批.md) · [PM 产品方案](./05-[TODO]-PM整理产品方案并由用户确认.md)
- **相关检查：** [19｜统一 Chat 与 HITL 核心纵切检查](../../../review/归档/19-[综合]-2026-07-14-统一Chat与HITL核心纵切检查.md)

## 背景

现有 V1 已经分别具备 Project 修改对话、Blueprint 确认和失败重试的部分能力，但它们仍是三条分散链路：Lead 问答不进入 Project 时间线，PM 缺少信息时只能结束 Run，确认和补充输入也没有共享统一的持久化暂停与恢复语义。

本文将这些需求合并成一个 V1 功能：用户始终在同一条 Project Chat 中与 Lead 交互；如果需要团队执行，PM 可以先补齐需求；缺少信息或遇到真实风险时，Runtime 持久化暂停并等待用户；用户回复后恢复原 Run，不重新创建一次无关构建。

## 摘要

- **统一对话**
  - 首次创建、已有项目修改、失败后继续都写入 Project Chat，消息、Run、产物和版本可以相互追溯。
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
2. **[Lead 路由]** Lead 对每条消息只产生 `direct` 或 `team`；`direct` 直接回答或澄清意图，`team` 才进入 PM。
3. **[PM 澄清]** PM 有责任判断构建所需信息是否足够；不足时不擅自补设定，而是向用户提问。
4. **[通用 HITL]** 用户补充信息和用户批准风险是两种不同 Human Task，但共用同一套持久化暂停、权限校验、CAS 决策和幂等恢复。
5. **[方案确认]** Blueprint 仍是可检查的产品 Contract。已明确授权且在基础预算内的 `supported` 工作可自动继续；`adapted`、范围变化、额外预算和破坏性操作需要 Approval。
6. **[已有项目修改]** 用户可继续与 Lead 对话，团队基于现有代码而不是原 Prompt 重建，成功后形成新版本。
7. **[失败后继续]** 生成或校验失败后保留 Artifact 和错误证据；用户可继续对话、补充或修改要求，不强制回到首页重新建项目。

## 2. 用户主链路

```text
统一 Project Chat
        |
        v
     Lead 路由
        |
        +-- direct --> Lead 回答 / 意图澄清
        |
        `-- team ----> PM 整理需求
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
                         +-------------------------+------------------+
                         |                                            |
                  supported + 基础授权                     适配 / 新风险
                         |                                            |
                         v                                            v
                      自动继续                                  Approval
                         |                                            |
                         `-------------------+------------------------'
                                             v
                   PM -> Architect -> Engineer -> Data Analyst
                                  -> Runtime Validator -> Reviewer
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

用户明确要构建后创建 Project 和 Run，原始消息立即写入 Project Chat。PM 可以直接产出 Blueprint，也可以暂停等待补充。这一阶段不创建 Build Version。

### 5.2 修改现有项目

每条修改消息先经过 Lead：

- `direct` 只在 Chat 中返回答案，不获取 Project 写锁，不创建新版本；
- `team` 先由 PM 检查修改目标和保留项，必要时通过 Input Request 补充；
- 只有信息足够且即将执行代码写入时才原子获取 Project 单写占用；
- 修改始终以提交消息时的 ProjectVersion 为基线。如果等待补充期间基线已改变，原任务进入 `stale`，用户需要基于新版本重新发起。

### 5.3 失败后继续

失败不等于删除本轮工作。系统保留：

- 已成功阶段的 Artifact；
- Validator / Reviewer 的 Evidence 和错误代码；
- Provider 用量与已结算配额；
- 本轮原始要求、PM 补充和失败摘要；
- 上一个可用 ProjectVersion。

用户可以在 Chat 中说“按照这个错误修复”或调整需求。新的执行 attempt 引用上一次失败摘要，但以上一个成功版本为代码基线；不得将未通过校验的候选代码冒充当前版本。

## 6. 状态与用户可见行为

```text
running
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

本轮不将以下能力暗示为已完成：

- V2 动态 TaskGraph、角色子集和并行执行；
- 长期 Agent Memory 或基于向量检索的 RAG；
- 外部 Git 或用户本地代码的无授权读取；
- 任意 Shell、动态依赖安装或绕过 Sandbox 的执行；
- ProductSpec 已能写入 `docs/product-spec.md` 并作为 adapted 确认页的查看对象；完整 generation、编辑失效、重新生成和显式 Architect Handoff 仍待完成，当前 PM 的下游可执行 Contract 仍是同源 Blueprint。
- 通用 Stop/Cancel API、富 Diff 消息卡片和所有风险类型的业务适配器。

## 8. 验收标准

1. 详细构建要求不被无意义地追问，信息确实不足时才创建 Input Request。
2. Input Request 刷新页面和重启服务后仍存在，用户可继续回复。
3. 同一 Input Request 并发回复只有一次生效，原 Run 只恢复一次。
4. 非归属用户无法读取或处理 Human Task。
5. 已有 Project 在等待 PM 补充时不长期占用写锁；真正开始代码写入前必须重新检查基线版本。
6. `direct` 回答不创建 ProjectVersion；`team` 成功修改会创建新版本，不改变线上发布指针。
7. 失败后 Artifact、错误和上一成功版本均可见，后续 Chat 不会把失败候选代码当成已发布或已成功版本。
