# 【工程设计】Project ↔ 代码仓库绑定设计评审

> 类型：工程设计｜状态：部分已修复，详见下方 Update｜日期：2026-07-11｜范围：Project、Git 仓库、Version 与交付归属

> 评审对象：`another-atom` 当前代码（`another_atom/storage/models.py`、`api/routes.py`、`agent/orchestrator.py`、`contracts/schemas.py`）。
> 本文可独立阅读。一句话背景：用户天然期望“一个项目对应一个（自己可掌控的）代码仓库”，这关系到**代码归属、交付与掌控**；本文查证当前设计里“项目”与“仓库”到底是什么关系。

## Update（2026-07-12，基于当前 `main`）

本评审正文记录的是 2026-07-11 的旧状态。之后已落地“Project ↔ 平台服务端本地 Git 仓库”的 V1 绑定；因此第 2、3 节中“平台内没有 repo 概念”的结论已不再成立。需要区分：**平台内仓库绑定已完成**，**用户自有 GitHub/GitLab remote 绑定尚未实现**。

| 原评审要点 | 当前状态 | 当前代码与验证依据 |
| --- | --- | --- |
| Project 没有仓库绑定 | 已修复（V1 平台内绑定） | `Project` 已有 `repository_path`、`repository_branch`；创建 Run 时同步初始化仓库，启动时会为存量 Project 回填。|
| 一个 Project 默认对应一个仓库 | 已修复（V1 一对一） | 仓库路径由 `project_id` 决定；`initialize_repository(project.id)` 创建独立本地 Git 仓库。|
| 平台 Version 与 Git 历史断开 | 已修复 | `ProjectVersion.git_commit` 保存 commit SHA；Build、Edit、Restore 都创建新 commit 并映射新版本。|
| 用户无法查看项目代码 | 已修复（只读查看） | 已提供按当前用户校验的 Project 文件列表与文件内容接口；Studio 可刷新并查看 Repository 文件和本次 Artifact，`.git` 元数据不可读取。|
| 存量 Project 无法迁移 | 已修复（最小回填） | 数据库启动时会为缺失仓库的 Project 初始化本地仓库，并为已有 Version 回填 commit。|
| 项目可推送到用户自己的仓库 | 未实现 | V1 不配置 Git remote，也没有 GitHub/GitLab OAuth、`repo_url`、push 状态或用户仓库凭证管理。当前仓库是平台托管的服务端本地 Git。|
| 仓库连接状态、分支与最近 push 可追溯 | 部分实现 | 有内部默认分支与 Version→commit 映射；没有 remote provider、连接状态、最近 push commit/时间等外部交付状态。|

本轮验证：`tests/integration/test_repository_and_sandbox.py` 已通过 7 项测试，覆盖 Version→commit、存量回填、文件浏览、跨用户隔离和 `.git` 隐藏。

### 更新后的结论

V1 已经满足“打开一个 Project = 打开一个平台托管、与该 Project 一对一绑定的代码仓库”，并能让 Build、Edit、Restore 对应可追溯的 Git commit。原评审中关于“平台内完全没有 repo 概念”的问题已关闭。

但“打开一个 Project = 打开我自己 GitHub/GitLab 下可 clone、可 push 的仓库”仍未满足。这不是遗漏修复，而是当前 V1 的明确边界；若下一阶段要解决，应新增 RemoteRepository/Connection 模型、OAuth/凭证管理、push Job 与 ProjectVersion→remote commit 状态，而不是把 remote URL 临时挂在 Project 字段上。

## 1. 背景：为什么「项目 ↔ 仓库」值得单独审视

对用户而言，“项目”和“我的代码仓库”几乎是同一件事的两面：**打开一个项目 = 打开我的一个代码库**。他期望的心智模型是：

> 我在这里建了一个项目 → 它就对应我账号下一个能拿走、能自己 push、能持续迭代的仓库。

这条对应关系一旦缺失或含糊，用户就会陷入“代码到底在哪、是不是我的、能不能带走”的不确定。之前评审里反复出现的“代码仓库归属缺位 / push 失败不透明”，其数据模型侧的根因很可能就在这里：如果 `Project` 里根本没有“绑定了哪个仓库”这个字段，那么“推送到用户仓库”就没有一个稳定的锚点可依附。所以有必要把“项目 ↔ 仓库”单拎出来作为一个设计议题查证清楚。

## 2. 现状（基于代码事实）

### 2.1 「项目」概念存在，且是一等公民

- 数据模型中有独立的 `Project` 表（`storage/models.py`），关键字段：`id`、`user_id`（外键，**归属到 user**）、`name`、`prompt`、`mode`、`status`、`latest_version_id`。
- API 层围绕 project 有完整能力：`GET /projects`、`GET /projects/{id}`、发布 / 取消发布、改版（revision）、恢复版本（restore）、导出（export），且均通过 `_owned_project(project_id, user_id)` 校验归属。
- 归属维度是 **user**（`Project.user_id`），目前**没有 org / tenant 层**（与多租户评审结论一致）。

### 2.2 构建 / 版本挂在 Project 维度，产物是 JSON 版本而非仓库

- `Run`（一次生成流程）挂 `project_id`（并带 `user_id`、`session_id`）。
- 构建产物是 `ProjectVersion`：挂 `project_id` + `run_id`，内容为 `app_spec`（结构化 JSON），一个 project 可有**多个递增版本**。
- `Deployment`（发布）与 project **一对一**（`Deployment.project_id` 有 unique 约束）。
- 即：**一个 Project 下有多个 Run、多个 Version、最多一个 Deployment**，交付形态是“平台内的 JSON 版本 + 导出接口”，**不是一个 git 仓库**。

### 2.3 完全没有「Project ↔ Repo」绑定

- 全后端代码（`another_atom/`）中搜不到任何 `repo / repository / git_url / clone_url / github / remote` 相关的模型、字段或逻辑；`Project` 表里也没有任何仓库字段。
- 产物的“带走”能力仅有 `GET /projects/{id}/export`（导出一份 JSON 快照），没有“这个项目绑定了哪个仓库、连没连上、上次推到哪个分支/commit”之类的信息。
- **结论：当前根本没有 repo 概念**，“一个项目对应一个仓库”这一预期在现状里**不成立**。

> **待确认**：是否有 `another_atom/` 之外（如部署脚本、外部服务）承担了 project→repo 的映射？当前仓库内未见任何此类代码或字段，本文按“平台内无 repo 绑定”来判断。

## 3. 问题（设计层面）

1. **项目有了、版本有了，但“项目 = 我的仓库”这条线缺失。** 平台把项目建模得相当完整（实体、多版本、发布、导出都有），却唯独没有把它锚定到用户可掌控的仓库。用户心智里最自然的那条对应关系，在数据模型里没有对应物。

2. **代码归属无处落地。** 产物只以 `ProjectVersion.app_spec`（JSON）+ 一个导出接口存在，不是一个用户能 clone、能持续 push、能在自己 GitHub 上看到的仓库。归属感因此是“平台托管的一份数据”，而非“我账号下的一个库”。

3. **交付链路缺少稳定的绑定锚点。** “生成 → 提交 → 推送到用户仓库”这条链，最后一步没有一个持久化的 `project.repo` 可推送；每次推送都得临时凑仓库信息。这正是之前“push 失败且不透明”在数据模型侧的根因：链路末端没有一等公民的仓库对象可依附。

4. **一致性与可追溯性无从谈起。** 没有 project↔repo 绑定，就无法回答“这个项目的代码现在在哪个仓库的哪个分支、和平台内的哪个 version 对应、上次推送成功没有”；版本历史（Version）与仓库历史（git commit）之间是断开的两套东西。

> 这与此前“代码仓库归属缺位”评审是同一问题的一体两面：那篇讲的是交互/交付体验层面的缺位，本篇指出它在数据模型层面就没有绑定字段作为支撑。体验层的缺失，源自模型层的缺失。

## 4. 更好的设计方向（可落地）

### 4.1 在 `Project` 上把“仓库”变成一等公民

给 `Project`（或新建一张 `ProjectRepo` 关联表）增加仓库绑定相关字段，例如：

- `repo_provider`（github / gitlab / 内建托管等）、`repo_url` / `repo_full_name`、`default_branch`；
- `repo_connection_status`（未绑定 / 已连接 / 权限不足 / 连接失败）；
- `last_pushed_branch`、`last_pushed_commit`、`last_pushed_at`；
- `binding_mode`（平台代建 / 用户绑定已有仓库）。

让“这个项目绑定了哪个仓库、什么状态、推到哪了”成为**可查询、可展示的持久事实**，而不是每次临时拼凑。

### 4.2 确立“一个 Project 对应一个用户可掌控仓库”的默认关系

- **默认一对一**：项目初始化时即代建或引导绑定一个仓库，使 project↔repo 从一开始就成立。
- 一对一是最贴合用户心智、也最易实现交付链路稳定的选择；**一对多 / 多对一**属于进阶场景，建议 V1 不做，但字段与约束上不要写死到无法演进，例如使用关联表而非直接把 repo 字段硬塞进 project。

### 4.3 让交付链路稳定依附于 project→repo

- 每次交付按 `project → 绑定的 repo` 稳定推送：生成/改版产生新 `ProjectVersion` 时，把对应产物推送到该项目绑定仓库的既定分支，并回写 `last_pushed_commit` 等状态。
- 把**平台版本（ProjectVersion）与 git commit 建立映射**，例如在 version 上记录对应 commit hash，让“平台里的第 N 版”和“仓库里的某次提交”能对应，恢复可追溯性。

### 4.4 迁移与兼容考虑

- 现有 project 无 repo 绑定，需要一条回填/绑定引导路径：对存量项目提供“现在绑定/创建仓库”的入口，把已有的最新 version 作为首次提交推入。
- 绑定信息涉及凭证与权限，需与“可信身份 / 授权”协同，避免把仓库写权限凭证与不可信的 `X-User-ID` 身份混在一起。

## 5. 小结

**「项目」这一层做得很完整，缺的是把它锚定到“用户可掌控的仓库”这条线。** 现状里 Project、Run、Version、Deployment、Export 一应俱全，唯独没有 repo 绑定；用户心智中最自然的“一个项目 = 我的一个仓库”在数据模型里没有对应物，这也是“代码归属缺位、push 不透明”的模型侧根因。

核心取向：**把“仓库”从“事后临时接的一环”提升为 `Project` 上的一等公民字段**，并默认建立“一个 Project 对应一个用户可掌控仓库”的一对一关系。

**优先级建议（从高到低）：**

1. 在 `Project` / 关联表上新增仓库绑定字段（provider / url / branch / 连接状态 / 最近推送）；
2. 项目初始化即代建或绑定仓库，让 project↔repo 默认成立；
3. 交付链路稳定依附 project→repo 推送，并回写推送状态；
4. 建立 ProjectVersion ↔ git commit 映射，恢复版本可追溯；
5. 提供存量项目回填绑定路径，并与可信身份/授权协同管理仓库凭证。

> 本文件为新增的独立设计评审稿，仅基于当时代码事实撰写，未改动仓库任何代码或其他评审文档。对现状不确定处已标注“待确认”；后续修复状态以上方 Update 为准。
