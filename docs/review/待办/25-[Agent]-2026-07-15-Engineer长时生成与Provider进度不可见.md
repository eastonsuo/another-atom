# Engineer 长时生成与 Provider 进度不可见

[toc]

> 类型：Agent 检查｜状态：待办｜日期：2026-07-15｜版本范围：V1｜代码基线：`f630481`｜运行证据：Run `c2e5f393-217f-407b-8577-4dd3158b0af2`

- **Agent 设计：** [V1 多 Agent 设计](../../design/V1/技术设计/01-[Agent]-多Agent设计.md)
- **相关检查：** [Engineer 项目源码 Contract 缺口](./22-[工程]-2026-07-14-Engineer项目源码Contract缺口.md)

## 背景

用户在产品说明确认后启动构建，Product Manager 和 Architect 均正常完成，但 Engineer 长时间停留在第一次模型请求。调试日志生成于 `2026-07-14T16:01:25.137397+00:00`；此时 Run 状态仍为 `engineer_running`，没有错误，也没有 Provider 切换、首 Token、输出接收或校验进度。

本 Review 只检查长等待的成因、可观察性和恢复风险，不据此判断该 Run 最终是否成功，也不在本文中确定具体超时秒数。

## 摘要

- **[P0｜真实 Provider 状态不可见]** `provider.fallback` 只在整个模型调用成功返回后补记。用户无法判断当前仍在主 Provider、已经切换备用 Provider，还是连接已经停滞。
- **[P0｜调用总时限可能超过 Worker lease]** 主 Provider、备用 Provider、结构修正和外层阶段重试分别拥有独立次数或超时，最坏时间会叠加；Worker lease 只在领取任务时设置，模型调用期间没有续租证据。
- **[P1｜Engineer 单次输出过重]** 当前 Engineer 在一次非流式请求中返回完整 `AppSpec`，包含 HTML、CSS、JavaScript 和元数据；相比 PM 与 Architect，它的输出规模和结构化校验成本显著更高。
- **[P1｜慢与“像卡死”是两个问题]** 流式接收可以暴露首 Token、持续生成和停滞状态，但不会自动减少总生成量；语义分批可以形成检查点、局部重试和并行生成，但必须先解决 Provider 路由、总时限和共享 Contract。

## 运行证据

本次日志中的阶段耗时为：

1. Product Manager 从 `agent.attempt.started` 到 `agent.output.validated` 约 `15.6` 秒。
2. 产品说明等待用户确认约 `158.7` 秒；这段时间不是模型执行耗时。
3. Architect 从 `agent.attempt.started` 到 `agent.output.validated` 约 `9.2` 秒。
4. Engineer 于 `15:58:04.279553+00:00` 开始第一次模型请求；截至日志生成时已等待约 `200.9` 秒，仍只有 `agent.attempt.started`。
5. Build Job lease 从 `15:57:55.062316+00:00` 持续到 `16:07:55.062316+00:00`，共 600 秒。

因此，慢点明确集中在 Engineer 模型调用，不是 PM、Architect 或队列调度的普遍延迟。

## 实现证据

1. [`config.py`](../../../another_atom/config.py) 默认配置 `OLLAMA_TIMEOUT_SECONDS=300`、`OLLAMA_FAILOVER_TIMEOUT_SECONDS=30`、`WORKER_LEASE_SECONDS=600`。
2. [`provider.py`](../../../another_atom/agent/provider.py) 在配置 DeepSeek fallback 时把 Ollama 主调用限制为 failover timeout；主调用超时后，DeepSeek 调用仍可使用完整 Provider timeout。
3. DeepSeek 请求使用 `stream: false`、`max_tokens: 8192`。完整响应返回前，没有首 Token、累计输出或停滞信号。
4. `create_app_spec` 要求 Engineer 一次返回完整自包含 Web `AppSpec`；[`schemas.py`](../../../another_atom/contracts/schemas.py) 允许 HTML、CSS、JavaScript 各最多 40,000 字符。
5. [`orchestrator.py`](../../../another_atom/agent/orchestrator.py) 在 `operation()` 成功返回后才读取 `fallback_provider` 并写入 `provider.fallback`，所以切换发生时用户看不到事件。
6. [`worker.py`](../../../another_atom/build/worker.py) 在领取 Build Job 时一次性设置 lease；当前模型调用路径没有持续续租或共享阶段 deadline。

## 能确认与不能确认的结论

### 能确认

- Engineer 的单次生成边界显著大于 PM 和 Architect。
- 当前前端与调试日志不能展示 Provider 调用内部状态。
- 现有超时、结构修正和阶段重试不是一个共享时间预算。
- 现状偏离 [V1 多 Agent 设计](../../design/V1/技术设计/01-[Agent]-多Agent设计.md) 已确定的两项要求：Provider 超时与 fallback 必须即时写事件；同一模型阶段必须使用共享总时限。

### 不能确认

- 调试日志没有 Provider 请求开始、首 Token、timeout 和 fallback 开始时间，因此不能证明这 200.9 秒具体消耗在 Ollama、DeepSeek、网络连接还是模型生成。
- 日志是运行中的快照，不能判断该 Run 后续是否完成、超时或被重复领取。
- 没有首 Token 延迟、输出 Token 速度和 Provider 响应头，不能据此确定合理的固定超时秒数。

## 影响

- 用户只能看到不断增加的等待时间，无法判断是否应继续等待或重试。
- 运维日志也无法区分 Provider 慢、fallback 慢、结构修正和 Worker 停滞，排障依赖推测。
- 如果 Provider 调用与结构修正超过 lease，另一个 Worker 可能重新领取同一 Build Job，造成重复模型调用、重复配额结算或竞争写入。
- 完整 `AppSpec` 任一部分校验失败时可能需要重新生成整份结果，放大延迟和重试成本。

## 后续处理要求

按以下顺序处理，不能只通过修改等待文案掩盖问题：

1. **Provider 生命周期事件：** 主 Provider 请求开始、超时、fallback 开始、首 Token、响应接收完成和 Contract 修正必须在发生时写入持久化事件。
2. **Provider 路由：** 模型与 Provider 的选择关系必须明确；对已确认不可用或处于熔断期的主 Provider，不应让每个批次重复等待同一 failover timeout。
3. **共享阶段时限与 lease：** 主调用、fallback、结构修正共同消耗一个阶段 deadline；长调用期间续租，且恢复路径证明同一阶段不会被重复执行。
4. **批内流式：** 服务端可以流式接收模型输出并限频上报进度，但前端不直接展示未完成 JSON 或代码；完整输出仍在流结束后统一校验。
5. **语义分批评估：** Engineer 可按 `Plan/HTML/CSS/JavaScript/Assemble/Validate` 建立显式批次；CSS 与 JavaScript 仅在共享 DOM/交互 Contract 确立后并行，失败只重试受影响批次。
6. **生成边界合并处理：** 语义分批应与 [Review 22](./22-[工程]-2026-07-14-Engineer项目源码Contract缺口.md) 的 `SourceBundle` 迁移协调，避免先为旧三字符串 `AppSpec` 建一套临时批次协议，再重复迁移通用源码 Contract。

## 验收标准

1. 调试日志可以按真实发生顺序看到主 Provider 请求、timeout、fallback、响应完成和 Contract 校验，不再等调用结束后补记 fallback。
2. 用户界面能区分“等待首 Token”“持续生成”“Provider 切换”“解析校验”和“保存产物”，刷新后事件仍可重放。
3. 同一模型阶段只有一个共享 deadline；实际调用期间 lease 不失效，自动化测试证明过期恢复不会并发重复执行。
4. Trace 至少记录 Provider、首 Token 延迟、总耗时、输入/输出 Token 和失败类型，但不暴露 Chain of Thought。
5. 若采用语义分批，每批都有独立 Artifact 或等价检查点、输入指纹和局部重试证据；最终组装仍通过完整 Contract 与 Runtime Validator。
6. 部署环境完成一次真实长输出验收，能够从日志确认生成期间持续有进度，且不会重复扣费或重复生成。

在上述实现与部署验证完成前，本 Review 保持“待办”。

## Update（2026-07-15）

已完成本地实现与自动化验证：

1. [`provider.py`](../../../another_atom/agent/provider.py) 在请求开始、首个返回片段、持续生成、超时、fallback 启动、响应完成和 Contract 修正发生时立即上报事件；Engineer 的 Ollama 与 DeepSeek 调用改为服务端流式接收，完整内容仍在内存中组装完成后统一执行 Contract 校验，未把半成品 JSON 或代码暴露给前端。
2. [`orchestrator.py`](../../../another_atom/agent/orchestrator.py) 在 Agent 阶段开始时绑定持久化事件处理器，并让同一阶段的主 Provider、fallback、结构修正和外层重试共同消耗 `AGENT_STAGE_TIMEOUT_SECONDS`；事件写入后立即提交，可由 SSE 和刷新后的历史记录重放。
3. [`provider.py`](../../../another_atom/agent/provider.py) 在 Ollama 超时后打开主 Provider 熔断窗口；窗口内的后续调用直接进入 DeepSeek，不再重复等待 Ollama failover timeout。
4. [`worker.py`](../../../another_atom/build/worker.py) 在 Build Job 执行期间使用独立数据库 Session 定时续租；续租更新同时校验 Job ID、当前 lease owner 和运行状态，旧 Worker 不能续写新 Worker 的 lease。
5. [`App.tsx`](../../../studio/src/App.tsx) 已订阅并展示上述 Provider 生命周期事件；等待时间以当前 Provider 请求开始事件为锚点，不再被周期性进度事件重置。
6. 新增测试覆盖 Ollama 流式组装后校验、Ollama 超时后的 DeepSeek 流式回退、熔断期跳过主 Provider、共享阶段时限阻止新请求、Provider 事件持久化重放，以及只有当前 Worker 能续租。全量结果为 `136 tests collected` 且全部通过；`ruff check another_atom tests` 与 Studio `npm run build` 通过。

本次没有为旧 `AppSpec` 增加临时语义分批协议。`Plan/HTML/CSS/JavaScript/Assemble/Validate` 分批仍与 [Review 22](./22-[工程]-2026-07-14-Engineer项目源码Contract缺口.md) 的 `SourceBundle` 迁移一起处理，避免重复建设两套生成 Contract。

尚未完成的是部署环境真实长输出验收，以及对重复扣费/重复生成的部署证据采集。因此本 Review 继续保持“待办”。
