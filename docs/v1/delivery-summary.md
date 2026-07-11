# V1 简要交付说明

## 1. 实现思路与关键取舍

- **[产品目标] 任意需求，受限交付：** 用户可以提出游戏、工具、看板或商品目录等不同目标；V1 将其实现为自包含的 HTML/CSS/JavaScript Web 应用。真实认证、支付、持久化数据库、第三方服务、原生能力、动态依赖和 Shell 不假装已经支持，而是进入 `adapted` 或 `unsupported`。

- **[Agent] 先产物，后执行：** Lead 只做 `direct/team` 分派；团队固定按 Product Manager → Architect → Engineer → Data Analyst 交接 Blueprint、ArchitectureSpec、Web AppSpec、ValidationReport 和 DataReview。这样每一步都能检查、保存和恢复，不依赖一段无限增长的聊天记录。

- **[审批] 只在风险点停下：** 受限 Web Runtime 内、基础预算内的 `supported` 工作自动继续；服务端能力替代、额外预算、破坏性源码操作和发布变更才需要确认。用户确认 PM 草案后直接进入 Architect，不重复调用 PM。

- **[工程] 状态优先于动画：** Run、Artifact、配额预占/结算、Build Job、Git commit 和 ProjectVersion 都持久化。单实例 V1 仍通过状态 CAS、唯一约束和阶段复用避免重复排队、重复结算和重启后的重复构建。

- **[安全] 预览与平台权限分开：** 生成源码写入每个 Project 的服务端 Git 仓库；Preview 在禁网、无同源权限的 iframe 中运行。V1 不执行模型生成的 Shell，不安装运行时依赖。

## 2. 当前完成程度

### 已完成

- **[完整链路]** 登录 → Lead → PM 草案/风险确认 → 固定团队构建 → Preview → Edit/Restore → Git Version → 显式 Publish 的本地纵切可运行。
- **[通用 Web 代码]** Engineer 可产出 `index.html`、`styles.css`、`app.js`；扫雷游戏、工具和目录不会被强制改写为商品目录。
- **[可检查与可恢复]** Blueprint、ArchitectureSpec、AppSpec、ValidationReport、DataReview、事件、版本和源码均可查看；Worker 重启会复用已提交阶段和既有版本。
- **[隔离与权限]** 用户名密码 Session、User/Project 归属校验、Preview 权限校验、Git 源码归属、配额事务和单实例并发审批保护已实现。
- **[可验证性]** 后端自动化测试 73 项通过；Studio lint 与生产构建通过。

### 尚未完成 / 不应宣称已完成

- **[Railway 验收]** 还未完成 Railway 单副本、持久化 Volume、真实 Provider 和公开 URL 的实机验收。
- **[真实 Sandbox]** 受限 Vim/Sandbox 的产品入口已存在，但 rootless 容器、禁网、seccomp/cgroup、资源限制、worktree 清理尚未在目标 Linux Host 完成实测。
- **[项目对话]** Lead 的提问/澄清、团队构建和后续 Follow-up 尚未形成按 `project_id / run_id / thread_id` 可恢复的完整对话线程。
- **[外部能力]** 不支持真实 OAuth、支付、云数据库、第三方 API、动态安装依赖、通用终端或任意后端代码执行。
- **[规模化]** 不支持多实例 API/Worker、消息队列、PostgreSQL LISTEN/NOTIFY、共享对象存储或分布式 Lease fencing。

## 3. 继续投入时的优先级

1. **[P0｜可交付] 完成 Railway + Linux Sandbox 实机验收。** 这是从“本地纵切可运行”变成“可公开交付”的必要条件；先验证持久化、重启恢复、双用户隔离、Public URL 和 Sandbox 边界。
2. **[P0｜可信使用] 完成项目对话线程与失败后的 Retry / Resolve。** 用户需要能回看 PM 为什么改写、当前卡在哪一步、如何继续，而不是只看到阶段日志。
3. **[P1｜Web 能力] 扩展通用 Web Contract。** 在不放开任意执行的前提下，增加更丰富的组件、跨页面状态和确定性交互测试；涉及真实后端时先设计受控服务能力，而不是把密钥或网络权限交给模型。
4. **[P2｜V2 Agent Runtime] 动态任务图、角色子集、局部并行、返工与仲裁。** 这些建立在 V1 的 Artifact、状态机、权限和恢复边界已经通过部署验收之后；现在提前实现只会扩大状态复杂度。

## 4. 结论

V1 已经完成“可检查的多角色生成 → 受限 Web 源码 → 可恢复版本 → 用户显式发布”的本地闭环。下一阶段的关键不是继续堆 Agent 数量或接更多外部服务，而是完成单副本部署与真实 Sandbox 验收，把现有正确性、安全边界和可恢复性带到公网环境。
