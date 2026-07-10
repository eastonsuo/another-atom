# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> Turn a product idea into a web prototype that can be reviewed, refined, versioned, and published.

Another Atom is designed as an AI agent workspace for creating web product prototypes from natural-language requirements. A user describes an idea, reviews the proposed product plan, and follows the result through design, implementation, validation, revision, and publishing.

The project is inspired by [Atoms](https://atoms.dev/), but it is independently designed and implemented. It is not an Atoms fork and does not use Atoms source code or internal infrastructure.

> **Current status:** A runnable V1 vertical slice is implemented with Ollama Cloud and Mock providers. DeepSeek V4 Pro is the default real model, with V4 Flash selectable per Run. Local generation, preview, editing, versioning, publishing routes, persistence, quota, and automated tests are available. Railway public deployment is not complete.

> **Design baselines:** [V1 engineering architecture](./docs/v1/architecture-design.md) · [V1 agent design](./docs/v1/agent-design.md)

## Version Roadmap

| Version | Purpose | Role model | Status |
| --- | --- | --- | --- |
| **V1** | Deliver one complete, publicly testable product-building flow | Team Leader, Product Manager, Architect, Engineer, and Data Analyst run in a fixed sequence | Local vertical slice implemented; hardening and cloud deployment remain |
| **V2** | Add autonomous collaboration, dynamic delegation, rework, and arbitration | Team Leader coordinates Product Manager, Architect, Engineer, and Data Analyst agents | Implement after V1 |

The project is implemented in **V1 -> V2** order. V1 is the current development and acceptance baseline; V2 starts after V1 passes cloud acceptance.

## V1 Target Experience

1. The user describes a product and can attach reference files.
2. Product Manager creates a **Blueprint**, an editable product plan containing pages, modules, visual direction, and data needs.
3. The user reviews and approves the Blueprint. Building cannot start without this approval.
4. Architect produces an **ArchitectureSpec** covering routes, data boundaries, visual tokens, and interaction structure.
5. Engineer produces an **AppSpec** and owns deterministic build and interaction validation.
6. Data Analyst checks catalog data completeness and explains the immutable engineering validation evidence.
7. The user previews the result, requests changes, restores an earlier version, exports project data, and publishes a selected version.

### A. Application Generation and Development

#### Step 1: Confirm the Requirement

```text
User prompt
    |
    v
[Team Leader] -> fixed orchestration
    |
    v
[Product Manager]
    |
    v
Blueprint
    |
    v
User review and approval
```

#### Step 2: Design and Build

```text
Approved Blueprint
    |
    v
[Architect] -> ArchitectureSpec
    |
    v
[Engineer] -> AppSpec
    |
    v
Platform-controlled React build
```

#### Step 3: Validate Quality

```text
Build result -> deterministic engineering ValidationReport
    |
    v
[Data Analyst] -> DataReview
    |
    v
Interactive preview
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

Team Mode is a **sequential role pipeline**. The roles do not run in parallel or delegate work dynamically in V1. Every handoff produces an artifact the user or reviewer can inspect.

## V1 Capability Map

V1 is not a collection of disconnected features. It is one complete path from an idea to a public result:

```text
Main flow:   Prompt + attachments -> Project -> Blueprint -> approval -> role pipeline -> Preview
Change flow: Preview -> Edit / Resolve / Restore -> ProjectVersion
Publish flow: ProjectVersion -> Publish / Update -> Public URL

End-to-end guarantees: persistence | quota | SSE events | recovery | Railway deployment
```

### 1. Start: Create a Project Directly from an Idea

- **What you do:** Open Home, write a multiline request, add reference attachments, and select Engineer Mode or Team Mode without first crossing a marketing page.
- **What the system does:** Empty requests, in-progress attachments, and submission failures show explicit states. A successful submission creates a real Project rather than a conversation that disappears when closed.
- **What remains:** The request, attachment metadata, and recent progress stay with the Project, which can later be reopened, renamed, or deleted from Projects.

### 2. Confirm: Agree on the Target Before Building

- **What you see:** Product Manager turns the request into an editable Blueprint covering the project name, pages, modules, visual direction, and data needs.
- **How the system decides:** Ollama Cloud or the deterministic Mock Provider classifies the request as `supported`, `adapted`, or `unsupported`; every result must pass the same Pydantic validation before it can change Run state.
- **How work proceeds:** Architect, Engineer, and Data Analyst produce ArchitectureSpec, AppSpec, and DataReview only after user approval. A stage cannot claim completion without approval and a real artifact.
- **Failure path:** After bounded model failures, the Project and input remain intact. The user can Retry, revise the request, or continue from a non-AI Starter Blueprint.

### 3. Build: See the Process and Use the Result

- **Real execution:** AppSpec enters the controlled React renderer. The asynchronous Build Worker uses only the fixed template and preinstalled dependencies and never executes ad hoc model-generated commands.
- **Visible process:** Studio streams the current role, build progress, and errors over SSE and restores the previous state after refresh.
- **Usable result:** Viewer switches between desktop and mobile. Home, Catalog, and Product pages and their core interactions actually run instead of appearing as static screenshots.
- **Continued editing:** Copy, buttons, colors, and product images remain editable. Console exposes actionable errors, and every Resolve leaves a repair record.

### 4. Deliver: Make Every Generation a Managed Version

- **Every change becomes a version:** Build, Edit, Resolve, and Restore each create a ProjectVersion. Restore creates a recovery version without overwriting history.
- **The user controls publishing:** Publish, Update, and Unpublish require an explicit user action and support Always Latest or Specify Version. Agents never publish automatically.
- **The result is verifiable:** A Public URL opens the correct version in a clean browser without login or local project state.
- **Data remains portable:** Export returns versioned JSON while excluding secrets, absolute paths, raw conversations, and internal quota ledger entries.

### 5. Protect: Make Multi-User Public Access Real

- **State survives:** PostgreSQL stores users, projects, sessions, quota, build jobs, events, and versions, with recovery after Railway process restarts.
- **Usage stays bounded:** Plans and the Usage Ledger reserve quota before an LLM call and settle afterward; concurrent sessions cannot bypass account limits.
- **Quota is application-local:** Another Atom's demo units count Provider requests for product control and are not shared with Codex usage. Ollama Cloud account limits remain an independent Provider concern.
- **Quota exhaustion has an exit:** V1 has no self-service top-up. Projects and existing results remain available for viewing/export while the demo account waits for an operator reset.
- **One HTTPS entry point:** Railway hosts the web service, asynchronous builds, and published results behind the same domain.
- **Boundaries stay honest:** Cloud, Integrations, and Growth explain V1 limits without triggering unfinished authorization, payment, or third-party costs.

> **What V1 can build:** V1 focuses on controlled product catalog and storefront sites. `unsupported` requests stop before build; `adapted` requests show what is mapped or omitted and require user approval before continuing.

## V1 Delivery Milestones

| Milestone | Deliverable | Stage acceptance | Status |
| --- | --- | --- | --- |
| **M0 Design baseline** | PRD, architecture, role contracts, and bilingual README | V1/V2 boundaries agree and critical state, data, and error contracts are traceable | Complete |
| **M1 Cloud foundation** | React workspace, FastAPI, PostgreSQL-compatible models, and Project/Session/Quota state | A project can be created and reopened; persisted jobs recover after restart | Implemented locally |
| **M2 Generation flow** | Prompt, attachment metadata, Blueprint approval, fixed role sequence, per-Run model selection, and persisted Build Job | No build before approval; every stage has a schema-validated artifact; failures are visible | Implemented with Ollama Cloud + Mock |
| **M3 Studio loop** | Desktop/mobile preview, editing, versions, and Restore | Core routes and interactions work; Build/Edit/Restore create recoverable versions | In progress; Resolve remains |
| **M4 Publish and hardening** | Publish/Unpublish, stable route, Export, automated tests, and Railway deployment | Main flow and negative paths pass locally; public cloud URL passes acceptance | In progress; Railway deployment remains |

### Final Acceptance Baseline

#### 1. Functional Loop

- The Golden Path completes successfully 5/5 times against clean data.
- A clean browser can open the public URL, and it follows Always Latest and Specify Version pointers exactly.

#### 2. Stability and Data Isolation

- Project, Session, version, and publish state recover in 5/5 refresh tests.
- Cross-project and cross-session event leakage remains at zero.

#### 3. Responsiveness and State Visibility

- Run/Build Job creation returns an identifier within one second, and the first user-visible event appears within two seconds of acceptance.
- Unapproved Blueprints, unsupported input, quota exhaustion, LLM failures, and build failures show explicit states without fake progress.

#### 4. User Experience

- Every visible control has working behavior, a disabled reason, or a capability-boundary response.
- Desktop and mobile layouts have no content or control overlap that blocks interaction.

#### 5. Data Contract and Security

- Export JSON follows the defined contract.
- Exported data excludes secrets, credentials, absolute paths, raw conversations, and internal quota ledger entries.

## Design Principles

### 1. Product Layer: Approve the Target Before Spending Build Resources

Natural-language requests can be ambiguous or outside V1 scope. Blueprint turns model interpretation into a product plan the user can edit and approve. Approval is both a product decision gate and a hard precondition for creating a Build Job.

### 2. Collaboration Layer: Roles Handoff Artifacts, Not Roleplay Messages

Team Leader, Product Manager, Architect, Engineer, and Data Analyst progressively reduce different kinds of uncertainty:

```text
Coordination layer Run state          -> StageDecision     control order, retry, and failure closure
Product layer      Prompt             -> Blueprint         decide what to build
Architecture layer Blueprint          -> ArchitectureSpec  define routes, data, and presentation bounds
Engineering layer  ArchitectureSpec   -> AppSpec + Report  build and validate platform behavior
Data layer         AppSpec + Report   -> DataReview        check data and explain evidence
Delivery layer     DataReview         -> ProjectVersion    preserve, restore, and publish the result
```

Every specialist handoff is schema-validated, persisted, and inspectable. V1 Team Leader is the deterministic orchestrator and emits auditable StageDecision/progress events rather than a fabricated model conversation.

### 3. Execution Layer: Models Decide, the Platform Controls Authority

The LLM interprets requirements and makes structured decisions, but it cannot install dependencies, alter build commands, execute arbitrary shell input, or publish automatically. The platform owns the renderer, build worker, quota transactions, and publishing service.

### 4. State Layer: Runs, Versions, and Publishing Stay Separate

A failed Agent Run must not damage an existing version. An edit must not silently change a pinned public version, and Restore must not erase history. Project, Run, ProjectVersion, and publish pointers are therefore modeled separately so every change is traceable and recoverable.

### 5. Evolution Layer: Prove the Loop in V1, Add Autonomy in V2

V1 proves whether request, approval, build, preview, edit, versioning, and publishing work as one usable loop. V2 keeps the same artifact and event contracts, then adds Leader, independent contexts, dynamic delegation, rework, and arbitration without burdening V1 with untestable complexity.

## Implementation Approach and Key Trade-offs

| Decision | Why | Benefit | Cost and boundary |
| --- | --- | --- | --- |
| Real LLM + structured contracts + deterministic renderer | Prove real requirement understanding while controlling execution risk in a shared cloud environment | Blueprint/AppSpec respond to input and builds remain verifiable | V1 does not support arbitrary stacks or free-form code execution |
| Railway Cloud as the only V1 execution surface | Public acceptance needs one stable, reproducible Session, Preview, and Publish path | Only one state, storage, and deployment path to maintain | V1 cannot operate on a user's local repository |
| Asynchronous Build Job + fixed template and dependencies | Builds must not block HTTP requests or execute ad hoc model-generated commands | Jobs are recoverable and resource/failure scope stays bounded | Generation is limited by template capability; initial build concurrency is one |
| Real Plan/Quota/Ledger without payment integration | Multiple users and sessions must share and settle account usage correctly | Concurrent calls cannot overspend and model usage is auditable | V1 excludes Stripe, wallet, top-up, and invoicing |

See the [V1 architecture design](./docs/v1/architecture-design.md) for components, states, data, security, and deployment details. See the [V1 agent design](./docs/v1/agent-design.md) for execution semantics, human-in-the-loop, context, tools, sandbox boundaries, validation, and repair.

## V1 Deployment and Access Architecture

Two operations are separate: **the developer deploys the Another Atom platform to Railway**, while **a user publishes a generated application version inside the platform**. The first is infrastructure deployment; the second is a product capability.

```text
Platform deployment

Developer -- git push --> GitHub
                         |
                         v
                  Railway auto-deploy
                         |
                         v
              Another Atom cloud service

User access and generated-app publishing

User browser -- HTTPS --> Railway public domain
                         |
             +-----------+----------------+
             | React Visual Studio        |
             | FastAPI REST + SSE         |----> Ollama Cloud / Mock
             | Sequential role pipeline   |
             | Async Build Worker         |
             | Preview / Published Routes |
             +-----------+----------------+
                         |
                +--------+---------+
                |                  |
                v                  v
          PostgreSQL        Persistent Volume
       users / projects /     workspace / builds
       sessions / quota /
       jobs / versions

User selects ProjectVersion -- Publish / Update --> Published Route
                                                    |
                                                    v
                                            Stable public URL
```

The model cannot install dependencies, change build commands, execute arbitrary shell input, or publish automatically. Builds run asynchronously with a controlled template and a bounded worker.

## Not in V1

- Terminal CLI or local repository execution.
- Runtime dependency installation or arbitrary code execution.
- Arbitrary technology stacks or generated backends.
- Autonomous or parallel multi-agent collaboration, which is implemented in V2.
- Arbitrary providers or unrestricted model identifiers; V1 exposes only the configured DeepSeek allowlist.
- Generated-app authentication, database, commerce, or payment systems.
- Stripe billing, wallet, top-up, or invoicing.

## Version Implementation Plan

### V2: Autonomous Multi-Agent (Planned Implementation)

V2 is the next implementation version after V1, not an optional showcase direction. It adds a Leader Agent, independent specialist contexts, selective parallel execution, structured rework, arbitration, and run-level budgets. Product, engineering, and behavior baselines are defined in the [V2 PRD](./docs/v2/another-atom-v2-prd.md), [V2 architecture](./docs/v2/architecture-design.md), and [V2 agent design](./docs/v2/agent-design.md). Sandbox provider, model strategy, and load-tested budgets still require ADR/test decisions before development.

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
- [x] Unit/integration tests, including five consecutive Golden Path runs
- [x] Dockerfile and Railway configuration

Not completed:

- [ ] Per-project source materialization and `npm run build`; the current generated app is a validated AppSpec rendered by the shared React runtime
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
| User experience | Blueprint approval, live state, interactive Preview, recoverable versions, and actionable errors |
| Innovation | Blueprint/ArchitectureSpec/AppSpec artifact chain, controlled role handoff, and versioned publishing loop |
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
