# e2e/fixtures

## `epic_emulator_test_client_private_key.pem` / `epic_emulator_test_client_public_jwk.json`

A **fixed, throwaway RSA keypair**, generated solely for
[`e2e/test_epic_emulator_acceptance.py`](../test_epic_emulator_acceptance.py) (Phase 4 M5). It has
no access to anything real:

- It authenticates against `epic-emulator`'s *emulated* SMART Backend Services flow only —
  `epic-emulator` is a local dev/test proxy, never a production system, and never holds real PHI.
- The public JWK is what a developer registers with `epic-emulator` at startup (config-only
  registration, decision E8) to make the e2e test reproducible without generating a new keypair
  and re-registering it by hand every run.
- Committing this keypair is intentional — it's allowlisted in [`.gitleaks.toml`](../../.gitleaks.toml)
  for exactly this reason, not an oversight to fix. Standard practice for a checked-in test
  fixture (comparable to the test TLS certs many projects commit for local/e2e-only use), not a
  production credential.

If you ever need a different test client, regenerate both files (see the header of
`test_epic_emulator_acceptance.py`) — nothing else depends on this exact keypair's value, only its
existence and internal consistency (the public JWK must match the private key).
