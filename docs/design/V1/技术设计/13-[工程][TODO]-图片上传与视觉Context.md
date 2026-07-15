# Another Atom V1 图片上传与视觉 Context

[toc]

- 文档状态：V1 设计已确认；同步首版和本地自动化测试已完成，持久化异步任务与 Railway 验收待完成
- 更新日期：2026-07-16
- 产品交互：[对话图片粘贴与视觉参考](../产品设计/08-[TODO]-对话图片粘贴与视觉参考.md)
- Agent 设计：[Another Atom V1 多 Agent 设计](./01-[Agent]-多Agent设计.md)
- 系统架构：[Another Atom V1 系统架构](./03-[工程]-系统架构.md)
- 对话交互：[常驻流式对话与执行期间输入控制](../产品设计/07-常驻流式对话与执行期间输入控制.md)
- Ollama 能力参考：[Vision](https://docs.ollama.com/capabilities/vision)、[Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)
- 模型边界参考：[DeepSeek V4 的 Vision Proxy 说明](https://api-docs.deepseek.com/quick_start/agent_integrations/github_copilot)

## 背景

当前首页虽然提供附件按钮，但浏览器只提交文件名、大小和 MIME 类型，主服务也只保存附件元数据。文件内容没有上传、持久化或传入 Provider，因此产品经理、架构师和工程师都无法看到用户粘贴的截图。`deepseek-v4-pro` 本身是文本模型，也不能通过给现有文本消息增加一个文件名来获得视觉能力。

V1 的具体粘贴、缩略图、发送和失败恢复交互由[对话图片粘贴与视觉参考](../产品设计/08-[TODO]-对话图片粘贴与视觉参考.md)定义。本文只回答如何真实接收图片、持久化、调用 Ollama 视觉模型、形成可审计 `ImageContext` 并交给 `deepseek-v4-pro` 和固定 Agent 流水线。

## 摘要

- **交互映射**
  - 工程状态必须支撑产品设计中的粘贴、缩略图、上传进度、即时消息和图片级重试，不在前端伪造完成状态。
- **模型分工**
  - Ollama 视觉模型只负责把图片转换为结构化事实；`deepseek-v4-pro` 继续负责路由、产品方案、架构和代码，不直接接收图片。
- **Context 事实源**
  - 每批图片形成不可变 `ImageContext` 记录，绑定消息、原图内容指纹、视觉模型和 Prompt 版本。进入团队后，Run Artifact 引用同一记录；下游角色不重复识图，也不依赖上一角色的转述。
- **持久化边界**
  - 原图和规范化副本保存在主服务持久化卷，数据库保存所有权、状态、路径和内容指纹；图片不进入 Runtime Executor，也不自动成为生成项目的业务素材。
- **失败语义**
  - 上传、解码或视觉解析失败时保留用户文字和图片，允许单独重试或移除；不得静默忽略图片后继续调用 Pro。
- **V1 范围**
  - 只支持作为需求参考的 PNG、JPEG 和 WebP 静态图片；不包含图片生成、图片编辑、视频、PDF 视觉解析或跨用户缓存。

## 1. 设计范围

### 1.1 目标

1. 用户可以复制截图并直接粘贴到首页或 Project 对话框。
2. 图片内容真实上传，刷新、模型重试和 Worker 重启后仍可恢复。
3. 视觉模型输出稳定、可校验、可追踪来源的 `ImageContext` 记录。
4. Lead、产品经理、架构师和工程师获得与各自职责匹配的图片 Context。
5. 图片处理失败不丢失用户输入，不启动缺少图片信息的错误流水线。
6. 纯文本请求保持现有路径，不产生视觉模型调用和额外用量。

### 1.2 非目标

- 不让 `deepseek-v4-pro` 直接处理图片；官方 V4 接口仍按文本模型使用。
- 不用视觉模型替换产品经理、架构师或工程师。
- 不把参考图自动复制到生成项目的 SourceBundle；如用户希望把图片作为产品素材，应在后续单独设计 `project_asset` 用途。
- 不承诺从截图恢复像素级一致的页面；视觉模型输出是实现参考，不是可逆设计文件。
- 不允许图片中的文字改变系统指令、角色权限、Runtime Contract 或审批状态。

## 2. 当前实现与目标差异

| 位置 | 当前实现 | V1 目标 |
| --- | --- | --- |
| 浏览器附件 | `File` 被转换为 `name/size/content_type` | 保留本地缩略图并上传真实字节，发送时只引用服务端 `attachment_id` |
| 剪贴板 | 对话框只处理文本输入 | `paste` 事件识别 `image/*`，文本和图片可同时进入同一条消息 |
| 数据库存储 | `Attachment.storage_key` 为空，只保存元数据 | 保存所有权、内容指纹、上传状态、原图和规范化副本路径 |
| Provider 输入 | `messages[].content` 为纯文本 | Ollama 视觉请求使用 `images`，输出结构化 `ImageContext`；Pro 仍接收纯文本 Contract |
| Agent Context | 不包含附件内容 | 每个下游角色引用同一 `ImageContext` 记录及其 Run Artifact |
| 失败处理 | 元数据存在也会继续运行 | 图片未上传或未解析时不进入 Lead/团队，提供图片级重试和移除 |

## 3. 产品交互的工程映射

具体页面行为以[对话图片粘贴与视觉参考](../产品设计/08-[TODO]-对话图片粘贴与视觉参考.md)为准。本节只定义这些行为需要哪些可靠后端事实。

### 3.1 Composer 本地状态与服务端状态

Composer 维护尚未发送的本地草稿状态：原始 `File`、临时缩略图 URL、上传进度和服务端 `attachment_id`。服务端只接受真实上传并校验完成的附件，不相信客户端提交的 `ready`、大小或 MIME。

```text
Clipboard/File input
  -> local draft item
  -> POST /api/attachments
  -> Attachment(status=ready, content_hash, storage_key)
  -> draft item receives attachment_id
```

`URL.createObjectURL` 只用于发送前预览，不能成为刷新恢复或 Provider 输入。图片移除、组件卸载和重新选择时必须释放 URL；服务端附件缩略图使用受鉴权的读取接口。

### 3.2 消息先持久化，再异步处理

首页当前先同步调用 `/lead/messages`，Lead 返回 `team` 后才创建 Project/Run；Project 对话路由当前也仍有同步 HTTP 路径。该现状无法可靠满足“用户消息立即出现、视觉解析可恢复”的产品要求。

目标流程复用现有对话设计中的持久化 `ConversationJob` 或等价任务，不为图片另建一套不可恢复的浏览器任务：

```text
提交文字 + attachment_ids
  -> 原子持久化用户消息、附件绑定和 ConversationJob(queued)
  -> HTTP 立即返回 message/job 标识
  -> Worker: vision_analysis -> Lead routing
  -> direct/clarify: 保存 Lead 消息，不创建 Build Run
  -> team: 创建 Project/Run，复用同一消息和 ImageContext
```

首次首页消息尚无 Project 时，附件先绑定用户消息/Lead 请求；路由为 `team` 后再关联新 Project。Project 内消息直接绑定现有 Project。数据库关系必须允许附件在进入 Project 前已有明确的 `user_id` 和消息归属，不能用可空 `project_id` 代替所有权。

同一 `client_message_id` 的重复提交必须返回原消息和任务，不重复绑定附件、不重复执行视觉调用。ConversationJob 的 lease、重启恢复和单活动轮次继续遵循现有对话技术设计。

### 3.3 状态投影

Studio 展示的上传、图片理解和失败状态来自以下事实，而不是本地计时器推测：

| 产品状态 | 工程事实 |
| --- | --- |
| 正在上传 | 当前请求进度；尚无可发送 `attachment_id` |
| 已就绪 | `Attachment.status=ready` 且上传响应已经返回 |
| 正在理解 | ConversationJob 当前步骤为 `vision_analysis`，并已持久化 started/progress 事件 |
| 理解完成 | `ImageContext` 记录已通过 Schema/指纹校验并提交；团队 Run 已创建时同步存在 Artifact 引用 |
| 理解失败 | Job 保存稳定错误码，用户消息和 Attachment 保持不变 |

用户可见“图片理解结果”由已提交 Artifact 投影；不得展示 Provider 未校验的流式 JSON、Base64、存储路径或私有推理。

## 4. 上传与持久化 Contract

### 4.1 上传流程

新增用户级预上传接口：

```text
POST   /api/attachments                 multipart/form-data
GET    /api/attachments/{attachment_id}          元数据
GET    /api/attachments/{attachment_id}/content  受鉴权图片内容
DELETE /api/attachments/{attachment_id}  仅限尚未绑定消息的附件
```

`POST` 完成身份校验、流式大小限制、真实媒体类型识别、图片解码、内容指纹和规范化副本生成，然后返回：

```json
{
  "id": "attachment-id",
  "name": "screenshot.png",
  "media_type": "image/png",
  "byte_size": 284133,
  "content_hash": "sha256:...",
  "status": "ready"
}
```

`LeadMessageRequest` 与 `ProjectMessageRequest` 新增 `attachment_ids: list[str]`，最多 5 项。服务端在同一事务中确认附件属于当前用户、状态为 `ready` 且尚未绑定其他消息，再绑定到已持久化的消息。Lead 路由为 `team` 后，创建 Run 时通过原始消息引用同一批附件，不让 `RunCreate` 再提交一份可漂移的附件元数据。客户端提交的名称、大小和 MIME 不再作为可信事实。

### 4.2 文件验证与规范化

- 允许 PNG、JPEG、静态 WebP；仅信任服务端解码结果，不信任扩展名和浏览器 MIME。
- 单文件最大 10 MB，每条消息最多 5 张；V1 沿用现有 Schema 上限，不在本设计扩大。
- 限制解码后的总像素，拒绝损坏文件、动画图片和可能导致内存放大的异常图片。
- 根据方向信息校正画面，生成受控尺寸的规范化副本供视觉模型使用；原图保留用于用户查看和后续追溯。
- 原图和规范化副本写入主服务持久化卷的用户/Project 隔离目录，文件名由服务端 ID 构造，不使用用户文件名拼接路径。
- 数据库保存 `user_id`、可空 `project_id`、原始名称、媒体类型、字节数、内容指纹、存储键、状态和创建时间；消息与附件通过受唯一约束的关联记录绑定。
- 未绑定的预上传文件定期清理；绑定后的文件随 Project 删除流程一并删除。

## 5. 视觉解析 Contract

### 5.1 Provider 配置

视觉解析继续使用 Ollama 协议：

| 配置 | 语义 |
| --- | --- |
| `OLLAMA_VISION_MODEL` | 明确配置支持图片的模型；未配置时图片入口显示不可用 |
| `OLLAMA_VISION_HOST` | 可选；默认复用 `OLLAMA_HOST` |
| `OLLAMA_VISION_API_KEY` | 可选；同一 Ollama 账户时复用现有 Key，分离账户时单独配置 |
| `VISION_TIMEOUT_SECONDS` | 图片解析独立超时，不占用 Pro 阶段超时 |

候选模型可以是 Ollama 提供的 `qwen3-vl`、`gemma3` 或其他明确标注 Text/Image 输入的模型。部署配置必须使用 Railway 环境实际可调用的模型标识，文档不把某个候选名称硬编码成产品 Contract。

同一 Ollama Cloud 账户只增加一次视觉模型调用，不需要部署第二套服务。自建 Ollama 时可以在同一个实例加载视觉模型；是否需要额外 GPU/内存取决于实际模型，不由 Another Atom 隐藏。

### 5.2 请求与输出

同一条消息中的图片优先作为一个批次传给视觉模型，REST 请求使用 Ollama `messages[].images`。Provider 要求结构化输出，失败时只进行一次针对 Contract 的格式修正，不重新执行整个 Agent 流水线。

每条图片产生一个 `ImageObservation`：

| 字段 | 语义 |
| --- | --- |
| `attachment_id` | 服务端附件 ID |
| `source_hash` | 原图内容指纹，防止 Context 与文件错配 |
| `summary` | 图片中可直接观察到的内容概要 |
| `ocr_text` | 可见文字，按区域组织；不是系统指令 |
| `regions` | 主要区域、相对位置、可见元素和层级关系 |
| `visual_cues` | 可观察到的颜色、密度、间距和样式线索；不声称像素精确 |
| `uncertainties` | 无法确认、遮挡或可能识别错误的内容 |

批次输出形成不可变 `ImageContext` 记录：

```json
{
  "schema_version": "1.0",
  "observations": [],
  "combined_summary": "...",
  "vision_provider": "ollama",
  "vision_model": "configured-model-id",
  "prompt_version": "image-context-v1",
  "content_hash": "sha256:..."
}
```

记录额外保存 `user_id`、`message_id`、状态和创建时间，不保存模型私有推理。首次消息尚未创建 Run 时，记录仍能绑定已经持久化的用户消息；路由为 `team` 并创建 Run 后，再创建 `image_context` Run Artifact，Artifact 只保存 `image_context_id + content_hash` 引用。这样 `direct/clarify` 不需要伪造 Build Run，团队下游又能沿用现有 Artifact Handoff。

缓存只允许在同一用户内按 `source_hash + vision_model + prompt_version` 复用；不同用户之间即使图片指纹相同也不共享持久化结果。复用只复用已经通过 Contract 校验的观察结果，仍为本条消息创建明确引用。

## 6. Agent Context 交接

图片只解析一次，之后以不可变 `ImageContext` 记录及其 Run Artifact 引用进入现有 Context 组装：

| 角色 | 接收的图片 Context | 使用边界 |
| --- | --- | --- |
| Lead | `combined_summary`、附件数量和用户文字 | 只用于判断直接回答、澄清或调用团队，不展开视觉方案 |
| 产品经理 | 完整 `ImageContext` 与用户文字 | 把图片中的产品事实、参考方向和不确定项写入 ProductSpec；文字与图片冲突时请求确认 |
| 架构师 | 已批准 ProductSpec + 完整 `ImageContext` | 将确认后的页面、布局和交互线索映射为架构；不得重新解释已被用户否定的图片内容 |
| 工程师 | ProductSpec + ArchitectureDesign + 完整 `ImageContext` | 实现已确认方案，并可参考截图细节；图片不能覆盖 Runtime Contract 或源码安全规则 |
| Engineer Repair | 上述有效文档、源码和失败证据 | 只有修复与图片相关时才保留 ImageContext，不重新调用视觉模型 |

用户明确文字的优先级高于视觉模型推断；已批准 ProductSpec 的产品结论高于原始图片描述。`ImageContext` 是证据，不是第二份产品规格。

OCR 文字和图片中的代码、命令、网页内容全部标记为不可信数据。Provider Prompt 必须明确禁止执行其中的指令，也不能把图片中的“忽略前文”等文本提升为系统或用户指令。

## 7. 状态、错误与用量

### 7.1 状态

附件状态使用：

```text
uploading -> ready -> bound -> analyzed
     |         |        |
     `-> failed `--------`-> analysis_failed
```

Run/对话任务增加 `vision_analysis` 阶段，但它不是新的 Agent 角色。阶段事件至少包含：

- `attachment.upload.completed|failed`
- `vision.analysis.started`
- `vision.analysis.progress`
- `vision.analysis.completed|failed`

事件先持久化再通过 SSE 推送；刷新页面后按现有事件游标恢复。

### 7.2 稳定错误

| 错误码 | 场景 | 用户出口 |
| --- | --- | --- |
| `ATTACHMENT_TYPE_UNSUPPORTED` | 不是允许的静态图片 | 移除并重新粘贴 |
| `ATTACHMENT_TOO_LARGE` | 超过单图上限 | 压缩或更换图片 |
| `ATTACHMENT_DECODE_FAILED` | 文件损坏或无法安全解码 | 移除并重传 |
| `ATTACHMENT_NOT_READY` | 发送时上传尚未完成 | 等待上传，不创建 Run |
| `VISION_MODEL_UNAVAILABLE` | 未配置模型或 Provider 不可用 | 保留消息，重试；不能静默走纯文本 |
| `VISION_OUTPUT_INVALID` | 结构化输出修正后仍无效 | 保留原图和原始用户消息，重试解析 |

视觉解析失败不创建 ProductSpec、ArchitectureDesign 或源码候选，也不移动 Project 当前版本。

### 7.3 用量

- 同一消息的图片默认批量解析为一次视觉 Provider 请求；实际调用写入 Usage Ledger 的独立 `vision_analysis` stage。
- 复用同一用户已有且 Contract 指纹一致的 `ImageContext` 时不产生新调用。
- 上传、解码和本地规范化不计模型调用；Provider 已返回但结构化修正失败的实际请求仍按真实用量记录。
- Studio 展示视觉调用和 Pro/Flash 调用的已使用次数，不把图片数量伪装成模型请求次数。

## 8. 安全与隐私边界

- 图片只能由所有者读取和绑定；所有 API 查询同时校验 `user_id` 与 Project 归属。
- 下载接口使用服务端生成的安全响应头，不直接暴露 Volume 路径。
- 日志、事件和 Provider Trace 只记录附件 ID、大小、媒体类型和内容指纹，不记录 Base64 或 OCR 全文。
- UI 在上传入口说明图片会发送给当前配置的 Ollama 视觉 Provider；如果是 Ollama Cloud，不能宣传为“仅本地处理”。
- Runtime Executor 不接收需求参考图；只有未来明确进入 SourceBundle 的项目素材才按 Runtime Contract 处理。
- 图片删除必须同时处理数据库记录、原图、规范化副本和可失效的 `ImageContext` 引用。

## 9. 实现顺序

1. **真实附件上传**：增加上传接口、持久化文件、所有权检查、内容指纹和清理任务；把现有元数据提交迁移为 `attachment_ids`。
2. **Composer 粘贴交互**：首页和 Project 对话框统一处理粘贴、选择、缩略图、进度、移除及发送禁用原因。
3. **视觉 Provider**：增加独立视觉配置、Ollama 图片请求、结构化 `ImageContext` Schema、不可变记录、Run Artifact 引用和用量记录。
4. **流程接入**：在 Lead 前增加 `vision_analysis`，把同一 `ImageContext` 按第六节传给固定角色并加入 ConversationJob/Worker 重启恢复。
5. **可检查结果**：对话记录展示附件，提供可展开图片理解结果、稳定错误和单独重试。
6. **Railway 验收**：配置真实视觉模型，验证主服务 Volume、Ollama Cloud 调用、刷新恢复和多用户隔离。

### 9.1 2026-07-16 本地实现进度

已实现：

- 首页和 Project 对话的真实图片预上传、鉴权读取、删除、粘贴、缩略图、失败重试和发送门禁；
- PNG、JPEG、静态 WebP 的服务端文件头、尺寸、动画和像素上限校验；
- `ReferenceAttachment`、不可变 `ImageContext`、Ollama `messages[].images` 结构化调用和 Run `image_context` Artifact；
- Lead 输入、Project Context 和 Build Run 的同一份图片 Context 复用；
- 用户消息即时投影、已发送图片展示和可展开图片理解结果；
- Mock Vision 集成测试、纯文本回归测试、Project 修改链路测试与 Studio 构建。

尚未实现，因此本文继续保留 `[TODO]`：

- `ConversationJob`/Worker 异步执行、lease 和重启恢复；当前视觉与 Lead 仍在原 HTTP 请求内顺序执行；
- 原图方向校正、受控尺寸规范化副本、未绑定附件定期清理和 Project 删除文件清理；
- 视觉阶段独立 Usage Ledger、持久化 SSE 进度、图片理解失败后的单独重试接口；
- Project 的 PM 补充和 ProductSpec 修改专用提交路径携带图片；
- Railway 真实视觉模型、Volume、跨用户和刷新恢复验收。

## 10. 验收标准

### 10.1 自动化验证

1. PNG、JPEG、WebP 上传成功，非法类型、伪造 MIME、超限和损坏图片被确定性拒绝。
2. 用户不能读取、绑定或删除其他用户的附件。
3. `LeadMessageRequest`/`ProjectMessageRequest` 只能绑定当前用户 `ready` 状态的附件，重复绑定被拒绝；`RunCreate` 只能沿用原始消息引用。
4. 使用 Fake Vision Provider 验证 Ollama 请求包含真实图片内容，输出 Schema、内容指纹和 Artifact 引用一致。
5. 有图片的请求必须先完成 `ImageContext`，再调用 Lead；纯文本请求不调用视觉 Provider。
6. 视觉超时、无效结构化输出和 Worker 重启后，用户文字、附件和已完成状态可以恢复且不会重复结算已完成调用。
7. OCR 中包含指令文本时，该内容只进入不可信 `ImageContext` 数据区，不改变角色 Prompt 或流程状态。

### 10.2 Railway 部署联调

用户交互验收统一以[产品设计第八节](../产品设计/08-[TODO]-对话图片粘贴与视觉参考.md#8-产品验收标准)为准；工程联调额外确认以下事实：

1. 在对话框复制并粘贴一张 UI 截图，立即看到缩略图和上传进度；普通文字可以继续编辑。
2. 上传完成后发送，用户消息立即出现，状态依次显示图片理解、Lead/产品经理、架构师和工程师阶段。
3. “图片理解结果”能够显示截图概要、可见文字、布局区域和不确定项，刷新页面后仍存在。
4. ProductSpec 和 ArchitectureDesign 能引用图片中真实存在的需求线索；Engineer 生成结果与已批准文档一致。
5. 暂停或移除视觉模型配置后，带图消息明确失败并允许重试，不能在忽略图片的情况下继续构建。
6. 另一个用户无法访问前一用户的附件 URL、缩略图或 ImageContext。

只有以上自动化检查和 Railway 登录态验收完成后，文件名状态才能从 `[TODO]` 改为 `[DONE]`。
