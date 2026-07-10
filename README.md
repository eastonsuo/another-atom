# Another Atom

[English](./README.md) | [简体中文](./README.zh-CN.md)

> A terminal-first AI agent that turns product ideas into runnable web applications and presents the result in a visual browser studio.

Another Atom is an independent, Atoms-inspired application builder. A user describes a product in the terminal or browser, reviews a structured Blueprint, and lets a local agent generate, build, preview, revise, version, and publish a real web application.

The project is designed as a standalone public engineering case study. It does not depend on Atoms source code or internal infrastructure.

## Product Direction

Another Atom treats the terminal as the primary control surface and the browser as the visual workspace:

```text
Terminal CLI
    |
    v
Python Agent Runtime ---- Auth / Quota / LLM Gateway
    |
    +---- Project Workspace ---- Generated React App
    |                                  |
    |                                  v
    `---- REST + SSE ----------> Visual Studio
                                       |
                                       v
                                  Public URL
```

The V1 workflow is:

```text
Prompt -> Blueprint -> Approval -> Build -> Preview
       -> Natural-language revision -> Version -> Publish
```

## V1 Capabilities

- Terminal CLI and browser Prompt Composer.
- Real LLM calls with validated Blueprint and AppSpec outputs.
- Human approval before project files are generated or modified.
- Controlled filesystem, build, preview, and publishing tools.
- React Visual Studio with live agent events and application preview.
- Persistent projects, multiple sessions, resumable runs, and versions.
- Account-level plans, quota reservation, and usage settlement.
- A deployable cloud demo with a public HTTPS result.

V1 does not expose unrestricted shell access to public users. The hosted demo uses constrained workspaces and command allowlists; arbitrary remote code execution requires isolated per-run containers and is outside the first release.

## Architecture

The implementation baseline is:

- **Agent and API:** Python, FastAPI, Pydantic, OpenAI Agents SDK.
- **CLI:** Typer and Rich.
- **Studio:** React, TypeScript, and Vite.
- **Communication:** REST for commands, SSE for agent events, OpenAPI for shared contracts.
- **Local state:** project files and SQLite.
- **Cloud state:** PostgreSQL for users, sessions, plans, quotas, usage, and deployment metadata.
- **Deployment:** Docker on Railway, with a PostgreSQL service and persistent volume.

Local mode runs the agent and workspace on the user's machine. Cloud demo mode runs the same core in a constrained Railway container so reviewers can test the product through a public URL.

## Repository Status

The repository currently contains the reviewed product and architecture documents. Application implementation and deployment are the next milestones.

- [x] Reference product analysis
- [x] V1 product definition
- [x] V1 architecture design
- [ ] Application implementation
- [ ] Automated verification
- [ ] Public deployment

## Documentation

- [Documentation index](./docs/README.md)
- [V1 architecture design](./docs/architecture-design.md)
- [V1 product requirements](./docs/another-atom-v1-prd.md)
- [Atoms reference product analysis](./docs/atoms-reference-analysis.md)

## Appendix

- Original product reference: [Atoms](https://atoms.dev/)
