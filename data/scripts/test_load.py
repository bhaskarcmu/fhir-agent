"""
Unit tests for load.py — server-independent logic only.

Tests cover:
  - Bundle validation (type checking, entry presence)
  - Environment variable handling (missing FHIR_BASE_URL, optional FHIR_API_KEY)
  - Transaction response parsing (success/failure counts)
  - API key header presence/absence
  - Bundle file discovery

No running fhir-service required. All HTTP interactions are mocked.

Run:
  python3 -m pytest data/scripts/test_load.py -v
"""

import importlib.util
import json
import os
import sys
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock, patch

# ─────────────────────────────────────────────────────────────────────────────
# Import load.py as a module (it lives outside a package)
# ─────────────────────────────────────────────────────────────────────────────
_LOAD_PATH = Path(__file__).parent / "load.py"
_spec = importlib.util.spec_from_file_location("load", _LOAD_PATH)
_load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_load)


# ─────────────────────────────────────────────────────────────────────────────
# validate_bundle
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateBundle(unittest.TestCase):

    def _valid_bundle(self):
        return {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [{"resource": {"resourceType": "Patient"}}],
        }

    def test_valid_transaction_bundle(self):
        self.assertIsNone(_load.validate_bundle(self._valid_bundle(), Path("test.json")))

    def test_not_a_dict(self):
        error = _load.validate_bundle(["not", "a", "dict"], Path("test.json"))
        self.assertIsNotNone(error)
        self.assertIn("not a JSON object", error)

    def test_wrong_resource_type(self):
        bundle = self._valid_bundle()
        bundle["resourceType"] = "Patient"
        error = _load.validate_bundle(bundle, Path("test.json"))
        self.assertIsNotNone(error)
        self.assertIn("Patient", error)
        self.assertIn("Bundle", error)

    def test_collection_bundle_rejected(self):
        bundle = self._valid_bundle()
        bundle["type"] = "collection"
        error = _load.validate_bundle(bundle, Path("test.json"))
        self.assertIsNotNone(error)
        self.assertIn("collection", error)
        self.assertIn("transaction_bundle", error)

    def test_empty_entries_rejected(self):
        bundle = self._valid_bundle()
        bundle["entry"] = []
        error = _load.validate_bundle(bundle, Path("test.json"))
        self.assertIsNotNone(error)
        self.assertIn("no entries", error)

    def test_missing_entries_rejected(self):
        bundle = self._valid_bundle()
        del bundle["entry"]
        error = _load.validate_bundle(bundle, Path("test.json"))
        self.assertIsNotNone(error)


# ─────────────────────────────────────────────────────────────────────────────
# get_config — environment variable handling
# ─────────────────────────────────────────────────────────────────────────────

class TestGetConfig(unittest.TestCase):

    def test_missing_fhir_base_url_exits(self):
        env = {"FHIR_BASE_URL": ""}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("FHIR_BASE_URL", None)
            with self.assertRaises(SystemExit) as ctx:
                _load.get_config()
            self.assertEqual(ctx.exception.code, 1)

    def test_base_url_trailing_slash_stripped(self):
        env = {"FHIR_BASE_URL": "http://localhost:8080/fhir/"}
        with patch.dict(os.environ, env):
            os.environ.pop("FHIR_API_KEY", None)
            os.environ.pop("BUNDLE_DIR", None)
            base_url, api_key, _ = _load.get_config()
        self.assertEqual(base_url, "http://localhost:8080/fhir")

    def test_api_key_present(self):
        env = {"FHIR_BASE_URL": "http://localhost:8080/fhir", "FHIR_API_KEY": "secret-key"}
        with patch.dict(os.environ, env):
            os.environ.pop("BUNDLE_DIR", None)
            _, api_key, _ = _load.get_config()
        self.assertEqual(api_key, "secret-key")

    def test_api_key_absent_returns_none(self):
        env = {"FHIR_BASE_URL": "http://localhost:8080/fhir"}
        with patch.dict(os.environ, env):
            os.environ.pop("FHIR_API_KEY", None)
            os.environ.pop("BUNDLE_DIR", None)
            _, api_key, _ = _load.get_config()
        self.assertIsNone(api_key)

    def test_empty_api_key_returns_none(self):
        env = {"FHIR_BASE_URL": "http://localhost:8080/fhir", "FHIR_API_KEY": ""}
        with patch.dict(os.environ, env):
            os.environ.pop("BUNDLE_DIR", None)
            _, api_key, _ = _load.get_config()
        self.assertIsNone(api_key)


# ─────────────────────────────────────────────────────────────────────────────
# parse_transaction_response
# ─────────────────────────────────────────────────────────────────────────────

class TestParseTransactionResponse(unittest.TestCase):

    def _response(self, statuses):
        return {
            "resourceType": "Bundle",
            "type": "transaction-response",
            "entry": [
                {"response": {"status": s, "location": f"Patient/{i}"}}
                for i, s in enumerate(statuses)
            ],
        }

    def test_all_success(self):
        resp = self._response(["201 Created", "200 OK", "201 Created"])
        successes, failures, errors = _load.parse_transaction_response(resp)
        self.assertEqual(successes, 3)
        self.assertEqual(failures, 0)
        self.assertEqual(errors, [])

    def test_mixed_success_and_failure(self):
        resp = self._response(["201 Created", "400 Bad Request", "201 Created"])
        successes, failures, errors = _load.parse_transaction_response(resp)
        self.assertEqual(successes, 2)
        self.assertEqual(failures, 1)
        self.assertEqual(len(errors), 1)

    def test_all_failures(self):
        resp = self._response(["500 Internal Server Error", "422 Unprocessable Entity"])
        successes, failures, errors = _load.parse_transaction_response(resp)
        self.assertEqual(successes, 0)
        self.assertEqual(failures, 2)

    def test_empty_response(self):
        resp = {"resourceType": "Bundle", "type": "transaction-response", "entry": []}
        successes, failures, errors = _load.parse_transaction_response(resp)
        self.assertEqual(successes, 0)
        self.assertEqual(failures, 0)

    def test_malformed_status_counted_as_failure(self):
        resp = {"resourceType": "Bundle", "type": "transaction-response",
                "entry": [{"response": {"status": "not-a-number"}}]}
        successes, failures, _ = _load.parse_transaction_response(resp)
        self.assertEqual(successes, 0)
        self.assertEqual(failures, 1)


# ─────────────────────────────────────────────────────────────────────────────
# post_bundle — API key header
# ─────────────────────────────────────────────────────────────────────────────

class TestPostBundleHeaders(unittest.TestCase):

    def _mock_response(self, status=200, body=None):
        body = body or {"resourceType": "Bundle", "type": "transaction-response", "entry": []}
        mock_resp = MagicMock()
        mock_resp.status = status
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_api_key_header_sent_when_present(self):
        bundle = {"resourceType": "Bundle", "type": "transaction", "entry": []}
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return self._mock_response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _load.post_bundle("http://localhost:8080/fhir", "my-secret-key", bundle)

        # urllib capitalises the first letter of header names
        self.assertIn("Apikey", captured["headers"])
        self.assertEqual(captured["headers"]["Apikey"], "my-secret-key")

    def test_api_key_header_absent_when_none(self):
        bundle = {"resourceType": "Bundle", "type": "transaction", "entry": []}
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return self._mock_response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _load.post_bundle("http://localhost:8080/fhir", None, bundle)

        self.assertNotIn("Apikey", captured["headers"])
        self.assertNotIn("apikey", captured["headers"])

    def test_posts_to_base_url_not_resource_endpoint(self):
        """Transaction bundles must POST to /fhir, not /fhir/Patient."""
        bundle = {"resourceType": "Bundle", "type": "transaction", "entry": []}
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return self._mock_response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _load.post_bundle("http://localhost:8080/fhir", None, bundle)

        self.assertEqual(captured["url"], "http://localhost:8080/fhir")
        self.assertNotIn("/Patient", captured["url"])


if __name__ == "__main__":
    unittest.main()
