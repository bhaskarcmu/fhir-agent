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

Solid structure overall — the skip-table-with-rationale and the "zero artifacts" check are good instincts. But there are real gaps, ranked by how much they matter:

**1. The document justifies the easy decision and skips the hard one.**
Most of the word count defends "don't split into 3 microservices yet." But nobody was seriously proposing that — three tightly-coupled sub-features of one emulator becoming three separate repos/deploys was never a live option worth this much argument. Citing Fowler's MonolithFirst (which is about whether a *new product* starts as microservices) to justify not over-decomposing a single module is solving a strawman. The actual hard question — **what does "correctly emulating Epic" even mean, and how do you know you got it right without a real Epic sandbox** — gets zero words. That's the riskier unknown and belongs in the problem statement, not the module-boundary question.

**2. "Demonstrably working end-to-end" has no source of truth.**
Working against what reference? Epic's published FHIR API docs / SMART Backend Services spec / App Orchard sandbox behavior? Without naming an authority to emulate against, "working" is whatever the implementer assumed, and Phase 5 (or a real Epic integration later) could discover the emulation was subtly wrong in ways the success criteria never would have caught.

**3. "Proprietary quirks" is unbounded scope, not a capability.**
Auth flow and custom extensions are concrete. "Quirks" (pagination, search params, error shapes) is an open-ended grab-bag that could expand indefinitely — which directly undermines the stated "optimized for speed" goal. This needs a specific, enumerated, closed list for Phase 4, or it'll be the thing that blows the timebox.

**4. No integration story.**
Who actually calls epic-emulator, and how does a developer switch between it and real fhir-service? Does it sit in front of fhir-service as a proxy, wrap it, or run standalone with its own store? Given the existing convention that `client/clinical` and `client/platform` serve different audiences, which one talks to epic-emulator matters and isn't addressed.

**5. The MonolithFirst argument is weaker here than in its original context.**
Fowler's pattern relies on *real production usage* revealing seams. Here the "usage" will be internal test suites exercising three areas together — which is fine, but it should be stated explicitly as the mechanism, and the success criteria should require enough test depth that the coupling findings in Phase 4's closing note are actually trustworthy, not superficial.

**6. "Zero artifacts from the skip table" is necessary but gameable.**
It's an absence check, not a correctness check. You could satisfy it letter-for-letter while still building internal package boundaries with DTO-style interfaces and strict method contracts between "areas" — i.e., paying microservice-shaped costs without any of the artifacts. Worth a note that the spirit (not just deployment artifacts) is being checked.

**7. Success criterion #3's stakeholder-testing sentence is out of place.**
"This should be done with actual testing, mimicking business and clinical stakeholder assessments" — for what is fundamentally a technical integration/auth/protocol emulator, it's unclear what a clinical stakeholder is assessing. Either this means "get a demo sign-off" or it's conflating two different kinds of validation. Needs disambiguation before it goes in a PRD.

**8. Security sensitivity of the auth-emulation piece is unflagged.**
Per this repo's own rules, security-sensitive code gets deeper scrutiny regardless of "it's just a prototype." Emulating OAuth2/SMART-on-FHIR backend-services flow means fake tokens/keys/signing — worth an explicit callout so shortcuts here don't later get mistaken for validated patterns elsewhere.

**Smaller open questions worth resolving before a PRD:**
- Where does epic-emulator physically live — new top-level dir, or a module under `fhir-service/`? Affects Maven setup and the repo table in CLAUDE.md.
- Data/fixtures: reuse `data/scripts/` Synthea generation, or does Epic-flavored data need its own fixtures?
- No timebox or rough size estimate for Phase 4 — "speed to prototype" isn't falsifiable without one.

Want me to hold these for when you actually draft the PRD, or react to any of them now?

## Turn 2

### Prompt

I want you to build a monolith first. Justify that using your best judgement - answer your own questions by modifying and changing, if necessary, the problem statement itself. Fill in the gaps, maybe give me options to choose from. I want to build a monolith real fast without consulting business and clinical stakeholders too much. Or tell me hos else to justify this.

### Claude response

*[Claude has not completed this turn yet.]*

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `265be5b6-c550-4af6-bed7-7be2bca6b9c4`
- **Created:** 31 July 2026, 12:31 UTC
- **Last updated:** 31 July 2026, 12:37 UTC
- **Turns:** 2
- **Status:** Incomplete
