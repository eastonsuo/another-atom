# Code Spec 与 Implementation Plan

本目录保存从 `docs/design/**` 派生的实施合同和可选任务账本，不是新的产品或技术设计来源。项目级门禁与阶段关系见 [`Feature 交付工作流`](../agents/feature-delivery-workflow.md)。

## Code Spec

正式 Code Spec 放在 `specs/`，推荐命名：

```text
YYYY-MM-DD-中文主题-Code-Spec.md
```

每份 Code Spec 至少记录：

- 文档性质、Feature 和覆盖范围；
- 唯一主技术设计及可定位章节；
- 目标代码仓库和代码基线；
- 明确非目标；
- 外部行为、组件边界、接口、数据、状态、失败、兼容与迁移合同中实际适用的内容；
- 正向、反向和恢复验收场景；
- `待书面审阅`、`已确认` 或 `需重新审阅` 状态；
- 状态为`已确认`时的确认主体、日期和可定位书面依据。

Code Spec 只能由已确认技术总设计受控派生。无法证明设计稳定、当前代码推翻核心前提或需要新增设计决定时，不创建或覆盖正式 Spec。

## Implementation Plan

Implementation Plan 放在 `plans/`，推荐命名：

```text
YYYY-MM-DD-中文主题-Implementation-Plan.md
```

Plan 默认可选，只在复杂、跨仓或需要多轮任务账本时使用。一个 Feature 只能有一份当前 Plan；它负责文件落点、依赖、任务状态、验证入口和完成证据，不补充设计合同，也不自动授权代码修改、推送或部署。

Plan 状态使用：`草拟中`、`阻塞`、`待审阅`、`可执行`、`需重新核对`、`已完成`、`已废弃`、`已被取代`或`历史参考`。进入`可执行`前必须单独获得用户确认。
