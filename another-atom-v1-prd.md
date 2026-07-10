# Another Atom V1.0 产品需求文档

[toc]

- 文档状态：待确认
- 版本名称：V1.0 可部署纵切版
- 前置文档：[Atoms 参考产品功能分析](./atoms-reference-analysis.md)
- 后续文档：用户确认本版本后再编写技术设计文档。

## 1. 版本结论

推荐实现 **V1.0 可部署纵切版**：做一个可公开访问、可完成核心任务、状态真实保存的 Atoms 产品体验 demo；AI 生成和第三方平台能力采用受控模拟。

它不是 Atoms 官网复刻，也不是静态高保真原型。用户必须能完整走通：

`创建项目 -> 输入需求 -> 选择模式 -> 确认计划 -> 查看 Agent 执行 -> 预览应用 -> 修改内容 -> 处理错误 -> 保存版本 -> 发布 -> 打开公开链接`

```text
 +---------+    +---------+    +-----------+    +---------+
 | Project |--->| Prompt  |--->| Plan / HIL|--->| Build   |
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

选择这个版本的原因是：Atoms 的核心价值存在于链路连续性，而不在功能数量。若第一版同时做真实多 Agent、代码沙箱、Supabase、Stripe、GitHub、GA4/GSC 和广告投放，工程风险会主要来自外部系统，反而无法判断主产品交互是否成立。

## 2. 版本选择

| 版本 | 定义 | 优势 | 代价 | 适用边界 |
| --- | --- | --- | --- | --- |
| V0.1 展示版 | 静态页面和预设动效 | 最快，适合讲概念 | 没有真实状态和任务闭环 | 只能做视觉评审，不符合“可用版本”目标 |
| **V1.0 可部署纵切版** | 核心交互真实，生成与外部服务受控模拟 | 可操作、可发布、能验证产品结构 | 不能证明真实 AI 和平台集成能力 | **本次推荐版本** |
| V1.5 半真实能力版 | V1.0 加一个真实 AI 或外部集成 | 能验证一个关键技术依赖 | 成本、稳定性和密钥管理复杂度上升 | V1.0 通过后再选一个方向 |
| V2.0 平台版 | 真实生成沙箱、Cloud、发布、支付和多集成 | 接近生产产品 | 已经不是 demo，工程与运维边界完全改变 | 仅在目标变成长期产品时成立 |

## 3. 产品目标

### 3.1 要证明的判断

V1.0 只验证三件事：

1. 用户是否能理解 Engineer/Team 两种模式带来的执行差异。
2. Agent 的计划、进度、人工确认、错误和版本是否能让生成过程可控。
3. 从预览、编辑到发布链接的闭环是否足以让产品从“聊天”变成“工作台”。

### 3.2 不证明的判断

V1.0 不用于证明：

- 大模型能稳定生成任意应用。
- 多 Agent 的内部协作质量优于单 Agent。
- 生成代码可安全地在多租户沙箱执行。
- Supabase、Stripe、GitHub、Google Ads、GA4/GSC 已真实接通。
- Atoms Cloud、计费和 App World 已达到生产可用水平。

这些能力如果在界面出现，必须明确标记为“演示连接”或“此版本不可用”，不能让用户误以为会产生真实数据、授权或费用。

```text
 +-------------------------------------------------------------+
 | REAL PRODUCT BEHAVIOR                                       |
 | Projects / Editing / Persistence / Versions / Public URL    |
 +-------------------------------------------------------------+
                              |
                              v
 +-------------------------------------------------------------+
 | CONTROLLED SIMULATION                                       |
 | Agent timeline / Build progress / Resolve / Sarah SEO       |
 +-------------------------------------------------------------+
                              |
                              v
 +-------------------------------------------------------------+
 | VISIBLE, NOT CONNECTED                                      |
 | Cloud / OAuth integrations / Ads / Analytics / Billing      |
 +-------------------------------------------------------------+
```

判断标准不是“页面是否出现”，而是状态是否真实改变：第一层必须保存和影响后续行为；第二层必须可重复且明确标注；第三层只能解释能力边界。

## 4. 目标用户与演示任务

### 4.1 目标用户

第一版只服务一个明确场景：需要快速理解 Atoms 产品逻辑并评估后续开发价值的产品、设计或研发评审者。

不面向真实外部客户长期建站，也不处理多人组织管理。

### 4.2 Golden Path

默认演示任务：

> 创建一个名为 Mono Market 的独立设计商品站，包含首页、商品列表、商品详情、购物车入口和基础 SEO。整体风格克制、编辑感强，适配桌面端和手机端。

选择商品站而不是纯 Landing Page，是因为它能同时验证多页面预览、内容编辑、响应式布局、错误处理、版本和发布；又不要求第一版实现真实订单、库存和支付。

V1.0 对其他自由输入只做有限解析：提取项目名称、主色、页面类型和关键模块，并映射到预设站点结构。产品不声称支持任意应用生成。

## 5. 产品结构

V1.0 包含六个可操作区域：

1. **Projects**：项目列表、创建项目和最近状态。
2. **Build Chat**：prompt、模式、计划确认、Agent 进度和任务消息。
3. **App Viewer**：桌面/手机预览、页面切换、刷新和选择元素。
4. **Edit Panel**：修改文本、颜色和图片，并形成新版本。
5. **Versions**：版本列表、预览、恢复和 Remix。
6. **Publish**：发布设置、公开链接、分享和下线。

Cloud、Integrations、Growth 作为项目侧栏中的能力中心存在，但只承担边界说明和演示状态，不扩展成独立后台。

概念工作区布局如下，具体尺寸和响应式方案留到技术设计阶段：

```text
 +------------------+-----------------------------------------------+
 | Projects         | Project header                 Version Publish|
 |                  +--------------------+--------------------------+
 | + New project    | Build Chat         | App Viewer               |
 |                  |                    |                          |
 | Recent           | Mode switch        | Desktop / Mobile         |
 | - Mono Market    | Agent timeline     | Route switch             |
 | - Remix copy     | Human approval     | Interactive preview      |
 |                  | Prompt / Attach    |                          |
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

### 6.1 项目与创建

- 显示项目列表，至少包含名称、封面、更新时间、当前版本和发布状态。
- 支持创建、重命名和删除 demo 项目；删除需要二次确认。
- 新项目可以输入 prompt，也可以使用 Golden Path 示例。
- 支持选择 Engineer Mode 或 Team Mode。
- Deep Research 和 Race Mode 可见但禁用，分别说明“本 demo 不实现研究产物”和“Max/并行模型能力未接入”。
- 文件和图片附件支持本地选择、名称/大小预览和移除，不上传到第三方服务。

### 6.2 模式与 Agent 执行

#### Engineer Mode

- 只显示 Alex 执行。
- 计划步骤较少，直接进入构建。
- 预估时间和 credit 展示为 demo 指标，不进行真实扣费。
- 适合用户观察“快速、低成本、覆盖窄”的模式特征。

#### Team Mode

- Mike 先拆解任务。
- Emma 输出页面和功能范围，Bob 输出站点结构，Alex 构建，Sarah 输出基础 SEO。
- 进入 Human-in-the-Loop 确认：用户可编辑、确认或取消待办。
- 用户确认后按阶段展示进度、当前 Agent 和阶段产物。
- 同一时刻只突出一个主执行阶段，避免把模拟流程做成无意义的消息瀑布。

#### 共同行为

- 支持 Stop；停止后可 Continue 或 Remix。
- 构建流程可重复执行，结果必须确定，不依赖外部模型稳定性。
- 构建完成后自动打开 App Viewer。
- Agent 文案明确是演示流程，不伪造真实模型推理内容。

两种可执行模式必须在流程上可区分，而不只是切换标签：

```text
 Engineer Mode

 Prompt --> Alex --> Build --> Validate --> Viewer
             |
             `-- short path / no approval gate

 Team Mode

 Prompt --> Mike --> Plan --> Human approval --> Specialists
                                      |              |
                               edit / confirm        +-- Emma
                                                     +-- Bob
                                                     +-- Alex
                                                     `-- Sarah
                                                          |
                                                          v
                                                   Build + SEO
                                                          |
                                                          v
                                                        Viewer
```

### 6.3 App Viewer

- 默认展示一个可交互的 Mono Market 站点，不使用静态截图代替应用。
- 支持 Home、Catalog、Product 三个路由。
- 支持 Desktop/Mobile 两种固定预览尺寸，切换时工作区布局不跳动。
- 支持刷新预览和在新标签打开当前预览。
- 支持选中标题、正文、按钮和商品图片；选中后打开 Edit Panel。
- Console 展示 info/error 两类事件，可清空。
- 提供一个可复现的模拟错误，例如商品详情按钮路由失效；点击 Resolve 后恢复并形成修复记录。

### 6.4 可视化编辑

- 文本元素可编辑内容。
- 按钮和强调元素可修改预设颜色。
- 商品图可从内置素材库替换。
- 修改有 Apply/Cancel，不应输入即破坏当前版本。
- Apply 后预览立即更新，并把项目标记为“有未保存改动”。
- 第一版不做任意 DOM 操作、拖拽布局、代码编辑器或自由上传图片裁切。

### 6.5 版本与 Remix

- 首次构建生成 Version 1。
- 每次明确保存生成新版本，并记录时间、摘要和来源：Build/Edit/Resolve/Restore。
- 可切换任意版本进行只读预览。
- Restore 把选定历史版本恢复为新的当前版本，不覆盖或删除原历史。
- Remix 从选定版本创建新项目，保留来源关系，但后续修改互不影响。
- 刷新浏览器后，项目、版本和当前编辑状态不能丢失。

### 6.6 发布与分享

- 支持首次 Publish、Update 和 Unpublish。
- 支持两种发布策略：Always Latest、Specify Version。
- 发布成功后生成稳定公开 URL，并可复制和打开。
- 公开 URL 应在无登录、无本地项目状态的浏览器中访问，展示被发布版本。
- Specify Version 下继续编辑或保存新版本，不应改变线上内容；手动 Update 后才改变。
- Always Latest 下保存新版本后，线上内容应更新到最新保存版本。
- Share 支持 Public 和 Link Only；Private 不进入 V1.0，因为第一版没有真实账号和成员体系。
- 支持编辑公开卡片的标题、描述和封面。
- Export 至少导出包含项目信息、当前内容和版本摘要的 JSON；静态代码 zip 不属于 P0。

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

### 6.7 能力中心

能力中心用于说明完整产品边界，不负责伪造已接通的平台。

- Cloud：展示 Database、Auth、Payments、Domains、Keys、AI 的能力说明和依赖关系。
- Integrations：展示 Supabase、Stripe、GitHub、Linear、Asana、Todoist。
- Growth：展示 Sarah SEO、GA4/GSC、Adrian Ads。
- 每项只允许三种状态：Available in Atoms、Demo simulation、Not included。
- 不出现真实 OAuth 按钮，不采集 API Key，不执行广告或支付动作。
- Sarah 在 Team Mode 中生成的 meta title、description 和 sitemap preview 可在 Growth 中查看，这是能力中心唯一的可操作结果。

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
            +-- Sarah SEO --------> demo output available
            +-- GA4 / GSC --------> visible, not connected
            `-- Adrian Ads -------> visible, not connected

 Status legend:
 [A] Available in Atoms   [D] Demo simulation   [N] Not included
```

## 7. P1 候选范围

以下功能可以在 P0 稳定后加入，但不阻塞首次部署：

- Prompt Queue 的暂停、排序和立即发送。
- Visual Editor 多选。
- 项目搜索、排序和收藏。
- Link Only 的访问 token 和过期时间。
- 更完整的 SEO checklist 与页面级 meta 编辑。
- App World 风格的公开项目列表。
- 构建完成声音和通知中心。
- 静态站点 zip 导出。

P1 不应在 P0 未闭环时提前开发。

## 8. 明确不做

V1.0 不实现：

- 真实 LLM 调用、代码生成或模型选择。
- 真实多 Agent 并行执行、Race Mode 和 Deep Research。
- 任意技术栈项目的构建、依赖安装和代码沙箱。
- 真实 Supabase、Stripe、GitHub、Google、Linear、Asana、Todoist 授权。
- 数据库管理、用户认证、订单、购物车状态、库存和真实支付。
- GA4/GSC 数据接入和 Google Ads 投放。
- 自定义域名 DNS、SSL 和域名购买。
- 移动 App 生成、Android build、视频/音频生成和文档/PPT 生成。
- 多人 Workspace、评论、邀请和权限管理。
- 真实 plan、credit 扣费、Wallet、充值和发票。
- 对 Atoms 原界面进行像素级复制。

这些不是“以后一定做”的路线承诺，只是从本版本排除。是否进入 V1.5 要根据 V1.0 的反馈决定。

## 9. 状态模型

三个状态层彼此关联，但不能混成一个状态：项目工作状态描述用户当前能做什么，构建状态描述一次任务执行，发布状态描述公开版本。

```text
 Project working state

 Draft --> Planning --> Needs input --> Building --> Ready <--> Has changes
              |             |              |
              +-------------+--------------+--> Stopped
                                                   |
                                      +------------+------------+
                                      v                         v
                               Continue from step             Remix

 Build lifecycle

 Queued --> Planning --> Awaiting approval --> Building --> Validating --> Complete
                              |                    |            |
                              v                    +----+-------+
                           Stopped                      v
                                                   Failed
                                                      |
                                             +--------+--------+
                                             v                 v
                                          Resolve           Remix

 Publish lifecycle

 Unpublished --> Publishing --> Live --> Updating --> Live
                      |            |
                      v            v
                   Failed     Unpublishing --> Paused

 A publish failure keeps the previous Live snapshot unchanged.
```

### 9.1 项目工作状态

- Draft：已创建，尚未构建。
- Planning：正在生成或等待确认计划。
- Building：执行模拟构建。
- Needs input：等待用户确认或补充。
- Ready：当前版本可预览。
- Has changes：存在未保存修改。
- Stopped：用户停止当前工作流，可从中断阶段继续或 Remix。

### 9.2 构建状态

- Queued -> Planning -> Awaiting approval -> Building -> Validating -> Complete。
- 任意执行阶段可进入 Stopped。
- Building 或 Validating 可进入 Failed；Failed 可 Resolve 或 Remix。

### 9.3 发布状态

- Unpublished -> Publishing -> Live -> Updating -> Live。
- Live 可进入 Unpublishing -> Paused。
- 发布失败保留上一个 Live 版本，不能把失败结果覆盖到公开地址。

## 10. 核心验收路径

### 10.1 主路径

1. 用户创建项目，使用 Golden Path prompt，选择 Team Mode。
2. Mike、Emma、Bob、Alex、Sarah 依次出现，系统生成可编辑计划。
3. 用户删除一个非关键待办并确认。
4. 构建完成后进入 Mono Market 的 Desktop 预览。
5. 用户切换到 Mobile，并在 Home/Catalog/Product 之间导航。
6. 用户选中首页标题，修改文案；替换一张商品图并 Apply。
7. 用户触发预设路由错误，在 Console 查看错误并点击 Resolve。
8. 系统保存 Version 2；用户对比 Version 1 和 Version 2。
9. 用户 Restore Version 1，系统创建新的恢复版本，历史仍完整。
10. 用户 Publish，选择 Specify Version，复制公开 URL。
11. 在无登录的新浏览器上下文打开 URL，看到指定版本。
12. 用户继续编辑并保存；线上保持原版本，直到点击 Update。

### 10.2 必须验证的反路径

- 未确认 Team Mode 计划时，不能进入 Building。
- 有未保存修改时离开项目，需要明确提示。
- 删除项目、Restore、Unpublish 必须二次确认。
- Resolve 失败时要保留原版本和错误信息。
- 发布中断不能让公开链接变成空白或错误版本。
- Disabled 的 Race/Deep Research/Connect 按钮必须解释原因，不能是无反馈死控件。

## 11. 验收标准

V1.0 只有同时满足以下条件才算完成：

1. 主路径可在一个连续会话内完整演示，不需要修改数据文件或刷新页面修复状态。
2. 项目、编辑内容和版本在刷新后仍存在。
3. 公开 URL 可从干净浏览器访问，并准确遵守发布版本策略。
4. Desktop 与 Mobile 预览可用，核心文字、控件和面板不重叠。
5. 所有可见按钮都有真实行为、禁用原因或明确的模拟反馈。
6. 模拟能力不触发外部授权、API 调用、支付或广告费用。
7. 至少覆盖三层状态中的 Draft、Needs input、Building、Failed、Ready、Live、Paused。
8. 至少覆盖 Build、Edit、Resolve、Restore 四种版本来源。
9. 部署地址可公开访问，README 写明运行方式、演示账号要求和已知边界；若不需要账号，应明确写无账号。

## 12. 风险与取舍

### 12.1 最大风险：把模拟流程做成动画

如果 Agent 进度与项目状态、版本和最终产物没有关联，用户只会看到一段预录过程。V1.0 要求每个关键阶段都改变可检查状态：计划影响任务，编辑影响版本，Resolve 影响错误，Publish 影响公开页面。

### 12.2 公开 URL 会提高实现成本，但不能删除

部署 demo 本体只能证明页面能打开，不能证明 Atoms 的“产物发布”闭环。公开版本必须能从干净浏览器访问，因此需要真实持久化和发布快照；具体实现放到技术设计文档决定。

### 12.3 功能中心容易制造虚假完成感

Cloud、Integrations、Growth 只保留依赖关系和状态，不做大而空的 dashboard。它们的作用是解释平台边界，而不是增加页面数量。

### 12.4 Golden Path 限制生成范围

模板驱动无法代表真实 AI，但结果稳定、可比较，适合验证主链路。界面和文档必须明确这一边界，避免把确定性模板包装成任意生成能力。

## 13. 进入技术设计前需要确认的产品决策

请确认以下版本判断，而不是技术栈：

1. 同意选择 V1.0 可部署纵切版。
2. 同意 P0 只执行 Engineer/Team，Race/Deep Research 可见但禁用。
3. 同意使用 Mono Market 作为唯一 Golden Path，并采用有限模板驱动生成。
4. 同意公开 URL、版本策略和跨浏览器访问属于 P0。
5. 同意 Cloud/Integrations/Growth 只做能力中心，除 Sarah SEO 结果外不接真实服务。

确认后，技术设计文档将只围绕上述已批准范围，定义架构、数据模型、发布方案、目录结构、测试和部署流程。
