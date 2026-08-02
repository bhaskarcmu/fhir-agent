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

-- M5 (decisions.md H49): the provider/model choice a session was created with, pinned for
-- that session's whole lifetime -- "model choice is a per-session decision," not something
-- that could drift mid-conversation if the environment's own defaults change later.
-- ADD COLUMN IF NOT EXISTS, not a fresh CREATE TABLE, so an existing dev database with
-- pre-M5 rows gets these columns added rather than the table being dropped and recreated.
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT 'ollama';
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS model text NOT NULL DEFAULT 'llama3.2:1b';
