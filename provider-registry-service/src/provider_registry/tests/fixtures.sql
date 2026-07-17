-- Small hand-written fixture (design.md M2: "not real data yet") exercising:
-- distance ordering, radius exclusion, taxonomy filter, entity_type filter, and the
-- npi_status default-exclusion / get_provider-still-returns-it policy from §4.1.

INSERT INTO ingestion_runs (id, started_at, completed_at, states_pulled, records_added)
VALUES ('11111111-1111-1111-1111-111111111111', now(), now(), '{NC}', 5);

INSERT INTO taxonomy_reference (code, grouping, classification, specialization, definition, nucc_version)
VALUES
    ('207RE0101X', 'Allopathic & Osteopathic Physicians', 'Endocrinology, Diabetes & Metabolism', NULL,
     'Endocrinology specialist', '24.1'),
    ('207RC0000X', 'Allopathic & Osteopathic Physicians', 'Cardiovascular Disease', NULL,
     'Cardiology specialist', '24.1');

INSERT INTO zip_centroids (zip5, lat, lon, state) VALUES
    ('27514', 35.9132, -79.0558, 'NC'),  -- Chapel Hill
    ('27601', 35.7796, -78.6382, 'NC'),  -- Raleigh (~23mi from Chapel Hill)
    ('90001', 33.9731, -118.2479, 'CA'); -- Los Angeles (far away)

INSERT INTO providers
    (npi, entity_type, first_name, last_name, organization_name, npi_status,
     deactivated_at, source, source_pulled_at, ingestion_run_id)
VALUES
    ('1111111111', 1, 'Jane', 'Doe', NULL, 'active',
     NULL, 'NPPES', now(), '11111111-1111-1111-1111-111111111111'),
    ('2222222222', 1, 'John', 'Smith', NULL, 'active',
     NULL, 'NPPES', now(), '11111111-1111-1111-1111-111111111111'),
    ('3333333333', 1, 'Retired', 'Doe', NULL, 'deactivated',
     '2025-01-01', 'NPPES', now(), '11111111-1111-1111-1111-111111111111'),
    ('4444444444', 2, NULL, NULL, 'Duke Health Endocrinology Center', 'active',
     NULL, 'NPPES', now(), '11111111-1111-1111-1111-111111111111'),
    ('5555555555', 1, 'Far', 'Cardiologist', NULL, 'active',
     NULL, 'NPPES', now(), '11111111-1111-1111-1111-111111111111');

INSERT INTO provider_addresses (npi, address_1, city, state, zip5, lat, lon, is_primary_practice)
VALUES
    ('1111111111', '100 Main St', 'Chapel Hill', 'NC', '27514', 35.9132, -79.0558, true),
    ('2222222222', '200 Fayetteville St', 'Raleigh', 'NC', '27601', 35.7796, -78.6382, true),
    ('3333333333', '100 Main St', 'Chapel Hill', 'NC', '27514', 35.9132, -79.0558, true),
    ('4444444444', '300 Franklin St', 'Chapel Hill', 'NC', '27514', 35.9132, -79.0558, true),
    ('5555555555', '400 Sunset Blvd', 'Los Angeles', 'CA', '90001', 33.9731, -118.2479, true);

INSERT INTO provider_taxonomies (npi, taxonomy_code, is_primary)
VALUES
    ('1111111111', '207RE0101X', true),
    ('2222222222', '207RE0101X', true),
    ('3333333333', '207RE0101X', true),
    ('4444444444', '207RE0101X', true),
    ('5555555555', '207RC0000X', true);
