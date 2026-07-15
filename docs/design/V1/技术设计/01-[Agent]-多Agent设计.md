# Another Atom 第一版多智能体（Agent）设计

[toc]

- 文档状态：V1 已实现基线；Railway 独立执行服务部署验收待完成
- 更新日期：2026-07-15
- 产品设计：[Another Atom V1 核心产品需求与交互](../产品设计/01-核心产品需求与交互.md)
- 工程设计：[Another Atom V1 系统架构](./03-[工程]-系统架构.md)
- 执行服务：[Another Atom V1 共享独立执行服务](./08-[工程][TODO]-共享独立执行服务.md)
- 当前实现：[Another Atom V1 关键设计与实现 Review](../../../review/归档/08-[综合]-2026-07-12-关键设计与实现检查.md)
- 整体产品：[Another Atom 整体产品目标与定位](../../整体/01-[产品]-整体产品目标与定位.md)
- 问题整理：[多角色 Agent 设计问题整理](../../../review/归档/10-[Agent]-2026-07-13-多角色Agent设计问题整理.md)
- 本次修订来源：[多角色职责与交付边界检查](../../../review/待办/23-[综合]-2026-07-14-多角色职责与交付边界检查.md)
- 修复契约检查：[首次生成修复与流式事件批处理](../../../review/待办/27-[Agent]-2026-07-15-首次生成修复与流式事件批处理.md)
- 演进讨论：[Agent Runtime 边界与演进讨论](../../../review/归档/09-[Agent]-2026-07-12-Agent-Runtime边界与演进讨论.md)
- V2 演进：[Another Atom V2 任务编排与多 Agent 协作](../../V2/技术设计/01-[Agent]-任务编排与多Agent协作.md)

## 背景

V1 需要让产品、架构和工程三种专业分工可检查、可恢复且能在有限成本内完成交付，不依赖开放式智能体（Agent）自主循环。本次修订前，产品经理（Product Manager）已能产出代码库中的完整产品规格（ProductSpec），但架构师（Architect）仍只输出短字段集合，工程师（Engineer）仍只输出三段网页（Web）源码，而数据分析师（Data Analyst）与质量评审员（Reviewer）在没有被证明的独立收益下增加了固定调用和失败面。

本次修订根据第二十三号评审（Review 23）将 V1 专业角色收敛为产品经理（Product Manager）、架构师（Architect）和工程师（Engineer），并将交付主线改为产品规格（ProductSpec）文档、架构设计文档、项目源码与单元测试。数据分析师（Data Analyst）和质量评审员（Reviewer）在 V1 新运行（Run）中暂不启用；确定性构建（Build）、测试（Test）和校验器（Validator）仍是必经工程门禁。

截至 2026-07-15，三角色链路、架构设计文档、源码包（SourceBundle）、工程师单元测试和共享独立执行服务调用已经写入代码并通过本地自动化验证。尚未完成的是 Railway 私网部署和真实多用户环境验收，不能把本地实现等同于已上线能力。

## 摘要

- **入口路由**
  - 团队负责人（Lead）只执行 `direct/team` 二选一路由，不动态创建任务图或调整权限。
- **固定三角色**
  - 团队（Team）只顺序运行产品经理（Product Manager）、架构师（Architect）和工程师（Engineer）。数据分析师（Data Analyst）与质量评审员（Reviewer）保留历史数据兼容，不再是 V1 新运行（Run）的必经阶段。
- **文档与源码交接**
  - 产品经理（Product Manager）交付已批准产品规格（ProductSpec），架构师（Architect）交付代码库中的架构设计文档，工程师（Engineer）交付项目源码、单元测试和必要测试配置。
- **工程自测闭环**
  - 工程师（Engineer）对构建和单元测试通过负责；运行系统（Runtime）在沙箱（Sandbox）中用固定适配器（Adapter）执行，并将不可改写的失败证据返回工程师有限修复。
- **确定性验收**
  - 构建（Build）、测试（Test）和校验器（Validator）生成独立证据（Evidence）；全部强制检查（mandatory check）通过后才能创建项目版本（ProjectVersion）和预览（Preview）。
- **控制边界**
  - 身份、权限、配额、代码写入和发布由平台运行系统（Runtime）控制；动态任务图（TaskGraph）、角色自主委派和开放工具（Tool）属于 V2。

**术语约定：** 本文的专业角色、交付契约和运行阶段统一使用“中文名称（英文标识）”。代码字段、枚举值、事件名和文件路径保留英文，并在相邻文字或表格语义列中给出中文含义；不把程序真实标识翻译成无法与代码对应的中文字段。


## 1. 设计结论

V1 采用 **团队负责人（Lead）二选一路由 + 文档驱动的固定三角色团队**，不是经典推理与行动循环（ReAct），也不是开放式自主智能体（Autonomous Agent）。

项目类型不由智能体（Agent）流程预设。团队负责人（Lead）和产品经理（Product Manager）必须保留用户指定的软件类型与目标平台；进入架构师（Architect）/工程师（Engineer）阶段后，运行系统（Runtime）应选择匹配的源码和运行契约（Contract）。当前实现只有网页应用规格（Web AppSpec），因此只有网页（Web）项目能进入完整生成、预览（Preview）和公开路由（Public Route）链路；非网页请求不得被改写成网页项目，而应在匹配适配器（Adapter）尚未实现时形成明确能力缺口。

```text
用户消息
   |
   v
Lead Agent -> LeadDecision(route=direct|team)
   |
   +-- direct -> 回答或澄清，不启动团队
   |
   `-- team -> Product Manager -> ProductSpec approval
                -> Architect -> ArchitectureDesign
                -> Engineer -> AppSpec + SourceBundle + unit tests
                -> Runtime Build / Test / Validator
                     |-- pass -> ProjectVersion -> Preview -> User acceptance
                     `-- resolvable -> Engineer repair -> full verification
```

四种范式的区别：


| 范式                                           | V1 是否采用 | 原因                                       |
| -------------------------------------------- | ------- | ---------------------------------------- |
| ReAct：模型循环执行 Action -> Observation -> Action | 否       | V1 不向模型开放 Shell、文件、构建或发布 Tool，不需要开放式工具循环 |
| 开放式 Plan-and-Execute                         | 否       | Lead 不能自由创建任务图、选择任意角色、决定权限、重试次数或发布       |
| Lead 二选一路由                                   | 是       | Lead 只决定直接回答/澄清，或调用完整固定团队；用户可以覆盖为“调用团队”  |
| Contract-first Plan -> Execute -> Validate   | 是       | 团队产生显式产物，平台按固定状态机执行，Validator 决定确定性结果    |


V1 把一次构建拆成四个边界清楚的步骤：

- **[产品（Product）｜明确做什么]** 产品经理（Product Manager）产出完整产品规格（ProductSpec）文档，保留用户的产品类型、核心流程、范围、能力边界和验收条件；用户批准后才进入架构阶段。
- **[架构（Architecture）｜明确如何实现]** 架构师（Architect）读取已批准产品规格（ProductSpec），在代码库中产出完整架构设计文档，明确模块、状态、数据流、接口、失败路径、目录和测试策略。
- **[工程（Engineering）｜代码与自测闭环]** 工程师（Engineer）交付完整项目文件，其中包含实现源码、单元测试和受控测试配置。工程师对通过负责，但不自报执行结果。
- **[验证（Verification）｜工程证据由平台生成]** 运行系统（Runtime）在沙箱（Sandbox）内用固定适配器（Adapter）执行构建和单元测试，校验器（Validator）独立检查范围、安全和能力边界。可修复失败返回工程师，修复后重新执行完整验证。



## 2. V1 角色与契约（Contract）

本节定义第二十三号评审（Review 23）确立的目标契约（Contract）。当前 [Pydantic 模式（Schema）](../../../../another_atom/contracts/schemas.py)和[模型服务（Provider）接口](../../../../another_atom/agent/provider.py)仍保留架构规格（ArchitectureSpec）、网页应用规格（Web AppSpec）、数据分析（DataProfile）和质量评审报告（ReviewReport），不代表这些现状继续作为目标设计。实现必须按本节迁移，并对历史阶段产物（Artifact）保留只读兼容。

### 2.1 固定团队总览


| 角色/阶段 | 要回答的核心问题 | 目标输入 | 目标输出 | 是否模型角色 |
| --- | --- | --- | --- | --- |
| 团队负责人（Lead） | 用户是在询问，还是明确要求构建？ | 当前消息和显式团队覆盖选择 | 团队负责人决策（`LeadDecision`） | 是，但只负责入口路由 |
| 产品经理（Product Manager） | 用户要构建什么，范围和验收条件是什么？ | 用户需求、必要对话和平台能力边界 | 产品规格（`ProductSpec`）文档及产品蓝图（`Blueprint`）结构化索引 | 是 |
| 架构师（Architect） | 已批准产品文档如何落为可实现、可验证的技术方案？ | 已批准产品规格（`ProductSpec`）、产品蓝图（`Blueprint`）索引和运行系统（Runtime）能力清单 | 架构设计（`ArchitectureDesign`）文档及其阶段产物（Artifact） | 是 |
| 工程师（Engineer） | 哪些实际文件实现了产品与架构设计，并如何用单元测试证明关键行为？ | 产品规格（`ProductSpec`）、架构设计（`ArchitectureDesign`）和适配器边界 | 应用规格（`AppSpec`）清单、源码包（`SourceBundle`）与单元测试 | 是 |
| 运行系统构建/测试（Runtime Build/Test） | 项目能否使用受控命令构建，单元测试是否通过？ | 应用规格（`AppSpec`）、源码包（`SourceBundle`）和固定适配器（Adapter） | 执行报告（`ExecutionReport`） | 否 |
| 运行系统校验器（Runtime Validator） | 产品范围、架构映射、源码安全和运行边界是否通过？ | 产品规格、架构设计、应用规格、源码包和执行报告 | 校验报告（`ValidationReport`） | 否 |
| 用户（User） | 当前版本是否符合预期，是否继续修改或发布？ | 预览（Preview）、源码、文档和验证证据 | 验收、修改或发布指令 | 否 |

团队负责人（Lead）只决定是否进入团队；进入 `team` 后只按产品经理（Product Manager）、架构师（Architect）、工程师（Engineer）的顺序执行。构建（Build）、测试（Test）和校验器（Validator）是运行系统（Runtime）的确定性阶段，不计入模型角色。

### 2.2 团队负责人（Lead）：区分询问与明确构建

**职责：** 团队负责人（Lead）是用户入口，只判断本条消息走 `direct` 还是 `team`。`direct` 返回回答或澄清；`team` 表示进入产品经理（Product Manager）、架构师（Architect）、工程师（Engineer）固定三角色团队。它不生成产品规格（ProductSpec），不选择专业角色，不执行工具（Tool），也不改变项目（Project）、版本或发布状态。

**当前输入契约（Contract）：**


| 字段           | 类型与硬约束               | 含义                                            |
| ------------ | -------------------- | --------------------------------------------- |
| `message`    | `str`，去空白后 1–4000 字符 | 用户本条原始消息                                      |
| `force_team` | `bool`，默认 `false`    | 用户显式选择“调用团队”；为 `true` 时直接覆盖模型路由               |
| `model`      | 可选 `str`，1–100 字符    | 选择允许的 Provider 模型；它用于运行配置，不作为 LeadDecision 字段 |


当前实现没有把 Project 摘要、历史对话、能力边界或预算摘要传给 Lead。因而 Lead 只能判断当前消息，不能声称自己已经理解完整 Project Context；Project 对话线程完成后才扩展这一输入。

**输出团队负责人决策（`LeadDecision`）：**


| 字段         | 类型与硬约束          | 语义                                 |
| ---------- | --------------- | ---------------------------------- |
| `route`    | `direct | team` | 唯一路由决定                             |
| `response` | `str`，1–800 字符  | 展示给用户的回答、澄清或团队交接说明                 |
| `reason`   | `str`，1–300 字符  | 可展示、可审计的简短路由依据，不是 Chain of Thought |


API 返回的 `LeadDecisionView` 额外包含 `message_id`、实际 `model` 和可选 `fallback_provider`。原文曾列出的 `intent_summary`、`risk_flags`、`estimated_provider_calls` 和 `clarification_question` 不在当前 Schema 中，不能作为已实现字段引用。

### 2.3 产品经理（Product Manager）：交付完整产品规格（ProductSpec）文档

**职责：** 产品经理（Product Manager）保留用户目标、项目类型和目标平台，把当前需求整理成可阅读、可编辑、可随代码库持久化的完整产品规格（ProductSpec）。产品规格是下游产品事实源；产品蓝图（Blueprint）保留为能力路由和结构化索引，不能取代完整文档交给架构师（Architect）。

**当前已实现：** 运行系统（Runtime）会形成产品规格阶段产物（ProductSpec Artifact），并把完整 Markdown 写入 `docs/product-spec.md`。用户可以在产品方案卡片中查看摘要并打开完整文档。完整生成代次（generation）、编辑失效和重新生成的剩余边界由 [PM 整理产品方案并由用户确认](../产品设计/05-[TODO]-PM整理产品方案并由用户确认.md) 继续约束。

**输出产品规格（`ProductSpec`）：**

| 字段 | 含义 |
| --- | --- |
| `path` | 固定为 `docs/product-spec.md` |
| `summary` | 用户可快速审阅的产品简介 |
| `content` | 完整 Markdown 产品文档 |
| `content_hash` | 用户批准、下游交接和失效检查绑定的内容指纹 |

产品规格（ProductSpec）至少覆盖产品背景、目标用户、核心流程、功能与页面、输入输出、状态与失败反馈、范围与不做事项、运行系统（Runtime）能力边界和可验证验收条件。`supported` 和 `adapted` 都必须由用户确认当前内容指纹后才能交给架构师（Architect）；`unsupported` 不进入架构阶段。

**同源产品蓝图索引（`Blueprint`）：**


| 字段                          | 类型与硬约束                              | 语义                      |
| --------------------------- | ----------------------------------- | ----------------------- |
| `schema_version`            | 固定 `"1.0"`                          | Contract 版本             |
| `project_name`              | `str`，1–80 字符                       | 用户可识别的 Project 名称       |
| `product_type`              | `str`，1–80 字符，默认 `web_application`  | 产品类型标签；该字段本身不扩大 V1 验收范围 |
| `support_level`             | `supported | adapted | unsupported` | 当前能力匹配结论                |
| `support_reasons`           | `list[str]`，最多 8 项                  | 范围结论的可展示依据              |
| `mapped_requirements`       | `list[str]`，最多 12 项                 | 已映射到受控实现的用户要求           |
| `omitted_requirements`      | `list[str]`，最多 12 项                 | 当前实现明确不包含的要求            |
| `rewrite_suggestion`        | 可选 `str`，最多 500 字符                  | 需要用户确认的替代草案；不能只写“请重新描述” |
| `capability_policy_version` | `catalog-v1 | web-v1`，默认 `web-v1`   | 生成 Blueprint 时依据的能力策略版本 |
| `pages`                     | `list[str]`，1–12 项，禁止空标签            | 页面或主要界面                 |
| `modules`                   | `list[str]`，1–20 项，禁止空标签            | 功能模块与关键交互               |
| `visual_direction`          | `str`，1–240 字符                      | 可供 Architect 使用的视觉方向    |
| `data_requirements`         | `list[str]`，最多 8 项                  | 页面需要的数据或本地状态要求          |


`support_level` 的语义：

- `supported`：在当前 V1 受控范围与基础预算内可以继续。
- `adapted`：保留产品目标，但必须删减真实认证、支付、数据库写入、localhost/loopback 和用户设备本地服务等能力，并等待用户确认映射。浏览器可直接访问的公网 API 不因“外部服务”这一名称自动降级。
- `unsupported`：主要目标无法由当前 Runtime 表达；原 Run 进入 `NeedsInput`，不创建 Build Job。

`rewrite_suggestion` 必须保持用户语言和原始目标，并明确替代了什么能力。Blueprint 与 ProductSpec 必须来自同一 generation；任一内容改变都要使已有批准和下游产物失效。

### 2.4 架构师（Architect）：交付代码库中的架构设计文档

**职责：** 架构师（Architect）只回答“已批准产品规格（ProductSpec）如何映射为可实现、可验证的技术方案”。它不重写产品目标，不用颜色和字体代替架构，也不发明当前运行系统（Runtime）不支持的技术能力。

**输入：** 已批准且内容指纹一致的产品规格（ProductSpec）摘要与完整 Markdown、同一代次（generation）的产品蓝图（Blueprint）索引、当前运行时适配器（Runtime Adapter）能力清单。架构师（Architect）不只读产品蓝图，也不接收未筛选的完整聊天历史。

**输出：** `docs/architecture-design.md` 与架构设计阶段产物（`ArchitectureDesign` Artifact）。Markdown 文档是下游技术事实源；阶段产物（Artifact）只记录交接和失效所需的引用，不再保存一份与文档重复的短字段架构。

| 字段 | 含义 |
| --- | --- |
| `path` | 固定为 `docs/architecture-design.md` |
| `summary` | 便于阶段卡片展示的架构摘要 |
| `content` | 完整 Markdown 架构设计文档 |
| `content_hash` | 工程交接与失效检查绑定的架构文档指纹 |
| `product_spec_hash` | 本架构设计所基于的 ProductSpec 指纹 |
| `runtime_adapter` | 实际用于实现、构建和测试的受控适配器 |

架构设计文档根据项目实际需要展开，但至少要回答：

- 目标平台、运行时适配器（Runtime Adapter）和已知能力缺口；
- 页面、入口、模块、组件及各自职责；
- 状态作用域、生命周期、数据流和持久化边界；
- 关键交互的触发、状态转移、成功结果和失败反馈；
- 接口、数据契约、网络与外部能力边界；
- 项目目录与关键文件规划；
- 单元测试策略以及产品规格（ProductSpec）验收条件到工程模块和测试的映射。

产品规格（ProductSpec）中已确认的视觉方向保持为产品事实。如需把它转成可机检的视觉规格（VisualSpec），视觉规格必须引用同一产品规格和架构设计（ArchitectureDesign）指纹，不得成为第二份独立改写产品方向的事实源。

架构设计（ArchitectureDesign）默认不是第二个强制人工确认（Human-in-the-loop，HITL）门禁。产品规格（ProductSpec）已经确认产品事实，架构师只在该边界内做技术展开，用户可在文件面板检查 `docs/architecture-design.md`，流水线默认继续。只有架构师发现实现必须改变已确认的产品范围、目标平台、外部能力或高风险权限时，才设置 `requires_product_reapproval=true`，停止下游工程阶段并回到产品规格确认；不能通过架构确认静默批准产品变更。

**2026-07-15 本地实现：** 架构师已读取当前产品规格（ProductSpec）和产品蓝图（Blueprint），生成 `ArchitectureDesign` 契约和 `docs/architecture-design.md`，记录产品规格指纹、运行时适配器（Runtime Adapter）、模块、状态流、交互、目录、测试策略和验收映射。Studio 在当前运行首次收到新的架构设计指纹时，自动打开项目文件面板并以 Markdown 预览显示该文档；显式的架构文档打开请求优先于同一时刻的后台文件列表刷新和默认 README 选择。该动作不暂停流水线、不增加批准门，也不覆盖未保存的文件修改。切换到已经生成完成的历史运行时不重复弹出。兼容用架构规格（ArchitectureSpec）仍作为 `visual_tokens` 保留，但不再是架构师的主要交付物。Railway 部署环境尚未验收。

### 2.5 工程师（Engineer）：交付项目源码、单元测试并对通过负责

**职责：** 工程师（Engineer）只回答“哪些实际文件实现了产品规格（ProductSpec）和架构设计（ArchitectureDesign），以及如何用单元测试证明关键模块行为”。它不重新定义产品文案和视觉方向，也不能用自报结果代替真实构建与测试。

**输入：** 已批准产品规格（ProductSpec）、与该产品规格指纹对齐的架构设计（ArchitectureDesign），以及主服务已选择的 Runtime Contract 标识、版本、内容指纹和 Engineer 可见要求。已有项目修改还需接收基线源码清单和明确变更要求。Runtime Contract 的选择、字段和校验职责以[通用源码与 Runtime 校验 Contract](./12-[工程][TODO]-通用源码与Runtime校验Contract.md)为事实来源；Engineer 只能原样引用，不能自行选择或改写 Contract。

**输出一：** 应用规格（`AppSpec`）。应用规格（AppSpec）收敛为应用交付清单，不再容纳完整源码或复制产品文案。

| 字段 | 含义 |
| --- | --- |
| `project_type` | 用户已批准的项目类型 |
| `target_platform` | 目标运行平台 |
| `runtime_adapter` | 运行系统（Runtime）允许的固定构建、测试和预览适配器 |
| `entrypoints` | 项目入口文件 |
| `test_entrypoints` | 单元测试入口或测试文件范围 |
| `implemented_capabilities` | 实际代码中已实现的能力 |
| `network_requirements` | 已批准的网络依赖与失败反馈要求 |
| `preview_support` | 当前适配器（Adapter）是否支持预览（Preview）；不支持不等于不能交付源码 |
| `product_spec_hash` | 实现所基于的产品规格（ProductSpec）指纹 |
| `architecture_design_hash` | 实现所基于的架构设计（ArchitectureDesign）指纹 |
| `source_manifest_hash` | 源码包（SourceBundle）的确定性清单指纹 |

**输出二：** 源码包（`SourceBundle`）。

```text
SourceBundle
  files[]
    path
    content_type
    role: source | unit_test | test_config | documentation
    content
  source_manifest_hash
```

源码包（SourceBundle）必须包含实现源码、单元测试和运行所必需的受控配置。工程师（Engineer）不得通过源码包自定义任意终端（Shell）命令、动态安装依赖或扩大网络权限；构建与测试命令只能由运行时适配器（Runtime Adapter）提供。

**“工程师（Engineer）自测”的准确含义：** 工程师交付测试并对构建和测试通过负责；运行系统（Runtime）在隔离沙箱（Sandbox）中执行固定命令，生成执行报告（ExecutionReport），并把可修复失败证据返回工程师。工程师不获得宿主终端（Shell）、密钥（Secret）、平台数据库、Git 远端（remote）或发布权限。

工程师（Engineer）自己编写的单元测试不能代替平台门禁。校验器（Validator）仍要独立检查产品范围、架构映射、源码完整性、安全边界、能力缺口与真实执行报告（ExecutionReport）。

**2026-07-15 本地实现：** 工程师已同时交付应用规格（AppSpec）、`web-static-v1` 源码包（SourceBundle）和 `tests/*.test.js` 单元测试；项目 Git 和项目版本（ProjectVersion）保存源码、测试、源码清单指纹和执行证据。当前应用规格（AppSpec）仍保留网页源码兼容字段，源码包的项目类型也仍只实现 `web-static-v1`，尚未完成面向非 Web 项目的通用清单迁移。该剩余迁移由[通用源码与 Runtime 校验 Contract](./12-[工程][TODO]-通用源码与Runtime校验Contract.md)定义目标设计，并由[第二十二号评审（Review 22）](../../../review/待办/22-[工程]-2026-07-14-Engineer项目源码Contract缺口.md)跟踪实现与验收证据。

### 2.6 运行系统构建、测试与校验器（Runtime Build、Test 与 Validator）：生成不可由智能体（Agent）改写的工程证据

**职责：** 构建工作器（Build Worker）、测试运行器（Test Runner）和校验器（Validator）都不是大语言模型（LLM）角色。运行系统（Runtime）校验 SourceBundle 中由主服务绑定的 Runtime Contract，再由满足该 Interface 的 Adapter 在隔离沙箱（Sandbox）内物化源码包，执行平台固定的构建和单元测试计划，并独立检查产品规格（ProductSpec）、架构设计（ArchitectureDesign）、交付规格、源码包和真实运行证据是否一致。没有 Runtime Binding 的有效源码进入 `source_ready`，不伪造在线执行证据。

**输出一：** 执行报告（`ExecutionReport`）。

| 字段 | 含义 |
| --- | --- |
| `source_manifest_hash` | 本次执行对应的源码包（SourceBundle）指纹 |
| `adapter_id` | 实际使用的固定适配器（Adapter） |
| `build_status` | 构建通过、失败或不适用 |
| `test_status` | 单元测试通过、失败或不适用 |
| `test_summary` | 测试数、通过数、失败数和耗时 |
| `evidence_refs` | 构建日志、测试日志和可定位失败的证据引用 |

**输出二：** 校验报告（`ValidationReport`）。

| 字段 | 含义 |
| --- | --- |
| `passed` | 所有 mandatory check 是否通过 |
| `checks` | 每项确定性检查的状态、根因、可修复性、详情和证据引用 |
| `source_manifest_hash` | 本次校验对应的源码包（SourceBundle）指纹 |
| `execution_report_ref` | 被校验的执行报告（ExecutionReport）引用 |

强制检查（mandatory check）至少包含：产品验收条件映射、架构模块与入口交接、源码完整性、单元测试存在与真实执行结果、能力边界、网络和安全约束。只有全部失败都属于工程师（Engineer）可修复的源码或测试问题时，运行系统（Runtime）才进入一次自动修复；适配器（Adapter）、沙箱（Sandbox）、平台或不明根因不得用智能体（Agent）重写源码来掩盖。

### 2.7 数据分析师（Data Analyst）：V1 暂不启用

V1 新运行（Run）不调用数据分析师（Data Analyst），不生成伪造的空数据分析（DataProfile），也不把数据分析作为创建项目版本（ProjectVersion）的条件。原因是当前产品主链路没有独立数据分析交付，大部分项目只有页面状态或少量内嵌记录，缺少证据证明必经模型调用能带来独立收益。

历史数据分析（DataProfile）和相关模式（Schema）可保留只读兼容，但编排器（Orchestrator）不再进入该阶段。未来如要重新启用，必须先有明确产品场景、独立交付物、真实数据来源、输入指纹和可验证收益，并另行修订正式设计。

### 2.8 质量评审员（Reviewer）：V1 暂不启用

V1 新运行（Run）不调用质量评审员（Reviewer），不生成伪造的空质量评审报告（ReviewReport），也不让模型结论（verdict）决定是否创建项目版本（ProjectVersion）。当前交付门禁由真实构建（Build）、测试（Test）、校验（Validation）证据和用户验收组成：前三者决定工程上是否可交付，用户决定是否继续修改或发布。

历史质量评审报告（ReviewReport）和相关模式（Schema）可保留只读兼容，但质量评审员（Reviewer）失败不再阻断新运行（Run）。未来如要重新启用模型质量评审，必须先证明它能发现确定性门禁和用户验收无法覆盖的问题，而不是为了保留多角色形式而必经调用。

### 2.9 固定交接链路

```text
Lead            -> LeadDecision（direct reply | fixed team）
Product Manager -> ProductSpec + Blueprint index -> User approval
Architect       -> ArchitectureDesign document
Engineer        -> AppSpec + SourceBundle + unit tests
Runtime         -> BuildArtifact + ExecutionReport
Validator       -> ValidationReport
                  |-- pass -> ProjectVersion -> Preview -> User acceptance
                  `-- resolvable -> Engineer repair -> full Build/Test/Validation
```

每个 Agent Artifact 都先经过 Schema 校验再持久化；ProductSpec、ArchitectureDesign 和 SourceBundle 还必须在 Project Git 中有对应文件和内容指纹。下一阶段读取已保存产物，不依赖上一角色的隐藏对话或 Chain of Thought。

### 2.10 二选一路由边界

V1 不再让用户先理解 Engineer Mode / Team Mode。默认入口只有 Lead：

```text
用户询问能力、状态或需求不完整
    -> direct -> Lead 回答或澄清

用户明确要求创建、修改、修复应用
    -> team -> Product Manager -> Architect -> Engineer
```

Lead 不得在 `direct` 路径中偷偷生成 ProductSpec、AppSpec、修改仓库或消耗团队预算。用户可以点击“调用团队”覆盖 direct 判断；进入 team 后，supported 和 adapted ProductSpec 都要求用户确认当前内容指纹，不再另行批准 Blueprint 表单。

## 3. Orchestrator 与执行状态

V1 的 Lead 是独立 Agent，但自主范围只到 `direct/team` 二选一；Runtime 校验 LeadDecision 后推进固定状态机：

```text
Created
  -> LeadRouting
       |-- DirectResponding -> Completed
       `-- TeamQueued
  -> ProductRunning
       |-- Unsupported -> NeedsInput
       `-- ProductSpecReady -> AwaitingProductApproval
  -> ArchitectRunning
  -> EngineerRunning
  -> BuildQueued
  -> Building
  -> Testing
  -> Validating
       |-- pass -> Versioning -> Completed / CompletedDegraded
       |-- resolvable + attempt=0
       |          -> EngineerRepairing -> BuildQueued -> Building -> Testing -> Validating
       `-- otherwise -> Failed -> NeedsInput
```

硬规则：

- Lead 只选择 direct/team；进入 team 后专业角色只有 Product Manager、Architect 和 Engineer，不由模型选择或追加角色。
- ProductSpec 未批准、内容指纹改变或能力结论为 unsupported 时，不得进入 Architect。
- ArchitectureDesign 的 `product_spec_hash` 必须与当前已批准 ProductSpec 一致；AppSpec 与 SourceBundle 必须同时绑定 ProductSpec、ArchitectureDesign 和源码清单指纹。
- 同一时刻一个 Run 只有一个主阶段；重试和修复创建新的 stage attempt。
- 每个阶段必须先持久化输入 Artifact 引用，再调用模型。
- 每个阶段必须先持久化输出，再发送 `stage.completed`。
- Build、Test 和 Validation 必须绑定同一 `source_manifest_hash`；任一修复改变源码后，旧 ExecutionReport 和 ValidationReport 立即失效。
- ProductSpec 确认是首次构建的固定门禁；其他 Approval 由确定性 Risk Policy 根据预算和目标操作决定。
- Publish 不属于 Agent Run，由用户通过独立发布状态机触发。



## 4. Human-in-the-loop



### 4.1 ProductSpec 固定确认与风险驱动确认

首次构建中，`supported` 和 `adapted` ProductSpec 都必须由用户确认当前 summary、Markdown 和内容指纹后才能进入 Architect。这一门禁用于确认产品事实源，不是对普通团队调用的额外风险弹窗。预览、打开 Vim、编辑 worktree 和追加保存 ProjectVersion 不另行审批；其他确认仍由具体后果和风险驱动。


| 确认点            | 触发条件                             | 用户可以做什么              | 未确认时系统行为               |
| -------------- | -------------------------------- | -------------------- | ---------------------- |
| ProductSpec 确认 | 首次生成 supported 或 adapted ProductSpec | 查看摘要和完整文档后确认、拒绝或要求修改 | 不进入 Architect |
| 需求澄清           | Lead 无法确认用户是否要求执行，或缺少关键输入        | 补充信息或明确“调用团队”        | 保持 direct，不创建 Team Run |
| 额外预算确认         | 预计调用超过基础预算、追加 retry/rework 或批量任务 | 接受本轮上限或停止            | 不预占额外额度                |
| 范围变更确认         | 修复或 Follow-up 需要改变已展示范围          | 接受新 Blueprint 或保留原范围 | 自动修改停止，进入 Needs input  |
| Worktree 破坏性确认 | 丢弃未提交修改、强制重置、删除 Project          | 查看影响后确认或取消           | 保留仓库和 dirty worktree   |
| 当前版本切换         | Restore 会创建新版本并改变当前指针            | 确认恢复目标               | 不移动当前版本                |
| 线上变更           | Publish、Update、Unpublish         | 查看目标版本/公开影响后显式执行     | Agent 和平台不改变线上状态       |




### 4.2 Approval Contract

确认必须绑定精确风险对象，而不是只保存一个布尔值：

```text
approval_id
approval_type
project_id
run_id
target_type: artifact | budget | worktree | version | deployment
target_id
target_hash
risk_level: light | destructive | public
effect_summary
requested_by_stage
decided_by_user_id
status: pending | approved | rejected | cancelled
created_at
decided_at
```

规则：

- 只有资源所属用户能审批。
- 目标 Artifact、worktree hash、预算或版本指针变化后，旧 approval 立即失效。
- 页面刷新或服务重启后，Run 从 `pending` approval 恢复，不得自动确认。
- 用户拒绝或取消后保留输入、Artifact、仓库和当前版本，但不预占新额度、不执行破坏性或公开动作。
- 显式点击带完整后果说明的 Save Version / Publish 操作本身可以构成轻确认，不再叠加无信息量的第二个弹窗；不可逆删除仍需要二次确认。



## 5. Context 管理



### 5.1 Context 不是完整聊天历史

V1 不把整个 Session 对话、所有日志和其他角色的隐藏推理直接传给下一角色。当前 Provider 输入由角色 instruction、Pydantic JSON Schema 和阶段 payload 组成：

```text
Stage Context
  = role instruction
  + current Contract JSON Schema
  + current stage payload
```



### 5.2 各阶段当前实际 Context


| 阶段 | 目标传入 Context | 不得传入 |
| --- | --- | --- |
| 团队负责人（Lead） | 当前 `message`；`force_team=true` 时运行系统（Runtime）直接覆盖路由 | 无关源码、密钥（Secret）、其他项目（Project）内容 |
| 产品经理（Product Manager） | 当前需求、必要对话、平台能力边界；修改场景还包含有效产品规格（ProductSpec）和变更范围 | 未筛选日志、密钥、其他项目事实 |
| 架构师（Architect） | 已批准产品规格（ProductSpec）摘要和完整 Markdown、同代次产品蓝图（Blueprint）索引、运行时适配器（Runtime Adapter）能力清单 | 未批准文档、完整聊天、源码、后续阶段内容 |
| 工程师（Engineer） | 已批准产品规格（ProductSpec）、当前架构设计（ArchitectureDesign）、运行时适配器（Runtime Adapter）边界；修改场景还包含基线源码包（SourceBundle）和变更要求 | 宿主文件、密钥（Secret）、其他项目（Project）、未批准阶段产物（Artifact） |
| 工程师修复（Engineer Repair） | 上述全部有效契约（Contract）、当前应用规格（AppSpec）与源码包（SourceBundle）、执行报告（ExecutionReport）、校验报告（ValidationReport）中的可修复证据 | 完整原始日志、平台故障、不可修复失败、发布权限 |

数据分析师（Data Analyst）和质量评审员（Reviewer）在 V1 新运行中没有上下文（Context）组装，因为代码不再调用这两个角色。现有模式（Schema）与旧方法仅用于历史数据兼容，不进入新运行的阶段交接（Handoff）。

### 5.3 Context 持久化与裁剪

- Session 保存用户可恢复的交互边界；Run 保存一次构建/修改任务；StageRun 保存一次角色调用。
- Artifact 使用不可变 ID、版本和 hash 引用，下一阶段不依赖内存对象。
- 当前单实例实现以每类唯一 Artifact 作为阶段恢复检查点；成功输出与该次 Provider usage 在同一事务提交，Worker 重启后直接复用已提交 Artifact。
- 错误上下文只保留错误码、失败 check、evidence ref 和截断摘要，不把无限日志送入模型。
- 每次调用记录 `model`、`prompt_version`、`input_artifact_refs`、`output_artifact_id`、usage 和 attempt。
- 不持久化或展示模型私有 Chain of Thought；只保存结构化输出、决策摘要和可审计证据。



## 6. Tool 设计



### 6.1 V1 Agent 可见 Tool

**默认没有可执行 Tool。** Lead 与 Product Manager、Architect、Engineer 通过显式输入获得所需 Artifact，并只返回经 Schema 校验的产物。Provider Adapter 不开放 Tool Calling；V1 的 Run、文档与源码写入、构建、单元测试、事件、配额和 Trace 由自有 Runtime 管理。

以下能力明确不暴露给模型：

- Shell、Python、Node、npm、Git。
- 任意文件读取或写入。
- 数据库查询与修改。
- Agent Provider 自主发起的 Tool 网络请求。生成应用按已批准 Blueprint 发起的公网 API 请求不属于 Agent Tool；仍受 Preview/Packager 网络边界约束。
- 配额结算。
- Build、Restore、Publish、Update、Unpublish。

Engineer 必须交付单元测试，但“负责自测”不会赋予它 Shell Tool。构建和测试的真实执行只能经由 Runtime 登记的 Adapter 发起。



### 6.2 平台 Runtime 操作

下列是平台内部操作，不是 LLM 可以自行调用的 Agent Tool：


| Runtime 操作                 | 调用者                | 策略                                                              |
| -------------------------- | ------------------ | --------------------------------------------------------------- |
| `load_stage_context`       | 编排器（Orchestrator） | 按用户、项目（Project）、运行（Run）和阶段产物（Artifact）归属读取 |
| `reserve_and_settle_quota` | 智能体服务（Agent Service） | 数据库事务，按每次模型服务（Provider）调用结算 |
| `persist_artifact`         | 智能体服务（Agent Service） | Pydantic 校验成功后写入不可变阶段产物（Artifact） |
| `write_design_document`    | 仓库服务（Repository Service） | 验证产品规格（ProductSpec）指纹后写入 `docs/architecture-design.md`，并保存 Git 与产物引用 |
| `enqueue_build`            | 编排器（Orchestrator） | 团队负责人（Lead）已路由 `team`、风险策略（Risk Policy）已满足且应用规格（AppSpec）有效时执行 |
| `open_editor_session`      | 终端服务（Terminal Service） | 校验认证会话（AuthSession）、项目所有者和单写锁后启动受限 Vim 沙箱 |
| `save_project_version`     | 仓库服务（Repository Service） | 校验执行结果和指纹、持久化源码与产物、创建 Git commit 并写入项目版本（ProjectVersion） |
| `materialize_source_bundle` | 共享执行服务（Runtime Executor） | 将已校验源码包（SourceBundle）物化到单次执行的临时工作目录 |
| `run_fixed_build`          | 共享执行服务（Runtime Executor） | 只执行运行时适配器（Runtime Adapter）配置的固定构建命令 |
| `run_fixed_tests`          | 共享执行服务（Runtime Executor） | 只执行运行时适配器配置的固定单元测试命令并生成执行报告（ExecutionReport） |
| `validate_build`           | 共享执行服务（Runtime Executor） | 基于文档、源码指纹和执行报告产生不可被智能体（Agent）修改的校验报告（ValidationReport） |
| `publish_version`          | 发布服务（Publish Service） | 只接受用户显式请求和合法 `version_id` |


V2 如需开放 Tool，应先引入结构化 `ToolRequest`、独立权限策略、审批和运行级沙箱；不能直接把这些 Runtime 操作注册给 V1 Agent。

当前 `web-static-v1` 适配器已经从应用规格（AppSpec）生成源码包（SourceBundle），在共享独立执行服务的临时目录中物化文件，固定执行 `node --check app.js`、`node --test tests/*.test.js` 和确定性校验，并把执行报告（ExecutionReport）写回主服务。该结论只适用于已登记的受限网页适配器；它不是通用依赖构建、任意 Shell 执行或任务级强沙箱，Railway 部署验收仍以[共享独立执行服务设计](./08-[工程][TODO]-共享独立执行服务.md)为准。

## 7. WebIDE、Sandbox 与执行边界



### 7.1 用户可编辑，但没有宿主 Shell

V1 增加 xterm.js + Vim WebIDE 后，用户可以修改当前 Project 的受控源码路径。xterm.js 只是终端渲染层，不直接连接宿主机；Terminal Service 通过一次性 WebSocket token 连接独立 Editor Sandbox，并固定启动 Vim，不启动 bash/zsh 登录 Shell。

### 7.2 沙箱管理器与共享执行服务

可信沙箱管理器（Sandbox Manager）只在 Linux 编辑宿主机上为每个编辑会话创建无根容器（rootless container）或等价命名空间（namespace）隔离：

- 非 root UID、只读根文件系统、`no-new-privileges`、drop all capabilities、seccomp。
- 默认无网络、无平台数据库连接、无 LLM/API Secret、无 Docker socket。
- 设置 CPU、内存、磁盘、PID、输出和生命周期上限；断开后按 grace period 销毁。
- 只挂载当前会话的临时 worktree；不挂载宿主 repo root，不暴露 `.git`、其他用户目录或绝对宿主路径。
- 编辑沙箱（Editor Sandbox）固定启动受限 Vim，禁用 Shell 逃逸（shell escape）、插件下载和仓库外文件访问。

构建、单元测试和确定性校验不在编辑沙箱宿主机中执行，而是在 Railway 同一项目、同一环境中的共享独立执行服务完成。执行服务使用固定镜像、固定依赖和固定适配器命令；用户不能提交 `package.json` 脚本、修改 lockfile、安装依赖或指定 Shell 命令。该服务与主服务是服务级隔离，不是每任务独立强沙箱。

目录关系：

```text
主服务受信 Git 裸仓库（编辑沙箱不可见）
        |
        | 导出 commit 快照
        v
临时会话工作树 ---- 可读写挂载 ----> 编辑沙箱 / Vim
        |
        | 收集允许路径中的文件为 SourceBundle
        v
主服务派发 -> 共享执行服务构建/测试/校验
        |
        v
仓库服务持久化 -> Git commit -> 项目版本（ProjectVersion）
```



### 7.3 Repository 与写入并发

- 每个 Project 同时最多一个可写 Editor Session；其他会话只读或等待。
- Vim `:write` 只修改临时 worktree，UI 显示 dirty 文件，不自动生成版本或更新线上内容。
- Save Version 是用户显式命令；Repository Service 校验 owner、base commit 和 worktree hash，防止覆盖并发修改。
- Git 元数据和 commit 只由可信 Repository Service 操作，Sandbox 内不能修改 hook、config、refs 或 remote。
- Restore 从历史 commit 导出新快照并创建新 commit，不移动或重写既有历史。



### 7.4 不能声称的能力

V1 不能声称支持：

- 用户或模型获得任意宿主 Shell。
- 动态依赖安装或不受控出网。
- 编辑 Sandbox 内使用 Git remote、SSH key 或平台凭证。
- 把受限 Vim 描述为完整 Terminal CLI 或 CC 式 Agent Runtime。

目录约束、`vim -Z` 或 `chroot` 单独都不构成强隔离。若目标部署环境不能提供 rootless container/namespace、资源限制和 Secret 隔离，则真实 Vim WebIDE 不能启用，只能退化为浏览器内文件编辑器。

## 8. Agent 错误、验收与有限修复



### 8.1 谁拥有验收权

```text
Build Worker             -> 是否成功构建
Test Runner              -> Engineer 交付的单元测试是否真实通过
Deterministic Validator  -> 产品、架构、安全和能力 mandatory checks 是否通过
Engineer                 -> 根据真实失败证据修改源码或单元测试
User                     -> 是否接受、继续修改或发布
```

Engineer 对构建和单元测试通过负责，但不能给自己的输出直接判定通过。只有 Runtime 生成的 ExecutionReport 和 ValidationReport 构成工程通过证据；任何修复都必须重新经过完整 Build、Test 和 Validation。

### 8.2 失败处理矩阵


| 失败类型                                                    | 证据来源                                          | 自动处理                        | 最终失败行为                               |
| ------------------------------------------------------- | --------------------------------------------- | --------------------------- | ------------------------------------ |
| Provider 超时/限流/5xx | Provider error | 主 Provider 一次，如已配置则切换备用 Provider 一次；不再外层盲目重启整个角色阶段 | `run.failed` / Needs input |
| Schema 输出无效 | validation errors | 对当前 Provider 输出定向修正最多 1 次，不与外层三次尝试叠加 | `INVALID_MODEL_OUTPUT` |
| Build 失败 | ExecutionReport 与 build log | Engineer 可修复根因时进入一次修复；平台故障不重写源码 | 仍失败则 `build.failed`，保留两轮证据 |
| Unit Test 失败 | ExecutionReport 与 test log | 将失败测试、堆栈摘要和相关文件返回 Engineer，最多修复 1 轮 | 仍失败则 Failed，不创建 ProjectVersion |
| mandatory validation fail，`source_or_test + resolvable` | ValidationReport | Engineer 自动修订最多 1 轮 | 仍失败则 Failed，保留两轮证据 |
| mandatory validation fail，其他根因                          | ValidationReport                              | 不调用 Agent 掩盖平台错误            | Failed / Needs input                 |
| 非 mandatory warning | ExecutionReport / ValidationReport | 不伪装为全量通过 | 可以 `CompletedDegraded` 创建版本，但必须向用户展示警告 |


Provider 或结构化输出达到最大尝试次数后，平台不得静默改用预设文本。Project 保留 Prompt、附件元数据、Session 和已完成 Artifact，进入 Needs input，并提供：

- Retry：创建新的 StageRun attempt，重新执行当前失败角色。
- Edit request：返回 Prompt 或 Blueprint 编辑，不自动继续旧阶段。
- Use starter Blueprint：由用户主动选择非 AI 回退，并在 Artifact 来源中明确标记。

每次实际 Provider 调用分别预占并结算用量；预占用于保证并发记账正确，不用于执行额度限制。

`CompletedDegraded` 只表示所有 mandatory Build、Test 和 Validation 已通过，但 ExecutionReport 或 ValidationReport 仍包含非阻断警告。Provider 失败不会伪造降级产物，而是按失败路径保留已经提交的 Artifact。

### 8.3 自动修复输入输出

```text
Input
  Blueprint + ArchitectureSpec
  + current EngineerOutput（AppSpec + unit_tests）
  + ValidationReport（含 Build/Test 失败证据）
        |
        v
Engineer Agent
        |
        v
revised EngineerOutput（AppSpec + unit_tests，独立 Artifact，repair_attempt=1）
        |
        v
Runtime deterministic render -> revised SourceBundle
        |
        v
Schema -> full Build -> full Test -> full Validation -> ProjectVersion / Failed
```

Repair 不能只返回 AppSpec 后复用旧测试。`runtime.unit_tests` 失败时，当前全部测试文件和失败详情必须进入 Engineer Repair Context；模型返回完整修订版 `EngineerOutput`，Runtime 再从该结果确定性生成修订后的 SourceBundle。`engineer_output_repair` 和 `app_spec_repair` 分别保留完整修复结果与兼容 AppSpec，修订后的 SourceBundle 重新绑定新的 `source_manifest_hash` 并执行完整 Build、Test 和 Validation。

修订后仍失败不再循环调用 Engineer，由用户决定是否修改产品或架构设计、重试工程阶段或停止。自动修复不得静默改变已批准 ProductSpec 和当前 ArchitectureDesign；需要改变范围或架构时，必须返回对应上游阶段并使下游产物失效。

### 8.4 User Resolve 与真实 Build Error

```text
真实 Build Error
build.failed -> run.failed -> 用户 Retry Build

已成功构建后的应用问题
validation.issue_detected -> User Resolve
    -> RevisionSpec
    -> new BuildJob
    -> ProjectVersion(source=Resolve)
```

两条路径共用 Artifact、Event 和 Version 基础设施，但状态和文案不同。Resolve 处理已构建应用中的可定位问题，不能被包装成 Agent 自动修复了 Renderer、编译或资源错误；Build Worker 的工程恢复规则以 [V1 系统架构](./03-[工程]-系统架构.md)为准。

## 9. Prompt、版本与可观测性

每个角色拥有独立 system instruction 和 Pydantic output schema。Prompt 不写在 API route 中，由版本化配置集中管理。

每个 StageRun 至少记录：

```text
agent_role
model
prompt_version
input_artifact_refs
output_artifact_id
attempt
status
started_at / completed_at
input_tokens / output_tokens
provider_request_id
trace_id
error_code
```

事件顺序：

```text
stage.started
engineer.context.prepared（Engineer 阶段）
agent.attempt.started attempt / max_attempts
provider.primary.started
provider.primary.timeout（如发生）
provider.fallback.started（如发生）
contract.repair.started（如发生）
agent.output.validated attempt / artifact_type
stage.output          artifact_id / artifact_type
stage.completed

build.started         source_manifest_hash / adapter_id
build.completed       status / evidence_refs
test.started          source_manifest_hash / adapter_id
test.completed        status / passed / failed / evidence_refs
validation.completed  passed / source_manifest_hash / execution_report_ref

或

stage.started
agent.attempt.started attempt / max_attempts
agent.retry           attempt / max_attempts / will_retry / failure_kind
stage.failed

或可修复工程失败

validation.completed  passed=false / resolvable=true
engineer.repair.started repair_attempt=1
build.started
test.started
validation.completed
```

事件先持久化，再通过 SSE 推送。Provider 超时、备用 Provider 开始和 Contract 修正必须在发生时立即写入，不得等整次调用返回后补记。浏览器重连后按 `event_id` 重放。Trace 用于工程排障，不能向用户展示 Chain of Thought。

模型可见说明与结构化原始输出使用不同事件：`agent.message.delta` 承载角色给用户的简短说明；`agent.output.delta` 只承载可检查的结构化响应，不包含 Provider 的隐藏推理字段。原始输出必须批量持久化，当前阈值为累计新增 2048 字符或距离上次落库 1 秒，流结束时强制补齐尾部；不得按 Provider token/chunk 逐条提交数据库事务。Studio 从 `ProjectMessage.payload.model_output` 读取累计内容并在浏览器端逐字符播放，因此批量持久化不改变用户可见的逐字效果。

`failure_kind` 区分 Provider 超时、Provider 配置、Provider 响应、Contract 校验、Build、Unit Test、Validation 和 Platform 故障。用户界面展示分类、尝试编号、是否进入 Engineer 修复和当前真实执行阶段；截断后的底层异常摘要保留在事件 Payload 与下载日志中。结构化模型原始输出可以在用户主动展开“模型返回详情”时显示，但隐藏推理内容不进入该字段。

每个模型阶段使用一个共享总时限，主 Provider、备用 Provider 和 Contract 修正共同消耗该时限，不把多层超时简单累加。具体秒数必须基于真实运行分布确定；当前材料不足，不在设计中凭假设写死。

## 10. 配额与并发

- 每个实际 Provider 调用单独预占并结算用量，包括 schema retry 和 repair。
- 成功阶段的 Artifact 与结算同事务提交；非 LLM 异常也必须结算已观测到的实际请求并释放剩余预占，不能把整笔 reservation 记为 used。
- Worker 恢复只重放尚无 Artifact 的阶段；已提交阶段、已完成 Run 和既有 Build Version 不重复执行或结算。
- 团队负责人（Lead）的 `direct` 路径只结算团队负责人调用；`team` 路径中的产品经理（Product Manager）、架构师（Architect）和工程师（Engineer）顺序执行，可修复工程失败最多增加一次工程师修复调用。数据分析师（Data Analyst）和质量评审员（Reviewer）不产生新用量。
- 同一账户的多个 Session 共享 Usage Account，用量预占必须使用数据库事务，确保实际请求不会重复或遗漏结算。
- `quota_limit` 作为兼容字段保留，但 V1 不读取它来阻断 Lead、Agent retry 或 repair。
- 用户取消 pending risk approval 时不发生新的模型调用或配额消耗。



## 11. 代码归属

```text
another_atom/agent/
├── orchestrator.py       Lead 路由校验、固定团队状态机与阶段推进
├── context.py            Stage Context 组装与裁剪
├── approvals.py          风险驱动 Human-in-the-loop Contract
├── repair.py             有限修复规则
├── roles/
│   ├── lead.py
│   ├── product_manager.py
│   ├── architect.py
│   └── engineer.py
├── prompts/              版本化 role instruction
└── tracing.py            StageRun / usage / trace 记录

another_atom/runtime/
├── adapters/             按项目类型登记固定物化、构建、测试和预览能力
├── build.py              隔离构建并产生构建证据
├── test.py               隔离执行单元测试并产生 ExecutionReport
└── validator.py          产生不可由 Agent 改写的 ValidationReport
```

Pydantic Contract 仍统一放在 `another_atom/contracts/`。Agent 目录只能引用 Contract，不能再定义一套 ProductSpec、ArchitectureDesign、AppSpec、SourceBundle、ExecutionReport 或 ValidationReport。现有 Data Analyst 和 Reviewer 实现在迁移期可保留，但只用于读取历史 Artifact，不再注册到 V1 新 Run 状态机。

## 12. V1 智能体（Agent）验收标准

- 团队负责人决策（LeadDecision）只能为 `direct` 或 `team`；`direct` 不创建团队运行（Team Run），`team` 只按产品经理（Product Manager）→架构师（Architect）→工程师（Engineer）三个专业角色推进。
- 产品经理（Product Manager）生成真实 `docs/product-spec.md`；`supported` 和 `adapted` 产品规格（ProductSpec）都必须绑定内容指纹由用户确认，`unsupported` 不进入架构师阶段。
- 架构师（Architect）必须读取已批准产品规格（ProductSpec）完整 Markdown，并生成真实 `docs/architecture-design.md`；架构设计（ArchitectureDesign）的 `product_spec_hash` 与当前产品规格一致。
- 工程师（Engineer）交付应用规格（AppSpec）清单和通用源码包（SourceBundle）；源码包包含实现源码、单元测试和受控测试配置，不只是 HTML、CSS 和 JavaScript 三个字符串。
- 运行系统（Runtime）在沙箱（Sandbox）中使用已登记适配器（Adapter）执行固定构建（Build）和单元测试（Unit Test），执行报告（ExecutionReport）与校验报告（ValidationReport）都绑定当前 `source_manifest_hash`。
- 构建、单元测试或校验器（Validator）中的可修复失败可返回工程师一次；修复后重新执行完整构建、测试和校验（Build、Test、Validation），旧证据不得复用。
- 只有强制构建、测试和校验（mandatory Build、Test、Validation）全部通过才能创建项目版本（ProjectVersion）；工程师自己编写的单元测试不能取代平台安全和能力门禁。
- 数据分析师（Data Analyst）和质量评审员（Reviewer）不在 V1 新运行（Run）中被调用，不产生新的数据分析（DataProfile）或质量评审报告（ReviewReport），也不影响项目版本（ProjectVersion）创建。
- 每个角色输出都有阶段产物标识（Artifact ID）、版本、指纹（hash）、提示词版本（prompt version）、用量（usage）和追踪（trace）；下一角色只接收已批准或已验证的显式产物。
- V1 智能体（Agent）没有终端（Shell）、宿主文件、Git 远端（remote）、任意网络、平台数据库或发布工具（Publish Tool）；构建和测试只由运行时适配器（Runtime Adapter）在隔离沙箱（Sandbox）中执行。
- 进程重启或服务端事件流（SSE）重连后，运行（Run）、待处理产品规格审批（pending ProductSpec approval）、阶段运行（StageRun）、构建（Build）、测试（Test）、校验（Validation）和事件可以恢复且不重复调用。
- 跨用户或跨项目（Project）的上下文（Context）、阶段产物（Artifact）、日志和事件泄漏数量为 0。



## 13. V1 智能体（Agent）边界与演进取舍

本节承接原 README 中的 V1 Agent 版本取舍。它们是 V1 为完成闭环而做的约束，不是整体产品的长期限制。

- **[固定三角色]** 每个 `team` 请求只执行产品经理（Product Manager）→架构师（Architect）→工程师（Engineer）。数据分析师（Data Analyst）和质量评审员（Reviewer）在 V1 暂不启用；它们只能在存在明确产品场景、独立交付物和可验证收益后通过新设计恢复。
- **[固定顺序执行]** V1 不并行执行智能体（Agent），也不允许多个角色共享可写工作区，以减少部分失败、并发配额和阶段产物（Artifact）合并变量。
- **[文档驱动交接]** 产品规格（ProductSpec）和架构设计（ArchitectureDesign）是随代码库持久化的人类可读事实源，阶段产物（Artifact）记录路径、内容指纹、上游指纹和生成信息，不建立一套与文档重复且可独立漂移的短字段事实源。
- **[工程责任与执行权分离]** 工程师（Engineer）对代码、单元测试和通过负责，但构建（Build）、测试（Test）、校验（Validation）、Git、版本（Version）和发布（Publish）只由运行系统（Runtime）执行。这样保留工程闭环，不把宿主终端（Shell）交给模型。
- **[阶段级上下文（Context）]** 运行系统（Runtime）为每个阶段组装所需的产品规格（ProductSpec）、架构设计（ArchitectureDesign）、应用规格（AppSpec）、源码包（SourceBundle）和证据（Evidence），不维护一段无限增长的共享聊天记录，也不实现独立智能体（Agent）长期记忆。
- **[运行系统（Runtime）控制返工]** 固定状态机、重试上限和失败出口决定是否返工；团队负责人（Lead）不能修改流程或无限重试。V2 才允许团队负责人提交结构化返工与仲裁建议。
- **[按项目类型选择契约（Contract）]** V1 智能体（Agent）必须保留用户指定的软件类型和目标平台。源码包（SourceBundle）使用通用文件清单表达项目，而真实构建（Build）、单元测试（Unit Test）和预览（Preview）只在存在匹配运行时适配器（Runtime Adapter）时可用。缺失适配器必须作为能力缺口暴露，不通过提示词（Prompt）暗示任意技术栈、动态依赖、网络、终端（Shell）、后端或自动发布已经可用。
