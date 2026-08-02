-- Agent session store (docs/phase6/design.md Section 4.3, M3). Plain SQL, applied at
-- startup/test-setup -- matching rxclaim-emulator's and provider-registry-service's schema.sql
-- convention rather than introducing a migration framework for a single-table schema.
--
-- Cross-session persistence only (one of memory's three separate axes -- see design.md; the
-- other two, per-conversation token budget and concurrent-session-count scaling, are
-- context_budget.py and Phase 6 M4 respectively, not this table).

CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    messages        text NOT NULL DEFAULT '[]',   -- JSON-encoded list[dict]; see session_store.py
    token_count     integer NOT NULL DEFAULT 0,   -- last observed input_tokens (design.md Section 4.3)
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
