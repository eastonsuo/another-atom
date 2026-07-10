# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> Turn a product idea into a web prototype that can be reviewed, refined, versioned, and published.

Another Atom is designed as an AI agent workspace for creating web product prototypes from natural-language requirements. A user describes an idea, reviews the proposed product plan, and follows the result through design, implementation, validation, revision, and publishing.

The project is inspired by [Atoms](https://atoms.dev/), but it is independently designed and implemented. It is not an Atoms fork and does not use Atoms source code or internal infrastructure.

> **Current status:** product and architecture design are complete. Application implementation and public deployment are not complete yet.

## Version Roadmap

| Version | Purpose | Role model | Status |
| --- | --- | --- | --- |
| **V1** | Deliver one complete, publicly testable product-building flow | Product Manager, Designer, Engineer, and QA run in a fixed sequence | Current implementation target |
| **V2** | Add autonomous collaboration, dynamic delegation, rework, and arbitration | Leader coordinates Product Manager, Architect, Designer, Engineer, and QA agents | Design direction only |

V1 is the only implementation and acceptance baseline. V2 documentation describes future direction and must not be read as completed functionality.

## V1 Target Experience

1. The user describes a product and can attach reference files.
2. Product Manager creates a **Blueprint**, an editable product plan containing pages, modules, visual direction, and data needs.
3. The user reviews and approves the Blueprint. Building cannot start without this approval.
4. Designer produces a **VisualSpec**, the structured visual and interaction rules.
5. Engineer produces an **AppSpec**, the machine-validated instructions used to create the application.
6. The platform builds the React application inside a restricted environment, and QA checks routes and core interactions.
7. The user previews the result, requests changes, restores an earlier version, exports project data, and publishes a selected version.

```text
[INPUT] Product request
   |
   v
[ROLE] Product Manager
   |
   v
[ARTIFACT] Blueprint
   |
   v
[USER] Review and approve
   |
   v
[ROLE] Designer
   |
   v
[ARTIFACT] VisualSpec
   |
   v
[ROLE] Engineer
   |
   v
[ARTIFACT] AppSpec
   |
   v
[PLATFORM] Controlled React build
   |
   v
[ROLE] QA
   |
   v
[RESULT] Interactive preview
   |
   v
[USER] Edit, restore, or publish a version
   |
   v
[RESULT] Public URL
```

Team Mode is a **sequential role pipeline**. The roles do not run in parallel or delegate work dynamically in V1. Every handoff produces an artifact the user or reviewer can inspect.

## Planned V1 Features

- Natural-language product requests and reference attachments.
- Editable Blueprint with an explicit approval gate.
- Product Manager, Designer, Engineer, and QA stage timeline.
- Real LLM calls with schema-validated outputs.
- Live progress events and an interactive desktop/mobile preview.
- Natural-language revisions, issue resolution, version restore, and version history.
- Multiple sessions with account-level usage limits.
- Versioned JSON export.
- User-controlled publishing, updates, unpublishing, and a stable public URL.
- Railway deployment with PostgreSQL and persistent project storage.

V1 is scoped to a controlled product catalog/storefront structure. Unsupported requests are stopped before building; related requests can only continue after the user reviews the proposed mapping.

## Why This Design

A direct chat-to-output flow makes intermediate decisions difficult to inspect. Another Atom instead introduces three structured checkpoints:

```text
User intent
    -> Blueprint: what should be built
    -> VisualSpec: how the product should look and behave
    -> AppSpec: what the build system should create
    -> ProjectVersion: the result that can be inspected and restored
```

This makes the generation process easier to understand and test. In V1, real LLM calls produce the structured checkpoints, while a fixed React template and platform-controlled build process turn them into a runnable result.

## How V1 Runs

V1 has one execution path: a cloud-hosted application deployed on Railway.

```text
Browser
  |
  v
React Visual Studio
  |
  | REST commands + SSE progress events
  v
FastAPI
  |
  +---- Sequential role orchestrator ----> OpenAI
  |
  +---- PostgreSQL
  |       users / projects / sessions / quota / jobs / versions
  |
  `---- Async build worker
          fixed React template / preinstalled dependencies
                              |
                              v
                    Preview and published app
```

The model cannot install dependencies, change build commands, execute arbitrary shell input, or publish automatically. Builds run asynchronously with a controlled template and a bounded worker.

## Not in V1

- Terminal CLI or local repository execution.
- Runtime dependency installation or arbitrary code execution.
- Arbitrary technology stacks or generated backends.
- Autonomous or parallel multi-agent collaboration.
- A model selector.
- Generated-app authentication, database, commerce, or payment systems.
- Stripe billing, wallet, top-up, or invoicing.

## Future Directions

### V2: Autonomous Multi-Agent

V2 introduces a Leader Agent, independent specialist contexts, selective parallel execution, structured rework, arbitration, and run-level budgets. See the [V2 role and orchestration design](./docs/v2/role-orchestration-design.md).

### Local Agent Runtime

A Claude Code-like runtime could later work with local files, Git, shell, npm, and a localhost Visual Studio. This direction is not implemented and has not yet been assigned to a release.

## Project Status

Completed:

- [x] Atoms public-feature analysis
- [x] V1 product requirements and acceptance criteria
- [x] V1 architecture and deployment design
- [x] V2 role and orchestration design
- [x] Submission note and bilingual documentation

Not completed:

- [ ] React Visual Studio and FastAPI implementation
- [ ] LLM integration, renderer, build worker, and persistence
- [ ] Automated testing and Railway resource verification
- [ ] Public deployment and online URL

## Links

- Source repository: [github.com/eastonsuo/another-atom](https://github.com/eastonsuo/another-atom)
- Online version: not deployed yet
- [V1 product requirements](./docs/v1/another-atom-v1-prd.md)
- [V1 architecture design](./docs/v1/architecture-design.md)
- [V1 submission note](./docs/v1/submission-note.md)
- [V2 overview](./docs/v2/overview.md)
- [V2 role and orchestration design](./docs/v2/role-orchestration-design.md)
- [Atoms reference analysis](./docs/reference/atoms-reference-analysis.md)

## Appendix

- Original product reference: [Atoms](https://atoms.dev/)
