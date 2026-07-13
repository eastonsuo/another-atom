# 【Bug】Another Atom V1 Engineer 与 QA 问题评审

> 类型：Bug｜状态：历史评审，已按后续工作树复核｜日期：2026-07-10｜范围：具体缺陷、测试缺口与可复现性

> **2026-07-13 归档 Update：** 表中高优先级问题已经修复并由后续测试覆盖；版本来源、配额、恢复和审计规则已进入 [V1 多 Agent 设计](../../design/V1/技术设计/01-[Agent]-多Agent设计.md)与 [V1 系统架构](../../design/V1/技术设计/03-[工程]-系统架构.md)。后续功能范围与实现状态以正式 [Design](../../design/README.md)、实际代码和验证结果为准。

- Review date: 2026-07-10
- Reviewer roles: Engineer + QA
- Baseline commit: `2c386c1`
- Scope: concrete defects, test gaps, and reproducibility
- Resolution status: reviewed against the current working tree

## Findings and resolution

| ID | Finding | Resolution |
| --- | --- | --- |
| E1 / QA2 | Failed runs settled the full reservation as used; tests only checked `reserved == 0` | **Fixed with a clarified rule**: settle actual Provider requests, not the full reservation. Failed calls that reached the Provider remain billable; unused reservations are released. Tests assert both `used` and `reserved` |
| E2 | Approval and worker could create duplicate BuildJobs | **Fixed**: one BuildJob per Run is enforced by a unique constraint and approval row locking |
| E3 | Project view must tolerate a project without a Run | **No change required**: current guard and creation transaction are retained |
| E4 | Edit/restore versions reuse the original build `run_id` | **Deferred (low)**: source distinguishes edit/restore, but a future provenance model should add an explicit parent/source relation instead of overloading `run_id` |
| E5 | SSE opened a new database session every 0.5 seconds | **Fixed**: one session is retained for the stream lifetime and expired before each poll |
| E6 | Retry exhaustion replaced schema errors with `LLMProviderError` | **Fixed**: the final original error type is re-raised |
| QA1 | Tests replaced the production async path with same-request execution | **Fixed**: the test dispatcher invokes the persistent worker claim/execute path using fresh database sessions; expired lease reclaim has a dedicated integration test |
| QA3 | Python 3.10 cannot run a Python 3.12 project | **Fixed as reproducibility policy**: CI explicitly uses Python 3.12; `pyproject.toml`, Docker and local docs already require 3.12+ |
| QA4 | Publish, unpublish, edit, and restore had no audit events | **Fixed**: delivery actions append persisted project Run events |

## Verification target

- Static checks: Ruff.
- Unit/integration tests: mock Provider, real worker session boundary, lease recovery, quota ledger, user isolation, version and publication flows.
- Frontend: ESLint, TypeScript and Vite production build.

The review's E1 recommendation to leave `used` unchanged for every failed Run was not adopted literally because Provider requests can incur real cost even when the product Run fails. The implemented rule only charges calls that actually occurred.
