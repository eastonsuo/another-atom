# Another Atom V1.0 产品需求文档

[toc]

- 文档状态：已确认，进入实施
- 版本名称：V1.0 可部署纵切版
- 前置文档：[Atoms 参考产品功能分析](../reference/atoms-reference-analysis.md)
- 技术文档：[Another Atom V1 架构设计](./architecture-design.md)

## 1. 版本结论

推荐实现 **V1.0 可部署纵切版**：做一个可公开访问、可使用用户名密码登录、项目按用户隔离、状态真实保存的 AI 应用生成产品；产品交互受 Atoms 启发，但使用 Another Atom 自己的品牌、角色和信息结构。每个 Project 绑定一个平台服务端本地 Git 仓库，用户可以通过结构化控件或 xterm.js + 受限 Vim WebIDE 修改源码。V1 交付 Cloud 形态，不实现用户电脑上的本地 Agent Runtime。

它不是 Atoms 官网复刻，也不是静态高保真原型。用户必须能完整走通：

`登录 -> 与 Lead 对话 -> Lead 直接回答或调用固定团队 -> 必要时确认风险 -> 预览 -> WebIDE/结构化修改 -> Git 版本 -> 发布`

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
| **V1.0 可部署纵切版** | Lead 二选一路由、固定团队、用户级隔离、本地 Git、受限 Vim WebIDE 和公开发布 | 可操作、可检查、可编辑、可恢复，并验证从对话到代码交付的闭环 | 只支持固定团队和受控源码范围，需要 Linux Sandbox Host | **本次推荐版本** |
| V2.0 自主多 Agent 版 | 在 V1 Lead/Contract 上增加动态任务图、角色子集、并行、返工和仲裁 | 验证真实 Agent 协作与扩展能力 | 上下文、并发配额和收敛控制更复杂 | V1 验收通过后实施 |

## 3. 产品目标

### 3.1 要证明的判断

V1.0 验证六件事：

1. 用户能否使用用户名密码登录，并在切换账号后只看到自己的 Project。
2. Lead 能否把消息稳定路由为直接回答/澄清或调用完整固定团队，且用户能覆盖为“调用团队”。
3. Blueprint 能否把模糊需求转成可检查的团队输入，只在必要风险点请求确认。
4. 一个 Project 能否稳定对应一个服务端本地 Git 仓库，ProjectVersion 能否追溯到 commit。
5. 用户能否通过受限 xterm.js + Vim 编辑当前项目，并安全保存为新版本。
6. 从预览、编辑、版本到发布链接的闭环是否足以让产品从“聊天”变成“工作台”。

### 3.2 不证明的判断

V1.0 不用于证明：

- 大模型能稳定生成任意应用。
- 多 Agent 的内部协作质量优于单 Agent。
- 用户或 Agent 可以安全执行任意代码、Shell、动态依赖或不受控网络。
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
3. **Build Workspace**：Blueprint、通用角色时间线、构建进度、任务消息，以及可刷新的 Project Repository / Run Artifacts 文件树。文件内容由后台按当前用户和 Project/Run 归属读取；未提交 Artifact 与 Git 仓库文件必须分组展示。
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

Lead 路由为 team 后进入项目工作区；若命中 Risk Policy，则先显示内联确认卡片。概念工作区布局如下，具体尺寸和响应式方案留到技术设计阶段：

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

- 未登录用户先进入用户名密码登录/注册页；登录成功后才进入 Studio。
- 第一屏直接进入可用工作台，不设置营销 Landing Page。
- 左侧导航包含 Another Atom 品牌、Home、Projects、Resources 和最近项目。
- 主区域显示中央 Prompt Composer，以及 Blueprint、示例或最近项目入口。
- Prompt Composer 支持多行输入、文件/图片附件、语音入口和发送命令；默认由 Lead 判断直接回答还是调用团队。
- Home 提供至少 2 个可一键填充的受支持示例 Prompt，例如独立设计商品站和书店目录；示例只填充输入，不自动提交。
- 不要求用户先理解 Engineer/Team 模式。Lead 路由后显示“直接回答”或“已调用固定团队”，并提供“调用团队”覆盖入口。
- Prompt Composer 必须覆盖 empty、typing、uploading、ready、submitting、error 六种状态。
- Build 在 Prompt 为空或附件处理中禁用，并给出明确原因。
- 最近项目显示名称、更新时间、当前版本和发布状态；点击后恢复对应工作区。
- 桌面端保留侧栏和中央构建区；移动端改为单区域导航，不能压缩成不可操作的桌面布局。
- 不显示无法解释或不会变化的虚假 credit、通知和在线状态。

#### 6.1.1 登录与用户级项目隔离

- 注册使用唯一 username + password；密码强度不足、用户名占用和登录失败必须给出明确但不泄漏账号存在性的提示。
- 登录使用安全 Session Cookie；退出会撤销当前 Session。账号切换等价于退出后登录另一个账号。
- V1 的租户边界是单个用户，不实现 Organization、邀请、共享 Project 或角色权限。
- Projects、Repository、Version、EditorSession、Run、事件和配额全部绑定当前用户。切换账号后，列表、最近项目、URL 直达和 WebSocket 都不能读取上一账号资源。
- Public URL 是明确发布后的匿名资源，不继承 Studio 的用户隔离；Unpublish 后必须失效。
- 验收至少准备两个账号，各自创建项目，并验证交叉读取、编辑、Preview、Terminal 和事件访问均返回无权限/不存在。

#### 6.1.2 Lead 单一对话入口

- Lead 是 V1 面向用户的唯一默认对话角色，不把内部角色接力直接作为主界面。
- 每条消息只产生 `direct` 或 `team` 两种路由：direct 由 Lead 回答或提出澄清；team 调用 Product Manager、Architect、Engineer、Data Analyst 完整固定团队。
- Lead 不能动态删减/新增专业角色、并行、仲裁返工或自动发布；这些属于 V2。
- 用户可将 direct 覆盖为“调用团队”。Lead 决定 team 时，UI 展示可读原因、预计基础模型调用量和可展开的团队步骤。
- direct 路径不能创建 AppSpec、BuildJob、Git commit 或 ProjectVersion，避免用“自己回答”伪装团队执行。

### 6.2 Blueprint 与项目创建

Blueprint 是 Another Atom 的主要结构化产物，也是用户核查团队理解的事实视图；它不再是所有构建都必须停下的固定审批门：

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
     inspect / edit / risk check
             |
             v
          Build task
```

- 提交 Prompt 后先创建 Draft 项目并生成 Blueprint，不直接播放构建进度。
- Blueprint 包含项目名称、产品类型、页面、模块、视觉方向和数据需求。
- 用户可修改字段、删除非关键模块或返回继续对话。
- 用户已经明确要求创建/修改应用、Blueprint 为 `supported` 且团队调用在基础预算内时，可以继续 Building，不追加无信息量确认。
- Prompt、附件元信息、Blueprint 和确认结果必须随项目持久化。
- V1 只支持商品展示/商品目录站。Product Manager 输出必须包含 `support_level`：`supported`、`adapted` 或 `unsupported`。
- `supported` 展示 Blueprint 后继续固定团队；`adapted` 必须列出被替换、忽略或映射的需求，并等待用户确认。
- `unsupported` 不为原请求创建 Build Job。Product Manager 必须保留原始主题，将其扩展成一份落入 V1 能力范围的完整商品目录需求草案，至少补齐商品类别、Home/Catalog/Product 页面和视觉方向。界面默认展示并填入该草案，用户可直接确认或先修改；确认后以草案创建新的 Run，不能把原请求伪装成已受支持后继续执行。
- Product Manager 还必须输出 `support_reasons[]`、`mapped_requirements[]`、`omitted_requirements[]` 和 `rewrite_suggestion`，使三态判定可以解释和复核。
- 文件和图片附件支持本地选择、名称/大小预览和移除，不上传到第三方服务。
- Projects 支持查看、重命名和删除项目；删除需要二次确认。

#### 6.2.1 风险驱动 Approval

Approval 只在以下必要时刻以内联卡片插入：

- `adapted` 改变或舍弃用户需求。
- 团队预计调用超过基础预算，或需要追加 retry/rework 预算。
- Follow-up/修复将改变已展示页面或模块范围。
- 丢弃未提交 Vim 修改、强制重置或删除 Project。
- Restore 改变当前版本指针。
- Publish、Update、Unpublish 改变公开内容。

普通 supported 构建、预览、打开 Vim、编辑临时 worktree 和显式 Save Version 不重复弹审批。操作按钮已经清楚展示对象与后果时，该点击本身可以构成轻确认；删除等不可逆动作仍使用二次确认。

#### 6.2.2 Project 与服务端本地 Git 仓库

- 每个 Project 创建时自动绑定一个平台服务端 local Git repository，默认一对一。
- 仓库位于执行宿主机持久化磁盘，不是用户电脑目录，也不连接 GitHub/GitLab remote。
- 初始化、Build、Edit、Resolve、Restore 都留下 Git commit；ProjectVersion 显示对应短 commit SHA。
- Restore 创建新 commit 和新 ProjectVersion，不执行 history rewrite；删除 Project 需要二次确认并进入可恢复清理流程。
- Repository 状态至少包含 provisioning、ready、dirty、saving、failed；仓库未 ready 时不能打开 WebIDE 或创建 Build Job。
- V1 不提供 remote、push、pull、branch 管理、SSH key 或 GitHub OAuth。用户代码归属先通过 Project 内可追溯本地仓库成立，远端绑定另行设计。

#### support_level 判定规则与示例

判定先看**主要用户目标**，不能只按关键词匹配：

| 判定 | 边界规则 | 典型输入 | 系统行为 |
| --- | --- | --- | --- |
| `supported` | 主要目标是商品浏览/展示，页面和模块都在 Home、Catalog、Product、展示型购物车入口、基础 SEO 范围内 | “创建独立设计商品站，包含首页、目录、详情和基础 SEO” | 展示 Blueprint，继续固定团队；用户可随时 Stop/Edit |
| `adapted` | 主要目标仍是商品展示；移除或静态替代次要能力后，核心目标不变 | “商品目录站，另外需要登录、收藏和结账” | 保留目录/详情；将登录、收藏、结账标为忽略或展示占位，列出映射后等待确认 |
| `unsupported` | 主要目标依赖真实认证、数据写入、交易、管理后台、实时协作或非商品站信息结构；移除后会改变产品本质 | “实现带库存、订单和支付的电商系统”“创建 CRM 管理后台” | 停止原请求并说明原因；PM 保留主题、生成完整可构建草案，用户确认或编辑后以新 Run 继续 |

一致性约束：

- `adapted` 不能新增真实后端、认证、交易、动态依赖或模板外页面类型。
- 如果被省略能力是用户主要目标，必须判为 `unsupported`，不能为了继续构建而降级成 `adapted`。
- 平台使用固定 Capability Policy 校验 Blueprint；同一输入、同一 Policy 版本必须得到相同的允许/拒绝边界。
- UI 必须同时展示原需求、映射结果和舍弃项。`adapted` 用户确认的是映射后的 Blueprint；`unsupported` 用户确认的是 PM 新生成的可构建需求草案，不是原 Prompt，也不是对原能力范围的放行。

### 6.3 Lead 与固定团队执行

#### Direct 路径

- Lead 回答产品能力、项目状态、现有 Artifact/Version 解释，或提出一个必要澄清问题。
- Direct 不创建 Team Run、BuildJob、Git commit 或 ProjectVersion，也不展示虚假角色时间线。
- 用户认为应执行时，可点击“调用团队”；覆盖操作写入 LeadDecision 事件。

#### Team 路径

- 团队是固定顺序角色接力：Product Manager、Architect、Engineer、Data Analyst 使用独立 instruction 和结构化输出，按顺序消费上一阶段明确产物。
- Product Manager 生成 Blueprint；Risk Policy 检查必要确认；Architect 生成 ArchitectureSpec，Engineer 生成 AppSpec，固定 Renderer 完成构建，Data Analyst 基于 ValidationReport 生成 DataReview。
- 确定性 ValidationReport 是质量门禁，DataReview 只能解释问题和提出建议，不能把失败改写为通过。
- DataReview 必须分别提供 `data_checks`、不可变 `engineering_checks`、warning 和可执行的 Resolve/修改建议；Data Analyst Agent 不能覆盖 Engineer/Validator 的确定性结果，也不能只生成角色消息。
- 当确定性 mandatory checks 已通过，但 Data Analyst Agent 因 Provider 或配额失败不可用时，可以进入 `Data Analyst degraded`：展示“仅完成确定性校验”，直接呈现 ValidationReport，不伪装成 Data Analyst Agent 已完成。Golden Path 验收仍必须包含真实 DataReview。
- `root_cause=app_spec` 且 `resolvable=true` 的 mandatory failure 最多触发 1 轮 Engineer 自动修订；仍失败或根因不明确时进入 Needs input，不自动无限返工。
- 基础 SEO 作为 Blueprint 和构建产物的一部分生成，不设置 Atoms 专有角色名称。
- 默认界面只由 Lead 汇总进度；展开团队详情后标注“固定团队 · 分阶段接力”，展示当前角色、阶段状态和可检查产物。
- 同一时刻只突出一个主执行阶段，避免把阶段事件做成无意义的消息瀑布。
- V1 不并行执行角色，不动态委派，不共享隐藏长期记忆，也不进行自动无限返工；这些属于 V2 自主多 Agent。

#### 路由与执行约束

- 支持 Stop；停止后可 Continue 或 Remix。
- LLM 输出必须经过结构校验和有限重试；文件写入与构建工具必须提供可检查、可恢复的确定性状态。
- 构建完成后自动打开 App Viewer。
- 团队文案明确是固定顺序 Pipeline，不使用“多个 Agent 正在并行协作”“团队自主讨论”等表述，也不展示模型私有推理内容。

Lead 的两个路由必须在行为上可区分，而不只是切换标签：

```text
 Direct

 Message --> Lead --> Answer / Clarify --> End

 Team: fixed sequential role pipeline

 Message --> Lead --> Product Manager --> Blueprint --> Risk Policy --> Architect --> Engineer --> Build --> Data Analyst --> Viewer
              |            |                    |           |          |       |
           requirements  edit/approve       ArchitectureSpec    AppSpec  Validation DataReview
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
- 结构化 Edit Panel 修改受控字段并更新 AppSpec；高级用户可以进入受限 Vim WebIDE 修改允许的源码文件。两种入口最终都必须经过同一 Save Version、Build、Validation 和 Git commit 流程。

### 6.5 可视化编辑

- 文本元素可编辑内容。
- 按钮和强调元素可修改预设颜色。
- 商品图可从内置素材库替换。
- 修改有 Apply/Cancel，不应输入即破坏当前版本。
- Apply 后预览立即更新，并把项目标记为“有未保存改动”。
- 第一版不做任意 DOM 操作、拖拽布局或自由上传图片裁切；源码编辑由独立 WebIDE 承担，不在可视化面板内嵌第二套文本编辑器。

### 6.5.1 xterm.js + Vim WebIDE

- Project Repository ready 后显示“Open code terminal”。点击后创建绑定当前用户、Project 和 base commit 的 EditorSession。
- xterm.js 提供终端显示、输入、resize、重连状态和关闭操作；服务端固定启动 Vim，不提供 bash/zsh 登录 Shell。
- Vim 只看到当前 Project 的临时 worktree 和允许编辑的源码/资产目录；`.git`、依赖清单、lockfile、构建脚本、其他用户文件和平台 Secret 不可见。
- `:write` 只保存到临时 worktree，Studio 同步显示 changed files 和 dirty 状态，不自动 commit、不自动发布。
- Save Version 显示 diff 摘要；用户显式执行后，平台校验 base commit、运行固定 Build/Validation、创建 Git commit 和 ProjectVersion。失败时保留 worktree 和错误，不移动当前版本。
- 同一 Project 同时只允许一个可写 EditorSession；第二个会话只能只读或等待，避免覆盖修改。
- 断线可在短时 grace period 内重连；超时后 Sandbox 销毁，但 dirty worktree 按策略保留到用户保存或明确丢弃。
- Terminal 不显示宿主机路径，不允许 shell escape、插件下载、网络访问、Git remote、任意进程或容器管理命令。

### 6.6 版本与 Remix

- 首次构建生成 Version 1。
- 每次明确保存生成新版本，并记录时间、摘要、来源和 Git commit SHA：Build/Edit/Resolve/Restore。
- 可切换任意版本进行只读预览。
- Restore 把选定历史版本恢复为新的当前版本，不覆盖或删除原历史。
- Remix 从选定版本创建新项目，保留来源关系，但后续修改互不影响。
- 刷新浏览器后，项目、版本和当前编辑状态不能丢失。
- ProjectVersion 与 Git commit 一一对应；版本历史不允许 force reset、rebase 或删除旧 commit。

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
  "repository": {
    "provider": "local_git",
    "default_branch": "main",
    "head_commit_sha": "abc123..."
  },
  "blueprint": {},
  "architecture_spec": {},
  "app_spec": {},
  "current_version": {
    "id": "version_2",
    "number": 2,
    "source": "Build|Edit|Resolve|Restore",
    "created_at": "2026-07-11T00:00:00Z",
    "summary": "Updated hero copy",
    "git_commit_sha": "abc123..."
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
- `unsupported` 输入必须在 Product Manager 完成范围判断后、Architect 和 Build 前终止原 Run。界面展示原因和 PM 生成的可构建草案；用户确认或编辑草案后创建新 Run，不能让原 Run 继续播放后续角色时间线或构建进度。

## 7. 后续候选范围（未归属版本）

以下功能只能在 V1 P0 稳定后重新评估，不阻塞首次部署，也不自动归入 V2：

- Terminal CLI、本地 Agent Runtime、本地工作区和 `localhost` 应用预览。
- 本地 SQLite 项目恢复，以及本地项目上传或发布到云端的同步协议。
- Follow-up 消息队列的暂停、排序和立即发送。
- Project 对话线程持久化：为 Lead 询问/澄清、团队构建和 Follow-up 消息增加 `project_id / run_id / thread_id`，支持按 Project 恢复完整对话历史；账号级、尚未创建 Project 的 direct 询问继续单独保存。
- Visual Editor 多选。
- 项目搜索、排序和收藏。
- Link Only 的访问 token 和过期时间。
- 更完整的 SEO checklist 与页面级 meta 编辑。
- 公开作品列表。
- 构建完成声音和通知中心。
- 静态站点 zip 导出。

这些候选不应在 P0 未闭环时提前开发。

## 8. 明确不做

V1.0 不实现：

- 任意技术栈的自由代码生成，以及由模型生成并直接执行 Shell 命令。
- 真实多角色并行、候选结果竞速和深度研究模式。
- 任意技术栈项目的构建、依赖安装和代码沙箱。
- 真实 Supabase、Stripe、GitHub、Google、Linear、Asana、Todoist 授权。
- 生成应用内部的数据库管理、用户认证、订单、购物车状态、库存和真实支付。
- GA4/GSC 数据接入和 Google Ads 投放。
- 自定义域名 DNS、SSL 和域名购买。
- 移动 App 生成、Android build、视频/音频生成和文档/PPT 生成。
- 多人 Workspace、评论、邀请和权限管理。
- 真实支付订阅、Wallet、充值和发票；Another Atom 平台自身的 Plan、配额与 Usage Ledger 属于 P0。
- 用户电脑上的 Terminal CLI、本地 Agent Runtime、本地 SQLite 和本地项目执行；V1 的 xterm/Vim 是云端受限 Project WebIDE，不是宿主 Shell。
- 对 Atoms 原界面进行像素级复制。

这些不是“以后一定做”的路线承诺，只是从本版本排除。是否进入后续版本要根据 V1 反馈和独立设计决定。

## 9. 状态模型

五个状态层彼此关联但不能混成一个状态：项目工作、Lead/Build、Repository、EditorSession 和发布状态分别描述不同事实。

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

 Lead routing --> Direct complete
       |
       `-> Team queued --> Blueprint --> Awaiting risk confirm? --> Building --> Validating --> Data Analyst Review --> Complete
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

 Repository lifecycle

 Provisioning --> Ready <--> Dirty --> Saving --> Ready
       |                    |          |
       `-> Failed           `----------`-> Failed (head unchanged)

 Editor lifecycle

 Starting --> Ready --> Connected <--> Dirty --> Saving --> Closed
     |                                      |
     `-> Failed                       Expired / Failed
```

### 9.1 项目工作状态

- Draft：已创建，尚未构建。
- Blueprint：正在生成或编辑结构化构建输入。
- Building：执行受控 Renderer 与真实构建。
- Needs input：等待用户澄清、处理 Risk Approval 或补充必要信息。
- Ready：当前版本可预览。
- Has changes：存在未保存修改。
- Stopped：用户停止当前工作流，可从中断阶段继续或 Remix。

### 9.2 构建状态

- Lead routing -> Direct complete，或 Team queued -> Blueprint -> Awaiting risk confirm（可选）-> Building -> Validating -> Data Analyst Review -> Complete/Complete degraded。
- 任意执行阶段可进入 Stopped。
- Building 失败进入 Failed，提供 Retry 或 Remix；已成功构建后的 Validation issue 才提供 Resolve。
- Complete degraded 只表示 mandatory checks 已通过但 AI Data Analyst 摘要未执行，必须在 UI 明确标注。

### 9.3 发布状态

- Unpublished -> Publishing -> Live -> Updating -> Live。
- Live 可进入 Unpublishing -> Paused。
- 发布失败保留上一个 Live 版本，不能把失败结果覆盖到公开地址。

### 9.4 Repository 与 Editor 状态

- Repository provisioning 失败时 Project 进入 Needs input，不能打开 WebIDE 或构建。
- Dirty 只表示临时 worktree 有修改；Git head 和当前 ProjectVersion 不变。
- Saving 成功后创建 commit/ProjectVersion 并回到 Ready；失败保留 dirty worktree 和原 head。
- EditorSession 过期或 Sandbox 失败不等于 Repository 损坏；平台根据 worktree 保留策略允许恢复或明确丢弃。

## 10. 核心验收路径

### 10.1 主路径

1. 用户 A 使用用户名密码登录，从 Lead 对话输入 Golden Path prompt，并添加一个可移除的图片附件。
2. Lead 输出 `route=team`；系统创建 Draft Project 和 local Git repository，Product Manager 生成 Blueprint。
3. Blueprint 为 supported，基础预算内不重复审批；Architect、Engineer、Data Analyst 按固定顺序接力，产生 ArchitectureSpec、AppSpec、ValidationReport/DataReview。
4. 构建完成后进入 Mono Market 的 Desktop 预览。
5. 用户切换到 Mobile，并在 Home/Catalog/Product 之间导航。
6. 用户先在结构化 Edit Panel 修改标题，再打开 xterm/Vim 修改允许的源码文件；worktree 显示 dirty。
7. 用户触发预设路由错误，在 Console 查看错误并点击 Resolve。
8. 用户执行 Save Version；系统完成 Build/Validation、创建 Git commit 和 Version 2，并显示 commit SHA。
9. 用户 Restore Version 1，系统创建新的恢复版本，历史仍完整。
10. 用户 Publish，选择 Specify Version，复制公开 URL。
11. 在无登录的新浏览器上下文打开 URL，看到指定版本。
12. 用户退出账号 A，登录账号 B，无法看到或通过 URL/Terminal 访问 Mono Market；重新登录 A 后项目、Repository、版本和发布状态完整。
13. 用户继续编辑并保存；线上保持原版本，直到点击 Update。

### 10.2 必须验证的反路径

- Prompt 为空、附件上传中、Lead 尚在澄清或存在 pending risk approval 时，不能进入 Building。
- 登录失败不能创建 Session；伪造 user id、跨用户 Project/Version/Terminal URL 必须被拒绝。
- Blueprint 缺少项目名称、页面或视觉方向时，团队不能继续，Lead 必须提示具体缺失字段并澄清。
- 有未保存修改时离开项目，需要明确提示。
- 删除项目、Restore、Unpublish 必须二次确认。
- 打开第二个可写 EditorSession 必须进入只读/等待；base commit 冲突不能覆盖已有修改。
- Sandbox 退出、断网或超时必须保留明确状态；用户不能通过 Vim 读取 `.git`、Secret、宿主路径或其他用户文件。
- Resolve 失败时要保留原版本和错误信息。
- 发布中断不能让公开链接变成空白或错误版本。
- 所有 Disabled 或 Connect 控件必须解释原因，不能是无反馈死控件。

## 11. 验收标准

### 11.1 功能验收

V1.0 只有同时满足以下条件才算完成：

1. 主路径可在一个连续会话内完整演示，不需要修改数据文件或刷新页面修复状态。
2. 用户名密码注册/登录/退出可用；两个账号切换后 Project、Repository、Version、Terminal、事件和配额隔离。
3. Lead direct/team 路由可验证；direct 不创建 Team Run，team 执行完整固定团队，用户可覆盖 direct 为 team。
4. Blueprint 可编辑并实际决定构建结果；supported 基础构建不重复审批，adapted 和风险动作必须确认。
5. 每个 Project 唯一绑定 local Git repository；Build/Edit/Resolve/Restore 的 ProjectVersion 均能解析到有效 commit SHA。
6. xterm/Vim 只访问当前 Project 临时 worktree；Save Version 通过 Build/Validation 后才 commit，失败不移动当前版本。
7. 项目、Prompt、Blueprint、dirty worktree 和版本在刷新/短时断线后可恢复。
8. 公开 URL 可从干净浏览器访问，并准确遵守发布版本策略。
9. Desktop 与 Mobile 预览可用，核心文字、控件和面板不重叠。
10. 所有可见按钮都有真实行为、禁用原因或明确的能力边界反馈。
11. 未接通的第三方能力不触发外部授权、API 调用、支付或广告费用。
12. 至少覆盖三层状态中的 Draft、Blueprint、Needs input、Building、Failed、Ready、Live、Paused。
13. 至少覆盖 Build、Edit、Resolve、Restore 四种版本来源。
14. 部署地址可公开访问，README 写明运行方式、演示账号要求和已知边界。
15. 非 Golden Path 输入明确进入 supported、adapted 或 unsupported，不产生超出支持范围的虚假构建。
16. Export JSON 包含 repository/commit 信息，且不包含密钥、凭证、绝对路径、原始对话或内部配额流水。
17. Home 至少有两个可填充示例；Lead 路由原因和“调用团队”覆盖入口在执行前可见。
18. `adapted` 展示映射/舍弃项，`unsupported` 展示原因和 PM 生成的完整可构建草案；用户确认或编辑后创建新 Run，Capability Policy 仍能阻止原范围外 Blueprint 进入 Build。
19. Queued 状态展示 `jobs_ahead` 和 Cancel，不在无样本时显示虚假 ETA。
20. 正常 team route 产生可消费 DataReview；deterministic-only 降级明确标注且不计入 Golden Path 成功。
21. Publish 面板持续显示线上/编辑版本；Always Latest 保存动作明确提示会更新线上内容。
22. 配额耗尽后保留 Project 和已有结果，并提供编辑、导出和等待管理员重置的明确出口。

### 11.2 量化验收与产品漏斗

V1 不在没有真实样本的情况下预设 Blueprint 审批率或 Publish 转化率，但必须采集完整漏斗，为后续价值判断建立基线：

```text
login_succeeded
prompt_submitted
lead_routed
scope_classified
blueprint_generated
risk_approval_requested / risk_approval_decided
repository_ready
role_stage_completed
build_succeeded
preview_opened
editor_opened
version_committed
revision_applied
published
public_app_opened
```

每条产品事件至少包含 `event_id`、`event_name`、`user_id`、`project_id`、`session_id`、`run_id`、`timestamp`、`route`、`outcome` 和 `error_code`；公开页面访问等无登录事件允许 `user_id`、`session_id`、`run_id` 为空。事件不得记录密码、Cookie、终端输入流、完整 Prompt、附件内容或模型私有推理。

部署前必须满足：

- Golden Path 在干净数据下连续执行 5 次，完成率为 5/5。
- 预期漏斗事件完整率为 100%，且顺序符合状态机。
- 跨 User、Project 或 Session 串事件数量为 0。
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
3. 同意 Cloud Mode 是唯一 P0 交付形态；用户电脑上的本地执行与 Terminal CLI 暂不归属具体版本，云端 xterm/Vim 只作为受限 Project WebIDE。
4. 同意 Home、Prompt Composer 和 Blueprint 都属于 P0，首页不是营销页。
5. 同意 V1 使用 Lead、Product Manager、Architect、Engineer、Data Analyst 等统一角色名称；Lead 只做 direct/team 二选一路由，团队保持固定顺序。
6. 同意使用 Mono Market 作为唯一 Golden Path，并采用有限模板驱动生成。
7. 同意公开 URL、版本策略和跨浏览器访问属于 P0。
8. 同意 Cloud/Integrations/Growth 只做能力中心，除基础 SEO 结果外不接真实服务。
9. 同意 Approval 只在 adapted、额外预算、范围变化、破坏性仓库操作和线上变更等必要风险点出现，普通 supported 构建不重复确认 Blueprint。
10. 同意 V1 使用用户名密码和服务端 Session，实现 user-level 多租户隔离；不实现 Organization/共享 Workspace。
11. 同意每个 Project 一对一绑定平台服务端 local Git repository，ProjectVersion 映射 Git commit；V1 不连接 Git remote。
12. 同意提供 xterm.js + 受限 Vim WebIDE；真实 PTY/Build 必须运行在独立 Sandbox，不能暴露宿主 Shell、`.git`、Secret 或其他用户目录。

上述决策已经进入设计基线：架构、数据模型、发布方案、目录结构、测试和部署流程见 [Another Atom V1 架构设计](./architecture-design.md)；执行范式、角色 Contract、Human-in-the-loop、Context、Tool、Sandbox、验收和有限修复见 [Another Atom V1 Agent 设计](./agent-design.md)。
