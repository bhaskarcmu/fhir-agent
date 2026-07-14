-- Seed data for the legacy core. Synthetic; drug NDCs align with the payer-KB crosswalk
-- (data/payer-kb/crosswalk/ndc_rxcui.csv) so the modern layer and legacy core agree on drugs.

-- Members: one active (000000001), one terminated 2026-01-31 (000000002) for the
-- inactive-coverage scenario.
MERGE INTO MBRMST (MBRID, MBRFNM, MBRLNM, PLANID, EFFDTE, TRMDTE, MBRSTS) VALUES
  ('000000001', 'KRISTLE', 'MRAZ',  'COM-SILVER', DATE '2026-01-01', DATE '2026-12-31', 'A'),
  ('000000002', 'JOHN',    'DOE',   'COM-SILVER', DATE '2025-01-01', DATE '2026-01-31', 'I');

-- Drug pricing (AWP + dispensing fee). semaglutide is the high-cost specialty example.
MERGE INTO DRGMST (NDCCDE, DRGNAM, AWPAMT, DSPFEE) VALUES
  ('0093-8675',  'AMOXICILLIN 500MG CAP',        12.50, 1.50),
  ('51655-999',  'LISINOPRIL 10MG TAB',           8.00, 1.50),
  ('63552-200',  'SEMAGLUTIDE 1MG/0.5ML PEN',   950.00, 2.00),
  ('60505-0065', 'OMEPRAZOLE 20MG CAP',           6.00, 1.50),
  ('0597-0405',  'ADALIMUMAB 40MG/0.8ML PEN',  3200.00, 2.00);

-- Accumulators start at zero for plan year 2026.
MERGE INTO ACCMST (MBRID, PLANYR, DEDMET, OOPMET) VALUES
  ('000000001', 2026, 0, 0),
  ('000000002', 2026, 0, 0);
