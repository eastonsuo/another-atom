# Another Atom V1 首次需求结构化澄清

[toc]

- **文档状态：** V1 当前 Agent Contract
- **产品设计：** [统一 Chat 与 Human-in-the-loop](../产品设计/06-统一Chat与Human-in-the-loop.md)
- **问题来源：** [首次需求结构化澄清检查](../../../review/待办/24-[产品]-2026-07-14-首次需求结构化澄清.md)

## 背景

首次入口原本只有 `direct | team`。当用户表达了构建意图但尚未说明关键产品条件时，Lead 只能把问题写进 `direct.response`，前端无法区分回答与澄清，也无法把用户选择确定性地交给 Product Manager。

本文定义首次入口的最小结构化澄清 Contract。它只增加一个入口路由和一组单选字段，不引入动态问卷、长期 Memory 或新的团队阶段。

## 摘要

- **路由语义**
  - 首次 Lead 使用 `direct | clarify | team`；只有 `team` 创建首次 Project 和 Run。
- **结构化输出**
  - `clarify` 返回一至四个问题，每题二至六个单选项；问题和选项由 Schema 校验。
- **确定性交接**
  - Studio 将原始需求和用户选择按固定文本格式组成补充需求，再使用显式 `force_team` 进入 PM。
- **授权边界**
  - 结构化选择只授权进入产品整理阶段，不替代 ProductSpec 确认，也不授权代码写入或发布。

## 1. 路由 Contract

`LeadRoute` 增加 `clarify`：

| 路由 | 使用条件 | 是否创建 Project/Run | 用户可见操作 |
| --- | --- | --- | --- |
| `direct` | 用户在询问能力、概念或当前行为，没有表达执行意图 | 否 | 查看回答；必要时显式调用团队 |
| `clarify` | 用户表达了构建意图，但缺少会实质改变交付结果的关键选择 | 否 | 完成结构化选择后进入下一步 |
| `team` | 用户明确要求构建，且信息足以交给 PM 整理 ProductSpec | 是 | 进入首次 Project 工作流 |

`force_team=true` 只表示用户已经完成结构化选择或明确覆盖 Lead 判断。它不跳过 PM，也不跳过 ProductSpec 确认。

## 2. 数据 Contract

`LeadDecision` 增加 `clarification_questions`：

```text
LeadDecision
  route: direct | clarify | team
  response: string
  reason: string
  clarification_questions: LeadClarificationQuestion[]

LeadClarificationQuestion
  id: string
  question: string
  options: LeadClarificationOption[2..6]

LeadClarificationOption
  value: string
  label: string
  description?: string
```

确定性校验规则：

1. `route=clarify` 时必须有一至四个问题；其他路由不得携带问题。
2. 同一 Decision 中问题 `id` 唯一，同一问题内 `value` 唯一。
3. 所有文本去除首尾空白并受长度上限约束。
4. Studio 为每题额外提供 `__unsure__`，显示为“暂不确定”，避免模型选项不覆盖用户情况时阻断下一步。

## 3. 下一步输入

Studio 不解析 Lead 的自然语言正文。用户完成选择后，按固定格式生成 PM 输入：

```text
<原始需求>

用户结构化补充：
- <问题一>：<所选标签>
- <问题二>：暂不确定
```

该文本作为首次 Run 的 Prompt 持久化。选择顺序严格按 `clarification_questions` 返回顺序；选项只使用当前 Decision 中的标签，不接受任意客户端字段注入。

## 4. UI 状态

`clarify` 卡片包含：

- Lead 的简短说明；
- 按问题分组的单选按钮；
- 已完成数量；
- “下一步”按钮。

按钮状态：

- 尚有未选择问题：禁用，并显示还需完成的数量；
- 提交中：禁用并显示加载状态；
- 全部完成：调用现有 Lead API 的显式团队覆盖，再创建一次首次 Run；
- API 失败：保留当前选择并展示错误，允许重试。

## 5. 边界与验收

- 本实现不把结构化澄清写成新的 HumanTask；Project 尚未创建，卡片仍属于首次入口的短会话状态。
- 刷新首页会丢失尚未提交的首次澄清选择，与当前首次 Prompt 草稿边界一致；Project 创建后的 PM 澄清继续使用持久化 HumanTask。
- 已有 Project Chat 继续使用 `answer | clarify | propose_change`，不复用本 Contract。
- 自动化测试必须覆盖 Schema 校验、Mock 路由、`clarify` 不创建 Project、下一步创建一次 Run，以及 Studio 生产构建。
