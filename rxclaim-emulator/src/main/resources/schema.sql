-- DB2/SQL400-style tables for the simulated RxClaim / IBM i core.
-- Names are deliberately legacy-flavoured (short, uppercase, "master file" naming),
-- as they would appear on Db2 for i. This is the legacy system-of-record + pricing data
-- the modern layer wraps (never rewrites) — see rxclaim-emulator/README.md.

-- MBRMST — Member Master File (eligibility system-of-record)
CREATE TABLE IF NOT EXISTS MBRMST (
  MBRID   CHAR(9)     NOT NULL PRIMARY KEY,  -- member id (zero-padded)
  MBRFNM  VARCHAR(30),                       -- member first name
  MBRLNM  VARCHAR(30),                       -- member last name
  PLANID  VARCHAR(20) NOT NULL,              -- benefit plan id
  EFFDTE  DATE        NOT NULL,              -- coverage effective date
  TRMDTE  DATE        NOT NULL,              -- coverage termination date
  MBRSTS  CHAR(1)     NOT NULL DEFAULT 'A'   -- A=active, I=inactive
);

-- DRGMST — Drug Master File (legacy pricing: AWP + dispensing fee)
CREATE TABLE IF NOT EXISTS DRGMST (
  NDCCDE  VARCHAR(11) NOT NULL PRIMARY KEY,  -- National Drug Code
  DRGNAM  VARCHAR(60),                       -- drug name
  AWPAMT  NUMERIC(11,2) NOT NULL,            -- average wholesale price (per unit)
  DSPFEE  NUMERIC(7,2)  NOT NULL             -- dispensing fee
);

-- ACCMST — Accumulator Master File (deductible / out-of-pocket running totals)
CREATE TABLE IF NOT EXISTS ACCMST (
  MBRID   CHAR(9)     NOT NULL,
  PLANYR  INTEGER     NOT NULL,              -- plan year
  DEDMET  NUMERIC(11,2) NOT NULL DEFAULT 0,  -- deductible met to date
  OOPMET  NUMERIC(11,2) NOT NULL DEFAULT 0,  -- out-of-pocket met to date
  PRIMARY KEY (MBRID, PLANYR)
);
