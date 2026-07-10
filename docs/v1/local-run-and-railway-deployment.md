# Another Atom V1 本地运行与 Railway 部署

本文只描述当前仓库已经实现的 V1 纵切版本。仓库默认使用 Mock Provider；配置 `OLLAMA_API_KEY` 和 `LLM_PROVIDER=ollama` 后使用 Ollama Cloud，默认模型为 DeepSeek V4 Pro。项目、Session、角色产物、配额、事件、版本和发布流程真实运行并持久化。

> 当前运行说明与已确认目标设计必须区分：现有纵切版仍使用 Engineer/Team、Blueprint 确认和演示身份头；[V1 架构设计](./architecture-design.md)已将正式 V1 调整为用户名密码 Session Gateway、Lead `direct/team` 路由、Project 本地 Git、xterm.js + 受限 Vim 和 Linux Sandbox Host。这些新增能力尚未落地，本文不会把它们写成当前可用功能。

## 1. 当前可运行范围

已经实现：

- Home Prompt Composer、Engineer/Team 模式和附件元数据；
- Blueprint 生成、范围三态判断和用户确认门；
- Team Leader、Product Manager、Architect、Engineer、Data Analyst 固定顺序 Pipeline；
- AppSpec 驱动的受控 React Renderer；
- SSE 事件、Desktop/Mobile 预览、结构化编辑；
- Build/Edit/Restore 版本历史；
- Publish、Unpublish、稳定公开路由和 JSON Export；
- 基于演示身份头的用户数据过滤、账户配额、失败重试和启动时 Build Job 恢复。

尚未实现：

- Ollama Cloud 的真实 token 用量结算（当前仍使用演示单位账本）；
- Resolve 修复入口、项目重命名/删除和附件文件上传；
- Railway 公网实例和真实域名；
- V2 自主多 Agent。
- 用户名密码登录、真实 Lead 路由、Project 本地 Git、xterm.js/Vim 和 Linux Sandbox Host。

## 2. 本地启动

### 2.1 前置条件

- Python 3.12 及以上；
- [uv](https://docs.astral.sh/uv/)；
- Node.js 22 及以上；
- npm。

### 2.2 安装依赖

在仓库根目录执行：

```bash
uv sync --dev
cd studio
npm install
npm run build
cd ..
```

`npm run build` 会把 React Studio 产物写入 `studio/dist`，FastAPI 将其作为同域静态页面提供。

### 2.3 启动统一服务

```bash
uv run uvicorn another_atom.main:app --host 127.0.0.1 --port 8000
```

浏览器打开：

- Studio：<http://127.0.0.1:8000>
- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

本地默认数据库是 `data/another_atom.db`。停止服务后再次启动，已有项目和版本仍会保留。需要干净数据时，先停止服务，再删除该数据库文件。

### 2.4 本地试用路径

1. 在 Home 输入商品展示站需求，或选择页面下方示例 Prompt。
2. 选择 `Team` 和当前可用模型，点击右侧构建按钮。模型在 Run 创建后固定，不受后续切换影响。
3. 检查 Product Manager 生成的 Blueprint；必要时修改项目名或视觉方向。
4. 点击 `Approve & build`。未确认前不会创建 Build Job。
5. 在左侧查看 Team Leader、Product Manager、Architect、Engineer、Renderer、Data Analyst 的真实阶段事件。
6. 构建完成后切换 Desktop/Mobile，进入生成站点的 Home、Catalog 和 Product 页面。
7. 在 `Edit` 修改标题、正文或主色并保存；确认版本列表新增一项。
8. 在 `Versions` 恢复旧版本；Restore 会创建新版本，不覆盖历史。
9. 点击 `Publish`，从提示条打开无需登录的公开路由。

V1 只接受商品展示/商品目录结构。可用以下输入检查边界与错误状态：

```text
Build a CRM for a sales team
```

结果应为 `unsupported`，并在构建前停止。

```text
Build a catalog with login and payment
```

结果应为 `adapted`，Blueprint 会列出被舍弃的交易能力。

Mock 测试环境还保留显式失败标记：`[fail:llm]`、`[fail:build]`、`[fail:data]`。它们只用于验收错误状态，不是用户功能。

## 3. 运行测试

后端单元测试、集成测试和五轮 Golden Path：

```bash
uv run pytest --cov=another_atom --cov-report=term-missing
```

Python 静态检查：

```bash
uv run ruff check .
uv run ruff format --check .
```

前端生产构建：

```bash
cd studio
npm run build
```

当前验收结果以仓库最新测试输出为准，不在文档中写死永久有效的数字。

## 4. 环境变量

| 变量 | 本地默认值 | Railway 建议值 | 用途 |
| --- | --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/another_atom.db` | `${{Postgres.DATABASE_URL}}` | SQLAlchemy 数据库连接 |
| `LLM_PROVIDER` | `mock` | `ollama` | 选择 Mock 或 Ollama Cloud Provider |
| `OLLAMA_API_KEY` | 空 | Railway Secret | Ollama Cloud Bearer Key；禁止提交到 Git |
| `OLLAMA_HOST` | `https://ollama.com` | 相同 | Ollama Cloud API Host |
| `OLLAMA_MODEL` | `deepseek-v4-pro` | 相同 | 新 Run 的默认模型 |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | `120` | 单次模型请求超时 |
| `DEMO_QUOTA_UNITS` | `100` | `100` 或按演示需要调整 | 每个新账户的演示配额 |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Railway 分配的 `https://...up.railway.app` | 生成公开访问地址 |
| `ENVIRONMENT` | `development` | `production` | 运行环境标识 |

`.env` 已被 Git 忽略；仓库只提交 `.env.example`。Ollama Cloud 当前不提供服务端 Structured Outputs，因此响应会经过本地 Pydantic 校验；失败时先带校验错误修复一次，再进入阶段级有限重试。

## 5. 当前纵切版的 Railway 部署

仓库已提供：

- 根目录 `Dockerfile`：构建 React Studio，并运行 FastAPI；
- `railway.toml`：指定 Dockerfile Builder、`/api/health` 健康检查和失败重启策略；
- PostgreSQL 驱动和自动建表逻辑。

Railway 会自动检测根目录中大写命名的 `Dockerfile`。参考：[Railway Dockerfile 文档](https://docs.railway.com/builds/dockerfiles)。

### 5.1 从 GitHub 创建服务

1. 确认代码已经推送到公开或 Railway 有权访问的 GitHub 仓库。
2. 在 Railway Dashboard 选择 `New Project`。
3. 选择 `Deploy from GitHub repo`，授权 GitHub 后选择 `another-atom`。
4. 建议先选择添加变量或暂缓首次部署，先完成 PostgreSQL 配置。

官方入口说明：[Railway Quick Start](https://docs.railway.com/quick-start)。

### 5.2 添加 PostgreSQL

1. 在 Project Canvas 点击 `+ New`，选择 `Database -> PostgreSQL`。
2. 记住 PostgreSQL 服务名；默认通常是 `Postgres`。
3. 打开 Another Atom Web Service 的 `Variables`。
4. 添加：

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
LLM_PROVIDER=ollama
OLLAMA_API_KEY=<Railway Secret>
OLLAMA_HOST=https://ollama.com
OLLAMA_MODEL=deepseek-v4-pro
OLLAMA_TIMEOUT_SECONDS=120
DEMO_QUOTA_UNITS=100
ENVIRONMENT=production
```

如果数据库服务名不是 `Postgres`，变量引用中的服务名必须同步修改。Railway PostgreSQL 会提供 `DATABASE_URL` 等连接变量，参考：[Railway PostgreSQL 文档](https://docs.railway.com/databases/postgresql)。

### 5.3 生成公网域名

1. 打开 Web Service 的 `Settings -> Networking`。
2. 生成 Railway Public Domain。
3. 将完整 HTTPS 地址写回 Web Service 变量，例如：

```text
PUBLIC_BASE_URL=https://another-atom-production.up.railway.app
```

4. 变量变更会触发重新部署；部署完成后检查 `/api/health`。

### 5.4 Volume 是否需要

当前 Railway 部署使用 PostgreSQL 保存核心状态，V1 只保存附件元数据，因此 **Volume 不是当前启动的硬依赖**。

若希望保留 SQLite 兜底文件，或后续实现附件/构建文件存储，可给 Web Service 添加 Volume，挂载到：

```text
/app/data
```

Railway 容器中的项目目录是 `/app`，相对路径 `./data` 对应 `/app/data`。参考：[Railway Volumes 文档](https://docs.railway.com/volumes)。V1 仍是单实例设计；需要水平扩容前，应把文件迁移到 S3 兼容对象存储，而不是让多个实例依赖单个 Volume。

### 5.5 首次部署验收

按以下顺序检查：

1. Deployment Logs 出现 Uvicorn 启动成功，且没有数据库连接错误。
2. `https://<domain>/api/health` 返回 `status: ok` 和 `database: postgresql`。
3. 打开根地址，创建一个 Team Mode 项目并确认 Blueprint。
4. 刷新页面后重新打开项目，确认 Run、事件和版本仍存在。
5. Publish 后用无登录的隐身窗口打开 Public URL。
6. 执行 Unpublish，确认旧 Public URL 返回不可用状态。

如果健康检查通过但页面构建后卡住，先看 Web Service 日志中的 Build Job 状态。当前 V1 把 Web 与 Job 执行放在同一服务，构建并发受控；负载增加后再拆独立 Worker Service。

## 6. 当前部署边界

- Railway 账户、PostgreSQL 和实际资源会产生平台用量；本仓库不承诺免费额度。
- 当前代码尚未实际创建 Railway Project，因此仓库中没有可填写的在线 Demo URL。
- Dockerfile 已提供，但本机 Docker daemon 未响应，本轮未完成本地镜像构建验证；Railway 首次 Build Log 仍需人工确认。
- 当前 Provider 是 Mock；部署成功只能证明产品闭环、状态与 UI 可运行，不能证明真实模型质量。

## 7. 正式 V1 的 Sandbox 部署前置

当前 Railway 单服务步骤只用于部署现有纵切版，不能验收正式 V1 的源码 WebIDE。正式 V1 需要增加 Linux Sandbox Host：

```text
Browser -- HTTPS/SSE/WSS --> Control Plane (Railway or Linux VM)
                                  |
                                  +--> PostgreSQL
                                  |
                                  `--> Linux Sandbox Host
                                       local Git / Vim PTY / Build
```

Sandbox Host 必须支持 rootless container、Linux namespace 和 cgroup。Editor Sandbox 使用非 root 用户、只读根文件系统、禁网、无平台 Secret、drop capabilities、seccomp、`no-new-privileges` 和 CPU/内存/磁盘/PID/时限上限；只挂载当前 EditorSession 的临时 worktree，且不包含 `.git`。

仅使用 Vim restricted mode、目录前缀检查或 `chroot` 不能作为多用户隔离边界。部署环境无法提供上述机制时，xterm.js 入口必须关闭。正式落地可以选择：

1. Railway 承载 Control Plane，独立 Linux VM 承载 Sandbox Host；
2. 一台 Linux VM 通过 Docker Compose 同时承载两层，但 Control Plane 不挂载用户 worktree，Sandbox 不持有数据库和 Provider 密钥。
