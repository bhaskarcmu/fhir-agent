# Epic Emulator

> **Status: placeholder — no implementation.** This module intentionally reserves the shape of
> the design. There is no code here yet.

## Intent

The platform is built against a **generic FHIR R4 endpoint first**
([`fhir-service`](../fhir-service/README.md)), so the agent and MCP tooling stay portable across
EHRs. Real EHRs then differ from stock FHIR in predictable ways. This module is where
**Epic-specific** deviations would live, so they never leak into the generic data layer or the
clinical logic:

- Epic-flavoured **auth** stubs (OAuth2 / SMART-on-FHIR launch context).
- Epic **custom profiles** and proprietary extensions.
- Endpoint and behaviour quirks worth emulating for realistic integration testing.

## Non-goals

- **Not** a fork of `fhir-service`. Generic R4 behaviour stays there; only Epic-specific
  deviations belong here.
- **Not** a claims/adjudication core. That is
  [`rxclaim-emulator`](../rxclaim-emulator/README.md) — a deliberately different category
  (non-FHIR, transactional legacy), kept a *sibling* of the EHR emulators rather than a member
  (deviation D2 in
  [`docs/phase2/requirements.md`](../docs/phase2/requirements.md#deviations-from-the-prd)).
- **Not** a certified or complete Epic implementation — an emulator for development and testing,
  never a conformance claim.
- **Not** on the current critical path. Phase 2 (claims adjudication) took priority; see
  [`docs/phase2/plan.md` §16](../docs/phase2/plan.md#16-future-work).

## If you pick this up

Start from the generic server's contract and add only what genuinely differs. The value of this
module is proving the platform's **portability claim** — that an EHR's peculiarities can be
absorbed at the edge without touching `client/clinical`, `triage-service`, or `mcp-agent`. If
implementing it requires changing those, the abstraction is wrong, and that finding is worth
more than the emulator.
