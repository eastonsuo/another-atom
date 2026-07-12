# Another Atom V1 设计索引

- 版本状态：当前实现与验收基线
- 实施顺序：V1 验收完成后再进入 V2

## 版本目标与范围

V1 用最小实现证明完整产品闭环：用户从 Lead 提交产品需求，检查 Blueprint，经过固定专业团队构建，获得 Preview 和 Project 源码，再通过 Edit、Restore 和显式 Publish 管理版本与公开结果。

- **[产品范围]** V1 接受游戏、工具、看板、目录等不同产品目标，但只交付自包含 HTML/CSS/JavaScript 浏览器应用；不宣称真实后端、支付、OAuth、外部网络、原生 Runtime 或动态依赖已经支持。
- **[Agent 范围]** Lead 只做 `direct/team` 二选一路由；`team` 固定执行 Product Manager → Architect → Engineer → Data Analyst → Runtime Validator → Reviewer，不做动态角色子集、并行或自主仲裁。
- **[工程范围]** 当前部署基线是本地单实例或 Railway 单副本；使用进程内调度、单 Worker、持久化 Job/Artifact/版本和服务端 Project Git。
- **[交付范围]** Build、Edit 和 Restore 创建 ProjectVersion 与 Git commit，但不会自动改变线上发布指针；Publish、Update 和 Unpublish 由用户明确触发。

## 用户闭环

```text
请求 -> Blueprint 检查/必要确认 -> 固定团队构建 -> Preview
     -> Edit / Resolve / Restore -> ProjectVersion -> 显式发布 -> Public URL
```

用户能检查 Blueprint、ArchitectureSpec、AppSpec、DataProfile、ValidationReport、ReviewReport、运行事件和 Project 文件；这些产物不是 README 中的概念展示，而是 V1 状态、恢复和验收的依据。

## 产品设计

- [产品需求](./产品设计/产品需求.md)
- [简要交付说明](./产品设计/简要交付说明.md)

## Agent 设计

- [多角色 Agent 设计](./Agent设计/Agent设计.md)
- [多角色 Agent 设计问答](./Agent设计/多角色Agent设计问答.md)
- [对话式 AI Coding 初版设计](./Agent设计/对话式AI-Coding初版设计.md)

## 工程设计

- [架构设计](./工程设计/架构设计.md)
- [本地运行与 Railway 部署](./工程设计/本地运行与Railway部署.md)

## Review

- [V1 Review 索引](../../review/V1/README.md)
- [关键设计与实现检查](../../review/V1/综合评审/2026-07-12-关键设计与实现检查.md)

## 当前状态与剩余验收

- **[已形成闭环]** Session、用户级 Project 隔离、Lead 路由、固定团队、风险确认、Project Git、Preview、版本与显式发布已有实现；具体完成证据以 Review 为准。
- **[不提前进入 V2]** 动态 TaskGraph、角色子集、局部并行、结构化返工、仲裁、多 Worker 与共享 Artifact Storage 不属于 V1。

仍需完成或补足证据的 V1 项目：

- **[Project 对话线程]** 将 Lead 澄清、团队构建和 Follow-up 按 `project_id / run_id / thread_id` 关联，并在 Project Workspace 中恢复完整讨论历史。
- **[真实 Provider 全链路]** 用真实模型分别验证 supported/adapted/unsupported 判定，并跑通 Product Manager → Architect → Engineer → Data Analyst → Reviewer 的完整链路，核对每阶段 Artifact 和 Usage Ledger。
- **[Linux Sandbox]** 在目标 Linux Host 验证 rootless Runtime、禁网、只读根文件系统、capability/seccomp、资源限制、跨用户隔离和 worktree 清理。
- **[部署恢复]** 在部署环境验证 Blueprint、Build Job、阶段 Artifact、配额和 ProjectVersion 的重启幂等恢复。
- **[浏览器验收]** 使用两个干净账号验证 Project 隔离，并从无登录浏览器验证显式发布的 Public URL。
- **[剩余交互]** 完成失败后的 Retry/Resolve、项目重命名/删除和附件实际上传；新增入口同时补齐 owner 校验、状态、错误和自动化测试。
