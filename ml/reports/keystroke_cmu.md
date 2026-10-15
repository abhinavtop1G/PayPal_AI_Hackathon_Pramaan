# Keystroke dynamics — 1D-CNN encoder on CMU DSL-StrongPassword

51 subjects type `.tie5Roanl` 400 times (8 sessions x 50). Users split 35/8/8 (train/valid/test, disjoint); the CNN never sees valid/test users. EER in % (lower is better), mean ± std over 3 training seeds; classic detectors are deterministic. Per-user EER = each user's own threshold (as in Killourhy & Maxion); pooled EER = one global threshold.

## A · held-out users, enrol on sessions 1-4, test on sessions 5-8

| method | per-user EER, 1 try | per-user EER, 3 tries | pooled EER, 1 try |
|---|---|---|---|
| 1D-CNN embedding (ours) | 13.0 ± 0.6 | 9.0 ± 0.3 | 15.9 ± 0.4 |
| Scaled Manhattan | 19.9 ± 0.0 | 18.4 ± 0.0 | 21.6 ± 0.0 |
| Mahalanobis (shrunk) | 22.2 ± 0.0 | 23.6 ± 0.0 | 24.9 ± 0.0 |
| 1D-CNN + scaled Manhattan (fusion) | 12.3 ± 0.4 | 8.3 ± 0.6 | 14.8 ± 0.9 |

## B · realistic enrolment: 10 attempts from the first session, test on sessions 5-8

| method | per-user EER, 1 try | per-user EER, 3 tries | pooled EER, 1 try |
|---|---|---|---|
| 1D-CNN embedding (ours) | 29.1 ± 0.8 | 26.4 ± 1.1 | 31.7 ± 1.4 |
| Scaled Manhattan | 28.2 ± 0.0 | 26.2 ± 0.0 | 36.0 ± 0.0 |
| Mahalanobis (shrunk) | 40.7 ± 0.0 | 40.2 ± 0.0 | 42.2 ± 0.0 |
| 1D-CNN + scaled Manhattan (fusion) | 25.9 ± 0.8 | 22.9 ± 0.5 | 30.5 ± 0.7 |

## C · Killourhy & Maxion protocol (train on first 200 attempts; impostors = first 5 attempts of the other 50)

| method | users | mean per-user EER | published |
|---|---|---|---|
| Scaled Manhattan | all 51 | 9.6 | 9.6 |
| Mahalanobis (shrunk) | all 51 | 13.3 | 11.0 |
| 1D-CNN embedding (ours) | 8 held-out | 9.7 ± 3.4 | |
| Scaled Manhattan | 8 held-out | 7.4 ± 2.7 | |
| Mahalanobis (shrunk) | 8 held-out | 7.9 ± 4.4 | |
| 1D-CNN + scaled Manhattan (fusion) | 8 held-out | 6.5 ± 2.1 | |

Serving model: seed 1 (best valid per-user EER 11.3%, protocol A), 84,096 parameters; fused-score threshold set at the pooled valid EER (10.8%, profile from the customer's past attempts).

Typing drifts between sessions: with only 10 enrolment attempts from one sitting (B) every method degrades sharply, so a deployed profile should be built from, and refreshed with, the customer's verified logins.

Caveats: one fixed password typed in a lab on one keyboard, so this verifies fixed-phrase entry (PIN / password), not free text. Our scaled Manhattan reproduces the published 9.6% on protocol C, which checks the baseline implementation. Only 8 test users: differences of a few points are within noise. The training sweep (dropout, weight decay, embedding size, augmentation strength) did not beat the defaults on valid users.
