# Fairness — `nonobstetric-v2` (admit_nonobstetric_y2)

Test panels 26–27, n = 11,863, outcome rate 7.9%, AUROC 0.795. Flag = top 10% of predicted risk (cutoff 19.0%); the flag catches 38% of all cases.

Calibration ratio = mean predicted ÷ observed rate (1.00 = calibrated; > 1 over-predicts the group, < 1 under-predicts it). "Cases caught" = share of the group's actual cases inside the flag (equal opportunity). Differences partly reflect real differences in base rates.

## Race / ethnicity

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| White, non-Hispanic | 6,997 | 9.0% | 0.787 (0.763–0.807) | 9.1% | 1.01 | 12% | 40% | 30% |
| Hispanic | 2,197 | 4.9% | 0.822 (0.783–0.856) | 5.1% | 1.04 | 4% | 27% | 32% |
| Black, non-Hispanic | 1,669 | 9.0% | 0.745 (0.709–0.779) | 8.7% | 0.96 | 12% | 36% | 27% |
| Asian, non-Hispanic | 665 | 3.2% | 0.737 (0.634–0.850) | 3.9% | 1.23 | 3% | 19% | 24% |
| Other or multiple, non-Hispanic | 335 | 8.7% | 0.881 (0.815–0.932) | 8.4% | 0.98 | 13% | 59% | 40% |

## Insurance (year 1)

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| Any private insurance | 7,271 | 5.6% | 0.776 (0.754–0.802) | 6.4% | 1.16 | 6% | 27% | 25% |
| Public insurance only | 3,671 | 14.0% | 0.750 (0.730–0.769) | 12.4% | 0.89 | 20% | 48% | 33% |
| Uninsured | 921 | 2.3% | 0.794 (0.704–0.880) | 2.8% | 1.23 | 0% | 5% | 25% |

## Sex

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| Women | 6,417 | 8.7% | 0.789 (0.768–0.807) | 8.5% | 0.98 | 11% | 42% | 34% |
| Men | 5,446 | 7.0% | 0.800 (0.777–0.824) | 7.3% | 1.05 | 9% | 33% | 25% |

## Age band

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| 18–44 | 4,362 | 2.3% | 0.700 (0.644–0.746) | 2.8% | 1.25 | 1% | 6% | 23% |
| 45–64 | 3,965 | 6.8% | 0.747 (0.720–0.775) | 7.3% | 1.07 | 6% | 27% | 29% |
| 65–74 | 2,094 | 13.4% | 0.693 (0.657–0.725) | 12.6% | 0.94 | 17% | 35% | 28% |
| 75 and over | 1,442 | 20.0% | 0.693 (0.654–0.726) | 18.7% | 0.93 | 38% | 62% | 33% |

## Widest gaps (groups with enough events)

| Dimension | AUROC range | Calibration ratio range | Cases caught range |
|---|---|---|---|
| Race / ethnicity | 0.737–0.881 (gap 0.144) | 0.96–1.23 | 19%–59% |
| Insurance (year 1) | 0.750–0.794 (gap 0.044) | 0.89–1.23 | 5%–48% |
| Sex | 0.789–0.800 (gap 0.011) | 0.98–1.05 | 33%–42% |
| Age band | 0.693–0.747 (gap 0.054) | 0.93–1.25 | 6%–62% |
