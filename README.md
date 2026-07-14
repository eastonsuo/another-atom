# Another Atom

[简体中文](./README.md) | [English](./README.en.md)

> 把模糊想法转化为用户可查看和编辑代码、持续迭代、管理版本并自主发布的软件项目。

## 产品结论

Another Atom 是一个多智能体 Vibe Coding 工作台。用户可以提出任意软件产品目标，专业 Agent 负责规划、实现和校验；Project 工作区把代码文件、版本历史、运行结果和发布状态放在同一条持续开发链路中。网页项目还可以直接在 Studio 中预览和进行视觉修改。

它与 [Atoms](https://help.atoms.dev/en) 面向同一个核心目标：让用户从意图出发，得到一个可以运行、可以修改、可以管理代码并可以发布的软件项目。Another Atom 使用自己的品牌、交互、Contract 和工程实现，不复用 Atoms 的源代码、私有 Prompt 或未公开基础设施。

```text
想法 / 资料 / 现有项目
          |
          v
     与 Lead 对话
          |
          v
   多智能体规划与执行
          |
          v
  项目代码 + 可用运行结果
          |
    +-----+-------------------+
    |                         |
    v                         v
运行 / 预览（有适配器）   查看 / 编辑 / 管理文件
    |                         |
    +-----------+-------------+
                v
          校验 / 修复 / 版本
                |
                v
          用户确认发布
                |
                v
         继续对话和迭代
```

完整产品判断与取舍见[整体产品目标与定位](./docs/design/整体/01-[产品]-整体产品目标与定位.md)。

## 要解决的核心问题

- **[从想法到实现]** 用户可能只有一个目标，没有完整需求、架构和代码。系统需要帮助补全必要信息，并直接形成可以运行的结果。
- **[AI 过程不可检查]** 单次 Prompt 很难判断模型理解了什么、为什么这样实现、失败发生在哪一步。多智能体需要通过明确分工和可查看产物，让过程可以理解和纠偏。
- **[生成结果难以继续]** 一次性代码或截图无法自然承接后续修改。Project 需要保存代码文件、当前状态和历史版本，让用户回到同一项目继续开发。
- **[用户缺少代码和上线控制]** Vibe Coding 不能把代码藏起来，也不能让新生成结果自动覆盖线上版本。用户需要查看和编辑代码，并明确决定发布哪个版本。

## 核心产品能力

### 多智能体协作

- **[单一入口]** 用户主要与 Lead 对话，不需要先理解内部角色、模式和流程。
- **[专业分工]** Product Manager、Architect、Engineer、Data Analyst、Reviewer 分别处理需求、结构、实现、数据和独立审查；确定性 Validator 提供不可由 Agent 改写的工程证据。
- **[按任务演进]** 简单任务应走短路径，复杂任务再调用更多角色、工具和返工；多智能体的目的不是增加 Agent 数量，而是降低不同类型的不确定性。
- **[用户介入]** 用户可以查看、修改和确认关键方案；系统只在范围、预算、破坏性操作和发布等真实风险处停下。

### Vibe Coding 工作区

- **[自然语言开发]** 用户通过对话创建、解释、修改和修复项目，不要求先定位代码文件或写出实现步骤。
- **[按项目类型运行]** Preview 是网页项目的运行与检查能力，不是产品范围限制。非 Web 项目仍应生成并管理对应源码、产物和版本；只有存在匹配的 Runtime 适配器时才提供直接运行或预览。
- **[视觉与代码双入口]** 普通用户可以选择界面元素修改内容和样式；需要精确控制时，可以查看和编辑项目代码文件。
- **[文件管理]** Project 展示源码、生成产物和媒体文件，支持查看、刷新、选择和后续扩展的增删改操作。
- **[针对当前对象继续对话]** 用户可以基于当前页面、元素、文件、错误或版本继续要求 Agent 修改，不必每次重新描述整个项目。

### Project、代码与版本

- **[Project 是核心资产]** 一个 Project 对应一份持续存在的软件项目，而不是一段 Chat。需求、代码、Agent 产物、版本和发布状态都归入 Project。
- **[代码仓库归属]** 每个 Project 默认绑定代码仓库，用户对源码拥有可见、可编辑和可带走的控制权；平台内部版本必须能追溯到 Git commit。
- **[修改形成版本]** Agent Build、用户 Edit、代码保存、自动修复和 Restore 都形成新版本，不覆盖历史。
- **[恢复不改历史]** 恢复旧版本会创建新的当前版本；过去的版本和操作记录继续保留。
- **[发布指针独立]** 用户可以发布最新版本或指定版本；新草稿、新构建和 Restore 不应偷偷改变线上结果。

### 从构建到在线产品

- **[质量闭环]** 构建结果需要经过可解释的校验；错误应能定位、修复和重新验证，而不是只提示“生成失败”。
- **[公开访问]** 用户可以把确认过的版本发布为稳定链接，并在后续修改后明确 Update。
- **[后续能力]** 数据库、认证、支付、域名、分析、SEO、第三方连接和作品分享属于从“应用原型”走向“在线产品”的长期能力，但必须围绕同一个 Project 和发布版本工作。
- **[持续迭代]** 发布不是终点。用户可以回到项目继续对话、修改、验证并发布下一版本。

## 产品界面

登录页通过用户名和密码建立会话；Project、源码仓库、版本和 Sandbox Session 都按账号隔离。

<p align="center">
  <img src="./docs/assets/readme/login-zh.png" alt="Another Atom 中文登录页：用户名密码登录与账号级项目隔离说明" width="480">
</p>

Studio 将 Lead 对话、专业 Agent、Project 历史、模型选择和账号配额放在同一工作区。

<p align="center">
  <img src="./docs/assets/readme/studio-home-v2-zh.png" alt="Another Atom 中文 Studio 首页：Lead 对话、固定专业团队、项目列表和真实 LLM 状态" width="640">
</p>

构建工作区同时展示可持久化进度、可交互 Preview、Project Repository、当前 Run Artifact 和运行日志。

<p align="center">
  <img src="./docs/assets/readme/studio-build-workspace-zh.png" alt="Another Atom 构建工作区：阶段流水线、移动端预览、项目文件树和运行日志" width="640">
</p>

对于网页项目，生成结果可以直接作为网页应用运行；用户可以检查真实交互、项目源码和结构化产物。其他项目类型不会为了获得 Preview 被改写成网页。

<p align="center">
  <img src="./docs/assets/readme/studio-game-preview-zh.png" alt="Another Atom 已完成的贪吃蛇游戏：可交互预览、阶段流水线、运行日志与 Project 文件" width="640">
</p>

Build、Edit 和 Restore 分别形成新版本；历史不会被覆盖，线上版本仍由用户显式选择。

<p align="center">
  <img src="./docs/assets/readme/version-history-zh.png" alt="Another Atom 版本历史：Build、Edit 和 Restore 都创建新版本" width="480">
</p>

## 整体设计原则

这些原则分别回答四个问题：项目如何持续推进、Agent 如何协作、平台如何控制权限，以及结果如何保存和发布。

### 1. 项目如何持续推进

- **[Project 承载完整开发过程]** 用户得到的不是一次回答，而是一份可以持续修改的软件项目。需求、Agent 产物、代码仓库、Preview、版本和发布状态统一归入 Project；用户再次进入时，可以从已有代码和状态继续开发。

- **[所有修改入口指向同一个 Project]** 对话用于表达意图，Preview 用于检查行为，视觉工具用于快速调整，源码文件用于精确控制。无论从哪个入口修改，结果都会回到同一个 Project，并记录在同一份版本历史中。

### 2. Agent 如何分工和交接

- **[角色通过可检查产物协作]** Lead 负责接收用户请求；Product Manager、Architect、Engineer、Data Analyst、Reviewer 分别负责产品、架构、代码、数据和独立审查。每个角色都要交付 Blueprint、ArchitectureSpec、源码、DataProfile 或 ReviewReport 等明确结果，而不是通过头像数量或对话长度制造“多人协作”的感觉。

- **[每个角色只接收当前任务需要的信息]** Agent 不共享一段无限增长的聊天记录。平台根据当前角色和任务准备必要 Context，再通过版本化 Artifact、Evidence 和 Handoff 传递结果，使输入、产出和失败原因都可以检查、恢复和追溯。

- **[正常流程自动推进，风险变化交给用户确认]** 用户明确要求构建后，已授权范围和基础预算内的工作自动继续；如果范围、预算、代码安全或线上发布状态发生变化，系统必须先获得用户确认。

### 3. 平台如何控制权限和执行

- **[模型负责生成，平台负责执行和授权]** LLM 负责理解需求、制定方案、生成代码和解释结果；平台 Runtime 负责身份、配额、流程状态、工具权限、仓库写入、Sandbox 和发布。模型可以提出要做什么，但不能绕过平台直接执行高权限操作。

- **[所有私有能力都先确认用户和 Project]** REST、SSE、私有 Preview 和 Terminal WebSocket 都通过统一 Gateway 识别登录 Session，并确认当前用户是否有权访问对应的 Run、Project、Version 和 Sandbox Session。Public Route 单独处理，只读取用户已经明确发布的版本。

### 4. 项目结果如何保存、发布和恢复

- **[代码、Git 提交和项目版本保持对应]** 每个 Project 默认拥有代码仓库。成功构建、用户编辑、代码保存和 Restore 都会形成 ProjectVersion，并对应一次 Git commit；自动修复产生的中间 Artifact 单独保留，只有通过校验的结果才进入版本历史。

- **[修改中的版本与线上版本分开管理]** 生成完成不等于上线。Project 中的工作版本可以持续变化，Public Route 只展示用户最后一次明确 Publish/Update 的版本；Restore 会创建新版本，不删除历史，也不会自动改变线上内容。

- **[页面状态以已保存的记录为准]** 用户看到的阶段、错误、用量、产物和版本都来自持久化记录。刷新页面、Worker 重启或恢复任务时，系统应复用已经完成的工作，避免重复调用模型、重复结算用量或重复创建版本。

## 整体逻辑架构

```text
用户浏览器
Studio / Preview / 文件与终端界面
                    |
              HTTPS / WSS
                    v
+----------------------------------------------------+
| 统一入口与平台主服务（Gateway / Control Plane）     |
| 身份与归属 | Lead 与风险策略 | Project / Version   |
| Publish    | Event / Quota   | Durable Scheduler   |
+---------------------------+------------------------+
                            |
          +-----------------+------------------+
          |                 |                  |
          v                 v                  v
      状态数据库       产物与代码仓库        LLM Provider
          |                 |
          |                 v
          |             Agent Worker
          |                 |
          |                 v
          +----------> Tool Gateway
                            |
                            v
                    Sandbox Provider
                文件 / 构建 / 测试 / Vim
```

- **Control Plane：** 维护可信身份、Project 归属、状态、配额、版本和发布指针。
- **Agent Runtime：** 组装必要 Context、调用模型、校验结果并保存 Artifact；不能绕过平台权限。
- **Repository：** 保存 Project 源码、Git 历史和 commit/version 映射。
- **Tool Gateway：** 根据用户、Project、Agent 角色、路径、网络和预算检查工具请求。
- **Sandbox：** 执行不可信文件修改、构建和测试，无权改变身份、配额和发布状态。

### Agent 与 Runtime 执行链

```text
用户消息
    |
    v
入口判断（LeadDecision） -- 直接处理（direct） --> 回答 / 澄清
    |
团队执行（team）
    v
产品方案（Blueprint） -> 风险策略（Risk Policy）
                              |
                              v
                   动态任务图 / 固定流水线
                  （TaskGraph / Fixed Pipeline）
                              |
                              v
            Agent 最小上下文 + 结构化产物交接
             （Context + Artifact Handoff）
                              |
                              v
               工具请求（ToolRequest）-> 隔离环境（Sandbox）
                              |
                              v
              数据分析 + 校验 + 独立审查
       （DataProfile + Validation + ReviewReport）
                              |
                              v
                 Git 提交 + 项目版本（ProjectVersion）
                              |
                              v
                  用户明确发布 / 更新（Publish / Update）
                              |
                              v
                    公开访问路由（Public Route）
```

- **规划与执行分离：** Lead 可以提出 direct、team 或 TaskGraph 建议，但 Runtime 校验角色、依赖、预算、Approval 和 Tool 权限。
- **模型与证据分离：** Agent 产生结构化判断；Renderer、Test、Validator 和 ToolResult 提供不可由模型自行改写的执行证据。
- **工作与发布分离：** Agent Run 和 ProjectVersion 可以持续推进，Public Route 只响应用户最后一次明确确认的发布指针。

### 部署与分享架构

这里区分两件事：开发者部署 Another Atom 平台；用户在平台内发布和分享某个 ProjectVersion。前者创建可信服务边界，后者只改变产品内发布指针。

```text
平台部署

开发者 -- 推送代码（git push） --> GitHub
                                  |
                           部署（Deploy）
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
              平台主服务                   Agent 执行服务
           （Control Plane）              （Agent Workers）
                    |                           |
          +---------+---------+       +---------+---------+
          |                   |       |         |         |
          v                   v       v         v         v
       状态数据库          产物存储   模型服务   状态/产物   隔离执行服务
      （State DB）    （Artifact Storage）      读写    （Sandbox Provider）

用户访问与分享

浏览器 -- HTTPS / WSS --> 统一网关（Unified Gateway）
                               |
                +--------------+--------------+
                |                             |
                v                             v
          登录后的工作台                  已发布版本路由
      （Authenticated Studio）          （Published Route）
       Project / 编辑 / Vim              用户选定的版本
                |                             |
                `---- 用户明确发布 ------------'
                                              |
                                              v
                                        稳定公开地址
                                      （Stable Public URL）
```

- **统一公网入口：** 浏览器只访问 Control Plane 的 HTTPS/WSS 域名，内部 Worker、数据库、产物存储和 Sandbox 不直接暴露给终端用户。
- **部署边界：** Control Plane、Agent Worker 和 Sandbox 可以按版本合并或拆分，但可信控制面与不可信执行面不能合并权限。
- **分享边界：** Public Route 只读取已发布版本，不开放 Project Repository、Agent Context、内部 Event、配额或 Sandbox Session。

详细工程边界由各版本架构设计维护，README 不重复版本实现细节。

## 当前版本

| 版本 | 服务整体目标的方式 | 状态与详细设计 |
| --- | --- | --- |
| **V1** | 用固定专业团队、Project Git、版本和显式发布证明完整闭环；当前已实现 Web 源码与浏览器 Preview 适配器 | Railway 单副本已验收；非 Web Runtime 适配器和 Linux Sandbox 实机安全验收待完成。见 [V1 产品](./docs/design/V1/产品设计/01-核心产品需求与交互.md)、[V1 Agent](./docs/design/V1/技术设计/01-[Agent]-多Agent设计.md)、[V1 架构](./docs/design/V1/技术设计/03-[工程]-系统架构.md) |
| **V2** | 在同一 Project、Artifact 和权限基础上增加动态任务图、角色子集、Tool、局部并行和返工 | 设计完成，待 V1 验收后实施。见 [V2 产品](./docs/design/V2/产品设计/01-产品范围与交互.md)、[V2 Agent](./docs/design/V2/技术设计/01-[Agent]-任务编排与多Agent协作.md)、[V2 架构](./docs/design/V2/技术设计/02-[工程]-多Agent执行与沙箱架构.md) |

当前代码包含真实 LLM Provider、Mock Provider、用户级隔离、Project Git、Web 项目可交互 Preview、版本与发布、持久化任务和 Provider 兜底。当前后端单元/集成测试共 85 项；详细完成度见 [V1 交付状态摘要](./docs/review/归档/11-[综合]-2026-07-13-V1交付状态摘要.md) 和 [V1 Review](./docs/review/归档/08-[综合]-2026-07-12-关键设计与实现检查.md)。

## 快速开始

### 前置要求

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 22 和 npm

本地默认使用 SQLite 和确定性 Mock Provider，不需要 API Key。真实 Ollama Cloud / DeepSeek 配置见[运行与部署说明](./docs/design/V1/技术设计/04-[工程]-运行与部署.md)。

### 1. 安装后端依赖

```bash
uv sync --python 3.12
```

### 2. 构建 Studio

```bash
cd studio
npm install
npm run build
cd ..
```

### 3. 启动后端

```bash
uv run --python 3.12 uvicorn another_atom.main:app --host 127.0.0.1 --port 8000
```

启动后访问：

- Studio：[http://127.0.0.1:8000](http://127.0.0.1:8000)
- 健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

本地数据默认保存在 `data/another_atom.db`。xterm.js + restricted Vim 还需要独立 Linux Sandbox Host、Sandbox 镜像和共享密钥。

## 文档导航

- **完整知识库：** [项目完整设计知识库](./PROJECT_KNOWLEDGE_BASE.md)
- **整体产品：** [整体产品目标与定位](./docs/design/整体/01-[产品]-整体产品目标与定位.md)
- **设计：** [设计文档规范与索引](./docs/design/README.md)
- **Review：** [检查、反思与 Bug 索引](./docs/review/README.md)
- **部署：** [运行与部署说明](./docs/design/V1/技术设计/04-[工程]-运行与部署.md)
- **Atoms 参考：** [Atoms 参考产品分析](./docs/design/整体/02-[参考]-Atoms参考产品分析.md)

## 项目状态

- **源码仓库：** [github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- **在线版本：** Railway 已部署并完成公开访问验收；具体服务域名由 Railway 部署环境管理。
- **当前限制：** 真实 Linux Sandbox 安全验收、完整 Project 对话线程、失败后的 Retry/Resolve 和需要后端的产品能力仍待后续版本完善。
