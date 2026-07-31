# Phase 4 Coupling Note (PRD G6)

Captured after building M1–M5, for Phase 5's decomposition to use as real evidence rather than
re-guessing the original three-area split named in the PRD. Verified against actual code and one
live end-to-end run (`e2e/test_epic_emulator_acceptance.py`), not asserted from the design alone.

**Auth (M2) stayed the most cleanly separable of the three.** It's a pure request gate with no
response-body access and no shared data structures with extension handling — if split into its
own service, only a yes/no token-validity check would need to cross a boundary.

**Extension handling (M3) and pagination (quirk A, M4) share a response-processing stage, not
state.** Both read and mutate the same proxied JSON body in sequence — extensions inside
resources, next-links at the `Bundle` level — inside one method (`FhirProxyController.proxy`).
They don't conflict (disjoint parts of the tree), but they do depend on a fixed application order
and a single pass over the same bytes. Split into separate services, that implicit method-call
order would need to become an explicit pipeline contract, and would add a network hop for what's
currently one in-process double-transform.

**The real, unplanned coupling: error-shape formatting (quirk C) turned out to be cross-cutting,
not scoped to "quirks."** Both the auth gate's `401` (M2) and the required-search-parameter
rejection (quirk B, M4) depend on the same `EpicOperationOutcome` helper built as part of the
quirks area. "How do I reject a request in Epic's shape" ended up needed by auth just as much as
by quirks — if decomposed, this would need to be its own shared library (or its own small
service) consumed by both, not owned by either alone, or the two areas will duplicate it and drift.

**Net evidence for Phase 5:** auth is the safest first candidate for independent decomposition.
Extension handling and pagination's shared response-processing stage argues for keeping them
together (or defining a real pipeline contract before splitting them). Error-shape formatting is
the one piece that doesn't cleanly belong to any single area — the strongest concrete signal that
the original three-way split named in the PRD was a reasonable starting guess, not a verified
boundary.
