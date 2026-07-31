# Phase 4 Testing & Analysis — Input to Defining Phase 5

**Status:** DRAFT — a testing/analysis exercise performed after Phase 4 (M1–M5) was complete and
merged, not a Phase 5 PRD itself. Everything below is either something actually run against live
services, or a review of actual merged code — nothing here is speculative.
**Method:** three passes over the same completed system, each asking a different question of it —
a clinician asking "is this safe," a business stakeholder asking "is this valuable and honest to
show," an architect asking "is this well-built and what should change." Findings are ranked by
severity, not by which hat found them.

---

## 0. Headline finding — read this first

**`epic-emulator`'s pagination quirk (M4, quirk A) can cause a real, silent, false-negative
clinical safety result.** Verified live, twice, with real running services (not simulated):

A patient with more than 20 active `AllergyIntolerance` records — a real-world count for e.g. an
elderly patient with a long-documented allergy history — gets **only the first 20** returned
through `epic-emulator`, because `client/clinical`'s FHIR client (used by `triage-service`) never
follows FHIR's `Bundle.link[relation=next]` pagination link; it assumes one page is the whole
answer. If the clinically-relevant allergy (in this test: penicillin) happens to fall on page 2, it
is silently dropped **before triage-service's rule engine ever sees it**.

| | Direct to `fhir-service` | Via `epic-emulator` |
|---|---|---|
| Allergy records returned for a 22-allergy test patient | 22 of 22 | **20 of 22** |
| Penicillin allergy present in the response? | Yes | **No** |
| `triage-service` risk result for Amoxicillin | **HIGH** — "CONFLICT DETECTED... Do not dispense" | **LOW** — "Safe to dispense" |

No error, no warning, no non-200 status — a `200 OK` response that looks completely normal and
says the opposite of the truth. This is the single most important finding in this document; see
§1.1 for full detail and §4 for the recommended fix. **It is a live bug in already-merged code on
`main`, not a hypothetical future risk** — it should not wait for a full Phase 5 to be scheduled.

---

## 1. The clinician's hat — is this safe?

Testing here means: exercise the actual clinical decision path, deliberately including inputs the
existing M1–M5 test suite never tried, and look for cases where the *answer* changes, not just
where the *mechanism* behaves as designed.

### 1.1 CRITICAL — pagination cap silently truncates safety-relevant data

Detail beyond the headline: the existing M4/M5 test suites never caught this because the only
patient fixture in use throughout Phase 4 (`Kristle Mraz`, per `data/scripts/seed_demo.py`) has
exactly one allergy record — comfortably inside the pagination cap. Every quirk-A test that exists
(`QuirksIntegrationTest`) checks that the cap is *applied* and that a `next` link is *rewritten* —
none of them check what a realistic multi-record patient's clinical outcome looks like on the far
side of that cap. The mechanism was tested; the consequence was not.

This is not a contrived edge case. Long-term patients with multiple documented allergies,
medication lists that grow over years of refills, or any bulk chart-review scenario will
realistically exceed 20 records. The cap value (20, `epic.quirks.pagination.max-count`) was
explicitly chosen in M4 as "clearly-below-typical-defaults... not derived from any real
Epic-documented number" (decision E13) specifically to make the cap *demonstrable* — which,
found here, cuts the wrong way: the more demonstrable the quirk, the more realistic patients it
silently breaks.

### 1.2 Checked and found safe: quirk B fails loud, not silent

Verified: if `epic-emulator` ever rejects a `MedicationRequest` search (missing `patient`/`status`
— quirk B), the rejection is a `400`, which `client/clinical`'s `_request()` turns into a raised
`FHIRClientError`, which `triage-service`'s own exception handling (`main.py`) turns into an
explicit `502` returned to the caller — **not** a silently-empty medication list read as "no active
medications, nothing to check." In practice this specific failure mode is moot anyway:
`client/clinical.get_medications()` already always sends both `patient` and `status`, so quirk B
never actually fires against the real client. Worth recording as a *pattern* observation for
whoever builds Phase 5 or extends the quirks list: **an error that surfaces as a loud failure is
safe by construction; an error that surfaces as a quietly-smaller-than-expected success is not** —
§1.1 is exactly the second kind, and it's the one worth being paranoid about generalizing from.

### 1.3 Checked and found safe: the backfilled Epic extension does not leak into clinical text

`client/clinical`'s `_parse_medication`/`_parse_allergy` read only specific known FHIR fields
(`code`, `status`, `criticality`, etc.) — neither reads the generic `extension` array at all, so
M3's synthetic `medication-therapy-class`/`allergy-source-system` backfill is structurally
invisible to the rules engine and to any clinician-facing note text. Confirmed by direct code
reading, not just absence of a symptom.

### 1.4 Regression check: the existing acceptance scenarios still pass

Re-ran `e2e/test_epic_emulator_acceptance.py` post-merge: both the HIGH-risk (drug-allergy
conflict) and LOW-risk control scenarios still produce identical outcomes direct vs. via
`epic-emulator`. This does **not** contradict §1.1 — it confirms the existing scenarios are simply
too small (1 allergy record) to ever cross the pagination boundary. A regression suite built
entirely from one small fixture will always look green regardless of this bug's presence.

---

## 2. The business stakeholder's hat — is this valuable, and can we honestly show it?

### 2.1 What can honestly be claimed today

- "We built a working simulation of Epic's integration surface — its login flow, its custom data
  fields, and three specific ways its API behaves differently from the plain FHIR standard — and
  proved our existing clinical workflow still works correctly when pointed at it." **True, and
  demonstrated live** (§0 notwithstanding — the *demo* scenario used in verification happens to
  avoid the bug; see §2.3 for why that matters).
- "This is a certified or verified-accurate simulation of real Epic behavior." **Not true, and the
  project's own documentation says so explicitly** (decision E10, PRD §6/§9): the specific
  parameter values (pagination cap, required-search-parameter set, error-code system) are
  structurally representative placeholders, not confirmed against Epic's real, gated documentation.
  No live Epic sandbox was ever used. This distinction must be preserved in any external-facing
  narrative — "we simulate the *shape* of Epic's quirks" is honest; "we replicate Epic's *exact*
  behavior" is not.

### 2.2 Demo readiness: not yet wired into the existing playbook

`docs/demo-guide.md` — this repo's own established, audience-tailored demo script (clinician,
insurer/payer, architect/developer, layperson, plus a Phase 3 section) — **has no Phase 4 section
at all**. Phase 4 is not in `docker-compose.yml`, has no CI job, and requires a developer to
hand-generate a test keypair and manually start two services with specific env vars (per
`e2e/test_epic_emulator_acceptance.py`'s own docstring) to see it work. This is expected — the PRD
explicitly deferred all of that as out of scope for Phase 4 (§7 non-goals table) — but it means
**Phase 4 cannot be shown to a business audience today without ad hoc setup work first.**

### 2.3 The real business risk here is §1.1, not a technical footnote

If Phase 4 were demoed or piloted today using a patient record with a realistic allergy count, the
demo would show a **false "safe to dispense" for a genuine drug-allergy conflict** — in a platform
whose entire value proposition is catching exactly that. This is a credibility risk, not just an
engineering one: it would be discovered by exactly the kind of stress-testing a serious pilot
evaluator would do, and "the demo only worked because the test patient conveniently had one
allergy" is a bad story to be telling after the fact rather than before it.

### 2.4 Effort delivered, for scoping Phase 5's investment ask

Five milestones, ~2,183 lines of Java across 16 main + 4 test files, 24 unit/integration tests + 2
live end-to-end tests, built and verified (including two genuine cross-cutting bugs found and fixed
along the way — the M4 JDK-HttpServer red herring correctly *not* fixed once found to be a
misdiagnosis, and the real M5 `apikey`-header auth gap that was fixed). This is a reasonable,
contained size for what monolith-first Phase 4 promised — "days, not weeks" per the PRD — and the
methodology (verify everything live, document what wasn't verified rather than assume it) is
itself worth preserving into Phase 5, not just the code.

---

## 3. The architect's hat — is this well-built, and what should change structurally?

### 3.1 Test coverage gap: mechanism-tested, consequence-untested

This is the structural version of §1.1's finding, stated as a testing-strategy problem rather than
a single bug: every quirk-A test in `QuirksIntegrationTest` asserts *that the interceptor did its
job* (count capped, link rewritten, token resolves) — none assert *what a realistic downstream
consumer experiences as a result*. The same pattern is worth auditing across the other two quirks
and the extension backfill before trusting them the same way: the tests prove the code does what
the code was written to do, not that what the code was written to do is safe for every realistic
caller. This is a real, generalizable gap, not specific to pagination — recommend a testing-policy
addition for Phase 5 (§4).

### 3.2 Deployment/CI posture — as documented, not a surprise

Confirmed directly: `epic-emulator` has **no CI job** (`.github/workflows/tests.yml` has no
reference to it — this means §1.1's bug would not be caught by CI even if a test for it existed,
until someone adds the job), **no `docker-compose.yml` entry**, and **no Terraform/cloud stub**
(only a single local-run `Dockerfile`, per the PRD's explicit non-goals). None of this is a
surprise — the PRD scoped it out deliberately — but it means Phase 4's own test suite, however
good it gets, currently only ever runs when a developer remembers to run it by hand. That's a
material risk multiplier on top of §3.1: **a bug like §1.1 can exist in merged code indefinitely
with zero automated signal.**

### 3.3 Coupling note (PRD G6), revisited with two more data points

[`docs/phase4/coupling-note.md`](../phase4/coupling-note.md) already captured the main structural
finding (error-shape formatting is genuinely cross-cutting between auth and quirks, not owned by
either). Two additions from this pass:

- **The pagination/extension response-processing pipeline and the *client* library on the other
  side of the wire are more coupled than the coupling note's original framing acknowledged.**
  §1.1 isn't really a coupling problem *inside* `epic-emulator` — it's a coupling problem between
  `epic-emulator`'s quirk-A behavior and an assumption baked into `client/clinical` (that one page
  is the whole answer) that Phase 4 never had reason to touch or verify until this pass. Any future
  quirk that changes response *shape* needs the same downstream-consumer check, not just an
  in-process unit test.
- **Security/secrets posture held up under scrutiny.** The e2e fixture's test-only keypair is
  correctly non-sensitive and correctly allowlisted (`.gitleaks.toml`) rather than hidden; no real
  credentials appear anywhere in the module. No new finding here — noted because it was checked,
  not assumed.

### 3.4 What Phase 5 decomposition evidence actually says (restating coupling-note's conclusion)

Auth remains the safest first candidate for independent extraction (§ per coupling-note.md).
Extension handling and pagination's shared response-processing stage argue for keeping those two
together, or defining a real pipeline contract before splitting them. Error-shape formatting
doesn't cleanly belong to any one area. Nothing in this testing pass changes that conclusion — it
adds §3.3's downstream-consumer-coupling point as a new, fourth consideration.

---

## 4. Recommendations for Phase 5 (and one thing before it)

### 4.0 Before Phase 5 starts: fix or mitigate §1.1

This is a live safety-relevant bug in merged code, not a Phase 5 backlog item. Two real fix
options, not mutually exclusive:

1. **The durable fix:** make `client/clinical`'s FHIR client follow `Bundle.link[relation=next]`
   when fetching medications/allergies. This is the correct behavior against *any* real FHIR
   server, not just `epic-emulator` — Phase 4 only surfaced a pre-existing latent gap in Phase 1
   code, it didn't create the underlying assumption. This does touch `triage-service`'s dependency
   (`client/clinical`), which is more invasive than anything Phase 4 itself touched.
2. **The fast mitigation:** raise `epic.quirks.pagination.max-count`'s default well above any
   realistic patient record count (or make quirk A's cap configurable per-deployment with a safe
   default), so the emulator's own demonstrability doesn't come at the cost of plausible patients
   silently losing data. This doesn't fix the underlying client gap (a real Epic server could still
   paginate at a value the client doesn't expect) but closes the immediate hole.

**This wasn't fixed as part of this analysis — it's flagged for an explicit decision** on priority
and approach before treating Phase 4 as fully closed.

### 4.1 Testing policy: add consequence-level tests, not just mechanism-level ones

For any quirk or backfill that changes response *shape or content*, require at least one test that
exercises it through the same client code path a real consumer uses (as `e2e/
test_epic_emulator_acceptance.py` already does for the happy path) with a realistic *volume* of
data, not just a realistic *shape* of data. §1.1 would have been caught by a 25-allergy fixture in
the existing e2e test.

### 4.2 Wire epic-emulator into CI

At minimum: a `phase4-java` job running `mvn -f epic-emulator/pom.xml test` on every PR (mirroring
`phase2-java`/`phase3` conventions already established), so this module's own test suite — once
§4.1 closes the coverage gap — actually runs automatically instead of depending on a developer
remembering to.

### 4.3 Decompose auth first, if/when Phase 5 decomposes at all

Per the coupling note: auth is evidence-backed as the cleanest split. Extension handling and
pagination should stay together unless a real pipeline contract is designed first. Error-shape
formatting needs an explicit home (shared library, or its own small service) rather than being
implicitly owned by "whichever area happened to build it first."

### 4.4 Resolve E10 if real Epic access ever becomes available

Every quirk/extension specific value in this module remains an unverified, structurally-plausible
placeholder (decision E10). If a future effort gets real Epic sandbox or documentation access, this
is the one item that would most change what's actually built here — including, possibly, the exact
pagination cap value that made §1.1 possible in the first place.

### 4.5 Update the demo guide, once §4.0 is resolved

Don't add Phase 4 to `docs/demo-guide.md` until §4.0 has a resolution — a demo built on the current
pagination behavior risks reproducing §2.3's exact scenario in front of a real audience.
