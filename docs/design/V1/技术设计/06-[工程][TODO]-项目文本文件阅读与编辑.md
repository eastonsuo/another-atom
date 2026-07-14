# Another Atom V1 项目文本文件阅读与编辑

[toc]

- **文档状态：** V1 产品与工程设计基线；文档纵切已实现，源码纵切与界面验收待完成
- **功能定位：** 在 Project 右侧文件面板中阅读和编辑受控的 UTF-8 文本文件，Markdown 额外提供渲染预览
- **当前基线：** Repository 普通文档已支持查看、Markdown 预览、编辑、CAS 保存和 Git 追溯；应用源码与 Run Artifact 暂时只读
- **关联设计：** [通过对话修改现有项目](../产品设计/03-通过对话修改现有项目.md)、[系统架构](./03-[工程]-系统架构.md)

## 背景

此前右侧“项目文件”只能通过 HTTP 列出 Project Repository 和当前 Run 产物，并以纯文本读取 `README.md`、JSON 和应用源码，无法保存。当前已补齐普通项目文档的查看与编辑纵切；可发布应用源码仍需经过 AppSpec、Validator 和 ProjectVersion，因此继续作为后续独立纵切。

本功能的底层能力是“通用文本文件阅读与编辑”，而不是一个只能修改 `README.md` 的 Markdown 工具。Markdown 只比其他文本类型多一层安全渲染预览；JSON 和代码文件可以在同一编辑基础上增加格式化、语法高亮或校验。

## 摘要

- **能力抽象**
  - Repository 中符合路径、大小和 UTF-8 规则的普通文本文件使用同一套阅读、编辑和保存能力；Markdown 另外支持渲染预览。
- **产物边界**
  - Run Artifact 是 Agent 阶段的可追溯证据，继续只读；如需改变需求或应用 Contract，必须走对话、结构化 Edit 或受控源码保存链路。
- **并发边界**
  - 打开文件不占用写锁；保存时同时校验内容哈希和 Project 统一写租约，避免覆盖 Agent、Vim 或其他页面已经产生的变更。
- **Git 与版本**
  - 普通文档保存产生可追溯 Git commit，但不伪造可发布应用版本；可发布源码的修改必须经过 AppSpec 同步和 Validator，成功后才创建 ProjectVersion。
- **失败保护**
  - 冲突或保存失败不清空用户输入，不移动当前版本和发布指针，并返回可操作的错误原因。

## 第一部分：产品设计

### 1. 产品目标

用户应当能在当前 Project 工作区中直接阅读和修改文本文件，而不必为了修改一段说明、JSON 配置或 CSS 就离开项目、下载文件或启动 Vim。

这项能力需要保持 Another Atom 现有的 Project 边界：

1. **[修改归属当前 Project]** 文件读写、Git commit、审计事件和可能产生的 ProjectVersion 都绑定当前用户和 Project。
2. **[文件面板是通用入口]** `.md`、`.txt`、`.json`、`.html`、`.css`、`.js` 等文本文件共用阅读和编辑框架，不按扩展名重复实现保存逻辑。
3. **[不绕过产物与版本规则]** 文件面板不能直接篡改 Run Artifact，也不能在未校验时将源码变更标记为新应用版本。
4. **[保存结果可理解]** 用户能明确知道当前是未保存、保存中、已保存、发生冲突还是校验失败。

### 2. 功能范围

#### 2.1 V1 实现

- **[通用文本阅读]** Repository 中未被保护、不超过大小上限且能以 UTF-8 解码的文件可在右侧面板查看。
- **[通用文本编辑]** 符合可编辑规则的 Repository 文本文件使用同一编辑器，支持保存、取消和未保存状态。
- **[Markdown 增强]** `.md` 文件默认可在“预览”和“源码”之间切换，编辑仍使用通用文本编辑器。
- **[类型提示]** JSON 保存前显示语法错误；常见代码文件按类型高亮。类型提示不取代服务端校验。
- **[安全保存]** 保存时执行用户归属、路径、大小、编码、内容哈希和 Project 写租约校验。
- **[可追溯结果]** 每次有实际变化的成功保存都能定位到 Git commit；可发布源码变更还要定位到 ProjectVersion。

#### 2.2 V1 不实现

- **[文件管理]** 不在本轮实现创建、删除、重命名、移动和批量上传；这些操作需要单独定义路径冲突和破坏性确认。
- **[多人协作]** 不实现多人光标、即时合并、评论和 OT/CRDT。
- **[所见即所得]** Markdown 不提供类 Word 富文本编辑，用户修改的仍是 Markdown 源文本。
- **[二进制编辑]** 图片、字体、压缩包和其他二进制文件只显示基本信息，不当作文本打开。
- **[自由运行]** 文件编辑不引入 Shell、依赖安装、外网访问或任意后端代码执行。

### 3. 文件分类与产品行为

| 文件类别 | 示例 | 查看 | 编辑 | 保存结果 |
| --- | --- | --- | --- | --- |
| 普通项目文档 | `README.md`、`notes.txt` | 文本；Markdown 可渲染 | 是 | Git commit，不创建 ProjectVersion |
| 非发布配置与代码 | 普通 `.json`、`.js` 等 | 格式化或高亮 | 是 | Git commit，不改变 Preview |
| 可发布应用源码 | `index.html`、`styles.css`、`app.js` | 高亮 | 是 | 同步 AppSpec、校验、Git commit 和 ProjectVersion |
| 应用 Contract | `app-spec.json` | 格式化 | 是，但必须通过 Schema 和完整校验 | Git commit 和 ProjectVersion |
| Run Artifact | `.another-atom/generated/*` | 是 | 否 | 无；保持原始证据 |
| Runtime 保护文件 | `.git/*`、`.another-atom/version.json` 等 | 隐藏或只读 | 否 | 无 |
| 二进制或超大文件 | 图片、字体、超限文件 | 基本信息 | 否 | 无 |

“文本文件”不只通过扩展名判断。服务端还必须确认内容能以 UTF-8 解码、未超过上限且不在保护路径。前端显示的 `editable` 只是交互提示，不能代替服务端重新校验。

### 4. 用户流程

```text
打开右侧“项目文件”
             |
             v
       选择 Repository 文件
             |
      +------+----------------+
      |                       |
      v                       v
Markdown 预览 / 源码       其他文本查看
      |                       |
      +-----------+-----------+
                  v
                编辑
                  |
          +-------+-------+
          |               |
          v               v
        保存            放弃修改
          |
          v
  归属 + 路径 + 写租约 + 内容 CAS
          |
     +----+--------------------+
     |                         |
     v                         v
  普通文本               可发布应用源码
     |                         |
     v                         v
 Git commit              AppSpec 同步与 Validator
     |                         |
     v                         v
  保存完成             Git commit + ProjectVersion
                                   |
                                   v
                             切换到新 Preview
```

### 5. 右侧面板交互

#### 5.1 阅读状态

- 选中 Markdown 时默认显示安全渲染的预览，可切换到源文本。
- 选中 JSON 时可格式化展示，但不应修改原文件的空格与换行，除非用户明确保存。
- 选中其他文本时显示原始内容和适用的语法高亮。
- Run Artifact 明确标记“只读产物”，不显示编辑按钮。

#### 5.2 编辑状态

- 点击“编辑”后进入源文本编辑器，显示“保存”和“取消”。
- 内容改变后显示“未保存”；内容与读取基线一致时不创建空提交。
- 切换文件、收起面板或离开页面前，如有未保存内容，提示“继续编辑 / 放弃修改”。
- `Cmd/Ctrl + S` 触发保存，但不绕过校验与确认。

#### 5.3 保存结果

- **[已保存]** 显示文件名、保存时间和 Git commit 短标识。
- **[已创建版本]** 如修改可发布源码，额外显示新的 ProjectVersion 并切换 Preview。
- **[内容冲突]** 文件在用户打开后已被修改时，不允许静默覆盖；保留当前编辑内容，让用户刷新后再决定。V1 不自动合并。
- **[项目忙碌]** Agent、Vim Save 或其他写操作已占用 Project 时，显示占用来源和“稍后重试”，不丢失本地编辑内容。
- **[校验失败]** JSON、AppSpec 或可发布源码未通过校验时，显示可定位到文件和原因的错误，不创建 ProjectVersion。

### 6. 版本与发布语义

#### 6.1 普通文本文件

修改 `README.md`、说明文档或不影响当前可发布应用的文本文件时：

- 成功保存生成 Git commit 和审计事件；
- 不创建 ProjectVersion，因为用户可预览和发布的应用并未改变；
- 不改变 `latest_version_id`、Preview 或 Public Route；
- 下一次应用版本提交建立在该文档 commit 之后，因此文档修改继续存在于项目 Git 历史。

#### 6.2 可发布应用源码

修改 `index.html`、`styles.css`、`app.js` 或 `app-spec.json` 时，文件内容和数据库中的 AppSpec 必须保持同一个可发布事实。因此不能只执行一次普通 Git commit。

保存链路必须：

1. 从当前 ProjectVersion 读取 AppSpec 和可发布源码基线；
2. 将用户修改合并为候选源码包；
3. 确定性同步 AppSpec 与 `index.html/styles.css/app.js`；
4. 执行 Schema、源码、能力边界、视觉 Token 和 Blueprint 交接校验；
5. 通过后以 `edit` 来源创建新 ProjectVersion 和 Git commit；
6. 将 Project `latest_version_id` 移动到新版本，但不改变发布指针。

如 AppSpec 和展开源码无法无损同步，V1 必须拒绝保存并说明冲突，不得选择其中一份静默覆盖另一份。

#### 6.3 发布边界

无论是文档 commit 还是新 ProjectVersion，文件保存都不自动 Publish 或 Update。已发布项目的 Public Route 继续指向用户上一次明确选择的版本。

## 第二部分：工程设计

### 7. 前端组件与状态

#### 7.1 组件边界

- **[RepositoryPanel]** 继续负责文件列表、选中文件和面板展开状态，不自己实现文件编辑逻辑。
- **[TextFileViewer]** 根据文件能力显示纯文本、格式化 JSON 或语法高亮。
- **[MarkdownPreview]** 安全渲染 Markdown，不启用 raw HTML，并过滤危险 URL 协议。
- **[TextFileEditor]** 管理编辑内容、dirty 状态、保存与取消；V1 可先使用受控文本编辑器，不必为了语法高亮引入完整 IDE。
- **[UnsavedChangesGuard]** 统一处理切换文件、关闭面板和页面离开。

#### 7.2 客户端状态

```text
idle -> loading -> viewing -> editing -> saving -> saved
                   |           |          |
                   |           |          +-> conflict / validation_error / failed
                   |           +-> viewing（放弃修改）
                   +-> load_error
```

一个编辑会话至少保留：

- `path` 和 `source`；
- 读取时的 `content_hash`；
- 原始内容和当前编辑内容；
- `editable`、`language` 和 `render_mode`；
- 保存状态与最近错误。

刷新文件列表不能静默清空正在编辑的本地内容。

### 8. API Contract

#### 8.1 文件列表

现有接口继续使用：

```http
GET /api/projects/{project_id}/files?run_id={run_id}
```

`ProjectFileEntry` 增加服务端计算的能力字段：

```json
{
  "path": "README.md",
  "source": "repository",
  "size": 1024,
  "kind": "markdown",
  "text": true,
  "editable": true,
  "render_mode": "markdown"
}
```

#### 8.2 读取文件

```http
GET /api/projects/{project_id}/files/content?path=README.md&source=repository&run_id={run_id}
```

`ProjectFileContent` 增加内容版本和能力信息：

```json
{
  "path": "README.md",
  "source": "repository",
  "content": "# Project\n",
  "content_hash": "sha256:...",
  "editable": true,
  "kind": "markdown",
  "render_mode": "markdown"
}
```

Artifact 读取结果必须返回 `editable: false`。

#### 8.3 保存文件

```http
PUT /api/projects/{project_id}/files/content
Content-Type: application/json
```

请求：

```json
{
  "path": "README.md",
  "content": "# Updated Project\n",
  "expected_content_hash": "sha256:...",
  "operation_id": "client-generated-uuid"
}
```

响应：

```json
{
  "path": "README.md",
  "content_hash": "sha256:...",
  "size": 18,
  "git_commit": "40-character-commit",
  "version": null,
  "saved_at": "2026-07-14T12:00:00Z"
}
```

如修改可发布源码，`version` 返回新创建的 `VersionView`。

#### 8.4 错误码

- `REPOSITORY_FILE_NOT_READABLE`：文件不存在、非 UTF-8 或超过读取上限。
- `REPOSITORY_FILE_NOT_EDITABLE`：Artifact、保护路径、二进制文件或当前不允许编辑的文件。
- `REPOSITORY_FILE_CONFLICT`：`expected_content_hash` 与服务端当前内容不一致。
- `PROJECT_WRITE_BUSY`：另一个 Agent、Vim 或文件保存正在修改 Project。
- `REPOSITORY_FILE_VALIDATION_FAILED`：JSON、AppSpec 或可发布源码校验失败。
- `REPOSITORY_FILE_SAVE_FAILED`：原子写入、Git 或持久化提交失败。

### 9. Repository 写入边界

#### 9.1 路径与文件限制

服务端必须重新执行以下检查，不信任前端传入的 `editable`：

- 路径必须是 Project Repository 根目录下的相对路径；
- resolve 后仍必须位于当前 Repository，拒绝 `..`、绝对路径和 symlink 越界；
- 拒绝 `.git/`、`.another-atom/` 等 Runtime 保护路径；
- V1 保持当前 256 KB 单文件上限，读取与保存使用同一字节口径；
- 内容必须是有效 UTF-8，不在服务端猜测或转换编码；
- 拒绝空文件名和超过路径长度限制的请求。

#### 9.2 原子写入

普通文本保存使用同目录临时文件，完成 `flush/fsync` 后通过 `os.replace` 替换目标，避免进程中断留下半个文件。Git 提交只 stage 当前保存链路确认的文件，不使用 `git add .` 带入其他未确认变更。

当候选内容与当前内容完全一致时，返回当前哈希和 commit，不生成空提交。

#### 9.3 可恢复保存操作

文件系统、Git 和数据库不在同一事务中，因此不能将“写文件 -> commit -> 记录事件”当作天然原子操作。V1 使用持久化保存操作记录跨越这个边界：

```text
FileSaveOperation
  id / project_id / user_id / path
  expected_hash / target_hash
  status: pending -> writing -> committed -> completed | failed
  git_commit / version_id / error_code
```

- API 先以 `operation_id` 建立或读取操作记录；
- Git commit message 或 trailer 包含 `operation_id`；
- 请求重试时，已完成操作直接返回原结果，不再创建 commit 或 ProjectVersion；
- 如 Git 已 commit 而数据库事务未完成，恢复逻辑通过 `operation_id` 对齐 commit 后继续物化事件或 ProjectVersion；
- 无法恢复的操作进入 `failed`，保留错误，不静默标记已保存。

### 10. 并发与一致性

#### 10.1 内容 CAS

读取文件时返回 `sha256` 内容哈希；保存时客户端必须回传 `expected_content_hash`。服务端在获得写权后再读取当前文件并比较：

```text
expected hash == current hash -> 可继续保存
expected hash != current hash -> 409 REPOSITORY_FILE_CONFLICT
```

哈希只防止覆盖同一文件已发生的变化，不能取代 Project 写互斥。

#### 10.2 Project 统一写租约

浏览器文件保存不得新建一套与 Agent、结构化 Edit 和 Vim 无关的锁。需要将现有 `active_write_run_id` 扩展为统一 Project 写租约，至少标记：

- `project_id`（唯一）；
- `owner_type`: `run | revision | sandbox | file_save`；
- `owner_id`；
- `acquired_at` 和 `expires_at`；
- 用于 CAS 释放的 lease token。

文件打开和本地编辑不占用租约；只有保存从服务端校验到 Git/版本完成期间占用。内容哈希在获得租约后重新校验，避免先检查后写入的竞态。

这项统一租约同时解决现有 Review 中“Vim Save 与结构化 Edit 未完全进入同一写互斥”的问题，不应只为新文件面板做局部修补。

### 11. 安全设计

#### 11.1 身份与归属

- 文件列表、读取和保存都从 Session 解析当前用户；
- 每次请求通过 `Project.user_id` 校验归属，不接受客户端自报 user ID；
- `run_id` 只用于选择当前 Project 的 Artifact，不能读取其他 Project 的 Run；
- Artifact 始终只读，服务端不因伪造 `source=repository` 而把 Artifact 路径视为普通文件。

#### 11.2 Markdown 渲染

- Markdown 预览默认不解析 raw HTML；
- 拒绝 `javascript:` 等危险协议；
- 外部链接使用明确的新窗口和 `noopener noreferrer`；
- 预览不执行脚本、iframe、内嵌事件和远程资源代码；
- 渲染层的过滤不能被“切换到源码”绕过，因为源码视图只显示纯文本。

#### 11.3 审计与敏感内容

成功保存记录 `project.file.updated` 事件，至少包含用户、Project、文件路径、旧哈希、新哈希、Git commit 和可选 version ID。事件不复制整份文件内容，避免在日志中第二次持久化用户数据或潜在密钥。

V1 生成仓库不应包含 `.env` 或密钥文件。如后续支持外部仓库导入，需要另行定义敏感文件隐藏和编辑规则，不能沿用“所有 UTF-8 文件默认显示”。

### 12. 实现顺序

1. **[Contract]** 扩展文件能力字段，确定保护路径、可发布源码清单和错误码。
2. **[Repository]** 实现通用 UTF-8 文本写入、内容哈希、原子替换、精确 Git stage 和幂等保存操作。
3. **[一致性]** 将 Agent、结构化 Edit、Vim Save 和文件保存接入同一 Project 写租约。
4. **[文档纵切]** 先完成 `README.md` 的阅读、Markdown 预览、编辑、冲突和 Git commit，验证通用文本基础。
5. **[源码纵切]** 实现 AppSpec 与展开源码同步、Validator、ProjectVersion 和 Preview 切换。
6. **[前端完整性]** 补齐未保存保护、快捷键、错误反馈、JSON 提示和语法高亮。
7. **[验证]** 完成权限、路径穿越、冲突、中断恢复、版本与发布隔离测试。

### 13. 验收标准

#### 13.1 产品验收

- `README.md` 可在 Markdown 预览、源码查看和编辑之间切换；
- JSON、HTML、CSS、JavaScript 和普通文本使用同一编辑入口；
- 保存后刷新页面仍能读取新内容，并可定位 Git commit；
- 文档保存不创建虚假应用版本，源码保存成功后 Preview 与新 ProjectVersion 一致；
- 冲突、Project 忙碌或校验失败时，界面保留用户输入并说明下一步；
- 文件保存不自动改变已发布版本。

#### 13.2 自动化验收

- **[单元测试]** UTF-8 判定、文件大小、保护路径、symlink 越界、哈希、精确 stage、空提交和 Markdown 危险内容。
- **[集成测试]** 双用户隔离、Artifact 只读、CAS 冲突、Project 写互斥、幂等重试、Git 已提交后的恢复、源码校验失败不创建版本。
- **[前端测试]** 阅读/编辑切换、dirty 状态、关闭保护、保存中禁用、冲突提示、Markdown 安全渲染和保存失败后内容保留。
- **[回归测试]** 现有文件列表、Artifact 查看、Vim、AI Edit、Restore、Preview 和 Publish 链路继续通过。

### 14. 当前实现状态

截至 2026-07-14，文档纵切已经实现：

- 文件列表和读取接口返回 `kind`、`editable`、`render_mode` 与 `content_hash`，Run Artifact 明确只读；
- Repository 路径、`.git` / `.another-atom`、symlink、UTF-8 与 256 KB 上限均由服务端重新校验；
- 普通项目文档支持 Markdown 安全预览、源码查看、编辑、取消、未保存保护和 `Cmd/Ctrl + S`；
- 保存使用内容哈希 CAS、Project 单写占用、同目录原子替换、精确 Git stage 和 `FileSaveOperation` 幂等记录；
- Git commit 与数据库提交之间发生中断时，启动恢复会按 operation trailer 对账并释放写占用；
- JSON 在前端和服务端进行语法校验；冲突、项目忙碌和保存失败不会清空本地编辑内容；
- 普通文档提交不创建 ProjectVersion，也不移动 Preview 或发布指针。

仍未完成：

- `app-spec.json`、`index.html`、`styles.css`、`app.js` 的 AppSpec 同步、Validator 与 ProjectVersion 源码保存纵切；当前这些文件只读，避免绕过质量门禁；
- 通用 Project 写租约尚未从兼容字段升级为带 `owner_type / owner_id / expires_at / token` 的独立 Contract；
- 代码语法高亮尚未实现；
- 应用内浏览器实例不可用，本次不能判断桌面和移动尺寸下的实际界面是否通过验收。

### 15. 完成条件

只有以下条件同时满足后，本文档才能从 `[TODO]` 改为 `[DONE]`：

1. Repository 通用文本阅读与编辑、Markdown 预览和 Artifact 只读边界已实现；
2. 文档 commit 和可发布源码 ProjectVersion 的语义已分开；
3. 文件保存与 Agent、结构化 Edit、Vim 使用同一 Project 写互斥；
4. 失败、冲突、中断恢复和用户归属自动化测试通过；
5. 桌面和移动尺寸下完成实际界面验收，且 README 与实际能力声明一致。
