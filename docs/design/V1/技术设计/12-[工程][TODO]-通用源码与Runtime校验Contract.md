# Another Atom V1 通用源码与 Runtime 校验 Contract

[toc]

- 文档状态：V1 设计已确认，代码、自动化测试和部署验收尚未完成
- 更新日期：2026-07-16
- 决策来源：[第二十二号评审：Engineer 项目源码 Contract 缺口](../../../review/待办/22-[工程]-2026-07-14-Engineer项目源码Contract缺口.md)
- Agent 设计：[Another Atom V1 多 Agent 设计](./01-[Agent]-多Agent设计.md)
- 系统架构：[Another Atom V1 系统架构](./03-[工程]-系统架构.md)
- 执行设计：[Another Atom V1 共享独立执行服务](./08-[工程][TODO]-共享独立执行服务.md)

## 背景

当前 Engineer Prompt 要求模型返回网页 `AppSpec` 和 Node.js 单元测试，`SourceBundle` 又把 `adapter_id`、`index.html` 和测试文件约束固定为 `web-static-v1`。随后 Repository Packager、候选源码修改校验、确定性 Validator 与 Runtime Executor 分别维护 HTML Fragment、Runtime 管理外壳、网络限制、固定文件名和固定命令。这些规则没有形成同一个 Interface：模型输出可以通过 Pydantic Schema，却在后续物化、Build/Test 或 Runtime 校验中因另一套隐藏规则失败。

Another Atom 的产品目标允许用户生成任意类型的项目源码。Preview 是存在匹配 Runtime Adapter 时的附加能力，不是源码交付成立的前提。因此不能通过固定 HTML 外壳、固定三文件结构或缩小项目类型来换取更高通过率。本设计建立通用 Source Contract 与版本化 Runtime Contract，统一 Engineer、确定性预检、Runtime Adapter 和 UI 使用的规则，同时保留安全、完整性和真实执行门禁。

## 摘要

- **源码事实源**
  - SourceBundle 是项目源码的权威产物，允许表达任意文本源码目录、入口、测试、配置和文档；AppSpec 只保留交付元数据，不再生成或重写源码。
- **统一运行 Interface**
  - Runtime Contract 是 SourceBundle 与运行能力 seam 上唯一的 Interface；Engineer、预检、Runtime Adapter 和 UI 使用同一版本与内容指纹。
- **校验职责**
  - 通用校验只处理路径、大小、内容指纹和声明一致性；项目形态、工具链、入口、依赖、网络和 Preview 规则由已选择的 Runtime Contract 声明；真实 Build/Test 只由 Runtime 执行。
- **结果语义**
  - 区分 `valid`、`source_ready`、`candidate_rejected` 和 `execution_blocked`。没有 Adapter 的项目仍可形成源码版本；候选失败不移动最后可用版本。
- **迁移策略**
  - 历史 `web-static-v1` 继续只读兼容；新 Web 生成使用语义明确的完整 Document Contract，不再把同一个 `html` 字段同时解释为 Fragment 和完整文档。
- **质量目标**
  - 90% 是按项目类型和 Runtime Contract 统计的首次候选质量目标，不是限制产品范围、固定模板或放松必要校验的设计输入。

## 1. 目标与非目标

### 1.1 目标

1. Engineer 在生成前获得后续预检和 Runtime 会实际执行的完整规则。
2. 通用 SourceBundle 不再由任何单一语言、框架或 Runtime Adapter 定义。
3. Runtime Adapter 只消费候选源码，不为 Preview 修改 Repository 中的权威源码。
4. 可以在不修改 Engineer、Repository 和 UI 规则副本的情况下新增 Runtime Contract。
5. 任何候选失败都保留原始证据和最后可用 ProjectVersion。
6. 同时统计通用源码交付质量与各 Runtime Contract 的 Build/Test/Preview 质量。

### 1.2 非目标

- V1 不承诺在 Railway 共享执行环境中安全运行任意不可信代码。
- V1 不开放模型提供的 Shell、包安装命令、镜像名称或宿主文件路径。
- V1 不因为支持任意源码交付就声称所有项目都支持在线 Build、Test 或 Preview。
- 本设计不在只有一个可执行 Adapter 时提前实现复杂插件框架；V1 可以使用版本化注册表和一个 `web-static` Adapter，第二个 Adapter 落地时再抽取可替换实现。
- 本设计不保证模型每次生成都正确；它保证规则一致、错误尽早暴露、失败不会破坏已有版本。

## 2. 当前实现与目标差异

| 位置 | 当前实现 | 目标设计 |
| --- | --- | --- |
| Engineer 输出 | `EngineerOutput(app_spec, unit_tests)` | `EngineerOutput(delivery_spec, source_bundle)` |
| AppSpec | 同时保存交付元数据和 HTML/CSS/JavaScript | 只保存交付元数据、产品入口说明与 Runtime 绑定 |
| SourceBundle | `adapter_id=web-static-v1`、入口固定 `index.html`、至少一个 `.test.js` | 通用文件清单、声明入口、可选 Runtime Binding |
| Packager | 从 AppSpec 三字段派生固定文件 | 原样验证和物化 SourceBundle，不合成业务源码 |
| 修改候选 | 重新提取 HTML body，并恢复 Runtime 外壳和 network guard | 对权威源码应用受控 Patch，不进行语言专属反向转换 |
| Validator | 同时混合网页形态、安全、产品映射和运行结果 | 通用源码、Runtime 兼容、真实执行、质量 Warning 分层 |
| Executor | 固定执行 `node --check app.js` 和 `node --test tests/*.test.js` | 只执行注册表中 Runtime Contract 对应的固定计划 |
| 失败语义 | Build/Preview 失败可使整个 Run 失败 | 区分源码无效、无法在线运行、安全阻断和候选执行失败 |

## 3. Module、seam 与 Interface

### 3.1 通用源码 Module

通用源码 Module 隐藏文件路径规范化、体积上限、内容指纹、Manifest 指纹和候选 Patch 应用。其外部 Interface 只有两个核心操作：

```text
validate_source(bundle) -> SourceValidationResult
apply_changes(base_bundle, change_set) -> CandidateSourceBundle
```

调用方不需要理解 HTML、Python、Node.js 或其他语言的内部结构。语言专属引用解析不进入这个 Interface；只有 Runtime Contract 声明并提供对应检查时才执行。

### 3.2 Runtime Contract seam

Runtime Contract 位于“已经通过通用源码校验的候选源码”与“某种可执行能力”之间：

```text
Engineer Context ----读取----+
                             |
Candidate SourceBundle -> Runtime Contract -> Runtime Adapter -> ExecutionResult
                             |
Preflight Validator --读取---+
                             |
Studio UI -----------读取----+
```

Runtime Contract 是 Interface，包含调用者必须知道的项目兼容条件、错误模式、能力和执行限制。Web、Python 或其他 Runtime Adapter 是满足该 Interface 的具体实现。Contract 不属于模型输出，模型只能引用主服务已选择并提供的 Contract 标识、版本和内容指纹。

### 3.3 V1 不提前建设插件框架

当前只有一个已实现的可执行 Adapter，因此 V1 只需：

- 一个由主服务和 Runtime Executor 共同依赖的版本化 Contract 注册表；
- 一个根据 `contract_id + version` 选择固定执行计划的分派 Module；
- 一个 `source-only` 结果路径，但 `source-only` 不是伪 Runtime Adapter，也不执行代码。

只有第二个真实可执行 Adapter 进入实现后，才把分派 Module 内部的不同实现抽成可替换 Adapter Interface。这样保留未来扩展 seam，不为假设变化增加当前 Interface 面积。

## 4. 通用 Source Contract

### 4.1 SourceBundle

目标 SourceBundle 使用新的 Schema 版本，最小字段如下：

| 字段 | 约束 | 语义 |
| --- | --- | --- |
| `schema_version` | 版本化字符串 | Source Contract 版本 |
| `project_type` | 非空、受长度限制 | 保留用户确认的软件类型，不决定 Runtime 能力 |
| `files` | 唯一路径的有界清单 | 项目权威源码、测试、配置和文档 |
| `entrypoints` | 可为空的声明列表 | 业务入口或测试入口；没有 Adapter 时只作为交付元数据 |
| `runtime_binding` | 可空 | 已选择 Runtime Contract 的标识、版本和内容指纹 |
| `manifest_hash` | SHA-256 | 对路径、角色、编码和内容指纹排序后的确定性指纹 |

V1 的“任意代码”指不限制编程语言、目录层级和文本源码文件名。二进制文件继续作为附件或构建产物管理，不要求模型在 SourceBundle 中生成任意二进制内容。

### 4.2 SourceFile

SourceFile 至少包含：

| 字段 | 约束 |
| --- | --- |
| `path` | 规范化相对 POSIX 路径；禁止绝对路径、空段、`.`、`..`、反斜杠和 `.git/` |
| `role` | `source`、`test`、`config`、`documentation` 或 `asset` |
| `encoding` | V1 固定 `utf-8`；其他编码未实现 |
| `content` | 受单文件和总量上限约束的文本 |
| `content_hash` | 内容 SHA-256 |

文件后缀不作为通用合法性判断。某个 Runtime Contract 可以声明自己只接受特定文件、入口或扩展名，但不得把该规则写回通用 Source Contract。

### 4.3 Entrypoint 与 RuntimeBinding

Entrypoint 只描述源码中的逻辑入口：

```json
{
  "kind": "application",
  "path": "src/main.py"
}
```

`kind` 初始只定义 `application` 和 `test`；构建命令、测试命令和 Preview 命令不由 SourceBundle 提供。

RuntimeBinding 只引用平台注册的 Contract：

```json
{
  "contract_id": "web-static-document",
  "contract_version": "1.0",
  "contract_hash": "sha256:..."
}
```

缺少 RuntimeBinding 不影响 SourceBundle 成立。主服务必须把它解释为“当前只交付源码”，不能自动选择 Web Adapter 或生成 HTML 替代品。

### 4.4 AppSpec 收敛

AppSpec 改为 DeliverySpec 后，只保留：

- 项目名称和简要说明；
- 项目类型与目标平台；
- 用户可见入口说明；
- SourceBundle Manifest 指纹；
- 可选 RuntimeBinding；
- 已确认能力缺口。

HTML、CSS、JavaScript 和测试内容只存在于 SourceBundle。Repository、Preview 和修改流程不得再从 DeliverySpec 反向生成源码，也不得要求 SourceBundle 能无损还原为旧 AppSpec 三字段。

## 5. Runtime Contract

### 5.1 Contract 内容

Runtime Contract 由平台代码注册并版本化，分为 Engineer 可见要求和 Executor 固定计划，两者属于同一个对象并共享内容指纹，不能分别维护。

| 区域 | 内容 |
| --- | --- |
| 身份 | `contract_id`、`version`、`contract_hash` |
| 支持范围 | 支持的项目类型、目标平台和明确不支持能力 |
| Source 要求 | 必需入口、文件规则、测试规则、Document/Fragment/构建产物语义 |
| 能力 | `build`、`test`、`preview`、`publish` 是否可用 |
| 依赖规则 | 是否允许清单文件、是否允许安装、预装工具链版本 |
| 网络规则 | 构建期和运行期允许的网络类别；localhost 与用户设备访问规则 |
| 执行计划 | 平台固定命令标识、超时、资源上限、产物收集规则 |
| 错误分类 | 哪些失败可由 Engineer 修复，哪些属于平台或安全问题 |

Engineer 读取 Source 要求、能力、依赖和网络规则；它不读取凭证、宿主路径或内部命令实现。Executor 读取同一 Contract 中的平台固定计划，拒绝 SourceBundle 自带的命令字符串。

### 5.2 Contract 选择

Contract 选择发生在 Engineer 前：

1. ProductSpec 保留用户目标、项目类型和目标平台。
2. Architect 根据已登记 Contract 记录匹配结果和能力缺口，但不能把不匹配项目改写为 Web。
3. Orchestrator 校验 Contract 仍存在且版本、指纹一致，再组装 Engineer Context。
4. Engineer 原样返回 RuntimeBinding；不允许模型自行选择、升级或降级 Contract。
5. 若没有匹配 Contract，Engineer 仍生成 SourceBundle，RuntimeBinding 为 `null`。

能力识别必须在 Engineer 前留痕，不能在生成失败后才把请求改判为“不支持”以改善通过率分母。

### 5.3 `web-static-v1` 迁移

历史 `web-static-v1` 把 `AppSpec.html` 解释为 body Fragment，由 Renderer 增加完整 Document 外壳、资源引用和 network guard。该模式保留历史 ProjectVersion 的只读 Preview 和导出，不再作为通用 SourceBundle 的模型。

新 Web 生成使用语义明确的 `web-static-document` Contract：

- `index.html` 是 SourceBundle 中的完整权威文件；Runtime 不增加或替换 `DOCTYPE/html/head/body`。
- CSS、JavaScript、图片和其他相对资源可以使用任意合法相对路径，不强制固定三文件名。
- 必需入口、测试约定、允许的内联资源和网络能力全部由 Contract 明示。
- Adapter 在临时候选工作区执行和生成 Preview，不把运行期 Guard 写回 Repository 源码；必要 Guard 由 Preview Sandbox 在运行层注入。
- 新旧 Contract 使用不同标识，禁止根据 HTML 内容猜测 Fragment 或 Document 模式。

具体是否允许内联 `<script>` 由 `web-static-document` 的安全实现和 Preview Sandbox 能力决定。本设计只要求规则显式且 Engineer 与 Runtime 一致，不通过全局源码校验预设结论。

## 6. 校验分层

### 6.1 通用 Source 校验

在进入 Runtime 前执行，失败表示候选 Source Contract 不成立：

- Schema 版本和字段合法；
- 文件路径、数量、单文件与总大小合法；
- 路径唯一，内容指纹和 Manifest 指纹一致；
- Entrypoint 引用 SourceBundle 中存在的普通文件；
- RuntimeBinding 的标识、版本和内容指纹存在且一致；
- Patch 目标、`before_hash` 和基线 Manifest 一致；
- 未声明文件没有在候选物化过程中变化。

通用校验不尝试解析所有语言的 import、包或动态加载。只有被 SourceBundle 显式声明的 Entrypoint，以及 Runtime Contract 能确定性解析的受控引用，才进行闭包检查。

### 6.2 Runtime 兼容预检

预检与 Runtime Adapter 读取同一 Runtime Contract，在调用 Executor 前检查：

- 项目类型和目标平台是否匹配；
- 必需入口、测试和配置是否存在；
- Document、Fragment 或构建产物语义是否匹配；
- 文件类型、依赖清单和受控引用是否符合该 Contract；
- 请求的网络和执行能力是否超出 Contract。

预检失败必须返回稳定错误码、具体路径和 Contract 条款，不应等到长时间模型 Repair 或真实执行后才暴露。

### 6.3 Runtime 真实执行

只有匹配 RuntimeBinding 且通过预检的候选进入 Executor：

- 在隔离临时目录原样物化 SourceBundle；
- 执行 Contract 注册的固定 Build/Test 计划；
- 应用 Sandbox、资源、时间和网络限制；
- 收集真实退出码、日志摘要和构建产物；
- 生成不可由 Engineer 改写的 ExecutionReport。

安全、权限、资源和真实 Build/Test 结果继续作为强制门禁。统一规范不等于放松这些校验。

### 6.4 产品与质量校验

产品验收映射只有存在确定性证据时才作为强制检查；代码风格、可选 README、非验收条件的辅助测试和非阻断体验建议产生 Warning。Validator 不应根据关键词猜测任意源码是否满足产品需求，也不能把 Reviewer 的主观建议升级为 Runtime 失败。

## 7. 结果与版本状态

### 7.1 统一结果

| 结果 | 条件 | 版本处理 | 用户可见行为 |
| --- | --- | --- | --- |
| `valid` | Source 与已绑定 Runtime 全部通过 | 原子创建并切换 ProjectVersion | 展示源码及 Contract 支持的 Build/Test/Preview |
| `source_ready` | Source 有效，但 RuntimeBinding 为空或当前环境没有对应运行能力 | 创建源码 ProjectVersion | 展示源码、文档、导出和明确能力缺口，不展示伪 Preview |
| `candidate_rejected` | Source、Runtime 兼容、Build 或 Test 未通过 | 不移动当前版本，保存候选证据 | 展示失败阶段、路径、错误码和有限 Repair 入口 |
| `execution_blocked` | 命中安全、权限或不可接受的执行风险 | 不执行、不提升为可运行版本 | 展示阻断原因；不得让 Engineer 通过改写日志掩盖 |

`source_ready` 不是失败，也不是 Runtime Adapter。它表示源码交付成立，但当前没有在线执行证据。

### 7.2 候选提升

```text
EngineerOutput
    -> Source Contract 校验
    -> 隔离候选 SourceBundle
    -> [无 RuntimeBinding] source_ready
    -> [有 RuntimeBinding] 兼容预检 -> Build -> Test -> Validation
    -> valid 后原子创建 ProjectVersion
```

候选失败不修改当前 Git commit、ProjectVersion、Publication 或 Public Route。初次生成没有最后可用版本时，候选和错误证据仍保存为 Run Artifact，用户可以修改要求或重试，但系统不得把未通过候选标为 Ready。

### 7.3 Repair

Repair 只接收：

- 当前有效产品与架构文档；
- 同一 Runtime Contract 快照；
- 固定基线 SourceBundle 和候选变更；
- 可修复的路径级错误证据。

Engineer 返回受控 SourceFileChangeSet，本地校验 `before_hash` 后应用到隔离候选。Repair 不返回完整项目，不修改 Runtime Contract，不处理平台或安全根因，且所有结果重新经过同一完整门禁。

## 8. 观测与 90% 目标

90% 是统一 Contract 实施后的质量结果，不是设计限制。系统至少记录：

- `project_type`；
- `source_contract_version`；
- Runtime Contract 标识、版本和内容指纹；
- 首次候选是否通过；
- 首次失败层级与稳定错误码；
- 是否进入 Repair 及 Repair 后结果；
- Provider、平台、取消和超时是否影响 Run。

指标分开计算：

1. 通用 Source Contract 首次通过率：所有收到完整 Engineer 响应的有效 Run。
2. Runtime 首次通过率：按 Runtime Contract 分组，只统计已经在 Engineer 前确认匹配的有效 Run。
3. Repair 后通过率：单独统计，不进入首次通过率。
4. 最终交付率：同时包含 `valid` 和 `source_ready`，但必须分别展示数量。

禁止通过缩小项目类型、失败后改判不支持、固定少量模板、放松安全/完整性门禁或把 Repair 计入首轮来达到 90%。达到目标需要真实有效 Run 证明；样本不足时只报告样本结果。

## 9. 迁移顺序

### 9.1 第一阶段：统一事实源

1. 新增 Source Contract 与 Runtime Contract Schema、注册表和内容指纹。
2. 从现有 `web-static-v1` 规则生成一份显式历史 Contract，用于兼容读取。
3. Engineer Context、预检和 Executor 改为读取同一个 Contract 快照。
4. 增加错误分层与指标字段，不改变历史 ProjectVersion。

### 9.2 第二阶段：SourceBundle 成为权威源码

1. Engineer 直接返回 DeliverySpec 和通用 SourceBundle。
2. Packager 不再从 AppSpec 三字段派生业务源码。
3. 修改链路只对 SourceBundle 应用受控 Patch。
4. AppSpec 三字段保留历史读取，停止写入新版本。

### 9.3 第三阶段：Web Document Adapter

1. 实现 `web-static-document` Contract 与 Adapter。
2. 覆盖完整 Document、任意相对文件结构和 Preview Sandbox。
3. 新 Web Run 切换到新 Contract；旧版本继续使用 `web-static-v1` 只读路径。
4. 校验 Preview 失败不会覆盖已有可用版本。

### 9.4 第四阶段：源码交付状态

1. 实现 `source_ready` ProjectVersion 和 UI 能力展示。
2. 验证一个没有 Runtime Adapter 的非 Web 项目可以保存、查看、编辑、版本化和导出源码。
3. 第二个真实可执行 Adapter 进入开发时，再评估是否抽取可替换 Adapter Interface。

## 10. 自动化验收

至少覆盖以下测试：

1. Engineer Context、预检和 Executor 使用完全一致的 Runtime Contract 标识、版本和内容指纹。
2. 完整 HTML Document 在 `web-static-document` 下不触发 Runtime-managed shell 错误。
3. HTML Fragment 不能冒充完整 Document；历史 `web-static-v1` 仍可只读 Preview。
4. SourceBundle 缺少声明 Entrypoint、路径越界、Manifest 不一致或 Patch Hash 不匹配时在 Executor 前失败。
5. Runtime Contract 缺失、版本错误或指纹不一致时不执行候选，并返回稳定错误码。
6. 没有 RuntimeBinding 的 Python、Node.js 之外任意文本源码项目形成 `source_ready` 版本，不生成 HTML。
7. Runtime Build/Test 失败只产生 `candidate_rejected`，当前 ProjectVersion、Publication 和 Public Route 不变。
8. Sandbox 或权限违规产生 `execution_blocked`，不进入 Engineer 自动 Repair。
9. Warning 不阻断源码版本；mandatory check 仍然阻断候选提升。
10. 首次通过、Repair 后通过、`valid` 与 `source_ready` 指标可由持久化事件复算。

## 11. 完成条件

以下条件全部满足前，本文保持 `[TODO]`：

- Source Contract、Runtime Contract 和结果状态已进入 Pydantic/OpenAPI 事实源；
- Engineer、Repository、Runtime Executor 和 Studio 不再维护不一致的规则副本；
- 新 Web Contract 与历史兼容路径完成自动化验证；
- 无 Adapter 的非 Web 源码交付路径完成自动化和部署验收；
- 候选失败保留旧版本和证据的负向路径完成验证；
- Review 22 增加实现、测试和部署证据后归档。

## 2026-07-16 实现进展

本次已完成第一版代码迁移，但尚未完成部署验收和指标验证，因此本文继续保持 `[TODO]`。

已经落地：

- `SourceBundle 2.0`、`RuntimeBinding`、`RuntimeContract`、`RuntimeCapabilities` 与四种结果语义进入 Pydantic/OpenAPI 事实源；
- 建立带版本和内容指纹的 Runtime Contract 注册表，新增 `web-static-document@1.0`，并保留 `web-static-v1@1.0` 历史读取兼容；
- Engineer 在生成前接收同一 Runtime Contract 的公开投影，直接输出权威源码文件与 Entrypoint；AppSpec 新版本不再承载 HTML、CSS 和 JavaScript 业务源码；
- 主服务预检和 Runtime Executor 共同调用同一 Contract 校验实现；完整 HTML Document 不再经过 Runtime 外壳反向提取和重写；
- 没有 RuntimeBinding 的非 Web 项目形成 `source_ready` 版本，不生成伪 `index.html`，Preview 和 Publish 根据能力返回明确边界；
- 项目对话修改与结构化编辑都在固定基线 SourceBundle 上生成或应用受控文件变更，修改后重新执行同一 Contract；Restore 复用原 SourceBundle 并重新校验；
- Studio Preview 直接消费 `web-static-document` 权威源码，在 Preview 层注入 Sandbox/CSP 和本地回环访问 Guard，不把运行期 Guard 写回 Repository；
- `candidate_rejected` 与 `execution_blocked` 不写入新的可用版本，原 Publication 和 Public Route 保持不变。

本地验证证据：

- `python -m pytest -q`：完整后端测试套件通过；
- `ruff check another_atom tests`：通过；
- `npm run build`（`studio/`）：TypeScript 与 Vite 生产构建通过；
- 回归覆盖 Runtime Contract 指纹、完整 Document、回环地址阻断、Source-only 交付及增量修改、Build/Test Repair、结构化编辑、Restore、Preview/Publish 能力边界和历史版本兼容。

仍未完成：

- Railway 部署环境的端到端验收与公开测试 URL 证据；
- 首次 Source/Runtime 通过率、Repair 后通过率及 `valid/source_ready` 分组指标的持久化统计和观测；
- 第二个真实可执行 Runtime Adapter。V1 不以此为当前交付前置条件，但在新增 Adapter 前不宣称任意项目都可在线运行。
