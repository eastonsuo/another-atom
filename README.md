# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> Turn a product idea into a web prototype that can be reviewed, refined, versioned, and published.

Another Atom is designed as an AI agent workspace for creating web product prototypes from natural-language requirements. A user describes an idea, reviews the proposed product plan, and follows the result through design, implementation, validation, revision, and publishing.

The project is inspired by [Atoms](https://atoms.dev/), but it is independently designed and implemented. It is not an Atoms fork and does not use Atoms source code or internal infrastructure.

> **Current status:** V1 product and architecture design and V2 role orchestration design are complete. Application implementation and public deployment for both versions are not complete yet.

> **Technical implementation baseline:** [Another Atom V1 Architecture Design](./docs/v1/architecture-design.md)

## Version Roadmap

| Version | Purpose | Role model | Status |
| --- | --- | --- | --- |
| **V1** | Deliver one complete, publicly testable product-building flow | Product Manager, Designer, Engineer, and QA run in a fixed sequence | Current implementation target |
| **V2** | Add autonomous collaboration, dynamic delegation, rework, and arbitration | Leader coordinates Product Manager, Architect, Designer, Engineer, and QA agents | Implement after V1 |

The project will be implemented in **V1 -> V2** order. V1 is the current development and acceptance baseline; V2 is a committed roadmap version to implement after V1 passes acceptance. Neither application version is complete yet.

## V1 Target Experience

1. The user describes a product and can attach reference files.
2. Product Manager creates a **Blueprint**, an editable product plan containing pages, modules, visual direction, and data needs.
3. The user reviews and approves the Blueprint. Building cannot start without this approval.
4. Designer produces a **VisualSpec**, the structured visual and interaction rules.
5. Engineer produces an **AppSpec**, the machine-validated instructions used to create the application.
6. The platform builds the React application inside a restricted environment, and QA checks routes and core interactions.
7. The user previews the result, requests changes, restores an earlier version, exports project data, and publishes a selected version.

### A. Application Generation and Development

#### Step 1: Confirm the Requirement

```text
User prompt
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
[Designer] -> VisualSpec
    |
    v
[Engineer] -> AppSpec
    |
    v
Platform-controlled React build
```

#### Step 3: Validate Quality

```text
Build result
    |
    v
[QA] -> ValidationReport / QAReview
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
- **How the system decides:** A real LLM classifies the request as `supported`, `adapted`, or `unsupported`; the result is valid only after schema validation.
- **How work proceeds:** Designer, Engineer, and QA produce VisualSpec, AppSpec, and QAReview only after user approval. A stage cannot claim completion without approval and a real artifact.
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
- **One HTTPS entry point:** Railway hosts the web service, asynchronous builds, and published results behind the same domain.
- **Boundaries stay honest:** Cloud, Integrations, and Growth explain V1 limits without triggering unfinished authorization, payment, or third-party costs.

> **What V1 can build:** V1 focuses on controlled product catalog and storefront sites. `unsupported` requests stop before build; `adapted` requests show what is mapped or omitted and require user approval before continuing.

## V1 Delivery Milestones

| Milestone | Deliverable | Stage acceptance | Status |
| --- | --- | --- | --- |
| **M0 Design baseline** | PRD, architecture, role contracts, and bilingual README | V1/V2 boundaries agree and critical state, data, and error contracts are traceable | Complete |
| **M1 Cloud foundation** | React workspace, FastAPI, PostgreSQL, and base Project/Session/Quota models | A project can be created and reopened; base state survives refresh and process restart | Not started |
| **M2 Generation flow** | Prompt, attachments, Blueprint approval, four-role sequence, and asynchronous build | No build before approval; every stage has a real artifact; failures are visible and retryable | Not started |
| **M3 Studio loop** | Desktop/mobile preview, editing, Resolve, versions, and Restore | Core routes and interactions work; Build/Edit/Resolve/Restore all create recoverable versions | Not started |
| **M4 Publish and hardening** | Publish/Update/Unpublish, stable URL, Export, automated tests, and Railway deployment | Main flow, negative paths, recovery, quota, and public access meet the final baseline | Not started |

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

Product Manager, Designer, Engineer, and QA progressively reduce different kinds of uncertainty:

```text
Request layer      Prompt       -> Blueprint      decide what to build
Design layer       Blueprint    -> VisualSpec     constrain presentation and interaction
Engineering layer  VisualSpec   -> AppSpec        define what the build system creates
Validation layer   Build Result -> QAReview       verify the result against the contracts
Delivery layer     QAReview     -> ProjectVersion preserve, restore, and publish the result
```

Every handoff is schema-validated, persisted, and inspectable in the interface. A role message without an artifact change does not complete a stage.

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

See the [V1 architecture design](./docs/v1/architecture-design.md) for components, states, data, security, and deployment details.

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
             | FastAPI REST + SSE         |----> OpenAI
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
- A model selector.
- Generated-app authentication, database, commerce, or payment systems.
- Stripe billing, wallet, top-up, or invoicing.

## Version Implementation Plan

### V2: Autonomous Multi-Agent (Planned Implementation)

V2 is the next implementation version after V1, not an optional showcase direction. It adds a Leader Agent, independent specialist contexts, selective parallel execution, structured rework, arbitration, and run-level budgets. Its full product scope, deployment profile, and quantitative acceptance baseline will be completed before V2 development; see the [V2 role and orchestration design](./docs/v2/role-orchestration-design.md).

### Unassigned Version: Local Agent Runtime

A Claude Code-like runtime could later work with local files, Git, shell, npm, and a localhost Visual Studio. This direction is not implemented and has not yet been assigned to a release.

## Project Status

Completed:

- [x] Atoms public-feature analysis
- [x] V1 product requirements and acceptance criteria
- [x] V1 architecture and deployment design
- [x] V2 role and orchestration design
- [x] Bilingual README, evaluation evidence, and project implementation constraints

Not completed:

- [ ] V1 React Visual Studio, FastAPI, LLM, renderer, build worker, and persistence
- [ ] V1 automated tests, Railway deployment, and public URL
- [ ] V2 complete PRD, technical design, deployment profile, and acceptance baseline
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
| Innovation | Blueprint/VisualSpec/AppSpec artifact chain, controlled role handoff, and versioned publishing loop |
| Deliverability | GitHub source, bilingual README, reproducible run steps, Railway URL, and known boundaries |

## Links

- Source repository: [github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- Online version: not deployed yet
- [V1 product requirements](./docs/v1/another-atom-v1-prd.md)
- [V1 architecture design](./docs/v1/architecture-design.md)
- [V2 implementation plan](./docs/v2/overview.md)
- [V2 role and orchestration design](./docs/v2/role-orchestration-design.md)
- [Atoms reference analysis](./docs/reference/atoms-reference-analysis.md)

## Appendix

- Original product reference: [Atoms](https://atoms.dev/)
