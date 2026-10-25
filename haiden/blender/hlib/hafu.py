"""破風板 (bargeboard) detail for 拝殿A-2 ver2 (params "hafu_detail").

A board lies in a vertical plane: origin O (on the back face, z=0), horizontal
unit A along the board, outward unit N. Stations are vertical (plumb) slices,
the cross-section profile is defined perpendicular to the board line and
stretched by 1/cos(slope) so the 成 (depth) is constant along the slope and
both ends are plumb cuts (拝み joint / 破風尻).

Profile (n outward from the back face, b downward from the top, perpendicular):
  登り裏甲 (top step, mostly under the 掛瓦), 登り茅負 (sloped face step),
  a thin fillet, the board face with two 眉 grooves and the 眉欠き recess
  along the lower edge. Near a 破風尻 the lower edge rises in a 繰形 and the
  眉 lines follow it and fade out.

Kanagu: 拝み金具 / 破風尻金具 / 中央金具 = thin plates with a cusped (雲形)
inner edge, a 猪目 cut-out, 唐草 scrolls in relief (打ち出し) and 鋲 rows;
六葉 釘隠し along the board.
"""
import math

import numpy as np

from . import geom as G
from . import parts as PT

ZV = np.array([0.0, 0.0, 1.0])

DEFAULTS = dict(
    t=0.065,                 # board thickness (厚)
    d1=0.045, p1=0.045,      # 登り裏甲: depth / projection beyond the board face
    d2=0.055, p2a=0.036, p2b=0.020,   # 登り茅負: depth / projection top / bottom (sloped face)
    d3=0.022, p3=0.012,      # fillet
    mayu_h=0.048, mayu_step=0.010,    # 眉欠き band height / recess
    grooves=(0.026, 0.052), groove_w=0.013, groove_d=0.008,
    kuri_L=0.26, kuri_H=0.42,          # 破風尻 繰形 length / rise (fraction of the body depth)
    fade_L=0.10,
    plate_t=0.004, plate_L=0.32, ogami_L=0.30, mid_L=0.22,
    rokuyo_r=0.042, rokuyo_step=0.85,
)


def cfg_of(hd, **over):
    c = dict(DEFAULTS)
    for k, v in (hd or {}).items():
        if k in c:
            c[k] = tuple(v) if isinstance(v, list) else v
    c.update(over)
    return c


def dome(center, n, r, seg=8):
    V, F = G.lathe([(r, 0.0), (r * 0.86, r * 0.5), (r * 0.5, r * 0.86), (0.0, r)], (0, 0, 0), seg, cap_bottom=True)
    return PT.orient(V, (0, 0, 0), n) + np.asarray(center, float), F


class Board:
    def __init__(self, O, A, N, a0, a1, ztop, h, cfg, end0="plain", end1="jiri", step=0.04):
        self.O = np.asarray(O, float)
        self.A = G.nrm(np.asarray(A, float))
        self.N = G.nrm(np.asarray(N, float))
        self.c = cfg
        self.end0, self.end1 = end0, end1
        L = abs(a1 - a0)
        base = np.linspace(a0, a1, max(3, int(math.ceil(L / step)) + 1))
        extra = []
        sg = 1.0 if a1 > a0 else -1.0
        for e, ae in ((end0, a0), (end1, a1)):
            span = cfg["kuri_L"] * 1.25 if e == "jiri" else cfg["fade_L"] * 1.2
            inward = sg if ae == a0 else -sg
            extra.append(ae + inward * np.linspace(0, min(span, L * 0.45), 22))
        a = np.unique(np.round(np.concatenate([base] + extra), 7))
        a = a[(a >= min(a0, a1) - 1e-9) & (a <= max(a0, a1) + 1e-9)]
        if sg < 0:
            a = a[::-1]
        self.a = a
        self.z = np.asarray(ztop(a), float)
        dz = np.gradient(self.z, a)
        self.cos = 1.0 / np.sqrt(1.0 + dz ** 2)
        self.s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(a), np.diff(self.z)))])
        self.S = float(self.s[-1])
        self.h = np.asarray(h(a), float) * np.ones_like(a)
        c = cfg
        self.b3 = -(c["d1"] + c["d2"] + c["d3"])
        # distance from each end (arc length)
        self.kuri = np.zeros_like(a)
        self.fade = np.ones_like(a)
        for e, dist in ((end0, self.s), (end1, self.S - self.s)):
            if e == "jiri":
                u = np.clip(1 - dist / c["kuri_L"], 0, 1)
                body = self.h + self.b3
                # concave rise then a small nose at the very end (繰形)
                rise = np.where(u < 0.78, np.sin(np.pi / 2 * u / 0.78) ** 2,
                                1 - 0.32 * np.sin(np.pi * (u - 0.78) / 0.22 * 0.5))
                self.kuri = np.maximum(self.kuri, c["kuri_H"] * body * rise * (u > 0))
                self.fade = np.minimum(self.fade, np.clip((dist - c["kuri_L"] * 0.55) / c["fade_L"], 0, 1))
            elif e == "plain":
                self.fade = np.minimum(self.fade, np.clip((dist - 0.02) / c["fade_L"], 0, 1))
        self.bb = -self.h + self.kuri          # bottom edge (perpendicular, <0)

    # ---------------------------------------------------------------- profile
    def profile(self, i):
        c = self.c
        t = c["t"]
        f = self.fade[i]
        b0, b1, b2, b3 = 0.0, -c["d1"], -(c["d1"] + c["d2"]), self.b3
        bb = self.bb[i]
        bm = bb + c["mayu_h"]
        gw, gd = c["groove_w"], c["groove_d"] * f
        g1, g2 = (bm + c["grooves"][0], bm + c["grooves"][1])
        # keep strictly ordered (top -> bottom), collapsing toward the bottom when cramped
        lim = b3 - 0.006
        g2 = min(g2, lim - gw / 2)
        g1 = min(g1, g2 - gw - 0.002)
        bm = min(bm, g1 - gw / 2 - 0.004)
        bb = min(bb, bm - 0.010)
        ms = c["mayu_step"] * f
        P = [(0.0, b0), (t + c["p1"], b0), (t + c["p1"], b1), (t + c["p2a"], b1), (t + c["p2b"], b2),
             (t + c["p3"], b2), (t + c["p3"], b3), (t, b3),
             (t, g2 + gw / 2), (t - gd, g2), (t, g2 - gw / 2),
             (t, g1 + gw / 2), (t - gd, g1), (t, g1 - gw / 2),
             (t, bm), (t - ms, bm - 0.006),
             (t - ms, bb + 0.006), (t - ms - 0.006, bb),
             (0.006, bb), (0.0, bb + 0.006)]
        return np.array(P)

    def end_cap(self, gold, end=1, t=0.003):
        """木口金具: thin plate over the plumb end face (破風尻)."""
        i = len(self.a) - 1 if end == 1 else 0
        pr = self.profile(i)
        o2 = np.stack([pr[:, 0], self.z[i] + pr[:, 1] / self.cos[i]], 1)
        sgn = 1.0 if end == 1 else -1.0
        dirv = self.A * (1.0 if self.a[-1] > self.a[0] else -1.0) * sgn
        org = self.O + self.a[i] * self.A + dirv * (t / 2 + 0.0005)
        gold.addt(G.extrude_poly(o2, t, (org, self.N, ZV), bevel=0.0008))

    def world(self, i, nb):
        nb = np.asarray(nb, float)
        return (self.O + self.a[i] * self.A + nb[:, 0:1] * self.N
                + (self.z[i] + nb[:, 1:2] / self.cos[i]) * ZV)

    def mesh(self):
        rings = [self.world(i, self.profile(i)) for i in range(len(self.a))]
        k = len(rings[0])
        V = np.concatenate(rings)
        F = G.grid_faces(len(rings), k, closed_c=True)
        Fl = F.tolist()
        Fl += G.cap_faces(self.profile(0), 0, reverse=False)
        Fl += G.cap_faces(self.profile(len(self.a) - 1), (len(rings) - 1) * k, reverse=True)
        return V, Fl

    # ---------------------------------------------------------------- mapping helpers
    def at(self, s):
        s = np.asarray(s, float)
        a = np.interp(s, self.s, self.a)
        z = np.interp(s, self.s, self.z)
        cs = np.interp(s, self.s, self.cos)
        bb = np.interp(s, self.s, self.bb)
        return a, z, cs, bb

    def pt(self, s, b, n):
        a, z, cs, _ = self.at(s)
        return self.O + np.asarray(a)[..., None] * self.A + np.asarray(n)[..., None] * self.N + \
            (np.asarray(z) + np.asarray(b) / np.asarray(cs))[..., None] * ZV

    def plane2d(self, s, b):
        a, z, cs, _ = self.at(s)
        return np.stack([np.asarray(a) * np.ones_like(b), np.asarray(z) + np.asarray(b) / np.asarray(cs)], -1)

    # ---------------------------------------------------------------- kanagu
    def plate(self, gold, s_lo, s_hi, cusp_lo=True, cusp_hi=True, inome=True, relief=True, rivets=True):
        c = self.c
        s_lo = max(0.0, s_lo); s_hi = min(self.S, s_hi)
        if s_hi - s_lo < 0.08:
            return
        bt = self.b3 - 0.006
        cd = min(0.07, (s_hi - s_lo) * 0.22)

        def bot(s):
            # plates stop on the 眉 line (top of the 眉欠き recess) so they lie flat on the board face
            return np.interp(s, self.s, self.bb) + c["mayu_h"] + 0.002

        def edge(s_e, sgn, cusp, down=True):
            u = np.linspace(0, 1, 25)
            b_top, b_bot = bt, float(bot(s_e))
            bvals = b_top + (b_bot - b_top) * u
            if cusp:
                # 雲形: two lobes with a point in the middle (sgn: direction into the plate)
                off = cd * (np.abs(np.sin(np.pi * 2 * u)) ** 0.65) * (1 - 0.25 * np.cos(np.pi * u))
                sv = s_e + sgn * (cd - off)
            else:
                sv = np.full_like(u, s_e)
            pts = np.stack([sv, bvals], 1)
            return pts if down else pts[::-1]

        ss = np.linspace(s_lo + (cd if cusp_lo else 0), s_hi - (cd if cusp_hi else 0), 30)
        top = np.stack([ss, np.full_like(ss, bt)], 1)
        right = edge(s_hi, -1, cusp_hi, down=True)
        sb = np.linspace(s_hi, s_lo, 40)
        bottom = np.stack([sb, bot(sb)], 1)
        left = edge(s_lo, 1, cusp_lo, down=False)
        sbo = np.vstack([top, right[1:], bottom[1:-1], left])
        # outline in the board plane (a, z)
        o2 = self.plane2d(sbo[:, 0], sbo[:, 1])
        # drop near-duplicates
        keep = np.concatenate([[True], np.linalg.norm(np.diff(o2, axis=0), axis=1) > 1e-4])
        o2 = o2[keep]
        holes = []
        sc_ = (s_lo + s_hi) / 2
        bc = (bt + float(bot(sc_))) / 2
        hh = (bt - float(bot(sc_)))
        if inome and hh > 0.07:
            cen = self.plane2d(np.array([sc_]), np.array([bc]))[0]
            holes.append(PT.heart(cen[0], cen[1], min(hh * 0.42, 0.08), n=18))
        nplate = c["t"] + c["plate_t"] / 2 + 0.0008
        org = self.O + nplate * self.N
        gold.addt(G.extrude_poly(o2, c["plate_t"], (org, self.A, ZV), holes=holes, bevel=0.0012))
        n_top = c["t"] + c["plate_t"] + 0.0008
        if relief and hh > 0.06:
            r0 = min(hh * 0.30, 0.05)
            for k, (sc2, sgn) in enumerate(((s_lo + (s_hi - s_lo) * 0.27, 1), (s_lo + (s_hi - s_lo) * 0.73, -1))):
                if (sc2 - s_lo) < r0 or (s_hi - sc2) < r0:
                    continue
                th = np.linspace(0, 2.6 * np.pi, 46)
                r = r0 * np.exp(-0.55 * th / np.pi) * 0.9
                sv = sc2 + sgn * r * np.cos(th)
                bv = bc + r * np.sin(th)
                # stem toward the plate middle
                st_s = np.linspace(sv[0], sc_ , 10)[1:]
                st_b = bc + (bv[0] - bc) * (1 - np.linspace(0, 1, 10)[1:]) + 0.18 * hh * np.sin(np.linspace(0, np.pi, 10)[1:])
                S_ = np.concatenate([st_s[::-1], sv])
                B_ = np.concatenate([st_b[::-1], bv])
                P = self.pt(S_, B_, np.full_like(S_, n_top + 0.002))
                gold.addt(G.sweep(P, G.circle_profile(0.0036, 6), mode="normal", up=self.N))
        if rivets:
            for (s_, b_) in self._perimeter_pts(sbo, 0.013, 0.065):
                gold.addt(dome(self.pt(np.array(s_), np.array(b_), np.array(n_top)), self.N, 0.0065))

    def _perimeter_pts(self, sbo, inset, step):
        # rivet spots: along the top and bottom edges (straight parts), inset
        out = []
        s0, s1 = sbo[:, 0].min(), sbo[:, 0].max()
        n = max(2, int((s1 - s0 - 2 * inset) / step) + 1)
        for s_ in np.linspace(s0 + inset * 3, s1 - inset * 3, n):
            out.append((s_, self.b3 - 0.006 - inset))
            out.append((s_, float(np.interp(s_, self.s, self.bb)) + self.c["mayu_h"] + 0.002 + inset))
        return out

    def rokuyo_row(self, gold, s_from, s_to, step=None, r=None):
        c = self.c
        step = step or c["rokuyo_step"]
        r = r or c["rokuyo_r"]
        L = s_to - s_from
        if L < step * 0.6:
            return
        n = max(1, int(round(L / step)))
        for k in range(n):
            s_ = s_from + L * (k + 0.5) / n
            _, _, _, bb = self.at(s_)
            b_ = (self.b3 + bb + c["mayu_h"] + c["grooves"][1]) / 2
            gold.addt(PT.rokuyo(self.pt(np.array(s_), np.array(b_), np.array(c["t"] + 0.001)), self.N, r=r, seg=16))

    def kanagu_std(self, gold):
        """拝み/破風尻 plates by end type + 六葉 between."""
        c = self.c
        s_a, s_b = 0.0, self.S
        if self.end0 == "ogami":
            self.plate(gold, 0.0, c["ogami_L"], cusp_lo=False, cusp_hi=True)
            s_a = c["ogami_L"]
        elif self.end0 == "jiri":
            self.plate(gold, 0.0, c["plate_L"], cusp_lo=False, cusp_hi=True)
            s_a = c["plate_L"]
        if self.end1 == "jiri":
            self.plate(gold, self.S - c["plate_L"], self.S, cusp_lo=True, cusp_hi=False)
            self.end_cap(gold, 1)
            s_b = self.S - c["plate_L"]
        elif self.end1 == "ogami":
            self.plate(gold, self.S - c["ogami_L"], self.S, cusp_lo=True, cusp_hi=False)
            s_b = self.S - c["ogami_L"]
        self.rokuyo_row(gold, s_a + 0.05, s_b - 0.05)
