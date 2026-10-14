"""BIOS authentication video: palette, fonts and shared components.

Palette = the console's design tokens (frontend/src/app/globals.css, Apple dark system colours), so the video and the
product read as one system. Decisions keep one colour each everywhere: allow = green, challenge = orange, block = red.
Signal families: behaviour = purple, device = cyan, transaction = orange (as in the console's signal panel).
"""
import pathlib

import manimpango
from manim import (DOWN, LEFT, RIGHT, UP, AnimationGroup, Create, FadeIn, FadeOut, Group, ImageMobject, Line,
                   MoveAlongPath, Rectangle, RoundedRectangle, Scene, Square, Succession, Text, VGroup, config, linear)

for _f in pathlib.Path(__file__).with_name("assets").joinpath("fonts").glob("*.ttf"):
    manimpango.register_font(str(_f))

UI, MONO = "Inter", "JetBrains Mono"
SHOTS = pathlib.Path(__file__).with_name("assets") / "shots"

BG = "#000000"
ELEV = "#0c0c0e"
SURFACE = "#1c1c1e"
SURFACE2 = "#2c2c2e"
LINE = "#38383a"
INK = "#ffffff"
MUTED = "#a1a1a8"      # label-secondary on black
FAINT = "#6e6e75"
BLUE = "#0a84ff"
INDIGO = "#5e5ce6"
GREEN = "#30d158"
ORANGE = "#ff9f0a"
RED = "#ff453a"
YELLOW = "#ffd60a"
PURPLE = "#bf5af2"
CYAN = "#64d2ff"
TEAL = "#40c8e0"

DECISION = {"allow": GREEN, "challenge": ORANGE, "block": RED}
FAMILY = {"behaviour": PURPLE, "device": CYAN, "transaction": ORANGE}

config.background_color = BG
CONTENT_TOP, CONTENT_BOTTOM = 3.75, -2.7   # keep content above the caption bar


def T(s, size=22, color=INK, font=UI, weight="NORMAL"):
    return Text(s, font=font, font_size=size, color=color, weight=weight)


def mono(s, size=15, color=MUTED):
    return Text(s, font=MONO, font_size=size, color=color)


def fit(m, max_w):
    if m.width > max_w:
        m.scale_to_fit_width(max_w)
    return m


def card(w, h, fill=SURFACE, stroke=LINE, r=0.22, opacity=1.0):
    return RoundedRectangle(width=w, height=h, corner_radius=r, stroke_width=1.2, stroke_color=stroke,
                            fill_color=fill, fill_opacity=opacity)


def box(label, sub="", w=3.0, h=1.0, stroke=LINE, fill=SURFACE, fg=INK, size=22, sub_size=14, r=0.2, sub_color=MUTED):
    rect = card(w, h, fill, stroke, r)
    parts = [fit(T(label, size, fg, weight="BOLD"), w - 0.3)]
    if sub:
        parts.append(fit(Text(sub, font=UI, font_size=sub_size, color=sub_color, line_spacing=0.8), w - 0.3))
    txt = VGroup(*parts).arrange(DOWN, buff=0.1)
    if txt.height > h - 0.15:
        txt.scale_to_fit_height(h - 0.15)
    txt.move_to(rect)
    return VGroup(rect, txt)


def pill(s, color=MUTED, fill=SURFACE, size=16, pad=0.16, font=UI, weight="NORMAL"):
    t = Text(s, font=font, font_size=size, color=color, weight=weight)
    r = RoundedRectangle(width=t.width + 2 * pad, height=t.height + 1.4 * pad, corner_radius=(t.height + 1.4 * pad) / 2,
                         stroke_width=1.2, stroke_color=color, fill_color=fill, fill_opacity=1)
    t.move_to(r)
    return VGroup(r, t)


def eyebrow(s, color=FAINT, size=14):
    """Letter-spaced uppercase label, like the console's panel eyebrows."""
    from manim import MarkupText
    return MarkupText(f'<span letter_spacing="1400">{s.upper()}</span>', font=UI, font_size=size, color=color)


def arrow(a, b, color=MUTED, width=2.0, tip=0.16):
    from manim import Arrow
    return Arrow(a, b, buff=0.06, stroke_width=width, color=color, tip_length=tip, max_tip_length_to_length_ratio=0.25)


def flow_along(a, b, color, n=3, size=0.09, run_time=1.0):
    path = Line(a, b)
    dots = [Square(side_length=size, fill_color=color, fill_opacity=1, stroke_width=0).move_to(a) for _ in range(n)]
    anim = AnimationGroup(*[Succession(MoveAlongPath(d, path, rate_func=linear, run_time=run_time),
                                       FadeOut(d, run_time=0.1)) for d in dots], lag_ratio=0.3)
    return anim, dots


class Caption:
    """Lower-third: headline + small letter-spaced tag; swaps text out-then-in."""

    def __init__(self, s: Scene):
        self.s = s
        w = config.frame_width
        self.bar = Rectangle(width=w, height=1.0, stroke_width=0, fill_color=ELEV, fill_opacity=0.97).to_edge(DOWN, buff=0)
        self.rule = Line(self.bar.get_corner(UP + LEFT), self.bar.get_corner(UP + RIGHT), stroke_width=1, color=LINE)
        self.bar.set_z_index(20)    # the caption always draws above screenshots, even while one fades in
        self.rule.set_z_index(20)
        self.text = VGroup()
        self.shown = False

    def parts(self):
        return [self.bar, self.rule, self.text]

    def say(self, headline, tag="", run_time=0.5):
        head = Text(headline, font=UI, font_size=30, color=INK, weight="BOLD")
        parts = [head]
        if tag:
            parts.insert(0, eyebrow(tag, BLUE, 13))
        new = VGroup(*parts).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
        new.move_to(self.bar).to_edge(LEFT, buff=0.6)
        fit(new, config.frame_width - 1.2)
        new.set_z_index(21)
        if not self.shown:
            self.s.play(FadeIn(self.bar), Create(self.rule), FadeIn(new, shift=UP * 0.08), run_time=run_time)
            self.shown = True
        else:
            if len(self.text):
                self.s.play(FadeOut(self.text, shift=UP * 0.06), run_time=run_time * 0.4)
            self.s.play(FadeIn(new, shift=UP * 0.06), run_time=run_time * 0.6)
        self.text = new

    def hide(self, run_time=0.4):
        if self.shown:
            parts = [self.bar, self.rule] + ([self.text] if len(self.text) else [])
            self.s.play(*[FadeOut(m) for m in parts], run_time=run_time)
            self.shown, self.text = False, VGroup()


class Shot(Group):
    """A console screenshot filling the frame above the caption bar, plus callouts in screenshot pixels."""

    def __init__(self, name, top_margin=0.25, bottom_margin=1.1):
        super().__init__()
        self.img = ImageMobject(str(SHOTS / f"{name}.png"))
        self.px_w, self.px_h = self.img.pixel_array.shape[1], self.img.pixel_array.shape[0]
        avail_h = config.frame_height - top_margin - bottom_margin
        self.img.scale_to_fit_height(avail_h)
        if self.img.width > config.frame_width - 0.3:
            self.img.scale_to_fit_width(config.frame_width - 0.3)
        self.img.move_to(UP * (bottom_margin - top_margin) / 2)
        self.frame = RoundedRectangle(width=self.img.width, height=self.img.height, corner_radius=0.08,
                                      stroke_width=1, stroke_color=LINE).move_to(self.img)
        self.add(self.img, self.frame)

    def at(self, x_px, y_px):
        c, w, h = self.img.get_center(), self.img.width, self.img.height
        return c + RIGHT * (x_px / self.px_w - 0.5) * w + UP * (0.5 - y_px / self.px_h) * h

    def box(self, x0, y0, x1, y1, color=YELLOW, stroke=4):
        a, b = self.at(x0, y0), self.at(x1, y1)
        r = RoundedRectangle(width=abs(b[0] - a[0]), height=abs(b[1] - a[1]), corner_radius=0.08,
                             stroke_color=color, stroke_width=stroke)
        r.move_to((a + b) / 2)
        self.add(r)
        return r


def clear(s: Scene, keep=(), run_time=0.4):
    gone = [m for m in s.mobjects if m not in keep]
    if gone:
        s.play(*[FadeOut(m) for m in gone], run_time=run_time)
