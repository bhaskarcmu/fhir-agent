"""
fhir-clinical-client
====================
Domain-abstracted FHIR client for clinical application developers.

    from fhir_clinical_client import FHIRClient, Patient
    from fhir_clinical_client import AuthenticationError, NotFoundError, FHIRClientError
"""

from .fhir_client import (
    FHIRClient,
    Patient,
    FHIRClientError,
    AuthenticationError,
    NotFoundError,
)

__all__ = [
    "FHIRClient",
    "Patient",
    "FHIRClientError",
    "AuthenticationError",
    "NotFoundError",
]
__version__ = "0.1.0"
