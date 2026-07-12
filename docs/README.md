# Another Atom 文档导航

[toc]

项目文档分为 Design 和 Review 两类，先按 `V1`、`V2`、`整体` 区分版本范围，再按产品、Agent、工程等领域分类。已经确认的方案进入 Design；带日期的检查、问题和阶段结论进入 Review。图片等非文档资源保存在 `assets/`。

## 设计

[设计文档](./design/README.md)回答“系统应该怎样工作”，是持续维护的实现依据。每个版本范围下按四个领域组织：

- `产品设计`：产品目标、用户流程、范围和版本优先级；
- `Agent设计`：角色、Context、Memory、调度、Handoff、Tool 和 Sandbox 交互边界；
- `工程设计`：系统架构、数据、部署、安全、可靠性和工程运行方式；
- `参考资料`：外部分析、术语和设计输入，不直接构成已采用 Contract。

## Review

[Review 文档](./review/README.md)回答“实际检查到了什么”，按产品评审、Agent 评审、工程评审和综合评审记录带日期的检查、反思、Bug、验证证据和阶段结论。

Review 发现需要系统性解决的问题时，在相应 Review 中记录依据与结论；形成正式决定后同步写入 Design。解决方案本身不在 Review 中长期维护。

## 资源

`assets/` 保存 README 和设计文档引用的图片，不参与设计与 Review 分类。
