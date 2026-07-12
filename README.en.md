# Another Atom

[简体中文](./README.md) | [English](./README.en.md)

> Turn a rough idea into a software project whose code you can inspect, edit, version, and publish.

Another Atom is a multi-agent Vibe Coding workspace. Users express intent in natural language; specialist Agents plan, implement, and validate, while the Project workspace keeps interactive preview, code files, version history, and publishing in one continuous development loop.

The core path is **idea → plan → multi-agent build → preview and code editing → validation and repair → version → publish → continue iterating**. See the [overall product goal and positioning](./docs/design/整体/产品设计/整体产品目标与定位.md).

## Product Interface

![Another Atom Chinese Studio home with Lead chat, fixed specialist team, project history, and real LLM status](./docs/assets/readme/studio-home-zh.png)

The Studio keeps Lead chat, the fixed specialist team, Project history, model selection, and account quota in one workspace. During a build it also exposes stage progress, Run logs, a collapsible file/Vim drawer, preview, versions, and publishing state.

![Another Atom build workspace with role pipeline, mobile preview, Project file tree, and Run log](./docs/assets/readme/studio-build-workspace-zh.png)

The build workspace shows persisted role progress, an interactive Preview, the Project Repository, and current Run Artifacts together. Files/Vim and Run logs stay collapsed as right-side tools until needed, so they do not permanently squeeze the main canvas.

![Another Atom version history where Build, Edit, and Restore create separate versions](./docs/assets/readme/version-history-zh.png)

Version history distinguishes Build, Edit, and Restore sources. Restore creates a new ProjectVersion and Git commit without overwriting history; the public version still changes only through explicit Publish/Update.

Another Atom is a multi-agent Vibe Coding workspace where users advance software projects through natural language while retaining control of requirements, code files, versions, and publishing. V1 currently delivers those product goals as self-contained Web applications.

The project is inspired by [Atoms](https://atoms.dev/), but it is independently designed and implemented. It is not an Atoms fork and does not use Atoms source code or internal infrastructure.

> **Current status:** A runnable V1 vertical slice is implemented with username/password Sessions, user-isolated Projects, real Lead routing, Ollama Cloud and Mock providers, per-Project Git, structured editing, restricted Vim/Sandbox integration, versioning, publishing routes, persistence, quota, and automated tests. Railway single-replica deployment, persistent storage, and public access have been accepted; target Linux Sandbox isolation acceptance remains.

> **Current runtime boundary:** The runnable slice is single-instance only. User requirements may describe any product goal; Product Manager preserves that goal and the team generates self-contained HTML/CSS/JavaScript. Supported offline Web behavior continues automatically, while server auth, payments, persistent writes, external services, native capabilities, or added risk require adaptation or stop before build. Committed stage artifacts, quota settlement, Build Jobs, source commits, and versions remain replay-safe across Worker restart.

> **Provider fallback:** Structured role calls use DeepSeek V4 through Ollama Cloud first, with non-thinking mode for Lead. When `DEEPSEEK_API_KEY` is configured, an Ollama timeout after 30 seconds switches once to the official DeepSeek API; ordinary HTTP errors do not trigger this fallback. The UI reports “switching provider,” Run stages persist a `provider.fallback` event, and usage from both requests is settled. See the [local and Railway guide](./docs/design/V1/工程设计/本地运行与Railway部署.md#24-配置真实模型与-deepseek-兜底) for configuration.

> **Design baselines:** [overall product positioning](./docs/design/整体/产品设计/整体产品目标与定位.md) · [V1 engineering architecture](./docs/design/V1/工程设计/架构设计.md) · [V1 agent design](./docs/design/V1/Agent设计/Agent设计.md)

> **Delivery summary:** [中文说明](./docs/design/V1/产品设计/简要交付说明.md)

## Version Roadmap

| Version | Purpose | Role model | Status |
| --- | --- | --- | --- |
| **V1** | Deliver a login-isolated, code-owning, publicly testable product-building flow | Lead chooses `direct` or the complete Product Manager → Architect → Engineer → Data Analyst team | Railway single-replica accepted; target Linux Sandbox isolation acceptance remains |
| **V2** | Add autonomous task graphs, role subsets, parallel work, rework, and arbitration | Lead dynamically coordinates specialist Agents under Runtime policy | Implement after V1 |

The project is implemented in **V1 -> V2** order. V1 is the current development and acceptance baseline; V2 starts after V1 passes cloud acceptance.

## V1 Target Experience

1. The user signs in with a username and password; switching accounts exposes only the newly authenticated user's Projects.
2. The user talks to Lead. Lead either answers/clarifies directly or invokes the complete fixed specialist team.
3. Product Manager creates a **Blueprint** while preserving the user's product goal. A self-contained browser game, tool, board, or catalog can be supported; server auth, payments, persistent writes, external services, native runtimes, or added risk require adaptation and confirmation. Unsupported goals do not build. The user can explicitly ask PM to regenerate the requirement draft, or confirm an edited draft and move directly to Architect without a second PM pass.
4. Architect and Engineer produce **ArchitectureSpec** and **AppSpec**; Data Analyst explains immutable validation evidence.
5. Every Project owns one server-side local Git repository. Build, Edit, Resolve, and Restore versions map to Git commits.
6. The user edits through structured controls or an xterm.js + restricted Vim WebIDE whose PTY runs in an isolated Sandbox.
7. A collapsible right drawer lists real Project Repository files and uncommitted Run Artifacts through ownership-checked HTTP endpoints, supports refresh, and opens restricted Vim only after a version exists.
8. Save Version validates and builds the worktree before committing; the user then previews and explicitly publishes a selected version.

### A. Application Generation and Development

#### Step 1: Sign In and Route the Request

```text
Username/password -> authenticated user context
    |
    v
[Lead] -> direct answer / clarification
    |
    `----> fixed team when execution is required
```

#### Step 2: Design and Build

```text
Product Manager -> Blueprint -> Risk Policy
    |
    v
[Architect] -> ArchitectureSpec
    |
    v
[Engineer] -> AppSpec
    |
    v
Platform-controlled build -> local Git commit
```

#### Step 3: Validate Quality

```text
Build result -> deterministic engineering ValidationReport
    |
    v
[Data Analyst] -> DataReview
    |
    v
Interactive preview / xterm.js + restricted Vim
```

### B. Preview, Version, and Publish

```text
Interactive preview
    |
    +-- Edit or Resolve -> save new version -> validate again
    |
    +-- Restore --------> create recovery version; keep history
    |
    `-- Select version -> Publish / Update
                                  |
                                  v
                           Stable public URL
```

Lead exposes one conversation surface. If it selects `team`, specialists run as a **fixed sequential pipeline**; V1 does not dynamically select role subsets, run roles in parallel, or arbitrate rework.

## V1 Capability Map

V1 is not a collection of disconnected features. It is one complete path from an idea to a public result:

```text
Main flow:   Login -> Lead direct | fixed team -> Project -> Blueprint -> Build -> Preview
Code flow:   Project -> local Git -> xterm/Vim Sandbox -> Save Version -> commit
Change flow: Preview -> structured Edit / Vim / Resolve / Restore -> ProjectVersion
Publish flow: ProjectVersion -> Publish / Update -> Public URL

Target guarantees: user isolation | persistence | quota | Git traceability | Sandbox | recovery
```

### 1. Start: Create a Project Directly from an Idea

- **What you do:** Sign in, open Home, and tell Lead what you want to build. There is no marketing page or mode selector in front of the workspace.
- **What the system does:** Lead makes one visible choice: answer or clarify directly, or call the complete fixed team. The user may override a direct route by choosing **Call team**.
- **What remains:** A team route creates a real Project and server-side local Git repository. The request, attachment metadata, recent progress, and source history stay bound to the authenticated user.

### 2. Scope: Make Decisions Visible Without Approving Every Step

- **What you see:** Product Manager turns the request into an editable Blueprint covering the project name, pages, modules, visual direction, and data needs.
- **How the system decides:** Ollama Cloud or the deterministic Mock Provider classifies the request as `supported`, `adapted`, or `unsupported`; every result must pass the same Pydantic validation before it can change Run state.
- **How work proceeds:** A normal `supported` request continues through the fixed team without another approval. `adapted` scope, extra budget, destructive repository actions, Restore pointer changes, and public deployment changes pause for an inline risk confirmation.
- **Failure path:** After bounded model failures, the Project and input remain intact. The user can Retry, revise the request, or continue from a non-AI Starter Blueprint.

### 3. Build: See the Process and Use the Result

- **Real execution:** AppSpec packages generated HTML, CSS, and JavaScript as Project source files. The asynchronous Build Worker never installs dependencies or executes ad hoc model-generated commands.
- **Visible process:** Studio streams the current role, build progress, and errors over SSE and restores the previous state after refresh.
- **Usable result:** Viewer switches between desktop and mobile and runs the generated Web application's actual client-side interactions inside an offline sandboxed iframe.
- **Continued editing:** Copy, buttons, colors, and product images remain editable. A restricted xterm.js + Vim editor exposes only the current Project worktree inside a rootless Sandbox; it is not a login shell.

### 4. Deliver: Make Every Generation a Managed Version

- **Every change becomes a version:** Build, Edit, Resolve, and Restore each create a ProjectVersion mapped to a commit in the Project's server-side local Git repository. Restore creates a recovery commit and version without rewriting history.
- **The user controls publishing:** Publish, Update, and Unpublish require an explicit user action and support Always Latest or Specify Version. Agents never publish automatically.
- **The result is verifiable:** A Public URL opens the correct version in a clean browser without login or local project state.
- **Data remains portable:** Export returns versioned JSON while excluding secrets, absolute paths, raw conversations, and internal quota ledger entries.

### 5. Protect: Make Multi-User Public Access Real

- **Identity is enforced:** Username/password login creates a server-side session cookie. Resource ownership comes from that session, not a caller-supplied user header; signing in as another user exposes only that user's Projects.
- **State survives:** V1 stores identity, projects, sessions, quota, jobs, events, and versions in SQLite on a persistent Volume. The same single-instance storage boundary persists trusted Project Git repositories and immutable build artifacts; PostgreSQL and shared object storage belong to the horizontal-scale path.
- **Usage stays bounded:** Plans and the Usage Ledger reserve quota before an LLM call and settle afterward; concurrent sessions cannot bypass account limits.
- **Quota is application-local:** Another Atom's demo units count Provider requests for product control and are not shared with Codex usage. Ollama Cloud account limits remain an independent Provider concern.
- **Quota exhaustion has an exit:** V1 has no self-service top-up. Projects and existing results remain available for viewing/export while the demo account waits for an operator reset.
- **Execution is isolated:** Terminal and build work run on a Linux Sandbox Host with non-root containers, no network, no secrets, a read-only root filesystem, dropped capabilities, seccomp, and CPU/memory/disk/PID/time limits.
- **One product entry point:** The browser uses one HTTPS Control Plane endpoint. Railway can host that Control Plane, while the WebIDE and builds require a Linux Sandbox Host; both may also run on one Linux VM for V1.
- **Boundaries stay honest:** Cloud, Integrations, and Growth explain V1 limits without triggering unfinished authorization, payment, or third-party costs.

> **What V1 can build:** V1 accepts arbitrary product requirements and implements self-contained browser applications. Games, tools, dashboards, and catalogs preserve their original product identity. Real server auth, payments, persistent database writes, external network services, native runtimes, package installation, and unrestricted Shell execution remain explicit capability boundaries.

## V1 Delivery Milestones

| Milestone | Deliverable | Stage acceptance | Status |
| --- | --- | --- | --- |
| **M0 Design baseline** | PRD, architecture, role contracts, and bilingual README | V1/V2 boundaries agree and critical state, data, and error contracts are traceable | Complete |
| **M1 Runtime foundation** | React workspace, FastAPI, persistence, quota, events, and leased Build Jobs | A Project can be created and reopened; persisted jobs recover after restart | Implemented locally |
| **M2 Agent flow** | Real Lead `direct/team` routing, fixed specialist team, structured artifacts, and risk policy | Direct never mutates a repository; Team stages persist inspectable artifacts; only risk events block | Lead/risk redesign pending implementation; current fixed pipeline works |
| **M3 Identity and source ownership** | Session Gateway, user isolation, one local Git repository per Project, and commit/version mapping | Two users cannot read each other's resources; every saved version resolves to a Project commit | Design complete; implementation pending |
| **M4 Studio and Sandbox** | Preview, structured editing, xterm.js + Vim, save/build/validate, and Restore | Terminal sees only its leased worktree; escape/network/resource tests pass; saved source is recoverable | Preview/editing works; WebIDE/Sandbox pending |
| **M5 Public delivery** | Publish/Unpublish, stable route, Export, automated tests, and cloud deployment | Main and negative paths pass; a clean browser opens the selected public version | Routes/tests implemented; public deployment pending |

### Final Acceptance Baseline

#### 1. Functional Loop

- The Golden Path completes successfully 5/5 times against clean data.
- A clean browser can open the public URL, and it follows Always Latest and Specify Version pointers exactly.

#### 2. Stability and Data Isolation

- Project, Session, version, and publish state recover in 5/5 refresh tests.
- Cross-user, cross-project, and cross-session resource/event leakage remains at zero.

#### 3. Responsiveness and State Visibility

- Run/Build Job creation returns an identifier within one second, and the first user-visible event appears within two seconds of acceptance.
- Lead routing, required risk approvals, unsupported input, quota exhaustion, LLM failures, build failures, and queued work show explicit states without fake progress.

#### 4. User Experience

- Every visible control has working behavior, a disabled reason, or a capability-boundary response.
- Desktop and mobile layouts have no content or control overlap that blocks interaction.

#### 5. Data Contract and Security

- Export JSON follows the defined contract.
- Exported data excludes secrets, credentials, absolute paths, raw conversations, and internal quota ledger entries.
- Every ProjectVersion resolves to a commit in its owning Project repository; Sandbox worktrees cannot access `.git`, other Projects, credentials, the host network, or the container runtime.

## Design Principles

### 1. Product Layer: One Lead, Confirmation Only at Real Risk

The user talks to one Lead. Lead either answers/clarifies or invokes the complete team. Blueprint remains an inspectable product contract, but it is not a blanket approval gate: confirmation appears only for adapted scope, additional budget, destructive source actions, pointer changes, and public deployment actions.

### 2. Collaboration Layer: Roles Handoff Artifacts, Not Roleplay Messages

Lead, Product Manager, Architect, Engineer, and Data Analyst progressively reduce different kinds of uncertainty:

```text
Coordination layer User message       -> LeadDecision      direct answer or fixed-team route
Product layer      Prompt             -> Blueprint         decide what to build
Architecture layer Blueprint          -> ArchitectureSpec  define routes, data, and presentation bounds
Engineering layer  ArchitectureSpec   -> AppSpec + Report  build and validate platform behavior
Data layer         AppSpec + Report   -> DataReview        check data and explain evidence
Delivery layer     DataReview         -> ProjectVersion    preserve, restore, and publish the result
```

Every specialist handoff is schema-validated, persisted, and inspectable. Lead is a real V1 Agent, but its authority is deliberately narrow: `direct` or `team`. The Runtime, not Lead, owns risk checks, state transitions, retries, and failure closure.

### 3. Execution Layer: Models Decide, the Platform Controls Authority

The LLM interprets requirements and makes structured decisions, but it cannot install dependencies, alter build commands, execute arbitrary shell input, or publish automatically. The platform owns identity, repositories, renderer, build worker, Sandbox, quota transactions, and publishing. The WebIDE launches fixed Vim inside a restricted worktree, not a general shell.

### 4. State Layer: Runs, Versions, and Publishing Stay Separate

A failed Agent Run must not damage an existing version. An edit must not silently change a pinned public version, and Restore must not erase history. Project, Run, ProjectVersion, Git commit, and publish pointers are modeled separately so every source and deployment change is traceable and recoverable.

### 5. Evolution Layer: Prove the Loop in V1, Add Autonomy in V2

V1 proves whether identity isolation, Lead routing, structured team execution, risk confirmation, source editing, build, versioning, and publishing work as one usable loop. V2 keeps these contracts and upgrades Lead to dynamic task graphs, role subsets, parallel work, rework, and arbitration.

## Implementation Approach and Key Trade-offs

| Decision | Why | Benefit | Cost and boundary |
| --- | --- | --- | --- |
| Real LLM + structured contracts + offline Web Runtime | Prove real requirement understanding while controlling execution risk in a shared cloud environment | Blueprint/AppSpec respond to input and builds remain verifiable | V1 supports different product goals as self-contained browser apps, not arbitrary stacks, server integrations, or free-form execution |
| Lead routing + risk-driven Approval | Lead distinguishes answer/clarify from team execution; supported offline Web work proceeds within base scope and budget | Keeps one conversational entry while matching confirmation to actual risk instead of every stage | Implemented; adapted capabilities, additional budget, destructive source actions, and public deployment changes still require explicit confirmation |
| Username/password Session Gateway + user-level tenant | Project ownership must be derived from trusted identity, not a caller header | Switching accounts produces testable Project isolation | V1 has no Organization, membership, or shared Project roles |
| One server-side local Git repository per Project | A Project needs durable, inspectable source ownership | ProjectVersion maps to a commit without requiring GitHub OAuth | V1 has no remote, push, pull, or user-machine repository |
| xterm.js + fixed Vim in a rootless Sandbox | Users need source-level editing without exposing a host shell | Familiar terminal editing with bounded filesystem and resources | Requires a Linux Sandbox Host; it is not a Claude Code-like terminal Agent |
| Asynchronous Build Job + restricted Web source packaging | Builds must not block HTTP requests or execute ad hoc model-generated commands | Jobs are recoverable and source/preview boundaries remain inspectable | V1 writes only self-contained HTML/CSS/JS and rejects network, dynamic imports, dependency installation, and Shell execution; initial build concurrency is one |
| One API process + one in-process Worker for the current slice | Local and Railway V1 need durable correctness before horizontal scale | SQLite checkpoints on a persistent Volume provide restart recovery without a queue cluster | No horizontal replicas, independent Worker cluster, LISTEN/NOTIFY, or message queue in V1 |
| Real Plan/Quota/Ledger without payment integration | Multiple users and sessions must share and settle account usage correctly | Concurrent calls cannot overspend and model usage is auditable | V1 excludes Stripe, wallet, top-up, and invoicing |

## Current Single-Instance Decision List

### Implemented in the runnable slice

- `POST /api/runs` commits and returns before Blueprint generation; an in-process background task uses a fresh database Session, and startup recovers interrupted `product_running` Runs.
- Supported Blueprints auto-queue. Adapted approval uses an `awaiting_approval -> build_queued` status CAS; confirming an edited PM requirement creates one new Run with the confirmed Blueprint and skips a second PM pass. Unique Approval and BuildJob constraints prevent duplicate queueing.
- A successful Agent stage commits its Artifact and Provider usage settlement together. Worker recovery reuses committed stage Artifacts, aligns terminal Jobs without replay, and reuses an existing build version.
- Failed calls settle only observed Provider requests and release the unused reservation; non-LLM exceptions also clear outstanding reservation.
- Preview queries join through Project ownership. Outside tests, an unknown `X-User-ID` returns 401 instead of creating a full-quota account.
- Validator checks Blueprint page coverage, canonical mapped-requirement evidence, ArchitectureSpec/AppSpec visual-token alignment, and color contrast.
- SSE keeps database polling for the single-instance baseline but reuses one read Session per connection.

### Confirmed design evolution: from a fixed Blueprint gate to Lead + Risk Policy

The original V1 interaction sent every non-`unsupported` Blueprint to `awaiting_approval`. Later design work introduced Lead as the single user-facing role and changed Approval from a mandatory pipeline stage into a risk-driven guardrail:

```text
User message -> LeadDecision
                 |-- direct -> answer / clarify
                 `-- team -> Product Manager -> Blueprint -> Risk Policy
                                                       |-- supported + base budget -> continue
                                                       |-- adapted / added risk -> Approval
                                                       `-- unsupported -> stop original goal
                                                              `-> PM requirement rewrite -> user confirmation -> new Run at Architect
```

This evolution is implemented. It preserves Blueprint as a persisted, inspectable contract while removing redundant confirmation from supported self-contained Web work inside the base budget. `adapted` capabilities, additional budget, later scope changes, destructive source actions, and public deployment changes still require Approval.

The benefit is a shorter Golden Path and a clearer one-Lead interaction model. The cost is losing the original mandatory pause for pre-build Blueprint editing; V1 handles later corrections through inspectable Artifacts, Edit/Follow-up, and new versions. Unsupported goals are not silently rebranded as supported applications: the original Run remains stopped, and the user must explicitly accept the alternative goal.

### Still required for V1 acceptance

- Validate the restricted Vim container, network denial, resource limits, and worktree cleanup on the target Linux Sandbox Host.
- Complete single-replica Railway deployment, restart verification against SQLite on a persistent Volume, and public-URL acceptance in a clean browser.
- Persist a Project conversation thread: associate Lead clarification, team build discussion, and Follow-up messages through `project_id / run_id / thread_id`. Today Lead messages are user-level, while build Prompts and Artifacts belong to Projects.

### Explicitly deferred beyond single-instance V1

- A full Token/JWT/OAuth authentication platform beyond the V1 server-side Session Gateway.
- PostgreSQL LISTEN/NOTIFY or message-queue SSE, a persistent queue service, an independent Worker cluster, cross-instance lease-owner fencing, and distributed optimistic concurrency control.
- Horizontal API/Worker replicas and the shared-object-storage architecture they require.

### Valid later optimizations, not current correctness work

- Multi-tenant Sandbox pooling, capacity scheduling, stronger container/MicroVM isolation, and moving immutable publish artifacts to object storage.
- Provider idempotency keys where supported, closing the narrow crash window between an external response and the Artifact transaction commit.
- Edit/Restore billing policy, Export pagination/streaming, and SPA-fallback 404 hardening.

See the [V1 architecture design](./docs/design/V1/工程设计/架构设计.md) for components, states, data, security, and deployment details. See the [V1 agent design](./docs/design/V1/Agent设计/Agent设计.md) for execution semantics, human-in-the-loop, context, tools, sandbox boundaries, validation, and repair.

## V1 Deployment and Access Architecture

Two operations are separate: **the developer deploys the Another Atom platform**, while **a user publishes a generated application version inside the platform**. The first provisions a trusted Control Plane and Sandbox Host; the second changes a product deployment pointer.

```text
Platform deployment

Developer -- git push --> GitHub
                         |
                         +--> Railway or Linux VM: Control Plane
                         |
                         `--> Linux Sandbox Host: Git / Vim / Build

User access and generated-app publishing

User browser -- HTTPS/WSS --> Control Plane public domain
                         |
             +-----------+----------------+
             | React Visual Studio        |
             | FastAPI REST + SSE + WSS   |----> Ollama Cloud / Mock
             | Session Gateway + Lead     |
             | Repository Service         |
             | Preview / Published Routes |
             +-----------+----------------+
                         |
                +--------+----------------+
                |                  |
                v                  v
          PostgreSQL        Linux Sandbox Host
       users / sessions /   local Git / worktrees /
       projects / quota /   Vim PTY / builds / artifacts
       jobs / versions

User selects ProjectVersion -- Publish / Update --> Published Route
                                                    |
                                                    v
                                            Stable public URL
```

Railway can host the Control Plane, but Railway alone is not assumed to provide the required terminal isolation. A Linux host with rootless containers/namespaces/cgroups is required for real WebIDE and Build Sandboxes. A single Linux VM may host both layers in V1 if network and privilege boundaries remain explicit.

## Not in V1

- Terminal CLI, login shell, or execution against a repository on the user's computer.
- GitHub/GitLab remote integration, push/pull, SSH keys, or repository sharing.
- Runtime dependency installation or arbitrary code execution.
- Arbitrary technology stacks or generated backends.
- Autonomous or parallel multi-agent collaboration, which is planned for V2.
- Arbitrary providers or unrestricted model identifiers; V1 exposes only the configured DeepSeek allowlist.
- Generated-app authentication, database, commerce, or payment systems.
- Stripe billing, wallet, top-up, or invoicing.

## Version Implementation Plan

### V2: Autonomous Multi-Agent (Planned Implementation)

V2 is the next implementation version after V1, not an optional showcase direction. It upgrades the V1 Lead from binary routing to dynamic task graphs, independent specialist contexts, role subsets, selective parallel execution, structured rework, arbitration, and run-level budgets. Product, engineering, and behavior baselines are defined in the [V2 PRD](./docs/design/V2/产品设计/产品需求.md), [V2 architecture](./docs/design/V2/工程设计/架构设计.md), and [V2 agent design](./docs/design/V2/Agent设计/Agent设计.md).

### Unassigned Version: Local Agent Runtime

A Claude Code-like runtime could later work with local files, Git, shell, npm, and a localhost Visual Studio. This direction is not implemented and has not yet been assigned to a release.

## Project Status

Completed:

- [x] Atoms public-feature analysis
- [x] V1 product requirements and acceptance criteria
- [x] V1 architecture and deployment design
- [x] V2 PRD, architecture, and agent design drafts
- [x] Bilingual README, evaluation evidence, and project implementation constraints
- [x] FastAPI API, SQLAlchemy persistence, quota ledger, events, versions, and publication routes
- [x] React Studio, generated HTML/CSS/JavaScript, offline sandboxed preview, desktop/mobile viewing, editing, and restore
- [x] Mock role Pipeline with schema validation and bounded failure paths
- [x] Ollama Cloud Provider, DeepSeek model selector, Provider usage ledger, and bounded retry
- [x] Ollama 30-second timeout with optional DeepSeek official API fallback, visible provider-switch state, and combined usage settlement
- [x] Persistent single-concurrency Build Worker with database lease recovery
- [x] Approval CAS, restart-safe stage checkpoints, quota release/settlement, owned Preview, asynchronous Blueprint generation, and contract-aware Validator tests
- [x] Username/password Session Gateway, two-user isolation, real Lead `direct/team` routing, Project Git, refreshable Repository/Artifact tree, and restricted Vim/Sandbox Gateway
- [x] Unit/integration tests, including five consecutive Golden Path runs
- [x] Dockerfile and Railway configuration

Not completed:

- [ ] Arbitrary generated source trees and per-project `npm run build`; current editable source is a validated `app-spec.json` rendered by the shared React runtime
- [ ] Linux-host acceptance for the restricted Vim container and Sandbox isolation controls
- [ ] Project conversation thread persistence for Lead clarification and Follow-up history
- [ ] Resolve workflow, project rename/delete, and attachment file upload
- [ ] Railway deployment and public URL
- [ ] V2 sandbox/model ADRs, load-tested budgets, and security baseline confirmation
- [ ] V2 autonomous multi-agent implementation, testing, and deployment

### Pre-Submission Check

- Add the online Demo URL to the README and challenge result form.
- Keep the GitHub repository public and complete the Golden Path in a clean browser.
- State whether a demo account is required; explicitly say when no account is needed.
- Update completed and incomplete status without presenting planned features as implemented.
- Record known boundaries, failure cases, Railway resource profile, and load-test results.

## Evaluation Evidence

| Dimension | Evidence required from the README and implementation |
| --- | --- |
| Completeness | Golden Path, negative paths, persistence recovery, public Preview/Publish, and automated test results |
| Engineering judgment | Technology choices, contracts, asynchronous builds, quota transactions, security boundaries, and explicit trade-offs |
| User experience | One Lead entry point, risk-driven confirmation, live state, interactive Preview/WebIDE, recoverable versions, and actionable errors |
| Innovation | Inspectable artifact chain, user-isolated local Git ownership, restricted terminal editing, and versioned publishing loop |
| Deliverability | GitHub source, bilingual README, reproducible run steps, Railway URL, and known boundaries |

## Links

- Source repository: [github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- Online version: Railway deployment and public access have been accepted; the service domain is managed by the Railway deployment environment.
- [Discussion documentation index](./docs/discussion/README.md)
- [Design documentation index](./docs/design/README.md)
- [Overall product goal and positioning (Chinese)](./docs/design/整体/产品设计/整体产品目标与定位.md)
- [V1 product requirements](./docs/design/V1/产品设计/产品需求.md)
- [V1 architecture design](./docs/design/V1/工程设计/架构设计.md)
- [V1 agent design](./docs/design/V1/Agent设计/Agent设计.md)
- [Local run and Railway deployment guide (Chinese)](./docs/design/V1/工程设计/本地运行与Railway部署.md)
- [Review documentation index](./docs/review/README.md)
- [V1 implementation inspection](./docs/review/V1/综合评审/2026-07-11-首次可运行版本检查.md)
- [V2 product requirements](./docs/design/V2/产品设计/产品需求.md)
- [V2 architecture design](./docs/design/V2/工程设计/架构设计.md)
- [V2 agent design](./docs/design/V2/Agent设计/Agent设计.md)
- [Atoms reference analysis](./docs/design/整体/参考资料/Atoms参考产品分析.md)

## Appendix

- Original product reference: [Atoms](https://atoms.dev/)
