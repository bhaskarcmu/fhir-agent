"""
Domain-abstracted FHIR client for clinical application developers.

Audience: Clinical application developers (Hat 2) — engineers at healthcare
providers, digital health firms, and care delivery organisations who build
workflows and experiences on top of the FHIR platform. Also the foundation
for the MCP agent.

This client is intentionally blind to fhir-service internals. It speaks in
clinical domain terms — patients, medications, conditions — not FHIR bundles,
search parameters, or HTTP verbs. You do not need to understand FHIR to use it.

Usage:
    from fhir_clinical_client import FHIRClient

    client = FHIRClient(
        gateway_url=os.environ["FHIR_GATEWAY_URL"],
        api_key=os.environ["FHIR_API_KEY"],
    )

    patient_id = client.create_patient(
        family="Smith", given="Jane", birth_date="1990-03-15", gender="female"
    )
    patient = client.get_patient(patient_id)
    print(patient.family_name)   # "Smith"
    print(patient.birth_date)    # datetime.date(1990, 3, 15)
"""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

@dataclass
class Patient:
    """
    A clinical patient record.

    This is a domain object — it does not expose FHIR resource structure.
    Fields map to the clinical concepts a care application cares about.
    """
    id: str
    family_name: str
    given_name: str
    gender: str
    birth_date: Optional[date] = None   # FHIR birthDate is optional


@dataclass
class Medication:
    """
    An active medication request for a patient.

    Derived from a FHIR MedicationRequest resource. Only active requests
    are returned by get_medications() — stopped, cancelled, and draft
    requests are excluded.
    """
    id: str
    code: str               # RxNorm code (e.g. "997488")
    display: str            # Human-readable name (e.g. "Fexofenadine hydrochloride 30 MG Oral Tablet")
    status: str             # FHIR status: "active", "on-hold", etc.
    authored_on: Optional[date] = None   # Date the prescription was written
    dosage_text: Optional[str] = None    # Free-text dosage instruction if present


@dataclass
class Allergy:
    """
    An allergy or intolerance recorded for a patient.

    Derived from a FHIR AllergyIntolerance resource. get_allergies() returns
    all recorded allergies regardless of clinical status — callers filter by
    the criticality or category fields if needed.
    """
    id: str
    code: str               # SNOMED CT code (e.g. "419199007")
    display: str            # Human-readable substance name
    criticality: str        # "low", "high", or "unable-to-assess"
    category: list[str]     # e.g. ["medication"], ["food"], ["environment"]
    recorded_date: Optional[date] = None


@dataclass
class Condition:
    """
    A clinical condition or diagnosis recorded for a patient.

    Derived from a FHIR Condition resource. get_conditions() returns
    all conditions regardless of clinical status — callers filter by
    the clinical_status field if needed.
    """
    id: str
    code: str               # SNOMED CT code (e.g. "5689008")
    display: str            # Human-readable condition name
    clinical_status: str    # "active", "resolved", "inactive", "remission"
    onset_date: Optional[date] = None       # When the condition began
    abatement_date: Optional[date] = None   # When the condition resolved (None if ongoing)
    recorded_date: Optional[date] = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FHIRClientError(Exception):
    """Raised when the FHIR gateway returns an unexpected response."""
    def __init__(self, message: str, status_code: int = 0, body: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}


class AuthenticationError(FHIRClientError):
    """Raised when the gateway rejects the API key (HTTP 401)."""


class NotFoundError(FHIRClientError):
    """Raised when a requested resource does not exist (HTTP 404)."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class FHIRClient:
    """
    Domain-abstracted client for the fhir-agent platform.

    Hides all FHIR mechanics (resource structure, bundle parsing, search
    parameters, HTTP headers) behind clinical domain methods.

    All methods raise FHIRClientError (or a subclass) on failure.
    They never return raw FHIR JSON.
    """

    def __init__(self, gateway_url: str, api_key: str):
        """
        Args:
            gateway_url: Base URL of the Kong gateway, e.g.
                         "http://localhost:8000" or "https://api.example.com".
                         Do not include /fhir — the client appends it.
            api_key:     API key issued by the platform team via create-key.sh.

        Raises:
            ValueError if gateway_url or api_key is empty.
        """
        if not gateway_url or not gateway_url.strip():
            raise ValueError(
                "gateway_url is required. Set FHIR_GATEWAY_URL to the Kong proxy URL."
            )
        if not api_key or not api_key.strip():
            raise ValueError(
                "api_key is required. Set FHIR_API_KEY to a key from create-key.sh."
            )
        self._base = gateway_url.rstrip("/") + "/fhir"
        self._api_key = api_key

    # -----------------------------------------------------------------------
    # Internal HTTP helper
    # -----------------------------------------------------------------------

    def _request(self, path: str, method: str = "GET", body: dict = None) -> tuple[int, dict]:
        """Send an authenticated FHIR request. Returns (status_code, parsed_body)."""
        url = f"{self._base}{path}"
        headers = {
            "Content-Type": "application/fhir+json",
            "Accept":       "application/fhir+json",
            "apikey":       self._api_key,
        }
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            try:
                body_text = e.read().decode("utf-8", errors="replace")
                resp_body = json.loads(body_text)
            except Exception:
                resp_body = {"error": str(e)}
            if e.code == 401:
                raise AuthenticationError(
                    "API key rejected. Check FHIR_API_KEY.", e.code, resp_body
                )
            if e.code == 404:
                raise NotFoundError(
                    f"Resource not found: {path}", e.code, resp_body
                )
            raise FHIRClientError(
                f"Gateway returned {e.code} for {method} {path}", e.code, resp_body
            )
        except Exception as e:
            raise FHIRClientError(f"Request failed: {e}")

    # -----------------------------------------------------------------------
    # Server status
    # -----------------------------------------------------------------------

    def get_server_status(self) -> dict:
        """
        Check whether the FHIR server is reachable and healthy.

        Returns:
            {"status": "ok", "fhir_version": "4.0.1"}

        Raises:
            FHIRClientError if the server is unreachable or unhealthy.
        """
        status, body = self._request("/metadata")
        if status != 200 or body.get("resourceType") != "CapabilityStatement":
            raise FHIRClientError(
                "Server did not return a valid CapabilityStatement.", status, body
            )
        return {
            "status": "ok",
            "fhir_version": body.get("fhirVersion", "unknown"),
        }

    # -----------------------------------------------------------------------
    # Patient operations
    # -----------------------------------------------------------------------

    def create_patient(
        self,
        family: str,
        given: str,
        gender: str,
        birth_date: Optional[str] = None,
    ) -> str:
        """
        Register a new patient.

        Args:
            family:     Family (last) name.
            given:      Given (first) name.
            gender:     "male", "female", "other", or "unknown".
            birth_date: ISO date string "YYYY-MM-DD", or None.

        Returns:
            The platform-assigned patient ID (string). Store this — it is
            the key for all subsequent operations on this patient.

        Raises:
            FHIRClientError on failure.
        """
        payload = {
            "resourceType": "Patient",
            "name": [{"family": family, "given": [given]}],
            "gender": gender,
        }
        if birth_date:
            payload["birthDate"] = birth_date

        status, body = self._request("/Patient", method="POST", body=payload)
        if status != 201:
            raise FHIRClientError(
                f"Failed to create patient (expected 201, got {status}).", status, body
            )
        patient_id = body.get("id")
        if not patient_id:
            raise FHIRClientError("Server returned 201 but no patient ID.", status, body)
        return patient_id

    def get_patient(self, patient_id: str) -> Patient:
        """
        Retrieve a patient by ID.

        Args:
            patient_id: The ID returned by create_patient().

        Returns:
            A Patient dataclass with clinical fields populated.

        Raises:
            NotFoundError if the patient does not exist.
            FHIRClientError on other failures.
        """
        status, body = self._request(f"/Patient/{patient_id}")
        if status != 200:
            raise FHIRClientError(
                f"Failed to retrieve patient {patient_id} (got {status}).", status, body
            )
        return self._parse_patient(body)

    def delete_patient(self, patient_id: str) -> None:
        """
        Delete a patient record.

        Primarily used for test cleanup. In production, consider whether
        deletion is the right operation vs. marking the patient as inactive.

        Args:
            patient_id: The ID of the patient to delete.

        Raises:
            NotFoundError if the patient does not exist.
            FHIRClientError on other failures.
        """
        self._request(f"/Patient/{patient_id}", method="DELETE")

    # -----------------------------------------------------------------------
    # Clinical data
    # -----------------------------------------------------------------------

    def get_medications(self, patient_id: str) -> list[Medication]:
        """
        Return all medication requests for a patient.

        Queries active MedicationRequests only (status=active). Stopped,
        cancelled, and draft prescriptions are excluded.

        Args:
            patient_id: The ID returned by create_patient() or get_patient().

        Returns:
            List of Medication domain objects, empty list if none recorded.

        Raises:
            FHIRClientError on server errors.
        """
        status, body = self._request(
            f"/MedicationRequest?patient={patient_id}&status=active&_count=100"
        )
        if status != 200:
            raise FHIRClientError(
                f"Failed to retrieve medications for patient {patient_id} (got {status}).",
                status, body,
            )
        return [
            self._parse_medication(entry["resource"])
            for entry in body.get("entry", [])
            if entry.get("resource", {}).get("resourceType") == "MedicationRequest"
        ]

    def get_allergies(self, patient_id: str) -> list[Allergy]:
        """
        Return all allergy and intolerance records for a patient.

        Returns all AllergyIntolerance resources regardless of clinical
        status. Callers filter by the criticality or category fields if
        needed. The triage service uses this to check drug-allergy conflicts.

        Args:
            patient_id: The ID returned by create_patient() or get_patient().

        Returns:
            List of Allergy domain objects, empty list if none recorded.

        Raises:
            FHIRClientError on server errors.
        """
        status, body = self._request(
            f"/AllergyIntolerance?patient={patient_id}&_count=100"
        )
        if status != 200:
            raise FHIRClientError(
                f"Failed to retrieve allergies for patient {patient_id} (got {status}).",
                status, body,
            )
        return [
            self._parse_allergy(entry["resource"])
            for entry in body.get("entry", [])
            if entry.get("resource", {}).get("resourceType") == "AllergyIntolerance"
        ]

    def get_conditions(self, patient_id: str) -> list[Condition]:
        """
        Return all conditions recorded for a patient.

        Returns all Condition resources regardless of clinical status
        (active, resolved, inactive, remission). Callers filter by
        the clinical_status field if they need only active conditions.

        Args:
            patient_id: The ID returned by create_patient() or get_patient().

        Returns:
            List of Condition domain objects, empty list if none recorded.

        Raises:
            FHIRClientError on server errors.
        """
        status, body = self._request(
            f"/Condition?patient={patient_id}&_count=100"
        )
        if status != 200:
            raise FHIRClientError(
                f"Failed to retrieve conditions for patient {patient_id} (got {status}).",
                status, body,
            )
        return [
            self._parse_condition(entry["resource"])
            for entry in body.get("entry", [])
            if entry.get("resource", {}).get("resourceType") == "Condition"
        ]

    # -----------------------------------------------------------------------
    # Future stubs
    # -----------------------------------------------------------------------

    # TODO: get_appointments(patient_id: str) -> list[Appointment]
    #   Returns upcoming appointments for the patient.
    #   Hides: GET /fhir/Appointment?patient={id}&date=ge{today}, Bundle parsing.

    # -----------------------------------------------------------------------
    # Internal parsers — FHIR mechanics stay here, never leak to callers
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_date(raw: str | None) -> Optional[date]:
        """Parse an ISO 8601 date or datetime string into a date. Returns None on failure."""
        if not raw:
            return None
        try:
            # FHIR dates can be "YYYY-MM-DD" or full datetimes "YYYY-MM-DDTHH:MM:SS+00:00"
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    @staticmethod
    def _parse_patient(resource: dict) -> Patient:
        """Parse a FHIR Patient resource into a domain Patient object."""
        name = resource.get("name", [{}])[0]
        family = name.get("family", "")
        given_list = name.get("given", [""])
        given = given_list[0] if given_list else ""

        birth_date = None
        raw_date = resource.get("birthDate")
        if raw_date:
            try:
                # date.fromisoformat() validates the full ISO 8601 date string,
                # including bounds (e.g. "2021-02-30" raises ValueError correctly).
                birth_date = date.fromisoformat(raw_date)
            except ValueError:
                birth_date = None  # malformed date — treat as absent

        return Patient(
            id=resource.get("id", ""),
            family_name=family,
            given_name=given,
            gender=resource.get("gender", "unknown"),
            birth_date=birth_date,
        )

    @staticmethod
    def _parse_medication(resource: dict) -> Medication:
        """Parse a FHIR MedicationRequest resource into a domain Medication object."""
        concept = resource.get("medicationCodeableConcept", {})
        codings = concept.get("coding", [{}])
        coding = codings[0] if codings else {}

        dosage_instructions = resource.get("dosageInstruction", [])
        dosage_text = dosage_instructions[0].get("text") if dosage_instructions else None

        return Medication(
            id=resource.get("id", ""),
            code=coding.get("code", ""),
            display=concept.get("text") or coding.get("display", ""),
            status=resource.get("status", ""),
            authored_on=FHIRClient._parse_date(resource.get("authoredOn")),
            dosage_text=dosage_text,
        )

    @staticmethod
    def _parse_allergy(resource: dict) -> Allergy:
        """Parse a FHIR AllergyIntolerance resource into a domain Allergy object."""
        code_concept = resource.get("code", {})
        codings = code_concept.get("coding", [{}])
        coding = codings[0] if codings else {}

        return Allergy(
            id=resource.get("id", ""),
            code=coding.get("code", ""),
            display=code_concept.get("text") or coding.get("display", ""),
            criticality=resource.get("criticality", "unable-to-assess"),
            category=resource.get("category", []),
            recorded_date=FHIRClient._parse_date(resource.get("recordedDate")),
        )

    @staticmethod
    def _parse_condition(resource: dict) -> Condition:
        """Parse a FHIR Condition resource into a domain Condition object."""
        code_concept = resource.get("code", {})
        codings = code_concept.get("coding", [{}])
        coding = codings[0] if codings else {}

        clinical_status_codings = (
            resource.get("clinicalStatus", {}).get("coding", [{}])
        )
        clinical_status = (
            clinical_status_codings[0].get("code", "unknown")
            if clinical_status_codings else "unknown"
        )

        return Condition(
            id=resource.get("id", ""),
            code=coding.get("code", ""),
            display=code_concept.get("text") or coding.get("display", ""),
            clinical_status=clinical_status,
            onset_date=FHIRClient._parse_date(resource.get("onsetDateTime")),
            abatement_date=FHIRClient._parse_date(resource.get("abatementDateTime")),
            recorded_date=FHIRClient._parse_date(resource.get("recordedDate")),
        )
