"""
Unit tests for the care-history methods (Phase 8 M5): demographics, encounters, medication
history, dispenses, care costs and coverage.

Most tests replay responses recorded from a real HAPI FHIR v7.2.0 server loaded with Synthea
v4.0.0 patients (fixtures/care_history.json; how it was made: record_care_history.py), so they
check the client against what a server actually sends, paging included. The rest cover shapes
Synthea doesn't produce (dispenses, Coverage, an emergency admit source).

No running fhir-service required.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from fhir_clinical_client import (
    CareCost, Demographics, Dispense, Encounter, FHIRClientError, InsuranceCoverage, Prescription,
)
from fhir_clinical_client.fhir_client import FHIRClient

RECORDING = json.loads((Path(__file__).parent / "fixtures" / "care_history.json").read_text())
SINCE = date.fromisoformat(RECORDING["since"])


class ReplayClient(FHIRClient):
    """Answers from the recording; an unrecorded request fails the test."""
    SEARCH_PAGE_SIZE = 10

    def __init__(self):
        super().__init__("http://gateway.test:8000")
        self.paths = []

    def _request(self, path, method="GET", body=None, headers=None):
        self.paths.append(path)
        if path not in RECORDING["responses"]:
            raise AssertionError(f"unrecorded request: {path}")
        return 200, RECORDING["responses"][path]


@pytest.fixture
def client():
    return ReplayClient()


PID = RECORDING["patient_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Replayed from a real server
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordedDemographics:

    def test_demographics_in_clinical_terms(self, client):
        d = client.get_demographics(PID)
        assert isinstance(d, Demographics)
        assert d.patient_id == PID and d.gender == "female"
        assert d.birth_date == date(2003, 4, 12)
        assert d.deceased is False and d.deceased_date is None
        assert d.state == "AZ" and d.postal_code
        assert d.race == ["Native Hawaiian or Other Pacific Islander"]
        assert d.ethnicity == "Not Hispanic or Latino"
        # The Synthea ID survives as an external identifier — what links FHIR to CSV (M6).
        assert "aa616abe-1761-0c9a-7959-07544679dafd" in d.external_ids


class TestRecordedEncounters:

    def test_every_page_is_read_and_replayed_through_the_gateway(self, client):
        encounters = client.get_encounters(PID, since=SINCE)
        pages = [p for p in client.paths if p.startswith("?_getpages=")]
        assert len(pages) >= 2                       # recorded with 10 per page
        assert len(encounters) > 20
        assert len({e.id for e in encounters}) == len(encounters)

    def test_since_is_sent_to_the_server(self, client):
        client.get_encounters(PID, since=SINCE)
        assert f"date=ge{SINCE.isoformat()}" in client.paths[0]

    def test_encounters_have_settings_and_times(self, client):
        encounters = client.get_encounters(PID, since=SINCE)
        assert all(isinstance(e, Encounter) for e in encounters)
        assert {e.setting for e in encounters} <= {"ambulatory", "emergency", "inpatient", "home_health", "virtual"}
        assert "ambulatory" in {e.setting for e in encounters}
        for e in encounters:
            assert e.start and e.start.tzinfo is not None
            assert e.end is None or e.end >= e.start
            assert e.type_display
        # Synthea records no admit source, so "from the ER?" stays unknown rather than False.
        assert all(e.admitted_from_emergency is None for e in encounters)


class TestRecordedMedicationHistory:

    def test_history_includes_every_status(self, client):
        history = client.get_medication_history(PID)
        assert all(isinstance(p, Prescription) for p in history)
        assert {"active", "completed"} <= {p.status for p in history}
        assert all(p.code and p.display and p.authored_on for p in history)
        assert all(p.encounter_id for p in history)

    def test_history_reads_every_page(self, client):
        history = client.get_medication_history(PID)
        assert len(history) > ReplayClient.SEARCH_PAGE_SIZE

    def test_synthea_records_no_dispenses_or_coverage(self, client):
        assert client.get_medication_dispenses(PID) == []
        assert client.get_coverage(PID) == []


class TestRecordedCareCosts:

    def test_costs_by_category_with_amounts_and_payer(self, client):
        costs = client.get_care_costs(PID, since=SINCE)
        assert all(isinstance(c, CareCost) for c in costs)
        assert {"professional", "institutional", "pharmacy"} <= {c.category for c in costs}
        assert all(c.billed is not None and c.billed >= 0 and c.currency == "USD" for c in costs)
        assert all(c.payer for c in costs)
        assert all(c.service_start and c.service_end >= c.service_start for c in costs)

    def test_pharmacy_costs_name_the_medicine_and_others_the_encounter(self, client):
        costs = client.get_care_costs(PID, since=SINCE)
        assert all(c.medication_codes for c in costs if c.category == "pharmacy")
        assert all(c.encounter_ids for c in costs)

    def test_costs_link_to_real_encounters(self, client):
        encounter_ids = {e.id for e in client.get_encounters(PID, since=SINCE)}
        costs = client.get_care_costs(PID, since=SINCE)
        linked = [eid for c in costs for eid in c.encounter_ids]
        assert linked and set(linked) <= encounter_ids


# ─────────────────────────────────────────────────────────────────────────────
# Shapes Synthea doesn't produce
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_emergency_admission_is_read_from_admit_source(self):
        stay = {"resourceType": "Encounter", "id": "e1", "status": "finished",
                "class": {"code": "IMP"},
                "period": {"start": "2024-03-01T10:00:00Z", "end": "2024-03-04T09:00:00Z"},
                "hospitalization": {"admitSource": {"coding": [{"code": "emd"}]}}}
        e = FHIRClient._parse_encounter(stay)
        assert e.setting == "inpatient" and e.admitted_from_emergency is True
        assert e.start == datetime(2024, 3, 1, 10, tzinfo=timezone.utc)
        stay["hospitalization"]["admitSource"]["coding"][0]["code"] = "gp"
        assert FHIRClient._parse_encounter(stay).admitted_from_emergency is False
        stay["class"]["code"] = "AMB"                # admit source means nothing outside a stay
        assert FHIRClient._parse_encounter(stay).admitted_from_emergency is None

    def test_unknown_encounter_class_is_other(self):
        assert FHIRClient._parse_encounter({"class": {"code": "FLD"}}).setting == "other"

    def test_deceased_without_a_date(self):
        d = FHIRClient._parse_demographics({"id": "p", "gender": "male", "deceasedBoolean": True})
        assert d.deceased is True and d.deceased_date is None and d.race == []

    def test_prescription_with_refills_and_supply(self):
        p = FHIRClient._parse_prescription({
            "id": "m1", "status": "active", "medicationCodeableConcept": {"coding": [{"code": "197361"}]},
            "dispenseRequest": {"validityPeriod": {"start": "2024-01-01", "end": "2024-12-31"},
                                "numberOfRepeatsAllowed": 3, "quantity": {"value": 30},
                                "expectedSupplyDuration": {"value": 4, "code": "wk"}},
            "encounter": {"reference": "Encounter/9"}})
        assert (p.refills_allowed, p.supply_days, p.quantity, p.encounter_id) == (3, 28.0, 30.0, "9")
        assert (p.valid_from, p.valid_until) == (date(2024, 1, 1), date(2024, 12, 31))

    def test_dispense(self):
        d = FHIRClient._parse_dispense({
            "resourceType": "MedicationDispense", "id": "d1", "status": "completed",
            "medicationCodeableConcept": {"coding": [{"code": "197361", "display": "Amlodipine 5 MG"}]},
            "quantity": {"value": 90}, "daysSupply": {"value": 90, "unit": "days"},
            "whenHandedOver": "2024-02-03T15:00:00+00:00",
            "authorizingPrescription": [{"reference": "MedicationRequest/m1"}]})
        assert isinstance(d, Dispense)
        assert (d.code, d.quantity, d.supply_days, d.prescription_id) == ("197361", 90.0, 90.0, "m1")
        assert d.dispensed_at == datetime(2024, 2, 3, 15, tzinfo=timezone.utc)

    def test_coverage(self):
        c = FHIRClient._parse_coverage({"id": "c1", "status": "active", "type": {"text": "Medicaid"},
                                        "payor": [{"display": "State Medicaid"}],
                                        "period": {"start": "2023-01-01"}})
        assert c == InsuranceCoverage(id="c1", payer="State Medicaid", plan_type="Medicaid",
                                      status="active", start=date(2023, 1, 1), end=None)

    def test_care_cost_without_item_dates_uses_the_billing_period(self):
        c = FHIRClient._parse_care_cost({
            "id": "x", "type": {"coding": [{"code": "institutional"}]},
            "billablePeriod": {"start": "2024-05-01", "end": "2024-05-03"},
            "total": [{"category": {"coding": [{"code": "submitted"}]}, "amount": {"value": 900.0, "currency": "USD"}}],
            "insurer": {"display": "Acme Health"}})
        assert (c.service_start, c.service_end) == (datetime(2024, 5, 1), datetime(2024, 5, 3))
        assert (c.billed, c.paid, c.payer) == (900.0, None, "Acme Health")

    def test_paging_stops_at_the_page_limit(self):
        class Endless(FHIRClient):
            def _request(self, path, method="GET", body=None, headers=None):
                return 200, {"entry": [], "link": [{"relation": "next", "url": "http://x/fhir?_getpages=a"}]}
        with pytest.raises(FHIRClientError, match="exceeded"):
            Endless("http://x")._search_all("Encounter", {"patient": "1"}, max_pages=3)


class TestExistingBehaviourUnchanged:

    def test_get_medications_still_requests_active_only_first_page(self):
        class Spy(FHIRClient):
            paths = []
            def _request(self, path, method="GET", body=None, headers=None):
                self.paths.append(path)
                return 200, {}
        Spy("http://x").get_medications("p1")
        assert Spy.paths == ["/MedicationRequest?patient=p1&status=active&_count=100"]


class TestHistoryCompleteness:
    """Added in Phase 8 M6: medicines named by reference, and condition histories over 100."""

    def test_referenced_medicines_are_resolved(self):
        page = json.loads((Path(__file__).parent / "fixtures" / "medication_reference_page.json").read_text())

        class OnePage(FHIRClient):
            paths = []
            def _request(self, path, method="GET", body=None, headers=None):
                self.paths.append(path)
                return 200, page
        history = OnePage("http://x").get_medication_history("p")
        assert "_include=MedicationRequest%3Amedication" in OnePage.paths[0]
        by_reference = [e["resource"] for e in page["entry"]
                        if e["resource"]["resourceType"] == "MedicationRequest" and "medicationReference" in e["resource"]]
        assert by_reference                                   # the recorded page really uses references
        assert len(history) == 5 and all(p.code and p.display for p in history)

    def test_condition_history_reads_every_page(self, client):
        history = client.get_condition_history(PID)
        assert sum(p.startswith("?_getpages=") for p in client.paths) == 3      # 32 conditions, 10 a page
        assert len(history) == 32 and len({c.id for c in history}) == 32
        assert all(c.code and c.display for c in history)

    def test_get_conditions_is_unchanged(self):
        class Spy(FHIRClient):
            paths = []
            def _request(self, path, method="GET", body=None, headers=None):
                self.paths.append(path)
                return 200, {}
        Spy("http://x").get_conditions("p1")
        assert Spy.paths == ["/Condition?patient=p1&_count=100"]


class TestNoCachedSearches:
    """Phase 8 M12: HAPI reuses a search's results for about a minute, so a record written just
    before a care-history read would be missing. Those searches ask for no cache."""

    def test_care_history_searches_ask_for_no_cache(self):
        class Spy(FHIRClient):
            sent = []
            def _request(self, path, method="GET", body=None, headers=None):
                self.sent.append(headers)
                return 200, {}
        Spy("http://x").get_encounters("p1")
        assert Spy.sent == [{"Cache-Control": "no-cache"}]

    def test_existing_methods_send_no_extra_headers(self):
        class Spy(FHIRClient):
            sent = []
            def _request(self, path, method="GET", body=None, headers=None):
                self.sent.append(headers)
                return 200, {}
        Spy("http://x").get_medications("p1")
        assert Spy.sent == [None]
