# Another Atom Project Memory

## Delivery Baseline

- Implement the project in V1 -> V2 order. V1 is the current implementation and acceptance baseline.
- V1 delivers a Railway-hosted cloud application; Terminal CLI and local repository execution are outside V1.
- V1 uses a fixed sequential role pipeline: Product Manager -> Architect -> Engineer -> Data Analyst.
- V2 autonomous multi-agent behavior is a planned implementation version after V1 acceptance; it is not implemented yet.
- User requirements may describe any product goal. V1 implements the goal as a self-contained browser application using generated HTML/CSS/JavaScript. Preserve the product identity; do not convert games or tools into catalogs. Server-side auth, payments, persistent database writes, external services, native runtimes, and unrestricted package/Shell execution remain capability boundaries and must be marked adapted or unsupported.

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
