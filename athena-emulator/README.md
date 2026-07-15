# Athena Emulator

> **Status: placeholder — no implementation.** This module intentionally reserves the shape of
> the design. There is no code here yet.

## Intent

The platform is built against a **generic FHIR R4 endpoint first**
([`fhir-service`](../fhir-service/README.md)), so the agent and MCP tooling stay portable across
EHRs. This module is where **athenahealth-specific** deviations would live, so they never leak
into the generic data layer or the clinical logic:

- Athena-flavoured **auth** stubs.
- Athena **custom profiles**, extensions, and endpoint quirks.
- Behaviour differences worth emulating for realistic integration testing.

Its existence alongside [`epic-emulator`](../epic-emulator/README.md) is the point: **two**
EHR-specific edges over one generic core is what makes portability a testable claim rather than
an assertion. One emulator proves nothing — the second is where leaky abstractions surface.

## Non-goals

- **Not** a fork of `fhir-service`. Generic R4 behaviour stays there.
- **Not** a claims/adjudication core — that is
  [`rxclaim-emulator`](../rxclaim-emulator/README.md), a deliberately separate category
  (deviation D2 in
  [`docs/phase2/requirements.md`](../docs/phase2/requirements.md#deviations-from-the-prd)).
- **Not** a certified or complete athenahealth implementation — for development and testing,
  never a conformance claim.
- **Not** on the current critical path. Phase 2 (claims adjudication) took priority; see
  [`docs/phase2/plan.md` §16](../docs/phase2/plan.md#16-future-work).

## If you pick this up

Add only what genuinely differs from the generic server. If absorbing Athena's peculiarities
requires changing `client/clinical`, `triage-service`, or `mcp-agent`, the abstraction is wrong
— report that rather than working around it.
