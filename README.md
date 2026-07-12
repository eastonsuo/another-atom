# Another Atom

[简体中文](./README.md) | [English](./README.en.md)

> 把模糊想法转化为用户可查看和编辑代码、持续迭代、管理版本并自主发布的软件项目。

## 产品结论

Another Atom 是一个多智能体 Vibe Coding 工作台。用户通过自然语言表达目标，专业 Agent 负责规划、实现和校验；Project 工作区把可交互预览、代码文件、版本历史和发布状态放在同一条持续开发链路中。

它与 Atoms 面向同一个核心目标：让用户从意图出发，得到一个可以运行、可以修改、可以管理代码并可以发布的软件项目。Another Atom 使用自己的品牌、交互、Contract 和工程实现，不复用 Atoms 的源代码、私有 Prompt 或未公开基础设施。

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
  可运行应用 + 项目代码
          |
    +-----+-------------------+
    |                         |
    v                         v
预览 / 视觉修改          查看 / 编辑 / 管理文件
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

完整产品判断与取舍见[整体产品目标与定位](./docs/design/整体/产品设计/整体产品目标与定位.md)。

## 要解决的核心问题

- **[从想法到实现]** 用户可能只有一个目标，没有完整需求、架构和代码。系统需要帮助补全必要信息，并直接形成可以运行的结果。
- **[AI 过程不可检查]** 单次 Prompt 很难判断模型理解了什么、为什么这样实现、失败发生在哪一步。多智能体需要通过明确分工和可查看产物，让过程可以理解和纠偏。
- **[生成结果难以继续]** 一次性代码或截图无法自然承接后续修改。Project 需要保存代码文件、当前状态和历史版本，让用户回到同一项目继续开发。
- **[用户缺少代码和上线控制]** Vibe Coding 不能把代码藏起来，也不能让新生成结果自动覆盖线上版本。用户需要查看和编辑代码，并明确决定发布哪个版本。

## 产品界面

![Another Atom 中文登录页：用户名密码登录与账号级项目隔离说明](./docs/assets/readme/login-zh.png)

登录页通过用户名和密码建立会话；Project、源码仓库、版本和 Sandbox Session 都按账号隔离。

![Another Atom 中文 Studio 首页：Lead 对话、固定专业团队、项目列表和真实 LLM 状态](./docs/assets/readme/studio-home-v2-zh.png)

Studio 将 Lead 对话、专业 Agent、Project 历史、模型选择和账号配额放在同一工作区。

![Another Atom 构建工作区：阶段流水线、移动端预览、项目文件树和运行日志](./docs/assets/readme/studio-build-workspace-zh.png)

构建工作区同时展示可持久化进度、可交互 Preview、Project Repository、当前 Run Artifact 和运行日志。

![Another Atom 已完成的贪吃蛇游戏：可交互预览、阶段流水线、运行日志与 Project 文件](./docs/assets/readme/studio-game-preview-zh.png)

生成结果直接作为网页应用运行；用户可以检查真实交互、项目源码和结构化产物。

![Another Atom 版本历史：Build、Edit 和 Restore 都创建新版本](./docs/assets/readme/version-history-zh.png)

Build、Edit 和 Restore 分别形成新版本；历史不会被覆盖，线上版本仍由用户显式选择。

## 整体设计原则

### 【Project 中心】用户得到的是软件项目，不是一次回答

Project 是需求、Agent 产物、代码仓库、预览、版本和发布状态的统一归属。用户再次进入时，应基于已有代码和状态继续推进，而不是重新开始一段 Chat。

### 【多智能体协作】角色通过产物交接，不进行角色扮演

Lead 是用户入口；Product Manager、Architect、Engineer、Data Analyst 等专业角色处理不同问题。角色价值由 Blueprint、架构、源码、校验和数据解读等可查看结果证明，不由头像数量或对话长度证明。

### 【Vibe Coding】自然语言、视觉编辑和代码文件属于同一工作区

用户可以通过对话表达意图，通过 Preview 检查结果，通过视觉工具快速修改，也可以查看和编辑源码文件。不同入口最终都作用于同一个 Project 和版本历史。

### 【Human-in-the-loop】正常工作自动继续，真实风险由用户决定

用户明确要求构建后，已授权范围和基础预算内的工作可以继续；范围变化、额外预算、破坏性代码操作和线上发布变化必须交还用户确认。

### 【代码归属】源码、Git 历史和产品版本必须能够对应

每个 Project 默认拥有代码仓库。构建、编辑、修复和恢复形成新版本并映射 Git commit；用户能够查看、编辑、管理和带走代码，而不是只得到平台内的一份不可解释结果。

### 【版本与发布】生成完成不等于上线

工作版本可以持续变化，线上版本只响应用户最后一次明确 Publish/Update。Restore 创建新版本，不删除历史，也不自动改变发布指针。

### 【Runtime 控制】模型提出内容，平台控制权限与副作用

LLM 负责理解、规划、生成和解释；Runtime 负责身份、配额、状态、工具权限、仓库写入、Sandbox 和发布。生成代码与平台控制面保持不同权限边界。

### 【可恢复】进度、产物和版本对应持久化事实

用户看到的阶段、错误、额度和版本必须来自可恢复状态。刷新、重试或服务重启不应重复已完成工作、重复扣费或重复创建版本。

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

详细工程边界由各版本架构设计维护，README 不重复版本实现细节。

## 当前版本

| 版本 | 服务整体目标的方式 | 状态与详细设计 |
| --- | --- | --- |
| **V1** | 用固定专业团队、受控 Web Runtime、Project Git、版本和显式发布证明完整闭环 | Railway 单副本已验收；Linux Sandbox 实机安全验收待完成。见 [V1 产品](./docs/design/V1/产品设计/产品需求.md)、[V1 Agent](./docs/design/V1/Agent设计/Agent设计.md)、[V1 架构](./docs/design/V1/工程设计/架构设计.md) |
| **V2** | 在同一 Project、Artifact 和权限基础上增加动态任务图、角色子集、Tool、局部并行和返工 | 设计完成，待 V1 验收后实施。见 [V2 产品](./docs/design/V2/产品设计/产品需求.md)、[V2 Agent](./docs/design/V2/Agent设计/Agent设计.md)、[V2 架构](./docs/design/V2/工程设计/架构设计.md) |

当前代码包含真实 LLM Provider、Mock Provider、用户级隔离、Project Git、可交互 Preview、版本与发布、持久化任务和 Provider 兜底。当前后端单元/集成测试共 74 项；详细完成度见 [V1 简要交付说明](./docs/design/V1/产品设计/简要交付说明.md) 和 [V1 Review](./docs/review/V1/综合评审/2026-07-12-关键设计与实现检查.md)。

## 快速开始

### 前置要求

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 22 和 npm

本地默认使用 SQLite 和确定性 Mock Provider，不需要 API Key。真实 Ollama Cloud / DeepSeek 配置见[本地运行与 Railway 部署说明](./docs/design/V1/工程设计/本地运行与Railway部署.md)。

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

- **整体产品：** [整体产品目标与定位](./docs/design/整体/产品设计/整体产品目标与定位.md)
- **设计：** [设计文档规范与索引](./docs/design/README.md)
- **讨论：** [未决讨论规范与索引](./docs/discussion/README.md)
- **Review：** [检查、反思与 Bug 索引](./docs/review/README.md)
- **部署：** [本地运行与 Railway 部署说明](./docs/design/V1/工程设计/本地运行与Railway部署.md)
- **Atoms 参考：** [Atoms 参考产品分析](./docs/design/整体/参考资料/Atoms参考产品分析.md)

## 项目状态

- **源码仓库：** [github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- **在线版本：** Railway 已部署并完成公开访问验收；具体服务域名由 Railway 部署环境管理。
- **当前限制：** 真实 Linux Sandbox 安全验收、完整 Project 对话线程、失败后的 Retry/Resolve 和需要后端的产品能力仍待后续版本完善。
