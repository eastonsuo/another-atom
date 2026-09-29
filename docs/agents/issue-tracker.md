# 议题跟踪器：GitHub

本仓库使用 GitHub Issues 跟踪执行事项。产品需求、设计和当前 Code Spec 的权威正文保存在对应 [Feature 目录](../features/README.md)，不在 Issue 中维护第二份 PRD 或设计合同。下文列出 `gh` 命令行操作示例；使用其他已授权 GitHub 工具时遵守相同的归属和操作边界。

## 与 Feature 和实施计划的关系

- Issue 记录排期、负责人、协作讨论、阻塞和关闭，引用当前 Feature 及相关设计、Spec 和验证证据；讨论中的产品或技术结论经确认后回写对应权威文档，不能只留在 Issue 中作为新的实施合同。
- 已有唯一 Implementation Plan 时，细分任务、依赖和完成证据在 Plan 维护，Issue 只保留协作状态、关注点和入口，不复制同一批任务的完成清单。没有 Plan 时，Issue 可以跟踪执行事项，不因存在 Issue 而自动生成 Plan。
- 不另建与 Issue 或现有 Plan 重复维护完成状态的 `TODO.md` 或第二套任务账本。关闭 Issue 不自动确认设计、证明部署成功或证明环境验收通过。

## 与 Bug 文档的关系

GitHub Issue 负责 Bug 的执行协作状态；[`docs/bug/`](../bug/README.md) 是代码缺陷的仓库证据源，负责稳定保存复现、根因、修复边界和验收结果。

- 一个能够独立修复和验收的 Bug 对应一个 Issue；同一根因的重复现象不重复建 Issue。
- Issue 正文链接 Bug 文档；Bug 文档元信息回填 Issue 编号。
- Issue 关闭不自动等于 Bug 归档。只有自动化或部署验证证据进入 Bug 文档后，文件才移入`归档`。
- Review 发现 Bug 时链接 Bug 文档；Issue 不承载长期 Design，修复需要改变 Contract 时仍按 Review → Design 流程处理。

## 操作约定

- **创建议题**：`gh issue create --title "..." --body "..."`。多行正文使用 heredoc。
- **读取议题**：`gh issue view <number> --comments`，使用 `jq` 过滤评论，并同时获取标签。
- **列出议题**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，根据任务添加合适的 `--label` 和 `--state` 过滤条件。
- **评论议题**：`gh issue comment <number> --body "..."`
- **添加或移除标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭议题**：`gh issue close <number> --comment "..."`

仓库信息从 `git remote -v` 推断；在仓库克隆目录中运行时，`gh` 会自动完成该推断。

## 将拉取请求作为分流入口

**PRs as a request surface: no.**

如需把外部拉取请求（Pull Request，PR）纳入分流队列，可将上述标记改为 `yes`；`/triage` 会读取该标记。

设置为 `yes` 后，PR 使用与议题相同的标签和状态：

- **读取 PR**：使用 `gh pr view <number> --comments` 读取内容和评论，使用 `gh pr diff <number>` 读取差异。
- **列出待分流的外部 PR**：运行 `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，仅保留 `authorAssociation` 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的记录，排除 `OWNER`、`MEMBER` 和 `COLLABORATOR`。
- **评论、添加标签或关闭**：使用 `gh pr comment`、`gh pr edit --add-label`、`gh pr edit --remove-label` 和 `gh pr close`。

GitHub 的议题与 PR 共用编号空间，因此 `#42` 可能指向任一类型。先运行 `gh pr view 42`；若不存在，再运行 `gh issue view 42`。

## 技能要求“发布到议题跟踪器”时

创建一个 GitHub Issue。

## 技能要求“获取相关工单”时

运行 `gh issue view <number> --comments`。

## 路径规划操作

以下约定供 `/wayfinder` 使用。一个地图（map）对应一个主议题，其子议题（child issue）作为具体工单。

- **地图**：使用一个带 `wayfinder:map` 标签的议题保存 Notes、Decisions-so-far 和 Fog。创建命令为 `gh issue create --label wayfinder:map`。
- **子工单**：通过 GitHub 子议题接口关联到地图，使用 `gh api` 调用 sub-issues endpoint。如果仓库未启用子议题，则在地图正文中添加任务列表，并在子工单正文顶部写入 `Part of #<map>`。标签使用 `wayfinder:<type>`，其中类型为 `research`、`prototype`、`grilling` 或 `task`。工单被领取后，分配给负责执行的开发者。
- **阻塞关系**：优先使用 GitHub 原生议题依赖。通过 `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` 添加依赖，其中 `<blocker-db-id>` 必须是阻塞议题的数字数据库 ID，可通过 `gh api repos/<owner>/<repo>/issues/<n> --jq .id` 获取，不能使用议题编号或 `node_id`。GitHub 返回的 `issue_dependencies_summary.blocked_by` 表示当前仍开放的阻塞项。如果原生依赖不可用，则在子工单正文顶部写入 `Blocked by: #<n>, #<n>`。所有阻塞议题关闭后，工单才解除阻塞。
- **前沿查询**：列出地图下仍开放的子工单，排除存在开放阻塞项或已有负责人者，按地图中的顺序选择第一个。
- **领取**：运行 `gh issue edit <n> --add-assignee @me`；这是会话中的第一次写操作。
- **解决**：运行 `gh issue comment <n> --body "<answer>"`，随后运行 `gh issue close <n>`，最后在地图的 Decisions-so-far 中追加上下文指针及链接。
