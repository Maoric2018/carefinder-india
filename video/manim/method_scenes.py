"""Manim animations for the method section of the CareFinder video.

Render (1920x1080, 30 fps):
  uv run --python 3.12 --with manim manim -qh --fps 30 -r 1920,1080 method_scenes.py ModelScene OddsScene ChecksScene AccessScene

Numbers come from params.json (read from the fitted model in the live app: the "Full method" panel and each card's
arithmetic) and beat times from beats.json (word timings of the voiceover), so each animation lands on the word
that describes it.
"""

import json
import math
from pathlib import Path

import numpy as np
from manim import (DOWN, LEFT, RIGHT, UP, Arrow, Axes, Circle, Create, CurvedArrow, DashedLine, Dot, FadeIn, FadeOut,
                   GrowArrow, GrowFromCenter, GrowFromEdge, Indicate, Line, MarkupText, NumberLine, Rectangle,
                   RoundedRectangle, Scene, Text, ValueTracker, VGroup, VMobject, always_redraw, config,
                   rate_functions, LaggedStart, AnimationGroup, SurroundingRectangle)

HERE = Path(__file__).parent
P = json.loads((HERE / "params.json").read_text())
BEATS = json.loads((HERE / "beats.json").read_text())

BG = "#051216"
TEAL = "#5EEAD4"
TEAL2 = "#14B8A6"
AMBER = "#F59E0B"
RED = "#F05252"
BLUE = "#60A5FA"
INK = "#F1F5F9"
MUTED = "#94A3B8"
PANEL = "#0B2329"
FONT = "Avenir Next"
config.background_color = BG


def T(s, size=32, color=INK, weight="MEDIUM", **kw):
    return Text(s, font=FONT, font_size=size, color=color, weight=weight, **kw)


def M(s, size=32, color=INK, **kw):
    return MarkupText(s, font=FONT, font_size=size, color=color, **kw)


def card(mob, color=TEAL2, pad=0.35):
    return RoundedRectangle(corner_radius=0.2, width=mob.width + 2 * pad, height=mob.height + pad * 1.4,
                            color=color, stroke_width=2).set_fill(PANEL, 0.95).move_to(mob)


def box(text, w, h=0.62, color="#2C4A50", size=24, tcolor=INK):
    r = RoundedRectangle(corner_radius=0.16, width=w, height=h, color=color, stroke_width=2).set_fill(PANEL, 1)
    return VGroup(r, T(text, size, tcolor).move_to(r))


def fit(m, right=6.8, left=-6.8):
    over = m.get_right()[0] - right
    if over > 0:
        m.shift(LEFT * over)
    under = left - m.get_left()[0]
    if under > 0:
        m.shift(RIGHT * under)
    return m


class Beat(Scene):
    key = ""

    def beat(self, name):
        return float(BEATS[self.key][name])

    def until(self, t):
        dt = t - self.renderer.time
        if dt > 0.02:
            self.wait(dt)

    def finish(self):
        self.until(self.beat("end"))


# ------------------------------------------------------------------------------------------------------------
class ModelScene(Beat):
    """No labels → weak supervision (Snorkel) → each field a noisy witness → EM in plain words."""
    key = "model"

    def construct(self):
        p = P["model"]
        self.until(self.beat("title"))
        title = T("No answer key, so learn from agreement", 42, weight="BOLD").to_edge(UP, buff=0.5)
        self.play(FadeIn(title, shift=0.2 * DOWN), run_time=0.5)

        # 1. nobody has labeled the records
        self.until(self.beat("nokey"))
        hdr = VGroup(T("facility record", 22, MUTED).move_to(LEFT * 2.6 + UP * 1.55),
                     T("really offers dialysis?", 22, MUTED).move_to(RIGHT * 2.9 + UP * 1.55))
        rows = VGroup()
        for i, n in enumerate(["Samarpan Trauma Centre", "Satyarthi Hospital", "City Care Clinic", "… 10,000 more"]):
            r = RoundedRectangle(corner_radius=0.14, width=9.6, height=0.62, color="#2C4A50", stroke_width=2).set_fill(PANEL, 1)
            r.move_to(UP * (0.8 - i * 0.78))
            name = T(n, 24, INK if i < 3 else MUTED).move_to(r).align_to(r, LEFT).shift(0.3 * RIGHT)
            q = M("<b>?</b>", 30, AMBER).move_to(RIGHT * 2.9 + UP * (0.8 - i * 0.78))
            rows.add(VGroup(r, name, q))
        self.play(FadeIn(hdr), LaggedStart(*[FadeIn(r, shift=0.15 * UP) for r in rows], lag_ratio=0.12), run_time=0.8)
        self.until(self.beat("cant"))
        clf = T("supervised classifier: needs these labels", 26, RED).next_to(rows, DOWN, 0.4)
        strike = Line(clf.get_left() + 0.1 * LEFT, clf.get_right() + 0.1 * RIGHT, color=RED, stroke_width=4)
        self.play(FadeIn(clf), run_time=0.25)
        self.play(Create(strike), run_time=0.25)

        # 2. weak supervision, as in Snorkel
        self.until(self.beat("snorkel"))
        self.play(FadeOut(VGroup(hdr, rows, clf, strike)), run_time=0.3)
        ws = M("<b>Weak supervision</b>", 34, TEAL).move_to(UP * 2.0)
        ws_sub = T("Snorkel (Stanford, Ratner et al. 2017): no hand labels; combine many noisy sources", 22, MUTED)
        ws_sub.next_to(ws, DOWN, 0.15)
        srcs = VGroup(box("source 1 says yes", 3.6, color=TEAL2), box("source 2 is silent", 3.6),
                      box("source 3 says yes", 3.6, color=TEAL2), box("source 4 says no", 3.6, color=RED))
        srcs.arrange(DOWN, buff=0.22).move_to(LEFT * 3.6 + DOWN * 1.05)
        est = box("estimated truth", 3.6, h=0.9, color=TEAL, size=26, tcolor=TEAL).move_to(RIGHT * 3.4 + DOWN * 1.05)
        arrows = VGroup(*[Arrow(s.get_right(), est.get_left(), buff=0.12, color="#3B6B70", stroke_width=3,
                                max_tip_length_to_length_ratio=0.05) for s in srcs])
        trust = T("each source's reliability is learned too", 20, MUTED).next_to(est, DOWN, 0.3)
        self.play(FadeIn(ws), FadeIn(ws_sub), run_time=0.4)
        self.play(LaggedStart(*[FadeIn(s, shift=0.2 * RIGHT) for s in srcs], lag_ratio=0.15),
                  LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.15), FadeIn(est), FadeIn(trust), run_time=1.2)

        # 3. here, each field of a record is a witness
        self.until(self.beat("witness"))
        self.play(FadeOut(VGroup(ws, ws_sub, srcs, est, arrows, trust)), run_time=0.3)
        y = VGroup(Circle(0.8, color=TEAL, stroke_width=5).set_fill(TEAL2, 0.18), M("<b>Y</b>", 48, TEAL))
        y_lab = T("really offers dialysis?", 22, MUTED).next_to(y, DOWN, 0.2)
        y_sub = T("hidden: yes or no", 18, MUTED).next_to(y_lab, DOWN, 0.08)
        ygrp = VGroup(y, y_lab, y_sub).move_to(LEFT * 5.0 + DOWN * 0.3)
        names = ["Procedures", "Equipment", "Capabilities", "Description", "Facility name", "Specialties"]
        boxes = VGroup(*[box(n, 2.7).move_to(LEFT * 1.3 + UP * (1.75 - i * 0.7)) for i, n in enumerate(names)])
        arr = VGroup(*[Arrow(y.get_right(), b.get_left(), buff=0.12, color="#3B6B70", stroke_width=3,
                             max_tip_length_to_length_ratio=0.06) for b in boxes])
        wit = T("each field = a noisy witness", 22, TEAL).next_to(boxes, DOWN, 0.3)
        self.play(GrowFromCenter(ygrp), run_time=0.4)
        self.play(LaggedStart(*[AnimationGroup(GrowArrow(a), FadeIn(b, shift=0.15 * RIGHT)) for a, b in zip(arr, boxes)],
                              lag_ratio=0.1), FadeIn(wit), run_time=1.0)

        # 4. EM, in plain words
        self.until(self.beat("em"))
        e_box = VGroup(RoundedRectangle(corner_radius=0.2, width=4.3, height=1.25, color=TEAL2, stroke_width=3).set_fill(PANEL, 1),
                       M("<b>1. Guess</b> each record's truth\nfrom its witnesses", 22)).move_to(RIGHT * 3.6 + UP * 1.2)
        m_box = VGroup(RoundedRectangle(corner_radius=0.2, width=4.3, height=1.25, color=AMBER, stroke_width=3).set_fill(PANEL, 1),
                       M("<b>2. Re-estimate</b> how reliable\neach witness is", 22)).move_to(RIGHT * 3.6 + DOWN * 1.2)
        a1 = CurvedArrow(e_box.get_right() + 0.12 * RIGHT, m_box.get_right() + 0.12 * RIGHT, angle=-2.2, color=MUTED)
        a2 = CurvedArrow(m_box.get_left() + 0.12 * LEFT, e_box.get_left() + 0.12 * LEFT, angle=-2.2, color=MUTED)
        it = ValueTracker(1)
        it_lab = always_redraw(lambda: T(f"expectation-maximization · round {int(it.get_value())}", 20, MUTED)
                               .next_to(m_box, DOWN, 0.35))
        self.play(FadeIn(e_box), FadeIn(m_box), Create(a1), Create(a2), FadeIn(it_lab), run_time=0.6)
        self.until(self.beat("guess"))
        self.play(Indicate(e_box[0], color=TEAL), it.animate.set_value(8), run_time=0.8)
        self.until(self.beat("reest"))
        self.play(Indicate(m_box[0], color=AMBER), it.animate.set_value(20), run_time=0.8)
        self.until(self.beat("conv"))
        done = M(f'<b>converged after {p["iterations"]} rounds</b> · Dawid &amp; Skene (1979)', 22, TEAL).to_edge(DOWN, buff=0.45)
        self.play(it.animate.set_value(p["iterations"]), FadeIn(done), run_time=0.9, rate_func=rate_functions.ease_out_cubic)
        self.finish()


# ------------------------------------------------------------------------------------------------------------
class OddsScene(Beat):
    """Likelihood ratios (dedicated, listed, silent) on a log scale, then the worked arithmetic for two records."""
    key = "odds"

    def construct(self):
        p = P["odds"]
        self.until(self.beat("title"))
        title = T("What EM learns: likelihood ratios", 40, weight="BOLD").to_edge(UP, buff=0.45)
        self.play(FadeIn(title, shift=0.2 * DOWN), run_time=0.5)
        self.until(self.beat("defn"))
        defn = M(f'LR  =  P(field says it | <span foreground="{TEAL}">really offers</span> dialysis)  ÷  '
                 f'P(field says it | <span foreground="{RED}">doesn\'t</span>)', 24).next_to(title, DOWN, 0.3)
        self.play(FadeIn(defn), run_time=0.4)

        # diverging bars on a log scale, centred on ×1
        x1 = 1.2                       # screen x of LR = 1
        unit = 1.55                    # screen units per factor of 10
        axis = Line(UP * 1.55, DOWN * 0.95, color=MUTED, stroke_width=2).move_to([x1, 0.3, 0])
        one = T("×1", 18, MUTED).next_to(axis, DOWN, 0.08)
        more = T("raises the odds →", 18, TEAL).move_to([x1 + 2.0, -0.95, 0])
        less = T("← lowers them", 18, RED).move_to([x1 - 1.6, -0.95, 0])

        def bar(label, v, yy, color):
            w = unit * math.log10(v)
            rect = Rectangle(width=abs(w), height=0.46, stroke_width=0).set_fill(color, 0.9)
            rect.move_to([x1 + w / 2, yy, 0])
            lab = T(label, 22, INK).move_to([-3.3, yy, 0])
            val = M(f"<b>×{v:g}</b>", 24, color).next_to(rect, RIGHT if w > 0 else LEFT, 0.12)
            return VGroup(rect, lab, val), w

        rows = [("ded", p["ded"], 1.15, TEAL), ("list", p["list"], 0.4, AMBER), ("silent", p["silent"], -0.35, RED)]
        for k, (key, (label, v), yy, color) in enumerate(rows):
            self.until(self.beat(key))
            g, w = bar(label, v, yy, color)
            anims = [GrowFromEdge(g[0], LEFT if w > 0 else RIGHT), FadeIn(g[1]), FadeIn(g[2])]
            if k == 0:
                anims += [Create(axis), FadeIn(one), FadeIn(more), FadeIn(less)]
            self.play(*anims, run_time=0.5)
            if key == "silent":
                note = T("silence is evidence too: hospitals that do dialysis usually say so", 20, MUTED).move_to([0, -1.4, 0])
                self.play(FadeIn(note), run_time=0.3)

        # worked arithmetic
        self.until(self.beat("base"))
        base = M(f'start: base rate <b>{p["base_p"]:.0%}</b> of records  →  odds <b>{p["base_odds"]}</b>', 24, INK)
        base.move_to([0, -1.6, 0]).align_to([-6.2, 0, 0], LEFT)
        self.play(FadeOut(note), FadeIn(base, shift=0.1 * UP), run_time=0.4)

        def chain_lines(row):
            f = row["factors"]
            if row["name"] == "Samarpan":
                a = (f'<b>Samarpan</b>:  1:11 × <span foreground="{TEAL}">{" × ".join(f[:3])}</span> × '
                     f'<span foreground="{RED}">{" × ".join(f[3:])}</span>')
                b = (f'overlap discount ^(1/{row["deff"]}), × {row["signal"]}  =  <b>{row["odds"]}</b>  →  '
                     f'<span foreground="{TEAL}"><b>{row["p"]}</b></span>')
                return [a, b]
            a = (f'<b>Satyarthi</b>:  1:11 × <span foreground="{AMBER}">{f[0]}</span> × '
                 f'<span foreground="{RED}">{" × ".join(f[1:])}</span> × {row["signal"]}  =  <b>{row["odds"]}</b>  →  '
                 f'<span foreground="{AMBER}"><b>{row["p"]}</b></span>')
            return [a]

        def block(row, y_top):
            g = VGroup(*[M(t, 20) for t in chain_lines(row)]).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
            g.move_to([0, 0, 0]).align_to([-6.2, 0, 0], LEFT)
            return g.shift(UP * (y_top - g.get_top()[1]))

        self.until(self.beat("sam"))
        sam = block(p["sam"], -2.05)
        self.play(FadeIn(sam, shift=0.1 * UP), run_time=0.5)
        self.until(self.beat("sat"))
        sat = block(p["sat"], -2.95)
        self.play(FadeIn(sat, shift=0.1 * UP), run_time=0.5)
        legend = T("teal: dedicated mentions · amber: in a list · red: silent fields", 16, MUTED).move_to([0, -3.6, 0]).align_to([-6.2, 0, 0], LEFT)
        self.play(FadeIn(legend), run_time=0.3)
        self.finish()


# ------------------------------------------------------------------------------------------------------------
class ChecksScene(Beat):
    """Learned red flags (constrained ≤ 1), the overlap discount, and the bootstrap interval."""
    key = "checks"

    def construct(self):
        p = P["checks"]
        self.until(self.beat("title"))
        title = T("Red flags, overlap, and uncertainty", 40, weight="BOLD").to_edge(UP, buff=0.45)
        line = NumberLine(x_range=[0, 1, 0.1], length=11.5, color=MUTED, include_numbers=False).shift(DOWN * 1.9)
        ticks = VGroup(*[T(f"{v:.1f}", 18, MUTED).next_to(line.n2p(v), DOWN, 0.15) for v in np.linspace(0, 1, 6)])
        axis_lab = T(f"P(offers {p['service']} | its record)", 20, MUTED).next_to(ticks, DOWN, 0.18)
        tracker = ValueTracker(p["p0"])
        marker = always_redraw(lambda: VGroup(
            Dot(line.n2p(tracker.get_value()), radius=0.15, color=TEAL),
            T(f"{tracker.get_value():.2f}", 30, TEAL, weight="BOLD").next_to(line.n2p(tracker.get_value()), UP, 0.25)))
        ev = T(p["flag_example"], 24).move_to(UP * 1.9)
        self.play(FadeIn(title, shift=0.2 * DOWN), Create(line), FadeIn(ticks), FadeIn(axis_lab), FadeIn(ev),
                  FadeIn(marker), run_time=0.6)

        self.until(self.beat("only"))
        cons = T("flag effects are constrained to ≤ ×1: a flag can only lower the odds", 22, MUTED).next_to(ev, DOWN, 0.3)
        self.play(FadeIn(cons), run_time=0.3)
        self.until(self.beat("clinic"))
        flag = M(f'<span foreground="{AMBER}">if it looked like a clinic</span>:  odds <b>×{p["flag_odds"]:.2f}</b> '
                 f'(1/16, learned)', 26).next_to(cons, DOWN, 0.3)
        self.play(FadeIn(flag), tracker.animate.set_value(0.21), run_time=1.0, rate_func=rate_functions.ease_in_out_cubic)

        # overlap discount
        self.until(self.beat("fields"))
        self.play(FadeOut(VGroup(ev, cons, flag)), run_time=0.3)
        circles = VGroup(*[Circle(0.62, color=c, stroke_width=4).set_fill(c, 0.12) for c in (TEAL, BLUE, AMBER)])
        circles[0].move_to(LEFT * 4.6 + UP * 1.45)
        circles[1].move_to(LEFT * 3.85 + UP * 1.45)
        circles[2].move_to(LEFT * 4.22 + UP * 0.85)
        labs = VGroup(T("procedures", 16, TEAL).next_to(circles[0], UP, 0.05).shift(LEFT * 0.3),
                      T("equipment", 16, BLUE).next_to(circles[1], UP, 0.05).shift(RIGHT * 0.3),
                      T("capabilities", 16, AMBER).next_to(circles[2], DOWN, 0.05))
        ov1 = M("fields copied from one web page are <b>not independent</b>", 24).move_to(RIGHT * 1.4 + UP * 1.7)
        ov2 = M(f'k agreeing fields count as  k / (1 + (k−1)ρ)  witnesses', 24, TEAL).next_to(ov1, DOWN, 0.25)
        ov3 = T(f"dialysis: ρ = {p['rho']:.2f}, so 3 agreeing fields count as about 2.8", 20, MUTED).next_to(ov2, DOWN, 0.2)
        self.play(LaggedStart(*[GrowFromCenter(c) for c in circles], lag_ratio=0.15), FadeIn(labs), FadeIn(ov1), run_time=0.7)
        self.play(FadeIn(ov2), FadeIn(ov3), run_time=0.5)

        # bootstrap interval
        self.until(self.beat("interval"))
        self.play(FadeOut(VGroup(circles, labs, ov1, ov2, ov3)), run_time=0.3)
        ex = T(p["ex_name"], 24).move_to(UP * 2.0)
        self.play(FadeIn(ex), tracker.animate.set_value(p["ex_p"]), run_time=0.6)
        self.until(self.beat("refit"))
        boot = T("refit the whole model on 100 resampled copies of the data", 22, BLUE).next_to(ex, DOWN, 0.25)
        lo, hi, mid = p["lo"], p["hi"], p["ex_p"]
        lg = lambda v: math.log(v / (1 - v))
        sd_lo, sd_hi = (lg(mid) - lg(lo)) / 1.645, (lg(hi) - lg(mid)) / 1.645
        from statistics import NormalDist
        zs = [NormalDist().inv_cdf((i + 0.5) / 100) for i in range(100)]
        draws = [1 / (1 + math.exp(-(lg(mid) + z * (sd_lo if z < 0 else sd_hi)))) for z in zs]
        rng = np.random.default_rng(3)
        order = rng.permutation(100)
        dots = VGroup(*[Dot(line.n2p(draws[k]) + UP * (1.6 + rng.random() * 0.4), radius=0.05, color=BLUE).set_opacity(0.9)
                        for k in order])  # start scattered above, then settle into a strip
        self.play(FadeIn(boot), FadeIn(dots), run_time=0.3)
        self.play(LaggedStart(*[d.animate.move_to(line.n2p(draws[k]) + UP * (0.75 + 0.07 * (j % 6)))
                                for j, (d, k) in enumerate(zip(dots, order))], lag_ratio=0.01), run_time=1.4)
        self.until(self.beat("middle"))
        a, b = line.n2p(lo), line.n2p(hi)
        yb = 1.45
        bracket = VGroup(Line(a + UP * yb, b + UP * yb, color=BLUE, stroke_width=5),
                         Line(a + UP * (yb - 0.18), a + UP * (yb + 0.18), color=BLUE, stroke_width=5),
                         Line(b + UP * (yb - 0.18), b + UP * (yb + 0.18), color=BLUE, stroke_width=5))
        ci = M(f'<b>middle 90%: {lo:.2f} – {hi:.2f}</b>', 26, BLUE).next_to(bracket, UP, 0.1)
        self.play(Create(bracket), FadeIn(ci), run_time=0.6)
        self.finish()


# ------------------------------------------------------------------------------------------------------------
class AccessScene(Beat):
    key = "access"

    def construct(self):
        p = P["access"]
        self.until(self.beat("title"))
        title = T("Can the patient get there in time?", 42, weight="BOLD").to_edge(UP, buff=0.5)
        a = Dot(LEFT * 6.0 + DOWN * 2.0, radius=0.13, color=BLUE)
        b = Dot(LEFT * 1.9 + UP * 1.2, radius=0.13, color=TEAL)
        a_l = T("patient", 20, BLUE).next_to(a, DOWN, 0.15)
        b_l = T("hospital", 20, TEAL).next_to(b, UP, 0.15)
        straight = DashedLine(a.get_center(), b.get_center(), color=MUTED, dash_length=0.12)
        s_lab = T(f"{p['km']:.0f} km straight line", 20, MUTED).move_to(straight.get_center() + RIGHT * 1.15 + DOWN * 0.2)
        s_lab = VGroup(Rectangle(width=s_lab.width + 0.2, height=s_lab.height + 0.14, stroke_width=0)
                       .set_fill(BG, 0.92).move_to(s_lab), s_lab)
        self.play(FadeIn(title, shift=0.2 * DOWN), FadeIn(a), FadeIn(b), FadeIn(a_l), FadeIn(b_l), Create(straight),
                  FadeIn(s_lab), run_time=0.7)

        self.until(self.beat("road"))
        pts = [a.get_center()]
        rng = np.random.default_rng(7)
        d = b.get_center() - a.get_center()
        perp = np.array([-d[1], d[0], 0]) / np.linalg.norm(d)
        for k in range(1, 12):
            t = k / 12
            pts.append(a.get_center() + d * t + perp * (math.sin(t * math.pi * 3.2) * 0.6 + rng.normal(0, 0.1)))
        pts.append(b.get_center())
        road = VMobject(color=AMBER, stroke_width=5).set_points_smoothly(pts)
        r_lab = fit(T(f"≈ {p['km'] * 1.4:.0f} km by road (×1.4 detour)", 20, AMBER).move_to(LEFT * 4.6 + UP * 2.3))
        speed = fit(T("~35 km/h, speed uncertain (log-normal)", 20, AMBER).next_to(r_lab, DOWN, 0.12))
        med = T(f"median ≈ {round(1.4 * p['km'] / 35, 2) * 60:.0f} min", 22, AMBER, weight="BOLD").next_to(speed, DOWN, 0.12)
        self.play(Create(road), FadeIn(r_lab), FadeIn(speed), run_time=1.2)
        self.bring_to_front(s_lab)
        self.play(FadeIn(med), run_time=0.3)

        self.until(self.beat("compute"))
        ax = Axes(x_range=[0, 4, 1], y_range=[0, 1.6, 0.5], x_length=6.2, y_length=3.2, tips=False,
                  axis_config={"color": MUTED, "stroke_width": 2}).move_to(RIGHT * 3.35 + DOWN * 0.15)
        xl = T("travel time (hours)", 20, MUTED).next_to(ax, DOWN, 0.42)
        nums = VGroup(*[T(str(h), 18, MUTED).next_to(ax.c2p(h, 0), DOWN, 0.12) for h in range(5)])
        sd, medh = math.sqrt(0.35 ** 2 + (p["loc_sd_km"] / p["km"]) ** 2), 1.4 * p["km"] / 35
        W = ValueTracker(2.0)

        def pdf(t):
            return 0.0 if t <= 0 else math.exp(-((math.log(t) - math.log(medh)) ** 2) / (2 * sd * sd)) / (t * sd * math.sqrt(2 * math.pi))

        curve = ax.plot(lambda t: min(pdf(t), 1.55), x_range=[0.02, 4, 0.02], color=TEAL, stroke_width=4)
        area = always_redraw(lambda: ax.get_area(ax.plot(lambda t: min(pdf(t), 1.55), x_range=[0.02, W.get_value(), 0.02]),
                                                 x_range=[0.02, W.get_value()], color=TEAL2, opacity=0.45))
        wline = always_redraw(lambda: DashedLine(ax.c2p(W.get_value(), 0), ax.c2p(W.get_value(), 1.55), color=RED,
                                                 dash_length=0.1, stroke_width=4))
        wlab = always_redraw(lambda: T(f"{W.get_value():.0f} h window", 20, RED).next_to(ax.c2p(W.get_value(), 1.55), UP, 0.08))

        def prob():
            z = (math.log(W.get_value()) - math.log(medh)) / sd
            return 1 / (1 + math.exp(-1.702 * z))

        pr = always_redraw(lambda: M(f'P(arrives in time) = <b>{prob():.0%}</b>', 30, TEAL).next_to(ax, UP, 0.55).align_to(ax, RIGHT))
        self.play(Create(ax), FadeIn(xl), FadeIn(nums), Create(curve), FadeIn(area), Create(wline), FadeIn(wlab), FadeIn(pr),
                  run_time=0.8)

        self.until(self.beat("csec"))
        basis = fit(VGroup(T("window: 2 h for a C-section", 22, INK),
                           T("Lancet Commission on Global Surgery", 18, MUTED)).arrange(DOWN, buff=0.1).next_to(xl, DOWN, 0.15))
        self.play(FadeIn(basis), Indicate(wlab, color=RED), run_time=0.5)

        self.until(self.beat("dial"))
        basis1 = fit(VGroup(T("window: 1 h for dialysis", 22, INK),
                            T("DOPPS: longer trips linked to higher mortality", 18, MUTED)).arrange(DOWN, buff=0.1).move_to(basis))
        self.play(W.animate.set_value(1.0), FadeOut(basis), FadeIn(basis1), run_time=0.9, rate_func=rate_functions.ease_in_out_cubic)

        self.until(self.beat("sam"))
        self.play(Indicate(pr, color=TEAL, scale_factor=1.15), run_time=0.6)

        self.until(self.beat("rank"))
        formula = M(f'rank  =  <span foreground="{TEAL}">P(offers it | record)</span>  ×  '
                    f'<span foreground="{BLUE}">P(arrives in time)</span>', 32).to_edge(DOWN, buff=0.45)
        self.play(FadeOut(basis1), FadeIn(card(formula)), FadeIn(formula), run_time=0.6)
        self.finish()
