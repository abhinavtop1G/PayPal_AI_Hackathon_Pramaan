# BIOS V2 · FRONTIER 04 screening video (Manim)

57 s explainer for the screening round ("a one-minute video explaining your approach and how it solves the problem").
Output: `out/bios_auth_explainer_1080p60.mp4` (1920×1080, 60 fps).

Beats: Problem (SIM swap beats SMS OTP) → Approach (one API call, 26 signals in 3 families, monotone XGBoost, policy) →
Attacks blocked with reasons + tree-SHAP (console screenshots) → The right challenge (passkey after SIM change, call-back
for a coached victim) → Results (simulated, labelled) → Real time + security + cloud design → End card.

```bat
%USERPROFILE%\env1\Scripts\python.exe assemble.py ql     :: draft 480p15
%USERPROFILE%\env1\Scripts\python.exe assemble.py qh     :: final 1080p60
```

Every number is read at render time from `~/Downloads/BIOS_auth` (`ml/reports/auth.json`, `backend/reports/auth_latency.md`,
`frontend/public/data/auth_demo.json`); scenes assert the demo decisions they describe. The ₹22,845 crore figure and the
RBI directions are external and cited on screen.

Screenshots: start the API and console (see `BIOS_auth/README.md`), then `node capture.mjs` (Chrome DevTools protocol,
1920×1080, deep links `/?scenario=…&verify=pass`), then `python crop_shots.py` (crops at panel boundaries, masks the
per-call latency chip; boxes in `assets/shots/regions.json`).

Honesty: results are labelled simulated; screenshots are labelled "recorded from the API · local run"; the cloud is
shown as a design with "deploy script written · first cloud run at the hack" (it has not been deployed).
