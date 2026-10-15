# PRAMAAN · FRONTIER 04 screening video (Manim)

57 s explainer for the screening round ("a one-minute video explaining your approach and how it solves the problem").
Output: `out/pramaan_auth_explainer_1080p60.mp4` (1920×1080, 60 fps).

Beats: Problem (SIM swap beats SMS OTP) → Approach (one API call, 26 signals in 3 families, monotone XGBoost, policy) →
Attacks blocked with reasons + tree-SHAP (console screenshots) → The right challenge (passkey after SIM change, call-back
for a coached victim) → Results (simulated, labelled) → Real time + security + cloud design → End card.

```bat
%USERPROFILE%\env1\Scripts\python.exe assemble.py ql     :: draft 480p15
%USERPROFILE%\env1\Scripts\python.exe assemble.py qh     :: final 1080p60
```

Every number is read at render time from the repo root (`ml/reports/auth.json`, `backend/reports/auth_latency.md`,
`frontend/public/data/auth_demo.json`); scenes assert the demo decisions they describe. The ₹22,845 crore figure and the
RBI directions are external and cited on screen.

Screenshots: start the API and console (see the main `README.md`), then `node capture.mjs` (Chrome DevTools protocol,
1920×1080, deep links `/?scenario=…&verify=pass`), then `python crop_shots.py` (crops at panel boundaries, masks the
per-call latency chip; boxes in `assets/shots/regions.json`).

Honesty: results are labelled simulated; screenshots are labelled "recorded from the API · local run"; the cloud is
shown as a design with "deploy script written · first cloud run at the hack" (it has not been deployed).

The committed render predates the PRAMAAN rename and the re-recorded demo (typing signal), so it still shows
"BIOS V2" and the older demo numbers. To re-render it: re-capture the screenshots (`node capture.mjs`, `python
crop_shots.py`) and update the demo assertions in `scenes.py` (the bot's top reasons changed).

---

# PRAMAAN explainer (plain words + a light technical layer, Manim)

PRAMAAN = Parallel Risk-Adaptive Multi-modal Authentication & Anomaly Network (the service in this repo). Team CaffeineEaters: Abhinav Saini, Aditi Pundir, Mannat Kaur, Aryamann Sharma.

61 s explainer for mixed audiences. Output: `out/pramaan_explainer_1080p60.mp4` (1920×1080, 60 fps, silent; captions
carry the story).

Beats: Intro (name, full form, प्रमाण = proof, team) → Problem (OTP checks a code, not the person) → Checks (tap Pay,
three checks run in parallel, then the models and signal counts behind each) → How it decides (Asha's SIM-swap case:
signals that fired → monotone XGBoost risk score → lowest expected loss → BLOCK → tree-SHAP reasons in English and
Hindi) → Three answers (allow / challenge / block) → Models and speed (per-model test results, measured p95 latency,
Google Cloud design) → Who it's for + end card with team and members.

```bat
python assemble_simple.py ql     :: draft 480p15
python assemble_simple.py qh     :: final 1080p60
```

Every figure is read from the repo at render time and asserted in `simple_scenes.py`: Asha's cases, risk score,
expected costs and reasons from `frontend/public/data/auth_demo.json`; model results from `ml/reports/`; latency from
`backend/reports/auth_latency.md`; signal counts from `ml/auth/features.py`. Latency is labelled "measured on a laptop
CPU over HTTP"; the cloud is shown as "built for Google Cloud" (the design in `docs/DEPLOY.md`), not as measured.

## Voiceover script (optional, record over the video)

| time | line |
|---|---|
| 0:00 | PRAMAAN: Parallel Risk-Adaptive Multi-modal Authentication and Anomaly Network. By team CaffeineEaters. |
| 0:04 | Paying online takes one tap, and so can losing your money. Today's OTP checks a code, not the person. |
| 0:11 | Meet PRAMAAN. When you tap Pay, three checks run in parallel: is it really you, is this your phone, and is this payment normal? Twenty-seven live signals, read by trained AI models. |
| 0:20 | A real example: a fraudster with Asha's swapped SIM tries sixty thousand rupees. The risk model gives a 94% risk score, the policy picks the action with the lowest expected loss, block, and tree-SHAP turns the score into reasons in English and Hindi. |
| 0:34 | Normal payments just go through. Unusual ones get one quick check that fits, like a fingerprint or a bank call-back. Clear attacks are blocked before the money moves. |
| 0:44 | Our models are trained and tested on public data: touch, typing, card fraud and mule rings. Ninety-five percent of decisions finish within seventy milliseconds, and it's built for Google Cloud. |
| 0:53 | For banks and UPI apps: plug in once, protect every payment. PRAMAAN, by team CaffeineEaters. |
