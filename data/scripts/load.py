#!/usr/bin/env python3
"""
load.py — Load Synthea FHIR transaction bundles into fhir-service.

Data flows through fhir-service, never directly to the database.
fhir-service handles parsing, validation, reference resolution, search
index population, and version tracking. Neon (or H2) is an implementation
detail that this script never addresses.

Works identically against:
  - Local fhir-service with H2 (no API key needed)
  - Deployed fhir-service behind Kong on Neon (API key required)

Environment variables:
  FHIR_BASE_URL   Base URL of the FHIR server, e.g. http://localhost:8080/fhir
                  For the deployed stack: http://<kong-ip>:8000/fhir
  FHIR_API_KEY    API key for Kong authentication. Omit for local H2.

Usage:
  # Local
  FHIR_BASE_URL=http://localhost:8080/fhir python3 data/scripts/load.py

  # Deployed (Neon via Kong)
  FHIR_BASE_URL=http://<kong-ip>:8000/fhir \\
  FHIR_API_KEY=<your-key> \\
  python3 data/scripts/load.py

  # Custom bundle directory
  FHIR_BASE_URL=http://localhost:8080/fhir \\
  BUNDLE_DIR=data/sample/fhir \\
  python3 data/scripts/load.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

def get_config() -> tuple[str, str | None, Path]:
    """Read and validate configuration from environment variables."""
    base_url = os.environ.get("FHIR_BASE_URL", "").rstrip("/")
    if not base_url:
        print("ERROR: FHIR_BASE_URL is not set.", file=sys.stderr)
        print("  Example: FHIR_BASE_URL=http://localhost:8080/fhir python3 data/scripts/load.py",
              file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("FHIR_API_KEY") or None  # None means local — no auth header

    repo_root = Path(__file__).parent.parent.parent
    default_bundle_dir = repo_root / "data" / "sample" / "fhir"
    bundle_dir = Path(os.environ.get("BUNDLE_DIR", str(default_bundle_dir)))

    return base_url, api_key, bundle_dir


# ─────────────────────────────────────────────────────────────────────────────
# Bundle validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_bundle(data: dict, path: Path) -> str | None:
    """
    Check that a JSON file is a FHIR transaction bundle before POSTing it.
    Returns an error message if invalid, None if valid.
    """
    if not isinstance(data, dict):
        return "not a JSON object"
    if data.get("resourceType") != "Bundle":
        return f"resourceType is '{data.get('resourceType')}', expected 'Bundle'"
    bundle_type = data.get("type", "")
    if bundle_type != "transaction":
        return (
            f"bundle type is '{bundle_type}', expected 'transaction'. "
            "Check synthea.properties: exporter.fhir.transaction_bundle must be true."
        )
    if not data.get("entry"):
        return "bundle has no entries"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────────────────────────

def post_bundle(base_url: str, api_key: str | None, bundle: dict) -> tuple[int, dict]:
    """
    POST a FHIR transaction bundle to the server base URL.
    Returns (status_code, response_body).
    Raises urllib.error.HTTPError on 4xx/5xx.
    """
    url = base_url  # transaction bundles POST to the base URL, not a resource endpoint
    headers = {
        "Content-Type": "application/fhir+json",
        "Accept":        "application/fhir+json",
    }
    if api_key:
        headers["apikey"] = api_key

    data = json.dumps(bundle).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return resp.status, body


def check_server(base_url: str, api_key: str | None) -> None:
    """Verify the server is reachable before attempting to load data."""
    metadata_url = base_url + "/metadata"
    headers = {"Accept": "application/fhir+json"}
    if api_key:
        headers["apikey"] = api_key

    req = urllib.request.Request(metadata_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("resourceType") != "CapabilityStatement":
                print("WARNING: Server responded but did not return a CapabilityStatement.")
                print(f"  Response: {json.dumps(body)[:200]}")
    except urllib.error.HTTPError as e:
        print(f"ERROR: Server returned HTTP {e.code} for GET {metadata_url}", file=sys.stderr)
        if e.code == 401:
            print("  Check FHIR_API_KEY.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Cannot reach {metadata_url}: {e.reason}", file=sys.stderr)
        print("  Is fhir-service running? Check FHIR_BASE_URL.", file=sys.stderr)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Response parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_transaction_response(response_body: dict) -> tuple[int, int, list[str]]:
    """
    Parse a FHIR transaction-response bundle.
    Returns (success_count, failure_count, error_messages).
    """
    successes = 0
    failures = 0
    errors = []

    for entry in response_body.get("entry", []):
        status_str = entry.get("response", {}).get("status", "")
        # Status is a string like "201 Created" or "200 OK"
        try:
            code = int(status_str.split()[0])
        except (ValueError, IndexError):
            code = 0

        if 200 <= code < 300:
            successes += 1
        else:
            failures += 1
            location = entry.get("response", {}).get("location", "unknown")
            errors.append(f"  {status_str} — {location}")

    return successes, failures, errors


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    base_url, api_key, bundle_dir = get_config()

    print("FHIR data loader")
    print(f"  Server     : {base_url}")
    print(f"  Auth       : {'API key set' if api_key else 'none (local)'}")
    print(f"  Bundle dir : {bundle_dir}")
    print()

    # ── Verify bundle directory exists ────────────────────────────────────────
    if not bundle_dir.exists():
        print(f"ERROR: Bundle directory not found: {bundle_dir}", file=sys.stderr)
        print("  Run one of:", file=sys.stderr)
        print("    ./data/scripts/generate.sh -p 100", file=sys.stderr)
        print("    ./data/scripts/download_sample.sh", file=sys.stderr)
        sys.exit(1)

    bundle_files = sorted(bundle_dir.glob("*.json"))
    if not bundle_files:
        print(f"ERROR: No *.json files found in {bundle_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(bundle_files)} bundle file(s).")
    print()

    # ── Verify server is reachable ────────────────────────────────────────────
    print("Checking server ...")
    check_server(base_url, api_key)
    print("  Server is reachable.")
    print()

    # ── Load bundles ──────────────────────────────────────────────────────────
    total_bundles   = len(bundle_files)
    loaded_bundles  = 0
    failed_bundles  = 0
    skipped_bundles = 0
    total_resources = 0
    total_failures  = 0

    for i, bundle_path in enumerate(bundle_files, 1):
        prefix = f"[{i:>{len(str(total_bundles))}}/{total_bundles}]"

        # Read and parse
        try:
            with open(bundle_path, encoding="utf-8") as f:
                bundle_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"{prefix} SKIP  {bundle_path.name} — invalid JSON: {e}")
            skipped_bundles += 1
            continue

        # Validate bundle type before sending
        error = validate_bundle(bundle_data, bundle_path)
        if error:
            print(f"{prefix} SKIP  {bundle_path.name} — {error}")
            skipped_bundles += 1
            continue

        entry_count = len(bundle_data.get("entry", []))

        # POST to fhir-service
        try:
            status_code, response_body = post_bundle(base_url, api_key, bundle_data)
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8", errors="replace"))
                detail = err_body.get("issue", [{}])[0].get("diagnostics", str(e))
            except Exception:
                detail = str(e)
            print(f"{prefix} FAIL  {bundle_path.name} — HTTP {e.code}: {detail[:120]}")
            failed_bundles += 1
            continue
        except urllib.error.URLError as e:
            print(f"{prefix} FAIL  {bundle_path.name} — connection error: {e.reason}")
            failed_bundles += 1
            continue

        # Parse transaction response
        successes, failures, err_msgs = parse_transaction_response(response_body)
        total_resources += successes
        total_failures  += failures

        if failures == 0:
            print(f"{prefix} OK    {bundle_path.name} — {successes}/{entry_count} resources")
            loaded_bundles += 1
        else:
            print(f"{prefix} WARN  {bundle_path.name} — {successes} ok, {failures} failed")
            for msg in err_msgs[:3]:  # show first 3 failures to avoid flooding output
                print(f"         {msg}")
            if len(err_msgs) > 3:
                print(f"         ... and {len(err_msgs) - 3} more")
            loaded_bundles += 1  # bundle was accepted even if some entries failed

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("─" * 60)
    print(f"  Bundles   : {loaded_bundles} loaded, {failed_bundles} failed, {skipped_bundles} skipped")
    print(f"  Resources : {total_resources} created")
    if total_failures:
        print(f"  Warnings  : {total_failures} resource-level failures (see above)")
    print("─" * 60)

    if failed_bundles > 0 or skipped_bundles > 0:
        print()
        print("Some bundles were not loaded. Check output above for details.")
        sys.exit(1)

    print()
    print("Verify the load:")
    print(f"  curl -s '{base_url}/Patient?_summary=count'")
    print(f"  curl -s '{base_url}/MedicationRequest?_summary=count'")
    print(f"  curl -s '{base_url}/AllergyIntolerance?_summary=count'")


if __name__ == "__main__":
    main()
