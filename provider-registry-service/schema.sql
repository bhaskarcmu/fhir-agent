-- Provider Registry schema (design.md §4.1). Plain SQL, applied at startup/test-setup —
-- matching rxclaim-emulator's schema.sql convention rather than introducing a migration
-- framework for a brand-new 7-table schema.

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    states_pulled       text[] NOT NULL DEFAULT '{}',
    records_added       integer NOT NULL DEFAULT 0,
    records_updated     integer NOT NULL DEFAULT 0,
    records_flagged     integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS providers (
    npi                 char(10) PRIMARY KEY,
    entity_type         smallint NOT NULL CHECK (entity_type IN (1, 2)),
    first_name          text,
    last_name           text,
    organization_name   text,
    phone               text,
    is_sole_proprietor  boolean,
    npi_status          text NOT NULL DEFAULT 'active' CHECK (npi_status IN ('active', 'deactivated')),
    deactivated_at      date,
    deactivation_reason text,
    source              text NOT NULL,
    source_pulled_at    timestamptz NOT NULL,
    ingestion_run_id    uuid REFERENCES ingestion_runs(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS taxonomy_reference (
    code                text PRIMARY KEY,
    grouping            text NOT NULL,
    classification      text NOT NULL,
    specialization       text,
    definition          text,
    nucc_version        text NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_addresses (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    npi                 char(10) NOT NULL REFERENCES providers(npi),
    address_1           text NOT NULL,
    address_2           text,
    city                text NOT NULL,
    state               char(2) NOT NULL,
    zip5                char(5) NOT NULL,
    zip4                char(4),
    lat                 double precision,
    lon                 double precision,
    is_primary_practice boolean NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_provider_addresses_npi ON provider_addresses (npi);
CREATE INDEX IF NOT EXISTS idx_provider_addresses_state ON provider_addresses (state);

CREATE TABLE IF NOT EXISTS provider_taxonomies (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    npi                 char(10) NOT NULL REFERENCES providers(npi),
    taxonomy_code       text NOT NULL REFERENCES taxonomy_reference(code),
    is_primary          boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_provider_taxonomies_npi ON provider_taxonomies (npi);
CREATE INDEX IF NOT EXISTS idx_provider_taxonomies_code ON provider_taxonomies (taxonomy_code);

CREATE TABLE IF NOT EXISTS zip_centroids (
    zip5                char(5) PRIMARY KEY,
    lat                 double precision NOT NULL,
    lon                 double precision NOT NULL,
    state               char(2) NOT NULL
);

CREATE TABLE IF NOT EXISTS anomaly_flags (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    npi                 char(10) NOT NULL REFERENCES providers(npi),
    run_id              uuid NOT NULL REFERENCES ingestion_runs(id),
    flag_type           text NOT NULL CHECK (flag_type IN
                            ('missing_taxonomy', 'missing_coordinate', 'stale', 'address_conflict')),
    detail              text
);
