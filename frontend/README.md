# RAKSHAM demo frontend

Four views under one app bar:

| View | What it shows |
|---|---|
| **Session** | One customer's phone during a scam or its genuine look-alike, the bank's analyst console for that session, and the full session timeline. 8 scenarios × 3 customers. |
| **Bank wall** | 270 customer sessions from a 12-hour slice of the simulator's held-out test data, replayed on a compressed clock: a session grid that lights up by risk, a live alert queue checked against ground truth, KPIs (scams interrupted, genuine interrupted, alerts per 1k, money protected), activity over the window. Click any session to open it in the Session view. |
| **Mule network** | Payee side: campaign cases ranked by recoverable money, the money flow of each case (victims → collector accounts → onward hops → exits), bilingual case summaries and the recommended analyst actions (credit hold, 1930 report, warn payers). |
| **Try it** | Build a session by hand. Every button sends one raw event to the live API, and the console shows what the models returned. Touch buttons send real HMOG gestures (own hands, hesitant, or someone else's hands). "Call · reported no." uses a number on the demo telecom's reported list. Presets replay a digital-arrest pattern and a genuine family emergency. |

Next.js 16 (App Router) · React 19 · Tailwind CSS v4 · Motion.

```bash
cd frontend
npm install
npm run dev                # http://localhost:3000
```

## Data

Every number on screen comes from `POST /v1/demo/{typology}`, the same session pipeline the backend serves. The phone and console replay that response one event at a time.

- **Offline (default).** The page plays recordings, regenerated from the repo root with `python -m backend.record_demo`:
  - `src/data/`: the 8 scenarios for each of the 3 customers.
  - `public/data/fleet.json`: the bank wall (12 h of held-out sessions run through the session service with one shared alert policy).
  - `public/data/campaign.json`: the mule network (cases and money-flow graphs after 60 days of the synthetic ledger).
- **Live.** Start the API (`uvicorn backend.app:app --port 8000`) and run `NEXT_PUBLIC_RAKSHAM_API=http://127.0.0.1:8000 npm run dev`. The app bar shows "Live API" when the live call succeeds; if it fails, the page falls back to the recording.
  - Before each replay the page calls `/v1/admin/reset?services=session`, because all demo sessions share one simulated user per customer. Use a demo server only.
  - The mule network loads the payee-side ledger on first use (about 10 s) and falls back to the recording if the API has no cases.
  - **Try it** needs the live API; the bank wall always plays its recording.
  - The backend allows `localhost:3000` (CORS); set `RAKSHAM_CORS_ORIGINS` to change it.

## Customers

The backend picks one simulator user per persona (`/v1/demo/{typology}?persona=`). The usual payment comes from that user, so the same scam scales to each person's money:

| Persona | Story | Usual payment |
|---|---|---|
| `senior` | Harjeet Singh, 67, farmer | ₹1,127 |
| `student` | Riya Sharma, 21, student | ₹403 |
| `professional` | Vikram Rao, 34, engineer | ₹4,312 |

Decisions can differ by customer. The professional's genuine family transfer (₹70,000) is **held** at 0.75% risk, because the expected fraud cost at that amount outweighs a hold's friction. The console labels it a held genuine payment (a false alarm), not money protected. The same story for the student (₹7,000) gets a nudge.

## Scenarios

There are four pairs. Each scam runs next to a genuine session with the same shape, for the same 60+ user, through the same models.

| Workflow | Scam (engine decision) | Genuine look-alike (engine decision) |
|---|---|---|
| Digital arrest | VoIP "CBI officer", app install, balance checks, ₹12,000 → **hold** (99.6%) | hospital calls about an accident, ₹43,158 to a new payee → **allow**, no alert |
| Voice clone | grandson's cloned voice from abroad, ₹53,948 → **hold** (98.0%) | niece on a new number, ₹18,000 → **allow** (0.25%) |
| Fake KYC app | KYC SMS, sideloaded app, screen control, OTP, ₹10,037 → **hold** (99.6%) | real bank SMS, Play Store update, OTP, three shop payments → **allow** ×3 |
| Investment scam | "earn daily" SMS, ₹958 first deposit → **hold** (95.3%) | registered fund house, deposits over three days → **allow** ×4 |

`src/config/scenarios.ts` holds only the story layer: names, numbers, SMS and page text, and narration. Events, timings, amounts, scores, reasons and alert copy all come from the API.

For a scam, the replay stops at the hold. The rest of the simulator log, where the victim keeps paying, is shown on the timeline as *prevented by the hold*. Its total is the "Money protected" figure.

## Controls

- **Space**: play / pause
- **← / →**: step one event (pauses playback)
- **R**: restart
- **1–8**: scenario
- **1× / 2× / 4×**: playback speed
- **Timeline**: click an event or drag the playhead to jump; **Steps / Time** switches between evenly spaced events and real time (sessions run from minutes to days).
- **Inspector**: click an event in the feed to inspect it; **Live** follows the replay again.
- **Alert sheet**: English / हिन्दी toggle, "Call 1930", "End the call".
- **Case log**: confirm scam, call customer, release hold, report to 1930. These are demo actions only; nothing is sent.

## What each part shows

- **Inside the decision.** For the current event, the pipeline stages that actually run light up in order:
  1. event in;
  2. device context;
  3. **caller reputation**: the telecom check by private set intersection, run only with consent;
  4. stage tracker (GRU);
  5. payee intel;
  6. **biometrics**: the real HMOG BiLSTM+LDA model's verdict on 10 real gestures, "owner's touch" or "someone else's touch?";
  7. fusion (monotone XGBoost);
  8. alert policy;
  9. customer message.

  Each stage shows its real value. Fusion and policy only run at a payment attempt. A call from a reported number also shows a
  "Reported for fraud" badge on the incoming-call screen.
- **Risk timeline.** The line is the GRU's P(scam in progress) after each event. The diamonds are the fused payment risk the policy acted on.
- **Why this session.** All six fusion inputs and the model behind each. The fusion model's top positive SHAP contributors are marked; they are the reasons the customer reads.
- **Fraud cost vs. friction.** Expected fraud cost against the friction cost of a hold, and the expected value of each tier: `p·A·efficacy − (1−p)·friction`, with tier values from `ml/engine/policy.py`. Below are the fleet results from `ml/reports/engine.md`.
- **Which scam is this?** The typology head's distribution over the four scams, P(scam in progress) as a sparkline, and the model's stage against the simulator's ground truth.
- **Analyst case log.** What the system recorded, interleaved with analyst actions.
- **Event inspector.** The exact JSON sent to the API and returned by it, for any event.
- **Session timeline.** Ground-truth chapters against the model's stage, every event, the payment decisions, and the stretch the hold prevented.

## Design notes

The UI follows Apple's HIG dark appearance:
- **Colour:** system colours with one meaning each (green allow, yellow nudge, orange cool-off, red hold).
- **Type:** text styles with size-specific tracking.
- **Materials:** translucent, with a bright top edge. They become opaque under `prefers-reduced-transparency` / `prefers-contrast: more`.
- **Corners:** continuous via `corner-shape: squircle` where supported.
- **Motion:** springs everywhere (`src/config/motion.ts`). They are critically damped by default; the alert sheet uses the one slightly bouncy spring. Springs are interruptible, and `prefers-reduced-motion` is honoured.
- **Phone:** drawn at its logical 390 × 844 size and scaled as a whole to fit the pane.
