# Another Atom V2

- 文档状态：角色编排方向已形成设计稿；完整产品范围与技术方案尚未立项

V2 从 V1 的固定顺序角色接力演进到自主多 Agent 协作。当前已完成角色、控制权、Handoff、回退、仲裁和收敛机制的专题设计：

- [V2 角色与编排设计](./role-orchestration-design.md)

```text
V1: Fixed Sequential Role Pipeline
Product Manager -> Designer -> Engineer -> QA

V2: Autonomous Multi-Agent System
Leader -> Product Manager / Architect / Designer / Engineer / QA
       -> dynamic delegation / selective parallel execution
       -> independent context and tool permissions
       -> feedback loops / conflict resolution / result merge
```

以下内容尚未确认，不能视为 V2 承诺：

- 是否与 CC 式本地 Agent Runtime 同版本交付。
- 模型供应商、具体编排框架和 Prompt 版本策略。
- 并行策略、预算分配和终止条件。
- 远程执行沙箱与本地执行的关系。
- V2 的产品范围、验收标准和部署方案。

V2 正式立项前，以 [V1 产品需求](../v1/another-atom-v1-prd.md)和 [V1 架构设计](../v1/architecture-design.md)为唯一实施基线；角色设计稿不能视为已经实现或承诺交付。
