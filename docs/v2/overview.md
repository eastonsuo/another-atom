# Another Atom V2

- 文档状态：V2 计划实施；Agent 设计已完成，完整 PRD、技术方案、部署规格与验收基线待实施前补齐

V2 从 V1 的固定顺序角色接力演进到自主多 Agent 协作。当前已完成执行范式、角色、控制权、Context、Tool、Sandbox、Handoff、回退、仲裁和收敛机制的 Agent 设计：

- [V2 Agent 设计](./agent-design.md)

```text
V1: Fixed Sequential Role Pipeline
Product Manager -> Designer -> Engineer -> QA

V2: Autonomous Multi-Agent System
Leader -> Product Manager / Architect / Designer / Engineer / QA
       -> dynamic delegation / selective parallel execution
       -> independent context and tool permissions
       -> feedback loops / conflict resolution / result merge
```

以下实现决策必须在 V2 开发前确认：

- 是否与 CC 式本地 Agent Runtime 同版本交付。
- 模型供应商、具体编排框架和 Prompt 版本策略。
- 并行策略、预算分配和终止条件。
- 远程执行沙箱与本地执行的关系。
- V2 的产品范围、验收标准和部署方案。

实施顺序固定为 V1 -> V2。当前开发以 [V1 产品需求](../v1/another-atom-v1-prd.md)和 [V1 架构设计](../v1/architecture-design.md)为基线；V1 验收完成并补齐上述决策后，本文及其后续 PRD/技术设计共同构成 V2 实施基线。规划不代表功能已经实现。
