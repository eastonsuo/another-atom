# Another Atom V2 设计索引

- 版本状态：计划版本，尚未实现
- 前置条件：V1 完成部署验收和 P0 闭环

## 版本目标与继承关系

V2 不创建另一套产品，而是在 V1 的 Session、Project、Git、Artifact、Risk Policy、Version 和 Publish Contract 上升级多智能体协作能力。

- **[Agent 目标]** Lead 从 `direct/team` 路由升级为受 Runtime 约束的 TaskGraph 协调者；专业角色按任务参与，并通过 Handoff、Evidence 和 ToolResult 交接。
- **[执行目标]** 只对无依赖冲突、无共享写入且预算已预留的任务开启局部并行；返工和仲裁必须有次数、预算和收敛边界。
- **[工程目标]** 将 Control Plane、Agent Worker、Artifact Storage 和 Sandbox Provider 按权限与容量拆分，支持持久化 Task/Lease、多 Worker 恢复和共享不可变产物。
- **[不变边界]** Agent 不能绕过 Tool Gateway、Risk Policy、预算或发布权限；ProjectVersion 仍需通过证据门禁，Publish 仍由用户明确触发。

## 产品设计

- [产品需求](./产品设计/产品需求.md)

## Agent 设计

- [Agent 设计](./Agent设计/Agent设计.md)

## 工程设计

- [架构设计](./工程设计/架构设计.md)

## Review

- [V2 Review 索引](../../review/V2/README.md)
