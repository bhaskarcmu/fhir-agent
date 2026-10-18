"""
Record the care-history fixtures from a real HAPI FHIR server (not run by pytest).

How the committed fixture was made (Phase 8 M5):
  1. Synthea v4.0.0, seed 42, 5 Arizona patients, FHIR transaction bundles (hospitals and
     practitioners loaded first — patients reference them conditionally).
  2. hapiproject/hapi:v7.2.0 (the image docker-compose.yml uses), loaded with those bundles.
  3. python3 client/clinical/tests/record_care_history.py http://localhost:8090/fhir <synthea-uuid>

Every request the client makes and the server's response body are saved, keyed by request
path. A small page size forces several pages, so paging is recorded too. Synthea's synthetic
identity details (names, SSN-style identifiers, phone, street address, mother's maiden name,
birthplace, and patient names in reference displays) are removed — nothing the client reads.
"""
import json
import sys
from datetime import date
from pathlib import Path

from fhir_clinical_client import FHIRClient

OUT = Path(__file__).parent / "fixtures" / "care_history.json"
SINCE = date(2022, 1, 1)      # keeps the fixture small; still spans several pages


class RecordingClient(FHIRClient):
    SEARCH_PAGE_SIZE = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recorded = {}

    def _request(self, path, method="GET", body=None):
        status, response = super()._request(path, method, body)
        self.recorded[path] = response
        return status, response


SYNTHEA_ID_SYSTEM = "https://github.com/synthetichealth/synthea"
DROP_EXTENSIONS = ("patient-mothersMaidenName", "patient-birthPlace")


def scrub(node):
    """Remove synthetic identity details, recursively; everything else is left as recorded."""
    if isinstance(node, list):
        return [scrub(x) for x in node]
    if not isinstance(node, dict):
        return node
    node = dict(node)
    if node.get("resourceType") == "Patient":
        for key in ("name", "telecom", "contact", "text"):
            node.pop(key, None)
        node["identifier"] = [i for i in node.get("identifier", []) if i.get("system") == SYNTHEA_ID_SYSTEM]
        node["address"] = [{k: v for k, v in a.items() if k not in ("line", "extension")} for a in node.get("address", [])]
        node["extension"] = [e for e in node.get("extension", []) if not e.get("url", "").endswith(DROP_EXTENSIONS)]
    if str(node.get("reference", "")).startswith("Patient/"):
        node.pop("display", None)
    return {k: scrub(v) for k, v in node.items()}


def main(base_url: str, synthea_id: str) -> None:
    client = RecordingClient(base_url)
    found = client._search_all("Patient", {"identifier": synthea_id})
    patient_id = found[0]["id"]
    client.get_demographics(patient_id)
    client.get_encounters(patient_id, since=SINCE)
    client.get_medication_history(patient_id)
    client.get_medication_dispenses(patient_id)
    client.get_care_costs(patient_id, since=SINCE)
    client.get_coverage(patient_id)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"patient_id": patient_id, "since": SINCE.isoformat(),
                               "responses": scrub(client.recorded)}, separators=(",", ":")) + "\n")
    print(f"{OUT}: {len(client.recorded)} responses")


if __name__ == "__main__":
    main(*sys.argv[1:3])
