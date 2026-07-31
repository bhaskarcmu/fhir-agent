# Critique Phase 4 epic-emulator problem statement

## Turn 1

### Prompt

I want to implement a Phase 4 now. Planning and brainstorming comes first, so do not implement or write anything yet. Do not yet architect anything, think about writing a PRD in subsequent prompts, not right now.

First, critique this problem statement:

__________________

Problem Statement — epic-emulator (Phase 4)

Context. fhir-service is intentionally EHR-agnostic. Per its roadmap, epic-emulator is the still-unbuilt module meant to simulate Epic-specific integration behavior — Epic's authentication flows, custom FHIR extensions/profiles, and proprietary API quirks — so the rest of the platform can be developed and tested against realistic Epic-like behavior without a real Epic sandbox.

Why monolith-first, specifically (the engineering rationale). The domain boundaries within Epic emulation are not yet known. Auth flow, custom extension handling, and proprietary-quirk simulation might turn out to be cleanly separable — or they might turn out to share more state and logic than expected (e.g., auth context needed by extension validation, shared request/response shaping across "quirks"). Committing to service boundaries now, before writing any real code against them, risks locking in an incorrect cut that becomes expensive to undo across separate repos, deploy pipelines, and network contracts. Per Fowler's MonolithFirst pattern, the correct sequence is: build it together, let real usage reveal where the actual seams are, then decompose along boundaries that are now evidence-based rather than guessed.

The problem to solve in Phase 4. Build a working, end-to-end epic-emulator as one deployable Spring Boot application, one Maven build, optimized for speed to a working prototype. Concretely, Phase 4 is scoped to skip every piece of work that would only be justified once real service boundaries exist:

Skipped in Phase 4 (deferred to Phase 5)	Why it's safe to skip now
Separate repos/builds per capability area	No confirmed boundary to split along yet
Per-area Dockerfiles / container images	One process to run and iterate on locally
K8s manifests, Kong routes per area	No independent deployability claim being made yet
Inter-area REST contracts / DTOs / serialization	No network boundary exists yet — direct method calls are correct, not sloppy
Per-area CI pipelines, integration tests across a network boundary	Nothing to integration-test across yet

This list is the speed argument — each row is real time and complexity a microservices-first approach would have paid upfront, before knowing if the boundary was even right.

Candidate capability areas (hypotheses to validate during Phase 4 — not commitments; Phase 5's actual decomposition should follow what real coupling patterns show up, not this list):

Epic auth emulation — SMART-on-FHIR / backend-services OAuth2 flow simulation.
Epic custom profile & extension handling — validating/injecting Epic-specific FHIR extensions on top of fhir-service's base R4 resources.
Epic proprietary quirks — non-standard pagination, search params, error shapes.


Explicit non-goals for Phase 4. Independent deployability, internal API boundaries between areas, containerization beyond a single local-run Dockerfile, production hardening. These aren't omissions — they're costs correctly deferred until Phase 5 has evidence to spend them well.

Constraints. Java 21, Spring Boot, Maven — same toolchain already proven in fhir-service, so none of Phase 5's later containerization/K8s/Kong work is new territory, only newly justified.

Success criteria for Phase 4.

All three candidate capability areas demonstrably working end-to-end, in one running process.
Zero artifacts from the "skipped" table above exist in the repo at the end of Phase 4 — this is the concrete, checkable evidence for the speed claim.

A short written note (a few sentences, captured for Phase 5) on which capability areas turned out to share state/logic in practice, and which stayed cleanly separate — this is the real output that makes Phase 5's decomposition evidence-based rather than a repeat of the original guess. This should be done with actual testing, mimicking business and clinical stakeholders assessments.

Forward note for Phase 5. Decomposition boundaries should be derived from what Phase 4 actually revealed about coupling and change patterns — not from the candidate list above verbatim. If two "areas" turned out to share significant state, that's a signal they may belong in the same service even after decomposition; that's the MonolithFirst payoff, and it's the part of this exercise that makes the whole Phase 4 → Phase 5 story a legitimate engineering decision rather than a staged one.

### Claude response

*[Claude has not completed this turn yet.]*

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `265be5b6-c550-4af6-bed7-7be2bca6b9c4`
- **Created:** 31 July 2026, 12:31 UTC
- **Last updated:** 31 July 2026, 12:31 UTC
- **Turns:** 1
- **Status:** Incomplete
