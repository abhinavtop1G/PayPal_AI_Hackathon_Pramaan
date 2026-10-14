"""Transaction authentication (BIOS): allow / challenge / block an online transaction from behaviour, device and
transaction-pattern signals, with the signals behind every decision.

    geo.py        cities, distances, IP intelligence (datacenter / anonymiser ranges, gateway geo header)
    state.py      live per-user / per-device / per-IP state (in-memory, or Redis with REDIS_URL)
    features.py   request + state -> model features (same code in simulation, training and serving)
    sim.py        account-takeover simulator: genuine users and attacks, with real HMOG touch windows
    model.py      monotone XGBoost risk model, prior correction, SHAP signal contributions
    policy.py     expected-cost decision allow / challenge / block and the choice of step-up challenge
    engine.py     the service object behind POST /v1/authenticate and /v1/challenge/verify
    evaluate.py   train + replay evaluation -> ml/reports/auth.md
"""
