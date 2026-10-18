# Fairness — `er-admit-v2` (admit_via_er_y2)

Test panels 26–27, n = 11,863, outcome rate 4.9%, AUROC 0.785. Flag = top 10% of predicted risk (cutoff 11.7%); the flag catches 40% of all cases.

Calibration ratio = mean predicted ÷ observed rate (1.00 = calibrated; > 1 over-predicts the group, < 1 under-predicts it). "Cases caught" = share of the group's actual cases inside the flag (equal opportunity). Differences partly reflect real differences in base rates.

## Race / ethnicity

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| White, non-Hispanic | 6,997 | 5.4% | 0.778 (0.749–0.800) | 5.5% | 1.01 | 11% | 42% | 20% |
| Hispanic | 2,197 | 3.2% | 0.812 (0.751–0.861) | 3.6% | 1.12 | 5% | 30% | 20% |
| Black, non-Hispanic | 1,669 | 5.6% | 0.772 (0.729–0.818) | 5.9% | 1.07 | 13% | 43% | 19% |
| Asian, non-Hispanic | 665 | 3.2% | 0.639 (0.512–0.770) | 2.8% | 0.90 | 3% | 19% | 20% |
| Other or multiple, non-Hispanic | 335 | 5.7% | _too few events (< 20) for a stable AUROC_ | 5.8% | 1.02 | 13% | 58% | 25% |

## Insurance (year 1)

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| Any private insurance | 7,271 | 3.1% | 0.752 (0.718–0.792) | 3.9% | 1.24 | 6% | 27% | 15% |
| Public insurance only | 3,671 | 9.2% | 0.747 (0.721–0.772) | 8.2% | 0.89 | 21% | 52% | 23% |
| Uninsured | 921 | 2.3% | 0.686 (0.556–0.809) | 2.2% | 0.98 | 1% | 0% | 0% |

## Sex

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| Women | 6,417 | 5.5% | 0.767 (0.738–0.790) | 5.4% | 0.98 | 11% | 44% | 22% |
| Men | 5,446 | 4.2% | 0.810 (0.785–0.837) | 4.7% | 1.11 | 9% | 34% | 16% |

## Age band

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| 18–44 | 4,362 | 1.9% | 0.666 (0.596–0.737) | 2.2% | 1.21 | 1% | 7% | 12% |
| 45–64 | 3,965 | 3.9% | 0.751 (0.715–0.790) | 4.6% | 1.17 | 7% | 30% | 18% |
| 65–74 | 2,094 | 7.6% | 0.728 (0.681–0.768) | 7.2% | 0.94 | 14% | 35% | 20% |
| 75 and over | 1,442 | 13.1% | 0.708 (0.672–0.745) | 12.0% | 0.92 | 41% | 67% | 22% |

## Widest gaps (groups with enough events)

| Dimension | AUROC range | Calibration ratio range | Cases caught range |
|---|---|---|---|
| Race / ethnicity | 0.639–0.812 (gap 0.173) | 0.90–1.12 | 19%–43% |
| Insurance (year 1) | 0.686–0.752 (gap 0.067) | 0.89–1.24 | 0%–52% |
| Sex | 0.767–0.810 (gap 0.044) | 0.98–1.11 | 34%–44% |
| Age band | 0.666–0.751 (gap 0.085) | 0.92–1.21 | 7%–67% |
