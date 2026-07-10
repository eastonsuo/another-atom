# Atoms 公开功能分析

[toc]

- 文档状态：评审稿
- 资料截止：2026-07-10
- 资料范围：[Atoms Help Center](https://help.atoms.dev/en) 英文站、各功能文章及截至 2026-06-15 的 Changelog。

## 1. 分析边界

本文回答的是：**从官方公开材料看，Atoms 已经实现并向用户提供了哪些产品能力，这些能力如何组成完整工作流。**

“所有功能”在本文中指帮助中心和 Changelog 明确披露的用户可感知能力，不等同于 Atoms 的内部能力全集。官方没有公开的模型编排、代码生成、运行时隔离、发布基础设施和安全实现，本文不补设定。

为避免把发布记录当成稳定承诺，功能按三种证据强度处理：

- **正式能力**：存在独立帮助文章，使用方式和边界相对明确。
- **更新记录能力**：只在 Changelog 中出现，说明产品已发布或在特定场景逐步开放，但完整可用范围不能判断。
- **冲突或未知**：官方材料彼此不一致，或只描述结果而未说明机制。

## 2. 核心判断

Atoms 不是单一 AI 编程对话框，而是围绕“从意图到在线产品”的 Agent 工作台。它的产品主链路是：

`输入需求与资料 -> 选择 Agent/模式 -> 计划与执行 -> 预览和编辑 -> 数据与外部服务 -> 校验和修复 -> 版本与发布 -> 分享和增长 -> 用量与成本管理`

下面是基于公开功能整理的概念关系图，不代表 Atoms 官方技术架构：

```text
 Prompt / Files / Images / URL / Project / Keys
                         |
                         v
              +----------------------+
              | Agent Orchestration  |<---- Human approval
              | Modes + Models       |----> Task for Human
              +----------+-----------+
                         |
                         v
              +----------------------+
              | Project Workspace    |
              | Chat + Viewer + Edit |
              +----+------------+----+
                   |            |
          +--------+            +---------+
          v                               v
 +------------------+          +--------------------+
 | Cloud & Services |          | Quality & Recovery |
 | Data/Auth/API/AI |          | Validate/Fix/Resume|
 +--------+---------+          +---------+----------+
          |                              |
          +---------------+--------------+
                          v
              +------------------------+
              | Versions + Remix       |
              +-----------+------------+
                          |
                          v
              +------------------------+
              | Publish + Domains      |
              +-----------+------------+
                          |
              +-----------+------------+
              v                        v
       Share / App World        SEO / Analytics / Ads

 Account / Plan / Credits / Wallet govern the full workflow.
```

真正构成产品差异的不是某个 Agent 名称，而是四个连续机制：

1. **任务编排**：根据任务复杂度切换单 Agent、多 Agent、竞速或深度研究。
2. **可见执行**：用户能看到计划、阶段结果、待确认事项、错误和恢复过程。
3. **工程闭环**：产物可预览、编辑、保存版本、恢复、发布和继续 Remix。
4. **上线后闭环**：数据库、认证、支付、域名、SEO、分析和广告进入同一工作区。

## 3. 功能全景

### 3.1 需求输入与创建入口

该功能域解决“用户如何把意图、上下文和资源交给系统”。

#### 正式能力

- 通过自然语言描述网站、应用、数据分析、研究或内容任务。
- 上传文件、文件夹和图片作为上下文；上传文章明确给出的单文件上限为 100MB。
- 通过 `@Agent` 指定 Agent，例如 `@Alex`、`@David`、`@Sarah`。
- 通过 `#` 引用指定文件或内容，减少 Agent 搜索范围和 credit 消耗。
- 从官方模板、App World 项目或历史版本开始，而不是每次从空项目开始。

#### 更新记录能力

- 首页和 Chat 支持语音输入及语音转文字。
- Prompt Queue 支持任务执行期间追加消息，并可暂停、继续、排序、编辑、删除、清空或立即发送。
- 升级后的 `#` 选择器可引用 Upload、AI、Keys、Projects；还支持 URL、Secret 和项目引用。
- 文件夹拖放上传、文本预览、图片附件、公开文件链接和项目媒体目录。
- 简单问答可不启动完整 Agent 环境，直接返回结果。
- 首页提供多语言模板提示和 Prototype、Video Mode 等快捷入口。

#### 产物类型

官方材料明确出现过以下产物：

- 网站和 Web 应用。
- 移动应用、移动预览和 Android 构建包。
- Deep Research 报告。
- PPT/Slides、Docs、PDF 和 Markdown-to-PDF。
- 数据分析、图表和结构化文件。
- 图片、音频、语音、视频和音乐。
- 接入 LLM 的 AI 应用，例如客服、导师和内容生成工具。

其中移动应用、多媒体生成、PDF 分析等主要来自 Changelog；不同账户和场景的开放范围不能仅凭帮助中心判断。

来源：[Overview](https://help.atoms.dev/en/articles/12087744-overview)、[Quick Start](https://help.atoms.dev/en/articles/12128979-quick-start)、[Upload File/Folder](https://help.atoms.dev/en/articles/12129040-upload-file-folder)、[Communicating with Agents](https://help.atoms.dev/en/articles/12174308-communicating-with-agents)、[Changelog](https://help.atoms.dev/en/articles/12174667-changelog)

### 3.2 Agent 团队与执行模式

该功能域解决“由谁处理任务、如何组织执行、用户在何处介入”。

#### Agent 角色

| Agent | 官方角色 | 主要任务边界 |
| --- | --- | --- |
| Mike | Team Leader | 拆解和分配任务，协调其他 Agent |
| Emma | Product Manager | 需求分析、市场研究、PRD 和路线图 |
| Bob | System Architect | 系统架构和技术方案 |
| Alex | Software Engineer | 全栈开发、功能实现、修复和部署 |
| David | Data Analyst | 数据处理、机器学习、爬取和数据问答 |
| Iris | Deep Researcher | 资料收集、筛选、分析和研究报告 |
| Sarah | SEO Specialist | 多语言 SEO 内容和搜索优化 |

这些是产品对用户呈现的角色分工。它们是否对应独立模型、独立上下文或固定内部 SOP，官方没有说明，不能判断。

#### 模式差异

模式决定执行路径，而 Agent 角色是路径中的专业节点：

```text
 User prompt --> Mode
                  |
                  +-- Engineer --> Alex -----------------> Build / Fix
                  |
                  +-- Team -----> Mike --> Human approval
                  |                         |
                  |                         v
                  |                  Specialists by task
                  |                  +-- Emma  : Product
                  |                  +-- Bob   : Architecture
                  |                  +-- Alex  : Engineering
                  |                  +-- David : Data
                  |                  +-- Sarah : SEO
                  |                  `-- Iris  : Deep Research
                  |
                  `-- Race ------> Candidate A --+
                                   Candidate B --+--> Compare / Select
                                   Candidate N --+

 Deep Research belongs to Team Mode.
 Race cannot be combined with Deep Research, Supabase, or Stripe projects.
```

| 模式 | 为什么合理 | 优势 | 代价 | 适用边界 |
| --- | --- | --- | --- | --- |
| Engineer Mode | 简单开发不需要完整团队 | 启动快、流程短、credit 较省 | 分析和专业覆盖较窄 | 适合小网站、原型、局部开发和修复；默认由 Alex 工作 |
| Team Mode | 复杂任务需要不同专业角色协作 | 能覆盖产品、架构、开发、数据和 SEO | 流程更重、耗时和 credit 更高 | 适合复合型应用、研究、数据和增长任务 |
| Race Mode | 同一需求并行得到多个候选结果 | 可比较模型或结果，增加选择空间 | 并行执行意味着更高消耗 | Max 计划能力；官方说明不支持 Supabase/Stripe 项目 |
| Deep Research Mode | 研究任务需要搜集、筛选和可追溯整理 | 适合深度报告，并可转为网站、PPT、PDF 或 Docs | 时间和 credit 成本较高 | 仅 Team Mode；不能与 Race Mode 同时使用 |

#### 执行控制

- Human-in-the-Loop：Agent 先给出可编辑待办，用户确认后执行，降低需求理解偏差。
- Task for Human / Ask Human：执行中要求用户补充信息或完成外部动作。
- 子 Agent 委派：把复杂开发拆成聚焦任务，形成“计划、委派、实现、验证”的流程。
- 模型选择：首页和设置中可选择默认或推荐模型，也支持 Auto；具体模型列表持续变化。
- 停止、继续与恢复：用户可停止生成；中断任务可继续或从恢复点重启。
- Agent 反馈：消息反馈、版本评分和 AI Feedback Assistant 用于评价结果或进入问题处理。

来源：[Your Agents Team](https://help.atoms.dev/en/articles/12129380-your-agents-team)、[Mode Switching Guide](https://help.atoms.dev/en/articles/12129385-mode-switching-guide)、[Race Mode](https://help.atoms.dev/en/articles/12129504-race-mode)、[Deep Research](https://help.atoms.dev/en/articles/12136255-deep-research)、[Changelog](https://help.atoms.dev/en/articles/12174667-changelog)

### 3.3 项目工作区、预览与编辑

该功能域解决“用户如何理解、检查并修改 Agent 产物”。

从功能关系看，工作区是 Chat、产物预览和修改工具之间的联动层，而不是三个孤立页面：

```text
 +----------------+ +--------------------------+ +----------------+
 | Project / Chat | | App Viewer               | | Edit / Inspect |
 |                | |                          | |                |
 | Prompt         | | Desktop / Mobile         | | Visual Editor  |
 | Agent progress | | Route switch             | | Selected item  |
 | Human task     | | Interactive app          | | Text / Color   |
 | Deliverables   | | Refresh / Open preview   | | Asset replace  |
 +-------+--------+ +-------------+------------+ +--------+-------+
         ^                        |                       |
         |                        +---- Select item ------+
         |                                                |
         +--------------- Apply / Ask Agent --------------+

                         +------------------+
                         | Console / Issues |
                         | Logs + Resolve   |
                         +------------------+
```

#### App Viewer

- Agent 生成应用后，在 Chat 内提供实时预览。
- 支持桌面端和移动端预览、刷新和预览链接。
- 移动项目支持二维码预览；Web 端到端流程也适配移动浏览器。
- 支持应用路由下拉切换，便于检查多页面应用。
- 支持受保护预览和专用认证流程，访问受限时显示原因。
- Console 显示运行信息和错误；错误可进入 Resolve 流程。

#### 编辑能力

- 可选择页面中的视觉元素进行编辑。
- Visual Editor 支持多选、工具栏和更明确的沙箱启动状态。
- Select to Chat 可把选中元素带入对话，让 Agent 基于具体元素修改。
- Editor/Edit Mode 用于更精细地调整内容；Changelog 还出现文件 diff、文件改名和删除等编辑状态。
- 支持主题和模板选择，并提供暗色主题预览缩略图。

#### 文件与媒体工作区

- 文件可预览、下载、复制，生成资产按项目目录归档。
- 图片、音频和视频结果可用交付卡片展示。
- 媒体资产中心集中管理生成的图片、音频和视频。
- Video Mode 覆盖生成、预览、剪辑选择、切分、缩放和本地导出。
- 长文件支持分段读取；PDF 支持指定页范围分析。

不能判断：生成项目实际使用的前端框架、包管理器、浏览器沙箱、容器生命周期和代码执行隔离策略。

来源：[App Viewer](https://help.atoms.dev/en/articles/12129698-app-viewer)、[Issue Report](https://help.atoms.dev/en/articles/12129264-issue-report)、[Changelog](https://help.atoms.dev/en/articles/12174667-changelog)

### 3.4 后端、数据与外部服务

该功能域解决“生成的前端如何拥有持久数据、身份、业务逻辑和第三方能力”。

公开材料显示两条后端路径和一组外部连接器。它们不是同一种能力：Atoms Cloud/Supabase 承担应用运行依赖，Connector 主要承担工作流数据交换。

```text
 Generated App
      |
      +--> Atoms Cloud
      |      +-- Database / Auth / Storage
      |      +-- Serverless / Keys / AI
      |      +-- Domains
      |      +-- Stripe
      |           `-- requires backend mode at project creation
      |
      +--> Supabase
      |      +-- Database / Auth
      |      +-- Edge Functions / Secrets
      |      `-- reconnect required after Remix
      |
      `--> Workflow Connectors
             +-- GitHub
             +-- Linear
             +-- Asana
             `-- Todoist
```

#### Atoms Cloud

正式文章列出的核心能力包括：

- Database：保存用户、商品、订单等持久数据。
- Auth：注册、登录、权限和 Session，包含邮箱密码与 Google 等登录方式。
- Payments：通过 Stripe 提供一次性支付或订阅。
- Custom Domains：给上线应用绑定自定义域名。
- API Key Management：保存第三方服务密钥。
- AI Integrations：在已发布应用中调用 GPT、Claude 等模型能力。

Changelog 进一步确认了数据库和存储管理界面：

- 查看 PostgreSQL 表结构，浏览和编辑表数据。
- 搜索、筛选和分页，CSV 导入与导出。
- 按项目和目录查看存储用量，搜索、排序、分页、面包屑导航和批量清理。
- Cloud 资源包括数据库存储/计算、容器镜像、Serverless、对象存储及其读写操作。
- Secrets/Production Keys 支持在构建和部署场景中补充密钥。

#### Supabase Connect

- 授权连接已有 Supabase 项目并读取表结构和安全设置。
- 支持邮箱密码与 Google 登录。
- 配置数据表并同步 Atoms UI 与 Supabase 数据。
- 使用 Edge Functions 处理邮件、表单、提醒、AI API 和支付等服务端逻辑。
- API Key 可保存到 Supabase Edge Functions Secrets Manager。
- Remix 后需要重新连接 Supabase；带 Supabase 的 App World 项目存在 Remix 限制。

#### Stripe Connect

- 支持一次性购买、订阅、卡支付、发票、退款、收据、交易和 payout 状态。
- 必须使用 Atoms Cloud，并在创建项目时启用 backend mode。
- 官方文章明确说明，已有非 Backend 项目不能后补开启该 Stripe 路径。

#### 其他外部集成

- GitHub：授权、创建仓库、Push、Pull 和保留提交历史；官方文章写明仅 Pro+ 可用，但 Pro+ 与当前计划名称关系不清晰。
- Linear：查询、总结、创建和更新 issue，也可辅助 sprint、standup、release notes 和 handoff。
- Asana：查询、创建和更新任务、评论及负责人/截止日期/状态。
- Todoist：创建和组织任务，设置优先级、日期、提醒和重复规则。
- Connector 的实际动作受连接账号权限和 Connector 支持范围限制。

不能判断：Atoms Cloud 底层厂商、租户隔离方式、数据备份、区域、SLA、密钥托管方案和运行时安全边界。

来源：[Atoms Cloud](https://help.atoms.dev/en/articles/13036940-atoms-cloud)、[Supabase Connect](https://help.atoms.dev/en/articles/12129788-supabase-connect)、[Stripe Connect](https://help.atoms.dev/en/articles/13038231-stripe-connect)、[GitHub Connect](https://help.atoms.dev/en/articles/13222322-github-connect)、[Connect and use integrations](https://help.atoms.dev/en/articles/15112407-connect-and-use-integrations)、[AI Integrations](https://help.atoms.dev/en/articles/13362318-ai-integrations)、[Cloud & AI Billing Guide](https://help.atoms.dev/en/articles/15645831-cloud-ai-billing-guide)

### 3.5 质量检查、错误处理与恢复

该功能域解决“自动生成失败或结果不可靠时，用户如何发现问题并继续工作”。

```text
 Build --> Preview --> Page Validation --> Ready
   |          |              |
   |          |              +--> Failed check
   |          +------------------> Runtime issue
   +-----------------------------> Build issue
                                      |
                                      v
                              Issue / Bug Report
                                      |
                         +------------+------------+
                         v                         v
                      Resolve             Resume / Remix
                         |                         |
                         +------------+------------+
                                      |
                                      v
                              Rebuild + Validate
```

- Issue Report：构建失败或 terminal error 时出现问题入口。
- Bug Report：展开日志和系统信息，便于判断失败上下文。
- Resolve：让 Agent 根据错误自动修复。
- 自动 Terminal Error Detection：识别终端错误并引导处理。
- Page Validation：检查按钮、表单、导航和核心交互，显示进度、结果和分数；登录、支付、游戏等场景采用不同检查逻辑。
- AI Code Review：用于开发结果的质量检查。
- Metrics、logging、observability：记录命令失败、Agent 活动和关键流程日志。
- Build Task Resume：中断的构建从指定阶段恢复，并处理进度和 credit 状态。
- 版本恢复保护：恢复失败时避免破坏原状态。

官方 Issue Report 建议：若连续 2-3 轮仍无法修复，可从当前版本 Remix 到新 Chat，减少旧上下文干扰。这说明 Remix 同时承担恢复策略，而不只是复制项目。

来源：[Issue Report](https://help.atoms.dev/en/articles/12129264-issue-report)、[Remix](https://help.atoms.dev/en/articles/12129010-remix)、[Changelog](https://help.atoms.dev/en/articles/12174667-changelog)

### 3.6 版本、发布与域名

该功能域解决“如何把一次生成变成可维护、可访问的线上版本”。

#### 版本与分支

版本、恢复、Remix 和发布的关系可以压缩为：

```text
 Build             Edit              Resolve
   |                 |                  |
   v                 v                  v
  V1 -------------->V2 -------------->V3
   |                  |
   |                  +--> Remix ------> New project / New history
   |
   +--> Restore V1 --------------------> V4
                                         (new current version;
                                          V1-V3 remain in history)

 Publish target:

   Always Latest  ---------------------> newest saved version
   Specify Version --------------------> pinned V1 / V2 / V3 / V4
```

- 项目在执行过程中生成版本记录。
- 可直接切换预览版本。
- 可把历史版本恢复为当前状态，并显示恢复进度和失败保护。
- Remix 可从 App World、项目或历史版本创建独立副本，不影响原项目。
- Remix 可缩短长对话上下文并减少重复 credit 消耗。
- App World 的 Replay 可播放应用从 prompt 到结果的逐步创建过程。

#### 发布

- Publish 生成线上链接；发布后入口变为 Update。
- 后续改动不会自动进入线上版本，除非选择 Always Latest 或手动 Update。
- Specify Version 可把线上应用锁定到指定保存版本。
- 支持 Unpublish 和应用状态切换。
- 发布后的 Overview 显示应用信息、线上状态和后续入口。
- 移动项目可触发 Android Build 并下载构建包。

#### 域名

- 可修改免费的 `.atoms.world` 子域名。
- 可连接已有域名，文档说明需要配置 A Record 和 TXT Record。
- 可通过 IONOS 购买域名。
- 可设置 Primary Domain，并把其他域名重定向到主域名。
- 更新记录还出现 DNS/SSL 检查、多域名展示、批量解绑和 Live/Paused 状态。

来源：[Publish](https://help.atoms.dev/en/articles/12129354-publish)、[Remix](https://help.atoms.dev/en/articles/12129010-remix)、[Connect and Manage Domains](https://help.atoms.dev/en/articles/13362391-connect-and-manage-domains)、[Changelog](https://help.atoms.dev/en/articles/12174667-changelog)

### 3.7 分享、发现与协作

该功能域解决“项目如何被其他人访问、复用和共同维护”。

#### 分享权限与导出

- Public：公开访问，并可进入 App World。
- Link Only：仅持有链接的人访问。
- Private：仅项目所有者或授权成员访问。
- Paid 用户可设置默认 Chat 权限。
- Export 可下载项目文件；Deep Research 和演示文档也有对应导出能力。
- 支持分享到 X、Instagram、LinkedIn 和 TikTok。
- App Card 可配置封面、名称、描述和分享版本。
- 分享链接使用访问 token 加强访问控制。

#### App World

- 公开项目的发现、分类、语言筛选和详情页。
- Templates 和 Showcase 用于筛选高质量项目并开始 Remix。
- 支持点赞、查看 credit 成本、公开标签和 SEO 友好路由。
- Replay 展示完整构建过程。

#### Workspace 协作

- Pro/Max Workspace 支持邀请协作者；2026-06-15 更新记录写明协作者席位为无限，Free 保持单成员。
- 协作场景包含工作状态、邀请链接、计划降级时的成员限制提示。
- Atoms Badge 可按账户默认或按项目控制；正式 Publish 文档写明 Pro/Max 可移除 Badge。

来源：[Share](https://help.atoms.dev/en/articles/12129279-share)、[Publish](https://help.atoms.dev/en/articles/12129354-publish)、[Changelog](https://help.atoms.dev/en/articles/12174667-changelog)

### 3.8 SEO、分析与广告增长

该功能域解决“应用上线后如何被搜索、衡量和投放”。

#### SEO

- Sarah 通过 `@Sarah` 或包含 SEO 意图的 prompt 触发，仅在 Team Mode 可用。
- 生成或优化多语言 SEO 内容。
- 配置页面 title、description、sitemap 和可索引页面。
- Publish 后在 Google Search Console 添加站点、通过 HTML Tag 验证并提交 sitemap。
- 公开页面使用可读 URL slug，并对私有、功能性或无效页面的索引规则做限制。

#### Marketing / Growth

- 连接 GA4，查看流量来源、用户行为和转化信号。
- 连接 Google Search Console，查看 Indexed Pages、Clicks、Impressions、CTR 和 Position。
- Growth 流程包含属性/站点连接、验证、授权状态、无数据提示和报告。
- Audience & Analytics 提供进入增长模块的统一入口。

#### Adrian Ads Agent

- 从产品和 Landing Page 提取广告信息。
- 生成广告文案、关键词、受众、预算、竞价和 campaign plan。
- 支持 Awareness、Traffic、Leads、Sales 等目标策略。
- 监控 CTR、CVR、Spend、Conversions、ROAS、CPC、CPA、地域、设备和人群特征。
- 支持多语言广告内容和基于数据的优化建议。

广告功能涉及真实 Google Ads 账户和支出。官方文章描述了自动执行，但账户审核、预算保护、归因准确性和误投处理机制披露不足，不能判断。

来源：[SEO](https://help.atoms.dev/en/articles/13362077-search-engine-optimization-seo)、[Boosting your SEO](https://help.atoms.dev/en/articles/12752284-boosting-your-seo)、[Marketing Module](https://help.atoms.dev/en/articles/14057591-marketing-module-guide)、[Adrian Ads Agent](https://help.atoms.dev/en/articles/14342754-adrian-ads-agent-for-automated-campaigns)、[Changelog](https://help.atoms.dev/en/articles/12174667-changelog)

### 3.9 账户、计划、用量与生态

该功能域解决“谁能使用哪些能力、如何控制费用，以及如何获得支持”。

#### 账户与设置

- 邮箱注册、Magic Link、Google 一键登录、邮箱验证和密码重置。
- 用户头像、用户名和用户资料页。
- 多语言界面、主题选择和默认模型设置。
- 通知中心、构建完成声音、订阅/credit 到期邮件和余额提醒。
- Chat 收藏、项目列表、Workspace 及成员邀请。

#### 计划与 credits

- 公开计划分为 Free、Pro、Max；Pro/Max 可选择不同 monthly credit 档位。
- Engineer、Team、Deep Research、Race 的消耗和计划边界不同。
- 长对话会增加 credit 消耗；官方建议先做 MVP、精确描述需求、合并同模块改动并用 Remix 缩短上下文。
- 计划支持月付、年付、升级、降级、取消、退款规则和促销码兑换；具体价格可能变化。

#### Cloud & AI Wallet

- Wallet balance、免费 Cloud/AI quota、充值、自动充值、余额提醒和 monthly limit。
- Usage 按 Cloud、AI、项目和资源显示，数据每日 UTC 0:00 更新。
- Transactions 记录充值、平台 credits、退款和调整；与资源用量明细分开。
- Cloud 按数据库、计算、Serverless、对象存储等实际资源计费；已发布应用的模型推理计入 AI 用量，开发期模型消耗不属于该项。
- 免费额度和余额都耗尽后，依赖 Cloud/AI 的应用可能暂停或停止。
- Monthly limit 不是严格实时硬停，延迟上报的用量仍可能产生费用。

#### 学习、社区与商业生态

- Help Center、AI 问答、Video Center、How-to Guides 和 Community & Support。
- App World 模板和示例用于学习与 Remix。
- Explorer Program 提供测试资格、认证、奖励和曝光。
- Affiliate Program 提供推荐佣金；比例属于易变化商业信息，不作为稳定功能参数。

来源：[Plans & Billing](https://help.atoms.dev/en/collections/15118226-plans-billing)、[Cloud & AI Wallet](https://help.atoms.dev/en/articles/14432563-cloud-ai-wallet)、[Cloud & AI Billing Guide](https://help.atoms.dev/en/articles/15645831-cloud-ai-billing-guide)、[Optimizing Credit Usage](https://help.atoms.dev/en/articles/12130438-optimizing-credit-usage)、[Changelog](https://help.atoms.dev/en/articles/12174667-changelog)

## 4. 功能之间的关键依赖

以下依赖决定了 Atoms 不是可随意拆散的功能集合：

1. **Stripe 依赖 Atoms Cloud 和项目创建时的 backend mode**，不能把支付当作后加插件。
2. **Sarah 和 Deep Research 依赖 Team Mode**；Race Mode 又与 Deep Research、Supabase/Stripe 存在不兼容边界。
3. **SEO/Growth 依赖已发布站点**，因为 GSC 验证、sitemap 和线上指标都需要公开地址。
4. **Publish 依赖版本状态**，线上可指向最新版本或指定版本；Update 决定修改何时进入生产。
5. **Remix 同时依赖版本和连接状态**，复制代码不等于复制 Supabase 授权或 Cloud 资源。
6. **Cloud/AI 应用依赖 Wallet**，余额和免费额度耗尽会影响已发布应用的持续可用性。
7. **App World 依赖分享权限**，Public 项目可进入发现和 Remix，Private/Link Only 不应被公开索引。

## 5. 公开材料中的冲突与不能判断

### 5.1 明确冲突

- Max Package 文章曾写 40GB，Changelog 又写 Max 容量从 40GB 增至 100GB。当前准确容量应以实时 Pricing/账户页为准。
- GitHub Connect 写“Pro+”，当前计划主结构是 Free/Pro/Max；Pro+ 与现行计划的映射不能判断。
- Help Center 首页显示各集合的文章总数，与进入集合后的数量不一致，首页统计可能未同步。
- 部分文章仍链接 `support.mgx.dev` 或使用 MGX 名称，品牌迁移关系不影响功能判断，但文档维护状态并不完全一致。

### 5.2 不能判断

- Agent 是否使用独立模型、独立上下文或固定协作协议。
- Race Mode 实际并行数量、候选选择算法和失败回退机制。
- 代码生成使用的固定技术栈、沙箱、容器、依赖缓存和网络权限。
- Atoms Cloud 的底层云厂商、区域、备份、SLA、租户隔离和数据删除保证。
- Page Validation、AI Code Review 的覆盖率和误报/漏报水平。
- Ads Agent 的预算硬限制、账户审核、自动暂停和异常投放保护。
- Changelog 中带有 “supported scenarios”“eligible users” 的功能，具体计划、地区和灰度范围。

## 6. 对 atoms_demo 的直接启示

功能分析只给出一个结论：**demo 的主干必须是从 prompt 到公开版本的连续闭环，而不是把上述九个功能域各做一张卡片。**

最值得保留的产品骨架是：模式差异、Agent 可见协作、App Viewer、可编辑结果、错误修复、版本恢复、发布链接。Cloud、集成、SEO、广告、Wallet 和 App World 用来说明平台边界，但是否进入 demo 的可操作范围，应由单独的版本文档决定。

对应范围见 [atoms_demo_v1_product_spec.md](./atoms_demo_v1_product_spec.md)。

## 7. 主要资料索引

- [Help Center 首页](https://help.atoms.dev/en)
- [Getting Started](https://help.atoms.dev/en/collections/15029509-getting-started)
- [Features](https://help.atoms.dev/en/collections/15031586-features)
- [Integrations](https://help.atoms.dev/en/collections/15033323-integrations)
- [Tips & Tricks](https://help.atoms.dev/en/collections/15035000-tips-tricks)
- [Plans & Billing](https://help.atoms.dev/en/collections/15118226-plans-billing)
- [Changelog](https://help.atoms.dev/en/articles/12174667-changelog)
