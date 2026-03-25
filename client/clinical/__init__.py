# Makes client/clinical/ a Python package.
#
# With this file present, FHIRClient is importable from the repo root without
# sys.path manipulation:
#
#   from client.clinical.fhir_client import FHIRClient
#
# Phase 2: this package will be converted to a proper installable distribution
# (pyproject.toml + pip install -e client/clinical/) so the MCP agent can import
# FHIRClient without depending on the repo layout.
