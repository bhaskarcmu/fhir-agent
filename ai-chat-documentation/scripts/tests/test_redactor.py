import unittest

from archive_ai.redactor import Redactor


class RedactorTest(unittest.TestCase):
    def setUp(self):
        self.r = Redactor()

    def _assert_masked(self, secret, category, keep=None):
        text = f"before {secret} after"
        out = self.r.redact(text)
        self.assertNotIn(secret, out)
        self.assertIn(f"‹redacted:{category}›", out)
        if keep:
            self.assertIn(keep, out)

    def test_anthropic_key(self):
        self._assert_masked("sk-ant-api03-ABCDEFGHIJ1234567890xyz", "anthropic-key")

    def test_github_tokens(self):
        self._assert_masked("ghp_" + "A" * 36, "github-token")
        self._assert_masked("github_pat_" + "B" * 30, "github-token")

    def test_aws_access_key(self):
        self._assert_masked("AKIAIOSFODNN7EXAMPLE", "aws-access-key")

    def test_private_key_block(self):
        block = "-----BEGIN RSA PRIVATE KEY-----\nMIIBsecret\n-----END RSA PRIVATE KEY-----"
        out = self.r.redact(block)
        self.assertNotIn("MIIBsecret", out)
        self.assertIn("‹redacted:private-key›", out)

    def test_bearer_keeps_header_prefix(self):
        out = self.r.redact("Authorization: Bearer abc.def.ghijklmnop")
        self.assertNotIn("abc.def.ghijklmnop", out)
        self.assertIn("Authorization: Bearer ", out)
        self.assertIn("‹redacted:bearer-token›", out)

    def test_url_credentials_keep_scheme_and_host(self):
        out = self.r.redact("db at postgres://user:hunter2@host:5432/db")
        self.assertNotIn("hunter2", out)
        self.assertIn("postgres://user:", out)
        self.assertIn("‹redacted:url-credentials›", out)

    def test_env_secret_keeps_key_name(self):
        out = self.r.redact("API_KEY=supersecretvalue123")
        self.assertNotIn("supersecretvalue123", out)
        self.assertTrue(out.startswith("API_KEY="))
        self.assertIn("‹redacted:env-secret›", out)

    def test_jdbc_query_password_masked(self):
        # The SPRING_DATASOURCE_URL / JDBC form: password lives in the query string,
        # so the scheme://user:pass@ url-credentials rule does not apply.
        url = "jdbc:postgresql://host/fhirdb?user=neondb_owner&password=npg_ABCdef123456&sslmode=require"
        out = self.r.redact(url)
        self.assertNotIn("npg_ABCdef123456", out)
        self.assertIn("password=", out)
        self.assertIn("sslmode=require", out)  # non-secret query params preserved

    def test_neon_token_masked_anywhere(self):
        self._assert_masked("npg_ABCdef1234567890", "neon-password")

    def test_neon_uri_form_masked(self):
        # The postgres://user:PASS@host authority form (NEON_DB_URL).
        out = self.r.redact("postgresql://neondb_owner:npg_ABCdef123456@ep-x.neon.tech/fhirdb")
        self.assertNotIn("npg_ABCdef123456", out)
        self.assertIn("postgresql://neondb_owner:", out)

    def test_counts_accumulate_and_value_never_leaks(self):
        self.r.redact("ghp_" + "A" * 36)
        self.r.redact("AKIAIOSFODNN7EXAMPLE")
        self.assertEqual(self.r.counts["github-token"], 1)
        self.assertEqual(self.r.counts["aws-access-key"], 1)

    def test_plain_text_untouched(self):
        text = "Please review gateway/kong-values.yaml for the smallest safe fix."
        self.assertEqual(self.r.redact(text), text)


if __name__ == "__main__":
    unittest.main()
