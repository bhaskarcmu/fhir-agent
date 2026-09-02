# Phase 7 Design — Medication Reconciliation

Architecture, component breakdown, and the technical sketches `milestone-plan.md` builds against.
Status and requirements live in [`README.md`](./README.md) and [`prd.md`](./prd.md).

## 1. Repo layout

```
med-reconciliation-service/     # deterministic core (R8) — no conversational logic
  src/med_reconciliation/
    identity.py                 # patient/encounter resolution (candidates + confirmation)
    normalizer.py                # RxNorm concept resolution + term-type detection (R3, R11)
    match.py                     # five-tier classification, structured dose/route/frequency compare (R7)
    recon.py                     # four discrepancy types (omission/addition/change/unclear)
    precedence.py                # loads precedence-policy.yaml, exposes reference labels only (R10)
    provenance.py                # per-field source/timestamp/age
    gate.py                      # RECONCILED / DISCREPANCIES_FOUND / INCOMPLETE_SOURCES — no external writer but this module
    composition.py               # builds + persists the Medication Reconciliation Record (R19)
    audit.py                     # append-only ledger: overrides + manual-verification entries (R17, R21)
    tools.py                     # the tool surface med-reconciliation-agent is allowed to call — see §3
  precedence-policy.yaml         # G6 — clinical reasoning, reviewable without reading code
  cli.py                         # structured-path demo surface (R13)

med-reconciliation-agent/       # NEW — conversational layer (R22), own top-level package
  src/med_reconciliation_agent/
    agent.py                     # tool-use loop, built on agent-platform (R23)
    explain.py                   # grounded narration of a reconciled view (G12)
    turn_gate.py                 # agent-turn safety enum — distinct from, no access to, gate.py above

athena-emulator/                 # built out this phase (R2)
epic-emulator/                   # extended this phase (R5, R9) — Outside Record endpoint variants
client/clinical/                 # extended, backward-compatible (FR3)
```

`med-reconciliation-agent` depends on `med-reconciliation-service`'s `tools.py` (via HTTP, or
in-process if colocated — an implementation detail for the design pass at build time, not decided
here) and on `agent-platform` (Phase 6) for session/memory, observability, and the
multi-provider seam. It does **not** depend on `client/clinical` directly, `triage-service`, or
`claims-service` — same "agent has no clinical logic of its own" boundary this repo already
holds.

## 2. Component responsibilities

Unchanged from the first design pass: `identity.py`, `normalizer.py`, `match.py`, `recon.py`,
`precedence.py`, `provenance.py`, `gate.py` — see prior revision (preserved in git history) for
full detail; sketches in §5–§7 below still apply. Two components are new:

| Component | Responsibility | Consumes | Produces |
|---|---|---|---|
| `composition.py` | Build and persist the Medication Reconciliation Record at the end of every run | `ReconciledLine[]`, per-source attempt telemetry, `gate.py`'s outcome | A FHIR `Composition`, written to `fhir-service` |
| `audit.py` | Append-only storage for classification/discrepancy overrides and manual-verification entries | Override/verification submissions (human-attributed) | New `Provenance`-shaped entries linked to an existing Composition — never a mutation of it |

## 3. The agent's tool contract — and what's deliberately not in it

`tools.py` (in `med-reconciliation-service`) defines exactly what `med-reconciliation-agent` can
call:

| Tool | What it does | What it cannot do |
|---|---|---|
| `search_patients(demographics)` | Runs `identity.py`'s candidate search | Cannot auto-select a candidate |
| `search_encounters(patient_id)` | Runs `identity.py`'s encounter search | Cannot auto-select a candidate |
| `confirm_patient(candidate_id)` | Relays an explicit human confirmation | Only callable with a human-originated selection already in the conversation |
| `confirm_encounter(candidate_id)` | Same, for encounter | Same constraint |
| `get_reconciled_view(patient_id, encounter_id)` | Returns `ReconciledLine[]` + gate outcome + Composition reference | Read-only |
| `submit_classification_override(line_id, new_classification, reason, practitioner_id)` | Calls `audit.py` to append an override | Cannot delete or replace the original computed value (`audit.py` enforces append-only at the storage layer, not just by convention) |
| `submit_manual_verification(composition_id, source, method, outcome, practitioner_id)` | Calls `audit.py` to append a `Provenance` entry | Same append-only constraint |

**There is no `set_outcome` / `override_gate` / `mark_reconciled` tool, and none is planned.**
This is the load-bearing design decision from this pass (`prd.md` G14, FR21): the gate's
unreachability from the agent is enforced by the tool surface simply not including a way to do
it, not by a permission check the agent could be prompted around. A future contributor adding
agent capabilities should read this table as the actual contract, not a suggestion — extending it
to touch `gate.py`'s output is a decision that needs its own review, not a routine addition.

`explain.py` calls `get_reconciled_view` and produces plain-language narration; its system prompt
constrains it to only state facts present in the returned data, the same grounding discipline
Phase 6 M6 uses for knowledge-base citations ("retrieval fires only after a deterministic decision
already exists... never before, as an input the agent reasons over").

`turn_gate.py` is a **separate** enum from `gate.py`'s `ReconciliationOutcome` — it governs
whether a given agent turn is safe to show the user at all (e.g., did the model stay grounded, did
it attempt something outside the tool contract), mirroring `agent-platform/output_gate.py`'s
pattern. It has no read or write access to the clinical gate. Two different gates, two different
questions — worth stating explicitly because conflating them was the exact failure mode this
design avoids.

## 4. The Medication Reconciliation Record (R19)

A FHIR `Composition`, generated by `composition.py` at the end of every run — `RECONCILED`,
`DISCREPANCIES_FOUND`, and `INCOMPLETE_SOURCES` alike, not only the incomplete case:

```
Composition
  subject: Patient reference
  encounter: Encounter reference
  date: run timestamp
  section[attempt-log]:
    - source: "epic_discharge_orders"
      queried_at, response_time_ms, status: succeeded | failed | timed_out
      narrative: templated from the above fields (R20) — e.g.
        "Queried epic_discharge_orders at 14:02:03. Responded in 340ms."
        "Queried athena_outpatient_list at 14:02:03. No response after 3 retries over 90s
         (connection timeout). No further automated retrieval attempted."
  section[reconciled-lines]: reference to ReconciledLine[] (§5 of the prior design revision)
  section[outcome]: gate.py's ReconciliationOutcome — RECONCILED | DISCREPANCIES_FOUND | INCOMPLETE_SOURCES
  section[unresolved-count]: integer
```

The attempt-log narrative is the artifact that satisfies the Joint Commission's "a good faith
effort... will be considered as meeting the intent" language — it is what makes an
`INCOMPLETE_SOURCES` outcome a *documented*, compliant state rather than an undocumented failure.
It is built entirely from a fixed template and real telemetry values (R20) — never model-generated
text — specifically because a document whose purpose is proving an effort was made cannot itself
contain an unverified claim.

Once created, a Composition is immutable. Later human action doesn't edit it — it adds to it (§5).

## 5. The audit ledger (R17, R21)

`audit.py` implements one generic append-only mechanism, reused for both use cases the PRD names:

```
AuditEntry
  target_composition: reference
  entry_type: "classification_override" | "manual_verification"
  submitted_by: Practitioner reference   # never optional — every entry is attributed
  submitted_at: timestamp
  # classification_override fields:
  target_line_id, original_value, new_value, reason
  # manual_verification fields:
  source, method, outcome
```

Each `AuditEntry` is written as (or alongside) a FHIR `Provenance` resource targeting the original
Composition, following `claims-service`'s `Provenance`-emission as a pattern precedent — not
shared code. Reading a record's full history means reading the Composition **plus** every
`AuditEntry` targeting it, in submission order; nothing is ever deleted or updated in place. This
is what makes FR25 ("every override and manual-verification entry is independently queryable...
nothing is hidden by a later action") a storage-layer guarantee, not a display-layer convention
that a future UI could quietly violate.

## 6. RxNorm term-type matching, precedence policy, reconciled-line data model, fail-closed gate

Unchanged from the first design pass — sketches (RxNav TTY/relationship walk for term-type
detection, the `precedence-policy.yaml` schema keyed by question type, the `ReconciledLine`/
`FieldProvenance` dataclasses, and `gate.py`'s three-outcome enum) all still apply as originally
written; preserved in git history rather than repeated here to keep this revision focused on
what's new.

## 7. Demo surface (R13, expanded)

`cli.py` (structured path, unchanged) and `med-reconciliation-agent`'s own CLI (conversational
path, mirroring `mcp-agent`'s interactive mode) both drive the same underlying pipeline. The
milestone-plan's M12 acceptance demo now has three beats instead of one: (1) the original
three-panel reconciled view, including a source going down mid-demo and the view degrading to
`INCOMPLETE_SOURCES`; (2) a conversational Trigger-B request resolving an ambiguous patient
candidate with explicit human confirmation; (3) a classification override submitted through the
agent, followed by pulling up the record and showing both the original computed value and the
override, side by side, neither hidden by the other.
