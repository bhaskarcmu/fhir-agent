# Documentation

Start with what you're trying to do.

| I want to… | Read | Time |
|---|---|---|
| **See the system work** — or show it to someone | [`demo-guide.md`](./demo-guide.md) | 5–15 min |
| **Understand the code and change it** | [`developer-guide.md`](./developer-guide.md) | 20 min |
| **Run the tests, or write good ones** | [`testing-guide.md`](./testing-guide.md) | 15 min |
| **Operate the gateway** (local, cloud, or the migration) | [`gateway-runbook.md`](./gateway-runbook.md) | 10 min |
| **Know why it's built this way** | [`phase2/plan.md`](./phase2/plan.md) | 30 min |
| **Audit what was decided, and whether it still holds** | [`phase2/decisions.md`](./phase2/decisions.md) | 5 min |
| **Know exactly what was agreed** (normative) | [`phase2/requirements.md`](./phase2/requirements.md) | reference |
| **Know what to build next** | [`phase2/plan.md` §16](./phase2/plan.md#16-future-work) | 5 min |

## The guides

**[Demo guide](./demo-guide.md)** — how to experience the system, and how to demo it to four
audiences (clinician, insurer, architect/developer, layperson). Includes the prep checklist that
stops a demo failing in front of people: the FHIR server is in-memory and adjudication fails
closed, so you must seed first.

**[Developer guide](./developer-guide.md)** — the mental model, the lifecycle of one claim
through the packages, the invariants you must not break, the local dev loop, a list of traps that
have already cost real hours, and how to add a rule / a downstream call / a FHIR artefact.

**[Testing guide](./testing-guide.md)** — what is tested (with counts), what is *not* (with
honesty), how to run every level, and how to write unit / white-box / component / interface /
e2e tests here. Its case study — how a dead clinical-safety check passed every test for several
milestones — is the most useful thing in this folder.

**[Gateway runbook](./gateway-runbook.md)** — the single operational source of truth for the Kong
edge across **both** phases: why two gateways exist, which one owns which route in each strangler
state (S0/S1/S2), exact local procedures (including the template→generated config flow), the
cloud position, the migration and its rollback, and troubleshooting.

## Design and decisions

**[`phase2/`](./phase2/README.md)** — the claims-adjudication modernisation slice.

- **[`decisions.md`](./phase2/decisions.md)** — the ADR-style index of every architectural
  decision (D1–D8, C1–C4, plus later ones) with **status and supersession markers**, linking to
  where each rationale lives. Start here to audit *what was decided and whether it still holds*.

- **[`requirements.md`](./phase2/requirements.md)** — normative. Requirements R1–R19, including
  the Decision Contract (R17), audit invariants and idempotency (R18), and the test matrix (R19).
  What we agreed to build, and deviations from the source PRD. No implementation detail, no
  status, no commit history.
- **[`plan.md`](./phase2/plan.md)** — architecture, service topology, gateway and local/cloud
  parity, cloud design, milestones, engineering standards, and **§16 future work**.
- **[`source-prd.md`](./phase2/source-prd.md)** — the archived DRAFT PRD that seeded the work.
  The *input*, not the contract; kept for provenance.

## Conventions for this folder

- **`requirements.md` is normative and stable.** It says *what must be true*. It does not carry
  status, milestones, branches, commits, or PR numbers — those live in git history and the plan.
- **`plan.md` says how and in what order**, including what's next.
- **The guides are practical.** They tell you what to type and what will bite you.
- **Service-level READMEs** (`claims-service/`, `triage-service/`, `gateway/`, `data/`, …) cover
  that component's own detail. The guides link to them rather than restating them.

## Elsewhere in the repo

| Path | What |
|---|---|
| [`../README.md`](../README.md) | Project overview and quick start |
| [`../CLAUDE.md`](../CLAUDE.md) | Working agreements: git rules, the two worktrees, how to work here (mirrored in `.clinerules`) |
| [`../data/reference/README.md`](../data/reference/README.md) | Reference-data source catalog (CMS Part D, ACA/QHP) with verified URLs |
| [`../data/payer-kb/README.md`](../data/payer-kb/README.md) | The curated payer knowledge base fixtures |
| [`../gateway/README.md`](../gateway/README.md) | Kong: KIC (Phase 1, GKE) and DB-less (Phase 2) |
