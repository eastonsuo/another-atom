# Another Atom Project Memory

## Delivery Baseline

- This project is developed by one person. By default, commit and push changes directly to `main`; create a separate branch or pull request only when the user explicitly asks for one.
- Implement the project in V1 -> V2 order. V1 is the current implementation and acceptance baseline.
- V1 delivers a Railway-hosted cloud application; Terminal CLI and local repository execution are outside V1.
- 第一版使用固定顺序的模型角色链路：产品经理（Product Manager）-> 架构师（Architect）-> 工程师（Engineer）。工程师之后的运行系统构建（Runtime Build）、测试（Test）和校验器（Validator）是确定性的非智能体阶段。新运行（Run）暂不启用数据分析师（Data Analyst）和质量评审员（Reviewer），仅保留历史阶段产物（Artifact）的只读兼容。
- 第一版的目标运行系统构建/测试/校验（Runtime Build/Test/Validation）由 Railway 同一项目、同一环境中的共享独立执行服务完成。所有用户共享该服务，主服务保持唯一任务事实源；执行服务不挂载主服务持久化卷、不持有业务密钥，且只允许固定受限运行时适配器（Runtime Adapter）。这是服务级隔离，不代表每用户或每任务独立强沙箱；在代码和 Railway 部署验收完成前，不得声称已支持真实构建和单元测试。
- V2 autonomous multi-agent behavior is a planned implementation version after V1 acceptance; it is not implemented yet.
- User requirements may describe any software product goal. Preserve the requested project type and target platform; never convert a non-Web project into a Web application or catalog merely because the current Runtime is easier to execute.
- Preview is a project-type capability, not the generation boundary. Web projects may use the implemented HTML/CSS/JavaScript Preview and Public Route. Non-Web projects still belong to the same Project/code/version model, but may expose only source, Artifacts, validation, and export until a matching build/run adapter exists.
- Keep product scope separate from Runtime support. Missing server-side auth, payments, persistent database writes, external services, native toolchains, dependencies, or Shell execution must be reported as an explicit capability gap; do not silently simulate, omit, or change the product type.

## Documentation Governance

- Design is continuously maintained in two scopes: `docs/design/` holds shared product, architecture, version and deployment baselines; `docs/features/<稳定编号>-<中文功能名>/` holds Feature-specific product and technical design. Each contract has one authoritative home. Start from `docs/features/README.md` and the Feature entry to locate it.
- During the documentation transition, existing design bodies remain at their current paths. `docs/features/文档归属与迁移映射.md` registers their ownership and planned destinations; a planned destination is not an active source. Update the existing authoritative file until an actual move updates the mapping and all links. Do not create a parallel copy.
- Feature directories and identifiers remain stable across iterations; version scope belongs in metadata. A Feature entry links applicable design, the current Code Spec, optional Plan, self-test and historical evidence. It does not duplicate design contracts or the Issue task queue. Create supporting documents only when needed.
- `docs/review/` records dated inspections, reflections, verification evidence, and milestone findings. A Review answers whether a product or technical area is complete and what the inspection found; it is not the current queue for independently reproducible implementation defects and does not become the long-term home of a solution design.
- `docs/bug/` records independently reproducible implementation defects where existing Design, Contract, or accepted behavior is already clear but the code does not satisfy it. A Bug may be fixed directly without changing Design. If resolving it would change the expected Contract or product behavior, treat that part as a Review finding and update the applicable shared or Feature design before implementation.
- New Review files start under `待办`. Move a Review to `归档` only after every finding is fixed, transferred to a newer pending Review or Bug, or made an explicit version-boundary decision; any durable conclusion must first be written into the applicable shared or Feature design, and the Review must receive a dated Update with the relevant Design, Bug, or verification links.
- New Bug files start under `待办`. Move a Bug to `归档` only after the implementation is fixed and the document contains reproducible automated or deployed verification evidence. GitHub Issue is the execution tracker; the Bug document is the repository evidence record. Link them when an Issue exists, but do not duplicate moment-to-moment task status in the Bug document.
- When a Review finds an independently reproducible code defect, create a Bug document and link it from the Review. When a Review finds a missing capability, unclear boundary, or Contract/design problem, create or update the applicable shared or Feature design, then link the Review finding and the design decision in both directions. Review and Bug records retain their existing numbering and evidence directories; Feature entries reference them.
- Under `docs/design/`, classify first by version scope: `V1`, `V2`, or `整体`. `V1` is the current implementation baseline, `V2` is the planned post-V1 version, and `整体` is only for system-wide principles, evolution, or references that do not belong to one version.
- Version design domain folders are `产品设计` and `技术设计`. Keep each version's `技术设计/` flat; mark the main question in the filename with `[Agent]` or `[工程]`. Keep `整体/` flat as well, using `[产品]` or `[参考]` instead of subdirectories.
- Every Design document starts with `背景` and `摘要` after its title, table of contents, and metadata. `背景` explains why the document exists and what problem created it; `摘要` states the document's established conclusions and boundaries without adding unsupported claims or duplicating the full body.
- `docs/review/` has only two flat status directories: `待办` and `归档`. Do not add version or domain subdirectories. Record version scope and product/Agent/engineering/comprehensive review type in the document metadata instead.
- `docs/bug/` also has only two flat status directories: `待办` and `归档`. Bug files use `NN-[产品|Agent|工程|综合]-YYYY-MM-DD-中文短主题.md`; the number is globally stable within `docs/bug/` and moving the file must not rename it.
- 目录名、文件名、文档标题和正文默认使用中文。必须保留的既有技术术语或角色标识，在正文中写成“中文名称（English identifier）”，不能只留下没有中文解释的英文。真实代码字段、枚举值、事件名、命令和文件路径保留英文，并在相邻正文或表格语义列中说明中文含义；不得把程序真实标识翻译成无法与代码对应的中文字段。评审文件使用稳定全局编号和类型标签：`NN-[产品|Agent|工程|综合]-YYYY-MM-DD-中文短主题.md`；从 `待办` 移到 `归档` 时不得改名。
- Existing version design files retain their names during the transition. Shared product design files use `NN-中文主题.md`, shared technical files use `NN-[Agent|工程]-中文主题.md`, and files under `整体/` use `NN-[产品|参考]-中文主题.md`; these numbers indicate reading order. Feature identifiers are independently stable and do not indicate priority. Feature design filenames do not encode `[TODO]` / `[DONE]`; record design confirmation, implementation and environment verification separately in metadata. `docs/design/README.md` indexes shared and not-yet-migrated design; `docs/features/README.md` indexes Feature entries.
- Design documents may be revised as the baseline changes. Dated Review findings and Bug records remain historical evidence; add a dated Update with code/test/deployment evidence instead of rewriting the original finding.
- Completed Features are not required to acquire retrospective Design, Code Spec, Plan or test records. Reuse existing evidence; only document material maintenance gaps when needed. A code-derived current-implementation note records its actual date and evidence, not inferred historical decisions or approvals. Directory registration does not confirm design or delivery completion.

## Evaluation Criteria

All implementation and scope decisions must be checked against these five dimensions.

### 1. Completeness

- 保护完整的第一版闭环：请求 -> 产品规格（ProductSpec）确认 -> 架构设计（ArchitectureDesign）-> 应用规格（AppSpec）+ 源码包（SourceBundle）+ 单元测试 -> 运行系统构建/测试/校验（Runtime Build/Test/Validation）-> 预览（Preview）-> 编辑/修复（Edit/Resolve）-> 版本（Version）-> 发布（Publish）-> 公开地址（Public URL）。
- Cover recovery and negative paths, not only the Golden Path.
- Treat persistence, visible failure states, and automated verification as part of the feature.

### 2. Engineering Judgment

- 把产品规格（ProductSpec）、产品蓝图（Blueprint）、架构设计（ArchitectureDesign）、应用规格（AppSpec）、源码包（SourceBundle）、执行报告（ExecutionReport）、校验报告（ValidationReport）、事件（Event）、错误（Error）、版本（Version）和导出格式（Export Format）保持为显式契约。
- Prefer the smallest implementation that completes the V1 loop; do not pull V2 autonomy or local runtime into V1.
- Record meaningful tradeoffs around safety, concurrency, quota, persistence, and deployment.
- Add tests in proportion to the affected state transition and user-facing blast radius.

### 3. User Experience

- Every visible control must work, explain why it is disabled, or state the capability boundary.
- Users must be able to inspect and approve key Agent outputs instead of trusting an opaque progress stream.
- Loading, failure, retry, restore, and publish states must remain understandable on desktop and mobile.

### 4. Innovation

- The V1 differentiator is the inspectable artifact chain, controlled role handoff, recoverable versions, and publishable result.
- Preserve the contracts needed for V2 multi-agent orchestration and a possible future local runtime.
- Do not add decorative AI behavior or extra features solely to appear innovative.

### 5. Deliverability

- Keep the repository runnable from documented steps and keep README claims aligned with implemented behavior.
- A milestone is complete only after its acceptance checks pass in the deployed environment.
- The final delivery requires a public test URL, source link, clear known boundaries, and reproducible verification results.

## Implementation Check

Before closing a task or milestone, verify:

1. Which evaluation dimension does this work improve?
2. Does it advance the V1 end-to-end loop or only add surface area?
3. What persisted state, error path, and user-visible behavior changed?
4. What automated or deployed verification proves it works?
5. Do README, PRD, architecture, and actual behavior still agree?

## Agent skills

### Feature delivery workflow

- 新增或改变产品行为、公共接口、数据语义、组件职责、跨组件合同、故障、兼容或迁移时，遵循 [`docs/agents/feature-delivery-workflow.md`](docs/agents/feature-delivery-workflow.md)。不得以普通 Bug／维护修复绕过技术设计和 Code Spec 门禁。
- 先从 [`docs/features/README.md`](docs/features/README.md) 定位 Feature，再读取其登记的共同基线、当前产品说明和技术总设计；跨 Feature 合同归 `docs/design/`，专项设计归对应 Feature，迁移期以登记的现有路径为准。正式 Code Spec 和可选 Implementation Plan 分别进入 `docs/superpowers/specs/` 与 `docs/superpowers/plans/`，与 Feature 入口双向关联，不得建立平行设计。
- Code Spec 是持续维护的实施合同；保持唯一当前文件和稳定路径，记录来源设计版本及适用范围。每次实施重新核对设计与 Spec，合同变化时更新并按影响重新审阅；文字修正不机械撤销确认。不得按日期反复生成同一 Feature 的并行当前 Spec，也不为已完成功能补历史 Spec。
- 每个阶段只在其门禁满足后进入下一阶段。技术总设计确认、Code Spec 确认、Plan 确认和环境写入授权彼此独立；Agent 不得代替用户确认，也不得因用户要求“完整推进”而跨过尚未满足的门禁。
- Implementation Plan 默认可选。只有用户明确要求，或复杂、跨仓、需要多轮维护任务账本时才使用；没有 Plan 不阻止已确认 Code Spec 进入实施。
- 本仓库不采用 `openspec/**` 作为默认 Feature 流程。除非用户明确决定迁移到 OpenSpec，否则不得新建第二套 Spec 状态源。

### Validation workflow

- 开发侧自测遵循 [`docs/validation/README.md`](docs/validation/README.md)，记录按需创建于 `docs/features/<稳定编号>-<中文功能名>/10-自测方案与执行记录.md`。一个 Feature 只维护一份当前记录，执行批次绑定实际版本并追加结果；`docs/validation/` 只保留公共规范。
- 非生产环境及其不可变版本、访问入口和授权边界从 [`docs/agents/validation-environments.md`](docs/agents/validation-environments.md) 读取。未登记或不能唯一识别的 Railway 环境不得推定为非生产环境。
- 本地单元测试、静态检查、前端 lint/build 和本地真实边界集成属于代码实施；制品构建与环境变更属于部署；Smoke、API、页面和 E2E 属于环境验证。三类事实不得相互替代。
- 本个人仓库的 `[实施澄清记录]` 位置登记为 `docs/features/<稳定编号>-<中文功能名>/11-实施澄清记录.md`；本轮已授权登记这一位置，后续在已授权 Feature 工作范围内按需创建，不为占位创建空文档。记录不能由现有依据唯一决定的语义冲突或持久工程取舍；普通实现问题和一次性操作授权不进入记录。完整讨论只留在该记录，已确认结论回写适用设计、Spec 或项目配置；记录本身不替代设计／Spec 确认及环境授权。

### Issue tracker

本仓库使用 GitHub Issues 跟踪议题。详见 `docs/agents/issue-tracker.md`。

### Triage labels

本仓库使用五个默认分流角色标签。详见 `docs/agents/triage-labels.md`。

### Domain docs

本仓库采用单上下文（single-context）领域文档布局。详见 `docs/agents/domain.md`。
