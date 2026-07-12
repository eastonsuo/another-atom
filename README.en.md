# Another Atom

[简体中文](./README.md) | [English](./README.en.md)

> Turn a rough idea into a software project whose code you can inspect, edit, version, and publish.

## Product Conclusion

Another Atom is a multi-agent Vibe Coding workspace. Users express intent in natural language; specialist Agents plan, implement, and validate, while the Project workspace keeps interactive preview, code files, version history, and publishing in one continuous development loop.

It shares [Atoms'](https://help.atoms.dev/en) core category goal: moving from intent to an online product. Another Atom uses its own brand, interaction model, contracts, and engineering implementation; it does not reuse Atoms source code, private prompts, or undisclosed infrastructure.

```text
Idea / materials / existing project
               |
               v
          Talk to Lead
               |
               v
     Multi-agent planning and execution
               |
               v
       Runnable app + project code
               |
         +-----+-------------------+
         |                         |
         v                         v
 Preview / visual edit      Inspect / edit / manage files
         |                         |
         +-----------+-------------+
                     v
          Validate / repair / version
                     |
                     v
              User-approved publish
                     |
                     v
          Continue conversation and iteration
```

See the [overall product goal and positioning](./docs/design/整体/产品设计/整体产品目标与定位.md) for the full decisions and trade-offs.

## Core Problems

- **From idea to implementation:** Users may start with only a goal, not a complete specification, architecture, or codebase. The system should fill the necessary gaps and produce a runnable result.
- **An opaque AI process:** A single prompt does not show what the model understood, why it implemented a solution, or where failure occurred. Specialist roles and inspectable artifacts make the process understandable and correctable.
- **Generated results are hard to continue:** One-off code or screenshots do not support sustained iteration. A Project must retain code files, current state, and version history so work can continue in place.
- **Insufficient control of code and production:** Vibe Coding must not hide source code or let new output silently replace the live version. Users inspect and edit code and explicitly choose what to publish.

## Product Interface

Login establishes a server-side Session; Projects, source repositories, versions, and Sandbox Sessions are isolated by account.

<p align="center">
  <img src="./docs/assets/readme/login-zh.png" alt="Another Atom Chinese login with password Session and account-level Project isolation" width="640">
</p>

Studio keeps Lead chat, specialist Agents, Project history, model selection, and account quota in one workspace.

<p align="center">
  <img src="./docs/assets/readme/studio-home-v2-zh.png" alt="Another Atom Chinese Studio home with Lead, specialist Agents, Project history, and real LLM status" width="640">
</p>

The build workspace shows durable progress, interactive Preview, Project Repository, current Run Artifacts, and logs.

<p align="center">
  <img src="./docs/assets/readme/studio-build-workspace-zh.png" alt="Another Atom build workspace with stage progress, mobile preview, Project files, and Run logs" width="640">
</p>

Generated output runs as a real Web application; users inspect interactions, source files, and structured artifacts.

<p align="center">
  <img src="./docs/assets/readme/studio-game-preview-zh.png" alt="Another Atom generated Snake game with interactive Preview, Run logs, and Project files" width="640">
</p>

Build, Edit, and Restore create separate versions. History remains intact, and users explicitly choose the live version.

<p align="center">
  <img src="./docs/assets/readme/version-history-zh.png" alt="Another Atom version history where Build, Edit, and Restore create separate versions" width="640">
</p>

## Overall Design Principles

### Project-centered: deliver a software project, not a response

A Project is the common owner of requirements, Agent artifacts, source repository, Preview, versions, and publishing state. Returning users continue from existing code and state rather than starting a new chat from scratch.

### Multi-agent collaboration: hand off artifacts, not roleplay messages

Lead is the user entry point. Product Manager, Architect, Engineer, Data Analyst, and later specialists address different uncertainties. Their value is proven by inspectable plans, architecture, source code, validation, and analysis—not avatars or message count.

### Context handoff: each role receives only what the task requires

Agents do not share an endlessly growing chat transcript. Runtime assembles the necessary Context for the current task and passes versioned Artifacts, Evidence, and Handoffs so inputs, outputs, and failures remain inspectable, recoverable, and traceable.

### Vibe Coding: natural language, visual editing, and source files share one workspace

Users express intent through conversation, inspect behavior through Preview, make quick visual changes, and inspect or edit source files when precision is needed. Every path affects the same Project and version history.

### Human-in-the-loop: routine work continues; users decide real risk

Once a user explicitly requests a build, work inside the accepted scope and base budget may continue. Scope changes, extra budget, destructive source operations, and public deployment changes require confirmation.

### Code ownership: source, Git history, and product versions remain traceable

Every Project owns a repository. Builds, edits, repairs, and restores create versions mapped to Git commits. Users inspect, edit, manage, and eventually export their code instead of receiving an opaque platform-only result.

### Version and publishing: generation does not equal production

Working versions may continue changing, while the public route follows the user's last explicit Publish/Update. Restore creates a new version without rewriting history or silently moving the publish pointer.

### Runtime authority: models propose; the platform controls side effects

LLMs understand, plan, generate, and explain. Runtime owns identity, quota, state, tool authorization, repository writes, Sandbox, and publishing. Generated code and trusted Control Plane authority stay separated.

### Unified authorization: APIs, Preview, and Terminal follow the same ownership rules

REST, SSE, private Preview, and Terminal WebSocket connections all pass through the unified Gateway, resolve the server Session, and verify ownership of Runs, Projects, Versions, and Sandbox Sessions. Public Routes are modeled separately and read only an explicitly published version.

### Recovery: progress and versions reflect durable facts

Visible stages, errors, usage, and versions must come from recoverable state. Refresh, retry, or process restart should not repeat completed work, usage settlement, or version creation.

## Overall Logical Architecture

```text
User Browser
Studio / Preview / Files and Terminal UI
                    |
              HTTPS / WSS
                    v
+----------------------------------------------------+
| Unified Gateway / Control Plane                    |
| Identity | Lead / Risk | Project / Version         |
| Publish  | Event / Quota | Durable Scheduler       |
+---------------------------+------------------------+
                            |
          +-----------------+------------------+
          |                 |                  |
          v                 v                  v
      State DB        Artifacts / Repository     LLM Provider
          |                 |
          |                 v
          |             Agent Worker
          |                 |
          |                 v
          +----------> Tool Gateway
                            |
                            v
                    Sandbox Provider
                  files / build / test / Vim
```

- **Control Plane:** owns trusted identity, Project ownership, state, quota, versions, and publish pointers.
- **Agent Runtime:** assembles the necessary Context, invokes models, validates results, and saves Artifacts without bypassing platform authority.
- **Repository:** stores Project source, Git history, and commit/version mappings.
- **Tool Gateway:** evaluates tool requests against user, Project, Agent role, path, network, and budget policy.
- **Sandbox:** runs untrusted file changes, builds, and tests without authority over identity, quota, or publishing.

### Agent and Runtime Execution Flow

```text
User message
    |
    v
LeadDecision -------- direct --------> Answer / clarification
    |
   team
    v
Blueprint -> Risk Policy -> TaskGraph / Fixed Pipeline
                              |
                              v
                  Minimal Agent Context + Artifact Handoff
                              |
                              v
                    ToolRequest -> Sandbox
                              |
                              v
                Validation + Evidence + DataReview
                              |
                              v
                   Git commit + ProjectVersion
                              |
                              v
                   explicit Publish / Update
                              |
                              v
                         Public Route
```

- **Planning and execution stay separate:** Lead may propose direct, team, or TaskGraph behavior; Runtime validates roles, dependencies, budget, Approval, and Tool authority.
- **Models and evidence stay separate:** Agents produce structured judgments; Renderer, Test, Validator, and ToolResult provide execution evidence that models cannot rewrite.
- **Work and publishing stay separate:** Agent Runs and ProjectVersions may continue evolving, while the Public Route follows only the user's last explicit publish pointer.

### Deployment and Sharing Architecture

This separates two actions: developers deploy the Another Atom platform, while users publish and share a ProjectVersion inside the product. The former creates trusted service boundaries; the latter changes only the product's publish pointer.

```text
Platform deployment

Developer -- git push --> GitHub
                           |
                        Deploy
                           |
             +-------------+-------------+
             |                           |
             v                           v
        Control Plane               Agent Workers
             |                           |
       +-----+------+              +-----+-----------+
       |            |              |       |         |
       v            v              v       v         v
   State DB   Artifact Storage   LLM    state/data   Sandbox Provider

User access and sharing

Browser -- HTTPS / WSS --> Unified Gateway
                              |
               +--------------+--------------+
               |                             |
               v                             v
      Authenticated Studio             Published Route
       Project / Edit / Vim            selected Version
               |                             |
               `---- explicit Publish -------'
                                             |
                                             v
                                      Stable Public URL
```

- **One public entry:** the browser reaches only the Control Plane HTTPS/WSS domain; internal Workers, databases, artifact storage, and Sandboxes are not exposed to end users.
- **Deployment boundary:** versions may combine or split Control Plane, Agent Worker, and Sandbox components, but trusted control authority and untrusted execution must not share privileges.
- **Sharing boundary:** the Public Route reads only the published version and does not expose the Project Repository, Agent Context, internal Events, quota, or Sandbox Sessions.

Version-specific engineering boundaries remain in each architecture document; the README does not duplicate implementation details.

## Current Versions

| Version | How it advances the overall goal | Status and design sources |
| --- | --- | --- |
| **V1** | Proves the complete loop with a fixed specialist team, bounded Web Runtime, Project Git, versions, and explicit publishing | Railway single-replica accepted; target Linux Sandbox isolation acceptance remains. See [V1 product](./docs/design/V1/产品设计/产品需求.md), [V1 Agent](./docs/design/V1/Agent设计/Agent设计.md), and [V1 architecture](./docs/design/V1/工程设计/架构设计.md) |
| **V2** | Adds dynamic task graphs, role subsets, tools, selective parallelism, and rework on the same Project, Artifact, and authority foundations | Designed, not implemented. See [V2 product](./docs/design/V2/产品设计/产品需求.md), [V2 Agent](./docs/design/V2/Agent设计/Agent设计.md), and [V2 architecture](./docs/design/V2/工程设计/架构设计.md) |

The current code includes real and Mock LLM providers, user isolation, Project Git, interactive Preview, versions and publishing, durable jobs, and Provider fallback. The backend currently collects 74 unit/integration tests. See the [V1 delivery summary](./docs/design/V1/产品设计/简要交付说明.md) and [V1 review](./docs/review/V1/综合评审/2026-07-12-关键设计与实现检查.md) for detailed completion status.

## Quick Start

### Requirements

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 22 and npm

Local development defaults to SQLite and a deterministic Mock Provider, with no API key required. See the [local and Railway guide](./docs/design/V1/工程设计/本地运行与Railway部署.md) for Ollama Cloud and DeepSeek configuration.

### 1. Install backend dependencies

```bash
uv sync --python 3.12
```

### 2. Build Studio

```bash
cd studio
npm install
npm run build
cd ..
```

### 3. Start the backend

```bash
uv run --python 3.12 uvicorn another_atom.main:app --host 127.0.0.1 --port 8000
```

Open:

- Studio: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Local data is stored in `data/another_atom.db`. xterm.js + restricted Vim additionally requires a Linux Sandbox Host, Sandbox image, and shared secret.

## Documentation

- **Overall product:** [Overall product goal and positioning (Chinese)](./docs/design/整体/产品设计/整体产品目标与定位.md)
- **Design:** [Design documentation index](./docs/design/README.md)
- **Discussion:** [Open discussion index](./docs/discussion/README.md)
- **Review:** [Inspection, reflection, and bug index](./docs/review/README.md)
- **Deployment:** [Local run and Railway deployment guide](./docs/design/V1/工程设计/本地运行与Railway部署.md)
- **Atoms reference:** [Atoms reference product analysis](./docs/design/整体/参考资料/Atoms参考产品分析.md)

## Project Status

- **Source:** [github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- **Online:** Railway deployment and public access have been accepted; the service domain is managed by the Railway environment.
- **Current limits:** target Linux Sandbox security acceptance, a complete Project conversation thread, failure Retry/Resolve, and backend-dependent product capabilities remain future work.
