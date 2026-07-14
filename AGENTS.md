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

- `docs/design/` is the normative, continuously maintained design source. Product requirements and product-level interaction design share one product design baseline; Agent/runtime and engineering implementation belong to technical design.
- `docs/review/` records dated inspections, reflections, bugs, verification evidence, and milestone findings. A Review states what was checked and what was found; it does not become the long-term home of a solution design.
- New Review files start under `待办`. Move a Review to `归档` only after every finding is fixed, transferred to a newer pending Review, or made an explicit version-boundary decision; any durable conclusion must first be written into `docs/design/`, and the Review must receive a dated Update with the relevant Design and verification links.
- When a Review finds a problem that needs a dedicated solution, create or update the corresponding document under `docs/design/`, then link the Review finding and the design decision in both directions.
- Under `docs/design/`, classify first by version scope: `V1`, `V2`, or `整体`. `V1` is the current implementation baseline, `V2` is the planned post-V1 version, and `整体` is only for system-wide principles, evolution, or references that do not belong to one version.
- Version design domain folders are `产品设计` and `技术设计`. Keep each version's `技术设计/` flat; mark the main question in the filename with `[Agent]` or `[工程]`. Keep `整体/` flat as well, using `[产品]` or `[参考]` instead of subdirectories.
- Every Design document starts with `背景` and `摘要` after its title, table of contents, and metadata. `背景` explains why the document exists and what problem created it; `摘要` states the document's established conclusions and boundaries without adding unsupported claims or duplicating the full body.
- `docs/review/` has only two flat status directories: `待办` and `归档`. Do not add version or domain subdirectories. Record version scope and product/Agent/engineering/comprehensive review type in the document metadata instead.
- 目录名、文件名、文档标题和正文默认使用中文。必须保留的既有技术术语或角色标识，在正文中写成“中文名称（English identifier）”，不能只留下没有中文解释的英文。真实代码字段、枚举值、事件名、命令和文件路径保留英文，并在相邻正文或表格语义列中说明中文含义；不得把程序真实标识翻译成无法与代码对应的中文字段。评审文件使用稳定全局编号和类型标签：`NN-[产品|Agent|工程|综合]-YYYY-MM-DD-中文短主题.md`；从 `待办` 移到 `归档` 时不得改名。
- Stable version product design files use `NN-中文主题.md`; technical design files use `NN-[Agent|工程]-中文主题.md`; files under `整体/` use `NN-[产品|参考]-中文主题.md`. The two-digit number is the reading order within that flat directory. Dated Review files do not add a second sequence number. Version directories do not contain their own README; `docs/design/README.md` is the single design index.
- Design documents may be revised as the baseline changes. Dated Review findings remain historical evidence; add a dated Update with code/test/deployment evidence instead of rewriting the original finding.

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
