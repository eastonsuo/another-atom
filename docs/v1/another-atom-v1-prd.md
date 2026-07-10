# Another Atom V1.0 产品需求文档

[toc]

- 文档状态：已确认，进入实施
- 版本名称：V1.0 可部署纵切版
- 前置文档：[Atoms 参考产品功能分析](../reference/atoms-reference-analysis.md)
- 技术文档：[Another Atom V1 架构设计](./architecture-design.md)

## 1. 版本结论

推荐实现 **V1.0 可部署纵切版**：做一个可公开访问、可完成核心任务、状态真实保存的 AI 应用生成 demo；产品交互受 Atoms 启发，但使用 Another Atom 自己的品牌、角色和信息结构。Blueprint 与 AppSpec 由真实 LLM 生成，项目通过受控工具和固定 React 模板落地；第三方平台能力仍采用受控模拟。V1 只交付 Railway Cloud Demo，不实现本地 Agent Runtime。

它不是 Atoms 官网复刻，也不是静态高保真原型。用户必须能完整走通：

`从首页输入需求 -> 选择模式 -> 确认 Blueprint -> 查看构建执行 -> 预览应用 -> 修改内容 -> 处理错误 -> 保存版本 -> 发布 -> 打开公开链接`

```text
 +---------+    +---------+    +-----------+    +---------+
 | Home    |--->| Prompt  |--->| Blueprint |--->| Build   |
 +---------+    +---------+    +-----------+    +----+----+
                                                      |
                                                      v
 +------------+   +---------+    +----------+    +----+----+
 | Public URL |<--| Publish |<---| Versions |<---| Viewer  |
 +------+-----+   +---------+    +----+-----+    +----+----+
        |                              ^               |
        |                              |               v
        |                         Save / Restore   Edit / Resolve
        |                                              |
        +---------------- User feedback ---------------+
```

这张图定义了 V1.0 的最小产品闭环：公开结果不是终点，用户可以回到 Viewer 继续修改，再通过版本和 Update 控制线上内容。

选择这个版本的原因是：挑战要求的核心价值存在于链路连续性，而不在功能数量。若第一版同时做真实多 Agent、代码沙箱、Supabase、Stripe、GitHub、GA4/GSC 和广告投放，工程风险会主要来自外部系统，反而无法判断主产品交互是否成立。

## 2. 版本选择

| 版本 | 定义 | 优势 | 代价 | 适用边界 |
| --- | --- | --- | --- | --- |
| V0.1 展示版 | 静态页面和预设动效 | 最快，适合讲概念 | 没有真实状态和任务闭环 | 只能做视觉评审，不符合“可用版本”目标 |
| **V1.0 可部署纵切版** | 真实 LLM 生成结构化结果，受控工具落地应用，外部服务受控模拟 | 可操作、可发布，并能验证核心 Agent 链路 | 不能证明任意代码生成和完整平台集成能力 | **本次推荐版本** |
| V2.0 自主多 Agent 版 | 在 V1 Contract 上增加 Leader、独立专业 Agent、动态委派、返工和仲裁 | 验证真实 Agent 协作与扩展能力 | 上下文、并发配额、沙箱和收敛控制更复杂 | V1 验收通过后实施 |

## 3. 产品目标

### 3.1 要证明的判断

V1.0 只验证四件事：

1. 用户能否从首页 Prompt Composer 顺利启动一个项目。
2. Blueprint 能否把模糊需求转成可编辑、可确认的构建输入。
3. 用户是否能理解 Engineer/Team 两种模式带来的执行差异。
4. 从预览、编辑、版本到发布链接的闭环是否足以让产品从“聊天”变成“工作台”。

### 3.2 不证明的判断

V1.0 不用于证明：

- 大模型能稳定生成任意应用。
- 多 Agent 的内部协作质量优于单 Agent。
- 生成代码可安全地在多租户沙箱执行。
- Supabase、Stripe、GitHub、Google Ads、GA4/GSC 已真实接通。
- 内置 Cloud、计费和公开作品广场已达到生产可用水平。

这些能力如果在界面出现，必须明确标记为“演示连接”或“此版本不可用”，不能让用户误以为会产生真实数据、授权或费用。

```text
 +-------------------------------------------------------------+
 | REAL PRODUCT BEHAVIOR                                       |
 | LLM / Blueprint / Build / Persistence / Versions / Publish  |
 +-------------------------------------------------------------+
                              |
                              v
 +-------------------------------------------------------------+
 | CONTROLLED EXECUTION                                        |
 | Template scope / Tool allowlist / Role stages / Resolve      |
 +-------------------------------------------------------------+
                              |
                              v
 +-------------------------------------------------------------+
 | VISIBLE, NOT CONNECTED                                      |
 | Cloud / OAuth integrations / Ads / Analytics / Billing      |
 +-------------------------------------------------------------+
```

判断标准不是“页面是否出现”，而是状态是否真实改变：第一层必须调用真实能力并保存结果；第二层必须由受控工具真实执行且明确范围；第三层只能解释能力边界。

## 4. 目标用户与演示任务

### 4.1 目标用户

第一版只服务一个明确场景：需要快速理解 Another Atom 产品逻辑并评估后续开发价值的产品、设计或研发评审者。

不面向真实外部客户长期建站，也不处理多人组织管理。

### 4.2 Golden Path

默认演示任务：

> 创建一个名为 Mono Market 的独立设计商品站，包含首页、商品列表、商品详情、购物车入口和基础 SEO。整体风格克制、编辑感强，适配桌面端和手机端。

选择商品站而不是纯 Landing Page，是因为它能同时验证多页面预览、内容编辑、响应式布局、错误处理、版本和发布；又不要求第一版实现真实订单、库存和支付。

V1.0 对其他自由输入只做有限解析：提取项目名称、主色、页面类型和关键模块，并映射到预设站点结构。产品不声称支持任意应用生成。

## 5. 产品结构

V1.0 包含七个可操作区域：

1. **Home**：产品第一屏、中央 Prompt Composer、模式与附件入口、最近项目和示例。
2. **Projects**：项目列表、创建结果和最近状态。
3. **Build Workspace**：Blueprint、通用角色时间线、构建进度和任务消息。
4. **App Viewer**：桌面/手机预览、页面切换、刷新和选择元素。
5. **Edit Panel**：修改文本、颜色和图片，并形成新版本。
6. **Versions**：版本列表、预览、恢复和 Remix。
7. **Publish**：发布设置、公开链接、分享和下线。

Cloud、Integrations、Growth 作为项目侧栏中的能力中心存在，但只承担边界说明和演示状态，不扩展成独立后台。

首页必须是可操作的构建入口，而不是营销页或静态欢迎页：

```text
 +----------------------+---------------------------------------------+
 | Another Atom         |                                User / Runs  |
 |                      |                                             |
 | Home                 |       Turn an idea into a live product      |
 | Projects             |                                             |
 | Resources            |   +-------------------------------------+   |
 |                      |   | Describe what you want to build...  |   |
 | Recent projects      |   |                                     |   |
 | - Mono Market        |   +-------------------------------------+   |
 | - Remix project      |   | Attach | Mode | Voice | Build --->  |   |
 |                      |                                             |
 |                      |   Blueprint / examples / recent projects    |
 +----------------------+---------------------------------------------+
```

提交 Prompt 并确认 Blueprint 后进入项目工作区。概念工作区布局如下，具体尺寸和响应式方案留到技术设计阶段：

```text
 +------------------+-----------------------------------------------+
 | Projects         | Project header                 Version Publish|
 |                  +--------------------+--------------------------+
 | + New project    | Build Chat         | App Viewer               |
 |                  |                    |                          |
 | Recent           | Role timeline      | Desktop / Mobile         |
 | - Mono Market    | Blueprint status   | Route switch             |
 | - Remix copy     | Build progress     | Interactive preview      |
 |                  | Follow-up prompt   |                          |
 +------------------+--------------------+--------------------------+
 | Capability Center| Context panel: Edit / Console / Versions      |
 | Cloud            | Opens only when the current task needs it     |
 | Integrations     |                                               |
 | Growth           |                                               |
 +------------------+-----------------------------------------------+
```

这里表达的是区域关系，不要求桌面端始终同时展开所有面板；移动端必须改为单区域切换。

## 6. P0 功能范围

P0 是部署前必须完成的范围。缺少任意一项，核心链路都不完整。

### 6.1 应用外壳与首页

- 第一屏直接进入可用工作台，不设置营销 Landing Page。
- 左侧导航包含 Another Atom 品牌、Home、Projects、Resources 和最近项目。
- 主区域显示中央 Prompt Composer，以及 Blueprint、示例或最近项目入口。
- Prompt Composer 支持多行输入、文件/图片附件、模式选择、语音入口和 Build 命令。
- Home 提供至少 2 个可一键填充的受支持示例 Prompt，例如独立设计商品站和书店目录；示例只填充输入，不自动提交。
- 模式选择旁必须直接说明差异：Engineer Mode 为“更快、阶段更少、产物更精简”；Team Mode 为“分阶段接力、过程与产物可检查”。
- Prompt Composer 必须覆盖 empty、typing、uploading、ready、submitting、error 六种状态。
- Build 在 Prompt 为空或附件处理中禁用，并给出明确原因。
- 最近项目显示名称、更新时间、当前版本和发布状态；点击后恢复对应工作区。
- 桌面端保留侧栏和中央构建区；移动端改为单区域导航，不能压缩成不可操作的桌面布局。
- 不显示无法解释或不会变化的虚假 credit、通知和在线状态。

### 6.2 Blueprint 与项目创建

Blueprint 是 Another Atom 的主要衍生能力，也是从 Prompt 进入 Build 的确认门：

```text
 Prompt + Attachments
          |
          v
 +------------------------+
 | Blueprint              |
 | - Project name         |
 | - Product type         |
 | - Pages                |
 | - Modules              |
 | - Visual direction     |
 | - Data requirements    |
 +-----------+------------+
             |
       edit / confirm
             |
             v
          Build task
```

- 提交 Prompt 后先创建 Draft 项目并生成 Blueprint，不直接播放构建进度。
- Blueprint 包含项目名称、产品类型、页面、模块、视觉方向和数据需求。
- 用户可修改字段、删除非关键模块、确认构建或返回继续编辑 Prompt。
- 未确认 Blueprint 时不能进入 Building。
- Prompt、附件元信息、Blueprint 和确认结果必须随项目持久化。
- V1 只支持商品展示/商品目录站。Product Manager 输出必须包含 `support_level`：`supported`、`adapted` 或 `unsupported`。
- `supported` 直接进入 Blueprint；`adapted` 必须在界面列出被替换、忽略或映射的需求，用户确认后才能继续。
- `unsupported` 不创建 Build Job，界面明确说明“V1 仅支持商品展示/目录站”，并提供 Golden Path 示例。
- Product Manager 还必须输出 `support_reasons[]`、`mapped_requirements[]`、`omitted_requirements[]` 和 `rewrite_suggestion`，使三态判定可以解释和复核。
- 文件和图片附件支持本地选择、名称/大小预览和移除，不上传到第三方服务。
- Projects 支持查看、重命名和删除项目；删除需要二次确认。

#### support_level 判定规则与示例

判定先看**主要用户目标**，不能只按关键词匹配：

| 判定 | 边界规则 | 典型输入 | 系统行为 |
| --- | --- | --- | --- |
| `supported` | 主要目标是商品浏览/展示，页面和模块都在 Home、Catalog、Product、展示型购物车入口、基础 SEO 范围内 | “创建独立设计商品站，包含首页、目录、详情和基础 SEO” | 生成 Blueprint，等待用户确认 |
| `adapted` | 主要目标仍是商品展示；移除或静态替代次要能力后，核心目标不变 | “商品目录站，另外需要登录、收藏和结账” | 保留目录/详情；将登录、收藏、结账标为忽略或展示占位，列出映射后等待确认 |
| `unsupported` | 主要目标依赖真实认证、数据写入、交易、管理后台、实时协作或非商品站信息结构；移除后会改变产品本质 | “实现带库存、订单和支付的电商系统”“创建 CRM 管理后台” | 构建前停止，说明原因并给出受支持示例和改写建议 |

一致性约束：

- `adapted` 不能新增真实后端、认证、交易、动态依赖或模板外页面类型。
- 如果被省略能力是用户主要目标，必须判为 `unsupported`，不能为了继续构建而降级成 `adapted`。
- 平台使用固定 Capability Policy 校验 Blueprint；同一输入、同一 Policy 版本必须得到相同的允许/拒绝边界。
- UI 必须同时展示原需求、映射结果和舍弃项；用户确认的是映射后的 Blueprint，不是原 Prompt。

### 6.3 模式与角色执行

#### Engineer Mode

- Engineer 根据 Prompt 生成最小 Blueprint，用户确认后由同一 Engineer 生成 AppSpec。
- 全程只显示 Engineer 角色，执行步骤较少，随后进入固定构建和验证。
- 只展示预计执行阶段，不展示不会真实变化的 credit 或扣费信息。
- 适合用户观察“快速、低成本、覆盖窄”的模式特征。

#### Team Mode

- Team Mode 是固定顺序的角色接力：Product Manager、Designer、Engineer、QA 使用独立 instruction 和结构化输出，按顺序消费上一阶段的明确产物。
- Product Manager 根据 Prompt 和附件生成 Blueprint；用户确认后，Designer 生成 VisualSpec，Engineer 生成 AppSpec，固定 Renderer 完成构建，QA 基于 ValidationReport 生成 QAReview。
- 确定性 ValidationReport 是质量门禁，QAReview 只能解释问题和提出建议，不能把失败改写为通过。
- QAReview 必须提供用户可读检查摘要、mandatory check 结果、warning、evidence 引用和可执行的 Resolve/修改建议；QA Agent 调用必须绑定这些可检查产物，不能只生成角色消息。
- 当确定性 mandatory checks 已通过，但 QA Agent 因 Provider 或配额失败不可用时，可以进入 `QA degraded`：展示“仅完成确定性校验”，直接呈现 ValidationReport，不伪装成 QA Agent 已完成。Golden Path 验收仍必须包含真实 QAReview。
- `root_cause=app_spec` 且 `resolvable=true` 的 mandatory failure 最多触发 1 轮 Engineer 自动修订；仍失败或根因不明确时进入 Needs input，不自动无限返工。
- 基础 SEO 作为 Blueprint 和构建产物的一部分生成，不设置 Atoms 专有角色名称。
- 工作区标题或时间线必须标注“Team Mode · 分阶段接力”，并展示当前角色、阶段状态和可检查产物。
- 同一时刻只突出一个主执行阶段，避免把阶段事件做成无意义的消息瀑布。
- V1 不并行执行角色，不动态委派，不共享隐藏长期记忆，也不进行自动无限返工；这些属于 V2 自主多 Agent。

#### 共同行为

- 支持 Stop；停止后可 Continue 或 Remix。
- LLM 输出必须经过结构校验和有限重试；文件写入与构建工具必须提供可检查、可恢复的确定性状态。
- 构建完成后自动打开 App Viewer。
- 角色文案明确是固定顺序角色 Pipeline，不使用“多个 Agent 正在并行协作”“团队自主讨论”等表述，也不展示模型私有推理内容。

两种可执行模式必须在流程上可区分，而不只是切换标签：

```text
 Engineer Mode

 Prompt --> Engineer --> Blueprint --> Confirm --> AppSpec --> Build --> Validate --> Viewer

 Team Mode: fixed sequential role pipeline

 Prompt --> Product Manager --> Blueprint --> Confirm --> Designer --> Engineer --> Build --> QA --> Viewer
              |            |                    |           |          |       |
           requirements  edit/approve       VisualSpec    AppSpec  Validation QAReview
```

### 6.4 App Viewer

- Build Job 进入队列后立即展示 Queued 状态、`jobs_ahead` 和 Cancel；没有稳定历史样本前不显示预计完成时间。
- 排队、开始构建、校验和完成/失败都通过持久化事件更新；用户提交后 2 秒内必须看到第一条状态事件。
- 默认展示一个可交互的 Mono Market 站点，不使用静态截图代替应用。
- 支持 Home、Catalog、Product 三个路由。
- 支持 Desktop/Mobile 两种固定预览尺寸，切换时工作区布局不跳动。
- 支持刷新预览和在新标签打开当前预览。
- 支持选中标题、正文、按钮和商品图片；选中后打开 Edit Panel。
- Console 展示 info/error 两类事件，可清空。
- 提供一个可复现的模拟错误，例如商品详情按钮路由失效；点击 Resolve 后恢复并形成修复记录。
- V1 编辑只修改受控字段并重新生成 AppSpec，不允许用户直接写代码。预设问题使用 Resolve；真实 Renderer/Build 错误显示 Build failed 和 Retry，不能混用文案。

### 6.5 可视化编辑

- 文本元素可编辑内容。
- 按钮和强调元素可修改预设颜色。
- 商品图可从内置素材库替换。
- 修改有 Apply/Cancel，不应输入即破坏当前版本。
- Apply 后预览立即更新，并把项目标记为“有未保存改动”。
- 第一版不做任意 DOM 操作、拖拽布局、代码编辑器或自由上传图片裁切。

### 6.6 版本与 Remix

- 首次构建生成 Version 1。
- 每次明确保存生成新版本，并记录时间、摘要和来源：Build/Edit/Resolve/Restore。
- 可切换任意版本进行只读预览。
- Restore 把选定历史版本恢复为新的当前版本，不覆盖或删除原历史。
- Remix 从选定版本创建新项目，保留来源关系，但后续修改互不影响。
- 刷新浏览器后，项目、版本和当前编辑状态不能丢失。

### 6.7 发布与分享

- 支持首次 Publish、Update 和 Unpublish。
- 支持两种发布策略：Always Latest、Specify Version。
- 发布成功后生成稳定公开 URL，并可复制和打开。
- 公开 URL 应在无登录、无本地项目状态的浏览器中访问，展示被发布版本。
- Specify Version 下继续编辑或保存新版本，不应改变线上内容；手动 Update 后才改变。
- Always Latest 下保存新版本后，线上内容应更新到最新保存版本。
- Publish 面板持续显示 `线上版本 vX / 当前编辑 vY`。Specify Version 下两者不一致时，Update 是唯一同步入口。
- Always Latest 下保存会改变线上内容时，保存控件必须显示“Save and update live”并给出轻量提示，避免用户把半成品误发布。
- Share 支持 Public 和 Link Only；Private 不进入 V1.0，因为第一版没有公开应用访问控制与成员授权体系。
- 支持编辑公开卡片的标题、描述和封面。
- Export 导出版本化 JSON；静态代码 zip 不属于 P0。JSON 最小字段集必须符合下面的 Contract，不导出密钥、凭证、绝对存储路径、原始对话或内部配额流水。

```json
{
  "schema_version": "1.0",
  "exported_at": "2026-07-11T00:00:00Z",
  "project": {
    "id": "project_123",
    "name": "Mono Market",
    "product_type": "product_catalog"
  },
  "blueprint": {},
  "visual_spec": {},
  "app_spec": {},
  "current_version": {
    "id": "version_2",
    "number": 2,
    "source": "Build|Edit|Resolve|Restore",
    "created_at": "2026-07-11T00:00:00Z",
    "summary": "Updated hero copy"
  },
  "versions": [],
  "publication": {
    "status": "unpublished|live|paused",
    "strategy": "latest|specified",
    "version_id": "version_2",
    "url": "https://example.com/apps/project_123"
  },
  "attachments": [
    {
      "id": "attachment_1",
      "file_name": "reference.png",
      "mime_type": "image/png",
      "size_bytes": 1024
    }
  ]
}
```

版本历史只有一份，两个发布策略只是使用不同指针：

```text
 Version history

 V1 --------> V2 --------> V3 --------> V4
               ^                         ^
               |                         |
 Specify Version pointer           Latest pointer
 stays on V2 until Update          moves after each save
               |                         |
               +------------+------------+
                            v
                      Published snapshot
                            |
                            v
                       Stable public URL

 Restore V1 creates V5; it does not delete V2-V4.
 Remix V2 creates another project with an independent history.
```

### 6.8 能力中心

能力中心用于说明完整产品边界，不负责伪造已接通的平台。

- Cloud：展示 Database、Auth、Payments、Domains、Keys、AI 的能力说明和依赖关系。
- Integrations：展示 Supabase、Stripe、GitHub、Linear、Asana、Todoist。
- Growth：展示基础 SEO 输出、GA4/GSC 和 Ads automation。
- 每项只允许三种状态：Demo available、Reference only、Not included。
- 不出现真实 OAuth 按钮，不采集 API Key，不执行广告或支付动作。
- Blueprint 和构建流程生成的 meta title、description 和 sitemap preview 可在 Growth 中查看，这是能力中心唯一的可操作结果。

```text
 Capability Center
      |
      +-- Cloud
      |     +-- Database / Auth / Storage
      |     +-- Payments / Domains / Keys
      |     `-- AI integration
      |
      +-- Integrations
      |     +-- Supabase / Stripe / GitHub
      |     `-- Linear / Asana / Todoist
      |
      `-- Growth
            +-- Basic SEO --------> demo output available
            +-- GA4 / GSC --------> visible, not connected
            `-- Ads automation ---> visible, not connected

 Status legend:
 [D] Demo available   [R] Reference only   [N] Not included
```

### 6.9 LLM 失败降级与范围提示

- LLM 在架构规定的最大尝试次数后仍失败时，项目进入 Needs input，不创建 Build Job，且保留 Prompt、附件、Project 和 Session。
- 界面必须显示失败阶段和可执行操作：Retry、Edit request、Use starter Blueprint。
- Use starter Blueprint 是用户主动选择的非 AI 回退方案，界面必须明确标注，不能伪装成模型生成结果。
- `QUOTA_EXCEEDED` 使用独立提示和配额状态，不显示为模型故障。
- Home 和 Workspace 显示剩余额度；达到上限后保留 Project、输入和已有版本，并提供返回编辑、查看/导出已有结果和等待管理员重置的出口。
- V1 不提供自助充值。演示账户使用可由管理员重置的种子 Plan；README 必须写明重置方式或演示限制，验收账户额度至少覆盖规定的 Golden Path 连续测试。
- `unsupported` 输入必须在 Blueprint 前终止，展示支持范围和 Golden Path 示例；不能继续播放角色时间线或构建进度。

## 7. 后续候选范围（未归属版本）

以下功能只能在 V1 P0 稳定后重新评估，不阻塞首次部署，也不自动归入 V2：

- Terminal CLI、本地 Agent Runtime、本地工作区和 `localhost` 应用预览。
- 本地 SQLite 项目恢复，以及本地项目上传或发布到云端的同步协议。
- Follow-up 消息队列的暂停、排序和立即发送。
- Visual Editor 多选。
- 项目搜索、排序和收藏。
- Link Only 的访问 token 和过期时间。
- 更完整的 SEO checklist 与页面级 meta 编辑。
- 公开作品列表。
- 构建完成声音和通知中心。
- 静态站点 zip 导出。
- `unsupported` 结果的一键“按商品目录站改写”草稿；必须先展示改写内容并由用户确认，不能自动提交或构建。

这些候选不应在 P0 未闭环时提前开发。

## 8. 明确不做

V1.0 不实现：

- 任意技术栈的自由代码生成、模型选择器，以及由模型生成并直接执行 Shell 命令。
- 真实多角色并行、候选结果竞速和深度研究模式。
- 任意技术栈项目的构建、依赖安装和代码沙箱。
- 真实 Supabase、Stripe、GitHub、Google、Linear、Asana、Todoist 授权。
- 生成应用内部的数据库管理、用户认证、订单、购物车状态、库存和真实支付。
- GA4/GSC 数据接入和 Google Ads 投放。
- 自定义域名 DNS、SSL 和域名购买。
- 移动 App 生成、Android build、视频/音频生成和文档/PPT 生成。
- 多人 Workspace、评论、邀请和权限管理。
- 真实支付订阅、Wallet、充值和发票；Another Atom 平台自身的 Plan、配额与 Usage Ledger 属于 P0。
- Terminal CLI、本地 Agent Runtime、本地 SQLite 和本地项目执行。
- 对 Atoms 原界面进行像素级复制。

这些不是“以后一定做”的路线承诺，只是从本版本排除。是否进入后续版本要根据 V1 反馈和独立设计决定。

## 9. 状态模型

三个状态层彼此关联，但不能混成一个状态：项目工作状态描述用户当前能做什么，构建状态描述一次任务执行，发布状态描述公开版本。

```text
 Project working state

 Draft --> Blueprint --> Needs input --> Building --> Ready <--> Has changes
              |             |              |
              +-------------+--------------+--> Stopped
                                                   |
                                      +------------+------------+
                                      v                         v
                               Continue from step             Remix

 Build lifecycle

 Queued --> Blueprint --> Awaiting confirm --> Building --> Validating --> QA Review --> Complete
                              |                    |            |             |
                              v                    v            v             `-> Complete degraded
                           Stopped              Failed    Validation issue
                                                   |            |
                                             Retry / Remix    Resolve

 Publish lifecycle

 Unpublished --> Publishing --> Live --> Updating --> Live
                      |            |
                      v            v
                   Failed     Unpublishing --> Paused

 A publish failure keeps the previous Live snapshot unchanged.
```

### 9.1 项目工作状态

- Draft：已创建，尚未构建。
- Blueprint：正在生成或编辑结构化构建输入。
- Building：执行受控 Renderer 与真实构建。
- Needs input：等待用户确认 Blueprint 或补充必要信息。
- Ready：当前版本可预览。
- Has changes：存在未保存修改。
- Stopped：用户停止当前工作流，可从中断阶段继续或 Remix。

### 9.2 构建状态

- Queued -> Blueprint -> Awaiting confirm -> Building -> Validating -> QA Review -> Complete/Complete degraded。
- 任意执行阶段可进入 Stopped。
- Building 失败进入 Failed，提供 Retry 或 Remix；已成功构建后的 Validation issue 才提供 Resolve。
- Complete degraded 只表示 mandatory checks 已通过但 AI QA 摘要未执行，必须在 UI 明确标注。

### 9.3 发布状态

- Unpublished -> Publishing -> Live -> Updating -> Live。
- Live 可进入 Unpublishing -> Paused。
- 发布失败保留上一个 Live 版本，不能把失败结果覆盖到公开地址。

## 10. 核心验收路径

### 10.1 主路径

1. 用户从 Home 的 Prompt Composer 输入 Golden Path prompt，选择 Team Mode，并添加一个可移除的图片附件。
2. 系统创建 Draft 项目并生成 Blueprint，用户修改视觉方向、删除一个非关键模块后确认。
3. Product Manager、Designer、Engineer、QA 按固定顺序接力，分别产生 Blueprint、VisualSpec、AppSpec、ValidationReport/QAReview；时间线标注“分阶段接力”。
4. 构建完成后进入 Mono Market 的 Desktop 预览。
5. 用户切换到 Mobile，并在 Home/Catalog/Product 之间导航。
6. 用户选中首页标题，修改文案；替换一张商品图并 Apply。
7. 用户触发预设路由错误，在 Console 查看错误并点击 Resolve。
8. 系统保存 Version 2；用户对比 Version 1 和 Version 2。
9. 用户 Restore Version 1，系统创建新的恢复版本，历史仍完整。
10. 用户 Publish，选择 Specify Version，复制公开 URL。
11. 在无登录的新浏览器上下文打开 URL，看到指定版本。
12. 用户返回 Home，从最近项目重新打开 Mono Market，Prompt、Blueprint、版本和发布状态仍完整。
13. 用户继续编辑并保存；线上保持原版本，直到点击 Update。

### 10.2 必须验证的反路径

- Prompt 为空、附件上传中或 Blueprint 未确认时，不能进入 Building。
- Blueprint 缺少项目名称、页面或视觉方向时，确认操作必须提示具体缺失字段。
- 有未保存修改时离开项目，需要明确提示。
- 删除项目、Restore、Unpublish 必须二次确认。
- Resolve 失败时要保留原版本和错误信息。
- 发布中断不能让公开链接变成空白或错误版本。
- 所有 Disabled 或 Connect 控件必须解释原因，不能是无反馈死控件。

## 11. 验收标准

### 11.1 功能验收

V1.0 只有同时满足以下条件才算完成：

1. 主路径可在一个连续会话内完整演示，不需要修改数据文件或刷新页面修复状态。
2. Home Prompt Composer 可完成输入、附件、模式选择、提交和错误反馈，不存在静态假控件。
3. Blueprint 可编辑、可确认并实际决定构建结果；未确认时不能开始构建。
4. 项目、Prompt、Blueprint、编辑内容和版本在刷新后仍存在，并可从最近项目恢复。
5. 公开 URL 可从干净浏览器访问，并准确遵守发布版本策略。
6. Desktop 与 Mobile 预览可用，核心文字、控件和面板不重叠。
7. 所有可见按钮都有真实行为、禁用原因或明确的能力边界反馈。
8. 未接通的第三方能力不触发外部授权、API 调用、支付或广告费用。
9. 至少覆盖三层状态中的 Draft、Blueprint、Needs input、Building、Failed、Ready、Live、Paused。
10. 至少覆盖 Build、Edit、Resolve、Restore 四种版本来源。
11. 部署地址可公开访问，README 写明运行方式、演示账号要求和已知边界；若不需要账号，应明确写无账号。
12. 非 Golden Path 输入明确进入 supported、adapted 或 unsupported，不产生超出支持范围的虚假构建。
13. Export JSON 包含约定最小字段，且不包含密钥、凭证、绝对路径、原始对话或内部配额流水。
14. Home 至少有两个可填充示例，Engineer/Team 模式选择处能在提交前说明差异。
15. `adapted` 展示映射/舍弃项，`unsupported` 展示原因和改写建议；Capability Policy 能阻止范围外 Blueprint。
16. Queued 状态展示 `jobs_ahead` 和 Cancel，不在无样本时显示虚假 ETA。
17. 正常 Team Mode 产生可消费 QAReview；deterministic-only 降级明确标注且不计入 Golden Path 成功。
18. Publish 面板持续显示线上/编辑版本；Always Latest 保存动作明确提示会更新线上内容。
19. 配额耗尽后保留 Project 和已有结果，并提供编辑、导出和等待管理员重置的明确出口。

### 11.2 量化验收与产品漏斗

V1 不在没有真实样本的情况下预设 Blueprint 审批率或 Publish 转化率，但必须采集完整漏斗，为后续价值判断建立基线：

```text
prompt_submitted
scope_classified
blueprint_generated
blueprint_approved
role_stage_completed
build_succeeded
preview_opened
revision_applied
published
public_app_opened
```

每条产品事件至少包含 `event_id`、`event_name`、`user_id`、`project_id`、`session_id`、`run_id`、`timestamp`、`mode`、`outcome` 和 `error_code`；公开页面访问等无登录事件允许 `user_id`、`session_id`、`run_id` 为空。事件不得记录完整 Prompt、附件内容或模型私有推理。

部署前必须满足：

- Golden Path 在干净数据下连续执行 5 次，完成率为 5/5。
- 预期漏斗事件完整率为 100%，且顺序符合状态机。
- 跨 Project 或 Session 串事件数量为 0。
- 异步创建 Run/Build Job 的 API 在 1 秒内返回标识。
- 请求被接受后 2 秒内产生第一条用户可见状态事件。
- 5 次刷新恢复测试中，Project、Session、版本和 Publish 状态恢复率为 5/5。

## 12. 风险与取舍

### 12.1 最大风险：真实 LLM 与执行结果脱节

如果真实 LLM 只生成对话文本，而角色进度与 Blueprint、项目状态、版本和最终产物没有关联，用户仍然只会看到一段不可验证过程。V1.0 要求每个关键阶段都改变可检查状态：Blueprint 影响构建，工具事件对应实际执行，编辑影响版本，Resolve 影响错误，Publish 影响公开页面。

### 12.2 公开 URL 会提高实现成本，但不能删除

部署 demo 本体只能证明页面能打开，不能证明“产物发布”闭环。公开版本必须能从干净浏览器访问，因此需要真实持久化和发布快照；具体实现以架构设计文档为准。

### 12.3 功能中心容易制造虚假完成感

Cloud、Integrations、Growth 只保留依赖关系和状态，不做大而空的 dashboard。它们的作用是解释平台边界，而不是增加页面数量。

### 12.4 Golden Path 限制生成范围

真实 LLM 与受控模板结合不能代表任意应用生成，但能同时验证需求理解和稳定落地。界面和文档必须明确这一边界，避免把有限 React 模板包装成任意技术栈生成能力。

### 12.5 首页容易退化成展示页

如果首页只有大标题、输入框样式和模板卡片，没有真实提交、状态反馈和最近项目恢复，它仍然是静态展示。V1.0 要求首页直接承担创建入口，并与 Blueprint 和项目持久化相连。

## 13. 已确认的产品决策

以下产品判断已经确认：

1. 同意选择 V1.0 可部署纵切版。
2. 同意 V1 真实调用 LLM 生成 Blueprint 与 AppSpec，但不允许模型自由生成依赖和 Shell 命令。
3. 同意 Cloud Demo Mode 是唯一 P0 交付形态，本地执行与 Terminal CLI 暂不归属具体版本。
4. 同意 Home、Prompt Composer 和 Blueprint 都属于 P0，首页不是营销页。
5. 同意 P0 只执行 Engineer/Team，并使用 Product Manager、Designer、Engineer、QA 等统一角色名称。
6. 同意使用 Mono Market 作为唯一 Golden Path，并采用有限模板驱动生成。
7. 同意公开 URL、版本策略和跨浏览器访问属于 P0。
8. 同意 Cloud/Integrations/Growth 只做能力中心，除基础 SEO 结果外不接真实服务。

上述决策已经进入设计基线：架构、数据模型、发布方案、目录结构、测试和部署流程见 [Another Atom V1 架构设计](./architecture-design.md)；执行范式、角色 Contract、Human-in-the-loop、Context、Tool、Sandbox、验收和有限修复见 [Another Atom V1 Agent 设计](./agent-design.md)。
