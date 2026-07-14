# Payer Knowledge Base (Phase 2, M1)

Curated, **real-grounded** reference data the adjudication rules engine consumes. Small by
design (per requirements R13 — curated fixtures, not full loads); grounded in real public
sources (per R13.1); structured for the C3 **repository seam** so a Postgres→NoSQL swap is a
no-op.

## Layout
```
payer-kb/
  plans/                 # one YAML per plan — payer type, tiers, cost-share, example coverage
    commercial-silver.yaml
    commercial-gold.yaml
    medicare-advantage-demo.yaml
    employer-ppo.yaml
  formulary/
    formulary.csv        # (plan_id, rxcui) → tier + PA/step-therapy/quantity-limit + covered
  pa-rules/
    pa-rules.yaml        # layered (federal/plan/customer) utilization rules → R17 severities
  crosswalk/
    ndc_rxcui.csv        # NDC ↔ RxCUI (claims key on NDC; clinical rules key on RxCUI)
```

## Schemas

**`formulary/formulary.csv`** — the high-cardinality lookup (`plan_id + rxcui → rule`), the
KV access pattern behind the C3 repository interface:

| column | meaning |
|---|---|
| `plan_id` | references `plans/*.yaml` `plan_id` |
| `rxcui` | RxNorm ingredient id (join to `crosswalk` for NDC) |
| `drug` | human label (convenience) |
| `tier` | normalized tier (see below) |
| `prior_auth` | bool — PA required |
| `step_therapy` | bool — must try/fail a first-line agent |
| `quantity_limit` | bool — a QL applies |
| `quantity_limit_qty` | the limit (e.g., `30/30d`); empty if none |
| `covered` | bool — on formulary (false = non-formulary) |

**Normalized tiers** (mapped from CMS Part D + ACA QHP tier vocabularies):
`PREFERRED-GENERIC`, `GENERIC`, `PREFERRED-BRAND`, `NON-PREFERRED-BRAND`, `SPECIALTY`,
`NON-FORMULARY`.

**`plans/*.yaml`** — plan config: `payer_type` (commercial|medicare|employer), tier
cost-sharing, deductible/MOOP, and an `example_coverage` block (active vs. inactive periods)
used to drive the eligibility demo scenarios.

**`pa-rules/pa-rules.yaml`** — deterministic utilization rules, **layered** (federal → plan →
customer, per §9.5). Each rule's `effect` maps to a Decision-Contract severity (R17):
`DENY` / `PEND` / `REVIEW`.

## Grounding (real, not fabricated — R13.1)
- **Tiers + PA/step-therapy/quantity flags:** structure from the **CMS Part D Formulary PUF**
  (Medicare) and **ACA QHP machine-readable formularies** (commercial) — see
  `data/reference/README.md` and `data/reference/aca-commercial/`.
- **Drugs (RxCUI) + classes:** RxNav (`data/reference/rxnorm/rxnorm_drug_classes.csv`).
- **NDC ↔ RxCUI:** openFDA (`crosswalk/ndc_rxcui.csv`, built by
  `data/scripts/build_ndc_rxcui_crosswalk.py`).
- Values (specific tiers/flags per plan) are **curated** to be representative and to drive the
  demo scenarios; the *mechanics* mirror real payer data. Proprietary PA criteria/pricing are
  out of scope.

## Demo scenarios this KB drives (R8)
1. **Approved** — `lisinopril` on `COM-SILVER` (PREFERRED-GENERIC, no flags).
2. **Rejected (inactive coverage)** — plan `example_coverage.inactive` + a claim dated outside
   the window (eligibility, not formulary).
3. **Pended → PA** — `semaglutide` on `COM-SILVER` (SPECIALTY, `prior_auth=true`).
4. **Safety alert** — `amoxicillin` (covered) + a penicillin-allergic member → clinical safety
   (reused triage) fires; formulary just covers the drug.
5. **Multi-reason denial** — `semaglutide` on `EMP-PPO` (`NON-FORMULARY` **and**
   `quantity_limit`) → aggregates two reasons (matches PRD §9.4).

## Reproduce the grounding inputs
```bash
python3 data/scripts/fetch_reference_data.py            # RxNorm + ICD-10
python3 data/scripts/fetch_aca_formulary_sample.py      # ACA QHP commercial sample
python3 data/scripts/build_ndc_rxcui_crosswalk.py       # NDC ↔ RxCUI (openFDA)
```
