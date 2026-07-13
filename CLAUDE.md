# CLAUDE.md

Guidance for Claude Code working in this repository. A Cline mirror of these
rules lives in `.clinerules` — keep the two in sync when either changes.

## What this project is

An agentic healthcare workflow platform. A clinician asks a natural-language
question; an LLM/MCP layer fetches FHIR data, evaluates clinical risk, and
returns a structured recommendation. Reference workflow: **prescription refill
risk triage** (drug-allergy conflict detection).

Request flow: **mcp-agent → triage-service → fhir-service**, fronted by a Kong
gateway. Key components:

| Path | What it is | Language |
|---|---|---|
| `fhir-service/` | HAPI FHIR JPA R4 server (H2 local, Neon PostgreSQL cloud) | Java 21 / Spring Boot |
| `triage-service/` | FastAPI service; drug-allergy rule engine → FHIR `RiskAssessment` | Python |
| `mcp-agent/` | Anthropic tool-use CLI orchestrator (**no clinical logic**) | Python |
| `client/clinical/` | Domain-abstracted FHIR client library (shared by agent + triage) | Python |
| `client/platform/` | Direct FHIR-server integration tests | Python |
| `gateway/` | Kong config (key-auth, rate limiting) for GKE | YAML / Helm |
| `data/scripts/` | Synthea data generation + demo seeding | Python |

Conventions to preserve: the agent orchestrates but holds no clinical logic
(rules live in `triage-service/src/triage/rules.py`); `client/clinical` speaks
clinical domain terms, never raw FHIR bundles; the two `client/` subfolders
serve different audiences and should not modify each other's code.

## Build & test

```
# Python packages (editable installs + test tooling — see .ona/automations.yaml)
python -m pip install -e "client/clinical[dev]" -e "triage-service[dev]" -e "mcp-agent[dev]"
pytest <path>                       # run focused tests for the changed package

# FHIR service (Java). Unset SPRING_DATASOURCE_URL / NEON_* first so tests use H2;
# otherwise MdmTest boots against a live DB and fails on auth (env issue, not code).
cd fhir-service && ./mvnw clean verify        # full build + tests
cd fhir-service && ./mvnw spring-boot:run     # run locally on :8080 (H2)
```

The mcp-agent accepts `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY` (the Ona secret name).

Run only the tests relevant to a change when practical. Never claim tests
passed unless they actually ran; if they can't run, say why.

## Repository layout — two worktrees

This project intentionally uses two Git worktrees. Treat them as independent
environments and never confuse them:

- `/workspaces/fhir-agent` — branch `main`. Application code, features, tests,
  pull requests, code review.
- `/workspaces/.ai-chat-history` — branch `ai-chat-history`. AI conversation
  archive, export scripts, archive tooling.

Before any Git write operation, briefly state: **current worktree, current
branch, intended target branch.** Refuse to run Git commands if the intended
worktree is ambiguous.

## Git rules

**Application code (`/workspaces/fhir-agent`)**
- Never commit directly to `main`.
- For any change to `main`-branch work, **default to creating a feature branch
  and opening a PR** — do this proactively without asking. Don't ask ambiguous
  "should I branch?" questions each time; just branch and push, then report.
  Only skip the branch/PR if I explicitly say to.
- Never merge branches yourself. Prepare work for GitHub review; keep the PR
  up to date as work continues.
- After a PR is merged, **always ask to delete the feature branch** — both the
  `origin` remote branch and the local branch. Delete only after I confirm, and
  never delete `main` or `ai-chat-history`.

**AI archive (`/workspaces/.ai-chat-history`)**
- Work only on `ai-chat-history`.
- Never open a PR; never merge `ai-chat-history` into `main`.
- Commit directly after successful testing and push to `origin/ai-chat-history`.
- Keep archive commits isolated from application history.

## Terminal usage

- Run one logical operation per state-changing or order-dependent step, and
  inspect its result before the next. Do **not** chain inspect + modify + test +
  commit + push into a single `&&`/`;` command.
- Batching **independent read-only** commands in one turn is fine and preferred.
- Avoid interactive commands; use non-interactive Git flags.
- If a command is denied or the UI marks it **Skipped**: stop, report it, and
  wait — never assume a skipped/denied command succeeded.

## How to work

Behave like a pragmatic senior engineer. Optimise for working software:

- Make reasonable assumptions when risk is low; state them briefly if helpful
  and continue rather than stopping for clarification.
- Implement the smallest useful solution. Don't over-engineer; avoid premature
  optimisation and unnecessary abstractions. Match the existing codebase.
- Refactor only when it clearly improves maintainability or saves real future
  effort. Don't expand scope unless asked.
- Reserve deep architectural analysis for changes that are hard to reverse or
  touch production reliability, **security, privacy, healthcare compliance, or
  data integrity.**

Stop and ask before: deleting files, destructive Git operations, changing infra
or deployment config, or modifying security-sensitive code. Protect secrets —
never expose credentials or commit sensitive information.

## Communication

Keep responses concise: briefly explain the approach, do the work, summarise the
result. Don't narrate every small action.

When work is complete, report: files changed, validation performed, branch name,
commit hash (if committed), and any known limitations.
