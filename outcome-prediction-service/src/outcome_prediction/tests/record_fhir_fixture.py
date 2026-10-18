"""Record the FHIR half of the parity fixture (M6) from a real server — not run by pytest.

How `fixtures/fhir_recording.json` was made:
  1. Synthea v4.0.0, seed 42, 20 Arizona patients, CSV + FHIR from the same run (O11, O61);
     hospital and practitioner bundles loaded first (patients reference them conditionally).
  2. hapiproject/hapi:v7.2.0 (the image docker-compose.yml uses), loaded with those bundles.
  3. python -m outcome_prediction.tests.record_fhir_fixture http://localhost:8090/fhir

It records every request the FHIR extractor makes for the 7 patients of the CSV fixture
(`fixtures/synthea_csv`, same seed, same patients), so the parity test runs both paths on the
same people offline. Each response keeps only the fields `client/clinical` reads — which also
drops Synthea's synthetic names, SSN-style identifiers, phone numbers and street addresses.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from fhir_clinical_client import FHIRClient

from outcome_prediction.etl.extract import fhir

OUT = Path(__file__).parent / "fixtures" / "fhir_recording.json"
SINCE = date(2021, 1, 1)            # covers year 1 = 2023 (+ 2024 label) and as-of dates from 2022
CSV_FIXTURE = Path(__file__).parent / "fixtures" / "synthea_csv" / "patients.csv"
SYNTHEA_ID_SYSTEM = "https://github.com/synthetichealth/synthea"

KEEP = {
    "Patient": {"resourceType", "id", "gender", "birthDate", "deceasedDateTime", "deceasedBoolean",
                "address", "extension", "identifier"},
    "Encounter": {"resourceType", "id", "class", "status", "period", "type", "hospitalization", "reasonCode"},
    "Condition": {"resourceType", "id", "code", "clinicalStatus", "onsetDateTime", "abatementDateTime", "recordedDate"},
    "ExplanationOfBenefit": {"resourceType", "id", "type", "item", "billablePeriod", "insurance", "insurer",
                             "total", "payment"},
}
EOB_ITEM_KEEP = {"servicedPeriod", "servicedDate", "encounter", "productOrService"}
US_CORE = ("us-core-race", "us-core-ethnicity")


def trim(resource: dict) -> dict:
    kind = resource.get("resourceType")
    r = {k: v for k, v in resource.items() if k in KEEP.get(kind, set(resource))}
    if kind == "Patient":
        r["identifier"] = [i for i in r.get("identifier", []) if i.get("system") == SYNTHEA_ID_SYSTEM]
        r["address"] = [{k: a[k] for k in ("state", "postalCode") if k in a} for a in r.get("address", [])]
        r["extension"] = [e for e in r.get("extension", []) if e.get("url", "").endswith(US_CORE)]
    if kind == "ExplanationOfBenefit":
        r["item"] = [{k: v for k, v in i.items() if k in EOB_ITEM_KEEP} for i in r.get("item", [])]
        for i in r["item"]:                 # the client reads only an RxNorm item's system and code
            codes = (i.get("productOrService") or {}).get("coding", [{}])[:1]
            i["productOrService"] = {"coding": [{k: c[k] for k in ("system", "code") if k in c} for c in codes]}
        r["total"] = [t for t in r.get("total", [])
                      if ((t.get("category") or {}).get("coding") or [{}])[0].get("code") == "submitted"]
        r["insurance"] = [{"focal": i.get("focal"), "coverage": {"display": (i.get("coverage") or {}).get("display")}}
                          for i in r.get("insurance", [])]
    return r


def trim_bundle(body: dict) -> dict:
    if body.get("resourceType") != "Bundle":
        return trim(body)
    return {"resourceType": "Bundle", "link": [l for l in body.get("link", []) if l.get("relation") == "next"],
            "entry": [{"resource": trim(e["resource"])} for e in body.get("entry", [])]}


class RecordingClient(FHIRClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recorded = {}

    def _request(self, path, method="GET", body=None):
        status, response = super()._request(path, method, body)
        self.recorded[path] = trim_bundle(response)
        return status, response


def main(base_url: str) -> None:
    synthea_ids = [line.split(",")[0] for line in CSV_FIXTURE.read_text().splitlines()[1:]]
    client = RecordingClient(base_url)
    link = {}
    for sid in synthea_ids:
        found = client._search_all("Patient", {"identifier": f"{SYNTHEA_ID_SYSTEM}|{sid}"})
        link[found[0]["id"]] = sid
    fhir.read(client, list(link), since=SINCE)
    OUT.write_text(json.dumps({"since": SINCE.isoformat(), "link": link, "responses": client.recorded},
                              separators=(",", ":")) + "\n")
    print(f"{OUT}: {len(client.recorded)} responses, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1])
