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
- **[P0｜可靠性未达到可用基线]** 当前实际观察中的 Engineer 候选一次通过率最多约 50%，大量错误直到 Build/Test 或 Repair 才暴露。V1 应把一次通过率提升到 90% 以上，同时保证任何候选失败都不会破坏已有可用版本。
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

### 可靠性目标与统计口径

当前实际使用中，Engineer 候选的一次通过率最多约 50%。这一数字来自现阶段运行观察，现有事件和统计尚不足以形成严格的历史基线；实现整改时必须先补齐可复算的通过率指标，不能继续依靠人工感受判断质量。

V1 本项整改目标为：

1. **Engineer 候选一次通过率达到 90% 以上。**“一次通过”指首次 Engineer 输出在不进入 Repair、不重新调用 Engineer 的情况下，连续通过结构化 Contract、SourceBundle/文件引用、Adapter 输入以及 Build/Test/Runtime 校验，并形成可预览或可交付版本。
2. **已有可用版本保留率为 100%。** 新候选只进入隔离候选区；全部门禁通过后才原子提升为新 ProjectVersion。候选失败只能标记“本次变更未通过”，不能把项目整体改成不可用状态。
3. **Provider 内部异常导致的任务失败为 0。** 非法 JSON、截断输出和结构纠错失败必须保留原始证据并进入有界重试或可解释失败，不能再转化为 `WORKER_FAILED`。
4. **未通过校验的候选写入正式版本为 0。** Repair 也必须重新经过完整门禁，不能绕过 Contract、Adapter 或 Runtime 校验。

一次通过率按 Adapter 分组统计，分子为首次候选直接通过的有效 Run 数，分母为进入 Engineer 且收到完整模型响应的有效 Run 数；用户取消、明确的上游 Provider 不可用不混入代码生成质量指标，但需单独统计。验收以每个已上线 Adapter 连续至少 100 个有效 Run 为窗口；样本不足时只能报告当前样本结果，不能宣称已经达到 90%。

这里的 90% 是首次候选质量目标，不包含 Repair 后成功。Repair 成功率和最终交付成功率应另行统计，否则会把低质量首轮输出隐藏在多次重试之后。

### 优先整改顺序

为先解决“不要失败”，实施顺序应固定为：

1. 固定 Runtime 管理外壳，模型不得修改 `DOCTYPE/html/head/body` 等 Adapter 管理结构；Web Engineer 只返回受控源码文件或受控文件 Patch。
2. 模型输出先落入隔离候选区，依次执行 Contract、路径与 Hash、文件引用闭包、Adapter 输入、Build/Test/Runtime 校验；全部通过后才原子替换当前版本。
3. 失败时保留最后可用版本和原始失败证据，并允许基于同一候选做局部 Repair；不得从头完整重生成整个项目。
4. 修复 Provider 结构纠错路径，使解析失败成为可恢复的 Contract 错误，而不是 Worker 崩溃。
5. 按项目类型选择 Adapter；没有 Adapter 的项目仍保存源码、文档和版本，只标记“不支持在线预览”，不得强制转成 Web 项目。

流式输出只能改善等待过程，不能提高一次通过率，因此不属于本项可靠性整改的核心手段。

### 修复与验收要求

1. 修复 Provider 在 JSON 提取失败时引用未初始化变量的问题，并覆盖 Ollama、DeepSeek 两条结构纠错路径。
2. 在 Executor 前增加 Adapter 输入预检，Web 项目至少覆盖 HTML 形态、Runtime 管理外壳、代码字段分离和相对引用闭包。
3. 通用 SourceBundle 不再由 HTML/CSS/JavaScript 三个字符串定义；项目类型、入口、测试入口、文件清单和 Adapter 绑定成为显式 Contract。
4. Repair 使用绑定失败证据和候选 revision 的有界文件变更，不再无上限完整重生成；任何修复结果都重新经过相同门禁。
5. 验收至少覆盖：一个 `web-static-v1` Web 项目成功 Build/Test/Preview；一个测试引用缺失文件的项目在 Executor 前失败并给出准确路径；一个无 Preview Adapter 的非 Web 项目仍可保存源码、文档和版本；一次非法模型 JSON 能稳定纠错或可解释失败而不产生 `WORKER_FAILED`。
6. 增加按 Adapter 记录的一次通过率、Repair 后通过率、最终交付成功率和 Provider 内部失败率；在连续至少 100 个有效 Run 的窗口中，一次通过率达到 90% 以上后才能关闭本项可靠性发现。

以上实现和部署证据补齐前，本 Review 继续保持`待办`。

## 2026-07-16 Update：Engineer 与 Runtime 规范统一校准

### 背景

前一版 Update 将“固定 Runtime 管理外壳”列为提高一次通过率的首要措施。该表述只适用于明确接收 HTML Fragment 的特定 Web Adapter，不能成为 Another Atom 支持任意代码时的通用设计。若为了达到一次通过率目标而固定源码骨架、缩窄项目类型或强制所有项目进入 Web 形态，会直接违反项目的产品基线。

本次校准覆盖 2026-07-15 Update 中“优先整改顺序”第 1 项，以及“修复与验收要求”第 2 项中把 Runtime 管理外壳视为通用约束的部分。其余关于 SourceBundle、候选版本、Provider 异常和局部 Repair 的发现继续成立。

### 校准后的核心判断

当前首要问题是 Engineer 的生成规范与 Runtime 的实际验收规范不统一，而不是 Runtime 校验整体过严：

1. Engineer Prompt 和结构 Schema 没有完整表达 Runtime 后续使用的规则。
2. 模型输出可以通过上游 Contract，却在 Packager 或 Runtime 中因另一套隐藏规则失败。
3. Runtime 把“当前 Adapter 无法预览”与“项目源码生成失败”混成同一种失败。
4. 部分 Web 形态规则被当成全局源码规则，反向限制了通用项目生成。

因此，不应通过全面放松 Runtime 或固定代码模板来追求通过率。正确方向是建立同一个 Runtime Contract 作为 Engineer、确定性预检、Runtime Adapter 和 UI 共同使用的 Interface：Engineer 在生成前看到完整规则，预检按相同规则提前发现确定性错误，Runtime Adapter 只负责真实构建和执行，UI 根据同一结果语义展示可预览、仅源码可用或禁止执行。

这里采用 `Runtime Contract` 而不是 `AdapterContract`：Contract 是位于通用 SourceBundle 与运行能力 seam 上的 Interface；具体 Web、Python 或其他 Runtime Adapter 是满足该 Interface 的实现。通用 SourceBundle 本身不服从任何单一 Adapter 的代码形态。

### Runtime 校验的保留、收敛与降级

Runtime 应对安全、源码完整性和真实执行结果保持严格，但不能对任意项目施加未声明的 Web 形态限制。

必须继续阻断的项目包括：

- 路径逃逸、越权文件写入、危险执行权限和 Sandbox 违规。
- 文件清单、入口、基线 Hash 或可确定性解析的受控引用不完整。
- 选择了某个 Runtime Adapter 后，不满足该 Adapter 已公开声明的必要输入。
- 实际 Build/Test 失败，且这些检查属于当前项目明确声明的验收条件。

必须改为 Adapter 专属、不能继续作为全局规则的项目包括：

- 是否允许完整 `DOCTYPE/html/head/body` 文档。
- 是否接收 HTML Fragment、完整 Document 或框架构建产物。
- 是否允许内联 `<script>`、如何声明依赖和使用什么入口。
- 是否必须存在 `index.html`、`styles.css` 或 `app.js`。

应降级为 Warning 或能力状态的项目包括：

- 当前没有匹配的 Preview Adapter。
- 代码风格、可选 README、非验收条件的辅助测试和非阻断质量建议。
- 源码有效但当前部署环境缺少对应工具链。

### 结果语义必须拆开

Runtime 和 Project 状态不应继续只有“成功/失败”两种结果。至少需要区分：

1. `valid`：源码与已选择的 Runtime Adapter 均通过，可以生成版本并提供对应运行能力。
2. `source_ready`：源码、文档和版本有效，但没有匹配 Adapter 或当前环境无法在线运行；不提供 Preview，不判定项目失败。
3. `candidate_rejected`：本次候选的 Contract、Build 或 Test 未通过；保留最后可用版本和完整证据。
4. `execution_blocked`：候选包含安全或权限问题，禁止执行；不得将其提升为可运行版本。

Preview 是某个 Runtime Adapter 提供的能力，不是源码交付成立的前提。Preview 失败不能覆盖已经存在的可用 ProjectVersion，也不能把非 Web 项目改写为 Web 项目。

### 90% 是质量目标，不是设计限制

Engineer 候选一次通过率达到 90% 以上仍是 V1 的质量目标，但它只能用于衡量统一规范后的实际结果，不能参与决定产品支持哪些代码形态。

明确禁止为了提高该指标而采取以下做法：

- 缩小任意代码的产品范围，或在失败后把项目归为“不支持”以减少分母。
- 强制模型使用少量固定模板、固定 HTML 外壳或固定文件名。
- 放松安全、完整性、Build/Test 等必要门禁。
- 把 Repair 后成功计入首次通过，或隐藏 Provider、解析和 Runtime 内部错误。

通过率应按项目类型和 Runtime Contract 分组统计；能力识别必须在进入 Engineer 前完成并单独留痕。没有 Runtime Adapter 的项目以 `source_ready` 交付，不进入对应 Preview 通过率，但必须进入通用 Source Contract 成功率统计。90% 是否达到只能由真实有效 Run 证明，不能通过修改产品定义实现。

### 修订后的处理要求

1. 定义通用 Source Contract，允许表达任意目录、文件、项目类型、入口、依赖、测试和可选 Runtime 绑定；不得由 HTML/CSS/JavaScript 三字段反向定义源码。
2. 定义版本化 Runtime Contract，并由 Engineer Prompt、确定性预检、Runtime Adapter 和 UI 共同读取，禁止各模块维护隐含且不一致的规则副本。
3. `web-static-v1` 必须明确声明自己接收完整 HTML Document、HTML Fragment 或构建产物中的哪一种；若兼容多种模式，必须使用显式字段区分，不能继续复用含义模糊的 `html` 字段。
4. Runtime Adapter 在隔离候选工作区消费源码，不得为了 Preview 修改 Repository 中的权威源码；候选通过后再原子生成 ProjectVersion。
5. 将校验结果映射为 `valid`、`source_ready`、`candidate_rejected` 和 `execution_blocked`，并分别验证版本保留、错误证据和 UI 状态。
6. 建立按项目类型与 Runtime Contract 分组的真实回归集，在不缩窄产品范围、不放松必要校验的前提下评估一次通过率。

上述 Interface 和状态转换进入对应 V1 技术设计前，不应按 2026-07-15 Update 中“固定 Runtime 管理外壳”的通用方案开始实现。本 Review 继续保持`待办`。

## 2026-07-16 Update：正式技术设计已建立

长期方案已经写入[通用源码与 Runtime 校验 Contract](../../design/V1/技术设计/12-[工程][TODO]-通用源码与Runtime校验Contract.md)，并在 Agent 设计、系统架构和共享独立执行服务设计中建立职责链接。正式设计确认：

- SourceBundle 是任意文本项目源码的权威产物，AppSpec 三段网页源码只保留历史兼容；
- Runtime Contract 是 Engineer、预检、Runtime Adapter 与 UI 共同使用的唯一 Interface；
- Web Fragment 与完整 Document 使用不同 Contract 标识，不再通过隐式 HTML 包装猜测；
- `source_ready` 与 Runtime 执行失败分开，没有 Adapter 不等于源码交付失败；
- 90% 只作为分组观测的首次候选质量目标，不参与缩小项目范围或放松强制门禁。

本次只完成设计落库，尚无代码、自动化测试或部署证据，因此本 Review 继续保持`待办`。

## 2026-07-16 Update：第一版实现与本地验证完成

对应技术设计已经完成第一版实现，主要代码证据包括：

- `another_atom/contracts/schemas.py`：SourceBundle 2.0、Runtime Contract、能力与结果状态；
- `another_atom/runtime/contracts.py`：版本注册表、内容指纹、通用 Source 校验与共享 Runtime 预检；
- `another_atom/agent/provider.py`、`another_atom/agent/orchestrator.py`：Engineer 生成前读取 Contract，区分 Runtime-bound 与 Source-only 交付；
- `another_atom/executor/runner.py`：按绑定 Contract 执行固定计划，并区分候选拒绝与安全阻断；
- `another_atom/repository/service.py`、`another_atom/runtime/artifacts.py`：权威 SourceBundle 物化、受控 Patch、版本提交和 Restore；
- `studio/src/components/PreviewApp.tsx`、`studio/src/App.tsx`：权威 Document Preview 与能力边界展示。

本地验证结果：完整 `pytest` 套件通过，`ruff check another_atom tests` 通过，Studio 的 TypeScript/Vite 生产构建通过。回归已覆盖完整 Document 不触发 Runtime-managed shell 错误、无 Adapter 项目形成 `source_ready`、非 Web 项目不生成伪 HTML、回环地址在执行前阻断、Source-only 和 Web 项目增量修改、结构化编辑与 Restore 重新校验、候选失败不覆盖已有版本。

尚缺 Railway 部署验收、公开 URL 证据及 90% 分组指标的真实样本统计。长期设计中的观测和部署完成条件仍未满足，因此本 Review 继续保持`待办`，不归档。
