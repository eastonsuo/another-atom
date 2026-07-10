# Another Atom V2

- 文档状态：方向占位，尚未进入产品定义或技术设计

V2 已确认的方向只有一项：从 V1 的固定顺序角色接力，演进到自主多 Agent 协作。

```text
V1: Fixed Sequential Role Pipeline
Planner -> Designer -> Engineer -> QA

V2: Autonomous Multi-Agent System
Supervisor -> dynamic delegation / parallel execution
           -> independent context and tool permissions
           -> feedback loops / conflict resolution / result merge
```

以下内容尚未确认，不能视为 V2 承诺：

- 是否与 CC 式本地 Agent Runtime 同版本交付。
- Agent 数量、模型供应商和编排框架。
- 并行策略、预算分配和终止条件。
- 远程执行沙箱与本地执行的关系。
- V2 的产品范围、验收标准和部署方案。

V2 正式立项前，以 [V1 文档](../v1/README.md)为唯一实施基线。
