# Engineer 项目源码 Contract 缺口

[toc]

> 类型：工程检查｜状态：待办｜日期：2026-07-14｜版本范围：V1｜基线：`AppSpec`、Engineer Prompt、Repository Packager 与 Preview Adapter

- **产品设计：** [V1 核心产品需求与交互](../../design/V1/产品设计/01-核心产品需求与交互.md)
- **Agent 设计：** [V1 多 Agent 设计](../../design/V1/技术设计/01-[Agent]-多Agent设计.md)
- **工程设计：** [V1 系统架构](../../design/V1/技术设计/03-[工程]-系统架构.md)

## 背景

工程阶段界面显示“工程师正在生成 HTML、CSS 和 JavaScript”。检查确认这不是单纯文案问题：当前 `AppSpec` 只包含 HTML body、CSS、JavaScript 和页面元数据，Repository Packager 固定物化 `index.html`、`styles.css`、`app.js` 与 `app-spec.json`。因此 Engineer 的实际生成边界仍是自包含 Web 应用，而不是通用 Project 源码。

## 摘要

- **[P0｜实现与产品边界冲突]** 产品基线要求保留用户请求的项目类型；Preview 只是一种项目类型能力，不能反向限定生成边界。但当前 Engineer Contract 会把所有可构建请求收敛为 Web `AppSpec`。
- **[P1｜Repository 不是 Engineer 的原生输出]** 当前项目文件由 Packager 从三个字符串派生，Engineer 不能表达多文件目录、配置、依赖声明、测试、README、服务端代码或非 Web 源码。
- **[P1｜Runtime Adapter 与源码 Contract 耦合]** 浏览器 Preview、Validator 和 Engineer 输出共享同一个 Web Contract，导致“暂时没有运行适配器”和“不能生成该类项目”无法区分。

## 证据

1. `another_atom/contracts/schemas.py` 的 `AppSpec` 以 `html`、`css`、`javascript` 为核心源码字段。
2. `another_atom/agent/provider.py` 要求 Engineer 返回可在单个 Sandbox HTML 文档中运行的完整 Web `AppSpec`。
3. `another_atom/repository/service.py` 固定物化四个版本文件，未接收通用文件清单。
4. `another_atom/build/renderer.py` 直接对浏览器源码和 Web Sandbox 能力执行门禁。
5. `docs/design/V1/产品设计/01-核心产品需求与交互.md` 明确 Preview 是项目类型能力，不是生成边界。

## 影响

- 非 Web 请求即使可以生成源码，也只能被拒绝、改写或伪装成网页。
- Web 全栈项目无法诚实表达服务端、依赖和配置，只能生成浏览器演示层。
- 把界面文案改为“生成项目代码”会扩大承诺，但不会改变实际交付物，因此不能作为修复。

## 后续处理要求

本 Review 只落库问题，不在本次进度可观察性修改中重构生成边界。进入实现前需新增或修订正式技术设计，至少确定：

1. 通用项目源码 Contract（例如文件清单、项目类型、入口、构建与运行元数据）的字段和大小边界。
2. Engineer 如何生成完整文件集，Repository 如何原样保存并建立 Artifact/Git/ProjectVersion 对应关系。
3. Web Preview、静态校验以及未来其他 Runtime 如何作为 Adapter 消费项目源码，而不是定义源码形态。
4. 没有 Runtime Adapter 时，如何仍然交付源码、文档、校验和导出，并明确“不支持在线预览”。
5. 从现有 `AppSpec` 与历史 ProjectVersion 迁移和兼容的方式。

在上述设计进入 `docs/design/V1/技术设计/`、实现完成且 Web 与至少一种无 Preview 项目路径通过验收前，本 Review 保持`待办`。

## 2026-07-15 Update：两次网页版贪吃蛇失败日志复核

### 复核材料

- Run `d276bc36-af08-4a5b-8606-01b1ff551db9`，最终错误 `BUILD_VALIDATION_FAILED`。
- Run `f697eba0-c55a-452e-840e-b2517a601df4`，最终错误 `WORKER_FAILED`。
- 本地调试日志：`another-atom-run-d276bc36-af08-4a5b-8606-01b1ff551db9.log`、`another-atom-run-f697eba0-c55a-452e-840e-b2517a601df4.log`。

两次请求都是网页版贪吃蛇，选择 `web-static-v1` 并校验 HTML 本身合理。日志证明的问题不是“Web 项目不应校验 HTML”，而是当前 Web `AppSpec`、通用项目源码和 Runtime Adapter 的职责仍未真正拆开：模型输出先按宽松 JSON Schema 通过 Contract validation，Runtime 再按更严格但没有在上游表达的 Web 文件约束执行，导致结构错误直到 Build/Test 阶段才暴露。

### 发现一：Web AppSpec 的 Schema 通过不等于可执行源码 Contract 成立

两个 Engineer 输出均把完整 `<!DOCTYPE html> / <html> / <head> / <body>` 文档、`<style>` 或 `<script>` 放入 `AppSpec.html`；Runtime 则把该字段当应用正文重新包入自己管理的 `index.html` 外壳。结果是嵌套文档、内联脚本或不存在的脚本入口进入 SourceBundle，虽然结构化 JSON 已通过校验，实际源码并不满足 `web-static-v1`。

这说明当前校验分层缺了一层 Adapter 输入校验：

1. 通用 Contract 只应确认 Project 类型、源码文件清单、入口、测试入口和 Adapter 绑定关系。
2. `web-static-v1` 应在调用 Executor 前确定性检查自己的输入约束，例如入口存在、HTML 形态、Runtime 管理外壳、CSS/JavaScript 分离和相对引用闭包。
3. Runtime Build/Test 继续保留，但只负责必须物化或执行后才能得到的证据，不能成为第一次发现静态文件结构错误的地方。

`<script>` 在这两次日志中被归入 `sandbox-boundary` 也不够准确。这里首先是 `web-static-v1` 输入结构违规，不是网络越界；Sandbox 可以保留最后一道防线，但上游应返回可定位的 Adapter Contract 错误。

### 发现二：SourceBundle 没有保证文件引用闭包

Run `f697...` 的 HTML 和测试引用 `src/constants.js`、`src/snake.js` 等文件，但 SourceBundle 只物化 `index.html`、`styles.css`、`app.js`、`app-spec.json` 和测试文件。测试因此以 `MODULE_NOT_FOUND` 失败。

当前 `web-source` 检查只确认固定 Web 文件存在，没有验证 HTML/CSS/JavaScript/测试中的受控相对引用是否都能在 SourceBundle 中解析。这个缺口对 Web 项目已经造成真实失败；迁移到通用 SourceBundle 后也必须作为 Adapter 无关的文件清单完整性门禁保留。

### 发现三：Repair 仍在同一个宽松 Contract 上完整重生成

Run `d276...` 的 Repair 收到了 `sandbox-boundary` 和 `runtime.unit_tests` 的确定性证据，但修复结果把 JavaScript 移入内联 `<script>`、清空独立 `javascript` 字段，也没有修正 `GameController.start()` 产生多余 `IDLE` 状态回调的问题。修复 JSON 再次通过 Contract validation，随后仍被相同门禁拒绝。

Run `f697...` 的 Repair 生成约 29 万字符、耗时约 493 秒后才进入结构纠错，说明完整重生成不仅不能保证对准失败项，还显著放大延迟和 Token 消耗。Repair 后续应以失败证据绑定的文件变更为交付单位，并受相同的 SourceBundle、Adapter 输入和执行门禁约束；不能因为是 Repair 就降低 Contract 强度。

### 发现四：Provider 纠错路径存在独立实现 bug

Run `f697...` 最终不是正常的校验失败，而是 `another_atom/agent/provider.py` 在 `_extract_json(content)` 抛错、`json_content` 尚未完成赋值时，异常分支仍引用 `json_content` 构造 Contract correction 消息，触发 `UnboundLocalError`，最终被包装成 `WORKER_FAILED`。

这是独立于源码 Contract 的 P0 实现 bug。模型输出不合法应形成可恢复的 `CONTRACT_VALIDATION_FAILED` 或进入有界纠错，不能让 Worker 自身崩溃，也不能覆盖原始验证证据。

### 根因结论

本次日志实证把原 Review 的主结论进一步收敛为：

> 当前实现把首个 Web Preview Adapter 的字段形态当成 Engineer 的通用生成边界，同时又没有把该 Adapter 的真实文件约束编码为模型输出后的确定性门禁。上游 Contract 过宽、下游 Runtime 过晚，Repair 和 Provider 异常处理再把一次可定位的生成错误放大为长时失败或 Worker 崩溃。

这不构成删除 Runtime 校验的理由。Runtime 仍必须生成不可由 Agent 自报的 Build/Test/Sandbox 证据；需要调整的是校验职责和时机：通用 SourceBundle 负责表达项目源码，Adapter 负责声明并预检其固定输入，Executor 负责真实执行。没有匹配 Adapter 的非 Web 项目仍可保存源码、文档和版本，但应明确“不支持在线运行或预览”，不能被改写成 HTML，也不能仅因没有 Preview Adapter 被判定为源码交付失败。

该结论已与[整体产品目标与定位](../../design/整体/01-[产品]-整体产品目标与定位.md#46-产品目标开放还是-runtime-无限制)和[V1 多 Agent 设计](../../design/V1/技术设计/01-[Agent]-多Agent设计.md#25-工程师engineer交付项目源码单元测试并对通过负责)对齐，不新增另一套长期设计。

### 修复与验收要求

1. 修复 Provider 在 JSON 提取失败时引用未初始化变量的问题，并覆盖 Ollama、DeepSeek 两条结构纠错路径。
2. 在 Executor 前增加 Adapter 输入预检，Web 项目至少覆盖 HTML 形态、Runtime 管理外壳、代码字段分离和相对引用闭包。
3. 通用 SourceBundle 不再由 HTML/CSS/JavaScript 三个字符串定义；项目类型、入口、测试入口、文件清单和 Adapter 绑定成为显式 Contract。
4. Repair 使用绑定失败证据和候选 revision 的有界文件变更，不再无上限完整重生成；任何修复结果都重新经过相同门禁。
5. 验收至少覆盖：一个 `web-static-v1` Web 项目成功 Build/Test/Preview；一个测试引用缺失文件的项目在 Executor 前失败并给出准确路径；一个无 Preview Adapter 的非 Web 项目仍可保存源码、文档和版本；一次非法模型 JSON 能稳定纠错或可解释失败而不产生 `WORKER_FAILED`。

以上实现和部署证据补齐前，本 Review 继续保持`待办`。
