# AGENT_CONTEXT

This file is the shortest entrypoint for any agent working in this repository.

## Read First
1. [Audit Index](./docs/project-audit/README.md)
2. [System Overview](./docs/project-audit/01-system-overview.md)
3. [Risk Register](./docs/project-audit/07-risk-register.md)
4. [Playbook](./docs/project-audit/08-onboarding-and-agent-playbook.md)

## Critical Invariants (Do Not Break)
- API namespace is `/api/*`; frontend client assumes this prefixing behavior.
- Auth model is `access token (memory) + refresh token (HttpOnly cookie)`.
- Permission model is role-driven (`OWNER`, `MANAGER`, `MEMBER`) and enforced in backend dependencies/services.
- Board ordering logic depends on `position` and rebalance mechanics.
- Project recency (`updated_at`) is used for sorting and is updated via `touch_project` flows.

## Known High-Priority Risks
- Manager can create invitation with `OWNER` role (`R-001`).
- Potential stale `updated_at` in member role update flow (`R-002`).
- Frontend API base URL env mismatch (`R-003`).

## Working Rule
Before implementing changes in auth, permissions, invitations, API contract, DB schema, or deploy config:
- update corresponding `docs/project-audit/*.md`
- update `07-risk-register.md` status/priority when risk is changed or resolved

## Typing Rule
- Backend code must pass `uv run basedpyright` from `backend/light_task` before CI.
- If a function return type is non-optional, every path must explicitly return a value or raise an exception.
- Do not rely on helper methods or policies to narrow `None`; add explicit runtime checks after permission validation when the value is used.
- Async context managers that never suppress exceptions must annotate `__aexit__` as `Literal[False]`, not plain `bool`.
- Protocol methods should use `...` bodies, not `pass`, so type checkers do not infer an implicit `None` return.
