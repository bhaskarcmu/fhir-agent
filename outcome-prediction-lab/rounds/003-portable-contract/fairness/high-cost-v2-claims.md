# Fairness — `high-cost-v2-claims` (high_cost_y2)

Test panels 26–27, n = 11,863, outcome rate 10.0%, AUROC 0.834. Flag = top 10% of predicted risk (cutoff 27.3%); the flag catches 44% of all cases.

Calibration ratio = mean predicted ÷ observed rate (1.00 = calibrated; > 1 over-predicts the group, < 1 under-predicts it). "Cases caught" = share of the group's actual cases inside the flag (equal opportunity). Differences partly reflect real differences in base rates.

## Race / ethnicity

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| White, non-Hispanic | 6,997 | 11.9% | 0.811 (0.796–0.829) | 12.3% | 1.04 | 12% | 45% | 43% |
| Hispanic | 2,197 | 5.6% | 0.885 (0.858–0.913) | 6.3% | 1.12 | 5% | 37% | 44% |
| Black, non-Hispanic | 1,669 | 9.5% | 0.845 (0.814–0.877) | 10.2% | 1.07 | 10% | 46% | 44% |
| Asian, non-Hispanic | 665 | 6.3% | 0.820 (0.743–0.878) | 5.4% | 0.85 | 3% | 26% | 61% |
| Other or multiple, non-Hispanic | 335 | 9.3% | 0.865 (0.799–0.930) | 11.1% | 1.20 | 13% | 58% | 42% |

## Insurance (year 1)

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| Any private insurance | 7,271 | 8.8% | 0.816 (0.798–0.831) | 9.3% | 1.05 | 7% | 35% | 42% |
| Public insurance only | 3,671 | 14.4% | 0.831 (0.814–0.845) | 14.9% | 1.04 | 18% | 55% | 45% |
| Uninsured | 921 | 1.8% | _too few events (< 20) for a stable AUROC_ | 2.0% | 1.10 | 0% | 12% | 67% |

## Sex

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| Women | 6,417 | 11.4% | 0.823 (0.806–0.840) | 11.8% | 1.04 | 12% | 46% | 44% |
| Men | 5,446 | 8.4% | 0.846 (0.831–0.864) | 8.9% | 1.06 | 8% | 41% | 44% |

## Age band

| Group | n | Rate | AUROC (95% CI) | Mean predicted | Calibration ratio | Flagged | Cases caught | Precision if flagged |
|---|---|---|---|---|---|---|---|---|
| 18–44 | 4,362 | 4.1% | 0.825 (0.793–0.859) | 4.7% | 1.16 | 2% | 23% | 37% |
| 45–64 | 3,965 | 10.0% | 0.818 (0.800–0.838) | 10.1% | 1.01 | 9% | 39% | 43% |
| 65–74 | 2,094 | 14.9% | 0.785 (0.757–0.811) | 16.0% | 1.07 | 16% | 48% | 44% |
| 75 and over | 1,442 | 20.8% | 0.770 (0.738–0.798) | 20.9% | 1.01 | 27% | 58% | 45% |

## Widest gaps (groups with enough events)

| Dimension | AUROC range | Calibration ratio range | Cases caught range |
|---|---|---|---|
| Race / ethnicity | 0.811–0.885 (gap 0.074) | 0.85–1.20 | 26%–58% |
| Insurance (year 1) | 0.816–0.831 (gap 0.015) | 1.04–1.05 | 35%–55% |
| Sex | 0.823–0.846 (gap 0.023) | 1.04–1.06 | 41%–46% |
| Age band | 0.770–0.825 (gap 0.055) | 1.01–1.16 | 23%–58% |
