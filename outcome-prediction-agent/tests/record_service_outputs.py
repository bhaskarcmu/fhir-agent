"""Record the scoring service's real tool outputs for this package's tests (not run by pytest).

Needs outcome-prediction-service installed (`pip install -e client/clinical -e
"outcome-prediction-service[dev,api]"`) and a trained meps25-v1 artifact; uses M6's recorded FHIR
conversation, so no FHIR server is needed:

    python outcome-prediction-agent/tests/record_service_outputs.py

The agent never imports the service at run time; these files are what its HTTP tools return.
`service_tools.json` is checked against the live definitions by the service's own tests.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from fhir_clinical_client import Patient

from outcome_prediction import api
from outcome_prediction.tests.test_etl_fhir import LINK, RECORDING, Replay

OUT = Path(__file__).parent / "fixtures"
PATIENT = next(iter(LINK))


class Server(Replay):
    def _request(self, path, method="GET", body=None, headers=None):
        path = re.sub(r"(date|created)=ge\d{4}-\d{2}-\d{2}", rf"\1=ge{RECORDING['since']}", path)
        return super()._request(path, method, body, headers)

    def search_patients(self, name):
        one = Patient(id=PATIENT, family_name="Doe", given_name="Jane", gender="female")
        two = Patient(id="9999", family_name="Doe", given_name="Jane", gender="female")
        return {"Jane Doe": [one], "Doe": [one, two]}.get(name, [])


def main() -> None:
    api.app.dependency_overrides[api.get_client] = lambda: Server()
    outputs = {}
    with TestClient(api.app) as c:
        outputs["tools"] = c.get("/agent-tools").json()
        calls = {
            "estimate": ("get_hospitalization_risk", {"patient_id": PATIENT, "as_of": "2023-12-31"}),
            "no_estimate": ("get_hospitalization_risk", {"patient_id": PATIENT, "as_of": "1950-01-01"}),
            "model_card": ("get_model_card", {}),
            "one_match": ("find_patient", {"name": "Jane Doe"}),
            "two_matches": ("find_patient", {"name": "Doe"}),
            "no_match": ("find_patient", {"name": "Nobody"}),
        }
        for key, (tool, args) in calls.items():
            outputs[key] = c.post(f"/agent-tools/{tool}", json=args).json()
    (OUT / "service_tools.json").write_text(json.dumps(outputs.pop("tools"), indent=1) + "\n")
    outputs["patient_id"] = PATIENT
    (OUT / "service_outputs.json").write_text(json.dumps(outputs, indent=1) + "\n")
    print(f"{OUT}: {sorted(outputs)}")


if __name__ == "__main__":
    main()
