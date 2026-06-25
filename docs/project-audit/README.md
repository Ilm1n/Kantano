# Project Audit Knowledge Base

## What This Is
This directory contains a full project audit for `Kantano` in `RU + EN` format. The goal is simple: a new engineer or agent should be able to understand architecture, constraints, risks, and operational context by reading only these `.md` files.

Audit scope includes:
- System architecture and bounded contexts
- Backend and frontend deep-dive
- API contract map
- Data model and migration history
- DevOps and environments
- Risk register with severity and evidence
- Onboarding and agent execution playbook

Audit snapshot date: `2026-03-20`.

## Quick Start
1. Read [01-system-overview.md](./01-system-overview.md) for mental model.
2. Read [07-risk-register.md](./07-risk-register.md) before changing behavior.
3. Use [08-onboarding-and-agent-playbook.md](./08-onboarding-and-agent-playbook.md) for practical setup and safe change rules.
4. Use domain deep-dives (`02`, `03`, `04`, `05`, `06`) for implementation-level work.

## Document Map
| File | Focus | When To Read |
|---|---|---|
| [01-system-overview.md](./01-system-overview.md) | Top-level architecture, components, flows, bounded contexts | First entry point |
| [02-backend-deep-dive.md](./02-backend-deep-dive.md) | FastAPI internals, auth, permissions, services, transactions, errors | Backend changes and bugfixes |
| [03-frontend-deep-dive.md](./03-frontend-deep-dive.md) | Vue router/store/data flow, API integration, analytics/consent | Frontend/product workflow changes |
| [04-api-contract.md](./04-api-contract.md) | Endpoint catalog, auth requirements, request/response conventions | API integrations and contract checks |
| [05-data-model-and-migrations.md](./05-data-model-and-migrations.md) | ER model, indexes, constraints, migration timeline | DB changes and performance/debug tasks |
| [06-devops-and-environments.md](./06-devops-and-environments.md) | Docker, Compose, Caddy, CI/CD, env contract | Deploy/infrastructure and runtime ops |
| [07-risk-register.md](./07-risk-register.md) | Prioritized findings with evidence and recommendations | Before any refactor/release |
| [08-onboarding-and-agent-playbook.md](./08-onboarding-and-agent-playbook.md) | 30/60-minute onboarding, diagnostics, safe execution rules | New contributor/agent kickoff |

## Standard Documentation Interface
All audit files `01..08` follow one consistent structure:
- `Purpose`
- `Current Behavior`
- `Dependencies`
- `Risks`
- `Open Questions`
- `References`

This allows fast scanning and predictable retrieval for both humans and agents.

## How To Keep Docs Fresh
Recommended update triggers:
- Any API contract change (`router`, `schemas`, generated client)
- Any permission/auth behavior change
- Any migration/index/data model update
- Any deploy/environment/config contract update
- Any resolved or newly introduced finding in risk register

Minimal maintenance flow:
1. Update affected section(s).
2. Add/adjust `References` with `path:line` evidence.
3. Sync [07-risk-register.md](./07-risk-register.md) status and priority.
4. If context changed materially, refresh root [AGENT_CONTEXT.md](../../AGENT_CONTEXT.md).
