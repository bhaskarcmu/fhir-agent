# Holdout ledger — every look at the test panels

Append-only (docs/phase8/experimentation-protocol.md §5). A row is written BEFORE the test
panels are scored; `holdout.require` refuses to score a candidate without one.

| When (UTC) | Round | Candidate | Test panels | Why this look |
|---|---|---|---|---|
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | any_stay/prototype | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | any_stay/new-portable | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | any_stay/new-with-survey | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | target/admit_nonobstetric_y2 | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | target/admit_via_er_y2 | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | target/any_ed_y2 | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | target/ed_visits_y2 | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | target/high_cost_y2 | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | target/cost_y2 | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | target/died_y2 | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T00:40:34+00:00 | 001-what-and-how | target/lost_insurance_y2 | 26, 27 | single confirmation of a CV-chosen finalist; pre-registered in rounds/001-what-and-how/README.md |
| 2026-10-18T02:10:44+00:00 | 003-portable-contract | nonobstetric-v2 | 26, 27 | pre-registered production-contract candidate (rounds/003-portable-contract/README.md) |
| 2026-10-18T02:10:49+00:00 | 003-portable-contract | any-ed-v2 | 26, 27 | pre-registered production-contract candidate (rounds/003-portable-contract/README.md) |
| 2026-10-18T02:10:55+00:00 | 003-portable-contract | high-cost-v2-claims | 26, 27 | pre-registered production-contract candidate (rounds/003-portable-contract/README.md) |
| 2026-10-18T14:31:33+00:00 | 004-focus-four-readiness | er-admit-v2 | 26, 27 | Round 004 pre-registered confirmation: records-only production-contract model for admission through the ER (README, written before CV). |
| 2026-10-18T14:31:43+00:00 | 003-portable-contract | nonobstetric-v2:fairness | 26, 27 | Round 004 pre-registered fairness look (FR-E6) for focus production model nonobstetric-v2. |
| 2026-10-18T14:31:51+00:00 | 003-portable-contract | any-ed-v2:fairness | 26, 27 | Round 004 pre-registered fairness look (FR-E6) for focus production model any-ed-v2. |
| 2026-10-18T14:32:00+00:00 | 003-portable-contract | high-cost-v2-claims:fairness | 26, 27 | Round 004 pre-registered fairness look (FR-E6) for focus production model high-cost-v2-claims. |
| 2026-10-18T14:32:10+00:00 | 004-focus-four-readiness | er-admit-v2:fairness | 26, 27 | Round 004 pre-registered fairness look (FR-E6) for focus production model er-admit-v2. |
| 2026-10-18T14:46:52+00:00 | 000-baseline-reproduction | meps25-v1 | 26, 27 | Round 000 pre-registered reproduction of M2's meps25-v1 (results already reported by M2; reveals nothing new). |
| 2026-10-18T14:46:55+00:00 | 000-baseline-reproduction | meps25-v1-comparison | 26, 27 | Round 000 pre-registered reproduction of M2's meps25-v1-comparison (results already reported by M2; reveals nothing new). |
