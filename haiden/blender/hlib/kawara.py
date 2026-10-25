"""本瓦葺 (hongawara-buki) tile library: tile templates, placement, ridges, ornaments.

Templates are built once in a local frame (x = u lateral, y = v along the tile
axis from its lower/eave end, z = w roof normal) and stamped onto the roof with
vectorised numpy transforms (one "array" per tile kind -> one mesh object), so
thousands of individual tiles stay cheap to build.
"""
import math

import numpy as np
from mathutils.geometry import tessellate_polygon
from mathutils import Vector

from . import geom as G

Z = np.array([0.0, 0.0, 1.0])


# ------------------------------------------------------------------ basics

def faces_to_arrays(F):
    """list-of-lists or ndarray faces -> list of homogeneous int arrays."""
    if isinstance(F, np.ndarray):
        return [F.astype(np.int64)]
    if len(F) and all(isinstance(f, np.ndarray) and f.ndim == 2 for f in F):
        return [f.astype(np.int64) for f in F if len(f)]
    by = {}
    for f in F:
        by.setdefault(len(f), []).append(f)
    return [np.array(v, np.int64) for v in by.values()]


def mb_add(mb, V, Fs):
    """Append vertices once and several face arrays (tris/quads) to a geom.MB."""
    V = np.asarray(V, float).reshape(-1, 3)
    base = mb.n
    mb.V.append(V)
    mb.n += len(V)
    for F in Fs:
        if F is not None and len(F):
            mb.Fa.append(np.asarray(F, np.int64) + base)
    return mb


class Tpl:
    """Accumulates template geometry (local u,v,w)."""

    def __init__(self, name=""):
        self.name = name
        self.Vs, self.Fs, self.n = [], [], 0

    def add(self, V, F):
        V = np.asarray(V, float).reshape(-1, 3)
        for a in faces_to_arrays(F):
            self.Fs.append(a + self.n)
        self.Vs.append(V)
        self.n += len(V)
        return self

    def addt(self, VF):
        return self.add(*VF)

    def done(self):
        self.V = np.concatenate(self.Vs)
        by = {}
        for a in self.Fs:
            by.setdefault(a.shape[1], []).append(a)
        self.F = [np.concatenate(v) for v in by.values()]
        self.ntris = sum(len(a) * (a.shape[1] - 2) for a in self.F)
        return self


def loft_rings(rings, cap_quads=None):
    """Rings: list of (K,3) closed loops (same K). Returns V, [quads]."""
    m, K = len(rings), len(rings[0])
    V = np.concatenate(rings)
    F = G.grid_faces(m, K, closed_c=True)
    out = [F]
    if cap_quads is not None:
        out.append(cap_quads[:, ::-1])
        out.append(cap_quads + (m - 1) * K)
    return V, out


def strip_caps(n):
    """Cap quads for a 'thick curve' loop P_0..P_n, Q_n..Q_0 (K = 2n+2)."""
    K = 2 * (n + 1)
    j = np.arange(n)
    return np.stack([j, j + 1, K - 2 - j, K - 1 - j], 1)


def prism2d(poly, z0, z1, mapf):
    """Flat prism from a 2D polygon (a,b) between heights z0..z1.
    mapf(a, b, h) -> (k,3) local points. Returns V, [tris, quads]."""
    poly = G.ccw(np.asarray(poly, float))
    k = len(poly)
    tris = np.array(tessellate_polygon([[Vector((p[0], p[1], 0.0)) for p in poly]]), np.int64)
    bot = mapf(poly[:, 0], poly[:, 1], np.full(k, z0))
    top = mapf(poly[:, 0], poly[:, 1], np.full(k, z1))
    V = np.vstack([bot, top])
    i = np.arange(k); i2 = (i + 1) % k
    sides = np.stack([i, i2, i2 + k, i + k], 1)
    return V, [tris[:, ::-1], tris + k, sides]


def tube(path, r, seg=5):
    V, F = G.sweep(np.asarray(path, float), G.circle_profile(r, seg), mode="normal", cap=False)
    return V, [F]


# ------------------------------------------------------------------ motifs

def tomoe_polys(r, n_heads=3, npts=11, clockwise=True):
    """3 comma shapes (巴) inside a disc of radius r (2D polygons)."""
    out = []
    rh = 0.24 * r
    sgn = -1.0 if clockwise else 1.0
    for k in range(n_heads):
        rot = 2 * math.pi * k / n_heads
        pts = []
        # head: half circle on the leading side
        hc = 0.40 * r
        for a in np.linspace(math.pi, 0, npts):
            rad = hc + rh * math.cos(a)
            tan = rh * math.sin(a) * -sgn
            ang = rot + tan / max(hc, 1e-6)
            pts.append((rad * math.cos(ang), rad * math.sin(ang)))
        T = np.linspace(0, 1, npts + 3)
        for side in (1, -1):
            seq = T if side == 1 else T[::-1]
            for t in seq:
                if side == 1 and t == 0:
                    continue
                if side == -1 and t == 0:
                    continue
                rc = hc + 0.33 * r * t
                w = 2 * rh * (1 - t) ** 1.25
                phi = rot + sgn * t * 2.0
                rr = rc + side * w / 2
                pts.append((rr * math.cos(phi), rr * math.sin(phi)))
        out.append(np.array(pts))
    return out


# ------------------------------------------------------------------ templates

def hira_tpl(L=0.40, W0=0.27, W1=0.25, sag=0.028, t=0.018, n=6):
    """平瓦: concave plate, lower (eave) end at v=0, wider at the lower end."""
    rings = []
    for v, W in ((0.0, W0), (L, W1)):
        u = np.linspace(-W / 2, W / 2, n + 1)
        wb = sag * (2 * u / W) ** 2
        P = np.stack([u, np.full_like(u, v), wb + t], 1)
        Q = np.stack([u, np.full_like(u, v), wb], 1)[::-1]
        rings.append(np.vstack([P, Q]))
    V, F = loft_rings(rings, strip_caps(n))
    return _tpl_from(V, F, "hira")


def _tpl_from(V, Fs, name):
    tp = Tpl(name)
    tp.Vs.append(V); tp.n = len(V)
    tp.Fs.extend(Fs)
    return tp


def maru_section(R_out, R_in, w0, n):
    th = np.linspace(0, math.pi, n + 1)
    P = np.stack([R_out * np.cos(th), w0 + R_out * np.sin(th)], 1)
    Q = np.stack([R_in * np.cos(th), w0 + R_in * np.sin(th)], 1)[::-1]
    return np.vstack([P, Q])


def maru_tpl(L=0.36, tama=0.055, Ro=0.078, tm=0.016, w0=0.055, n=8, flat=1.0):
    """丸瓦: half cylinder with a 玉縁 (spigot) at the upper end."""
    Ri = Ro - tm
    Rt = Ri - 0.003
    Ri2 = Rt - tm * 0.75
    rings = []
    for v, ro, ri in ((0.0, Ro, Ri), (L - tama, Ro, Ri), (L - tama + 0.008, Rt, Ri2), (L, Rt, Ri2)):
        s = maru_section(ro, ri, w0, n)
        s[:, 1] = w0 + (s[:, 1] - w0) * flat
        rings.append(np.stack([s[:, 0], np.full(len(s), v), s[:, 1]], 1))
    V, F = loft_rings(rings, strip_caps(n))
    return _tpl_from(V, F, "maru")


def noki_hira_tpl(hira_kw, face_h=0.062, face_t=0.024, n=8, relief=True):
    """軒平瓦: 平瓦 + 瓦当 (弓形の顎) with 唐草 relief on its face."""
    L = hira_kw.get("L", 0.40); W0 = hira_kw.get("W0", 0.27)
    sag = hira_kw.get("sag", 0.028); t = hira_kw.get("t", 0.018)
    tp = Tpl("noki_hira")
    h = hira_tpl(**hira_kw)
    tp.Vs += h.Vs; tp.Fs += h.Fs; tp.n = h.n
    W = W0 + 0.004
    u = np.linspace(-W / 2, W / 2, n + 1)
    top = sag * (2 * u / W) ** 2 + t + 0.002
    bot = top - face_h
    rings = []
    for v in (-face_t, 0.004):
        P = np.stack([u, np.full_like(u, v), top], 1)
        Q = np.stack([u, np.full_like(u, v), bot], 1)[::-1]
        rings.append(np.vstack([P, Q]))
    V, F = loft_rings(rings, strip_caps(n))
    tp.add(V, F)
    if relief:
        yf = -face_t
        mid = lambda x: sag * (2 * x / W) ** 2 + t + 0.002 - face_h / 2
        # border lines (外区の界線)
        for dz in (face_h / 2 - 0.009, -face_h / 2 + 0.008):
            xs = np.linspace(-W / 2 + 0.008, W / 2 - 0.008, 10)
            tp.add(*tube(np.stack([xs, np.full_like(xs, yf - 0.001), mid(xs) + dz], 1), 0.0028, 3))
        # 唐草: two scrolling stems from the centre motif outwards
        for sg in (-1, 1):
            xs = np.linspace(0.024, W / 2 - 0.014, 20)
            ph = (xs - 0.024) / 0.052 * 2 * math.pi
            zz = mid(sg * xs) + 0.0105 * np.sin(ph)
            tp.add(*tube(np.stack([sg * xs, np.full_like(xs, yf - 0.002), zz], 1), 0.0034, 4))
            # leaf curls at each crest
            for k in range(3):
                xc = 0.024 + 0.052 * (k + 0.25)
                if xc > W / 2 - 0.02:
                    break
                a = np.linspace(0, 1.6 * math.pi, 8)
                rr = 0.007 * (1 - a / (2.2 * math.pi))
                cx = sg * (xc + 0.006); cz = mid(sg * xc) + 0.0105 - 0.008
                pts = np.stack([cx + sg * rr * np.cos(a), np.full_like(a, yf - 0.002), cz + rr * np.sin(a)], 1)
                tp.add(*tube(pts, 0.0025, 3))
        # centre motif (中心飾り): small tri-lobed boss
        poly = []
        for a in np.linspace(0, 2 * math.pi, 18, endpoint=False):
            rr = 0.013 * (0.65 + 0.35 * abs(math.cos(1.5 * a)))
            poly.append((rr * math.cos(a), rr * math.sin(a)))
        z0 = mid(0.0)
        tp.add(*prism2d(poly, 0.0, 0.006, lambda a, b, hh: np.stack([a, yf - hh, z0 + b], 1)))
    return tp


def noki_maru_tpl(maru_kw, disc_t=0.026, relief=True, seg=20):
    """軒丸瓦: 丸瓦 + 瓦当 disc with 巴紋 and 珠文 (連珠) ring."""
    Ro = maru_kw.get("Ro", 0.078); w0 = maru_kw.get("w0", 0.055)
    tp = Tpl("noki_maru")
    m = maru_tpl(**maru_kw)
    tp.Vs += m.Vs; tp.Fs += m.Fs; tp.n = m.n
    Rd = Ro + 0.007
    prof = [(Rd - 0.003, 0.004), (Rd, 0.0), (Rd, -disc_t + 0.004), (Rd - 0.004, -disc_t), (0.0, -disc_t)]
    tp.addt(G.lathe(prof, (0, 0, w0), seg, cap_bottom=True, axis="y"))
    if relief:
        yf = -disc_t
        # raised outer rim (外縁)
        tp.addt(G.lathe([(0.80 * Rd, yf), (0.80 * Rd, yf - 0.006), (0.97 * Rd, yf - 0.006), (0.97 * Rd, yf)],
                        (0, 0, w0), seg, cap_bottom=False, cap_top=False, axis="y"))
        # 珠文 ring
        for k in range(12):
            a = 2 * math.pi * k / 12
            c = (0.69 * Rd * math.cos(a), 0, w0 + 0.69 * Rd * math.sin(a))
            tp.addt(G.lathe([(0.0062, yf + 0.001), (0.0062, yf - 0.004), (0.0, yf - 0.0065)], c, 6,
                            cap_bottom=False, axis="y"))
        # 巴 (three commas)
        for poly in tomoe_polys(0.58 * Rd, npts=7):
            tp.add(*prism2d(poly, 0.0, 0.0075, lambda a, b, hh: np.stack([a, yf - hh, w0 + b], 1)))
    return tp


def kake_tpl(L=0.30, top_w=0.12, drop=0.11, t=0.018, n_rel=True):
    """掛瓦 (けらば瓦): L-section piece capping the bargeboard, 唐草 face outside.
    local: u = outward (+x = outside of the gable), v = along edge, w = up."""
    P = np.array([(-top_w, t + 0.012), (0.0, t + 0.012), (0.022, 0.0), (0.022, -drop)])
    Q = np.array([(-top_w, 0.012), (0.0, 0.012 - 0.002), (0.022 - t, -0.004), (0.022 - t, -drop)])[::-1]
    sec = np.vstack([P, Q])
    rings = [np.stack([sec[:, 0], np.full(len(sec), v), sec[:, 1]], 1) for v in (0.0, L - 0.004)]
    V, F = loft_rings(rings, strip_caps(len(P) - 1))
    tp = _tpl_from(V, F, "kake")
    if n_rel:
        vs = np.linspace(0.03, L - 0.03, 14)
        zz = -drop / 2 + 0.012 * np.sin((vs - 0.03) / (L - 0.06) * 4 * math.pi)
        tp.add(*tube(np.stack([np.full_like(vs, 0.024), vs, zz], 1), 0.004, 4))
        for dz in (-0.012, -drop + 0.012):
            vs2 = np.array([0.006, L - 0.01])
            tp.add(*tube(np.stack([np.full(2, 0.024), vs2, np.full(2, dz)], 1), 0.003, 3))
    return tp


# ------------------------------------------------------------------ placement

def frames(D, Lat):
    D = G.nrm(D)
    N = G.nrm(np.cross(Lat, D))
    flip = N[:, 2] < 0
    N[flip] *= -1
    Lat = G.nrm(np.cross(D, N))
    return D, Lat, N


def place(mb, tpl, A, D, Lat, N, scale=None, lift=None, Lnom=None, cuts=()):
    """Stamp tpl at k placements. A: (k,3) origin, D/Lat/N unit frames.
    scale: (k,) along-axis scale (clipped tiles). lift: (k,) extra normal
    offset at v=0 fading to 0 at v=Lnom (tile resting on courses below).
    cuts: callables (X (k,n,3), D) -> shift (k,n) along D."""
    k = len(A)
    if k == 0:
        return 0
    T = tpl.V
    u, v, w = T[:, 0], T[:, 1], T[:, 2]
    sc = np.ones(k) if scale is None else np.asarray(scale)
    vv = v[None, :] * sc[:, None]
    ww = np.broadcast_to(w[None, :], (k, len(w))).copy()
    if lift is not None:
        Ln = Lnom if Lnom else max(v.max(), 1e-6)
        ww = ww + np.asarray(lift)[:, None] * np.clip(1 - v[None, :] / Ln, 0, 1)
    X = A[:, None, :] + D[:, None, :] * vv[..., None] + Lat[:, None, :] * u[None, :, None] + N[:, None, :] * ww[..., None]
    for c in cuts:
        s = c(X, D)
        if s is not None:
            X = X + D[:, None, :] * s[..., None]
    n = len(T)
    Vall = X.reshape(-1, 3)
    offs = (np.arange(k) * n)[:, None, None]
    Fs = [(F[None] + offs).reshape(-1, F.shape[1]) for F in tpl.F]
    mb_add(mb, Vall, Fs)
    return k


class Column:
    """A tile column on a roof surface: dense polyline + lateral tangents."""

    def __init__(self, P, Lat):
        self.P = np.asarray(P, float)
        self.Lat = np.asarray(Lat, float)
        seg = np.linalg.norm(np.diff(self.P, axis=0), axis=1)
        self.s = np.concatenate([[0], np.cumsum(seg)])
        self.length = self.s[-1]

    def at(self, a):
        a = np.clip(np.asarray(a, float), 0, self.length)
        P = np.stack([np.interp(a, self.s, self.P[:, i]) for i in range(3)], -1)
        L = np.stack([np.interp(a, self.s, self.Lat[:, i]) for i in range(3)], -1)
        return P, L

    def stations(self, ashi, L, start=0.0, minlen=0.06, end=None):
        end = self.length if end is None else end
        a = np.arange(start, end - minlen, ashi)
        if len(a) == 0:
            return a, a, a
        b = np.minimum(a + L, end)
        return a, b, (b - a) / L


def stamp_column(mb, col, tpl, ashi, L, first=None, lift0=0.0, cuts=(), start=0.0, end=None, minlen=0.06,
                 counts=None, key=None):
    """Lay tiles along a Column (lower end first). first: template for the
    eave course (軒瓦). Returns number of tiles."""
    a, b, sc = col.stations(ashi, L, start, minlen, end)
    if len(a) == 0:
        return 0
    PA, LA = col.at(a)
    PB, _ = col.at(b)
    D, Lat, N = frames(PB - PA, LA)
    lift = np.full(len(a), lift0)
    n = 0
    if first is not None:
        n += place(first[0], first[1], PA[:1], D[:1], Lat[:1], N[:1], sc[:1], lift[:1], L, cuts)
        PA, D, Lat, N, sc, lift = PA[1:], D[1:], Lat[1:], N[1:], sc[1:], lift[1:]
    n += place(mb, tpl, PA, D, Lat, N, sc, lift, L, cuts)
    if counts is not None and key:
        counts[key] = counts.get(key, 0) + n
    return n


# ------------------------------------------------------------------ ridges

def path_frames(P):
    P = np.asarray(P, float)
    T = G.nrm(np.gradient(P, axis=0))
    side = np.cross(T, Z)
    side = G.nrm(side)
    return T, side


def ridge(parts, P, n_layers=5, w0=0.40, hn=0.044, inset=0.010, base_h=0.075, bury=0.20,
          lp=0.27, gap=0.008, droop=0.016, kan=True, kan_r=None, kan_flat=0.8, counts=None, key="ridge",
          end_pad=(0.0, 0.0)):
    """熨斗積み棟: 面戸(漆喰)+ 熨斗瓦 n段(左右割熨斗, 目地) + 冠瓦(雁振瓦).
    P: dense centre line at the tile-top level. parts: dict of geom.MB by role
    ('mendo','noshi','kanmuri'). Layers stack vertically (Z)."""
    P = G.resample(np.asarray(P, float), 0.03)
    T, side = path_frames(P)
    col = Column(P, side)
    Lr = col.length
    # 面戸 base (white plaster) continuous
    prof = np.array([(-w0 / 2 - 0.01, -bury), (w0 / 2 + 0.01, -bury), (w0 / 2 + 0.01, base_h), (-w0 / 2 - 0.01, base_h)])
    V, F = G.sweep(P, prof, mode="vertical", cap=True)
    parts["mendo"].add(V, F)
    # 熨斗 pieces
    boxes = []
    for i in range(n_layers):
        wi = w0 - 2 * inset * i
        z0 = base_h + i * hn
        off = (i % 2) * lp / 2
        a = np.arange(-off - end_pad[0], Lr + end_pad[1], lp)
        a0 = np.clip(a, -end_pad[0], Lr + end_pad[1])
        a1 = np.clip(a + lp - gap, -end_pad[0], Lr + end_pad[1])
        ok = a1 - a0 > 0.04
        a0, a1 = a0[ok], a1[ok]
        for sg in (-1, 1):
            boxes.append((a0, a1, sg, wi, z0))
    bV, bF = [], []
    nb = 0
    q = np.array([[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]])
    for (a0, a1, sg, wi, z0) in boxes:
        p0, s0 = _at_ext(col, a0)
        p1, s1 = _at_ext(col, a1)
        c_in, c_out = 0.003, wi / 2
        hh = hn - 0.011
        corners = []
        for (pp, ss) in ((p0, s0), (p1, s1)):
            for (c, dz) in ((c_in, 0.0), (c_out, -droop)):
                corners.append(pp + ss * (sg * c) + Z * (z0 + dz))
        # order: bottom (a0 in, a0 out, a1 out, a1 in), top same
        b = [corners[0], corners[1], corners[3], corners[2]]
        Vb = np.stack(b + [x + Z * hh for x in b], 1)  # (k,8,3)
        k = len(a0)
        bV.append(Vb.reshape(-1, 3))
        bF.append((q[None] + (np.arange(k) * 8 + nb)[:, None, None]).reshape(-1, 4))
        nb += k * 8
    if bV:
        mb_add(parts["noshi"], np.concatenate(bV), [np.concatenate(bF)])
    if counts is not None:
        counts[key + "_noshi"] = counts.get(key + "_noshi", 0) + nb // 8
    ztop = base_h + n_layers * hn
    if kan:
        wt = w0 - 2 * inset * (n_layers - 1)
        r = kan_r if kan_r else wt / 2 * 0.86
        tpl = maru_tpl(L=0.33, tama=0.04, Ro=r, tm=0.018, w0=0.0, n=10, flat=kan_flat).done()
        a = np.arange(-end_pad[0], Lr + end_pad[1] - 0.05, 0.29)
        b = np.minimum(a + 0.33, Lr + end_pad[1])
        PA, LA = _at_ext(col, a)
        PB, _ = _at_ext(col, b)
        D, Lat, N = frames(PB - PA, LA)
        PA = PA + Z * (ztop - 0.012)
        place(parts["kanmuri"], tpl, PA, D, Lat, N, (b - a) / 0.33)
        if counts is not None:
            counts[key + "_kanmuri"] = counts.get(key + "_kanmuri", 0) + len(a)
        ztop += r * kan_flat
    return ztop, P


def _at_ext(col, a):
    """Column.at with linear extrapolation beyond both ends."""
    a = np.asarray(a, float)
    P, L = col.at(a)
    d0 = G.nrm(col.P[1] - col.P[0]); d1 = G.nrm(col.P[-1] - col.P[-2])
    lo = a < 0; hi = a > col.length
    if np.any(lo):
        P[lo] = col.P[0] + d0 * a[lo][:, None]
    if np.any(hi):
        P[hi] = col.P[-1] + d1 * (a[hi] - col.length)[:, None]
    return P, L


# ------------------------------------------------------------------ ornaments

def oni_outline(W, H, n=64, style="oni"):
    """鬼瓦(雲型 鬼板) outline: legs straddling the ridge, scalloped cloud top,
    鰭 lobes on the sides. Origin at bottom centre."""
    pts = [(-0.5 * W, 0.0), (-0.24 * W, 0.0)]
    for a in np.linspace(math.pi, 0, 10):                      # ridge notch (足)
        pts.append((0.24 * W * math.cos(a), 0.17 * H * math.sin(a)))
    pts.append((0.5 * W, 0.0))
    # right side with 鰭 scallops
    for z in np.linspace(0.02, 0.46, 9) * H:
        pts.append((0.5 * W + 0.045 * W * abs(math.sin(3 * math.pi * z / (0.46 * H))), z))
    # top: ellipse with cloud lobes and a crown point
    for a in np.linspace(0.0, math.pi, n):
        rx, rz = 0.5 * W, 0.54 * H
        lobe = 1 + 0.07 * abs(math.sin(4.5 * a)) ** 0.7
        x = rx * math.cos(a) * lobe
        z = 0.46 * H + rz * math.sin(a) * lobe
        if abs(a - math.pi / 2) < 0.12:
            z += 0.06 * H * (1 - abs(a - math.pi / 2) / 0.12)
        pts.append((x, z))
    for z in np.linspace(0.46, 0.02, 9) * H:
        pts.append((-0.5 * W - 0.045 * W * abs(math.sin(3 * math.pi * z / (0.46 * H))), z))
    out = []
    for p in pts:
        if not out or abs(out[-1][0] - p[0]) + abs(out[-1][1] - p[1]) > 1e-6:
            out.append(p)
    return np.array(out)


def _frame(origin, facing):
    f = np.array([facing[0], facing[1], 0.0]); f = f / np.linalg.norm(f)
    U = np.cross(Z, f)
    return np.asarray(origin, float), U, f


def oni(mb, origin, facing, W=0.55, H=0.60, t=0.10, toribusuma=True, crest="tomoe", ridge_top=None):
    """鬼瓦 (鬼板型, 雲の縁・巴の中心・渦の浮彫・鳥衾)."""
    o, U, f = _frame(origin, facing)
    ol = oni_outline(W, H)
    mb.addt(G.extrude_poly(ol, t, (o - f * t / 2, U, Z), bevel=0.01))
    inner = G.offset_poly(G.ccw(ol), 0.055 * W)
    # raised rim (縁) as frame with hole
    mb.addt(G.extrude_poly(G.ccw(ol), 0.022, (o + f * 0.011, U, Z), holes=[inner], bevel=0.0))
    # central crest boss + tomoe
    cz = 0.50 * H
    rb = 0.17 * W
    c = o + Z * cz + f * 0.0
    V, F = G.lathe([(rb, 0.0), (rb, 0.03), (rb * 0.9, 0.045), (0.0, 0.05)], (0, 0, 0), 28)
    mb.add(_to_world(V, c, U, f), F)
    for poly in tomoe_polys(rb * 0.82, npts=8):
        V2, F2 = prism2d(poly, 0.05, 0.065, lambda a, b, h: np.stack([a, b, h], 1))
        mb_add(mb, _to_world(V2, c, U, f), F2)
    # cloud scrolls (渦) left/right
    for sg in (-1, 1):
        a = np.linspace(0, 2.6 * math.pi, 26)
        rr = 0.11 * W * (1 - a / (3.2 * math.pi))
        pts = np.stack([sg * (0.27 * W + rr * np.cos(a)) , 0.25 * H + rr * np.sin(a), np.full_like(a, 0.022)], 1)
        V3, F3 = tube(pts, 0.012, 5)
        mb_add(mb, _to_world(V3, o, U, f), F3)
        a = np.linspace(0, 1.8 * math.pi, 18)
        rr = 0.07 * W * (1 - a / (2.4 * math.pi))
        pts = np.stack([sg * (0.18 * W + rr * np.cos(a)), 0.80 * H + rr * np.sin(a), np.full_like(a, 0.022)], 1)
        V3, F3 = tube(pts, 0.010, 5)
        mb_add(mb, _to_world(V3, o, U, f), F3)
    if toribusuma:
        # 鳥衾: curved round tile projecting forward over the oni top
        zt = ridge_top if ridge_top is not None else o[2] + H * 0.85
        p0 = o - f * 0.25 + Z * (zt - o[2] - 0.03)
        p3 = o + f * 0.16 + Z * (H * 0.98)
        bz = G.bezier(p0, p0 + f * 0.18, p3 - f * 0.12 - Z * 0.03, p3, 12)
        r = 0.042 if W > 0.4 else 0.03
        V4, F4 = G.sweep(bz, G.circle_profile(r, 12), mode="normal")
        mb.add(V4, F4)
        tdir = G.nrm(bz[-1] - bz[-2])
        Vd, Fd = G.lathe([(r + 0.01, 0.0), (r + 0.01, 0.02), (0.0, 0.025)], (0, 0, 0), 16)
        Vd = _orient_z(Vd, tdir) + bz[-1]
        mb.add(Vd, Fd)
        for poly in tomoe_polys(r * 0.75, npts=6):
            V5, F5 = prism2d(poly, 0.025, 0.031, lambda a, b, h: np.stack([a, b, h], 1))
            mb_add(mb, _orient_z(V5, tdir) + bz[-1], F5)


def _to_world(V, c, U, f):
    """local (a=U, b=Z, h=f) -> world."""
    V = np.asarray(V, float)
    return np.asarray(c, float) + V[:, 0:1] * U + V[:, 1:2] * Z + V[:, 2:3] * f


def _orient_z(V, n):
    from .parts import orient
    return orient(V, (0, 0, 0), n)


def shishiguchi(mb, origin, facing, W=0.80, H=0.72, depth=0.45):
    """獅子口: box-like ridge end with 綾筋 (3 arched bands) and 経の巻 (3 rolls)."""
    o, U, f = _frame(origin, facing)
    # body: front outline (trapezoid + arched top), extruded backward
    pts = [(-0.50 * W, 0.0), (0.50 * W, 0.0), (0.50 * W, 0.55 * H)]
    for a in np.linspace(0, math.pi, 25):
        pts.append((0.50 * W * math.cos(a), 0.55 * H + 0.30 * H * math.sin(a) ** 0.8))
    pts.append((-0.50 * W, 0.55 * H))
    ol = np.array(pts)
    mb.addt(G.extrude_poly(ol, depth, (o - f * depth / 2, U, Z), bevel=0.012))
    # 綾筋: three concentric arched bands on the face
    for k, s in enumerate((0.92, 0.74, 0.56)):
        a = np.linspace(0.02, math.pi - 0.02, 26)
        x = 0.5 * W * s * np.cos(a)
        z = 0.55 * H * (0.15 + 0.85 * s) + 0.30 * H * s * np.sin(a) ** 0.8
        z = np.concatenate([[0.06 * H], z, [0.06 * H]]) if k == 0 else z
        x = np.concatenate([[x[0]], x, [x[-1]]]) if k == 0 else x
        pts3 = np.stack([x, z, np.full_like(x, 0.012)], 1)
        V, F = G.sweep(pts3, G.rect_profile(0.03, 0.024), mode="normal")
        mb.add(_to_world(V, o, U, f), F)
    # 経の巻: three rolls on top (axis along facing)
    r = 0.075 * W
    for xx in (-0.30 * W, 0.0, 0.30 * W):
        zc = 0.55 * H + 0.30 * H * (1 - (xx / (0.5 * W)) ** 2) ** 0.4 + r * 0.8
        c = o + U * xx + Z * zc
        V, F = G.sweep(np.array([c - f * (depth / 2 + 0.03), c + f * (depth / 2 + 0.04)]), G.circle_profile(r, 16), mode="normal")
        mb.add(V, F)
        for poly in tomoe_polys(r * 0.8, npts=6):
            V5, F5 = prism2d(poly, 0.0, 0.008, lambda a, b, h: np.stack([a, b, h], 1))
            mb_add(mb, _orient_z(V5, f) + c + f * (depth / 2 + 0.04), F5)
    # 鰭 (side fins)
    for sg in (-1, 1):
        fin = np.array([(0.0, 0.05 * H), (0.12 * W, 0.0), (0.16 * W, 0.18 * H), (0.10 * W, 0.40 * H), (0.0, 0.48 * H)])
        fin[:, 0] *= sg
        fin[:, 0] += sg * 0.5 * W
        mb.addt(G.extrude_poly(fin, 0.06, (o + f * 0.0, U, Z), bevel=0.0))


def tomoebuta(mb, origin, axis_dir, r=0.10, L=0.25):
    """巴蓋 / 隅巴: short round cover along the hip with a 巴 disc at its tip."""
    d = G.nrm(np.asarray(axis_dir, float))
    o = np.asarray(origin, float)
    V, F = G.sweep(np.array([o - d * L, o]), G.circle_profile(r, 16), mode="normal")
    mb.add(V, F)
    Vd, Fd = G.lathe([(r + 0.012, 0.0), (r + 0.012, 0.025), (0.0, 0.03)], (0, 0, 0), 20)
    mb.add(_orient_z(Vd, d) + o, Fd)
    for poly in tomoe_polys((r + 0.01) * 0.62, npts=7):
        V5, F5 = prism2d(poly, 0.03, 0.038, lambda a, b, h: np.stack([a, b, h], 1))
        mb_add(mb, _orient_z(V5, d) + o, F5)
    for k in range(12):
        a = 2 * math.pi * k / 12
        Vd, Fd = G.lathe([(0.006, 0.0), (0.006, 0.035), (0.0, 0.039)], (0.0, 0.0, 0.0), 6)
        Vd = Vd + np.array([0.80 * (r + 0.012) * math.cos(a), 0.80 * (r + 0.012) * math.sin(a), 0])
        mb.add(_orient_z(Vd, d) + o, Fd)
