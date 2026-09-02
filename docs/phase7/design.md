# Phase 7 Design — Medication Reconciliation

Architecture, component breakdown, and the two technical sketches (precedence policy, RxNorm
term-type matching) that `milestone-plan.md` builds against. Status and requirements live in
[`README.md`](./README.md) and [`prd.md`](./prd.md) — not restated here.

## 1. Repo layout

```
med-reconciliation-service/     # new — deterministic core service (R8)
  src/med_reconciliation/
    identity.py                 # patient/encounter resolution (candidates + confirmation)
    normalizer.py                # RxNorm concept resolution + term-type detection (R3, R11)
    match.py                     # five-tier classification, structured dose/route/frequency compare (R7)
    recon.py                     # four discrepancy types (omission/addition/change/unclear)
    precedence.py                # loads precedence-policy.yaml, exposes reference labels only (R10)
    provenance.py                # per-field source/timestamp/age
    gate.py                      # RECONCILED / DISCREPANCIES_FOUND / INCOMPLETE_SOURCES
  precedence-policy.yaml         # G6 — clinical reasoning, reviewable without reading code
  cli.py                         # demo surface (R13)

athena-emulator/                 # built out this phase (R2) — mirrors epic-emulator's shape
  (Java/Spring Boot, own auth flavor + quirks, deliberately different from epic-emulator's)

epic-emulator/                   # extended this phase (R5, R9) — Outside Record endpoint variants

client/clinical/                 # extended, backward-compatible (FR3)
  fhir_client.py                 # broader status filter, structured dosage fields, dispense fetch
```

`med-reconciliation-service` calls both emulators through two `FHIRClient` instances
(`client/clinical`'s existing arbitrary-base-URL support — no new HTTP client written). It does
not import `triage-service` or `claims-service`, and neither of those is modified except where
`client/clinical` additions are backward-compatible by construction (FR3).

## 2. Component responsibilities

| Component | Responsibility | Consumes | Produces |
|---|---|---|---|
| `identity.py` | Trigger A: pass through notification's patient+encounter. Trigger B: demographic search → scored candidates → human confirmation (patient, then encounter). | `client/clinical` Patient/Encounter search against both sources | Confirmed `(patient_id, encounter_id)` per source, or a rejected/pending state — never a silent best guess |
| `normalizer.py` | Resolve each MedicationRequest/MedicationDispense entry to an RxNorm concept + term type | Raw entries from `client/clinical` | `(rxcui, term_type, source_entry)` or `unresolved` |
| `match.py` | Pair entries across sources at the same/related RxNorm concept; classify into 5 tiers using structured dose/route/frequency | Normalized entries from both sources | `MatchResult` per pairing |
| `recon.py` | Turn match results into the 4 Joint-Commission discrepancy types, one line per medication concept | `MatchResult`s + unpaired entries (→ omissions) | `ReconciledLine[]` |
| `precedence.py` | Load `precedence-policy.yaml`; attach a reference label per line (which source *generally* wins this question, and why) — never mutates or drops a source's contribution | `ReconciledLine[]`, policy file | Same lines, annotated |
| `provenance.py` | Attach source system, response time, and record age to every field | Per-source fetch metadata (timing, timestamps) | Field-level provenance envelope |
| `gate.py` | Roll up source reachability + discrepancy presence into one outcome enum | Per-source reachability flags, `ReconciledLine[]` | `RECONCILED \| DISCREPANCIES_FOUND \| INCOMPLETE_SOURCES` |

## 3. RxNorm term-type matching (R11 — sketch, unvalidated until M5)

RxNav's `findRxcuiByString` (with `search=2`, approximate matching) resolves free text /
structured `Medication.code` display text to a candidate RxCUI. Each RxCUI carries a **TTY**
(term type) attribute — e.g. `IN` (ingredient), `SCD`/`SCDC` (semantic clinical drug — the
dose+route+form level), `SBD` (branded). The plan:

1. Resolve each entry to its best-matching RxCUI, recording the TTY reached.
2. If the TTY is already `SCD`/`SBD` (clinical/branded drug — dose and form baked in), use RxNav's
   relatedness API (`getRelatedByType` / ingredient relationship) to also derive the ingredient
   RxCUI, so two entries at different TTYs (e.g. one source codes to `SCD`, the other only reaches
   `IN`) can still be recognized as *related*, and classified as "ingredient-level-only" rather
   than "unresolved."
3. Pair entries whose ingredient RxCUI matches. Within a matched pair, compare:
   - **Same clinical-drug RxCUI** → `identical`.
   - **Same ingredient, same dose/route, different formulation with no clinical difference**
     (e.g. brand vs. generic of the same clinical drug) → `equivalent`.
   - **Same ingredient, different salt/release-profile/dose** (the metoprolol tartrate vs.
     succinate case from the brainstorm doc) → `same-ingredient-different-product`.
   - **Matched only at the ingredient TTY**, dose/route not comparable → `ingredient-level-only`.
   - **No RxCUI resolved at all** → `unresolved`.
4. Dose/route/frequency for the comparison above comes from FR3's structured
   `dosageInstruction` fields (`client/clinical`'s extension) — not from re-parsing display text.

This is a design sketch, not a verified integration. M5 is where RxNav's actual behavior (rate
limits, approximate-match quality, relationship-API coverage) gets confirmed against real data,
the way Phase 4's M2 had to downgrade an assumed live-Epic-docs check to a documented,
honestly-flagged placeholder when reality didn't cooperate. If RxNav's relationship API turns out
to be insufficient for step 2, the fallback is documented in `decisions.md` when that's known —
not guessed here.

## 4. Precedence policy (R10 — sketch)

`precedence-policy.yaml`, loaded by `precedence.py`, keyed by **question type**, not by
individual FHIR field — matching how the brainstorm doc frames it and how a clinical reviewer
would actually think about it:

```yaml
# precedence-policy.yaml — read by clinicians and engineers alike.
# This is reference/labeling only. It never causes a source's value to be dropped or overwritten
# (prd.md G6, non-goals) — see gate.py / recon.py, which always preserve every source's line.

question_types:
  what_was_prescribed:
    precedence: [epic_discharge_orders, athena_outpatient_list]
    reason: >
      Discharge orders are the newest, most specific record of intended therapy at the
      transition point.

  what_patient_is_actually_taking:
    precedence: [athena_outpatient_list, epic_discharge_orders]
    reason: >
      The outpatient clinic has longitudinal knowledge of the patient (e.g. drugs the patient
      self-discontinued) that a single discharge encounter cannot capture.

  was_drug_ever_obtained:
    precedence: [epic_medication_dispense, athena_medication_dispense]
    reason: >
      Fill/dispense data is the only signal describing what actually happened at the pharmacy;
      order data from either EHR only describes intent.
```

Each `ReconciledLine` gets an advisory label ("per policy, `athena_outpatient_list` is generally
more trustworthy for 'is the patient actually taking this'") attached alongside — not instead
of — both sources' raw values. A reviewer reads the YAML to audit the clinical reasoning without
reading the service's code, same intent as the brainstorm doc's original framing.

## 5. Reconciled-line data model (sketch)

```python
@dataclass
class FieldProvenance:
    source: str            # e.g. "epic_discharge_orders"
    response_time_ms: int
    record_age: timedelta
    queried_at: datetime

@dataclass
class ReconciledLine:
    rxcui: str | None                  # None only if unresolved
    term_type: str | None
    discrepancy_type: Literal["omission", "addition_duplication", "change", "unclear"]
    match_tier: Literal["identical", "equivalent", "same_ingredient_different_product",
                         "ingredient_level_only", "unresolved"]
    contributions: dict[str, FieldProvenance]   # source name -> provenance, one entry per source that had this line
    precedence_label: str | None                # advisory only (§4)
```

An `unresolved` line still appears with whatever raw source data exists — it is never dropped
(`prd.md` FR9, acceptance criteria).

## 6. Fail-closed gate (mirrors `agent-platform/output_gate.py` / `fail_closed.py`)

```python
class ReconciliationOutcome(str, Enum):
    RECONCILED = "reconciled"                  # all sources reachable, no discrepancies
    DISCREPANCIES_FOUND = "discrepancies_found" # all sources reachable, >=1 discrepancy
    INCOMPLETE_SOURCES = "incomplete_sources"   # >=1 source unreachable — always wins, regardless of discrepancy count
```

`gate.py` is new code in `med-reconciliation-service`, not an import of `agent-platform` (that
package is the agent tier; this is a deterministic core service, same tier as `triage-service`) —
it deliberately re-implements the same enum-gate *pattern*, the way `claims-service`'s
`HttpTriageClient.java` independently re-implemented the fail-closed idea in Java rather than
sharing code across a language boundary.

## 7. Demo surface (R13)

`cli.py` — a script in the same spirit as `e2e/test_epic_emulator_acceptance.py`: runs the full
pipeline for one seeded patient against both live emulators, prints a three-panel terminal view
(hospital list | outpatient list | reconciled view, discrepancy-labeled), and — as its scripted
second act — stops `athena-emulator` mid-run and re-runs to show the view degrade to
`INCOMPLETE_SOURCES` instead of quietly rendering a one-sided list. This is `milestone-plan.md`
M8's deliverable.
