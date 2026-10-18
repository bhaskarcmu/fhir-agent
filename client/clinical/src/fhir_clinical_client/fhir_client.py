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
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import date, datetime
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


# Care history (Phase 8): what a risk model reads about a patient's past use of care.
# Times are datetimes because stays are counted in nights; they keep the source's time zone.

@dataclass
class Demographics:
    """
    The demographic facts a population-health model needs about a patient.

    Derived from a FHIR Patient resource. `race` and `ethnicity` come from the US Core
    race and ethnicity extensions (category names, e.g. "White", "Hispanic or Latino").
    """
    patient_id: str
    gender: str                             # "male", "female", "other", "unknown"
    birth_date: Optional[date] = None
    deceased: bool = False
    deceased_date: Optional[date] = None    # None if alive, or if only "deceased: yes" is recorded
    state: Optional[str] = None             # As recorded, usually a US postal code ("AZ")
    postal_code: Optional[str] = None
    race: list[str] = field(default_factory=list)
    ethnicity: Optional[str] = None
    external_ids: list[str] = field(default_factory=list)   # Identifiers from source systems (e.g. an MRN)


@dataclass
class Encounter:
    """
    One contact with the health system: a visit, an emergency-room attendance, a hospital stay.

    `setting` is one of "ambulatory", "emergency", "inpatient", "home_health", "virtual",
    "short_stay", "observation" or "other". A record's own type (e.g. "Well child visit")
    is kept in `type_display`, because settings are broad.
    """
    id: str
    setting: str
    status: str                             # "finished", "in-progress", ...
    start: Optional[datetime] = None
    end: Optional[datetime] = None          # None while the encounter is still open
    type_code: str = ""                     # SNOMED CT, e.g. "185345009"
    type_display: str = ""
    admitted_from_emergency: Optional[bool] = None   # Hospital stays only; None if not recorded
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class Prescription:
    """
    A prescription (medication order) in the patient's history, current or past.

    Derived from a FHIR MedicationRequest. Unlike get_medications(), the history includes
    stopped and completed prescriptions. Refill and supply details are often not recorded.
    """
    id: str
    code: str                               # RxNorm code
    display: str
    status: str                             # "active", "stopped", "completed", ...
    authored_on: Optional[datetime] = None
    valid_from: Optional[date] = None       # The period the prescription may be dispensed in
    valid_until: Optional[date] = None
    refills_allowed: Optional[int] = None
    supply_days: Optional[float] = None     # Expected days of supply per fill
    quantity: Optional[float] = None        # Quantity per fill
    encounter_id: Optional[str] = None      # The encounter it was written in


@dataclass
class Dispense:
    """A medication handed to the patient by a pharmacy (a fill or refill)."""
    id: str
    code: str                               # RxNorm code
    display: str
    status: str                             # "completed", ...
    dispensed_at: Optional[datetime] = None
    quantity: Optional[float] = None
    supply_days: Optional[float] = None
    prescription_id: Optional[str] = None


@dataclass
class CareCost:
    """
    The cost of one billed episode of care, from the payer's explanation of benefit.

    `category` is "professional", "institutional", "pharmacy", "oral" or "vision". Amounts
    are in the claim's currency: `billed` is what was submitted, `paid` what the payer paid.
    """
    id: str
    category: str
    service_start: Optional[datetime] = None
    service_end: Optional[datetime] = None
    billed: Optional[float] = None
    paid: Optional[float] = None
    currency: Optional[str] = None
    payer: Optional[str] = None             # e.g. "Medicare", or an insurer's name
    encounter_ids: list[str] = field(default_factory=list)
    medication_codes: list[str] = field(default_factory=list)   # RxNorm codes billed (pharmacy)


@dataclass
class InsuranceCoverage:
    """A period of insurance cover for the patient."""
    id: str
    payer: Optional[str] = None
    plan_type: Optional[str] = None         # e.g. "Medicaid", "PPO"
    status: str = ""
    start: Optional[date] = None
    end: Optional[date] = None              # None if open-ended


NO_CACHE = {"Cache-Control": "no-cache"}     # care-history searches: never a cached result


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

    SEARCH_PAGE_SIZE = 100      # results per page for the care-history methods, which read every page

    def __init__(self, gateway_url: str, api_key: Optional[str] = None):
        """
        Args:
            gateway_url: Base URL of the Kong gateway. Both forms are accepted:
                         "http://localhost:8000"       (without /fhir)
                         "http://localhost:8000/fhir"  (with /fhir)
                         The client normalises either form internally.
            api_key:     Optional API key issued by the platform team via
                         create-key.sh. When omitted, the client uses a local-dev
                         fallback without authentication headers.

        Raises:
            ValueError if gateway_url is empty.
        """
        if not gateway_url or not gateway_url.strip():
            raise ValueError(
                "gateway_url is required. Set FHIR_GATEWAY_URL to the Kong proxy URL."
            )
        # Normalise: strip trailing /fhir if present, then append it once.
        # This means FHIR_GATEWAY_URL=http://host:8000 and
        # FHIR_GATEWAY_URL=http://host:8000/fhir both work correctly.
        base = gateway_url.rstrip("/")
        if base.endswith("/fhir"):
            base = base[: -len("/fhir")]
        self._base = base + "/fhir"
        self._api_key = api_key.strip() if api_key and api_key.strip() else None

    # -----------------------------------------------------------------------
    # Internal HTTP helper
    # -----------------------------------------------------------------------

    def _request(self, path: str, method: str = "GET", body: dict = None,
                 headers: Optional[dict] = None) -> tuple[int, dict]:
        """Send an authenticated FHIR request. Returns (status_code, parsed_body).
        `headers` adds request headers (the care-history searches send Cache-Control)."""
        url = f"{self._base}{path}"
        headers = {
            "Content-Type": "application/fhir+json",
            "Accept":       "application/fhir+json",
            **(headers or {}),
        }
        if self._api_key:
            headers["apikey"] = self._api_key
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

    def search_patients(self, name: str) -> list[Patient]:
        """
        Search for patients by name (partial match).

        Uses FHIR's name search parameter, which matches against any part
        of the patient's name (family, given, prefix, suffix). Case-insensitive
        on most FHIR servers including HAPI.

        Args:
            name: Full or partial patient name, e.g. "Kristle" or "Mraz".

        Returns:
            List of matching Patient objects. Empty list if no match.
            If multiple patients match, all are returned — the caller
            (or the agent) decides which one to use.

        Raises:
            FHIRClientError on server errors.
        """
        # HAPI FHIR does not support multi-token name search in a single
        # name= parameter. Split on whitespace and issue one name= per token;
        # HAPI ANDs multiple name= parameters, matching all tokens.
        tokens = name.strip().split()
        name_params = "&".join(f"name={t}" for t in tokens)
        status, body = self._request(f"/Patient?{name_params}&_count=20")
        if status != 200:
            raise FHIRClientError(
                f"Patient search failed (got {status}).", status, body
            )
        return [
            self._parse_patient(entry["resource"])
            for entry in body.get("entry", [])
            if entry.get("resource", {}).get("resourceType") == "Patient"
        ]

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
    # Care history (Phase 8) — complete histories, so every page is read
    # -----------------------------------------------------------------------

    def get_demographics(self, patient_id: str) -> Demographics:
        """
        Return the patient's demographics: gender, birth and death dates, state, race,
        ethnicity and source-system identifiers.

        Raises:
            NotFoundError if the patient does not exist.
            FHIRClientError on other failures.
        """
        status, body = self._request(f"/Patient/{patient_id}")
        if status != 200:
            raise FHIRClientError(
                f"Failed to retrieve patient {patient_id} (got {status}).", status, body
            )
        return self._parse_demographics(body)

    def get_encounters(self, patient_id: str, since: Optional[date] = None) -> list[Encounter]:
        """
        Return the patient's encounters — visits, emergency attendances, hospital stays.

        Args:
            patient_id: The patient's ID.
            since:      If given, only encounters on or after this date.

        Returns:
            Every matching encounter (all pages), in the server's order.
        """
        query = {"patient": patient_id}
        if since:
            query["date"] = f"ge{since.isoformat()}"
        return [self._parse_encounter(r) for r in self._search_all("Encounter", query)]

    def get_medication_history(self, patient_id: str) -> list[Prescription]:
        """
        Return every prescription in the patient's history, whatever its status
        (active, stopped, completed, ...). get_medications() is unchanged: active only.

        A prescription may name its medicine by reference to a separate record (common for
        medicines given in hospital); those records are fetched with the search.
        """
        medicines: dict = {}
        found = self._search_all("MedicationRequest",
                                 {"patient": patient_id, "_include": "MedicationRequest:medication"},
                                 included=medicines)
        return [self._parse_prescription(r, medicines) for r in found]

    def get_condition_history(self, patient_id: str) -> list[Condition]:
        """
        Return every condition in the patient's history (all pages). get_conditions() is
        unchanged and returns at most the first 100.
        """
        return [
            self._parse_condition(r)
            for r in self._search_all("Condition", {"patient": patient_id})
        ]

    def get_medication_dispenses(self, patient_id: str) -> list[Dispense]:
        """
        Return the medications pharmacies have handed to the patient (fills and refills).
        Many systems don't record dispenses; then the list is empty.
        """
        return [
            self._parse_dispense(r)
            for r in self._search_all("MedicationDispense", {"patient": patient_id})
        ]

    def get_care_costs(self, patient_id: str, since: Optional[date] = None) -> list[CareCost]:
        """
        Return the billed cost of the patient's care, one entry per claim.

        Args:
            patient_id: The patient's ID.
            since:      If given, only claims processed on or after this date.
        """
        query = {"patient": patient_id}
        if since:
            query["created"] = f"ge{since.isoformat()}"
        return [
            self._parse_care_cost(r)
            for r in self._search_all("ExplanationOfBenefit", query)
        ]

    def get_coverage(self, patient_id: str) -> list[InsuranceCoverage]:
        """
        Return the patient's recorded insurance cover. Some systems record cover only on
        claims; then this list is empty and get_care_costs() carries the payer.
        """
        return [
            self._parse_coverage(r)
            for r in self._search_all("Coverage", {"patient": patient_id})
        ]

    def _search_all(self, resource_type: str, query: dict, max_pages: int = 200,
                    included: Optional[dict] = None) -> list[dict]:
        """Run a search and follow every 'next' page; return the matching resources.

        Servers write 'next' links with their own host, which may not be reachable through
        the gateway, so only the link's query string is replayed against this client's base.
        Resources the search `_include`s are put in `included`, keyed "Type/id".

        Every page asks the server not to answer from a cache: HAPI reuses a search's results for
        about a minute, so a record written just before would be missing (found in Phase 8 M12).
        """
        path = f"/{resource_type}?" + urllib.parse.urlencode({**query, "_count": self.SEARCH_PAGE_SIZE})
        resources = []
        for _ in range(max_pages):
            status, body = self._request(path, headers=NO_CACHE)
            if status != 200:
                raise FHIRClientError(
                    f"{resource_type} search failed (got {status}).", status, body
                )
            resources += [
                entry["resource"] for entry in body.get("entry", [])
                if entry.get("resource", {}).get("resourceType") == resource_type
            ]
            if included is not None:
                for entry in body.get("entry", []):
                    r = entry.get("resource", {})
                    if r.get("resourceType") and r.get("resourceType") != resource_type:
                        included[f"{r['resourceType']}/{r.get('id', '')}"] = r
            next_url = next(
                (link.get("url") for link in body.get("link", []) if link.get("relation") == "next"),
                None,
            )
            if not next_url:
                return resources
            path = "?" + urllib.parse.urlsplit(next_url).query
        raise FHIRClientError(f"{resource_type} search exceeded {max_pages} pages.")

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

    # -- care history (Phase 8) ---------------------------------------------

    _US_CORE_RACE = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race"
    _US_CORE_ETHNICITY = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity"
    _ENCOUNTER_SETTINGS = {
        "AMB": "ambulatory", "EMER": "emergency", "IMP": "inpatient", "ACUTE": "inpatient",
        "NONAC": "inpatient", "HH": "home_health", "VR": "virtual", "SS": "short_stay",
        "OBSENC": "observation",
    }
    _INPATIENT_SETTINGS = ("inpatient", "short_stay", "observation")

    @staticmethod
    def _parse_datetime(raw: str | None) -> Optional[datetime]:
        """Parse an ISO 8601 date or datetime. Returns None on failure. Keeps any time zone."""
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _ref_id(ref: dict | None) -> Optional[str]:
        """'Encounter/163' or 'urn:uuid:abc' -> '163' / 'abc'."""
        raw = (ref or {}).get("reference")
        if not raw:
            return None
        return raw.split("/")[-1].removeprefix("urn:uuid:")

    @staticmethod
    def _first_coding(concept: dict | None) -> dict:
        codings = (concept or {}).get("coding") or [{}]
        return codings[0]

    @staticmethod
    def _duration_days(duration: dict | None) -> Optional[float]:
        """A FHIR Duration in days (supply durations are recorded in d, wk or mo)."""
        if not duration or duration.get("value") is None:
            return None
        per_day = {"d": 1, "day": 1, "days": 1, "wk": 7, "mo": 30, "a": 365, "h": 1 / 24}
        unit = duration.get("code") or duration.get("unit") or "d"
        return float(duration["value"]) * per_day[unit] if unit in per_day else None

    @staticmethod
    def _parse_demographics(resource: dict) -> Demographics:
        def us_core(url: str) -> list[str]:
            for ext in resource.get("extension", []):
                if ext.get("url") == url:
                    names = [sub["valueCoding"].get("display", "") for sub in ext.get("extension", [])
                             if sub.get("url") == "ombCategory" and "valueCoding" in sub]
                    text = [sub.get("valueString") for sub in ext.get("extension", [])
                            if sub.get("url") == "text" and sub.get("valueString")]
                    return names or text
            return []

        address = (resource.get("address") or [{}])[0]
        deceased_date = FHIRClient._parse_date(resource.get("deceasedDateTime"))
        ethnicity = us_core(FHIRClient._US_CORE_ETHNICITY)
        return Demographics(
            patient_id=resource.get("id", ""),
            gender=resource.get("gender", "unknown"),
            birth_date=FHIRClient._parse_date(resource.get("birthDate")),
            deceased=bool(resource.get("deceasedBoolean")) or deceased_date is not None,
            deceased_date=deceased_date,
            state=address.get("state"),
            postal_code=address.get("postalCode"),
            race=us_core(FHIRClient._US_CORE_RACE),
            ethnicity=ethnicity[0] if ethnicity else None,
            external_ids=[i["value"] for i in resource.get("identifier", []) if i.get("value")],
        )

    @staticmethod
    def _parse_encounter(resource: dict) -> Encounter:
        setting = FHIRClient._ENCOUNTER_SETTINGS.get(
            (resource.get("class") or {}).get("code", ""), "other"
        )
        type_concept = (resource.get("type") or [{}])[0]
        type_coding = FHIRClient._first_coding(type_concept)
        admitted_from_emergency = None
        admit_source = (resource.get("hospitalization") or {}).get("admitSource")
        if setting in FHIRClient._INPATIENT_SETTINGS and admit_source:
            admitted_from_emergency = FHIRClient._first_coding(admit_source).get("code") == "emd"
        period = resource.get("period") or {}
        return Encounter(
            id=resource.get("id", ""),
            setting=setting,
            status=resource.get("status", ""),
            start=FHIRClient._parse_datetime(period.get("start")),
            end=FHIRClient._parse_datetime(period.get("end")),
            type_code=type_coding.get("code", ""),
            type_display=type_concept.get("text") or type_coding.get("display", ""),
            admitted_from_emergency=admitted_from_emergency,
            reason_codes=[FHIRClient._first_coding(c).get("code", "")
                          for c in resource.get("reasonCode", []) if FHIRClient._first_coding(c).get("code")],
        )

    @staticmethod
    def _parse_prescription(resource: dict, medicines: Optional[dict] = None) -> Prescription:
        concept = resource.get("medicationCodeableConcept")
        if concept is None:                       # named by reference to a Medication record
            ref = (resource.get("medicationReference") or {}).get("reference", "")
            concept = ((medicines or {}).get(ref) or {}).get("code") or {}
        coding = FHIRClient._first_coding(concept)
        dispense = resource.get("dispenseRequest") or {}
        validity = dispense.get("validityPeriod") or {}
        quantity = (dispense.get("quantity") or {}).get("value")
        return Prescription(
            id=resource.get("id", ""),
            code=coding.get("code", ""),
            display=concept.get("text") or coding.get("display", ""),
            status=resource.get("status", ""),
            authored_on=FHIRClient._parse_datetime(resource.get("authoredOn")),
            valid_from=FHIRClient._parse_date(validity.get("start")),
            valid_until=FHIRClient._parse_date(validity.get("end")),
            refills_allowed=dispense.get("numberOfRepeatsAllowed"),
            supply_days=FHIRClient._duration_days(dispense.get("expectedSupplyDuration")),
            quantity=float(quantity) if quantity is not None else None,
            encounter_id=FHIRClient._ref_id(resource.get("encounter")),
        )

    @staticmethod
    def _parse_dispense(resource: dict) -> Dispense:
        concept = resource.get("medicationCodeableConcept") or {}
        coding = FHIRClient._first_coding(concept)
        quantity = (resource.get("quantity") or {}).get("value")
        prescriptions = resource.get("authorizingPrescription") or []
        return Dispense(
            id=resource.get("id", ""),
            code=coding.get("code", ""),
            display=concept.get("text") or coding.get("display", ""),
            status=resource.get("status", ""),
            dispensed_at=FHIRClient._parse_datetime(
                resource.get("whenHandedOver") or resource.get("whenPrepared")),
            quantity=float(quantity) if quantity is not None else None,
            supply_days=FHIRClient._duration_days(resource.get("daysSupply")),
            prescription_id=FHIRClient._ref_id(prescriptions[0]) if prescriptions else None,
        )

    @staticmethod
    def _parse_care_cost(resource: dict) -> CareCost:
        def amount(category: str) -> tuple[Optional[float], Optional[str]]:
            for total in resource.get("total", []):
                if FHIRClient._first_coding(total.get("category")).get("code") == category:
                    money = total.get("amount") or {}
                    return money.get("value"), money.get("currency")
            return None, None

        items = resource.get("item", [])
        starts, ends = [], []
        for item in items:
            period = item.get("servicedPeriod") or {}
            day = item.get("servicedDate")
            starts.append(FHIRClient._parse_datetime(period.get("start") or day))
            ends.append(FHIRClient._parse_datetime(period.get("end") or day))
        starts, ends = [s for s in starts if s], [e for e in ends if e]
        if not starts:                       # no service dates on the items: the billing period
            billable = resource.get("billablePeriod") or {}
            starts = [s for s in [FHIRClient._parse_datetime(billable.get("start"))] if s]
            ends = [e for e in [FHIRClient._parse_datetime(billable.get("end"))] if e]

        payer = None
        for insurance in resource.get("insurance", []):
            if insurance.get("focal", True):
                payer = (insurance.get("coverage") or {}).get("display")
                break
        if not payer:
            payer = (resource.get("insurer") or {}).get("display")

        billed, currency = amount("submitted")
        payment = (resource.get("payment") or {}).get("amount") or {}
        encounter_ids, medication_codes = [], []
        for item in items:
            for ref in item.get("encounter", []):
                if (eid := FHIRClient._ref_id(ref)) and eid not in encounter_ids:
                    encounter_ids.append(eid)
            coding = FHIRClient._first_coding(item.get("productOrService"))
            if "rxnorm" in coding.get("system", "") and coding.get("code"):
                medication_codes.append(coding["code"])
        return CareCost(
            id=resource.get("id", ""),
            category=FHIRClient._first_coding(resource.get("type")).get("code", ""),
            service_start=min(starts) if starts else None,
            service_end=max(ends) if ends else None,
            billed=billed,
            paid=payment.get("value"),
            currency=currency or payment.get("currency"),
            payer=payer,
            encounter_ids=encounter_ids,
            medication_codes=medication_codes,
        )

    @staticmethod
    def _parse_coverage(resource: dict) -> InsuranceCoverage:
        type_concept = resource.get("type") or {}
        payors = resource.get("payor") or [{}]
        period = resource.get("period") or {}
        return InsuranceCoverage(
            id=resource.get("id", ""),
            payer=payors[0].get("display"),
            plan_type=type_concept.get("text") or FHIRClient._first_coding(type_concept).get("display"),
            status=resource.get("status", ""),
            start=FHIRClient._parse_date(period.get("start")),
            end=FHIRClient._parse_date(period.get("end")),
        )
