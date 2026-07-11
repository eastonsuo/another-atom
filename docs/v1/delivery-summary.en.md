# V1 Delivery Summary

## Approach and trade-offs

- **[Product goal] Any goal, bounded delivery:** V1 preserves product identity—games, tools, boards, and catalogs—and delivers a self-contained HTML/CSS/JavaScript Web application. Real authentication, payments, persistent databases, third-party services, native runtimes, dynamic dependencies, and Shell execution remain explicit `adapted` or `unsupported` boundaries.
- **[Agents] Artifacts before execution:** Lead routes `direct/team`; Product Manager → Architect → Engineer → Data Analyst hand off structured, persisted Contracts rather than an unbounded shared chat.
- **[Approval] Stop only for risk:** Supported work within the offline Web Runtime and base budget continues automatically. Capability substitutions, extra budget, destructive source actions, and publishing changes require confirmation.
- **[Engineering] Durable facts over transient UI:** Runs, Artifacts, quota settlement, Jobs, Git commits, and versions are persisted. CAS, uniqueness constraints, and stage reuse keep the single-instance runtime replay-safe.
- **[Security] Preview is separated from platform authority:** Generated source belongs to the Project Git repository and executes in a network-denied, sandboxed iframe. V1 neither runs model-provided Shell nor installs runtime dependencies.

## Current status

### Completed

- Local end-to-end flow: login → Lead → PM draft/risk confirmation → fixed team build → Preview → Edit/Restore → Git version → explicit Publish.
- General Web source delivery: `index.html`, `styles.css`, and `app.js`; a game or tool is not silently converted into a catalog.
- Inspectable, recoverable artifacts, versions, usage settlement, ownership checks, and single-instance approval protection.
- 73 backend tests, Studio lint, and production build pass.

### Not complete

- Railway single-replica deployment, persistent Volume, real Provider, and public URL acceptance.
- Target Linux Sandbox validation: rootless isolation, network denial, seccomp/cgroup limits, cleanup, and cross-tenant checks.
- Persisted Project conversation threads across Lead, build, and follow-up messages.
- OAuth, payments, cloud databases, external APIs, arbitrary backend execution, general terminal access, and horizontal scaling.

## Next priorities

1. **P0 — Deliverability:** validate Railway + Linux Sandbox, persistence/restart recovery, two-user isolation, and Public URL.
2. **P0 — Trustworthy continuation:** persist Project conversation threads and complete Retry / Resolve failure paths.
3. **P1 — Web capability:** enrich the bounded Web Contract and deterministic interaction tests without granting arbitrary execution.
4. **P2 — V2 runtime:** dynamic task graphs, role subsets, parallel work, rework, and arbitration after V1 deployment acceptance.

## Conclusion

V1 has the local loop from inspectable multi-role generation to bounded Web source, recoverable versions, and user-controlled publication. The next high-value work is deployment and Sandbox acceptance—not adding more Agents or unbounded external capability.
