"""
Unit tests for FHIRClient domain object parsers.

Tests are grounded in real Synthea FHIR R4 output — the resource structures
used here match what Synthea actually produces, verified against generated
bundles in data/sample/fhir/.

No running fhir-service required.

Run:
  python3 -m pytest client/clinical/tests/test_parsers.py -v
"""

import unittest
from datetime import date

import pytest

from fhir_clinical_client import Allergy, Condition, Medication, Patient
from fhir_clinical_client.fhir_client import FHIRClient


# ─────────────────────────────────────────────────────────────────────────────
# _parse_date
# ─────────────────────────────────────────────────────────────────────────────

class TestParseDate:

    def test_iso_date_string(self):
        assert FHIRClient._parse_date("1990-06-15") == date(1990, 6, 15)

    def test_fhir_datetime_string(self):
        # Synthea produces full datetimes for authoredOn, onsetDateTime, etc.
        assert FHIRClient._parse_date("2004-04-27T23:32:28+00:00") == date(2004, 4, 27)

    def test_none_returns_none(self):
        assert FHIRClient._parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert FHIRClient._parse_date("") is None

    def test_malformed_returns_none(self):
        assert FHIRClient._parse_date("not-a-date") is None


# ─────────────────────────────────────────────────────────────────────────────
# _parse_medication
# ─────────────────────────────────────────────────────────────────────────────

class TestParseMedication:

    def _synthea_medication_request(self):
        """Real structure from a Synthea-generated MedicationRequest."""
        return {
            "resourceType": "MedicationRequest",
            "id": "54880da8-ffa7-f1ab-ba79-7c3f48e9b434",
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": {
                "coding": [
                    {
                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": "997488",
                        "display": "Fexofenadine hydrochloride 30 MG Oral Tablet",
                    }
                ],
                "text": "Fexofenadine hydrochloride 30 MG Oral Tablet",
            },
            "subject": {"reference": "Patient/544f37bb"},
            "authoredOn": "2004-04-27T23:32:28+00:00",
            "dosageInstruction": [
                {"sequence": 1, "text": "Take as needed.", "asNeededBoolean": True}
            ],
        }

    def test_full_medication_request(self):
        med = FHIRClient._parse_medication(self._synthea_medication_request())
        assert med.id == "54880da8-ffa7-f1ab-ba79-7c3f48e9b434"
        assert med.code == "997488"
        assert med.display == "Fexofenadine hydrochloride 30 MG Oral Tablet"
        assert med.status == "active"
        assert med.authored_on == date(2004, 4, 27)
        assert med.dosage_text == "Take as needed."

    def test_display_falls_back_to_coding_display(self):
        resource = self._synthea_medication_request()
        del resource["medicationCodeableConcept"]["text"]
        med = FHIRClient._parse_medication(resource)
        assert med.display == "Fexofenadine hydrochloride 30 MG Oral Tablet"

    def test_missing_authored_on(self):
        resource = self._synthea_medication_request()
        del resource["authoredOn"]
        med = FHIRClient._parse_medication(resource)
        assert med.authored_on is None

    def test_missing_dosage_instruction(self):
        resource = self._synthea_medication_request()
        del resource["dosageInstruction"]
        med = FHIRClient._parse_medication(resource)
        assert med.dosage_text is None

    def test_empty_dosage_instruction_list(self):
        resource = self._synthea_medication_request()
        resource["dosageInstruction"] = []
        med = FHIRClient._parse_medication(resource)
        assert med.dosage_text is None

    def test_missing_coding(self):
        resource = self._synthea_medication_request()
        resource["medicationCodeableConcept"] = {"text": "Some drug"}
        med = FHIRClient._parse_medication(resource)
        assert med.code == ""
        assert med.display == "Some drug"

    def test_returns_medication_instance(self):
        med = FHIRClient._parse_medication(self._synthea_medication_request())
        assert isinstance(med, Medication)


# ─────────────────────────────────────────────────────────────────────────────
# _parse_allergy
# ─────────────────────────────────────────────────────────────────────────────

class TestParseAllergy:

    def _synthea_allergy(self):
        """Real structure from a Synthea-generated AllergyIntolerance."""
        return {
            "resourceType": "AllergyIntolerance",
            "id": "4cbf505e-e053-e440-cf11-fb5a66edd73c",
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                        "code": "active",
                    }
                ]
            },
            "verificationStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                        "code": "confirmed",
                    }
                ]
            },
            "type": "allergy",
            "category": ["environment"],
            "criticality": "low",
            "code": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "419199007",
                        "display": "Allergy to substance (finding)",
                    }
                ],
                "text": "Allergy to substance (finding)",
            },
            "patient": {"reference": "Patient/544f37bb"},
            "recordedDate": "2004-04-27T22:54:01+00:00",
        }

    def test_full_allergy(self):
        allergy = FHIRClient._parse_allergy(self._synthea_allergy())
        assert allergy.id == "4cbf505e-e053-e440-cf11-fb5a66edd73c"
        assert allergy.code == "419199007"
        assert allergy.display == "Allergy to substance (finding)"
        assert allergy.criticality == "low"
        assert allergy.category == ["environment"]
        assert allergy.recorded_date == date(2004, 4, 27)

    def test_display_falls_back_to_coding_display(self):
        resource = self._synthea_allergy()
        del resource["code"]["text"]
        allergy = FHIRClient._parse_allergy(resource)
        assert allergy.display == "Allergy to substance (finding)"

    def test_missing_criticality_defaults(self):
        resource = self._synthea_allergy()
        del resource["criticality"]
        allergy = FHIRClient._parse_allergy(resource)
        assert allergy.criticality == "unable-to-assess"

    def test_missing_category_defaults_to_empty(self):
        resource = self._synthea_allergy()
        del resource["category"]
        allergy = FHIRClient._parse_allergy(resource)
        assert allergy.category == []

    def test_medication_category(self):
        resource = self._synthea_allergy()
        resource["category"] = ["medication"]
        allergy = FHIRClient._parse_allergy(resource)
        assert allergy.category == ["medication"]

    def test_missing_recorded_date(self):
        resource = self._synthea_allergy()
        del resource["recordedDate"]
        allergy = FHIRClient._parse_allergy(resource)
        assert allergy.recorded_date is None

    def test_returns_allergy_instance(self):
        allergy = FHIRClient._parse_allergy(self._synthea_allergy())
        assert isinstance(allergy, Allergy)


# ─────────────────────────────────────────────────────────────────────────────
# _parse_condition
# ─────────────────────────────────────────────────────────────────────────────

class TestParseCondition:

    def _synthea_condition_resolved(self):
        """Real structure from a Synthea-generated resolved Condition."""
        return {
            "resourceType": "Condition",
            "id": "ce152b5b-f8cc-45dd-0f86-d2bd39057cb7",
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "resolved",
                    }
                ]
            },
            "verificationStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                        "code": "confirmed",
                    }
                ]
            },
            "code": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "367498001",
                        "display": "Seasonal allergic rhinitis",
                    }
                ],
                "text": "Seasonal allergic rhinitis",
            },
            "subject": {"reference": "Patient/544f37bb"},
            "onsetDateTime": "2006-05-20T01:54:01+00:00",
            "abatementDateTime": "2021-10-29T01:54:01+00:00",
            "recordedDate": "2006-05-20T01:54:01+00:00",
        }

    def _synthea_condition_active(self):
        resource = self._synthea_condition_resolved()
        resource["clinicalStatus"]["coding"][0]["code"] = "active"
        del resource["abatementDateTime"]
        return resource

    def test_resolved_condition(self):
        cond = FHIRClient._parse_condition(self._synthea_condition_resolved())
        assert cond.id == "ce152b5b-f8cc-45dd-0f86-d2bd39057cb7"
        assert cond.code == "367498001"
        assert cond.display == "Seasonal allergic rhinitis"
        assert cond.clinical_status == "resolved"
        assert cond.onset_date == date(2006, 5, 20)
        assert cond.abatement_date == date(2021, 10, 29)
        assert cond.recorded_date == date(2006, 5, 20)

    def test_active_condition_no_abatement(self):
        cond = FHIRClient._parse_condition(self._synthea_condition_active())
        assert cond.clinical_status == "active"
        assert cond.abatement_date is None

    def test_display_falls_back_to_coding_display(self):
        resource = self._synthea_condition_resolved()
        del resource["code"]["text"]
        cond = FHIRClient._parse_condition(resource)
        assert cond.display == "Seasonal allergic rhinitis"

    def test_missing_clinical_status_defaults(self):
        resource = self._synthea_condition_resolved()
        del resource["clinicalStatus"]
        cond = FHIRClient._parse_condition(resource)
        assert cond.clinical_status == "unknown"

    def test_missing_onset_date(self):
        resource = self._synthea_condition_resolved()
        del resource["onsetDateTime"]
        cond = FHIRClient._parse_condition(resource)
        assert cond.onset_date is None

    def test_returns_condition_instance(self):
        cond = FHIRClient._parse_condition(self._synthea_condition_resolved())
        assert isinstance(cond, Condition)


# ─────────────────────────────────────────────────────────────────────────────
# search_patients — URL encoding and response parsing
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchPatients(unittest.TestCase):

    def _mock_search_response(self, patients: list[dict]):
        """Build a FHIR Bundle search response containing the given patient resources."""
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(patients),
            "entry": [{"resource": p} for p in patients],
        }

    def _synthea_patient(self, pid="abc123", family="Mraz", given="Kristle"):
        return {
            "resourceType": "Patient",
            "id": pid,
            "name": [{"family": family, "given": [given]}],
            "gender": "female",
            "birthDate": "1974-03-12",
        }

    def _make_client(self):
        return FHIRClient("http://localhost:8080/fhir", "test-key")

    def _mock_request(self, client, status, response_body):
        client._request = lambda path, method="GET", body=None: (status, response_body)

    def test_returns_list_of_patients(self):
        client = self._make_client()
        self._mock_request(
            client, 200,
            self._mock_search_response([self._synthea_patient()])
        )
        results = client.search_patients("Kristle")
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], Patient)

    def test_patient_fields_populated(self):
        client = self._make_client()
        self._mock_request(
            client, 200,
            self._mock_search_response([self._synthea_patient()])
        )
        p = client.search_patients("Mraz")[0]
        self.assertEqual(p.id, "abc123")
        self.assertEqual(p.family_name, "Mraz")
        self.assertEqual(p.given_name, "Kristle")
        self.assertEqual(p.gender, "female")
        self.assertEqual(p.birth_date, date(1974, 3, 12))

    def test_empty_results_returns_empty_list(self):
        client = self._make_client()
        self._mock_request(
            client, 200,
            {"resourceType": "Bundle", "type": "searchset", "total": 0}
        )
        results = client.search_patients("NoSuchPerson")
        self.assertEqual(results, [])

    def test_multiple_matches_all_returned(self):
        client = self._make_client()
        self._mock_request(
            client, 200,
            self._mock_search_response([
                self._synthea_patient("id1", "Smith", "Alice"),
                self._synthea_patient("id2", "Smith", "Bob"),
            ])
        )
        results = client.search_patients("Smith")
        self.assertEqual(len(results), 2)

    def test_server_error_raises_fhir_client_error(self):
        from fhir_clinical_client import FHIRClientError
        client = self._make_client()
        self._mock_request(client, 500, {"issue": []})
        with self.assertRaises(FHIRClientError):
            client.search_patients("anyone")

    def test_spaces_encoded_in_name(self):
        """Multi-word names are split into separate name= parameters (no raw spaces)."""
        client = self._make_client()
        captured = {}
        def fake_request(path, method="GET", body=None):
            captured["path"] = path
            return (200, {"resourceType": "Bundle", "type": "searchset"})
        client._request = fake_request
        client.search_patients("Kristle Mraz")
        # HAPI does not treat + as a space; each token must be a separate name= param
        self.assertIn("name=Kristle", captured["path"])
        self.assertIn("name=Mraz", captured["path"])
        self.assertNotIn(" ", captured["path"])
        self.assertNotIn("Kristle+Mraz", captured["path"])


# ─────────────────────────────────────────────────────────────────────────────
# Public imports
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicImports:
    """Verify all new symbols are exported from the package root."""

    def test_medication_importable(self):
        from fhir_clinical_client import Medication
        assert Medication is not None

    def test_allergy_importable(self):
        from fhir_clinical_client import Allergy
        assert Allergy is not None

    def test_condition_importable(self):
        from fhir_clinical_client import Condition
        assert Condition is not None
