# Another Atom Project Memory

## Delivery Baseline

- This project is developed by one person. By default, commit and push changes directly to `main`; create a separate branch or pull request only when the user explicitly asks for one.
- Implement the project in V1 -> V2 order. V1 is the current implementation and acceptance baseline.
- V1 delivers a Railway-hosted cloud application; Terminal CLI and local repository execution are outside V1.
- V1 uses a fixed sequential role pipeline: Product Manager -> Architect -> Engineer -> Data Analyst -> Reviewer. Runtime Validator remains a deterministic non-Agent stage between Data Analyst and Reviewer.
- V2 autonomous multi-agent behavior is a planned implementation version after V1 acceptance; it is not implemented yet.
- User requirements may describe any product goal. V1 implements the goal as a self-contained browser application using generated HTML/CSS/JavaScript. Preserve the product identity; do not convert games or tools into catalogs. Server-side auth, payments, persistent database writes, external services, native runtimes, and unrestricted package/Shell execution remain capability boundaries and must be marked adapted or unsupported.

## Documentation Governance

- `docs/design/` is the normative, continuously maintained design source. Put product requirements, Agent contracts and runtime design, engineering architecture and deployment design, and other stable design/reference material there.
- `docs/review/` records dated inspections, reflections, bugs, verification evidence, and milestone findings. A Review states what was checked and what was found; it does not become the long-term home of a solution design.
- When a Review finds a problem that needs a dedicated solution, create or update the corresponding document under `docs/design/`, then link the Review finding and the design decision in both directions.
- Under both `docs/design/` and `docs/review/`, classify first by version scope: `V1`, `V2`, or `整体`. `V1` is the current implementation baseline, `V2` is the planned post-V1 version, and `整体` is only for system-wide principles, evolution, or references that do not belong to one version.
- Design domain folders are `产品设计`, `Agent设计`, `工程设计`, and `参考资料`. Review domain folders are `产品评审`, `Agent评审`, `工程评审`, and `综合评审`. Classify by the main question the document answers, not by its author or temporary workflow stage.
- Use Chinese directory names, file names, document titles, and prose by default. Keep English only for established technical names such as Agent, Runtime, Context, Sandbox, API, and Git. Dated Review files use `YYYY-MM-DD-中文短主题.md`.
- Design documents may be revised as the baseline changes. Dated Review findings remain historical evidence; add a dated Update with code/test/deployment evidence instead of rewriting the original finding.

## Evaluation Criteria

All implementation and scope decisions must be checked against these five dimensions.

### 1. Completeness

- Protect the full V1 loop: request -> Blueprint approval -> build -> preview -> edit/resolve -> version -> publish -> public URL.
- Cover recovery and negative paths, not only the Golden Path.
- Treat persistence, visible failure states, and automated verification as part of the feature.

### 2. Engineering Judgment

- Keep Blueprint, VisualSpec, AppSpec, events, errors, versions, and export formats as explicit contracts.
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
