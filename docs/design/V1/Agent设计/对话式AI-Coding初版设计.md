# Another Atom V1 对话式 AI Coding 初版设计

[toc]

- 文档状态：设计提案
- 适用版本：V1 P0
- 当前基线：[V1 Agent 设计](./Agent设计.md) · [V1 架构设计](../工程设计/架构设计.md)
- 关联 Review：[审批式与对话式交互评审](../../../review/V1/产品评审/2026-07-10-审批与对话交互评审.md)

## 1. 结论

初版目标不是实现完整 Coding Agent，而是在现有 Project、Run、Artifact、ProjectVersion、Git、Validator 和 Worker 上补齐一条受控修改闭环：

```text
围绕当前项目对话
  -> 选择文件或版本
  -> 提出修改要求 / 查看 Agent 建议
  -> 生成 ChangeProposal
  -> 展示 Diff 和校验结果
  -> 用户确认
  -> 写入源码并创建 ProjectVersion + Git commit
```

实现难度中等，不需要推翻当前架构。主要新增项目对话、修改提案和基于版本的恢复语义。初版继续以 AppSpec 为生成代码事实源，不向 Agent 开放任意文件写入、Shell、依赖安装和网络。

## 2. 要解决和不解决的问题

### 2.1 初版解决

- 用户可以在同一 Project 中持续对话，而不是每次重新创建项目；
- 用户可以选择当前版本或文件作为本轮上下文；
- Agent 回答项目问题时不修改文件；
- Agent 修改项目时必须生成可检查的 ChangeProposal；
- 用户能看到受影响文件、Diff 和 ValidationReport；
- 用户确认后才创建新版本和 Git commit；
- 失败后可以复用已完成 Artifact，从失败阶段继续。

### 2.2 初版不解决

- 动态拆任务、并行 Specialist、返工仲裁；
- Agent 任意编辑多文件或直接操作 Git；
- Shell、依赖安装、受控网络和浏览器自动化；
- 多个写 Agent 的分支、冲突和合并；
- 跨 Project 的长期用户画像或向量 Memory。

这些能力会引入 TaskGraph、Tool Gateway 和 Agent Task Sandbox，属于固定修改闭环稳定后的演进范围。

## 3. 当前实现基础与缺口

当前已经具备：

- ProjectSession 和 Run；
- Blueprint、ArchitectureSpec、AppSpec、ValidationReport 和 DataReview；
- ProjectVersion 与 Git commit；
- Project 文件查看；
- Validator、Build Worker、SSE 和持久化 Event。

当前缺口：

- LeadMessage 与 Run 没有形成统一项目对话；
- ProjectSession 没有完整 Message 模型；
- RevisionRequest 只支持标题、正文和主色等固定字段；
- 文件选择没有进入 Agent Context；
- Agent 输出与版本创建之间没有 Diff 和用户确认；
- failed Run 没有标准 parent/base/evidence 恢复关系。

## 4. 对话意图

初版只支持三类互斥意图：

```text
ask
  解释当前项目、文件、Artifact 或失败原因
  不创建修改版本

modify
  基于当前版本生成修改提案
  用户确认后创建版本

retry
  基于失败 Run 和已有 Artifact 继续
  只重跑必要阶段
```

意图可以由 Lead 结构化判断，但用户选择“修改项目”或“从这里重试”时具有更高优先级，模型不能把显式写操作降级为普通回答。

## 5. 数据 Contract

### 5.1 ConversationMessage

```text
id
project_id
session_id
user_id
role: user | assistant | system
message_type: text | artifact | change_proposal | error
content
intent: ask | modify | retry
run_id?
base_version_id?
artifact_refs[]
selected_files[]
status: pending | completed | failed
created_at
```

它把 Lead、Run、Artifact、修改提案和版本结果串成统一时间线，但不保存 Chain of Thought。

### 5.2 Run 关联

Run 增加：

```text
parent_run_id?
base_version_id?
trigger_message_id?
intent?
```

这些字段用于回答本次修改由哪条消息触发、基于哪个版本、复用了哪个失败 Run，而不是靠时间顺序猜测。

### 5.3 ChangeProposal

```text
summary
base_version_id
affected_files[]
updated_app_spec
reasons[]
validation_report
risk_flags[]
```

`affected_files` 和最终 Diff 由 Runtime 比较旧、新 AppSpec 后计算，不能只相信模型声明。Proposal 本身不移动当前版本和发布指针。

## 6. Context

Follow-up 修改的最小 Context：

```text
用户最新消息
+ 当前已接受 Blueprint
+ 当前 ArchitectureSpec
+ base ProjectVersion 的 AppSpec
+ 用户选中的文件内容
+ 当前 Capability Policy
+ 最近一次相关失败 Evidence
```

默认不包含：完整项目聊天、所有历史版本、完整日志、其他 Agent 私有上下文和无关文件。

文件选择只是 Context 输入。初版 Engineer 仍输出更新后的 AppSpec，由 Runtime 生成文件和 Diff；不允许模型直接写 Repository。

## 7. 状态机

只读回答：

```text
message.created
  -> routing
  -> answering
  -> completed
```

修改：

```text
message.created
  -> routing
  -> modification_running
  -> validating
  -> awaiting_change_approval
       |-- reject -> completed_without_change
       `-- approve -> version_creating -> completed
```

拒绝 Proposal 时保留消息、Proposal 和校验证据，但不创建版本。确认时 Repository Service 物化源码、创建 Git commit 和 ProjectVersion；Publish 仍是独立用户动作。

## 8. 失败恢复

失败恢复创建子 Run，并复用已完成 Artifact：

```text
原 Run：PM ✓ -> Architect ✓ -> Engineer ✓ -> Validation ✗

用户补充修改意见
  -> 新 Run(parent_run_id, base_version_id)
  -> 复用 Blueprint + ArchitectureSpec
  -> 输入原 AppSpec + failed checks + 用户约束
  -> Engineer Repair
  -> Validation
  -> ChangeProposal / NeedsInput
```

Retry 不能默认整轮重跑；只有上游 Contract 变化时才使下游 Artifact 失效。

## 9. UI

现有 Workspace 增加 Project 对话区域，不重做整个布局。消息需要区分普通回答、修改提案、失败、等待确认和已创建版本。

ChangeProposal 至少展示：

- 修改摘要；
- base version；
- 受影响文件；
- Diff；
- ValidationReport；
- 确认并创建版本；
- 继续调整；
- 放弃。

用户在文件面板选择文件后发消息，消息必须保存所选路径和对应 base version，避免后续版本变化后仍引用错误内容。

## 10. Sandbox 边界

初版 Agent 不需要新的 Agent Task Sandbox：

```text
Agent -> AppSpec / ChangeProposal
Runtime -> Validator
Repository Service -> 文件和 Git commit
```

现有 Linux Sandbox 继续服务用户 Vim 编辑。只有 Agent 获得直接文件 Patch、构建、测试、依赖或浏览器 Tool 时，才引入独立 Task Snapshot 和 Agent Task Sandbox。

## 11. 实施顺序

1. 持久化 ConversationMessage，形成 Project 时间线并支持只读问答；
2. 文件选择进入 Context，但保持 Agent 只读；
3. 增加 ChangeProposal、Diff、Validation 和确认后版本创建；
4. 增加 parent Run、base version 和失败 Evidence，支持阶段级 retry；
5. 通过 Review 后再评估文件级 Patch 和 Agent Task Sandbox。

## 12. 验收

- 每条修改消息能追溯 trigger message、base version、Run、Proposal 和结果版本；
- ask 不创建 ProjectVersion；
- reject 不修改文件、当前版本或发布指针；
- approve 后 Diff、AppSpec、仓库文件和 Git commit 一致；
- base version 变化后旧 Proposal 不能直接确认；
- retry 不重复调用已完成且仍有效的阶段，不重复扣费；
- 失败原因、重试入口和用户下一步在刷新、断线和重启后仍可恢复；
- 跨用户、Project、Session 的消息、文件和 Context 泄漏为 0。
