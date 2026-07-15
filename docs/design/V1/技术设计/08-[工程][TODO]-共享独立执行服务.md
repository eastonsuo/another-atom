# Another Atom V1 共享独立执行服务

[toc]

- 文档状态：V1 局部实现；本地代码与关键自动化验证已完成，Railway 部署验收及完整故障测试尚未完成
- 更新日期：2026-07-15
- 决策来源：[第二十三号评审：多角色职责与交付边界检查](../../../review/待办/23-[综合]-2026-07-14-多角色职责与交付边界检查.md)
- 智能体设计：[Another Atom V1 多智能体设计](./01-[Agent]-多Agent设计.md)
- 系统架构：[Another Atom V1 系统架构](./03-[工程]-系统架构.md)
- 部署设计：[Another Atom V1 运行与部署](./04-[工程]-运行与部署.md)
- Contract 设计：[Another Atom V1 通用源码与 Runtime 校验 Contract](./12-[工程][TODO]-通用源码与Runtime校验Contract.md)

> **2026-07-15 实现更新：** 已增加独立执行服务入口 `another_atom.executor.app:app`、非 root 的 `Dockerfile.executor`、`railway.executor.toml`、共享执行契约、主服务调用客户端和 `web-static-v1` 运行器。新构建会在执行服务临时目录物化源码，固定执行 `node --check app.js` 与 `node --test tests/*.test.js`，再运行确定性校验；主服务校验请求和返回指纹后保存源码包（SourceBundle）、构建产物（BuildArtifact）、执行报告（ExecutionReport）和校验报告（ValidationReport）。私有接口已经实现持有者令牌（Bearer）认证、时间戳、正文指纹、逐行 JSON（NDJSON）流式事件、全局单并发、重复执行保护、总截止时间和取消信号。本地自动化已覆盖成功链路、架构边界退回产品规格、私有 HTTP 契约、执行截止时间和取消信号；Railway 私网部署、服务中断、经 HTTP 取消运行中任务和多用户压力验收仍未完成，因此本文继续保持 `[TODO]`。

## 背景

本设计实施前，构建工作器（Build Worker）与主服务运行在同一进程，所谓“构建”实际只调用 `validate_app_spec()` 完成静态源码检查，没有执行工程师（Engineer）交付的真实构建命令和单元测试，也没有生成执行报告（ExecutionReport）。第二十三号评审据此确定：工程师负责交付源码与单元测试，运行系统（Runtime）负责真实执行，模型不能自报通过。

本设计把运行期工程验证从主服务迁到 Railway 同一项目、同一环境中的共享独立执行服务（Runtime Executor）。所有用户共用一个执行服务和一条受控队列，主服务与执行服务不共享进程、持久化卷、数据库凭据或模型密钥。该方案提供服务级隔离，不提供每用户或每任务的独立容器；因此 V1 只允许已登记的受限网页运行时适配器（Web Runtime Adapter），不扩大为公网多租户任意代码执行。

## 摘要

- **部署拓扑**
  - Railway 同一项目、同一环境部署主服务（Control Plane）和共享执行服务（Runtime Executor），两者只通过 Railway 私有网络通信；执行服务不创建公网域名。
- **职责边界**
  - 源码物化、固定构建、单元测试和确定性工程校验全部在执行服务完成；主服务保留身份、用户归属、审批、配额、任务状态、产物持久化、版本和发布门禁。
- **共享方式**
  - 所有用户共享一个无状态执行服务，V1 全局并发为一；主服务负责排队和每用户并发限制，执行服务不读取用户数据库，也不保存用户源码。
- **执行契约**
  - 主服务发送交付规格、源码包（SourceBundle）、Runtime Contract 标识/版本/指纹和上游指纹；执行服务校验同一 Contract 后流式返回阶段事件，最终返回构建产物（BuildArtifact）、执行报告（ExecutionReport）和校验报告（ValidationReport）。现有 AppSpec 与固定适配器字段属于迁移兼容。
- **安全边界**
  - 适配器命令固化在执行服务镜像中，模型和用户不能提交命令、安装依赖或获得终端。Railway 非特权服务不能提供任务级嵌套容器，因此该方案不能声称具备任意不可信代码的强沙箱能力。
- **迁移边界**
  - 第一阶段只实现 `web-static-v1`；其他项目类型仍可交付源码，但在没有匹配适配器时必须显示能力缺口，不能被改写成网页项目。

Runtime Executor 的部署、认证、并发、临时目录和资源限制继续以本文为事实来源；SourceBundle 与 Runtime Adapter 之间的 Interface、校验职责和 `valid/source_ready/candidate_rejected/execution_blocked` 结果语义以[通用源码与 Runtime 校验 Contract](./12-[工程][TODO]-通用源码与Runtime校验Contract.md)为事实来源。执行服务不得维护另一份未暴露给 Engineer 和确定性预检的项目形态规则。

## 1. 设计结论

方案可行，但“与主服务隔离”的准确含义是：

- 主服务和执行服务使用不同 Railway 服务实例、进程、镜像职责和资源限制；
- 执行服务不挂载主服务的 SQLite/Project Git 持久化卷；
- 执行服务不持有数据库、模型服务（Provider）、Git 远端、发布或用户会话密钥；
- 执行服务只接受主服务通过私有网络发起的受认证请求；
- 用户代码只存在于单次任务临时目录，结果返回后立即清理；
- 所有用户共享同一个执行服务、同一工具链和同一全局并发上限。

它不表示：

- 每个用户拥有独立 Railway 环境；
- 每个任务拥有独立容器、虚拟机、网络命名空间或内核；
- 执行服务可以安全运行任意 Shell、动态依赖、后端服务或原生工具链；
- Railway 私有网络等同于任务级禁止出网。

V1 不使用单独 Railway 环境承载执行服务。Railway 私有网络只覆盖同一项目、同一环境；跨环境调用需要公网入口，会增加认证、延迟和攻击面。执行服务应与主服务位于同一环境，但作为独立服务部署。

## 2. 服务拓扑

```text
Railway 项目 / 生产环境

浏览器（Browser）
   |
   | HTTPS / SSE
   v
+--------------------------------------------------+
| 主服务（Control Plane）                          |
|                                                  |
| 认证 / 项目 / 智能体 / 审批 / 配额                 |
| 构建任务队列 / 阶段产物 / 版本 / 发布               |
| SQLite + 项目 Git 持久化卷                        |
+-------------------------+------------------------+
                          |
                          | 私有 HTTP
                          | runtime-executor.railway.internal
                          v
+--------------------------------------------------+
| 共享执行服务（Runtime Executor）                 |
|                                                  |
| 请求校验 / 源码物化                              |
| 固定构建 / 固定测试 / 校验器                     |
| 临时工作目录 / 有界日志                          |
| 无公网域名 / 无持久化卷                          |
+--------------------------------------------------+
```

Railway 环境隔离用于生产、预发布和拉取请求环境，不用于为每个用户任务创建执行沙箱。正式部署依据：

- [Railway 环境（Environments）](https://docs.railway.com/environments)
- [Railway 私有网络工作方式（Private Networking）](https://docs.railway.com/networking/private-networking/how-it-works)
- [Railway 非特权容器限制](https://docs.railway.com/guides/github-actions-runners)
- [Railway 副本资源限制（Resource Limits）](https://docs.railway.com/pricing/cost-control)

## 3. 职责边界

### 3.1 主服务（Control Plane）

主服务继续拥有业务事实和最终控制权：

- 登录身份、用户与项目归属；
- 产品规格（ProductSpec）确认、审批和能力边界；
- 智能体编排、模型调用和配额结算；
- 构建任务（BuildJob）排队、租约、取消和恢复；
- 应用规格（AppSpec）、源码包（SourceBundle）及上游指纹的持久化；
- 执行结果的模式校验、请求指纹匹配和来源认证；
- 执行报告、校验报告、构建产物、项目版本（ProjectVersion）和发布状态持久化；
- 只有全部强制检查通过后才创建版本和预览。

主服务不得：

- 在自身进程中执行用户项目的构建或单元测试；
- 把数据库连接、模型密钥或发布密钥发送给执行服务；
- 接受模型自报的构建、测试或校验结果；
- 在执行服务失败时伪造降级通过结果。

### 3.2 共享执行服务（Runtime Executor）

执行服务集中承担所有运行期工程验证：

- 再次校验请求模式、体积、内容指纹和适配器标识；
- 校验源码路径、文件角色、文件数量和单文件大小；
- 在任务临时目录物化源码包；
- 执行适配器中预先登记的固定构建命令；
- 执行工程师交付的单元测试；
- 执行源码完整性、网络边界、产品验收映射和架构交接等确定性检查；
- 生成构建产物、执行报告和校验报告；
- 发送阶段事件并在任务结束后清理工作目录。

执行服务不得：

- 读取主服务数据库、Project Git Volume 或其他用户目录；
- 调用模型服务、修改产品规格或架构设计；
- 创建项目版本、Git commit 或发布；
- 接受请求中的 Shell 命令、包管理命令或任意镜像名称；
- 在本地持久化用户源码、报告或构建产物。

### 3.3 “所有验证都在执行服务”的边界

迁移到执行服务的是运行期工程验证，包括源码检查、构建、单元测试和确定性校验器（Validator）。以下边界校验仍必须留在主服务：

- 用户身份与项目归属；
- 用户是否批准当前产品规格指纹；
- 当前运行是否允许进入工程阶段；
- 配额、取消和并发状态；
- 返回报告是否来自已配置执行服务；
- 返回的 `execution_id`、`request_hash`、`source_manifest_hash` 和上游指纹是否匹配当前任务。

这些不是重复执行工程校验，而是防止执行服务或网络返回结果越权影响主服务状态。

## 4. 多用户共享与隔离

### 4.1 共享模型

V1 所有用户共享：

- 一个执行服务部署；
- 一个固定工具链镜像；
- 一个运行时适配器注册表；
- 一个全局执行槽位；
- 同一套资源、日志和超时上限。

主服务仍按用户保存构建任务。执行服务只接收不透明的 `execution_id`、`run_id` 和内容指纹，不需要接收用户名、邮箱、Cookie 或用户密钥。

### 4.2 排队与公平性

V1 初始约束：

- `MAX_CONCURRENT_EXECUTIONS=1`；
- 同一用户同时最多一个运行中任务；
- 同一运行同时最多一个有效执行尝试；
- 主服务在用户之间轮转调度（round-robin）：先选择最久未获得执行权且存在排队任务的用户，再执行该用户最早的任务；派发时间必须持久化，不能只保存在工作器内存中；
- 用户界面展示排队、构建、测试、校验和取消状态，不承诺缺少数据依据的预计完成时间。

执行服务不维护第二套持久化队列。主服务的 `build_jobs` 是唯一任务事实源，执行服务只处理已经被主服务工作器领取的请求。

### 4.3 临时目录隔离

每次执行使用独立目录：

```text
/tmp/another-atom-executor/{execution_id}/
├── source/
├── dist/
├── logs/
└── result/
```

规则：

- `execution_id` 只由主服务生成，不能直接作为未经校验的绝对路径；
- 目标路径必须在任务根目录内，拒绝绝对路径、`..`、符号链接和路径穿越；
- 执行进程使用非 root 用户，清空继承环境，只注入适配器明确允许的变量；
- 启动时清理超过任务期限的遗留目录；
- 成功、失败、取消和超时都执行清理；
- 日志不得记录完整源码、认证头或请求正文。

由于所有任务仍运行在同一个 Railway 服务容器中，这一目录边界不是内核级多租户隔离。V1 通过全局单并发、无持久化卷、无业务密钥和固定受限适配器降低风险；不能据此开放任意代码执行。

## 5. 内部执行接口

### 5.1 接口选择

V1 使用主服务工作器发起的同步流式私有 HTTP 请求，不在执行服务中新增消息队列或数据库：

```text
POST /v1/executions
Authorization: Bearer <EXECUTOR_SHARED_TOKEN>
X-Request-Timestamp: <UTC timestamp>
X-Content-SHA256: <request body hash>
Content-Type: application/json
Accept: application/x-ndjson
```

执行服务通过换行分隔 JSON（NDJSON）依次返回阶段事件和唯一终态结果。浏览器不直接访问该接口；主服务收到事件后先持久化，再通过现有服务端事件流（SSE）发送给用户。

辅助接口：

```text
GET  /health
POST /v1/executions/{execution_id}/cancel
```

执行服务不配置 Railway 公网域名。共享令牌仍是必需的，因为私有网络解决传输可达性，不替代服务身份认证。

执行服务必须重新计算请求体 SHA-256，使用常数时间方式校验服务令牌，并拒绝超出配置时钟偏差的时间戳。同一 `execution_id` 在执行服务进程内只能有一个活动请求；重复派发返回冲突，不并行启动第二个进程。执行服务重启后不尝试恢复旧任务，由主服务依据租约和新的执行尝试号决定是否全量重跑。

### 5.2 执行请求（ExecutionRequest）

| 字段 | 类型与硬约束 | 中文语义 |
| --- | --- | --- |
| `schema_version` | 固定 `"1.0"` | 内部执行接口版本 |
| `execution_id` | UUID | 本次执行尝试的唯一标识 |
| `run_id` | UUID | 对应主服务运行，仅用于追踪 |
| `attempt` | `int >= 1` | 执行尝试序号 |
| `adapter_id` | 已登记字符串 | 固定运行时适配器标识 |
| `request_hash` | 64 位十六进制 | 除自身外请求内容的确定性指纹 |
| `product_spec_hash` | 64 位十六进制 | 已批准产品规格指纹 |
| `architecture_design_hash` | 64 位十六进制 | 当前架构设计指纹 |
| `source_manifest_hash` | 64 位十六进制 | 源码包清单指纹 |
| `app_spec` | 应用规格对象 | 项目类型、入口、测试入口和适配器边界 |
| `source_bundle` | 源码包对象 | 源码、单元测试和受控配置 |
| `acceptance_criteria` | 有上限字符串列表 | 需要确定性映射的产品验收条件 |
| `deadline_ms` | 受配置上下限约束 | 整次执行剩余总时限，不由模型决定 |

请求中不包含用户 Cookie、密码、模型密钥、数据库地址、Git 凭据或发布凭据。请求大小、文件数、单文件大小和日志大小的具体上限需要根据真实生成物分布确定，当前不能无依据写死；实现前必须作为服务配置提供，并在部署验收中记录最终值。

### 5.3 阶段事件（ExecutionEvent）

```json
{
  "schema_version": "1.0",
  "execution_id": "...",
  "sequence": 3,
  "type": "test.completed",
  "timestamp": "...",
  "payload": {
    "status": "passed",
    "duration_ms": 1200
  }
}
```

允许的核心事件：

```text
execution.accepted
source.materializing
source.materialized
build.started
build.completed
test.started
test.completed
validation.started
validation.completed
execution.completed
execution.failed
execution.cancelled
```

事件只包含状态、耗时、计数、错误类别和证据引用，不发送完整源码或无限原始日志。

### 5.4 执行结果（ExecutionResult）

| 字段 | 中文语义 |
| --- | --- |
| `schema_version` | 结果契约版本 |
| `execution_id` | 对应的执行尝试 |
| `request_hash` | 被执行请求的指纹 |
| `adapter_id` | 实际使用的适配器 |
| `source_manifest_hash` | 被执行源码包的指纹 |
| `build_artifact` | 有界构建产物文件和清单指纹；失败时为空 |
| `execution_report` | 构建与测试的不可变执行证据 |
| `validation_report` | 确定性检查结果 |

主服务必须重新用 Pydantic 校验结果，并逐项比较请求与响应指纹。任一指纹、执行标识或模式不匹配时，结果按 `EXECUTOR_RESULT_INVALID` 失败处理，不能创建项目版本。

第一阶段 `web-static-v1` 的构建产物（BuildArtifact）只允许 UTF-8 文本文件。终态结果中的每个产物文件至少包含受控相对路径、字节数、SHA-256 和 UTF-8 内容；二进制文件、非法路径或超过响应上限的产物直接失败。主服务接收后重新计算文件和总清单指纹，只持久化验证通过的文件。后续如需支持二进制或大产物，再引入对象存储和短时上传凭据；不在本接口中无上限内联传输。

## 6. 运行时适配器

### 6.1 适配器注册表

适配器只能由执行服务镜像内的代码注册：

```text
adapter_id
supported_project_types
allowed_paths
allowed_file_roles
materialize_handler
build_command
test_command
validation_profile
preview_support
resource_profile
```

`build_command` 和 `test_command` 不能从应用规格、源码包、提示词或测试配置读取。测试配置只能表达适配器允许的测试文件范围和数据，不能定义命令、插件、依赖或环境变量。

### 6.2 第一阶段：`web-static-v1`

第一阶段只实现受限静态网页项目：

- 工具链基于仓库当前 Node.js 22 基线，并固定在执行服务 Dockerfile；
- 接受 `index.html`、`styles.css`、`app.js`、受控 `src/**/*.js`、`tests/**/*.test.js`、`app-spec.json` 和适配器允许的测试配置；
- 不接受 `package.json` 脚本、lockfile 修改、`npm install`、动态依赖或远程可执行资源；
- 构建阶段执行 JavaScript 语法检查和固定静态站点打包，产出受控 `dist/`；
- 测试阶段使用镜像预装的固定 Node.js 测试运行器执行 `tests/**/*.test.js`；
- 校验阶段检查路径、源码完整性、危险浏览器能力、网络边界、入口文件、产品验收映射、架构交接和测试真实结果；
- 预览继续使用当前无同源 iframe 与内容安全策略（CSP）边界。

工程师必须把可独立测试的逻辑放入允许的源码模块。页面渲染结果和浏览器交互不能仅凭 Node.js 单元测试判定通过，仍需要平台的结构化检查和预览验收。

### 6.3 暂不支持

本设计不直接开放：

- 用户或模型提供的 Shell 命令；
- 动态安装 npm、pip、系统包或原生依赖；
- 任意后端服务、数据库迁移和长驻进程；
- 原生移动端、桌面端和系统级工具链；
- Docker-in-Docker 或请求指定容器镜像；
- 需要强任务级网络隔离的代码。

缺少适配器时返回 `ADAPTER_UNSUPPORTED`，由主服务展示能力缺口。它不是工程师修改源码可以解决的失败。

## 7. 构建、测试与校验顺序

```text
主服务领取 BuildJob
        |
        v
校验用户归属、批准状态和上游指纹
        |
        v
调用共享执行服务
        |
        v
请求认证 / 请求 hash / Adapter 检查
        |
        v
创建临时目录并物化 SourceBundle
        |
        v
静态执行前检查
        |
        v
固定构建（Build）
        |
        +-- 失败 -> ExecutionReport(build=failed) -> 返回主服务
        |
        v
固定单元测试（Unit Test）
        |
        +-- 失败 -> ExecutionReport(test=failed) -> 返回主服务
        |
        v
确定性校验器（Validator）
        |
        v
构建产物（BuildArtifact）+ 执行报告（ExecutionReport）+ 校验报告（ValidationReport）
        |
        v
主服务校验响应和指纹
        |
        +-- 全部 mandatory pass -> ProjectVersion / Preview
        |
        `-- source_or_test + resolvable -> Engineer 修复一次 -> 全量重跑
```

执行顺序不能调整为“先创建版本，再异步补测试”。构建、测试和校验必须绑定同一 `source_manifest_hash`；源码发生任何变化，旧构建产物和报告立即失效。

## 8. 状态、持久化与恢复

### 8.1 构建任务状态

`BuildStatus` 目标状态调整为：

```text
queued
-> dispatching
-> materializing
-> building
-> testing
-> validating
-> succeeded | failed | cancelled | waiting_input
```

`build_jobs` 至少增加：

```text
execution_id
execution_attempt
adapter_id
dispatched_at
request_hash
source_manifest_hash
architecture_design_hash
executor_status
last_event_sequence
execution_report_artifact_id
validation_report_artifact_id
build_artifact_id
```

字段名必须以最终数据库迁移和 Pydantic 契约为准；不在 JSON 日志或事件中另建一套不可查询的状态事实源。

### 8.2 无状态执行服务

执行服务不保存任务数据库。主服务工作器持有任务租约并消费执行事件：

- 最终结果只有在主服务事务提交后才算成功；
- 执行服务重启或连接中断时，本次尝试标记为 `EXECUTOR_LOST`；
- 尚无最终报告的任务可以由主服务创建新执行尝试并完整重跑一次；
- 已提交执行报告、校验报告和项目版本的任务不得重复运行；
- 外部执行不是严格恰好一次（exactly-once），但数据库产物和项目版本必须幂等；
- 执行服务不通过缓存伪装已完成结果。

### 8.3 取消

尚未派发的排队任务由主服务直接取消并释放预占配额，不调用执行服务。已派发任务的取消顺序为：

1. 主服务先把任务标记为取消中；
2. 调用执行服务取消接口；
3. 执行服务终止当前进程组并清理目录；
4. 返回 `execution.cancelled`；
5. 主服务释放租约和未使用配额，不创建版本。

取消请求超时不能被当成任务已经停止。主服务必须等待执行连接结束或租约到期后再允许同一运行重新执行。

## 9. 失败归属与工程修复

| 错误类别 | 所有者 | 是否进入工程师修复 |
| --- | --- | --- |
| `REQUEST_INVALID` | 主服务/契约实现 | 否 |
| `ADAPTER_UNSUPPORTED` | 平台能力边界 | 否，进入需要输入（Needs input） |
| `SOURCE_INVALID` | 工程师源码或测试 | 是，最多一次 |
| `BUILD_FAILED` | 工程师源码 | 是，最多一次 |
| `TEST_FAILED` | 工程师源码或测试 | 是，最多一次 |
| `VALIDATION_FAILED` | 按检查项根因判断 | 只有 `source_or_test + resolvable` 可以 |
| `BUILD_TIMEOUT` / `TEST_TIMEOUT` | 工程师源码或测试 | 是，最多一次 |
| `EXECUTOR_DEADLINE_EXCEEDED` | 平台总时限或根因不明 | 否，保留证据后由用户重试 |
| `EXECUTOR_UNAVAILABLE` | 平台执行服务 | 否，最多执行一次基础设施重试 |
| `EXECUTOR_INTERNAL` | 平台执行服务 | 否 |
| `CANCELLED` | 用户操作 | 否 |

平台故障不得通过调用工程师改写源码来掩盖。工程师修复只能修改应用规格、源码包或单元测试；如果需要改变产品范围或架构，必须回到对应上游阶段并使下游报告失效。

## 10. 安全边界

### 10.1 Railway 服务配置

执行服务要求：

- 与主服务位于同一 Railway 项目和环境；
- 不创建公网域名，只使用 `runtime-executor.railway.internal`；
- 不挂载持久化 Volume；
- 使用非 root 用户和只读应用目录，只有任务临时目录可写；
- 不配置 `DATABASE_URL`、模型密钥、管理员凭据、Cookie 密钥、Git 凭据或发布密钥；
- 只配置内部认证令牌、资源上限、日志级别和适配器开关；
- 设置 Railway 副本级 CPU/内存限制，但不能把它表述为每任务资源隔离。

主服务的所有内部接口仍要求正常身份或服务认证。执行服务与主服务处于同一私有网络，不代表执行服务可以绕过主服务授权。

### 10.2 进程约束

每个固定构建或测试进程必须：

- 使用固定参数数组，不通过 `shell=True` 或字符串拼接执行；
- 使用任务目录作为当前工作目录；
- 清空环境变量后注入最小允许集合；
- 设置总时限、输出上限和进程组终止；
- 禁止访问 Docker socket；
- 不把原始异常、宿主路径或其他任务信息返回用户。

### 10.3 已知剩余风险

Railway 服务是非特权容器，不能在服务内部依赖 Docker-in-Docker 为每次任务创建嵌套容器。当前材料也不能证明 Railway 提供每任务禁止公网出站的能力。因此：

- 目录隔离、非 root 和进程限制不能等价为强恶意代码沙箱；
- `web-static-v1` 仍需限制可执行文件、模块和测试入口；
- 被执行的 JavaScript 仍可能通过死循环、内存消耗或进程异常使当前执行服务副本不可用；超时、Railway 副本资源上限和自动重启只能限制故障面，不能消除这一风险；
- 执行服务中不得存在可被读取的业务密钥或历史源码；
- V1 不开放用户自带依赖和任意测试命令；
- 若未来支持任意后端或原生代码，必须保留本接口契约，但把执行实现迁移到每任务独立容器、微型虚拟机或专用沙箱平台。

## 11. 部署配置

### 11.1 仓库结构

当前实现结构：

```text
Dockerfile.executor                 # 执行服务镜像
another_atom/
├── executor/
│   ├── app.py                      # 私有 HTTP 入口
│   └── runner.py                   # web-static-v1 固定进程与生命周期
└── runtime/
    ├── artifacts.py                # 架构文档与源码包物化
    └── client.py                   # 主服务调用、流式读取与结果指纹校验
```

共享契约仍放在 `another_atom/contracts/`；主服务客户端和执行服务不得分别定义同名但不兼容的请求、报告或状态模型。

### 11.2 Railway 服务

在现有 Railway 项目和生产环境中新增 `runtime-executor`：

1. 使用同一 Git 仓库，Dockerfile 路径设置为 `Dockerfile.executor`；
2. 启动独立 FastAPI/Uvicorn 执行服务；
3. 不生成 Public Domain；
4. 不挂载 Volume；
5. 主服务通过私有域名访问；
6. 先部署执行服务并通过 `/health`，再把主服务执行地址切换到该私有服务。

主服务变量：

```text
RUNTIME_EXECUTOR_URL=http://runtime-executor.railway.internal:<PORT>
RUNTIME_EXECUTOR_SHARED_TOKEN=<Railway Secret>
RUNTIME_EXECUTOR_TIMEOUT_SECONDS=<按压测确定>
RUNTIME_EXECUTOR_REQUEST_MAX_BYTES=<按生成物分布确定>
RUNTIME_EXECUTOR_CLOCK_SKEW_SECONDS=60
```

执行服务变量：

```text
RUNTIME_EXECUTOR_SHARED_TOKEN=<与主服务一致的 Railway Secret>
RUNTIME_EXECUTOR_MAX_CONCURRENCY=1
RUNTIME_EXECUTOR_REQUEST_MAX_BYTES=<按生成物分布确定>
RUNTIME_EXECUTOR_CLOCK_SKEW_SECONDS=60
```

具体大小和秒数必须由真实生成项目的构建、测试和日志分布确定。设计只固定它们必须是平台配置，并且模型和用户不能提高上限。

## 12. 可观测性

主服务记录：

- 排队等待时间；
- 执行服务请求耗时；
- 物化、构建、测试和校验分阶段耗时；
- 请求与源码清单指纹；
- 适配器和工具链版本；
- 执行尝试次数；
- 构建/测试退出码和测试计数；
- 错误类别、是否可修复和证据引用；
- 清理是否成功。

不得记录：

- 完整源码包；
- 用户提示词全文；
- 请求认证令牌；
- 模型、数据库、Cookie 或发布密钥；
- 无上限的标准输出和标准错误。

用户界面展示真实阶段和截断错误摘要，不展示执行服务内部路径或平台堆栈。

## 13. 自动化验证

### 13.1 契约测试

- 请求和结果在主服务、执行服务之间使用同一 Pydantic 模型；
- 请求 hash、源码清单 hash 和上游指纹任一不匹配即失败；
- 未登记适配器、额外字段、非法路径和超限文件被拒绝；
- 返回报告不能省略构建或测试状态。

### 13.2 适配器测试

- 合法静态网页源码完成固定构建并产生 `dist/`；
- JavaScript 语法错误形成 `BUILD_FAILED`；
- 单元测试失败形成 `TEST_FAILED`；
- 测试文件缺失或未真实执行不能伪装通过；
- 构建和测试命令只能来自适配器注册表；
- 修复后完整重新物化、构建、测试和校验。

### 13.3 多用户隔离测试

- 用户甲的源码、日志和报告不出现在用户乙的任务或事件中；
- 两个用户同时提交时只运行一个任务，另一个保持可见排队状态；
- 同一用户不能通过并发请求获得两个运行槽位；
- 前一任务完成或失败后目录被清理，后一任务无法读取遗留文件；
- 执行请求中不存在用户 Cookie、数据库地址和模型密钥。

### 13.4 恢复与失败测试

- 执行服务未启动时主服务返回 `EXECUTOR_UNAVAILABLE`，不创建版本；
- 流式连接中断时不复用不完整报告；
- 执行服务重启后主服务最多创建一次新的完整执行尝试；
- 取消会终止进程、清理目录和释放主服务租约；
- 已提交版本的任务不会因工作器重启再次执行；
- 平台故障不会触发工程师改写源码。

### 13.5 Railway 部署验收

- 执行服务没有公网域名；
- 主服务能够通过私有域名调用 `/health` 和执行接口；
- 执行服务没有数据库、模型、Cookie、Git 和发布密钥；
- 执行服务没有持久化 Volume；
- 在真实 Railway 实例完成一次构建通过、测试失败、修复后通过和取消流程；
- 构建期间主服务 API、SSE 和预览查询保持可用；
- Railway 重部署执行服务后，运行中任务形成明确失败并可按规则恢复。

## 14. 实施顺序

1. 在共享契约中实现 `SourceBundle`、`ExecutionRequest`、`BuildArtifact`、`ExecutionReport`、`ValidationReport` 和新增状态枚举。
2. 创建执行服务骨架、内部认证、请求 hash 校验、健康检查和临时目录生命周期。
3. 实现 `web-static-v1` 物化、固定构建、固定测试和确定性校验。
4. 实现主服务执行客户端、流式事件持久化、取消和执行结果校验。
5. 迁移现有 `_run_build()`，删除“只调用 `validate_app_spec()` 却标记构建完成”的路径。
6. 实现 `BuildJob` 状态和数据迁移，并使项目版本引用真实执行报告和校验报告。
7. 完成契约、适配器、多用户隔离、恢复和失败自动化测试。
8. 在 Railway 同一项目、同一环境部署执行服务，完成真实部署验收后再开启生产功能开关。

## 15. 完成条件

以下条件全部满足前，本文保持 `[TODO]`：

1. 主服务不再直接执行项目构建、单元测试或运行期确定性校验。
2. 所有新运行都通过共享执行服务完成源码物化、构建、测试和校验。
3. 构建与测试命令来自固定适配器，模型和用户无法覆盖。
4. 执行报告和校验报告绑定同一个源码清单、架构设计和产品规格指纹。
5. 构建、测试或强制校验失败时不创建项目版本；可修复失败最多返回工程师一次。
6. 所有用户共享一个执行服务且不会发生源码、日志、报告或事件串用户。
7. 执行服务不持有主服务业务密钥、不挂载持久化卷且没有公网域名。
8. 自动化测试覆盖成功、构建失败、测试失败、校验失败、取消、超时、服务中断和修复重跑。
9. Railway 部署环境完成真实构建与测试验收，并记录最终资源、大小和超时配置。
10. README、运行部署文档、系统架构、智能体设计和实际行为保持一致。
