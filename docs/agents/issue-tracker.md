# 议题跟踪器：GitHub

本仓库的议题和产品需求文档（PRD）记录在 GitHub Issues 中。所有操作使用 `gh` 命令行工具完成。

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
