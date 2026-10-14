# Real biometrics on simulated touch windows

Every touch window in `data/sim_wf` is 10 real gestures from the customer's held-out HMOG subject (or, for `remote`, from a different subject), scored by the BiLSTM+LDA model against the customer's profile enrolled from sessions 1-12. Deviation > 0 means the window does not match the enrolled owner (the model's EER threshold).

| profile | what it is | windows | mean deviation | flagged as not the owner |
|---|---|---|---|---|
| normal | own hands | 64,811 | -0.58 | 25.5% |
| distracted | own hands, mild documented shift | 7,854 | -0.563 | 25.9% |
| rushed | own hands, documented hurry shift | 12,350 | -0.563 | 26.2% |
| coerced | own hands, documented stress shift (assumption: HMOG has no coercion labels) | 18,705 | -0.543 | 26.2% |
| remote | someone else's real gestures (overlay / remote-control fraud) | 7,524 | 0.482 | 76.0% |

The model recognises *who* is touching, not *how stressed* they are: it separates someone else's hands from the owner's, while modelled coercion barely moves it. Coercion is left to the stage tracker's own touch-rhythm inputs.
