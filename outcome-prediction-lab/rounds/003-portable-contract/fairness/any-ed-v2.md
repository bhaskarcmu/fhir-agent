# Fairness — `any-ed-v2` (any_ed_y2)

Test panels 26–27, n = 11,863, outcome rate 15.5%, AUROC 0.740. Flag = top 10% of predicted risk (cutoff 31.1%); the flag catches 28% of all cases.

Calibration ratio = mean predicted ÷ observed rate (1.00 = calibrated; > 1 over-predicts the group, < 1 under-predicts it). "Cases caught" = share of the group's actual cases inside the flag (equal opportunity). Differences partly reflect real differences in base rates.

## Race / ethnicity

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| White, non-Hispanic | 6,997 | 16.4% | 0.729 (0.710–0.745) | 16.1% | 0.98 | 11% | 29% | 45% |
| Hispanic | 2,197 | 11.7% | 0.746 (0.718–0.772) | 11.5% | 0.98 | 5% | 18% | 41% |
| Black, non-Hispanic | 1,669 | 19.2% | 0.732 (0.697–0.763) | 18.5% | 0.96 | 16% | 34% | 42% |
| Asian, non-Hispanic | 665 | 7.7% | 0.706 (0.630–0.779) | 7.5% | 0.98 | 1% | 6% | 33% |
| Other or multiple, non-Hispanic | 335 | 17.3% | 0.779 (0.704–0.845) | 18.5% | 1.07 | 19% | 52% | 48% |

## Insurance (year 1)

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| Any private insurance | 7,271 | 12.3% | 0.713 (0.695–0.734) | 12.7% | 1.03 | 5% | 18% | 42% |
| Public insurance only | 3,671 | 23.3% | 0.716 (0.700–0.734) | 21.9% | 0.94 | 22% | 42% | 45% |
| Uninsured | 921 | 9.1% | 0.782 (0.728–0.833) | 7.9% | 0.86 | 2% | 11% | 60% |

## Sex

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| Women | 6,417 | 17.4% | 0.732 (0.714–0.747) | 16.5% | 0.95 | 12% | 31% | 46% |
| Men | 5,446 | 13.2% | 0.745 (0.725–0.763) | 13.6% | 1.04 | 8% | 24% | 41% |

## Age band

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| 18–44 | 4,362 | 10.3% | 0.686 (0.661–0.713) | 10.9% | 1.05 | 4% | 13% | 38% |
| 45–64 | 3,965 | 14.4% | 0.749 (0.728–0.770) | 14.4% | 1.00 | 9% | 27% | 43% |
| 65–74 | 2,094 | 19.2% | 0.712 (0.680–0.741) | 18.1% | 0.94 | 13% | 30% | 45% |
| 75 and over | 1,442 | 28.5% | 0.680 (0.654–0.710) | 25.8% | 0.90 | 28% | 45% | 46% |

## Widest gaps (groups with enough events)

| Dimension | AUROC range | Calibration ratio range | Cases caught range |
|---|---|---|---|
| Race / ethnicity | 0.706–0.779 (gap 0.072) | 0.96–1.07 | 6%–52% |
| Insurance (year 1) | 0.713–0.782 (gap 0.069) | 0.86–1.03 | 11%–42% |
| Sex | 0.732–0.745 (gap 0.013) | 0.95–1.04 | 24%–31% |
| Age band | 0.680–0.749 (gap 0.069) | 0.90–1.05 | 13%–45% |
