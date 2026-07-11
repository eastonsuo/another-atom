# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> Turn a product idea into a web prototype that can be reviewed, refined, versioned, and published.

Another Atom is designed as an AI agent workspace for creating web product prototypes from natural-language requirements. A user describes an idea, reviews the proposed product plan, and follows the result through design, implementation, validation, revision, and publishing.

The project is inspired by [Atoms](https://atoms.dev/), but it is independently designed and implemented. It is not an Atoms fork and does not use Atoms source code or internal infrastructure.

> **Current status:** A runnable V1 vertical slice is implemented with Ollama Cloud and Mock providers. DeepSeek V4 Pro is the default real model, with V4 Flash selectable per Run. Local generation, preview, editing, versioning, publishing routes, persistence, quota, and automated tests are available. Railway public deployment is not complete.

> **Current runtime boundary:** The runnable slice is single-instance only. Blueprint generation now runs after `POST /api/runs` through an in-process background task; approval uses a database status CAS; committed stage artifacts, quota settlement, Build Jobs, and build versions are replay-safe across Worker restart. The slice still requires explicit Blueprint approval—risk-only confirmation remains the target design pending Lead/Risk Policy implementation. Production no longer creates arbitrary users from unknown `X-User-ID` values, but the real Session Gateway is still pending, so this header remains a temporary demo identity mechanism rather than production authentication.

> **Approved V1 design expansion, not implemented yet:** username/password Session Gateway with user-level Project isolation; a real Lead Agent that routes each message to `direct` or the complete fixed team; one server-side local Git repository per Project; and an xterm.js + restricted Vim WebIDE backed by an isolated Linux Sandbox Host.

> **Design baselines:** [V1 engineering architecture](./docs/v1/architecture-design.md) · [V1 agent design](./docs/v1/agent-design.md)

## Version Roadmap

| Version | Purpose | Role model | Status |
| --- | --- | --- | --- |
| **V1** | Deliver a login-isolated, code-owning, publicly testable product-building flow | Lead chooses `direct` or the complete Product Manager → Architect → Engineer → Data Analyst team | Existing vertical slice works; Gateway/Git/WebIDE/Sandbox design is pending implementation |
| **V2** | Add autonomous task graphs, role subsets, parallel work, rework, and arbitration | Lead dynamically coordinates specialist Agents under Runtime policy | Implement after V1 |

The project is implemented in **V1 -> V2** order. V1 is the current development and acceptance baseline; V2 starts after V1 passes cloud acceptance.

## V1 Target Experience

1. The user signs in with a username and password; switching accounts exposes only the newly authenticated user's Projects.
2. The user talks to Lead. Lead either answers/clarifies directly or invokes the complete fixed specialist team.
3. Product Manager creates a **Blueprint**. Normal supported work proceeds without a redundant approval; scope adaptation, extra budget, destructive repository actions, and public changes request inline confirmation.
4. Architect and Engineer produce **ArchitectureSpec** and **AppSpec**; Data Analyst explains immutable validation evidence.
5. Every Project owns one server-side local Git repository. Build, Edit, Resolve, and Restore versions map to Git commits.
6. The user edits through structured controls or an xterm.js + restricted Vim WebIDE whose PTY runs in an isolated Sandbox.
7. Save Version validates and builds the worktree before committing; the user then previews and explicitly publishes a selected version.

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

- **Real execution:** AppSpec enters the controlled React renderer. The asynchronous Build Worker uses only the fixed template and preinstalled dependencies and never executes ad hoc model-generated commands.
- **Visible process:** Studio streams the current role, build progress, and errors over SSE and restores the previous state after refresh.
- **Usable result:** Viewer switches between desktop and mobile. Home, Catalog, and Product pages and their core interactions actually run instead of appearing as static screenshots.
- **Continued editing:** Copy, buttons, colors, and product images remain editable. A restricted xterm.js + Vim editor exposes only the current Project worktree inside a rootless Sandbox; it is not a login shell.

### 4. Deliver: Make Every Generation a Managed Version

- **Every change becomes a version:** Build, Edit, Resolve, and Restore each create a ProjectVersion mapped to a commit in the Project's server-side local Git repository. Restore creates a recovery commit and version without rewriting history.
- **The user controls publishing:** Publish, Update, and Unpublish require an explicit user action and support Always Latest or Specify Version. Agents never publish automatically.
- **The result is verifiable:** A Public URL opens the correct version in a clean browser without login or local project state.
- **Data remains portable:** Export returns versioned JSON while excluding secrets, absolute paths, raw conversations, and internal quota ledger entries.

### 5. Protect: Make Multi-User Public Access Real

- **Identity is enforced:** Username/password login creates a server-side session cookie. Resource ownership comes from that session, not a caller-supplied user header; signing in as another user exposes only that user's Projects.
- **State survives:** PostgreSQL stores identity, projects, sessions, quota, jobs, events, and versions. The Sandbox Host persists trusted local Git repositories and immutable build artifacts.
- **Usage stays bounded:** Plans and the Usage Ledger reserve quota before an LLM call and settle afterward; concurrent sessions cannot bypass account limits.
- **Quota is application-local:** Another Atom's demo units count Provider requests for product control and are not shared with Codex usage. Ollama Cloud account limits remain an independent Provider concern.
- **Quota exhaustion has an exit:** V1 has no self-service top-up. Projects and existing results remain available for viewing/export while the demo account waits for an operator reset.
- **Execution is isolated:** Terminal and build work run on a Linux Sandbox Host with non-root containers, no network, no secrets, a read-only root filesystem, dropped capabilities, seccomp, and CPU/memory/disk/PID/time limits.
- **One product entry point:** The browser uses one HTTPS Control Plane endpoint. Railway can host that Control Plane, while the WebIDE and builds require a Linux Sandbox Host; both may also run on one Linux VM for V1.
- **Boundaries stay honest:** Cloud, Integrations, and Growth explain V1 limits without triggering unfinished authorization, payment, or third-party costs.

> **What V1 can build:** V1 focuses on controlled product catalog and storefront sites. `unsupported` requests stop before build; `adapted` requests show what is mapped or omitted and require user approval before continuing.

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
| Real LLM + structured contracts + deterministic renderer | Prove real requirement understanding while controlling execution risk in a shared cloud environment | Blueprint/AppSpec respond to input and builds remain verifiable | V1 does not support arbitrary stacks or free-form code execution |
| Username/password Session Gateway + user-level tenant | Project ownership must be derived from trusted identity, not a caller header | Switching accounts produces testable Project isolation | V1 has no Organization, membership, or shared Project roles |
| One server-side local Git repository per Project | A Project needs durable, inspectable source ownership | ProjectVersion maps to a commit without requiring GitHub OAuth | V1 has no remote, push, pull, or user-machine repository |
| xterm.js + fixed Vim in a rootless Sandbox | Users need source-level editing without exposing a host shell | Familiar terminal editing with bounded filesystem and resources | Requires a Linux Sandbox Host; it is not a Claude Code-like terminal Agent |
| Asynchronous Build Job + fixed template and dependencies | Builds must not block HTTP requests or execute ad hoc model-generated commands | Jobs are recoverable and resource/failure scope stays bounded | Generation is limited by template capability; initial build concurrency is one |
| One API process + one in-process Worker for the current slice | Local and Railway V1 need durable correctness before horizontal scale | PostgreSQL Job/Artifact checkpoints provide restart recovery without a queue cluster | No horizontal replicas, independent Worker cluster, LISTEN/NOTIFY, or message queue in V1 |
| Real Plan/Quota/Ledger without payment integration | Multiple users and sessions must share and settle account usage correctly | Concurrent calls cannot overspend and model usage is auditable | V1 excludes Stripe, wallet, top-up, and invoicing |

## Current Single-Instance Decision List

### Implemented in the runnable slice

- `POST /api/runs` commits and returns before Blueprint generation; an in-process background task uses a fresh database Session, and startup recovers interrupted `product_running` Runs.
- Blueprint approval uses an `awaiting_approval -> build_queued` status CAS. Unique Approval and BuildJob constraints prevent duplicate queueing.
- A successful Agent stage commits its Artifact and Provider usage settlement together. Worker recovery reuses committed stage Artifacts, aligns terminal Jobs without replay, and reuses an existing build version.
- Failed calls settle only observed Provider requests and release the unused reservation; non-LLM exceptions also clear outstanding reservation.
- Preview queries join through Project ownership. Outside tests, an unknown `X-User-ID` returns 401 instead of creating a full-quota account.
- Validator checks Blueprint page coverage, canonical mapped-requirement evidence, ArchitectureSpec/AppSpec visual-token alignment, and color contrast.
- SSE keeps database polling for the single-instance baseline but reuses one read Session per connection.

### Still required for V1 acceptance

- Replace the temporary identity header with the username/password Session Gateway and prove two-user isolation. The current rejection of unknown IDs is hardening, not complete authentication.
- Implement per-Project source materialization, commit/version mapping, and a rootless per-user/per-Project Sandbox before exposing xterm.js/Vim or real project builds.
- Complete Railway deployment, restart verification against PostgreSQL and persistent storage, and public-URL acceptance in a clean browser.

### Explicitly deferred beyond single-instance V1

- A full Token/JWT/OAuth authentication platform beyond the V1 server-side Session Gateway.
- PostgreSQL LISTEN/NOTIFY or message-queue SSE, a persistent queue service, an independent Worker cluster, cross-instance lease-owner fencing, and distributed optimistic concurrency control.
- Horizontal API/Worker replicas and the shared-object-storage architecture they require.

### Valid later optimizations, not current correctness work

- Multi-tenant Sandbox pooling, capacity scheduling, stronger container/MicroVM isolation, and moving immutable publish artifacts to object storage.
- Provider idempotency keys where supported, closing the narrow crash window between an external response and the Artifact transaction commit.
- Edit/Restore billing policy, Export pagination/streaming, and SPA-fallback 404 hardening.

See the [V1 architecture design](./docs/v1/architecture-design.md) for components, states, data, security, and deployment details. See the [V1 agent design](./docs/v1/agent-design.md) for execution semantics, human-in-the-loop, context, tools, sandbox boundaries, validation, and repair.

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

V2 is the next implementation version after V1, not an optional showcase direction. It upgrades the V1 Lead from binary routing to dynamic task graphs, independent specialist contexts, role subsets, selective parallel execution, structured rework, arbitration, and run-level budgets. Product, engineering, and behavior baselines are defined in the [V2 PRD](./docs/v2/another-atom-v2-prd.md), [V2 architecture](./docs/v2/architecture-design.md), and [V2 agent design](./docs/v2/agent-design.md).

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
- [x] React Studio, interactive controlled renderer, desktop/mobile preview, editing, and restore
- [x] Mock role Pipeline with schema validation and bounded failure paths
- [x] Ollama Cloud Provider, DeepSeek model selector, Provider usage ledger, and bounded retry
- [x] Persistent single-concurrency Build Worker with database lease recovery
- [x] Approval CAS, restart-safe stage checkpoints, quota release/settlement, owned Preview, asynchronous Blueprint generation, and contract-aware Validator tests
- [x] Unit/integration tests, including five consecutive Golden Path runs
- [x] Dockerfile and Railway configuration

Not completed:

- [ ] Per-project source materialization and `npm run build`; the current generated app is a validated AppSpec rendered by the shared React runtime
- [ ] Username/password Session Gateway and two-user isolation acceptance
- [ ] Real Lead `direct/team` routing and risk-driven inline approvals
- [ ] ProjectRepository provisioning and ProjectVersion-to-commit mapping
- [ ] xterm.js + restricted Vim, Terminal Gateway, and rootless Sandbox Host
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
- Online version: not deployed yet
- [V1 product requirements](./docs/v1/another-atom-v1-prd.md)
- [V1 architecture design](./docs/v1/architecture-design.md)
- [V1 agent design](./docs/v1/agent-design.md)
- [Local run and Railway deployment guide (Chinese)](./docs/v1/local-run-and-railway-deployment.md)
- [V1 implementation review](./review/2026-07-11-v1-implementation-review.md)
- [V2 product requirements](./docs/v2/another-atom-v2-prd.md)
- [V2 architecture design](./docs/v2/architecture-design.md)
- [V2 agent design](./docs/v2/agent-design.md)
- [Atoms reference analysis](./docs/reference/atoms-reference-analysis.md)

## Appendix

- Original product reference: [Atoms](https://atoms.dev/)
