"""PRAMAAN · FRONTIER 04 screening video: 60 s explainer of the transaction-authentication service.

    python assemble.py ql      # draft 480p15
    python assemble.py qh      # final 1080p60
    python -m manim -ql scenes.py Approach      # one beat

Every number on screen is read at render time from the project's own outputs (no hand-copied figures):
    ml/reports/auth.json               simulated evaluation (designs, per-scenario, ROC-AUC)
    backend/reports/auth_latency.md    measured HTTP latency
    frontend/public/data/auth_demo.json   recorded API decisions for the demo customer (local run)
External figures (₹22,845 crore, RBI directions) are cited on screen.
"""
import json
import pathlib
import re

from manim import (DOWN, LEFT, ORIGIN, RIGHT, UL, UP, UR, Circle, Create, DashedVMobject, FadeIn, FadeOut, GrowFromEdge,
                   Line, Rectangle, RoundedRectangle, Scene, Text, VGroup, Write, config, smooth)
from manim.utils.rate_functions import ease_out_cubic

from style import (BG, BLUE, CYAN, DECISION, ELEV, FAINT, GREEN, INDIGO, INK, LINE, MONO, MUTED, ORANGE, PURPLE, RED,
                   SURFACE, SURFACE2, UI, YELLOW, Caption, Shot, T, arrow, box, card, clear, eyebrow, fit, flow_along,
                   mono, pill)

REPO = pathlib.Path(__file__).resolve().parents[1]
R = json.loads((REPO / "ml/reports/auth.json").read_text())
DEMO = json.loads((REPO / "frontend/public/data/auth_demo.json").read_text(encoding="utf-8"))["runs"]
LAT = {m.group(1): float(m.group(2)) for m in re.finditer(
    r"\| POST /v1/authenticate \((.+?)\) \| \d+ \| [\d.]+ \| ([\d.]+) \|", (REPO / "backend/reports/auth_latency.md").read_text())}
D = R["designs"]
ENG, OTP, RULES = D["risk engine (all signals)"], D["SMS OTP on every payment"], D["rules engine + SMS OTP"]
P95_PLAIN = LAT["no touch data"]
P95_TOUCH = LAT["+10 touch gestures verified"]


def pct(x, nd=1):
    return f"{x:.{nd}f}%"


def risk(scn):
    return f"{100 * DEMO[scn]['response']['risk_score']:.1f}%"


def rupees(x):
    s = f"{int(round(x)):,}"
    return f"₹{s}"


# ---------------------------------------------------------------------------- 1 · problem (8 s)
def phone(label, color=MUTED):
    body = RoundedRectangle(width=1.25, height=2.3, corner_radius=0.22, stroke_width=2, stroke_color=color,
                            fill_color=SURFACE, fill_opacity=1)
    notch = RoundedRectangle(width=0.4, height=0.07, corner_radius=0.035, stroke_width=0, fill_color=LINE,
                             fill_opacity=1).move_to(body.get_top() + DOWN * 0.15)
    name = T(label, 18, color).next_to(body, DOWN, buff=0.15)
    return VGroup(body, notch, name)


def sim_chip(color=YELLOW):
    r = RoundedRectangle(width=0.42, height=0.55, corner_radius=0.06, stroke_width=1.5, stroke_color=color,
                         fill_color=ELEV, fill_opacity=1)
    t = T("SIM", 12, color, weight="BOLD").move_to(r)
    return VGroup(r, t)


def beat_problem(s: Scene, cap: Caption):
    ident = VGroup(eyebrow("PRAMAAN · FRONTIER 04", BLUE, 14),
                   T("Fast and secure online transaction authentication", 17, MUTED)).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
    s.add(ident.to_corner(UL, buff=0.35))          # visible from the first frame
    asha = phone("Asha · Ludhiana", INK).move_to(LEFT * 4.6 + UP * 0.9)
    crook = phone("fraudster", RED).move_to(RIGHT * 4.6 + UP * 0.9)
    bank = box("Bank", "sends an SMS OTP", w=2.3, h=0.9).move_to(UP * 2.9)
    sim = sim_chip().move_to(asha[0].get_center() + DOWN * 0.3)
    s.add(asha, crook, bank, sim)                 # the first frame already shows the story, not black
    cap.say("A fraudster swaps Asha's SIM, and her OTP goes with it", "1 · the problem")
    s.wait(0.4)
    s.play(sim.animate.move_to(crook[0].get_center() + DOWN * 0.3), run_time=1.0, rate_func=smooth)
    otp = pill("OTP 482913", BLUE, size=16, font=MONO).move_to(bank.get_bottom() + DOWN * 0.35)
    s.play(FadeIn(otp, shift=DOWN * 0.1), run_time=0.3)
    s.play(otp.animate.move_to(crook[0].get_center() + UP * 0.45), run_time=0.8, rate_func=ease_out_cubic)
    ok = T("✓ OTP check passed", 20, GREEN, weight="BOLD").next_to(crook, DOWN, buff=0.2)
    s.play(FadeIn(ok, shift=UP * 0.1), run_time=0.4)
    s.wait(0.8)
    cap.say("SMS OTP is beaten by SIM swap, OTP phishing and coached users")
    otp_pill = pill("SMS OTP", MUTED, size=20).move_to(ORIGIN + UP * 0.9)
    strike = Line(otp_pill.get_left() + LEFT * 0.1, otp_pill.get_right() + RIGHT * 0.1, color=RED, stroke_width=4)
    holes = VGroup(*[pill(x, RED, size=15) for x in ("SIM swap", "OTP phishing", "coached user")]).arrange(DOWN, buff=0.15)
    holes.next_to(otp_pill, DOWN, buff=0.35)
    s.play(FadeIn(otp_pill), run_time=0.3)
    s.play(Create(strike), FadeIn(holes, lag_ratio=0.25), run_time=0.8)
    loss = VGroup(T("₹22,845 crore", 40, INK, weight="BOLD"),
                  T("lost to cyber fraud in India in 2024", 18, MUTED),
                  mono("source: MHA reply in Lok Sabha, July 2025", 14, MUTED)).arrange(DOWN, buff=0.08)
    loss.move_to(DOWN * 2.05)
    s.play(FadeIn(loss, shift=UP * 0.1), run_time=0.6)
    s.wait(1.45)


# ---------------------------------------------------------------------------- 2 · approach (10 s)
def family(title, n, color, lines):
    rect = card(3.05, 1.45, SURFACE, color, 0.18)
    head = VGroup(T(title, 19, color, weight="BOLD"), T(str(n), 15, color, font=MONO)).arrange(RIGHT, buff=0.15)
    body = VGroup(*[T(x, 13, MUTED) for x in lines]).arrange(DOWN, aligned_edge=LEFT, buff=0.05)
    g = VGroup(head, body).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
    fit(g, 2.75)
    g.move_to(rect).align_to(rect, LEFT).shift(RIGHT * 0.16)
    return VGroup(rect, g)


def beat_approach(s: Scene, cap: Caption):
    cap.say("One call: POST /v1/authenticate → allow, challenge or block", "2 · our approach")
    req = box("POST", "/v1/authenticate", w=1.85, h=1.0, stroke=BLUE).move_to(LEFT * 5.95 + UP * 0.55)
    fams = VGroup(
        family("Behaviour", 5, PURPLE, ["touch vs owner (BiLSTM, real HMOG)", "scripted input · unknown call", "screen share"]),
        family("Device", 13, CYAN, ["new device · SIM changed", "emulator · remote-access app", "VPN / hosting IP · impossible travel"]),
        family("Transaction", 8, ORANGE, ["amount vs usual · new payee", "payee risk · 24 h spend", "failed challenges"]),
    ).arrange(DOWN, buff=0.18).move_to(LEFT * 2.75 + UP * 0.55)
    model = box("Monotone XGBoost", "one risk score · tree-SHAP", w=2.5, h=1.15, stroke=INK).move_to(RIGHT * 0.65 + UP * 0.55)
    state = box("Live state", "user · device · IP history", w=2.6, h=0.8, stroke=LINE, size=16, sub_size=12)
    state.next_to(model, DOWN, buff=0.45)
    policy = box("Policy", "picks the right challenge", w=2.05, h=1.0, stroke=INK, size=19).move_to(RIGHT * 3.3 + UP * 0.55)
    pills = VGroup(*[pill(k.upper(), DECISION[k], size=15, weight="BOLD") for k in ("allow", "challenge", "block")])
    pills.arrange(DOWN, buff=0.16).move_to(RIGHT * 5.75 + UP * 0.55)
    rbi = mono("RBI Authentication Directions 2025: behaviour, device, location, history", 14, MUTED)
    rbi.to_corner(UR, buff=0.3)

    s.play(FadeIn(req, shift=RIGHT * 0.2), run_time=0.5)
    a1 = [arrow(req.get_right(), f.get_left(), MUTED, 1.6) for f in fams]
    s.play(*[Create(a) for a in a1], FadeIn(fams, lag_ratio=0.2), run_time=1.0)
    s.wait(0.9)
    cap.say("26 signals: behaviour 5 · device 13 · transaction 8")
    a2 = [arrow(f.get_right(), model.get_left(), MUTED, 1.6) for f in fams]
    a3 = arrow(state.get_top(), model.get_bottom(), FAINT, 1.4)
    s.play(*[Create(a) for a in a2], FadeIn(model), FadeIn(state), Create(a3), FadeIn(rbi), run_time=0.9)
    anims = []
    for f in fams:
        an, dots = flow_along(f.get_right(), model.get_left(), f[0].get_stroke_color(), n=2, run_time=0.7)
        s.add(*dots)
        anims.append(an)
    s.play(*anims, run_time=0.9)
    s.wait(0.7)
    cap.say("Policy picks allow, challenge or block, and returns the reasons")
    a4 = arrow(model.get_right(), policy.get_left(), MUTED, 1.6)
    a5 = [arrow(policy.get_right(), p.get_left(), DECISION[k], 1.6) for p, k in zip(pills, ("allow", "challenge", "block"))]
    s.play(Create(a4), FadeIn(policy), run_time=0.5)
    s.play(*[Create(a) for a in a5], FadeIn(pills, lag_ratio=0.2), run_time=0.7)
    out = mono("{ decision, risk_score, challenge_type, reasons EN + HI, signals[], latency_ms }", 16, MUTED)
    out.next_to(VGroup(req, pills), DOWN, buff=0.15).set_x(0).set_y(-2.45)
    s.play(FadeIn(out, shift=UP * 0.08), run_time=0.5)
    s.wait(1.15)


# ---------------------------------------------------------------------------- 3 · attacks blocked, with reasons (9 s)
LOCAL = "recorded from the API · local run"


def show_shot(s, cap, name, prev=None):
    """A console screenshot cropped at panel boundaries (crop_shots.py), filling the content area."""
    from manim import Group
    shot = Shot(f"crops/{name}", top_margin=0.45, bottom_margin=1.15)
    tag = mono(LOCAL, 13, MUTED).to_corner(UR, buff=0.12)
    if prev is not None:
        s.play(FadeOut(prev), run_time=0.25)
    s.play(FadeIn(shot), FadeIn(tag), run_time=0.4)
    return Group(shot, tag)


def mark(g, name, key, color, stroke=4):
    """Callout on a cropped shot; regions.json boxes are in full-screenshot pixels."""
    cx, cy = SHOT_REGIONS[name]["crop"][:2]
    x0, y0, x1, y1 = SHOT_REGIONS[name][key]
    return g[0].box(x0 - cx, y0 - cy, x1 - cx, y1 - cy, color=color, stroke=stroke)


def beat_attacks(s: Scene, cap: Caption):
    sw, bot = DEMO["sim_swap"]["response"], DEMO["bot"]["response"]
    assert sw["decision"] == "block" and {"device_new", "amt_z"} <= {r["signal"] for r in sw["reasons"]}
    assert bot["decision"] == "block" and "accounts_on_device" in {r["signal"] for r in bot["reasons"]}
    assert bot["features"]["accounts_on_device"] == 30
    g = show_shot(s, cap, "shot_simswap_block")
    cap.say(f"SIM swap: {rupees(sw['amount'])} from a new phone in Kolkata → block", "3 · attacks blocked, with reasons")
    s.play(Create(mark(g, "shot_simswap_block", "decision", RED)), run_time=0.4)
    s.wait(1.0)
    cap.say("Why: a device never seen on her account, an amount far above usual")
    s.play(Create(mark(g, "shot_simswap_block", "reasons", YELLOW)), run_time=0.4)
    s.wait(0.8)
    cap.say("Every decision returns each signal's push on the risk (tree-SHAP)")
    s.play(Create(mark(g, "shot_simswap_block", "shap", PURPLE)), run_time=0.4)
    s.wait(1.4)
    g2 = show_shot(s, cap, "shot_bot_block", prev=g)
    cap.say("Credential-stuffing bot, device seen on 30 accounts → block")
    s.play(Create(mark(g2, "shot_bot_block", "reasons", YELLOW)), Create(mark(g2, "shot_bot_block", "accounts", CYAN)),
           run_time=0.4)
    s.wait(1.2)


# ---------------------------------------------------------------------------- 4 · the right challenge (12 s)
def beat_challenge(s: Scene, cap: Caption):
    np_, co = DEMO["genuine_new_phone"]["response"], DEMO["coerced"]["response"]
    assert np_["decision"] == "challenge" and np_["challenge_type"] == "passkey"
    assert co["challenge_type"] == "bank_callback" and "1930" in co["message_en"]
    g = show_shot(s, cap, "shot_newphone_passkey")
    cap.say("Real Asha, new phone + new SIM: passkey on her registered phone", "4 · the right challenge")
    s.play(Create(mark(g, "shot_newphone_passkey", "challenge", ORANGE)), run_time=0.4)
    s.wait(1.2)
    cap.say("After a SIM change, never an SMS OTP: it would reach the attacker")
    s.wait(1.6)
    g2 = show_shot(s, cap, "shot_newphone_passed", prev=g)
    cap.say("She passes: allow, and the new phone becomes trusted")
    s.play(Create(mark(g2, "shot_newphone_passed", "final", GREEN)), run_time=0.4)
    s.wait(1.2)
    g3 = show_shot(s, cap, "shot_coerced_callback", prev=g2)
    cap.say(f"Coached victim, {rupees(co['amount'])}: bank call-back + 1930 scam warning")
    s.play(Create(mark(g3, "shot_coerced_callback", "message", ORANGE)), run_time=0.4)
    s.wait(1.6)


# ---------------------------------------------------------------------------- 5 · results, simulated (11 s)
def hbar(label, value, color, w_max=6.0, size=17, bold=False):
    lab = T(label, size, INK if bold else MUTED, weight="BOLD" if bold else "NORMAL")
    lab_box = VGroup(lab).set_width(min(lab.width, 3.3))
    track = RoundedRectangle(width=w_max, height=0.32, corner_radius=0.16, stroke_width=0, fill_color=SURFACE2,
                             fill_opacity=1)
    bar = RoundedRectangle(width=max(0.05, w_max * value / 100), height=0.32, corner_radius=0.16, stroke_width=0,
                           fill_color=color, fill_opacity=1)
    num = T(pct(value), 17, color if bold else INK, weight="BOLD", font=UI)
    return lab_box, track, bar, num


def beat_results(s: Scene, cap: Caption):
    cap.say(f"Simulated: {R['data']['users']:,} customers, {R['data']['requests']:,} requests, real HMOG touch",
            "5 · results (simulated)")
    badge = pill("SIMULATED", YELLOW, size=13, weight="BOLD")
    title = T("Attack requests stopped", 22, INK, weight="BOLD").to_corner(UL, buff=0.45).shift(DOWN * 0.1)
    sub = T("genuine payments challenged", 15, MUTED).move_to([5.35, 2.4, 0])
    badge.next_to(title, RIGHT, buff=0.4)
    rows = [("Our risk engine", ENG, BLUE, True), ("Rules + SMS OTP", RULES, MUTED, False),
            ("SMS OTP on every payment", OTP, MUTED, False)]
    drawn, grows = VGroup(), []
    for i, (lab, d, col, bold) in enumerate(rows):
        lab_m, track, bar, num = hbar(lab, d["attacks_stopped_pct"], col, bold=bold)
        y = 1.7 - i * 0.85
        lab_m.move_to([-6.85, y, 0], aligned_edge=LEFT)
        track.move_to([-3.35, y, 0], aligned_edge=LEFT)
        bar.move_to([-3.35, y, 0], aligned_edge=LEFT)
        num.next_to(track, RIGHT, buff=0.2)
        ch = pill(f"{pct(d['genuine_challenged_pct'])} challenged", ORANGE if not bold else GREEN, size=14)
        ch.move_to([5.6, y, 0])
        drawn.add(lab_m, track, num, ch)
        grows.append(GrowFromEdge(bar, LEFT))
        drawn.add(bar)
    s.play(FadeIn(badge), FadeIn(title), FadeIn(sub), run_time=0.4)
    s.play(*[FadeIn(m) for m in drawn if m not in [g.mobject for g in grows]], *grows, run_time=1.1, rate_func=ease_out_cubic)
    s.wait(0.9)
    cap.say(f"{pct(ENG['attacks_stopped_pct'])} of attack requests stopped, only {pct(ENG['genuine_challenged_pct'])} of genuine challenged")
    s.wait(2.2)
    abl = [("behaviour only", D["behaviour signals only"]["attacks_stopped_pct"], PURPLE),
           ("device only", D["device signals only"]["attacks_stopped_pct"], CYAN),
           ("transaction only", D["transaction signals only"]["attacks_stopped_pct"], ORANGE),
           ("all three together", ENG["attacks_stopped_pct"], BLUE)]
    cap.say("No single signal family is enough; together they stop the most")
    strip = VGroup()
    for i, (lab, v, col) in enumerate(abl):
        lab_m, track, bar, num = hbar(lab, v, col, w_max=3.2, size=14, bold=(i == 3))
        num.scale(0.85)
        g = VGroup(lab_m, VGroup(track, bar), num)
        lab_m.move_to([-6.85, -1.0 - i * 0.42, 0], aligned_edge=LEFT)
        track.move_to([-3.35, -1.0 - i * 0.42, 0], aligned_edge=LEFT)
        bar.move_to([-3.35, -1.0 - i * 0.42, 0], aligned_edge=LEFT)
        num.next_to(track, RIGHT, buff=0.15)
        strip.add(g)
    note = VGroup(mono("simulated customers & attacks · real HMOG touch", 14, MUTED),
                  mono("challenge outcomes assumed, same for every row", 14, MUTED),
                  mono(f"hardest attacks: {pct(R['difficulty']['hard (0.66-1)']['stopped'])} stopped · "
                       f"coached victims: {pct(ENG['per_scenario']['coerced']['final_blocked'])} stopped", 14, MUTED)
                  ).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
    fit(note, 5.4).move_to([1.25, -1.6, 0], aligned_edge=LEFT)
    s.play(FadeIn(strip, lag_ratio=0.15), FadeIn(note), run_time=0.8)
    s.wait(2.4)


# ---------------------------------------------------------------------------- 6 · real time, secured, cloud (7 s)
def beat_cloud(s: Scene, cap: Caption):
    cap.say(f"Real time: p95 {P95_PLAIN:.1f} ms over HTTP, {P95_TOUCH:.1f} ms with the touch check", "6 · fast and secure")
    l1 = VGroup(T(f"{P95_PLAIN:.1f} ms", 46, GREEN, weight="BOLD"), T("p95 · no touch data", 15, MUTED)).arrange(DOWN, buff=0.08)
    l2 = VGroup(T(f"{P95_TOUCH:.1f} ms", 46, GREEN, weight="BOLD"), T("p95 · + 10 touch gestures verified", 15, MUTED)).arrange(DOWN, buff=0.08)
    lat = VGroup(l1, l2).arrange(RIGHT, buff=0.8).move_to(LEFT * 3.3 + UP * 1.6)
    lat_note = mono("measured: laptop CPU · HTTP · API key + HMAC checks on", 14, MUTED).next_to(lat, DOWN, buff=0.18)
    sec = VGroup(*[pill(x, BLUE, size=15) for x in ("API keys", "HMAC-signed requests", "replay rejection",
                                                   "rate limiting", "audit log")]).arrange(RIGHT, buff=0.15)
    fit(sec, 7.0)
    sec.next_to(lat_note, DOWN, buff=0.45).set_x(-3.3)
    s.play(FadeIn(lat, shift=UP * 0.1), FadeIn(lat_note), run_time=0.6)
    s.play(FadeIn(sec, lag_ratio=0.15), run_time=0.7)
    s.wait(0.9)
    cap.say("Cloud design: Cloud Run in Mumbai, Redis state, Cloud SQL audit")
    cloud = RoundedRectangle(width=5.4, height=3.9, corner_radius=0.35, stroke_width=1.6, stroke_color=MUTED)
    cloud = DashedVMobject(cloud, num_dashes=60).move_to(RIGHT * 3.75 + UP * 0.55)
    ct = T("Google Cloud · asia-south1 (Mumbai)", 15, INK, weight="BOLD").next_to(cloud.get_top(), DOWN, buff=0.2)
    parts = VGroup(box("Cloud Run", "risk API", w=2.2, h=0.8, size=16, sub_size=11),
                   box("Memorystore", "live state", w=2.2, h=0.8, size=16, sub_size=11),
                   box("Cloud SQL", "audit log", w=2.2, h=0.8, size=16, sub_size=11),
                   box("Secret Manager", "keys", w=2.2, h=0.8, size=16, sub_size=11)).arrange_in_grid(2, 2, buff=0.18)
    parts.move_to(cloud.get_center() + DOWN * 0.1)
    armor = pill("Cloud Armor + load balancer in front", MUTED, size=12).next_to(parts, DOWN, buff=0.2)
    status = mono("deploy script written · first cloud run at the hack", 14, YELLOW).next_to(cloud, DOWN, buff=0.12)
    s.play(Create(cloud), FadeIn(ct), run_time=0.6)
    s.play(FadeIn(parts, lag_ratio=0.15), FadeIn(armor), FadeIn(status), run_time=0.8)
    s.wait(1.4)


# ---------------------------------------------------------------------------- 7 · end card (4 s)
def beat_end(s: Scene, cap: Caption):
    cap.hide(run_time=0.3)
    pills = VGroup(*[pill(k.upper(), DECISION[k], size=26, weight="BOLD") for k in ("allow", "challenge", "block")])
    pills.arrange(RIGHT, buff=0.35).move_to(UP * 1.0)
    line = T("in real time, with the signals behind every decision", 26, INK).next_to(pills, DOWN, buff=0.5)
    track = VGroup(T("PRAMAAN · FRONTIER 04", 18, BLUE, weight="BOLD"),
                   T("Fast and Secure Online Transaction Authentication", 22, MUTED)).arrange(DOWN, buff=0.12)
    track.next_to(line, DOWN, buff=0.7)
    s.play(FadeIn(pills, lag_ratio=0.2), run_time=0.7)
    s.play(FadeIn(line, shift=UP * 0.08), run_time=0.5)
    s.play(FadeIn(track), run_time=0.5)
    s.wait(1.4)
    s.play(*[FadeOut(m) for m in s.mobjects], run_time=0.5)


# ---------------------------------------------------------------------------- screenshot callout regions (pixels)
_REG = pathlib.Path(__file__).with_name("assets") / "shots" / "regions.json"
SHOT_REGIONS = json.loads(_REG.read_text()) if _REG.exists() else {}
SIMSWAP, BOT = SHOT_REGIONS.get("shot_simswap_block"), SHOT_REGIONS.get("shot_bot_block")
NEWPHONE, PASSED = SHOT_REGIONS.get("shot_newphone_passkey"), SHOT_REGIONS.get("shot_newphone_passed")
COERCED = SHOT_REGIONS.get("shot_coerced_callback")

BEATS = [("Problem", beat_problem), ("Approach", beat_approach), ("Attacks", beat_attacks),
         ("Challenge", beat_challenge), ("Results", beat_results), ("Cloud", beat_cloud), ("End", beat_end)]
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
