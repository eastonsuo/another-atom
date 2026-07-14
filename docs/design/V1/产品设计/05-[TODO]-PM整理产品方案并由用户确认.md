# Another Atom V1 PM 整理产品方案并由用户确认

[toc]

- **文档状态：** V1 产品设计基线；基础 ProductSpec 查看与确认纵切已实现，编辑失效和重新生成待完成
- **功能定位：** PM 把用户需求整理成可编辑的简介和代码库内真实 ProductSpec，用户确认后再进入 Architect
- **通用审批：** [V1 Human-in-the-loop 用户审批](./04-[TODO]-Human-in-the-loop用户审批.md)
- **审批技术机制：** [V1 Human-in-the-loop 审批机制](../技术设计/05-[Agent][TODO]-Human-in-the-loop审批机制.md)
- **产品基线：** [V1 核心产品需求与交互](./01-核心产品需求与交互.md)

## 背景

用户最初的一句话通常不足以直接约束 Architect 和 Engineer。尤其当目标应用依赖大模型或其他 V1 不具备的运行能力时，如果 PM 没有先把目标、交互、范围、能力适配和验收标准写清楚，下游可能实现出结构完整但不符合用户预期的应用。

本文定义 PM 如何把对话整理成简介和代码库内真实的 `docs/product-spec.md`，用户如何修改、要求重新生成和确认，以及批准后的内容如何交给 Architect。Markdown 的通用阅读与编辑能力不在本文重复设计；本文只消费文档内容及其变更事实。

## 摘要

- **双层产品方案**
  - 卡片展示简短、可编辑的产品简介；完整需求保存在代码库内真实的 `docs/product-spec.md`，两者属于同一个 generation。
- **先确认再设计**
  - supported 和 adapted 方案都必须由用户确认当前 ProductSpec，未确认前不能进入 Architect。
- **修改后必须重新生成**
  - 用户修改简介或 Markdown 后，当前 generation 失效，下一步不可用；PM 必须基于修改结果重新生成一致的简介和文档。
- **复用通用 Approval**
  - PM 流程不自建审批状态、权限、CAS 和恢复逻辑，而是把当前 generation 作为 subject 交给 Human-in-the-loop 控制面。
- **精确交接**
  - Architect 只接收同一次已批准 generation 的简介与完整 Markdown；内容或 hash 不一致时不得继续。
- **能力边界前置**
  - ProductSpec 必须保留用户的产品身份，同时明确 V1 中被保留、适配和不支持的能力，不能用静态展示页掩盖核心能力缺失。
- **失败仍可继续对话**
  - 生成或重新生成失败后保留已有 Artifact 和用户修改，回到对话说明失败；用户可以继续调整或重试。

## 1. 产品结论

首次构建不再把用户原始 Prompt 直接交给 Architect，而是先形成一个可检查的产品基线：

```text
用户需求
  -> PM 澄清并生成
       |-- 简介：用于对话卡片快速判断方向
       `-- docs/product-spec.md：代码库内完整产品文档
  -> 用户查看或修改
       |-- 未修改：可以确认
       `-- 已修改：必须让 PM 重新生成
  -> 用户确认当前 generation
  -> Architect 接收“批准的简介 + 完整 Markdown”
```

用户确认的是一个完整、版本明确的 ProductSpec generation，而不是孤立的一段简介或某个文件路径。简介负责降低快速判断成本，Markdown 负责保存完整、可直接编辑并随代码库持续存在的产品约束。

## 2. 与 Human-in-the-loop 的区别和联系

### 2.1 责任边界

| 问题 | PM 产品方案流程 | 通用 Human-in-the-loop |
| --- | --- | --- |
| 待确认对象从哪里来 | 生成简介和 `docs/product-spec.md` | 不生成业务对象 |
| 用户修改后怎么办 | 检测修改、进入 `needs_regeneration`、调用 PM 重写 | 把旧 subject 标记为 stale |
| 卡片展示什么 | 简介、文档位置、生成状态和确认入口 | 只提供通用决定状态与失效语义 |
| 谁可以确认 | 不自行判断 | 校验 Project owner |
| 确认绑定什么 | 提供当前 generation 的内容与 hash | 保存对精确 subject 的决定 |
| 确认后做什么 | 组装 Architect Handoff | 通过固定 `resume_architect` 适配器恢复 |
| 并发、审计和重启恢复 | 不重复实现 | 统一负责 CAS、持久化、事件和恢复 |

### 2.2 复用方式

PM 流程通过以下语义接入通用控制面：

```text
gate_source   = workflow
approval_type = product_spec
subject       = 当前 ProductSpec generation
subject_hash  = hash(canonical(generation_id, summary_hash, product_spec_blob_sha))
resume_kind   = resume_architect
```

首次 ProductSpec 是固定工作流门禁，不由 Risk Policy 决定是否需要展示。Risk Policy 仍可在 ProductSpec 批准后的范围变化、额外预算或破坏性 Diff 中复用同一 Approval 控制面，但属于新的 subject，不能沿用首次确认。

### 2.3 不建立第二套审批

PM 侧不能增加独立的 `approved=true`、用户归属判断或“已确认就直接调用 Architect”的捷径。否则 ProductSpec 编辑失效、并发双击、服务重启和审计会与 Restore、Deployment 等其他 Approval 形成不同语义。

反过来，通用 Human-in-the-loop 也不负责 PM Prompt、Markdown 写入、摘要生成、内容 Diff 或 Architect Context。这样其他业务可以复用 Approval，而不必接受 ProductSpec 专属的数据和界面。

## 3. 功能范围

本文包含：

- PM 基于用户对话整理产品方案；
- 生成简介和 `docs/product-spec.md`；
- 展示生成状态、简介和 Markdown 位置；
- 检测简介或 Markdown 修改并要求重新生成；
- 用户确认当前 generation；
- 把已批准的简介和完整 Markdown 交给 Architect；
- 生成、重生成和恢复失败时保留已有 Artifact。

本文不包含：

- 通用 Markdown 文件树、阅读器和编辑器的具体交互；
- Approval 的数据库、CAS、权限和恢复实现；
- Architect 如何产出技术设计；
- 真实外部模型、Secret、网络和服务端能力的扩展设计。

## 4. ProductSpec generation

一次 generation 至少包含以下相互绑定的事实：

```text
ProductSpecGeneration
  generation_id
  project_id / run_id
  source_message_ids
  summary
  summary_hash
  product_spec_path = docs/product-spec.md
  product_spec_blob_sha
  capability_result
  status
  created_at
```

`docs/product-spec.md` 是 Project 代码库中的真实文件，用户可以通过通用文档能力阅读和编辑。系统仍需保存当前 generation 对应的不可变内容引用；仅记录可变路径不足以证明用户批准的是哪一版文档。

简介与 Markdown 必须来自同一次 generation。不能更新其中一个后继续把另一个当成已同步内容，也不能让卡片显示新简介而 Architect 读取旧文件。

## 5. PM 生成流程

PM 生成时使用：

- 用户当前需求和必要的前序对话；
- V1 产品与 Runtime 能力边界；
- 当前 Project 已有文件和产品基线（已有项目修改场景）；
- 用户在上一 generation 上修改的简介或 Markdown（重新生成场景）。

PM 输出：

1. 可在卡片中快速判断方向的简介；
2. 完整 `docs/product-spec.md`；
3. supported、adapted 或 unsupported 的能力结论；
4. adapted 时明确的 preserved、mapped、omitted 和相应验收边界。

如果信息不足以形成可执行产品方案，PM 通过对话提出必要问题，不生成一个用假设补齐的 ProductSpec。能否继续必须依据现有材料判断，不能为了让流程前进而增加用户没有表达的核心功能。

## 6. ProductSpec 内容

文档内容按实际产品需要展开，不要求为了模板完整而机械填充空章节，但至少必须能回答：

- 背景、用户目标和本轮要解决的问题；
- 目标用户及关键使用场景；
- 核心流程、页面或功能模块；
- 主要输入、输出、状态和失败反馈；
- 本轮范围、不做事项及已有项目中保持不变的部分；
- V1 能力边界以及 preserved、mapped、omitted；
- 可由后续实现和验证检查的验收条件。

产品身份必须保持不变。用户要求翻译软件、游戏或工具时，ProductSpec 不能为了适配自包含 Web Runtime 而把它改成介绍页、目录页或静态展示站。

## 7. 对话卡片与文档

ProductSpec 卡片只承担当前阶段必需的信息：

- 展示可编辑的简介；
- 明确提示完整文档位于 `docs/product-spec.md`，用户可通过通用文档功能查看或直接编辑；
- 展示 `generating / awaiting_approval / needs_regeneration / regenerating / failed` 等当前状态；
- 在当前 generation 未被修改时提供“确认并进入技术设计”。

卡片不再增加“阅读完整文档”“让模型修改”“直接编辑”等独立操作菜单。阅读和直接编辑属于通用文档能力；让模型重写由简介或 Markdown 修改后的重新生成流程承接。

用户仍可只看简介后确认，也可以进入 Markdown 检查完整内容。系统提示用户存在完整文档，但不强制证明用户已经逐段阅读。

## 8. 修改与重新生成

### 8.1 修改后的限制

用户修改简介或 `docs/product-spec.md` 后：

1. 当前 generation 进入 `needs_regeneration`；
2. 对应 pending Approval 进入 stale；
3. “确认并进入技术设计”不可用；
4. 卡片明确提示“内容已修改，请先重新生成产品方案”；
5. Architect 不得读取修改后的半同步内容。

这里要求重新生成，不是因为用户编辑无效，而是要让 PM 重新对齐简介、完整文档、能力判断和验收条件。否则用户可能只改了摘要，而正文仍保留冲突范围，或只改了正文，卡片与下游 Handoff 仍引用旧结论。

### 8.2 重新生成输入与结果

重新生成由用户明确触发，避免每次输入或文件保存都产生 Provider 调用。PM 读取：

- 用户修改后的简介；
- 用户修改后的完整 Markdown；
- 上一次 generation；
- 原始需求和必要对话；
- 当前 V1 能力边界。

成功后创建新的 generation，以重新生成结果更新工作区中的 `docs/product-spec.md` 和简介，并展示相对上一 generation 的主要变化。新的 generation 创建新的 Approval subject；旧 Approval 保留为 stale 历史，不能恢复。

## 9. 状态与失败处理

```text
generating
  |-- success -> awaiting_approval
  `-- failed  -> failed

awaiting_approval
  |-- summary / Markdown edited -> needs_regeneration
  `-- confirmed -> approved -> handing_off

needs_regeneration
  -> regenerating
       |-- success -> awaiting_approval
       `-- failed  -> needs_regeneration（保留失败信息和已有内容）
```

首次生成失败时，系统进入对话说明失败原因和可重试状态，不创建可确认的空 ProductSpec。重新生成失败时，保留用户修改、上一 generation、失败 attempt 和现有 `docs/product-spec.md`，不得回滚成看似仍可批准的旧状态。

Approval 成功只代表当前 ProductSpec 已获授权。后续 Architect 或 Build 失败时，ProductSpec generation 和 Approval 历史继续保留，失败事实进入对话；如果用户改变产品方案，再创建新的 generation，而不是修改已批准记录。

图中的 `awaiting_approval / approved` 是对关联 Approval 的界面投影，不是 PM 另外保存的一套审批状态；PM 自身只维护生成、内容变更和重新生成事实。

## 10. Architect Handoff

批准后，PM 流程向 Architect 提供：

```text
ProductSpecHandoff
  project_id / run_id
  generation_id
  approved_summary
  product_spec_path
  product_spec_content_ref
  product_spec_blob_sha
  approval_id
  capability_result
```

Architect 实际获得的是“简介 + 完整 Markdown”，不是只有文件路径，也不是完整聊天记录。简介用于快速建立方向，Markdown 是产品约束事实源；必要对话来源可通过 generation 引用追溯，但不把未筛选聊天和模型私有推理塞入 Handoff。

恢复前必须重新计算简介和 Markdown 的 hash，并确认与 Approval subject 一致。文件被修改、generation 不一致、Approval 非 approved 或能力结果为 unsupported 时，`resume_architect` 失败且不进入技术设计。

## 11. 示例：需要大模型的翻译软件

用户要求生成“使用大模型完成翻译的网页版软件”时，PM 不能只写“生成一个翻译页面”。ProductSpec 必须先区分两种不同验收目标：

- 用户接受 V1 adapted 原型：保留翻译软件身份、文本输入、语言选择、触发、加载/失败状态、结果和复制交互；明确真实模型调用、API Key、生产翻译质量和服务端配额不在当前交付中，译文只能是明确标注的模拟结果。
- 用户坚持真实大模型翻译：当前 V1 能力不足，进入 Needs input，不生成一个伪装成可用翻译服务的前端，也不能通过 Approval 绕过能力限制。

用户确认 adapted ProductSpec 后，Architect 收到的简介和 Markdown 都必须包含同一能力边界。后续用户对布局和交互不满意可以继续修改；对真实翻译质量不满意不能靠重复生成相同的自包含前端解决。

## 12. 验收路径

### 12.1 主路径

1. PM 根据用户需求生成简介和代码库内 `docs/product-spec.md`。
2. 卡片展示简介和文档位置，用户可以通过通用文档能力查看完整内容。
3. 当前 generation 未被修改时，用户确认后只恢复一次 Architect。
4. Architect 收到批准的简介和完整 Markdown，二者来自同一 generation。

### 12.2 修改路径

1. 用户编辑简介或 Markdown 后，确认入口立即不可用并提示重新生成。
2. 重新生成保留用户修改意图，产出新的简介、Markdown 和 generation。
3. 新 generation 需要重新确认，旧 Approval 不可复用。

### 12.3 能力与失败路径

1. adapted 方案在简介和 Markdown 中一致展示 preserved、mapped、omitted 和验收边界。
2. unsupported 方案不进入可批准状态。
3. 首次生成失败不产生空白可确认对象；重新生成失败保留已有 Artifact 和用户修改。
4. 并发确认、页面重放或服务重启不会重复进入 Architect。

## 13. 当前实现差距

当前已实现的基础纵切：

- PM 生成 Blueprint 后，Runtime 同步形成 ProductSpec Artifact，并把完整 Markdown 写入代码库 `docs/product-spec.md`；
- 中文请求要求 PM 的用户可见 Blueprint 字段使用中文，否则按无效输出重试，不再在中文确认页直接展示整页英文方案；
- adapted 请求的确认页只提示用户通过“项目文件”查看 ProductSpec，不再把项目名、视觉方向、页面和模块铺成视觉稿式表单；
- pending HumanTask 绑定 ProductSpec Artifact、路径和内容 hash，批准记录优先引用 ProductSpec Artifact；
- `docs/product-spec.md` 随 Project Git 仓库持久化，服务重启后仍可读取。

尚未满足本文的部分：

- supported 方案仍可能跳过首次产品基线确认；
- 当前以 ProductSpec Artifact 和内容 hash 绑定确认对象，尚未增加独立 generation ID 与简介 hash；
- 没有编辑后的 `needs_regeneration`、stale 和重新生成流程；
- Approval 尚未完整迁移为通用 `workflow + product_spec + resume_architect` 服务；
- Architect 当前仍读取与 ProductSpec 同源的 Blueprint，尚未改成显式“已批准简介 + 完整 Markdown”Handoff；
- 失败后保留 Artifact 并回到对话的完整状态与验证尚未落地。

## 14. 实施顺序

1. 定义 ProductSpec generation、简介和 Markdown 内容引用。
2. 让 PM 生成并写入真实 `docs/product-spec.md`，在卡片展示简介和文档位置。
3. 接入通用文档变更事实，落地 `needs_regeneration` 与重新生成。
4. 通过通用 Human-in-the-loop 创建 `workflow + product_spec` Approval。
5. 实现只接受已批准 generation 的 `resume_architect` Handoff。
6. 验证首次生成、修改重生成、失败恢复、能力限制、并发确认和重启恢复路径。
