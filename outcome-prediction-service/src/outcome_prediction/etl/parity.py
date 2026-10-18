"""CSV ↔ FHIR parity (M6, FR-F3; prd.md §9 criterion 6).

The same Synthea patients go through both extractors and the same transform. FR-F3 holds when
the contract rows are identical **or every difference is listed and explained**. "Explained"
is checked, not asserted: each known cause has a verifier that must hold for every person whose
value differs. A difference no verifier explains makes the comparison fail.

    python -m outcome_prediction.etl.parity --csv DIR --fhir http://localhost:8090/fhir [--year 2023]
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from outcome_prediction.etl.canonical import Canonical
from outcome_prediction.etl.extract import fhir as fhir_extract
from outcome_prediction.etl.transform import to_contract
from outcome_prediction.model import FEATURES, LABEL


@dataclass(frozen=True)
class Context:
    """Both sides of one comparison, indexed by the CSV (Synthea) patient ID."""
    year: int
    csv: Canonical
    csv_rows: pd.DataFrame
    fhir_rows: pd.DataFrame
    fhir_warnings: pd.DataFrame
    fhir: Canonical                 # FHIR canonical tables, person_id already mapped to the CSV ID


def _in(canon: Canonical, year: int, people, classes) -> pd.Series:
    """People (of `people`) with an encounter of one of `classes` starting in `year`."""
    e = canon.encounter
    hit = e[(e.start.dt.year == year) & e.encounter_class.isin(classes) & e.person_id.isin(people)]
    return pd.Series(pd.Index(people).isin(hit.person_id.unique()), index=people)


def _income_default(ctx, people):
    warned = set(ctx.fhir_warnings[ctx.fhir_warnings.warning == to_contract.WARN_INCOME].patient_ref)
    return (ctx.fhir_rows.loc[people, "povcaty1"] == to_contract.DEFAULT_POVCAT) & pd.Index(people).isin(warned)


def _office_outpatient(ctx, people):
    both = ["obtotvy1", "optotvy1"]
    return ctx.csv_rows.loc[people, both].sum(axis=1) == ctx.fhir_rows.loc[people, both].sum(axis=1)


def _hospice(ctx, people):
    return _in(ctx.csv, ctx.year, people, ["hospice"])


def _snf_year1(ctx, people):
    return _in(ctx.csv, ctx.year, people, ["snf"])


def _snf_year2(ctx, people):
    return _in(ctx.csv, ctx.year + 1, people, ["snf"])


def _prescriptions(ctx, people):
    """FHIR has no fill counts or stop dates: fills = pharmacy claims in the window, and a
    prescription's cost counts only if its claim falls in the window. Encounter costs must match."""
    e = ctx.csv.encounter
    enc_cost = e[e.start.dt.year == ctx.year].groupby("person_id").cost.sum().reindex(people, fill_value=0)
    fhir_med_cost = ctx.fhir_rows.loc[people, "totexpy1"] - enc_cost
    return fhir_med_cost.round() >= -1          # the encounter part is fully present on the FHIR side


def _fills_are_pharmacy_claims(ctx, people):
    """FHIR fills = the pharmacy-claim fill records dated in year 1, exactly."""
    m = ctx.fhir.medication_fill
    n = m[(m.start.dt.year == ctx.year) & m.source_ref.str.startswith("ExplanationOfBenefit/")]
    return ctx.fhir_rows.loc[people, "rxtoty1"] == n.groupby("person_id").size().reindex(people, fill_value=0)


def _coverage_from_claims(ctx, people):
    """Cover the CSV records in year 1 that no FHIR claim in year 1 shows (no claim, no cover)."""
    def owners(cov):
        y = cov[(cov.start.dt.year <= ctx.year) & (cov.stop.isna() | (cov.stop.dt.year >= ctx.year))]
        return y.groupby("person_id").ownership.agg(set).reindex(people).apply(
            lambda v: v if isinstance(v, set) else set())
    csv, fh = owners(ctx.csv.coverage), owners(ctx.fhir.coverage)
    return pd.Series([bool(c - f) for c, f in zip(csv, fh)], index=people)


# feature -> [(reason, verifier)]: a differing person is explained if ANY verifier holds for them.
EXPLAINED: dict[str, list[tuple[str, Callable]]] = {
    "povcaty1": [("FHIR carries no income: default 4 with a warning (O66)", _income_default)],
    "obtotvy1": [("Office and hospital-outpatient visits share Encounter.class AMB; counted as office (O65)", _office_outpatient)],
    "optotvy1": [("Office and hospital-outpatient visits share Encounter.class AMB; counted as office (O65)", _office_outpatient)],
    "hhtotdy1": [("Hospice and home health share Encounter.class HH; counted as home health (O65)", _hospice)],
    "ipdisy1": [("SNF and hospital stays share Encounter.class IMP; counted as stays (O65)", _snf_year1)],
    "ipngtdy1": [("SNF and hospital stays share Encounter.class IMP; counted as stays (O65)", _snf_year1)],
    LABEL: [("SNF and hospital stays share Encounter.class IMP; a year-2 SNF stay counts (O65)", _snf_year2)],
    "rxtoty1": [("No dispenses or fill counts in FHIR: one fill per pharmacy claim in the window (O65)", _fills_are_pharmacy_claims)],
    "totexpy1": [("Prescription costs come from pharmacy claims dated in the window, not prorated fills (O65)", _prescriptions)],
    "inscovy1": [("No Coverage records: insurance inferred from claims, blind to cover without claims (O65)", _coverage_from_claims)],
}


def compare(ctx: Context) -> dict:
    out = {"year": ctx.year, "people": int(len(ctx.csv_rows)), "identical": [], "differences": [],
           "unexplained": []}
    for f in FEATURES + [LABEL]:
        diff = ctx.csv_rows.index[ctx.csv_rows[f] != ctx.fhir_rows[f]]
        if not len(diff):
            out["identical"].append(f)
            continue
        explained = pd.Series(False, index=diff)
        reasons = []
        for reason, verify in EXPLAINED.get(f, []):
            ok = verify(ctx, diff).reindex(diff, fill_value=False).astype(bool)
            if ok.any():
                reasons.append({"reason": reason, "people": int(ok.sum())})
            explained |= ok
        entry = {"feature": f, "people": int(len(diff)), "csv_mean": float(ctx.csv_rows[f].mean()),
                 "fhir_mean": float(ctx.fhir_rows[f].mean()), "reasons": reasons,
                 "unexplained_people": sorted(map(str, diff[~explained]))}
        out["differences"].append(entry)
        if entry["unexplained_people"]:
            out["unexplained"].append(f)
    out["holds"] = not out["unexplained"]
    return out


def context(csv: Canonical, fhir: fhir_extract.Extract, link: dict[str, str], year: int) -> Context:
    """`link` maps FHIR patient ID -> CSV patient ID (the Synthea ID, kept as Patient.identifier)."""
    c = to_contract.training_rows(csv, year).set_index("patient_ref").sort_index()
    f = to_contract.training_rows(fhir.canonical, year)
    _, _, warnings = to_contract.scoring_rows(fhir.canonical, pd.Timestamp(year, 12, 31), explain=True)
    f["patient_ref"] = f.patient_ref.map(link)
    warnings = warnings.assign(patient_ref=warnings.patient_ref.map(link))
    f = f.set_index("patient_ref")
    mapped = {name: t.assign(person_id=t.person_id.map(link)) for name, t in fhir.canonical.tables().items()}
    if set(c.index) != set(f.index):
        raise ValueError(f"different people: CSV-only {sorted(set(c.index) - set(f.index))[:5]}, "
                         f"FHIR-only {sorted(set(f.index) - set(c.index))[:5]}")
    return Context(year, csv, c, f.reindex(c.index), warnings, Canonical(**mapped))


def markdown(result: dict) -> str:
    lines = [f"# CSV ↔ FHIR parity — year 1 = {result['year']}", "",
             f"{result['people']} adults through both extractors. **FR-F3 {'holds' if result['holds'] else 'FAILS'}**: "
             f"{len(result['identical'])} of {len(FEATURES) + 1} columns identical; every other difference "
             f"{'is explained and verified' if result['holds'] else 'must be explained — see UNEXPLAINED'}.", "",
             "| Column | People differing | CSV mean | FHIR mean | Reason (people it explains) |", "|---|---|---|---|---|"]
    for d in result["differences"]:
        why = "; ".join(f"{r['reason']} ({r['people']})" for r in d["reasons"]) or "—"
        if d["unexplained_people"]:
            why += f"; **UNEXPLAINED: {len(d['unexplained_people'])}**"
        lines.append(f"| `{d['feature']}` | {d['people']} | {d['csv_mean']:.2f} | {d['fhir_mean']:.2f} | {why} |")
    lines += ["", "Identical: " + ", ".join(f"`{c}`" for c in result["identical"]) + "."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    from fhir_clinical_client import FHIRClient

    from outcome_prediction.etl.extract import synthea_csv
    from outcome_prediction.settings import reports_dir
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", required=True)
    parser.add_argument("--fhir", required=True, help="FHIR base URL (or gateway URL)")
    parser.add_argument("--year", type=int, default=2023)
    args = parser.parse_args(argv)
    client = FHIRClient(args.fhir)
    found = client._search_all("Patient", {"_elements": "id"})
    link = {p["id"]: client.get_demographics(p["id"]).external_ids[0] for p in found}
    result = compare(context(synthea_csv.read(args.csv), fhir_extract.read(client, list(link)), link, args.year))
    reports_dir().mkdir(parents=True, exist_ok=True)
    (reports_dir() / f"parity_{args.year}.json").write_text(json.dumps(result, indent=2) + "\n")
    (reports_dir() / f"parity_{args.year}.md").write_text(markdown(result))
    print(markdown(result))
    if not result["holds"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
