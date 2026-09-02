# Phase 7: Medication Reconciliation

## Turn 1

### Prompt

I want to srart Phase 7 for Patient Medications Reconciliation, with the following scope:

==========================

Capability. Given a confirmed patient identity and a discharge encounter, retrieve the medication list from each connected source independently, normalize each entry to a standard drug concept, and return a reconciled view that preserves every source's contribution, labels each line by discrepancy type, and attaches the source and timestamp to every field. Connected sources should include at least Epic EHR and Athena EHR APIs, plus any additional capabilities that the environment provides (more to be clarified later).

Trigger A — event. A facility admission or discharge notification supplies the patient identity and the encounter context.

Trigger B — on demand. A clinician supplies demographics; the system resolves candidates and requires human confirmation of both patient and encounter before retrieval.

Non-goals. Does not produce a single merged medication list. Does not auto-resolve ambiguous patient identity. Does not assess drug interactions.

Acceptance criteria. Every returned line carries its source, that source's response time, and its match confidence. Any source that did not respond is reported as unreachable, never as empty. Entries that could not be coded are counted and surfaced, never dropped. A single unreachable source yields an incomplete-sources outcome, never a reconciled one.

===========================

Tell me first if "Phase 7" is an available, compltetely unused, phase for this!

### Claude response

I'll check whether "Phase 7" has already been used anywhere in this repo before answering.

Yes — **Phase 7 is completely unused.** I checked docs/ (only phase2–phase6 exist), git log/branches/PR titles (highest is phase6, all merged), and grepped the whole tree for "phase 7" / "phase7" — zero hits anywhere.

Two things from that search are directly relevant to how you scope this, though:

1. **Athena is not real yet.** `athena-emulator/` is an explicit placeholder — no auth, no data, nothing implemented (confirmed in its README and `docs/phase4/README.md`). If Phase 7 needs to actually query "Athena EHR APIs," that's new build work, not an existing integration to point at. Worth deciding up front whether Phase 7 builds out athena-emulator, or targets a real Athena sandbox, or treats Athena as an environment-provided source to defer (your "more to be clarified later" already leaves room for this).

2. **Epic-emulator (Phase 4) has a known unresolved safety bug.** `docs/phase5/README.md` documents E16: its pagination cap can silently drop records (documented for allergies, but the same pagination path likely affects medication lists too) — flagged as a precondition to fix/mitigate before building more on top of it. Given your acceptance criteria explicitly demand *no silent drops, ever* for coded/uncoded entries, this bug is squarely in Phase 7's blast radius if Epic is one of your two required sources.

Neither blocks calling this "Phase 7" — Phase 5 stays reserved separately for epic-emulator decomposition and doesn't conflict with a new Phase 7 number.

Want me to draft the standard `docs/phase7/prd.md` + `design.md` (matching the pattern the other phases use), or do you want to go straight to a milestone breakdown?

## Turn 2

### Prompt

Tell me based on what you know so far, if "Patient Medications Reconciliation" is a good name for this phase. And, here is more inout to help with PRD writing:

======================
Why medication reconciliation is the right slice

Three reasons, in order of how much they'll matter.

One: it's the only transitions-of-care requirement that is genuinely a data-merge problem. Of the four national transitions-of-care indicators, three are essentially "did someone do a thing and write it down" — notification received, discharge information received, patient contacted. Medication reconciliation is different. It is defined as comparing the medications ordered at discharge against the most recent medication list in the outpatient record and resolving the differences (NCQA, Humana measure flyer). That is literally a two-source join with conflict resolution. It's the one indicator you cannot satisfy without solving the problem you actually solved at Oak Street.

Two: the regulation already describes the architecture you want to build. The Joint Commission's medication safety goal spells out the steps: obtain the current medication list including name, dose, route, frequency, duration and purpose; compare it against what the organization has ordered "in order to identify and resolve discrepancies"; and it explicitly defines discrepancies as "omissions, duplications, contraindications, unclear information, and changes." It also includes this note: "It is often difficult to obtain complete information on current medications... A good faith effort to obtain this information from a patient or resident and/or other sources will be considered as meeting the intent" (The Joint Commission, effective January 2026).

Read that last note again. The regulator has written your fail-closed doctrine into the standard: incomplete is an acceptable outcome as long as you documented the attempt. Your existing output_gate.py / fail_closed.py pattern is already the right answer, and now it has a regulatory citation rather than just being good engineering taste.

Three: the problem is real and heavily documented. A study of 339 older patients found 68% experienced unintentional medication discrepancies somewhere in their care transitions — 35% at admission, 20% at transfer, and 49% at discharge (PMC). A systematic review found the median rate of unintentional medication discrepancies after discharge was around 50% (PMC). And specific to your nursing-home gap: at least one discrepancy occurs in 75% of hospital-to-nursing-facility admissions (UCLA, citing Kerstenetsky et al.). Half of transitions produce a medication error. You don't have to argue that this matters.

Your repo already has the socket for this
This is the part that makes the answer an emphatic yes rather than a "sure, you could."

From your own Phase 4 documentation: epic-emulator is built through M5 — pass-through proxy, simulated backend-services auth, Epic-style extension backfill on MedicationRequest and AllergyIntolerance, three named quirks including the required patient + status parameter combination and Epic-shaped error responses. And then there's this, written by you:

"This module was reserved as an empty placeholder back in Phase 2 alongside a sibling athena-emulator. That sibling remains a placeholder — Phase 4 builds out only the Epic half. The original two-emulator 'portability isn't provable with just one edge' framing is not fulfilled by Phase 4 alone; whether athena-emulator is ever built is a separate, later decision."

You left yourself the exact door you now want to walk through. Medication reconciliation is the first use case that genuinely requires two edges — a single-source med list needs no reconciling. So the story isn't "I added another emulator for symmetry." It's "I found the workload that made the second edge necessary, and building it proved the portability claim I'd only asserted."

Everything else you need is also already there: triage-service already fetches medications and allergies and returns a RiskAssessment with basis references; your rules engine already detects duplicate therapeutic class, which is one of the four reconciliation conflict types; claims-service already emits Provenance; and your Phase 6 agent already re-fetches rather than recalling medication data. This is an extension, not a new project.

What you can actually get, for free
Source	Reality	Use in this build
Epic sandbox	Free developer signup; R4 base at https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/, live capability statement confirms FHIR 4.0.1 (Epic on FHIR, metadata)	The hospital-side list
Epic MedicationRequest	Read + Search, R4, with a documented required-parameter pattern	Discharge orders
Epic Outside Record APIs	Medication, MedicationRequest, and MedicationDispense all have distinct (Outside Record) variants at R4 (Epic on FHIR)	See below — this is the find
Epic MedicationDispense (Fill Status)	Read + Search, R4	Did the patient actually pick it up
athenahealth R4	Published sandbox base URLs, e.g. https://ap23sandbox.fhirapi.athenahealth.com/demoAPIServer/fhir/r4 (athenahealth GitHub); implementation guide v25.0.0 (athenahealth)	The outpatient-side list
RxNorm / RxNav	Free, no API key, no license for the RxNorm API; findRxcuiByString supports exact, normalized, and approximate matching — normalized ignores word order, punctuation, inflections and salt forms, so "morphine sulfate" resolves to morphine and "hctz" matches hydrochlorothiazide (NLM, NLM FAQs)	The matching engine
US Core MedicationRequest	Servers SHALL support patient + intent=order,plan, and SHALL support _include=MedicationRequest:medication (HL7 US Core)	Your portable contract
Two things to note carefully.

The Outside Record APIs are the whole thesis in one detail. Epic ships a separate set of medication endpoints for data that originated outside the organization. Which means Epic itself models "this came from somewhere else" as a first-class, structurally distinct thing — because provenance changes how the data may be trusted. Every reconciliation engine has to make that same distinction. If you build it, you're not imitating Epic's design, you're independently arriving at it, and you can say so.

One caveat to verify before you assert it. The athenahealth R4 implementation guide describes the API server in "athenaPractice and athenaFlow products" (athenahealth) — those are the former GE Centricity lines, not athenaOne, whose API sits at a different base (per this integration guide — treat that source as secondary). Confirm which one you're hitting before you say "athenahealth" flatly in an interview. Getting that distinction right is itself a credibility signal; getting it wrong in front of someone who knows is expensive.

The trap to avoid
Do not build a drug-interaction checker. The National Library of Medicine discontinued the free RxNav drug-drug interaction API on or about January 2, 2024, and removed the Interactions tab from the web interface at the same time. NLM's own FAQ confirms it and lists the two sources it had drawn from (NLM RxNav, NLM FAQs). Salesforce removed the drug-interaction tab from its Medication Management product as a direct consequence (Salesforce release notes).

There is a real upside here. Knowing this makes you sound like someone who has actually shipped against these APIs rather than read about them. And the correct architectural response is a good answer in itself: interaction checking is a licensed-content dependency, so you isolate it behind an interface with a null implementation, and your gate returns "cannot assess" rather than "no interactions found." An empty result from a dead endpoint rendered as "safe" is exactly the class of bug your fail-closed module exists to prevent.

What the build actually looks like
Six components. Call it Phase 7.

1. athena-emulator — finally build it. Same shape as epic-emulator: proxy in front of fhir-service, its own auth flavor, its own quirks. Deliberately make its quirks different from Epic's — different pagination behavior, different required parameters, different error envelope. The point of the second edge is to make source-specific behavior impossible to hide in shared code.

2. med-normalizer — the honest hard part. Two lists never match on strings. Metoprolol tartrate 25mg twice daily versus metoprolol succinate 50mg extended-release once daily: same ingredient, different salt, different release profile, different clinical meaning. Resolve every entry to an RxNorm concept identifier and record which term type you landed on — the ingredient level, the clinical drug level, or the branded level. Then classify the match:

Identical — same clinical-drug concept, same dose, same frequency

Equivalent — same concept, differences that don't change therapy

Same ingredient, different product — the metoprolol case; needs a human

Ingredient-level only — you matched, but not precisely enough to compare doses

Unresolved — you could not code it

That last bucket is the most important thing on the screen. A reconciliation tool that silently drops what it couldn't parse is worse than no tool, because it manufactures false confidence. Report the unresolved count as a headline number, not a footnote.

3. recon-engine — the four discrepancy types the regulator names. Use their vocabulary, not your own: omission (present at discharge, absent in the outpatient list), addition/duplication (the same therapeutic class twice — you already have this rule), change (dose, route, or frequency differs), and unclear (couldn't code, or sources conflict irreconcilably). Emit each one with the source that contributed each side, the timestamp of each side, and the match classification. Your existing RiskAssessment + basis-reference pattern already produces exactly this shape.

4. A precedence policy that lives in a config file, not in code. Which source wins, per field, with reasons. Discharge orders beat the outpatient list on what was prescribed because they're newer. The outpatient list may beat discharge orders on what the patient is actually taking because the clinic knows the patient. Fill data beats both on whether the drug was ever obtained. Put it in YAML next to policy.md so a reviewer can read your clinical reasoning without reading Java. Reviewers who can read the policy trust the code more.

5. Provenance and freshness on every single field. Provenance resources are already in your claims service — extend them here. Each reconciled line carries which system it came from, when that system last answered, and how old the underlying record is. Then the rule you already believe in: a source that didn't answer renders as "we could not reach athenahealth as of 14:02," never as a blank cell and never as an absence.

6. The gate. Reuse output_gate.py and fail_closed.py unchanged. Outcomes: RECONCILED, DISCREPANCIES_FOUND, INCOMPLETE_SOURCES. There is no "clean" outcome available when a source was unreachable. And because the Joint Commission explicitly accepts a documented good-faith effort, INCOMPLETE_SOURCES isn't a failure state — it's a compliant one, as long as you recorded what you tried. Say that out loud in the interview; it shows you understand that the regulation and the architecture agree.

What you demo in ninety seconds
One patient. Two live sandboxes. On screen: the hospital list, the outpatient list, and the reconciled view in the middle, with each line labeled by discrepancy type, each field showing its source and age, and the unresolved count visible at the top. Then kill the athenahealth emulator mid-demo and show the view degrade to "one source unavailable — reconciliation incomplete" instead of quietly showing a one-sided list that looks complete.

That last five seconds is the entire demo. Anyone can show a working happy path. Almost nobody shows what their product does when a feed goes dark, which is the state a transitions platform is in most of the time.

The lines this earns you
"I picked medication reconciliation because it's the only one of the four transitions indicators you can't satisfy with a workflow checkbox — it requires reconciling two medication lists from two systems that don't agree, which is the problem I actually had at Oak Street with Greenway on one side and Epic on the other."

"The interesting part isn't the API calls, it's the match classification. Same ingredient, different salt, different release profile is not a match, and a tool that scores it as one is dangerous. So every line carries how confidently it was coded, and the count of what couldn't be coded is on the screen, not in a log."

"I built the athenahealth emulator specifically because reconciliation needs two sources. My own Phase 4 notes say portability isn't provable with one edge — this is the workload that made the second edge necessary."

One piece of scope discipline
Don't extend this to the nursing home. The temptation is obvious given everything we've discussed, and it's the wrong move: there is no free nursing-facility API sandbox, so you'd be inventing your data, and an interviewer from PointClickCare will know immediately. Keep the build strictly hospital-to-clinic, where both sources are real.

Then say the extension out loud instead of building it: "This works because both endpoints expose a standards-based API. The reason the same pattern breaks going hospital-to-nursing-facility is that the third list — what the facility is actually administering — only exists inside the facility's own system of record. That's a data-access problem, not an algorithm problem, and it's the gap I'd want to understand how you're closing."

That converts an honest scope limit into your closing question, and it lands you exactly where their product strategy lives.

Is it fair to set the requirement as: "Either through a notification of facility admission/discharge, or through a clinician simply manually asking for medication information by identifying a patient - take a patient's identity as input and find their latest set of medications" ?

Mostly fair. The trigger half is right and the input half hides the two hardest problems in the build. Let me take it apart.

What's right
Separating the trigger from the capability is correct, and it's the thing junior requirements get wrong. Both paths converge on one operation — resolve a patient, then assemble their medications — and only the entry point differs. That means one testable core with two thin adapters in front of it, instead of two parallel implementations that drift. Keep that.

It also correctly refuses to make the notification the product. That's the same point you made about pings, expressed as a requirement, and it's the right instinct.

Problem one: "take a patient's identity as input" is the project, not the input
Those five words are where most of the engineering lives, and stating them as a given is the kind of thing an architect will probe.

There is no portable patient identity. A medical record number is reliable inside one organization and not portable outside it, because source systems use different identifier namespaces — the hospital's number for the patient is not your number for the patient (FirestarterPro — secondary source, but the claim is uncontroversial). So Epic requires one of several minimum data sets before it will match a patient at all: the Epic FHIR identifier, a typed identifier pair, a social security number, given plus family name plus birth date, or given plus family name plus legal sex plus phone or email (reported here — treat as secondary; Epic's own guidance points developers to the Patient.$match demographics operation for finding an existing record, Epic on FHIR).

And the standards treat this as a distinct, hard operation rather than a search. Patient/$match accepts a partially complete Patient resource and hands it to a master patient index, which returns candidates with scores (HL7 FHIR). There is an entire US implementation guide devoted to extending $match for cross-organizational use, with graded input profiles by identity assurance level (HL7 US Identity Matching IG).

How badly does this fail in practice? Facilities fail to link records for the same patient as often as half the time, and matching within a single facility can be as low as 80% (Pew Charitable Trusts). A study of 398,939 confirmed duplicate records found middle name was the top mismatch field at 58.3%, with social security number second at over half (PMC). And the tolerance is brutally asymmetric: organizations reportedly accept roughly one in a million false positives, because merging two patients' charts is a catastrophic error (University of Memphis thesis).

So your requirement needs to say what happens when identity is ambiguous. The correct behavior is not "pick the best candidate." It's: return the candidate set with match evidence, refuse to merge, and make a human confirm. That's another fail-closed case, and it's a better answer than a clean one.

Also — and this is the part that will land — your two triggers are not equivalent inputs. A facility notification arrives with an encounter attached: which facility, admitted when, discharged when. A clinician typing a name arrives with nothing. That encounter context is what makes the medications reconcilable, because it defines the window. Presenting the two paths as interchangeable with "either/or" flattens a real difference. The manual path needs the clinician to also pick an encounter, or the system has to infer one and say which one it inferred.

Problem two: "their latest set of medications" is the wrong noun
This is the bigger issue, because it quietly contradicts the thing you're building.

There is no latest set. That's the entire premise of reconciliation. There are multiple concurrent lists, each authoritative for a different question — what the hospital ordered at discharge, what the clinic believes the patient is taking, what the pharmacy actually dispensed — and they disagree. "Latest" implies you can order them on one timeline and take the top one. You can't, for three reasons:

Recency is ambiguous. Prescribed-on date, record-last-updated date, and last-clinically-verified date are three different timestamps that answer three different questions, and the newest record is frequently not the truest one.

Newer isn't more authoritative per field. Discharge orders are newer, but the clinic may know the patient stopped taking something. Fill data is the only source that knows whether the drug was ever obtained.

A single flattened list destroys the output. If you return one merged list, you've thrown away the discrepancies — which are the deliverable.

If you build to "find the latest set," you'll build a med list viewer. You already have the better design in your head; the requirement just doesn't say it yet.

The rewrite
Capability. Given a confirmed patient identity and a discharge encounter, retrieve the medication list from each connected source independently, normalize each entry to a standard drug concept, and return a reconciled view that preserves every source's contribution, labels each line by discrepancy type, and attaches the source and timestamp to every field.

Trigger A — event. A facility admission or discharge notification supplies the patient identity and the encounter context.

Trigger B — on demand. A clinician supplies demographics; the system resolves candidates and requires human confirmation of both patient and encounter before retrieval.

Non-goals. Does not produce a single merged medication list. Does not auto-resolve ambiguous patient identity. Does not assess drug interactions.

Acceptance criteria. Every returned line carries its source, that source's response time, and its match confidence. Any source that did not respond is reported as unreachable, never as empty. Entries that could not be coded are counted and surfaced, never dropped. A single unreachable source yields an incomplete-sources outcome, never a reconciled one.

Two sentences of that are worth saying out loud in the interview: the non-goal that you deliberately do not produce one merged list, and the criterion that an unreachable source can never render as an empty one. Both are choices a reviewer can disagree with, which is exactly why they signal that you made them.

### Claude response

Mostly good, with one fix I'd make: drop "Patient" and use the singular "Medication" — not "Medications."

**Why "Medication Reconciliation," not "Patient Medications Reconciliation":**

- Every source you're citing (NCQA, The Joint Commission) uses the term of art **"medication reconciliation"** — singular, no "patient" prefix. Matching it exactly matters here specifically because part of your interview story is "the regulator already describes the architecture I built" — if your own phase name doesn't match their vocabulary, that line lands weaker.
- "Patient" is redundant in this repo. Every phase operates on a patient (Phase 1 triage, Phase 3 provider search all take a patient/identity). None of your existing phase names carry it — "Provider Search & Referral," "Epic Emulator," "Agent Platform Hardening" — so adding it here breaks the naming pattern without adding information.
- "Medications" (plural) reads as "reconciling several medications" rather than "reconciling the medication *list*" — the singular is both more standard and slightly more precise.

**One thing worth deciding, not fixing:** your repo's phase-name pattern varies between a bare capability noun (Phase 4: "Epic Emulator") and capability-plus-qualifier (Phase 3: "Provider Search & **Referral**"). The differentiator you spent the most words on — that this is a genuine two-source, cross-EHR problem, not a single-list fetch — isn't in "Medication Reconciliation" at all; that phrase is satisfied even by a one-source tool. If you want the name itself to carry that thesis (useful since it's your strongest interview line), something like:

- **"Medication Reconciliation"** — clean, matches regulatory vocabulary exactly, safe default.
- **"Cross-EHR Medication Reconciliation"** — names the actual hard part (two sources that disagree) up front.
- **"Medication Reconciliation (Transitions of Care)"** — ties it to the NCQA/Joint Commission indicator family you're grounding the whole PRD in.

My pick: plain **"Medication Reconciliation"** for the phase folder/doc titles (`docs/phase7/`), and let the PRD's opening paragraph do the work of naming it a cross-EHR, transitions-of-care problem — that's consistent with how Phase 3's PRD opens ("Phase 3 answers the question Phase 1/2 don't...") rather than cramming it into the title.

Want me to start drafting `docs/phase7/prd.md` using the capability/triggers/non-goals/acceptance-criteria rewrite you already have, plus the six-component build breakdown?

## Turn 3

### Prompt

Create the docs folder structure for Phase 7. Write the PRD draft. Dont plan milestones out yet, and dont think about merging anything yet. I want to brainstorm the scope and methods with you. Similar pattern as other phases

### Claude response

No response requested.

## Turn 4

### Prompt

Ask me questions to clarify scope, especially in terms of data sources

### Claude response

I've got your four answers locked in (epic-emulator as the Epic source, build athena-emulator for real this phase, RxNorm via a live-first abstraction layer, and a new minimal identity/encounter resolver). While I dig into the codebase to ground the remaining questions in what actually exists today (rather than guessing), let me ask a second round on the parts that are genuinely judgment calls, not fact-lookups.

Good — the codebase check confirms a few things that matter for what I write: `client/clinical`'s `FHIRClient` already takes an arbitrary base URL (so pointing it at both emulators needs no client rework), but `get_medications()` is scoped to the triage use case only — hardcoded `status=active`, and dosage collapsed to a text string rather than structured dose/route/frequency. Given the "real structured comparison" and "MedicationDispense in scope" answers, Phase 7 will need to extend `client/clinical` (not bypass it — that's the repo's existing shared-abstraction convention) rather than write parallel FHIR-fetch code. I'll note that as a stated assumption in the PRD rather than a fresh question, since the repo's own layout already dictates the answer.

I now have enough to draft. Writing `docs/phase7/prd.md`.

`docs/phase7/prd.md` is written, and `docs/phase7/` is created (no `README.md`/`design.md`/`decisions.md` yet — deliberately, since none of that is settled).

Summary of what's in it:
- **§1–2**: problem statement grounded in NCQA/Joint Commission/PMC citations, plus a table of the four scope decisions you already made (epic-emulator-only, build athena-emulator for real, RxNorm as a live-first abstraction, new identity resolver) and the follow-up ones (Outside Record modeling, MedicationDispense in scope, structured dose/route/frequency comparison, one new `med-reconciliation-service`).
- **§3–5**: goals, non-goals, and the two triggers — written to keep Trigger A/B asymmetric (B needs encounter confirmation, A doesn't), per your original rewrite.
- **§6**: 17 functional requirements, including one the codebase audit surfaced that you hadn't decided yet — `client/clinical`'s `get_medications()` is hardcoded to `status=active` and flattens dosage to text, so FR3 commits to extending it (backward-compatibly) rather than bypassing it, since that's the repo's existing shared-abstraction convention.
- **§9**: your four acceptance criteria, plus one I added explicitly requiring both patient *and* encounter confirmation on Trigger B (implied by your capability doc but not stated as a standalone bar).
- **§10**: seven open questions I did *not* resolve myself — repo module naming, where the epic-emulator Outside-Record work lands procedurally, precedence-policy schema, RxNorm term-type mechanics, real-sandbox validation, demo surface, and the third-source question.

One thing worth flagging: I made a call in FR3 without asking — extending `client/clinical` in place rather than writing separate fetch code — because CLAUDE.md already states that library is "shared by agent + triage" and the two `client/` subfolders shouldn't be bypassed. Low-risk, but say so if you'd rather isolate Phase 7's changes from `client/clinical` entirely.

Want to keep going on the §10 open questions next, or is there another data-source angle you want to press on first?

## Turn 5

### Prompt

Continue with open questions, and proceed to milestone planning if ready

### Claude response

Making the calls on the remaining open questions myself (all low-risk/reversible — naming, doc organization, technical sketches), then moving straight to milestones. I'll update the PRD, add a `decisions.md`, a `design.md` with the technical sketches milestone planning needs, and the milestone plan itself.

Now the decisions index.

Now the milestone plan.

Now updating the top-level `docs/README.md` index to register Phase 7, matching how the other phases are listed.

I missed the `telemetry-schema.md` line. Fixing the match now.

Per this repo's working agreements (CLAUDE.md), any change to `main`-branch work defaults to a feature branch + PR, done proactively. Current worktree: `/workspaces/fhir-agent`, current branch `main`, target: a new feature branch. Let me check status first before making any git changes.

There's a pre-existing unrelated modified file (`provider-search-agent/src/provider_search_agent/agent.py`) from before this session — I'll leave that untouched and stage only the docs changes.

Staged correctly — only the docs changes, unrelated file left alone. Committing now.

PR opened: **[#63](https://github.com/bhaskarcmu/fhir-agent/pull/63)** on branch `docs/phase7-medication-reconciliation-planning`. (The "1 uncommitted change" warning `gh` printed is the pre-existing, unrelated `provider-search-agent/agent.py` edit from before this session — left untouched, not part of this PR.)

**What's in it:**
- `docs/phase7/prd.md` — problem statement, resolved decisions from our two Q&A rounds, goals/non-goals, the two triggers, 17 FRs, acceptance criteria, and the now-mostly-resolved open-questions section.
- `docs/phase7/decisions.md` — R1–R14, ADR-style, same convention as the other phases.
- `docs/phase7/design.md` — repo layout, component responsibilities, the RxNorm term-type matching sketch, the precedence-policy YAML sketch, and a reconciled-line data model.
- `docs/phase7/milestone-plan.md` — M1–M8, none started: athena-emulator build → resource-surface parity (dispense + Outside-Record) → client/clinical extension → identity resolver → normalizer/matcher → recon-engine + precedence policy → provenance + gate → end-to-end acceptance case and demo.
- `docs/phase7/README.md` — canonical status doc, and `docs/README.md` updated to register Phase 7.

Calls I made without asking (all reversible, flagged in `decisions.md`):
- Service name `med-reconciliation-service/`, monolith-first shape (R8).
- `athena-emulator`'s new Outside-Record work is tracked under Phase 7, not reopened as a Phase 4 milestone (R9).
- Demo surface is a CLI/terminal script, not a new HTTP API or UI (R13).
- Precedence-policy schema keyed by *question type*, not per-field (R10).

Two things still genuinely open by design, not resolved: whether a third connected source gets added this phase (R14), and RxNorm's relationship-API behavior isn't validated — that's explicitly M5's job, not assumed correct from the design sketch.

Ready for M1 whenever you want to start building, or keep iterating on scope first — the PR stays open and I can push more commits to it as we refine.

## Turn 6

### Prompt

explain the milestone plan

### Claude response

Here's the milestone plan in plain terms — [docs/phase7/milestone-plan.md](docs/phase7/milestone-plan.md).

**The core sequencing idea:** build the two real sources first, then the plumbing to read them richly, then split into two independent tracks that don't depend on each other, then converge everything into one pipeline and prove it live.

| # | What it builds | Depends on | Why here |
|---|---|---|---|
| **M1** | `athena-emulator` — proxy, auth, quirks (deliberately different from Epic's) | nothing new | You can't reconcile two sources until the second one exists. This is the "second edge" the whole phase's thesis rests on. |
| **M2** | MedicationDispense on both emulators + Epic's `(Outside Record)` endpoint variants | M1 | Both new resource types are needed by later milestones (M5's matching, M6's precedence policy) — added once, to both emulators, so they don't drift apart. |
| **M3** | `client/clinical` extended — broader status filter, structured dose/route/frequency, dispense fetch | M2 | The existing `get_medications()` is scoped to triage's needs only (active-only, flattened text). This is the one milestone touching code outside Phase 7's new service, kept small and backward-compatible on purpose — `triage-service` must not notice. |
| **M4** | Identity + encounter resolver (both triggers) | M3 | Needs the search capability M3 provides. Produces a confirmed `(patient_id, encounter_id)` — the input everything downstream needs. |
| **M5** | Normalizer + five-tier match classifier (RxNorm + structured dose/route/frequency) | M2 | **The riskiest milestone** — "the honest hard part." Doesn't need M3/M4 (identity), so it can run in parallel with M4 against hand-picked test patients. |
| **M6** | recon-engine (4 discrepancy types) + precedence-policy YAML | M5 | Takes M5's match results and turns them into labeled, policy-annotated lines. Doesn't strictly need M4 either — can be tested with fixed IDs. |
| **M7** | Provenance + the fail-closed gate (`RECONCILED`/`DISCREPANCIES_FOUND`/`INCOMPLETE_SOURCES`) | M6 | Where the acceptance-critical behavior lives: a dead source must render as "unreachable," never "empty," and must force `INCOMPLETE_SOURCES` no matter what else is true. |
| **M8** | Wire both triggers through M1–M7, live acceptance test, CLI demo | M4, M7 | Everything converges. Includes the actual "kill athena-emulator mid-demo" moment from the brainstorm doc, verified working — not just described. |

**The one thing worth noticing:** M4 (identity resolver) and M5 (normalizer/matcher) are the two tracks that don't depend on each other — they both only need M2/M3's data surface, not each other's output. So in practice they could be built in either order, or by two people at once; M6/M7/M8 are the ones that force sequencing.

**Highest risk item:** M5. Everything else here is either a known pattern (M1/M2 mirror Phase 4's already-proven emulator shape) or mechanical plumbing (M3, M4, M7). M5 is the one where the design doc's sketch is explicitly marked "unvalidated" — RxNav's relationship API might not actually support walking cleanly from a clinical-drug term type back to its ingredient, and that's only found out by building it.

**Deliberately not a milestone:** a real Epic/Athena sandbox check, a third connected source, prod/cloud deployment, and the nursing-facility extension — all named in the plan's closing section so nobody mistakes their absence for an oversight.

## Turn 7

### Prompt

Explain the clinical user's experience when this phase is done. Should w4e introduce anything agentic here?

### Claude response

Worth being honest here: as currently scoped (M1–M8), there isn't really a "clinical user experience" yet — it's a pipeline proven to work via a CLI demo, not a clinician-facing product. Let me walk through both triggers as scoped today, and where the real gaps are.

## Trigger A (event) — today's scope

A test harness (or, eventually, a real ADT feed) hands the pipeline a patient ID + encounter ID directly, and it runs straight through to a reconciled result. **There is no actual notification listener built in this plan** — M4 says "pass through notification's patient+encounter," but nothing ingests a real HL7v2 ADT message or FHIR `Encounter` subscription. A clinician experiences nothing here yet; this trigger exists in code as an entry point, not as a live integration.

## Trigger B (on demand) — today's scope

A clinician's actual experience, as scoped, is: someone runs `cli.py` with demographics as arguments, gets a printed list of candidate patients in a terminal, and... M4 says confirmation is "required," but no interactive confirmation UI is designed — M8's demo is explicitly a **scripted** run against one seeded patient, not a live back-and-forth. So today, "confirm the patient, then confirm the encounter" is a data contract the pipeline enforces, not a screen a clinician clicks through.

## The output itself

`ReconciledLine[]` — a data structure, rendered by M8 as a terminal three-panel view for demo purposes. Real fields (source, response time, discrepancy type, unresolved count, `INCOMPLETE_SOURCES` banner) are all there, but "legible to a clinician under time pressure" is a UI design problem this phase doesn't touch, same way Phase 6 built only a thin HTTP API and stopped short of any UI.

So: Phase 7 as scoped proves the *engine* works. A real clinician-facing product needs, on top of it: a real ADT/notification listener (Trigger A), an interactive confirmation UI or conversational front-end (Trigger B), and a legible results screen. None of that is in M1–M8 — worth deciding now whether that's Phase 7b, or explicitly out of scope entirely.

## Should anything be agentic here?

One place fits cleanly: **Trigger B's intake**, as a conversational front-end over M4's deterministic resolver — a clinician says "reconcile meds for the patient in bed 4," the agent extracts demographics and calls the resolver as a tool, presents candidates, and asks for confirmation. This is the exact shape `mcp-agent`/`claims-agent` already use elsewhere in this repo (agent orchestrates and explains, deterministic service decides), so it's low-risk and consistent with how the codebase already draws that line. The tradeoff: it adds a whole new agent surface to a phase that's already eight milestones deep, for a UX improvement rather than a new capability — worth sequencing after M1–M8 ship, not folded into them.

The one place I'd actively avoid an agent: identity matching, RxNorm classification, discrepancy typing, and the fail-closed gate. Those need to stay deterministic — that's both this repo's standing doctrine and literally a stated non-goal in the Phase 7 PRD ("does not auto-resolve ambiguous patient identity").

Want me to sketch what a Phase 7b (or a Phase 7 M9) covering the notification listener, confirmation UI, and the conversational agent would look like — or hold off until M1–M8 actually ship?

## Turn 8

### Prompt

Can these be explicitly done by a human using an agentic (I mean chatbot) interface:

 identity matching, RxNorm classification, discrepancy typing, and the fail-closed gate.

### Claude response

*[Claude has not completed this turn yet.]*

<details>
<summary>Execution details — 31 tool events</summary>

### Turn 1 activity

- **Bash** `echo "=== grep for Phase N mentions in tracked files ===" && grep -rniE "phase[ _-]?[0-9]" --include="*.md" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.json" . 2>/dev/null | gre…`
- **Bash** `echo "=== git log phase mentions ===" && git log --all --oneline | grep -niE "phase[0-9]|phase[ _-]?[0-9]" | sort -u`
- **Bash** `echo "=== branches ===" && git branch -a | grep -niE "phase" ; echo "=== PR list titles mentioning phase (if gh available) ===" && gh pr list --state all --limit 200 --json number,title,headRefName 2>…`
- **Bash** `echo "=== docs/ top-level phase dirs ===" && ls -d docs/phase* 2>/dev/null
echo "=== README phase4/phase5 status blurbs ===" && grep -n -i "phase 4\|phase 5\|phase4\|phase5" README.md | head -60`
- **Bash** `grep -n -i "phase" README.md | grep -iE "phase[ _]?4|phase[ _]?5|phase[ _]?7"
echo "---"
ls docs/phase4 docs/phase5 docs/phase6
echo "--- phase5 README ---"
cat docs/phase5/README.md 2>/dev/null | hea…`
- **Bash** `grep -rniE "phase[ _]?7" . --include="*.md" --include="*.py" --include="*.yaml" --include="*.yml" 2>/dev/null | grep -v ".git/"
echo "--- any athena mentions ---"
grep -rniE "athena" . --include="*.md…`

### Turn 2 activity

- **Bash** `for f in docs/phase2/prd.md docs/phase3/prd.md docs/phase4/prd.md docs/phase6/prd.md; do echo "=== $f ==="; head -5 "$f" 2>/dev/null; echo; done`

### Turn 3 activity

- **Bash** `echo "=== phase4 prd.md (full) ===" 
cat docs/phase4/prd.md
echo
echo "=== phase4 README.md ===" 
cat docs/phase4/README.md`
- **Bash** `echo "=== phase6 prd.md (full) ===" 
cat docs/phase6/prd.md`
- **Bash** `echo "=== docs/README.md ===" 
cat docs/README.md`
- **Bash** `mkdir -p docs/phase7 && ls docs/`

### Turn 4 activity

- **AskUserQuestion** `{"questions": [{"question": "For the hospital-side (Epic) medication source, what should Phase 7 actually call?", "header": "Epic source", "multiSelect": false, "options": [{"label": "epic-emulator on…`
- **Agent** `Survey existing modules relevant to Phase 7 scope`
- **AskUserQuestion** `{"questions": [{"question": "The brainstorm doc calls out Epic's separate \"Outside Record\" medication endpoints (Medication/MedicationRequest/MedicationDispense variants for data that originated out…`
- **Write** `/workspaces/fhir-agent/docs/phase7/prd.md`

### Turn 5 activity

- **Edit** `/workspaces/fhir-agent/docs/phase7/prd.md`
- **Edit** `/workspaces/fhir-agent/docs/phase7/prd.md`
- **Write** `/workspaces/fhir-agent/docs/phase7/decisions.md`
- **Write** `/workspaces/fhir-agent/docs/phase7/design.md`
- **Write** `/workspaces/fhir-agent/docs/phase7/milestone-plan.md`
- **Write** `/workspaces/fhir-agent/docs/phase7/README.md`
- **Edit** `/workspaces/fhir-agent/docs/README.md`
- **Edit** `/workspaces/fhir-agent/docs/README.md`
- **Read** `/workspaces/fhir-agent/docs/README.md`
- **Edit** `/workspaces/fhir-agent/docs/README.md`
- **Bash** `git status`
- **Bash** `git checkout -b docs/phase7-medication-reconciliation-planning`
- **Bash** `git add docs/README.md docs/phase7/ && git status`
- **Bash** `git commit -m "$(cat <<'EOF'
docs(phase7): Medication Reconciliation — PRD, design, decisions, milestone plan

Planning pass for a new Phase 7: given a confirmed patient identity and
discharge encount…`
- **Bash** `git push -u origin docs/phase7-medication-reconciliation-planning`
- **Bash** `gh pr create --title "docs(phase7): Medication Reconciliation — PRD, design, decisions, milestone plan" --body "$(cat <<'EOF'
## Summary
- New Phase 7: given a confirmed patient identity and discharge…`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `b4b04851-828e-40dd-9240-5f17ee29eb7d`
- **Created:** 2 September 2026, 02:43 UTC
- **Last updated:** 2 September 2026, 03:20 UTC
- **Turns:** 8
- **Status:** Incomplete
