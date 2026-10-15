"""PRAMAAN in plain words, with a light technical layer: a ~60 s explainer for mixed audiences.

PRAMAAN = Parallel Risk-Adaptive Multi-modal Authentication & Anomaly Network (the transaction-authentication service in this repo).
Team CaffeineEaters: Abhinav Saini, Aditi Pundir, Mannat Kaur, Aryamann Sharma.

    python assemble_simple.py ql      # draft 480p15
    python assemble_simple.py qh      # final 1080p60
    python -m manim -ql simple_scenes.py Decides      # one beat

Storyboard (seconds are the budget each beat is written to):
    0 Intro     4  name, full form (initials lit), "proof" in Hindi, team
    1 Problem   7  one tap to pay / to lose money; SIM swap, stolen password, scam call; OTP checks a code
    2 Checks    8  tap Pay -> three checks in parallel (you? your phone? normal payment?), then the models behind them
    3 Decides  13  one real example (SIM swap, Rs 60,000): signals -> risk model -> score -> lowest expected loss
                   -> BLOCK -> tree-SHAP reasons in English and Hindi
    4 Answers  10  allow / challenge / block with Asha's other examples
    5 Models    9  models we train + their test results; measured latency; Google Cloud design
    6 End       8  who it is for; end card with team and members

Nothing on screen is hand-typed from memory:
    frontend/public/data/auth_demo.json   Asha's amounts, decisions, risk score, expected costs, reasons (EN/HI)
    ml/reports/auth.json                  fusion model ROC-AUC and simulated request count
    ml/reports/{biometrics_hmog,keystroke_cmu,tabular_ensemble,gnn_aml}.md   per-model test results
    backend/reports/auth_latency.md       measured p95 latency (laptop CPU, end to end over HTTP)
    ml/auth/features.py                   signal counts per family
The cloud is shown as the deploy design (docs/DEPLOY.md); it has not been benchmarked on Cloud Run.
"""
import json
import math
import pathlib
import re
import sys

from manim import (DOWN, LEFT, RIGHT, UL, UP, UR, Circle, Create, FadeIn, FadeOut, GrowFromEdge, Indicate,
                   MarkupText, RoundedRectangle, Scene, VGroup)
from manim.utils.rate_functions import ease_out_cubic

from style import (BLUE, CYAN, DECISION, FAINT, FAMILY, GREEN, INK, LINE, MUTED, ORANGE, PURPLE, RED, SURFACE,
                   SURFACE2, UI, Caption, T, arrow, box, card, clear, eyebrow, fit, flow_along, mono, pill)

REPO = pathlib.Path(__file__).resolve().parents[1]
REP = REPO / "ml" / "reports"
HINDI = "Nirmala UI"     # Windows' Devanagari font; Inter has no Devanagari glyphs

NAME = "PRAMAAN"
FULL = ["*Parallel", "*Risk-*Adaptive", "*Multi-modal", "*Authentication", "&", "*Anomaly", "*Network"]   # * = acronym letter
TEAM = "CaffeineEaters"
MEMBERS = ["Abhinav Saini", "Aditi Pundir", "Mannat Kaur", "Aryamann Sharma"]
TRACK = "FRONTIER 04 · Fast and Secure Online Transaction Authentication"

# ---------------------------------------------------------------------------- facts, read from the repo
DEMO = json.loads((REPO / "frontend/public/data/auth_demo.json").read_text(encoding="utf-8"))["runs"]
AUTH = json.loads((REP / "auth.json").read_text())
sys.path.insert(0, str(REPO))
from ml.auth.features import FAMILY as FEAT_FAMILY, FEATURES  # noqa: E402

N_SIGNALS = len(FEATURES)
N_FAM = {f: sum(FEAT_FAMILY[x] == f for x in FEATURES) for f in ("behaviour", "device", "transaction")}


def md_cells(path, row_start):
    for line in (REP / path).read_text(encoding="utf-8").splitlines():
        if line.startswith(row_start):
            return [c.strip() for c in line.strip().strip("|").split("|")]
    raise SystemExit(f"row not found in {path}: {row_start}")


def first_num(cell):
    return float(re.match(r"[\d.]+", cell).group(0))


EER_TOUCH = first_num(md_cells("biometrics_hmog.md", "| 10 gestures | BiLSTM + LDA score fusion")[2])
EER_TYPING = first_num(md_cells("keystroke_cmu.md", "| 1D-CNN embedding (ours)")[1])
AUC_CARD = first_num(md_cells("tabular_ensemble.md", "| stack_lr(cat+lgb+xgb) | causal")[2])
AUC_GNN = first_num(md_cells("gnn_aml.md", "| Temporal GNN, diff attention")[6])
AUC_FUSION = AUTH["ranking"]["risk engine (all signals)"]["roc_auc"]
SIM_REQUESTS = AUTH["data"]["requests"]
LAT = {m.group(1): float(m.group(2)) for m in re.finditer(
    r"\| POST /v1/authenticate \((.+?)\) \| \d+ \| [\d.]+ \| ([\d.]+) \|",
    (REPO / "backend/reports/auth_latency.md").read_text())}
P95_PLAIN, P95_TOUCH = LAT["no touch data"], LAT["+10 touch gestures verified"]


def run(name):
    return DEMO[name]["response"]


def amount(name):
    r = DEMO[name]
    return r["response"].get("amount", r.get("amount"))


def rupees(x):
    return f"₹{int(round(x)):,}"


ROUTINE, NEWPHONE, COACHED, SIMSWAP = "genuine_routine", "genuine_new_phone", "coerced", "sim_swap"
assert run(ROUTINE)["decision"] == "allow"
assert run(NEWPHONE)["decision"] == "challenge" and run(NEWPHONE)["challenge_type"] == "passkey"
assert run(COACHED)["decision"] == "challenge" and run(COACHED)["challenge_type"] == "bank_callback"
assert "unknown_call_active" in {x["signal"] for x in run(COACHED)["reasons"]}
SW = run(SIMSWAP)
assert SW["decision"] == "block" and SW["rule"] is None          # the block comes from the cost comparison, not a rule
assert [x["signal"] for x in SW["reasons"][:3]] == ["device_new", "typing_dev", "amt_z"]
assert min((k for k, v in SW["expected_cost"].items() if v is not None), key=lambda k: SW["expected_cost"][k]) == "block"
assert P95_TOUCH < 100

DEMO_TAG = "example from our working prototype · demo customer"
SHORT = {"device_new": "new device on the account", "typing_dev": "typing rhythm ≠ owner's",
         "amt_z": "amount far above usual"}


# ---------------------------------------------------------------------------- drawing helpers
def phone(w=1.9, h=3.4, stroke=INK):
    body = RoundedRectangle(width=w, height=h, corner_radius=0.28, stroke_width=2.2, stroke_color=stroke,
                            fill_color=SURFACE, fill_opacity=1)
    notch = RoundedRectangle(width=0.5, height=0.08, corner_radius=0.04, stroke_width=0, fill_color=LINE,
                             fill_opacity=1).move_to(body.get_top() + DOWN * 0.2)
    return VGroup(body, notch)


def pay_screen(ph, amt, to="send money"):
    a = T(amt, 30, INK, weight="BOLD")
    who = T(to, 14, MUTED)
    btn_r = RoundedRectangle(width=1.35, height=0.46, corner_radius=0.23, stroke_width=0, fill_color=BLUE, fill_opacity=1)
    btn = VGroup(btn_r, T("Pay", 18, INK, weight="BOLD").move_to(btn_r))
    g = VGroup(a, who, btn).arrange(DOWN, buff=0.22)
    fit(g, ph[0].width - 0.3)
    g.move_to(ph[0])
    return g


def icon_touch(color=PURPLE):
    return VGroup(Circle(0.1, color=color, fill_color=color, fill_opacity=1, stroke_width=0),
                  Circle(0.21, color=color, stroke_width=2),
                  Circle(0.32, color=color, stroke_width=1.5).set_stroke(opacity=0.6))


def icon_phone(color=CYAN):
    body = RoundedRectangle(width=0.4, height=0.66, corner_radius=0.07, stroke_width=2.2, stroke_color=color)
    dot = Circle(0.03, color=color, fill_opacity=1).move_to(body.get_bottom() + UP * 0.09)
    return VGroup(body, dot)


def icon_money(color=ORANGE):
    ring = Circle(0.32, color=color, stroke_width=2.2)
    return VGroup(ring, T("₹", 21, color, weight="BOLD").move_to(ring))


def full_form(size=28):
    """The full form with each initial lit in blue, so PRAMAAN can be read off it."""
    text = " ".join(FULL).replace("&", "&amp;")
    text = re.sub(r"\*(\w)", lambda m: f'<span foreground="{BLUE}" weight="bold">{m.group(1)}</span>', text)
    assert re.sub(r"<[^>]+>", "", text).count("*") == 0
    return MarkupText(text, font=UI, font_size=size, color=MUTED)


def check_card(icon, q, sub, chip, color, w=8.7, h=1.5):
    """Card + its model chip; the chip's line is laid out from the start and shown later."""
    rect = card(w, h, SURFACE, color, 0.22)
    tech = pill(chip, color, fill=SURFACE2, size=14)
    txt = VGroup(T(q, 24, INK, weight="BOLD"), T(sub, 16, MUTED), tech).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
    row = VGroup(icon, txt).arrange(RIGHT, buff=0.3)
    row.move_to(rect).align_to(rect, LEFT).shift(RIGHT * 0.3)
    txt.remove(tech)
    return VGroup(rect, icon, txt), tech


def example(situation, outcome, color, w=9.4):
    s = fit(T(situation, 22, INK), w)
    o = fit(T("→ " + outcome, 20, color), w)
    return VGroup(s, o).arrange(DOWN, aligned_edge=LEFT, buff=0.08)


def corner_tag(text):
    return mono(text, 13, MUTED).to_corner(UR, buff=0.2)


# ---------------------------------------------------------------------------- 0 · intro (4 s)
def beat_intro(s: Scene, cap: Caption):
    name = T(NAME, 96, INK, weight="BOLD").move_to(UP * 1.25)
    full = fit(full_form(28), 12.6).next_to(name, DOWN, buff=0.35)
    hindi = T("प्रमाण  =  “proof”", 22, FAINT, font=HINDI).next_to(full, DOWN, buff=0.3)
    team = VGroup(eyebrow("team", BLUE, 14), T(TEAM, 26, BLUE, weight="BOLD")).arrange(DOWN, buff=0.1)
    team.next_to(hindi, DOWN, buff=0.55)
    s.play(FadeIn(name, scale=0.94), run_time=0.6)
    s.play(FadeIn(full, shift=UP * 0.08), run_time=0.6)
    s.play(FadeIn(hindi), FadeIn(team, shift=UP * 0.08), run_time=0.5)
    s.wait(2.3)


# ---------------------------------------------------------------------------- 1 · the problem (7 s)
def beat_problem(s: Scene, cap: Caption):
    ident = eyebrow(f"{NAME} · team {TEAM}", BLUE, 14).to_corner(UL, buff=0.35)
    ph = phone().move_to(LEFT * 4.6 + UP * 0.55)
    scr = pay_screen(ph, rupees(amount(SIMSWAP)))
    s.add(ident, ph, scr)
    cap.say("Paying online takes one tap. So can losing your money.", "the problem")
    threats = VGroup(*[VGroup(T(t, 26, RED, weight="BOLD"), T(d, 19, MUTED)).arrange(DOWN, aligned_edge=LEFT, buff=0.06)
                       for t, d in (("SIM swap", "a fraudster takes over your phone number"),
                                    ("Stolen password", "someone else logs in as you"),
                                    ("Scam call", "a caller talks you into paying"))]).arrange(DOWN, aligned_edge=LEFT, buff=0.4)
    threats.move_to(RIGHT * 1.9 + UP * 0.9)
    lines = [arrow(t.get_left() + LEFT * 0.15, ph.get_right() + RIGHT * 0.1, RED, 1.6) for t in threats]
    s.play(FadeIn(threats, lag_ratio=0.35, shift=LEFT * 0.15), *[Create(a) for a in lines], run_time=1.3)
    s.wait(1.1)
    cap.say("Today's main check is an OTP. It checks a code, not the person.")
    otp = pill("OTP  ✓", GREEN, size=20, weight="BOLD").next_to(ph, DOWN, buff=0.3)
    note = T("…but a SIM-swapper or a scam caller can still get past it", 20, ORANGE)
    fit(note, 6.9).next_to(threats, DOWN, buff=0.45).align_to(threats, LEFT)
    s.play(FadeIn(otp, shift=UP * 0.1), FadeIn(note, shift=UP * 0.08), run_time=0.5)
    s.wait(0.6)
    loss = VGroup(T("₹22,845 crore", 34, INK, weight="BOLD"),
                  T("lost to cyber fraud in India in 2024", 17, MUTED),
                  mono("source: MHA reply in Lok Sabha, July 2025", 12, MUTED)).arrange(DOWN, aligned_edge=LEFT, buff=0.06)
    loss.next_to(note, DOWN, buff=0.35).align_to(threats, LEFT)
    s.play(FadeIn(loss, shift=UP * 0.08), run_time=0.5)
    s.wait(1.6)


# ---------------------------------------------------------------------------- 2 · three checks in parallel (8 s)
def beat_checks(s: Scene, cap: Caption):
    ph = phone().move_to(LEFT * 5.6 + UP * 0.55)
    scr = pay_screen(ph, rupees(amount(SIMSWAP)))
    specs = [(icon_touch(), "Is it really you?", "how you tap, swipe and type",
              f"{N_FAM['behaviour']} signals · BiLSTM touch + CNN typing models", FAMILY["behaviour"]),
             (icon_phone(), "Is this your phone?", "known phone, fresh SIM, emulator, VPN, location jump",
              f"{N_FAM['device']} signals · device, SIM and network checks", FAMILY["device"]),
             (icon_money(), "Is the payment normal?", "amount vs usual, spending speed, who you pay",
              f"{N_FAM['transaction']} signals · spending history + payee-risk model", FAMILY["transaction"])]
    cards, chips = VGroup(), VGroup()
    for ic, q, sub, chip, col in specs:
        c, t = check_card(ic, q, sub, chip, col)
        cards.add(c)
        chips.add(t)
    offsets = [t.get_center() - c.get_center() for c, t in zip(cards, chips)]
    cards.arrange(DOWN, buff=0.2).move_to(RIGHT * 1.35 + UP * 0.6)
    for c, t, off in zip(cards, chips, offsets):
        t.move_to(c.get_center() + off)
    fans = [arrow(ph.get_right(), c.get_left(), c[0].get_stroke_color(), 1.8) for c in cards]

    s.add(ph, scr)
    cap.say(f"Meet {NAME}: tap Pay, and three checks run in parallel", "how it works")
    s.play(Indicate(scr[2], color=INK, scale_factor=1.12), run_time=0.5)
    s.play(*[Create(a) for a in fans], FadeIn(cards, lag_ratio=0.15, shift=RIGHT * 0.15), run_time=1.1)
    anims = []
    for c, a in zip(cards, fans):
        an, dots = flow_along(a.get_start(), a.get_end(), c[0].get_stroke_color(), n=2, run_time=0.6)
        s.add(*dots)
        anims.append(an)
    s.play(*anims, run_time=0.8)
    s.wait(1.4)
    cap.say(f"{N_SIGNALS} live signals, read by trained AI models")
    s.play(FadeIn(chips, lag_ratio=0.2, shift=UP * 0.06), run_time=0.7)
    s.wait(2.6)


# ---------------------------------------------------------------------------- 3 · how it decides, one real example (13 s)
def beat_decides(s: Scene, cap: Caption):
    tag = corner_tag(DEMO_TAG)
    y = 2.35
    rows = VGroup()
    for x in SW["reasons"][:3]:
        dot = Circle(0.07, color=FAMILY[x["family"]], fill_opacity=1, stroke_width=0)
        rows.add(VGroup(dot, T(SHORT[x["signal"]], 18, INK)).arrange(RIGHT, buff=0.18))
    rows.arrange(DOWN, aligned_edge=LEFT, buff=0.16)
    sig = VGroup(eyebrow("signals that fired", FAINT, 12), rows).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
    sig.move_to([-6.75, y, 0], aligned_edge=LEFT)
    model = box("Risk model", "monotone XGBoost", w=2.5, h=1.1, stroke=INK, size=22, sub_size=15).move_to([-1.35, y, 0])
    score = VGroup(T(f"{100 * SW['risk_score']:.0f}%", 46, RED, weight="BOLD"), T("risk score", 16, MUTED)
                   ).arrange(DOWN, buff=0.06).move_to([1.55, y, 0])
    verdict = pill("BLOCK", RED, size=26, weight="BOLD").move_to([5.6, y, 0])
    a1 = arrow(sig.get_right() + RIGHT * 0.1, model.get_left(), MUTED, 1.8)
    a2 = arrow(model.get_right(), score.get_left() + LEFT * 0.1, MUTED, 1.8)
    a3 = arrow(score.get_right() + RIGHT * 0.1, verdict.get_left(), RED, 1.8)

    cap.say(f"Real example: a fraudster with Asha's swapped SIM tries {rupees(amount(SIMSWAP))}", "how it decides")
    s.play(FadeIn(tag), FadeIn(sig, lag_ratio=0.2, shift=RIGHT * 0.1), run_time=0.7)
    s.wait(1.2)
    cap.say("A trained risk model fuses every signal into one risk score")
    s.play(Create(a1), FadeIn(model), run_time=0.5)
    an, dots = flow_along(a1.get_start(), a1.get_end(), BLUE, n=3, run_time=0.5)
    s.add(*dots)
    s.play(an, run_time=0.6)
    s.play(Create(a2), FadeIn(score, scale=0.9), run_time=0.5)
    s.wait(1.0)

    cap.say("The policy picks the action with the lowest expected loss")
    cost = SW["expected_cost"]
    top = max(v for v in cost.values() if v is not None)
    bars = VGroup()
    for k in ("allow", "challenge", "block"):
        v = cost[k]
        lab = T(k, 18, DECISION[k], weight="BOLD")
        track = RoundedRectangle(width=5.2, height=0.3, corner_radius=0.15, stroke_width=0, fill_color=SURFACE2, fill_opacity=1)
        bar = RoundedRectangle(width=max(0.08, 5.2 * v / top), height=0.3, corner_radius=0.15, stroke_width=0,
                               fill_color=DECISION[k], fill_opacity=1)
        val = T(rupees(v), 18, INK if k == "block" else MUTED, weight="BOLD" if k == "block" else "NORMAL")
        bars.add(VGroup(lab, track, bar, val))
    for i, (lab, track, bar, val) in enumerate(bars):
        yy = 0.55 - i * 0.55
        lab.move_to([-3.6, yy, 0], aligned_edge=LEFT)
        track.move_to([-1.7, yy, 0], aligned_edge=LEFT)
        bar.move_to([-1.7, yy, 0], aligned_edge=LEFT)
        val.next_to(track, RIGHT, buff=0.25)
    head = eyebrow("expected loss if we…", FAINT, 12).move_to([-3.6, 1.1, 0], aligned_edge=LEFT)
    foot = mono("loss = risk × amount, or the cost of stopping a genuine payer (our assumed values)", 12, MUTED)
    foot.move_to([-3.6, -1.1, 0], aligned_edge=LEFT)
    pick = RoundedRectangle(width=bars[2].width + 0.35, height=0.5, corner_radius=0.12, stroke_width=2.5,
                            stroke_color=RED).move_to(bars[2])
    s.play(FadeIn(head), *[FadeIn(b[0]) for b in bars], *[FadeIn(b[1]) for b in bars], FadeIn(foot), run_time=0.4)
    s.play(*[GrowFromEdge(b[2], LEFT) for b in bars], *[FadeIn(b[3]) for b in bars], run_time=0.8, rate_func=ease_out_cubic)
    s.play(Create(pick), Create(a3), FadeIn(verdict, scale=0.9), run_time=0.6)
    s.wait(1.1)

    cap.say("tree-SHAP turns the score into reasons, in English and Hindi")
    cost_grp = VGroup(head, bars, foot, pick)
    top_c = max(x["contribution"] for x in SW["reasons"][:3])
    items = VGroup()
    for x in SW["reasons"][:3]:
        col = FAMILY[x["family"]]
        track = RoundedRectangle(width=1.6, height=0.22, corner_radius=0.11, stroke_width=0, fill_color=SURFACE2,
                                 fill_opacity=1)
        shap = RoundedRectangle(width=1.6 * x["contribution"] / top_c, height=0.22, corner_radius=0.11, stroke_width=0,
                                fill_color=col, fill_opacity=1).align_to(track, LEFT)
        txt = VGroup(T(x["text_en"].capitalize(), 20, INK), T(x["text_hi"], 18, MUTED, font=HINDI)
                     ).arrange(DOWN, aligned_edge=LEFT, buff=0.04)
        items.add(VGroup(VGroup(track, shap), txt).arrange(RIGHT, buff=0.35))
    items.arrange(DOWN, aligned_edge=LEFT, buff=0.22)
    reasons = VGroup(eyebrow("why: each signal's push on the risk (tree-SHAP)", FAINT, 12), items
                     ).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    fit(reasons, 12.6).move_to([-6.75, -0.75, 0], aligned_edge=LEFT)
    s.play(FadeOut(cost_grp), run_time=0.3)
    s.play(FadeIn(reasons[0]), FadeIn(items, lag_ratio=0.25, shift=UP * 0.06), run_time=0.9)
    s.wait(2.4)


# ---------------------------------------------------------------------------- 4 · three outcomes (10 s)
def beat_answers(s: Scene, cap: Caption):
    tag = corner_tag("examples from our working prototype · demo customer")
    keys = ("allow", "challenge", "block")
    pills = {k: pill(k.upper(), DECISION[k], size=22, weight="BOLD") for k in keys}
    f = 2.4 / pills["challenge"].width                                  # one scale for all; CHALLENGE is the widest
    for p in pills.values():
        p.scale(f)
    x_pill, x_text = -6.5, -3.4
    rows = {
        "allow": VGroup(example(f"Asha's usual {rupees(amount(ROUTINE))} payment",
                                "approved instantly, no OTP to wait for", GREEN)),
        "challenge": VGroup(example(f"Asha pays {rupees(amount(NEWPHONE))} from her new phone",
                                    "confirms with her fingerprint or face on her registered phone", ORANGE),
                            example(f"Asha sends {rupees(amount(COACHED))} while on a call with an unknown number",
                                    "her bank calls her back first, with a scam warning", ORANGE)
                            ).arrange(DOWN, aligned_edge=LEFT, buff=0.3),
        "block": VGroup(example(f"A fraudster who swapped Asha's SIM tries {rupees(amount(SIMSWAP))}",
                                "blocked before any money moves", RED)),
    }
    ys = {"allow": 2.55, "challenge": 0.55, "block": -1.6}
    for k in keys:
        rows[k].move_to([x_text, ys[k], 0], aligned_edge=LEFT)
        pills[k].move_to([x_pill, rows[k].get_center()[1], 0], aligned_edge=LEFT)

    cap.say("Everything normal? The payment just goes through, no OTP.", "three possible answers")
    s.play(FadeIn(tag), FadeIn(pills["allow"], shift=RIGHT * 0.1), FadeIn(rows["allow"], shift=RIGHT * 0.1), run_time=0.6)
    s.wait(1.9)
    cap.say("Unusual? One quick extra check that fits the situation.")
    s.play(FadeIn(pills["challenge"], shift=RIGHT * 0.1), FadeIn(rows["challenge"], lag_ratio=0.3, shift=RIGHT * 0.1),
           run_time=0.8)
    s.wait(3.0)
    cap.say("Clearly an attack? Blocked before the money moves.")
    s.play(FadeIn(pills["block"], shift=RIGHT * 0.1), FadeIn(rows["block"], shift=RIGHT * 0.1), run_time=0.6)
    s.wait(1.9)


# ---------------------------------------------------------------------------- 5 · models we train, speed, cloud (9 s)
def beat_models(s: Scene, cap: Caption):
    rows = [("Touch rhythm", "BiLSTM + LDA", "HMOG · real phone gestures", f"{EER_TOUCH:.1f}% EER", PURPLE),
            ("Typing rhythm", "1D-CNN", "CMU · real keystrokes", f"{EER_TYPING:.1f}% EER", PURPLE),
            ("Card fraud", "CatBoost + LightGBM + XGBoost", "IEEE-CIS · card payments", f"{AUC_CARD:.2f} AUC", ORANGE),
            ("Mule rings", "temporal graph network", "IBM AML · bank transfers", f"{AUC_GNN:.2f} AUC", ORANGE),
            ("Fusion", "monotone XGBoost", f"{SIM_REQUESTS / 1000:.0f}k simulated requests", f"{AUC_FUSION:.3f} AUC", BLUE)]
    table = VGroup()
    for what, mdl, data, res, col in rows:
        left = VGroup(VGroup(T(what, 19, INK, weight="BOLD"), T(mdl, 16, col)).arrange(RIGHT, buff=0.2),
                      T(data, 14, MUTED)).arrange(DOWN, aligned_edge=LEFT, buff=0.04)
        table.add(VGroup(left, T(res, 20, INK, weight="BOLD")))
    for i, r in enumerate(table):
        yy = 2.45 - i * 0.82
        r[0].move_to([-6.75, yy, 0], aligned_edge=LEFT)
        r[1].move_to([1.0, yy, 0], aligned_edge=RIGHT)
    title = eyebrow("models we train · tested on held-out data", FAINT, 12).move_to([-6.75, 3.3, 0], aligned_edge=LEFT)
    key = mono("EER: how often it mixes up two people (lower is better) · AUC: 1.0 = perfect ranking of fraud", 12, MUTED)
    fit(key, 7.8).move_to([-6.75, -1.75, 0], aligned_edge=LEFT)

    speed = VGroup(T(f"{P95_TOUCH:.0f} ms", 54, GREEN, weight="BOLD"),
                   T("95% of decisions, end to end,", 16, MUTED),
                   T("touch check included", 16, MUTED),
                   T(f"{P95_PLAIN:.0f} ms without touch data", 16, MUTED)).arrange(DOWN, aligned_edge=LEFT, buff=0.06)
    speed.move_to([2.0, 2.2, 0], aligned_edge=LEFT)
    measured = mono("measured on a laptop CPU over HTTP", 12, MUTED).next_to(speed, DOWN, buff=0.12, aligned_edge=LEFT)
    cloud = VGroup(T("Built for Google Cloud (Mumbai)", 17, BLUE, weight="BOLD"),
                   *[T(x, 16, INK) for x in ("Cloud Run: the risk API", "Redis: live memory of users & devices",
                                              "Postgres: audit log of every decision", "target: under 100 ms per payment")]
                   ).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
    cloud.move_to([2.0, -0.9, 0], aligned_edge=LEFT)

    cap.say("The models we train, each tested on public or simulated data", "models and speed")
    s.play(FadeIn(title), FadeIn(table, lag_ratio=0.15, shift=UP * 0.06), run_time=1.0)
    s.play(FadeIn(key), run_time=0.3)
    s.wait(2.0)
    cap.say(f"95% of decisions finish within {math.ceil(P95_TOUCH)} ms, built for Google Cloud")
    s.play(FadeIn(speed, shift=UP * 0.08), FadeIn(measured), run_time=0.5)
    s.play(FadeIn(cloud, lag_ratio=0.15), run_time=0.6)
    s.wait(2.6)


# ---------------------------------------------------------------------------- 6 · who it is for + end card (8 s)
def beat_end(s: Scene, cap: Caption):
    cap.say("For banks and UPI apps: plug in once, protect every payment", "who it's for")
    users = VGroup(*[pill(x, INK, size=20) for x in ("Banks", "UPI & payment apps", "Online shops")]).arrange(DOWN, buff=0.3)
    users.move_to(LEFT * 4.7 + UP * 0.55)
    core = box(NAME, "", w=3.2, h=1.2, stroke=BLUE, size=36).move_to(UP * 0.55)
    outs = VGroup(*[pill(k.upper(), DECISION[k], size=20, weight="BOLD") for k in ("allow", "challenge", "block")])
    outs.arrange(DOWN, buff=0.3).move_to(RIGHT * 4.7 + UP * 0.55)
    a_in = [arrow(u.get_right(), core.get_left(), MUTED, 1.6) for u in users]
    a_out = [arrow(core.get_right(), o.get_left(), DECISION[k], 1.6) for o, k in zip(outs, ("allow", "challenge", "block"))]
    s.play(FadeIn(users, lag_ratio=0.2), run_time=0.4)
    s.play(*[Create(a) for a in a_in], FadeIn(core), run_time=0.4)
    s.play(*[Create(a) for a in a_out], FadeIn(outs, lag_ratio=0.2), run_time=0.5)
    s.wait(1.2)
    cap.hide(run_time=0.3)
    clear(s, run_time=0.3)
    name = T(NAME, 72, INK, weight="BOLD")
    full = fit(full_form(22), 11.5)
    line = fit(T("Stops payment fraud before the money moves, with a reason for every decision.", 22, INK), 12.5)
    team = VGroup(T(f"Team {TEAM}", 26, BLUE, weight="BOLD"),
                  T("   ·   ".join(MEMBERS), 20, MUTED)).arrange(DOWN, buff=0.14)
    track = T(TRACK, 14, FAINT)
    VGroup(name, full, line, team, track).arrange(DOWN, buff=0.32).move_to(UP * 0.1)
    team.shift(DOWN * 0.15)
    track.shift(DOWN * 0.3)
    s.play(FadeIn(name, scale=0.95), FadeIn(full), run_time=0.5)
    s.play(FadeIn(line, shift=UP * 0.08), run_time=0.4)
    s.play(FadeIn(team, shift=UP * 0.08), FadeIn(track), run_time=0.5)
    s.wait(2.6)
    s.play(*[FadeOut(m) for m in s.mobjects], run_time=0.5)


BEATS = [("Intro", beat_intro), ("Problem", beat_problem), ("Checks", beat_checks), ("Decides", beat_decides),
         ("Answers", beat_answers), ("Models", beat_models), ("End", beat_end)]
NAMES = [n for n, _ in BEATS]


def _make(fn, last):
    def construct(self):
        cap = Caption(self)
        fn(self, cap)
        if not last:
            clear(self, keep=(), run_time=0.3)
    return construct


for _i, (_name, _fn) in enumerate(BEATS):
    globals()[_name] = type(_name, (Scene,), {"construct": _make(_fn, _i == len(BEATS) - 1)})
