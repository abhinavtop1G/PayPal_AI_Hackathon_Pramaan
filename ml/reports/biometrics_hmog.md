# HMOG continuous authentication — open-set verification

Users split 70/15/15 (train/valid/test, disjoint). Test users: 15. Profile = sessions 1–12, probes = sessions 13–24; impostors = all other test users. EER in % (lower is better); per-user = mean of each user's own EER (per-user thresholds).

| window | model | test EER | per-user EER | sitting | walking | valid EER |
|---|---|---|---|---|---|---|
| 10 gestures | Window stats + cosine | 20.1 | 18.8 | 23.9 | 17.6 | 17.3 |
| 10 gestures | Window stats + LDA | 14.8 | 13.3 | 15.5 | 14.3 | 13.1 |
| 10 gestures | BiLSTM gesture encoder (3 seeds) | 16.9 ± 1.5 | 16.8 ± 1.3 | 17.3 ± 0.4 | 16.4 ± 1.7 | 15.0 ± 0.7 |
| 10 gestures | BiLSTM + LDA score fusion | 14.4 ± 0.2 | 12.8 ± 0.4 | 15.6 ± 0.4 | 13.5 ± 0.2 | 12.4 ± 0.1 |
| 20 gestures | Window stats + cosine | 18.9 | 16.4 | 22.8 | 16.2 | 15.3 |
| 20 gestures | Window stats + LDA | 13.0 | 11.3 | 13.7 | 12.6 | 10.7 |
| 20 gestures | BiLSTM gesture encoder (3 seeds) | 17.3 ± 2.6 | 16.0 ± 0.6 | 16.1 ± 0.8 | 17.1 ± 2.8 | 13.7 ± 1.2 |
| 20 gestures | BiLSTM + LDA score fusion | 13.5 ± 0.2 | 10.9 ± 0.3 | 14.3 ± 0.5 | 12.8 ± 0.1 | 11.0 ± 0.1 |
