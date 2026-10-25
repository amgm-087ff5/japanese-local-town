#!/usr/bin/env python3
"""Procedurally build a highly detailed Japanese shrine worship hall (拝殿).

    python3 haiden/blender/build_haiden.py --out haiden/out

Form: 入母屋造・平入・桁行3間×梁間2間・正面1間向拝(軒唐破風)・銅板段葺・丹塗.
Coordinates: X = 桁行 (width), Y = 梁間 (depth, front = -Y), Z = up, metres.
Outputs: haiden.blend, haiden.glb, haiden_web.glb (Draco when gltf-transform
is available), stats.json, textures/ (baked material tiles).
"""
import argparse
import datetime
import json
import math
import os
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import bmesh  # noqa: E402

from hlib import geom as G  # noqa: E402
from hlib import parts as PT  # noqa: E402
from hlib.materials import Mats, bake_tiles, glb_material, BAKE  # noqa: E402

FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"

# --------------------------------------------------------------------------
P = None
M = None
ROOT = None
OBJ_COUNTER = {}


def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        ROOT.children.link(c)
    return c


def emit(name, mb, mat, cname, smooth=32.0):
    if mb is None or mb.empty():
        return None
    me = mb.to_mesh(name)
    me.materials.append(M[mat])
    if smooth:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(smooth))
    ob = bpy.data.objects.new(name, me)
    coll(cname).objects.link(ob)
    return ob


def one(vf):
    return G.MB().addt(vf)


# ==========================================================================
# frames / helpers

class Frame:
    """Plan grid of the main hall."""

    def __init__(self, p):
        bx, by = p["bays_x"], p["bays_y"]
        self.X0 = sum(bx) / 2
        self.Y0 = sum(by) / 2
        self.xs = np.concatenate([[0], np.cumsum(bx)]) - self.X0
        self.ys = np.concatenate([[0], np.cumsum(by)]) - self.Y0

    def perimeter_pillars(self):
        out = []
        for i, x in enumerate(self.xs):
            for j, y in enumerate(self.ys):
                if i in (0, len(self.xs) - 1) or j in (0, len(self.ys) - 1):
                    out.append((x, y))
        return out


SIDES = {
    # name: (along-axis, outward sign, which wall coordinate)
    "Front": ("x", -1),
    "Back": ("x", 1),
    "Right": ("y", 1),
    "Left": ("y", -1),
}


def side_xy(side, W0, o, s):
    """Plan point at outward offset o from wall line W0, along-coordinate s."""
    ax, sg = SIDES[side]
    if ax == "x":
        return s, sg * (W0 + o)
    return sg * (W0 + o), s


def side_dir(side):
    ax, sg = SIDES[side]
    return np.array([0.0, sg, 0.0]) if ax == "x" else np.array([sg, 0.0, 0.0])


def along_dir(side):
    ax, _ = SIDES[side]
    return np.array([1.0, 0, 0]) if ax == "x" else np.array([0, 1.0, 0])


# ==========================================================================
# Roof math

class RoofFn:
    """Teri (concave) roof height + corner sori, for the main roof."""

    def __init__(self, Xe, Ye, Z0, R):
        self.Xe, self.Ye, self.Z0, self.R = Xe, Ye, Z0, R
        dd = np.linspace(0, Ye + 2.0, 4000)
        s = R["slope_eave"] + (R["slope_ridge"] - R["slope_eave"]) * np.clip(dd / Ye, 0, 1) ** R["slope_pow"]
        F = np.concatenate([[0], np.cumsum((s[1:] + s[:-1]) / 2 * np.diff(dd))])
        self.dd, self.Fv, self.sv = dd, F, s

    def F(self, d):
        return np.interp(d, self.dd, self.Fv)

    def slope(self, d):
        return np.interp(d, self.dd, self.sv)

    def S(self, x, y):
        R = self.R
        ax = self.Xe - np.abs(x)
        ay = self.Ye - np.abs(y)
        d = np.minimum(ax, ay)
        u = np.abs(ax - ay)
        g = np.clip(1 - u / R["sori_len"], 0, 1) ** R["sori_pow"]
        f = np.clip(1 - np.maximum(d, 0) / R["sori_fade"], 0, 1) ** 2
        return R["sori_rise"] * g * f

    def lip(self, d):
        R = self.R
        return R["step_lip"] * (1 - np.mod(d, R["step_len"]) / R["step_len"])

    def z(self, x, y, d, top=True):
        z = self.Z0 + self.F(d) + self.S(x, y)
        if top:
            z = z + self.lip(d)
        return z


def step_rows(a, b, base, step, eps=0.004, extra=()):
    rows = set(np.round(np.linspace(a, b, max(2, int(math.ceil((b - a) / base)) + 1)), 6))
    k0 = int(math.floor(a / step))
    for k in range(k0, int(math.ceil(b / step)) + 1):
        for v in (k * step, k * step - eps):
            if a < v < b:
                rows.add(round(v, 6))
    for v in extra:
        if a < v < b:
            rows.add(round(v, 6))
    return np.array(sorted(rows))


def slab_grid(X, Y, Zt, Zb):
    """Closed slab from a (nr,nc) grid of top/bottom heights."""
    nr, nc = X.shape
    top = np.stack([X, Y, Zt], -1).reshape(-1, 3)
    bot = np.stack([X, Y, Zb], -1).reshape(-1, 3)
    V = np.vstack([top, bot])
    n = nr * nc
    Ft = G.grid_faces(nr, nc)
    Fb = G.grid_faces(nr, nc, flip=True) + n
    loop = [(0, j) for j in range(nc)] + [(i, nc - 1) for i in range(1, nr)] + \
           [(nr - 1, j) for j in range(nc - 2, -1, -1)] + [(i, 0) for i in range(nr - 2, 0, -1)]
    L = np.array([i * nc + j for i, j in loop])
    L2 = np.roll(L, -1)
    Fw = np.stack([L2, L, L + n, L2 + n], 1)
    return V, np.vstack([Ft, Fb, Fw])


def grid_patch(rows, rng, ncol, mapxy):
    T = np.linspace(0, 1, ncol)
    nr = len(rows)
    X = np.zeros((nr, ncol)); Y = np.zeros((nr, ncol))
    for i, d in enumerate(rows):
        a, b = rng(d)
        s = a + (b - a) * T
        X[i], Y[i] = mapxy(d, s)
    D = np.repeat(np.asarray(rows)[:, None], ncol, 1)
    return X, Y, D


# ==========================================================================
# Eave stack (rafters etc.) - shared logic for main hall and kohai

class Eave:
    def __init__(self, zr0, sj, sh, o_k, noki, T, ura_out=None):
        self.zr0, self.sj, self.sh, self.o_k, self.noki, self.T = zr0, sj, sh, o_k, noki, T
        self.ura_out = T["uragou_out"] if ura_out is None else ura_out

    def ji_bot(self, o):
        return self.zr0 - self.sj * o

    @property
    def kioi_bot(self):
        return self.ji_bot(self.o_k) + self.T["ji_h"]

    @property
    def kioi_top(self):
        return self.kioi_bot + self.T["kioi_h"]

    def hien_bot(self, o):
        return self.kioi_top - self.sh * (o - self.o_k)

    @property
    def kay_o(self):
        return self.noki - self.T["kayaoi_w"] / 2

    @property
    def kay_bot(self):
        return self.hien_bot(self.kay_o) + self.T["hien_h"] - 0.01

    @property
    def kay_top(self):
        return self.kay_bot + self.T["kayaoi_h"]

    @property
    def ura_top(self):
        return self.kay_top + self.T["uragou_t"]

    @property
    def o_eave(self):
        return self.noki + self.ura_out


# ==========================================================================
# BUILD

def build(p):
    global P
    P = p
    T = p["taruki"]
    R = p["roof"]
    K = p["kumi"]
    KH = p["kohai"]
    fr = Frame(p)
    X0, Y0 = fr.X0, fr.Y0
    pr = p["pillar_d"] / 2
    info = {}

    # ---------------------------------------------------------------- heights
    z_kidan = p["kidan_h"]
    z_kame = z_kidan + p["kamebara_h"]
    z_soseki = z_kame + p["soseki_h"]
    z_ptop = p["pillar_top"]
    nk0, nk1 = p["nuki_z"]
    z_daito1 = z_ptop + K["daito"][1]
    z_hij0 = z_daito1 - 0.06
    z_hij1 = z_hij0 + K["hijiki_h"]
    z_mak1 = z_hij1 + K["makito"][1]
    de = 0.32                                   # 出三斗 projection
    gagyo_h = 0.22
    z_gagyo_top = z_mak1 + gagyo_h
    zr0 = z_gagyo_top + de * T["ji_slope"]      # rafter bottom at wall line
    E = Eave(zr0, T["ji_slope"], T["hien_slope"], p["kioi_d"], p["noki_de"], T)
    Xe = X0 + E.o_eave
    Ye = Y0 + E.o_eave
    Z0 = E.ura_top + R["nokitsuke_t"]
    RF = RoofFn(Xe, Ye, Z0, R)
    dg = R["irimoya_d"]
    Xg = Xe - dg
    ho = R["hafu_out"]
    z_apex = RF.z(0, 0, Ye)

    # kohai
    yk = -Y0 - KH["depth"]
    kx = fr.xs[1:3]                  # kohai pillar x (= centre bay pillars)
    Wk = abs(kx[0]) + KH["side_de"]
    kp_base = z_kidan + 0.20
    kp_top = KH["pillar_top"]
    kz_daito1 = kp_top + KH["daito"][1]
    kz_hij0 = kz_daito1 - 0.05
    kz_hij1 = kz_hij0 + KH["hijiki_h"]
    kz_mak1 = kz_hij1 + KH["makito"][1]
    kt = kz_mak1 + KH["keta_h"]       # kohai rafter bottom at keta line
    o_in = -(abs(yk) - (Y0 + de))     # kohai rafters reach main gagyo
    sjk = (z_gagyo_top - kt) / (-o_in)
    EK = Eave(kt, sjk, T["hien_slope"], KH["kioi_d"], KH["noki_de"], T)
    yke = yk - EK.o_eave              # kohai roof eave line (y)
    Zk0 = EK.ura_top + R["nokitsuke_t"]
    kh_h = KH["karahafu_h"]
    kh_w = KH["karahafu_halfw"]

    def bump(x):
        t = np.clip(np.abs(x) / kh_w, 0, 1)
        return kh_h * np.cos(t * np.pi / 2) ** 2

    def kfade(dk):
        return np.clip(1 - np.asarray(dk) / KH["karahafu_fade"], 0, 1) ** 1.5

    # join of kohai roof into main front slope
    y_j = -Y0 - 0.55
    d_j = Ye - abs(y_j)
    dk_j = y_j - yke

    info.update(dict(X0=X0, Y0=Y0, Xe=Xe, Ye=Ye, Z0=Z0, z_apex=float(z_apex), Xg=Xg, Wk=Wk, yk=yk, yke=yke))

    # ================================================================ 01 Kiso
    C = "01_Kiso_Foundation"
    kx0 = X0 + p["kidan_margin"]
    ky1 = Y0 + p["kidan_margin"]
    ky0 = -(Y0 + p["kidan_margin"] + p["kidan_front_extra"])
    core = G.MB().addt(G.box((-kx0 + 0.05, ky0 + 0.05, 0), (kx0 - 0.05, ky1 - 0.05, z_kidan - 0.02)))
    emit("Kidan_Core", core, "Ishi_Granite", C)
    # facing blocks + coping stones (葛石)
    face = G.MB(); cope = G.MB()
    rng = np.random.default_rng(7)
    edges = [((-kx0, ky0), (kx0, ky0)), ((kx0, ky0), (kx0, ky1)), ((kx0, ky1), (-kx0, ky1)), ((-kx0, ky1), (-kx0, ky0))]
    for (a, b) in edges:
        a = np.array(a); b = np.array(b)
        L = np.linalg.norm(b - a)
        dv = (b - a) / L
        nv = np.array([dv[1], -dv[0]])
        n = max(1, int(round(L / 0.9)))
        cuts = np.linspace(0, L, n + 1)
        for k in range(n):
            for (z0, z1, depth, ch, mbx, w0) in ((0.0, z_kidan - 0.12, 0.10, 0.008, face, 0.0), (z_kidan - 0.12, z_kidan, 0.36, 0.015, cope, 0.03)):
                l0 = cuts[k] + 0.004; l1 = cuts[k + 1] - 0.004
                if mbx is face:
                    # stagger
                    pass
                p0 = a + dv * l0 + nv * w0
                p1 = a + dv * l1 + nv * w0 - nv * depth
                mn = np.minimum(p0, p1); mx = np.maximum(p0, p1)
                jit = rng.uniform(-0.004, 0.004)
                mbx.addt(G.cbox((mn[0], mn[1], z0), (mx[0], mx[1], z1 + jit), ch))
    emit("Kidan_Hameishi_FaceStones", face, "Ishi_Granite", C)
    emit("Kidan_Katsuraishi_Coping", cope, "Ishi_Granite", C)
    # top paving
    pav = G.MB()
    pitch = 0.6
    xs_ = np.arange(-kx0 + 0.36, kx0 - 0.36, pitch)
    ys_ = np.arange(ky0 + 0.36, ky1 - 0.36, pitch)
    for i, x in enumerate(xs_):
        for y in ys_:
            off = 0.3 if i % 2 else 0
            yy = y + off
            if yy + pitch > ky1 - 0.36:
                continue
            x1 = min(x + pitch - 0.012, kx0 - 0.36)
            pav.addt(G.cbox((x, yy, z_kidan - 0.03), (x1, yy + pitch - 0.012, z_kidan + rng.uniform(-0.003, 0.004)), 0.006))
    emit("Kidan_Shikiishi_Paving", pav, "Ishi_Granite", C)
    # front stone steps
    st = G.MB()
    for k in range(2):
        h = z_kidan * (2 - k) / 2
        st.addt(G.cbox((-1.6 + 0.0, ky0 - 0.36 * (2 - k), 0), (1.6, ky0 - 0.36 * (1 - k) + 0.02, h - 0.005), 0.012))
    emit("Kidan_Ishidan_Steps", st, "Ishi_Granite", C)

    # kamebara
    km = G.MB()
    out0 = p["kamebara_out"] + 0.15
    secs = []
    for t in np.linspace(0, np.pi / 2, 10):
        off = 0.15 + p["kamebara_out"] * math.cos(t)
        secs.append((X0 + off, Y0 + off, z_kidan + p["kamebara_h"] * math.sin(t)))
    km.addt(G.loft_rect(secs, (0, 0), ch=0.25))
    emit("Kamebara_Plinth", km, "Shikkui_Plaster", C)
    # soseki
    ss = G.MB()
    for (x, y) in fr.perimeter_pillars():
        ss.addt(G.lathe([(pr + 0.07, z_kame - 0.02), (pr + 0.07, z_soseki - 0.03), (pr + 0.04, z_soseki), (0, z_soseki)], (x, y, 0), 28))
    emit("Soseki_Base_Stones", ss, "Ishi_Granite", C)

    # ================================================================ 02 Jiku (axial)
    C = "02_Jiku_Frame"
    for n_, (x, y) in enumerate(fr.perimeter_pillars(), 1):
        prof = [(pr - 0.012, z_soseki), (pr, z_soseki + 0.012), (pr, z_ptop - 0.002), (pr * 0.95, z_ptop)]
        mb = one(G.lathe(prof, (x, y, 0), p["pillar_seg"]))
        emit("Hashira_Pillar_%02d" % n_, mb, "Nuri_Shu_Vermilion", C, smooth=50)
    # sill
    sill = G.MB()
    for side in SIDES:
        ax, sg = SIDES[side]
        A = X0 if ax == "x" else Y0
        W = Y0 if ax == "x" else X0
        p0 = side_xy(side, W, 0, -A); p1 = side_xy(side, W, 0, A)
        sill.addt(G.beams([(p0[0], p0[1], (z_soseki + p["floor_z"]) / 2)], [(p1[0], p1[1], (z_soseki + p["floor_z"]) / 2)], 0.14, p["floor_z"] - z_soseki, 0.01))
    emit("Dodai_Sill", sill, "Kiji_Old_Wood", C)

    # nageshi (ji / uchi) - outside the pillars, wrap around
    nd = p["nageshi_depth"]
    for nm, (z0, z1) in (("Ji", p["nageshi_ji_z"]), ("Uchi", p["nageshi_uchi_z"])):
        mb = G.MB()
        for side in SIDES:
            ax, _ = SIDES[side]
            A = X0 if ax == "x" else Y0
            W = Y0 if ax == "x" else X0
            o = pr + nd / 2 - 0.02
            ext = A + o + nd / 2
            p0 = side_xy(side, W, o, -ext); p1 = side_xy(side, W, o, ext)
            # profile: slightly sloped top face (長押の見付)
            path = np.array([[p0[0], p0[1], 0], [p1[0], p1[1], 0]])
            h = z1 - z0
            prof = np.array([(-nd / 2, 0), (nd / 2, 0), (nd / 2, h - 0.01), (nd / 2 - 0.012, h), (-nd / 2, h)])
            if SIDES[side][1] < 0 and ax == "x" or (ax == "y" and SIDES[side][1] < 0):
                prof[:, 0] *= 1
            V, F = G.sweep(path, prof, mode="vertical")
            V[:, 2] += z0
            mb.add(V, F)
        emit("Nageshi_%s_Tie" % nm, mb, "Nuri_Shu_Vermilion", C)
    # kugikakushi (rokuyo) on nageshi at each pillar
    kk = G.MB()
    for (x, y) in fr.perimeter_pillars():
        for (z0, z1) in (p["nageshi_ji_z"], p["nageshi_uchi_z"]):
            zc = (z0 + z1) / 2
            for side in SIDES:
                ax, sg = SIDES[side]
                W = Y0 if ax == "x" else X0
                on = (ax == "x" and abs(y - sg * Y0) < 1e-6) or (ax == "y" and abs(x - sg * X0) < 1e-6)
                if not on:
                    continue
                n = side_dir(side)
                c = np.array([x, y, zc]) + n * (pr + nd - 0.02)
                kk.addt(PT.rokuyo(c, n, r=0.055, seg=24))
    emit("Kugikakushi_Rokuyo_Kanagu", kk, "Kanagu_Gold", C)

    # kashiranuki + kibana
    nb = G.MB(); kb = G.MB()
    zc = (nk0 + nk1) / 2
    for side in ("Front", "Back", "Right", "Left"):
        ax, _ = SIDES[side]
        A = X0 if ax == "x" else Y0
        W = Y0 if ax == "x" else X0
        p0 = side_xy(side, W, 0, -A); p1 = side_xy(side, W, 0, A)
        nb.addt(G.beams([(p0[0], p0[1], zc)], [(p1[0], p1[1], zc)], p["nuki_w"], nk1 - nk0, 0.012))
    for (x, y) in [(sx * X0, sy * Y0) for sx in (-1, 1) for sy in (-1, 1)]:
        for d in (np.array([np.sign(x), 0, 0]), np.array([0, np.sign(y), 0])):
            ol = PT.kibana_outline(p["kibana_len"] + pr, nk1 - nk0 + 0.02)
            kb.addt(G.extrude_poly(ol, p["nuki_w"], (np.array([x, y, zc]), d, np.array([0, 0, 1.0])), bevel=0.008))
    emit("Kashiranuki_HeadTie", nb, "Nuri_Shu_Vermilion", C)
    emit("Kibana_BeamEnd", kb, "Nuri_Shu_Vermilion", C)

    # ================================================================ walls / doors (Tategu)
    C = "08_Tategu_Walls"
    z_in0 = p["nageshi_ji_z"][1]
    z_in1 = p["nageshi_uchi_z"][0]
    kab = G.MB()     # gofun small walls
    ita = G.MB()     # plank walls
    kos = G.MB()     # lattice bars
    wak = G.MB()     # frames
    dark = G.MB()
    gold = G.MB()

    def bay_list(side):
        ax, _ = SIDES[side]
        arr = fr.xs if ax == "x" else fr.ys
        return [(arr[i], arr[i + 1], i) for i in range(len(arr) - 1)]

    def wall_box(side, s0, s1, z0, z1, t, o=0.0, mb=None):
        W = Y0 if SIDES[side][0] == "x" else X0
        a = side_xy(side, W, o - t / 2, s0); b = side_xy(side, W, o + t / 2, s1)
        mb.addt(G.box((min(a[0], b[0]), min(a[1], b[1]), z0), (max(a[0], b[0]), max(a[1], b[1]), z1)))

    def lattice(side, s0, s1, z0, z1, pitch=0.095, bar=0.028, frame_w=0.075, o=0.0, horiz=True, split=False):
        wall_box(side, s0, s1, z0, z0 + frame_w, 0.07, o, wak)
        wall_box(side, s0, s1, z1 - frame_w, z1, 0.07, o, wak)
        wall_box(side, s0, s0 + frame_w, z0, z1, 0.07, o, wak)
        wall_box(side, s1 - frame_w, s1, z0, z1, 0.07, o, wak)
        if split:
            m = (s0 + s1) / 2
            wall_box(side, m - frame_w / 2, m + frame_w / 2, z0, z1, 0.07, o, wak)
            # door pulls
            for sgn in (-1, 1):
                W = Y0 if SIDES[side][0] == "x" else X0
                c = side_xy(side, W, o + 0.05, m + sgn * 0.09)
                gold.addt(PT.rokuyo((c[0], c[1], (z0 + z1) / 2), side_dir(side), r=0.04, seg=16))
        ss = np.arange(s0 + frame_w + pitch / 2, s1 - frame_w, pitch)
        for s in ss:
            wall_box(side, s - bar / 2, s + bar / 2, z0 + frame_w, z1 - frame_w, bar, o, kos)
        if horiz:
            for z in np.arange(z0 + frame_w + pitch, z1 - frame_w, pitch):
                wall_box(side, s0 + frame_w, s1 - frame_w, z - bar / 2, z + bar / 2, bar * 0.8, o - 0.008, kos)
        wall_box(side, s0, s1, z0, z1, 0.02, -0.16, dark)

    for side in SIDES:
        for (s0, s1, i) in bay_list(side):
            a0, a1 = s0 + pr - 0.01, s1 - pr + 0.01
            # small walls (小壁) above uchi-nageshi and above kashiranuki
            wall_box(side, a0, a1, p["nageshi_uchi_z"][1] - 0.02, nk0 + 0.01, 0.06, 0, kab)
            wall_box(side, a0, a1, nk1 - 0.01, z_mak1 + 0.02, 0.06, 0, kab)
            if side == "Front":
                lattice(side, a0, a1, z_in0, z_in1, split=(i == 1))
            elif side in ("Right", "Left") and ((side == "Right" and i == 0) or (side == "Left" and i == 0)):
                zm = (z_in0 + z_in1) / 2 - 0.15
                wall_box(side, a0, a1, z_in0, zm, 0.04, 0, ita)
                wall_box(side, a0, a1, zm - 0.04, zm + 0.04, 0.07, 0, wak)
                lattice(side, a0, a1, zm, z_in1, pitch=0.11, horiz=False)
            else:
                wall_box(side, a0, a1, z_in0 - 0.02, z_in1 + 0.02, 0.05, 0, ita)
                # plank joints (目板)
                for s in np.arange(a0 + 0.3, a1 - 0.1, 0.3):
                    wall_box(side, s - 0.02, s + 0.02, z_in0, z_in1, 0.07, 0, wak)
    emit("Kokabe_SmallWall_Gofun", kab, "Gofun_White", C)
    emit("Itakabe_PlankWall", ita, "Nuri_Shu_Vermilion", C)
    emit("Koshido_Lattice_Bars", kos, "Kuro_Urushi_Lacquer", C)
    emit("Koshido_Frame", wak, "Nuri_Shu_Vermilion", C)
    emit("Uchi_Interior_Dark", dark, "Uchi_Dark", C, smooth=0)
    emit("Tobira_Kanagu_Pulls", gold, "Kanagu_Gold", C)

    # ================================================================ 03 Kumimono
    C = "03_Kumimono_Brackets"
    dai = G.MB(); hij = G.MB(); mak = G.MB(); tsk = G.MB(); kae = G.MB(); fl_ = G.MB()
    for (x, y) in fr.perimeter_pillars():
        dai.addt(PT.to_block(x, y, z_ptop, K["daito"][0], K["daito"][1]))
        corner = abs(abs(x) - X0) < 1e-6 and abs(abs(y) - Y0) < 1e-6
        walls = []
        if abs(abs(y) - Y0) < 1e-6:
            walls.append(np.array([1.0, 0, 0]))
        if abs(abs(x) - X0) < 1e-6:
            walls.append(np.array([0, 1.0, 0]))
        outs = []
        if abs(abs(y) - Y0) < 1e-6:
            outs.append(np.array([0, np.sign(y), 0]))
        if abs(abs(x) - X0) < 1e-6:
            outs.append(np.array([np.sign(x), 0, 0]))
        zc = (z_hij0 + z_hij1) / 2
        for wdir in walls:
            # along-wall hijiki with 3 makito (平三斗)
            if corner:
                # corner: shorter, toward the inside only + extends outward
                pass
            ol = PT.hijiki_outline(K["hijiki_len"], K["hijiki_h"])
            hij.addt(G.extrude_poly(ol, K["hijiki_w"], (np.array([x, y, zc]), wdir, np.array([0, 0, 1.0])), bevel=0.006))
            for off in (-K["hijiki_len"] / 2 + K["makito"][0] / 2, 0, K["hijiki_len"] / 2 - K["makito"][0] / 2):
                c = np.array([x, y, 0]) + wdir * off
                mak.addt(PT.to_block(c[0], c[1], z_hij1, K["makito"][0], K["makito"][1]))
        for odir in outs:
            # outward hijiki (出三斗) carrying the gagyo
            L = de + 0.42
            c = np.array([x, y, zc]) + odir * (de + 0.21 - L / 2)
            ol = PT.hijiki_outline(L, K["hijiki_h"])
            hij.addt(G.extrude_poly(ol, K["hijiki_w"], (c, odir, np.array([0, 0, 1.0])), bevel=0.006))
            cm = np.array([x, y, 0]) + odir * de
            mak.addt(PT.to_block(cm[0], cm[1], z_hij1, K["makito"][0], K["makito"][1]))
        if corner:
            dg_ = np.array([np.sign(x), np.sign(y), 0]) / math.sqrt(2)
            L = de * math.sqrt(2) + 0.5
            c = np.array([x, y, zc]) + dg_ * (de * math.sqrt(2) + 0.25 - L / 2)
            ol = PT.hijiki_outline(L, K["hijiki_h"])
            hij.addt(G.extrude_poly(ol, K["hijiki_w"], (c, dg_, np.array([0, 0, 1.0])), bevel=0.006))
            cm = np.array([x + np.sign(x) * de, y + np.sign(y) * de, 0])
            mak.addt(PT.to_block(cm[0], cm[1], z_hij1, K["makito"][0], K["makito"][1]))
    # kentozuka / kaerumata between pillars
    for side in SIDES:
        for (s0, s1, i) in bay_list(side):
            s = (s0 + s1) / 2
            W = Y0 if SIDES[side][0] == "x" else X0
            c = side_xy(side, W, 0, s)
            if side == "Front":
                ol = PT.kaerumata_outline(0.78, z_hij1 - nk1 + 0.01)
                kae.addt(G.extrude_poly(ol, 0.10, (np.array([c[0], c[1], nk1 - 0.005]), along_dir(side), np.array([0, 0, 1.0])), bevel=0.01))
                fl_.addt(PT.flower((c[0], c[1] - 0.03, nk1 + (z_hij1 - nk1) * 0.36), (0, -1, 0), r=0.085))
            else:
                tsk.addt(G.cbox((c[0] - 0.06, c[1] - 0.06, nk1 - 0.01), (c[0] + 0.06, c[1] + 0.06, z_hij1), 0.01))
            mak.addt(PT.to_block(c[0], c[1], z_hij1, K["makito"][0], K["makito"][1]))
            # gagyo support makito on outward line too (spaced)
    emit("Masugumi_Daito_BearingBlock", dai, "Nuri_Shu_Vermilion", C)
    emit("Masugumi_Hijiki_BracketArm", hij, "Nuri_Shu_Vermilion", C)
    emit("Masugumi_Makito_SmallBlock", mak, "Nuri_Shu_Vermilion", C)
    emit("Kentozuka_Strut", tsk, "Nuri_Shu_Vermilion", C)
    emit("Kaerumata_FrogLeg", kae, "Kiji_Hinoki_Wood", C)
    emit("Kaerumata_Hana_CarvedFlower", fl_, "Kanagu_Gold", C)

    # keta (wall plate) + gagyo (outer purlin)
    kt_mb = G.MB(); gg = G.MB()
    for side in SIDES:
        ax, _ = SIDES[side]
        A = X0 if ax == "x" else Y0
        W = Y0 if ax == "x" else X0
        p0 = side_xy(side, W, 0, -A - 0.25); p1 = side_xy(side, W, 0, A + 0.25)
        h = zr0 - z_mak1
        kt_mb.addt(G.beams([(p0[0], p0[1], z_mak1 + h / 2)], [(p1[0], p1[1], z_mak1 + h / 2)], K["keta_w"], h, 0.012))
        ext = A + de + 0.35
        p0 = side_xy(side, W, de, -ext); p1 = side_xy(side, W, de, ext)
        path = np.array([[p0[0], p0[1], z_mak1 + gagyo_h / 2], [p1[0], p1[1], z_mak1 + gagyo_h / 2]])
        V, F = G.sweep(path, G.rect_profile(0.2, gagyo_h, 0.05), mode="vertical")
        gg.add(V, F)
    emit("Keta_WallPlate", kt_mb, "Nuri_Shu_Vermilion", C)
    emit("Gagyo_OuterPurlin", gg, "Nuri_Shu_Vermilion", C)

    # ================================================================ 04 Noki (eaves)
    C = "04_Noki_Eaves"
    pitch = T["spacing_target"]

    def lift(x, y):
        return RF.S(x, y)

    def in_kohai(side, s, margin=0.0):
        return side == "Front" and abs(s) < Wk + margin

    ji = G.MB(); hi = G.MB(); tips = G.MB(); tipg = G.MB()
    kio = G.MB(); kay = G.MB(); ura = G.MB(); sof = G.MB(); men = G.MB()
    for side in SIDES:
        ax, _ = SIDES[side]
        A = X0 if ax == "x" else Y0
        W = Y0 if ax == "x" else X0
        n_half = int((A + p["noki_de"]) / pitch) + 1
        ss = (np.arange(-n_half, n_half) + 0.5) * pitch
        J0, J1, H0, H1 = [], [], [], []
        for s in ss:
            if in_kohai(side, s, 0.06):
                continue
            o0 = -0.10 if abs(s) <= A else abs(s) - A + T["sumiki_w"] * 0.6
            if o0 > p["noki_de"] - 0.15:
                continue
            # ji-daruki
            if o0 < E.o_k:
                a = side_xy(side, W, o0, s); b = side_xy(side, W, E.o_k + 0.06, s)
                za = E.ji_bot(o0) + T["ji_h"] / 2 + lift(*a)
                zb = E.ji_bot(E.o_k + 0.06) + T["ji_h"] / 2 + lift(*b)
                J0.append((a[0], a[1], za)); J1.append((b[0], b[1], zb))
            oh0 = max(o0, E.o_k - 0.22)
            a = side_xy(side, W, oh0, s); b = side_xy(side, W, p["noki_de"] - 0.03, s)
            za = E.hien_bot(oh0) + T["hien_h"] / 2 + lift(*a)
            zb = E.hien_bot(p["noki_de"] - 0.03) + T["hien_h"] / 2 + lift(*b)
            H0.append((a[0], a[1], za)); H1.append((b[0], b[1], zb))
        if J0:
            ji.addt(G.beams(J0, J1, T["ji_w"], T["ji_h"], 0.006))
            # ji tip end-grain caps (木口 黄土)
            J0a, J1a = np.array(J0), np.array(J1)
            dvec = G.nrm(J1a - J0a)
            tips.addt(G.beams(J1a - dvec * 0.004, J1a + dvec * 0.004, T["ji_w"] + 0.004, T["ji_h"] + 0.004))
        if H0:
            hi.addt(G.beams(H0, H1, T["hien_w"], T["hien_h"], 0.006))
            H0a, H1a = np.array(H0), np.array(H1)
            dvec = G.nrm(H1a - H0a)
            tipg.addt(G.beams(H1a - dvec * 0.02, H1a + dvec * 0.006, T["hien_w"] + 0.008, T["hien_h"] + 0.008))
        # kioi / kayaoi / uragou along the side
        segs = [(-1, 1)]
        if side == "Front":
            segs = [(-1, -Wk / (A + 3)), (Wk / (A + 3), 1)]
        for (f0, f1) in segs:
            for (mbx, o, w, h, zfun) in (
                    (kio, E.o_k, T["kioi_w"], T["kioi_h"], lambda o: E.kioi_bot),
                    (kay, E.kay_o, T["kayaoi_w"], T["kayaoi_h"], lambda o: E.kay_bot),
                    (ura, p["noki_de"] + T["uragou_out"] / 2 - 0.06, T["kayaoi_w"] + T["uragou_out"] + 0.06, T["uragou_t"], lambda o: E.kay_top)):
                L = A + o
                s0 = f0 * L if f0 == -1 else f0 * (A + 3)
                s1 = f1 * L if f1 == 1 else f1 * (A + 3)
                sv = np.linspace(s0, s1, max(8, int(abs(s1 - s0) / 0.08)))
                pts = []
                for s in sv:
                    q = side_xy(side, W, o, s)
                    pts.append((q[0], q[1], zfun(o) + h / 2 + lift(*q)))
                V, F = G.sweep(np.array(pts), G.rect_profile(w, h, 0.004), mode="vertical")
                mbx.add(V, F)
        # soffit boards (化粧裏板) and menido boards
        for (oa, ob_, zf, hh) in ((-0.05, E.o_k, E.ji_bot, T["ji_h"]), (E.o_k, E.kay_o, E.hien_bot, T["hien_h"])):
            rows = np.linspace(oa, ob_, 8)

            def rngf(o, _A=A):
                return (-(_A + max(o, 0)), _A + max(o, 0))
            X, Y, D = grid_patch(rows, rngf, int(2 * (A + p["noki_de"]) / 0.08), lambda o, s, _s=side, _W=W: side_xy(_s, _W, o, s))
            Zt = np.vectorize(zf)(D) + hh + lift(X, Y) + 0.016
            if side == "Front":
                # cut out kohai zone by clamping columns (keep two halves)
                for half in (-1, 1):
                    msk = (half * X) >= Wk
                    if msk.sum() < 4:
                        continue
                    cols = np.where(msk.all(0))[0]
                    if len(cols) < 2:
                        continue
                    Xs, Ys, Zs = X[:, cols], Y[:, cols], Zt[:, cols]
                    sof.addt(slab_grid(Xs, Ys, Zs, Zs - 0.014))
            else:
                sof.addt(slab_grid(X, Y, Zt, Zt - 0.014))
        # menido (white boards between rafters over the wall plate)
        p0 = side_xy(side, W, 0.0, -A); p1 = side_xy(side, W, 0.0, A)
        if side == "Front":
            for (q0, q1) in (((-A, 0), (-Wk, 0)), ((Wk, 0), (A, 0))):
                a = side_xy(side, W, 0.0, q0[0]); b = side_xy(side, W, 0.0, q1[0])
                men.addt(G.beams([(a[0], a[1], zr0 + T["ji_h"] / 2)], [(b[0], b[1], zr0 + T["ji_h"] / 2)], 0.03, T["ji_h"]))
        else:
            men.addt(G.beams([(p0[0], p0[1], zr0 + T["ji_h"] / 2)], [(p1[0], p1[1], zr0 + T["ji_h"] / 2)], 0.03, T["ji_h"]))
    emit("Jidaruki_BaseRafters", ji, "Nuri_Shu_Vermilion", C)
    emit("Hiendaruki_FlyingRafters", hi, "Nuri_Shu_Vermilion", C)
    emit("Taruki_Koguchi_EndPaint", tips, "Ki_Ochre", C)
    emit("Taruki_Saki_Kanagu", tipg, "Kanagu_Gold", C)
    emit("Kioi_RafterRail", kio, "Nuri_Shu_Vermilion", C)
    emit("Kayaoi_EaveRail", kay, "Nuri_Shu_Vermilion", C)
    emit("Uragou_EaveBoard", ura, "Kiji_Hinoki_Wood", C)
    emit("Noki_Uraita_Soffit", sof, "Gofun_White", C)
    emit("Menido_InfillBoard", men, "Gofun_White", C)

    # sumiki (hip rafters)
    sk = G.MB(); skk = G.MB()
    for sx in (-1, 1):
        for sy in (-1, 1):
            pts = []
            for o in np.linspace(-0.1, p["noki_de"] + 0.06, 14):
                x = sx * (X0 + o); y = sy * (Y0 + o)
                if o < E.o_k:
                    z = E.ji_bot(o) + T["sumiki_h"] / 2 - 0.02
                else:
                    z = min(E.ji_bot(o) + T["sumiki_h"] / 2 - 0.02, E.hien_bot(o) + T["sumiki_h"] / 2 - 0.03)
                pts.append((x, y, z + lift(x, y)))
            pts = np.array(pts)
            V, F = G.sweep(pts, G.rect_profile(T["sumiki_w"], T["sumiki_h"], 0.01), mode="vertical")
            sk.add(V, F)
            tip = pts[-1]
            dv = G.nrm(pts[-1] - pts[-2])
            skk.addt(G.beams([tip - dv * 0.05], [tip + dv * 0.012], T["sumiki_w"] + 0.016, T["sumiki_h"] + 0.016))
    emit("Sumiki_HipRafter", sk, "Nuri_Shu_Vermilion", C)
    emit("Sumiki_Kanagu", skk, "Kanagu_Gold", C)

    # ================================================================ 05 Yane (roof)
    C = "05_Yane_Roof"
    sl = R["step_len"]
    th = R["thick"]
    cs = R["col_step"]
    roof = G.MB()

    def zt(X, Y, D):
        return RF.z(X, Y, D, True)

    def zb(X, Y, D):
        return RF.z(X, Y, D, False) - th

    def add_patch(mb, rows, rngf, ncol, mapxy):
        X, Y, D = grid_patch(rows, rngf, ncol, mapxy)
        mb.addt(slab_grid(X, Y, zt(X, Y, D), zb(X, Y, D)))

    for side in SIDES:
        ax, sg = SIDES[side]
        A_e = Xe if ax == "x" else Ye   # along half-length at eave
        Wd = Ye if ax == "x" else Xe

        def mp(d, s, _side=side, _Wd=Wd):
            # offset is measured inward from eave: o = E.o_eave - d
            return side_xy(_side, _Wd - E.o_eave, E.o_eave - d, s) if False else (
                (s, SIDES[_side][1] * (_Wd - d)) if SIDES[_side][0] == "x" else (SIDES[_side][1] * (_Wd - d), s))
        if ax == "x":
            if side == "Front":
                rows = step_rows(0, d_j, 0.05, sl)
                for half in (-1, 1):
                    def rngf(d, h=half):
                        a, b = Wk, A_e - d
                        return (a, b) if h > 0 else (-b, -a)
                    add_patch(roof, rows, rngf, int((A_e - Wk) / cs) + 2, mp)
                rows = step_rows(d_j, dg, 0.05, sl)
                add_patch(roof, rows, lambda d: (-(A_e - d), A_e - d), int(2 * A_e / cs), mp)
            else:
                rows = step_rows(0, dg, 0.05, sl)
                add_patch(roof, rows, lambda d: (-(A_e - d), A_e - d), int(2 * A_e / cs), mp)
            rows = step_rows(dg, Ye, 0.06, sl)
            add_patch(roof, rows, lambda d: (-(Xg + ho), Xg + ho), int(2 * (Xg + ho) / cs), mp)
        else:
            rows = step_rows(0, dg, 0.05, sl)
            add_patch(roof, rows, lambda d: (-(A_e - d), A_e - d), int(2 * A_e / cs), mp)
    emit("Yane_Doban_CopperRoof", roof, "Doban_Rokusho_Copper", C, smooth=40)

    # hakomune (box ridge) + onita
    hm = G.MB(); crest = G.MB(); oni = G.MB()
    L = Xg + ho + 0.04
    zb0 = z_apex - 0.32
    hb = R["hakomune_h"]
    hm.addt(G.cbox((-L, -0.19, zb0), (L, 0.19, zb0 + 0.32 + hb * 0.72), 0.02))
    hm.addt(G.cbox((-L - 0.03, -0.235, zb0 + 0.32 + hb * 0.72), (L + 0.03, 0.235, zb0 + 0.32 + hb * 0.72 + 0.06), 0.015))
    hm.addt(G.cbox((-L - 0.05, -0.27, zb0 + 0.32 + hb * 0.72 + 0.06), (L + 0.05, 0.27, zb0 + 0.32 + hb), 0.03))
    hm.addt(G.cbox((-L, -0.215, zb0 + 0.32 + 0.05), (L, 0.215, zb0 + 0.32 + 0.11), 0.01))
    for xx in np.arange(-L + 0.55, L - 0.4, 1.1):
        for sy in (-1, 1):
            crest.addt(PT.rokuyo((xx, sy * 0.19, zb0 + 0.32 + hb * 0.42), (0, sy, 0), r=0.08, seg=24))
    for sx in (-1, 1):
        ol = PT.onita_outline(0.86, R["onita_h"])
        oni.addt(G.extrude_poly(ol, 0.10, (np.array([sx * (L + 0.06), 0, zb0 + 0.1]), np.array([0, sx * -1.0, 0]) * -1 if sx > 0 else np.array([0, -1.0, 0]), np.array([0, 0, 1.0])), bevel=0.015))
        crest.addt(PT.rokuyo((sx * (L + 0.12), 0, zb0 + 0.1 + R["onita_h"] * 0.55), (sx, 0, 0), r=0.13, seg=32))
    emit("Hakomune_BoxRidge", hm, "Doban_Rokusho_Copper", C)
    emit("Onita_RidgeEndBoard", oni, "Doban_Rokusho_Copper", C)
    emit("Mune_Mon_Crest", crest, "Kanagu_Gold", C)

    # sumimune (hip ridges) + mizukiri on side-skirt top edge
    smb = G.MB(); smo = G.MB(); mz = G.MB()
    for sx in (-1, 1):
        for sy in (-1, 1):
            ds = np.linspace(0.12, dg - 0.02, 30)
            x = sx * (Xe - ds); y = sy * (Ye - ds)
            z = RF.z(x, y, ds, False) + 0.05
            pts = np.stack([x, y, z], 1)
            V, F = G.sweep(pts[::-1], G.rect_profile(R["sumimune_w"], 0.24, 0.02), mode="vertical")
            smb.add(V, F)
            # tip ornament (small oni)
            dvec = G.nrm(np.array([sx, sy, 0.0]))
            ol = PT.onita_outline(0.36, 0.42)
            fu = np.array([-dvec[1], dvec[0], 0])
            smo.addt(G.extrude_poly(ol, 0.06, (pts[0] + np.array([0, 0, -0.10]) + dvec * 0.03, fu, np.array([0, 0, 1.0])), bevel=0.01))
        yy = np.linspace(-(Ye - dg), Ye - dg, 30)
        zz = RF.z(sx * Xg, yy, dg, False) + 0.03
        pts = np.stack([np.full_like(yy, sx * (Xg + 0.02)), yy, zz], 1)
        V, F = G.sweep(pts, G.rect_profile(0.16, 0.12, 0.02), mode="vertical")
        mz.add(V, F)
    emit("Sumimune_HipRidge", smb, "Doban_Rokusho_Copper", C)
    emit("Sumioni_HipEndBoard", smo, "Doban_Rokusho_Copper", C)
    emit("Mizukiri_GableSkirtRidge", mz, "Doban_Rokusho_Copper", C)

    # ================================================================ 06 Tsuma (gable)
    C = "06_Tsuma_Gable"
    hf = G.MB(); gb = G.MB(); kg = G.MB(); tb = G.MB(); gk = G.MB(); hk = G.MB()
    for sx in (-1, 1):
        xh = sx * (Xg + ho + R["hafu_t"] / 2 - 0.01)
        yy = np.linspace(-(Ye - dg) - 0.05, (Ye - dg) + 0.05, 61)
        dd = Ye - np.abs(yy)
        ztop = RF.z(np.full_like(yy, sx * (Xg + ho)), yy, dd, True) + 0.035
        # 拝み (apex) slight cusp
        zc_ = ztop - R["hafu_h"] / 2
        pts = np.stack([np.full_like(yy, xh), yy, zc_], 1)
        V, F = G.sweep(pts, G.rect_profile(R["hafu_t"], R["hafu_h"], 0.01), mode="vertical")
        hf.add(V, F)
        # gold edge strip on hafu
        pts2 = pts.copy(); pts2[:, 2] = ztop - 0.012; pts2[:, 0] += sx * 0.002
        V, F = G.sweep(pts2, G.rect_profile(R["hafu_t"] + 0.006, 0.026), mode="vertical")
        hk.add(V, F)
        # tsuma wall polygon (board) + kitsuregoshi lattice
        xw = sx * Xg
        zbase = RF.z(Xg, 0.0, dg, False) + 0.03
        ys = np.linspace(-(Ye - dg), Ye - dg, 81)
        ztp = RF.z(np.full_like(ys, Xg), ys, Ye - np.abs(ys), False) - th - 0.01
        mask = ztp > zbase + 0.02
        yv = ys[mask]; zv = ztp[mask]
        outline = [(yv[0], zbase), (yv[-1], zbase)] + [(y_, z_) for y_, z_ in zip(yv[::-1], zv[::-1])]
        outline = np.array(outline)
        o2 = outline.copy(); o2[:, 1] -= zbase
        fr_ = (np.array([xw, 0, zbase]), np.array([0, 1.0, 0]) * (1 if sx > 0 else -1), np.array([0, 0, 1.0]))
        o3 = o2.copy()
        if sx < 0:
            o3[:, 0] *= -1
        gb.addt(G.extrude_poly(o3, 0.04, fr_))
        # lattice bars
        for y_ in np.arange(yv[0] + 0.06, yv[-1], 0.13):
            ztop_y = np.interp(y_, ys, ztp)
            if ztop_y - zbase < 0.05:
                continue
            kg.addt(G.beams([(xw + sx * 0.035, y_, zbase)], [(xw + sx * 0.035, y_, ztop_y)], 0.035, 0.035))
        for z_ in np.arange(zbase + 0.10, zv.max(), 0.13):
            inside = yv[zv > z_ + 0.01]
            if len(inside) < 2:
                continue
            kg.addt(G.beams([(xw + sx * 0.055, inside[0], z_)], [(xw + sx * 0.055, inside[-1], z_)], 0.035, 0.035))
        # tsuma-koryo / beam at the bottom of the gable
        tb.addt(G.cbox((xw - 0.08, -(Ye - dg), zbase - 0.06), (xw + 0.08, Ye - dg, zbase + 0.10), 0.02) if True else None)
        # gegyo (懸魚) at the apex
        W_, H_ = 0.80, 0.78
        z_g = RF.z(Xg + ho, 0, Ye, False) - R["hafu_h"] + 0.06
        org = np.array([xh + sx * (R["hafu_t"] / 2 + 0.03), 0, z_g])
        ol = PT.gegyo_outline(W_, H_)
        holes = [PT.heart(0, -H_ * 0.42, 0.20), PT.heart(-W_ * 0.17, -H_ * 0.65, 0.15), PT.heart(W_ * 0.17, -H_ * 0.65, 0.15)]
        U = np.array([0, -sx * 1.0, 0])
        gk.addt(G.extrude_poly(ol, 0.06, (org, U, np.array([0, 0, 1.0])), holes=holes))
        for side_ in (1, -1):
            fin = PT.gegyo_fin(W_, H_, side_)
            gk.addt(G.extrude_poly(fin, 0.04, (org + np.array([-sx * 0.01, 0, 0]), U, np.array([0, 0, 1.0]))))
        hk.addt(PT.rokuyo(org + np.array([sx * 0.035, 0, -H_ * 0.12]), (sx, 0, 0), r=0.09, seg=24))
        hk.addt(PT.rokuyo(org + np.array([sx * 0.035, 0, -H_ * 0.85]), (sx, 0, 0), r=0.06, seg=24))
    emit("Hafu_GableBargeboard", hf, "Nuri_Shu_Vermilion", C)
    emit("Hafu_Kanagu_GoldTrim", hk, "Kanagu_Gold", C)
    emit("Tsuma_GableBoard", gb, "Kuro_Urushi_Lacquer", C)
    emit("Kitsuregoshi_GableLattice", kg, "Nuri_Shu_Vermilion", C)
    emit("Tsuma_Koryo_GableBeam", tb, "Nuri_Shu_Vermilion", C)
    emit("Gegyo_GablePendant", gk, "Kiji_Hinoki_Wood", C)

    # ================================================================ 07 Kohai
    C = "07_Kohai_Porch"
    kp = G.MB(); ks = G.MB()
    kw = KH["pillar_w"]
    for n_, x in enumerate(kx, 1):
        ks.addt(G.cbox((x - 0.20, yk - 0.20, z_kidan - 0.02), (x + 0.20, yk + 0.20, kp_base), 0.03))
        mb = one(G.loft_rect([(kw / 2, kw / 2, kp_base), (kw / 2, kw / 2, kp_top)], (x, yk), ch=0.03))
        emit("Kohai_Hashira_Pillar_%02d" % n_, mb, "Nuri_Shu_Vermilion", C)
        # gold base ring (根巻金具)
        gm = one(G.loft_rect([(kw / 2 + 0.008, kw / 2 + 0.008, kp_base), (kw / 2 + 0.008, kw / 2 + 0.008, kp_base + 0.16),
                             (kw / 2 + 0.002, kw / 2 + 0.002, kp_base + 0.17)], (x, yk), ch=0.035))
        emit("Kohai_Nemaki_Kanagu_%02d" % n_, gm, "Kanagu_Gold", C)
    emit("Kohai_Soban_StoneBase", ks, "Ishi_Granite", C)

    # koryo (rainbow beam = kohai head tie) with kibana
    kr = G.MB(); kkb = G.MB()
    kzr0, kzr1 = kp_top - 0.32, kp_top
    xr = np.linspace(kx[0], kx[1], 40)
    arch = 0.035 * (1 - (xr / kx[1]) ** 2)
    pts = np.stack([xr, np.full_like(xr, yk), (kzr0 + kzr1) / 2 + arch / 2], 1)
    hgt = (kzr1 - kzr0) + arch * 0.0
    V, F = G.sweep(pts, G.rect_profile(0.15, kzr1 - kzr0, 0.02), mode="vertical")
    kr.add(V, F)
    for x in kx:
        for d in (np.array([np.sign(x), 0, 0]), np.array([0, -1.0, 0])):
            ol = PT.kibana_outline(0.42 + kw / 2, kzr1 - kzr0)
            kkb.addt(G.extrude_poly(ol, 0.15, (np.array([x, yk, (kzr0 + kzr1) / 2]), d, np.array([0, 0, 1.0])), bevel=0.01))
    emit("Kohai_Koryo_RainbowBeam", kr, "Nuri_Shu_Vermilion", C)
    emit("Kohai_Kibana_BeamEnd", kkb, "Nuri_Shu_Vermilion", C)

    # kohai kumimono
    kd = G.MB(); khj = G.MB(); kmk = G.MB(); kkae = G.MB(); ktb = G.MB()
    for x in kx:
        kd.addt(PT.to_block(x, yk, kp_top, KH["daito"][0], KH["daito"][1]))
        zc = (kz_hij0 + kz_hij1) / 2
        ol = PT.hijiki_outline(0.86, KH["hijiki_h"])
        khj.addt(G.extrude_poly(ol, 0.11, (np.array([x, yk, zc]), np.array([1.0, 0, 0]), np.array([0, 0, 1.0])), bevel=0.006))
        for off in (-0.43 + KH["makito"][0] / 2, 0, 0.43 - KH["makito"][0] / 2):
            kmk.addt(PT.to_block(x + off, yk, kz_hij1, KH["makito"][0], KH["makito"][1]))
        # tabasami (手挟) on the inner side, under the rising rafters
        Lt = 0.85
        H0 = KH["keta_h"] + 0.02
        H1 = H0 + Lt * sjk
        ol = PT.tabasami_outline(Lt, H0, H1)
        ktb.addt(G.extrude_poly(ol, 0.09, (np.array([x, yk + 0.08, kz_mak1 - 0.02]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])), bevel=0.006))
    # kaerumata on koryo centre
    ol = PT.kaerumata_outline(0.66, kz_hij1 - kzr1 + 0.01)
    kkae.addt(G.extrude_poly(ol, 0.10, (np.array([0, yk, kzr1 - 0.005]), np.array([1.0, 0, 0]), np.array([0, 0, 1.0])), bevel=0.01))
    kmk.addt(PT.to_block(0, yk, kz_hij1, KH["makito"][0], KH["makito"][1]))
    kfl = one(PT.flower((0, yk - 0.03, kzr1 + (kz_hij1 - kzr1) * 0.36), (0, -1, 0), r=0.075))
    emit("Kohai_Kaerumata_Hana_CarvedFlower", kfl, "Kanagu_Gold", C)
    emit("Kohai_Daito_BearingBlock", kd, "Nuri_Shu_Vermilion", C)
    emit("Kohai_Hijiki_BracketArm", khj, "Nuri_Shu_Vermilion", C)
    emit("Kohai_Makito_SmallBlock", kmk, "Nuri_Shu_Vermilion", C)
    emit("Kohai_Kaerumata_FrogLeg", kkae, "Kiji_Hinoki_Wood", C)
    emit("Kohai_Tabasami_CarvedWedge", ktb, "Kiji_Hinoki_Wood", C)

    # kohai keta
    kk_ = G.MB()
    kk_.addt(G.beams([(-Wk + 0.15, yk, kz_mak1 + KH["keta_h"] / 2)], [(Wk - 0.15, yk, kz_mak1 + KH["keta_h"] / 2)], KH["keta_w"], KH["keta_h"], 0.015))
    emit("Kohai_Keta_Purlin", kk_, "Nuri_Shu_Vermilion", C)

    # ebikoryo
    eb = G.MB()
    z_main_nuki = (nk0 + nk1) / 2
    for x in kx:
        p0 = np.array([x, yk, (kzr0 + kzr1) / 2 - 0.02])
        p3 = np.array([x, -Y0, z_main_nuki])
        span = abs(p3[1] - p0[1])
        bz = G.bezier(p0, p0 + [0, span * 0.45, 0], p3 + [0, -span * 0.45, 0], p3, 32)
        sc = np.linspace(1.0, 0.85, len(bz))
        V, F = G.sweep(bz, G.rect_profile(0.12, 0.25, 0.02), mode="vertical", scale=np.stack([np.ones_like(sc), sc], 1))
        eb.add(V, F)
    emit("Ebikoryo_CurvedTieBeam", eb, "Nuri_Shu_Vermilion", C)

    # kohai rafters & eave
    def klift(x, o):
        dk = EK.o_eave - o
        return bump(x) * kfade(dk)

    kji = G.MB(); khi = G.MB(); ktip = G.MB(); ktg = G.MB(); kki = G.MB(); kka = G.MB(); kur = G.MB(); ksof = G.MB()
    nkr = int(Wk / pitch)
    xs_r = (np.arange(-nkr, nkr) + 0.5) * pitch
    J0, J1, H0_, H1_ = [], [], [], []
    for x in xs_r:
        if abs(x) > Wk - 0.06:
            continue
        a = (x, yk - o_in); b = (x, yk - (EK.o_k + 0.06))
        J0.append((a[0], a[1], EK.ji_bot(o_in) + T["ji_h"] / 2))
        J1.append((b[0], b[1], EK.ji_bot(EK.o_k + 0.06) + T["ji_h"] / 2 + klift(x, EK.o_k + 0.06)))
        o_a = EK.o_k - 0.22; o_b = KH["noki_de"] - 0.03
        H0_.append((x, yk - o_a, EK.hien_bot(o_a) + T["hien_h"] / 2 + klift(x, o_a)))
        H1_.append((x, yk - o_b, EK.hien_bot(o_b) + T["hien_h"] / 2 + klift(x, o_b)))
    kji.addt(G.beams(J0, J1, T["ji_w"], T["ji_h"], 0.006))
    khi.addt(G.beams(H0_, H1_, T["hien_w"], T["hien_h"], 0.006))
    J1a = np.array(J1); dv = G.nrm(J1a - np.array(J0))
    ktip.addt(G.beams(J1a - dv * 0.004, J1a + dv * 0.004, T["ji_w"] + 0.004, T["ji_h"] + 0.004))
    H1a = np.array(H1_); dv = G.nrm(H1a - np.array(H0_))
    ktg.addt(G.beams(H1a - dv * 0.02, H1a + dv * 0.006, T["hien_w"] + 0.008, T["hien_h"] + 0.008))
    for (mbx, o, w, h, z0f) in ((kki, EK.o_k, T["kioi_w"], T["kioi_h"], EK.kioi_bot),
                                (kka, EK.kay_o, T["kayaoi_w"], T["kayaoi_h"], EK.kay_bot),
                                (kur, KH["noki_de"] + T["uragou_out"] / 2 - 0.06, T["kayaoi_w"] + T["uragou_out"] + 0.06, T["uragou_t"], EK.kay_top)):
        xv = np.linspace(-Wk, Wk, 90)
        pts = np.stack([xv, np.full_like(xv, yk - o), z0f + h / 2 + klift(xv, o)], 1)
        V, F = G.sweep(pts, G.rect_profile(w, h, 0.004), mode="vertical")
        mbx.add(V, F)
    for (oa, ob_, zf, hh) in ((o_in, EK.o_k, EK.ji_bot, T["ji_h"]), (EK.o_k, EK.kay_o, EK.hien_bot, T["hien_h"])):
        rows = np.linspace(oa, ob_, 14)
        X, Y, D = grid_patch(rows, lambda o: (-Wk + 0.04, Wk - 0.04), 70, lambda o, s: (s, yk - o))
        Zt = zf(D) + hh + klift(X, D) + 0.016
        ksof.addt(slab_grid(X, Y, Zt, Zt - 0.014))
    emit("Kohai_Jidaruki_BaseRafters", kji, "Nuri_Shu_Vermilion", C)
    emit("Kohai_Hiendaruki_FlyingRafters", khi, "Nuri_Shu_Vermilion", C)
    emit("Kohai_Taruki_Koguchi_EndPaint", ktip, "Ki_Ochre", C)
    emit("Kohai_Taruki_Saki_Kanagu", ktg, "Kanagu_Gold", C)
    emit("Kohai_Kioi_RafterRail", kki, "Nuri_Shu_Vermilion", C)
    emit("Kohai_Kayaoi_EaveRail", kka, "Nuri_Shu_Vermilion", C)
    emit("Kohai_Uragou_EaveBoard", kur, "Kiji_Hinoki_Wood", C)
    emit("Kohai_Uraita_Soffit", ksof, "Gofun_White", C)

    # kohai roof (joins the main front slope)
    zj_main = lambda x: RF.z(x, np.full_like(x, y_j), np.full_like(x, d_j), False)
    m1 = RF.slope(d_j)
    m0 = KH["roof_slope_eave"]
    rows = step_rows(0, dk_j, 0.05, sl)
    X, Y, D = grid_patch(rows, lambda d: (-Wk, Wk), int(2 * Wk / 0.05), lambda d, s: (s, yke + d))
    t = D / dk_j
    z1 = zj_main(X)
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1; h10 = t ** 3 - 2 * t ** 2 + t; h01 = -2 * t ** 3 + 3 * t ** 2; h11 = t ** 3 - t ** 2
    zbase = h00 * Zk0 + h10 * dk_j * m0 + h01 * z1 + h11 * dk_j * m1
    zbase = zbase + bump(X) * kfade(D)
    ztop = zbase + RF.lip(D) * (1 - t)
    emit("Kohai_Yane_Doban_CopperRoof", one(slab_grid(X, Y, ztop, zbase - th)), "Doban_Rokusho_Copper", C, smooth=40)
    info["Zk0"] = float(Zk0)

    # karahafu board + side hafu + uketo gegyo
    kb_ = G.MB(); kbg = G.MB(); ug = G.MB()
    xv = np.linspace(-Wk - 0.02, Wk + 0.02, 120)
    zt_e = Zk0 + bump(xv) + RF.lip(0) + 0.03
    pts = np.stack([xv, np.full_like(xv, yke - 0.035), zt_e - 0.16], 1)
    V, F = G.sweep(pts, G.rect_profile(0.07, 0.32, 0.012), mode="vertical")
    kb_.add(V, F)
    pts2 = pts.copy(); pts2[:, 2] = zt_e - 0.012; pts2[:, 1] -= 0.003
    V, F = G.sweep(pts2, G.rect_profile(0.078, 0.026), mode="vertical")
    kbg.add(V, F)
    for sx in (-1, 1):
        dks = np.linspace(0, abs(yke) - Ye + 0.15, 30)
        x = np.full_like(dks, sx * (Wk + 0.035))
        tt = dks / dk_j
        zz = (2 * tt ** 3 - 3 * tt ** 2 + 1) * Zk0 + (tt ** 3 - 2 * tt ** 2 + tt) * dk_j * m0 + (-2 * tt ** 3 + 3 * tt ** 2) * zj_main(x) + (tt ** 3 - tt ** 2) * dk_j * m1
        zz = zz + bump(x) * kfade(dks) + 0.03
        pts = np.stack([x, yke + dks, zz - 0.15], 1)
        V, F = G.sweep(pts, G.rect_profile(0.06, 0.30, 0.01), mode="vertical")
        kb_.add(V, F)
    W_, H_ = 0.55, 0.55
    org = np.array([0, yke - 0.08, Zk0 + kh_h - 0.25])
    ug.addt(G.extrude_poly(PT.gegyo_outline(W_, H_), 0.05, (org, np.array([1.0, 0, 0]), np.array([0, 0, 1.0])),
                           holes=[PT.heart(0, -H_ * 0.45, 0.13)]))
    kbg.addt(PT.rokuyo(org + np.array([0, -0.03, -H_ * 0.15]), (0, -1, 0), r=0.06, seg=24))
    emit("Karahafu_CurvedBargeboard", kb_, "Nuri_Shu_Vermilion", C)
    emit("Karahafu_Kanagu_GoldTrim", kbg, "Kanagu_Gold", C)
    emit("Uketo_Gegyo_Pendant", ug, "Kiji_Hinoki_Wood", C)

    # ================================================================ 09 En (veranda), koran, kizahashi
    C = "09_En_Veranda"
    eo = 1.05
    ez = p["en_z"]
    en = G.MB(); eg = G.MB(); et = G.MB(); ets = G.MB()
    # front en
    bw = 0.16
    for x in np.arange(-(X0 + eo), X0 + eo - 0.01, bw):
        en.addt(G.box((x + 0.004, -(Y0 + eo), ez - 0.04), (min(x + bw, X0 + eo) - 0.004, -(Y0 + pr), ez)))
    for sx in (-1, 1):
        for y in np.arange(-(Y0 + pr), Y0 + 0.35, bw):
            x0_, x1_ = X0 + pr, X0 + eo
            if sx < 0:
                x0_, x1_ = -x1_, -x0_
            en.addt(G.box((x0_, y + 0.004, ez - 0.04), (x1_, min(y + bw, Y0 + 0.35) - 0.004, ez)))
    # en-katsura edge beams
    eg.addt(G.cbox((-(X0 + eo), -(Y0 + eo) - 0.02, ez - 0.16), (X0 + eo, -(Y0 + eo) + 0.10, ez - 0.035), 0.01))
    for sx in (-1, 1):
        a, b = sorted([sx * (X0 + eo) - sx * 0.10, sx * (X0 + eo) + sx * 0.02])
        eg.addt(G.cbox((a, -(Y0 + eo), ez - 0.16), (b, Y0 + 0.35, ez - 0.035), 0.01))
    # en-tsuka posts on stones
    for x in np.arange(-(X0 + eo - 0.05), X0 + eo, p["en_tsuka_step"]):
        for yv_ in (-(Y0 + eo - 0.05),):
            et.addt(G.cbox((x - 0.06, yv_ - 0.06, z_kidan + 0.06), (x + 0.06, yv_ + 0.06, ez - 0.15), 0.01))
            ets.addt(G.cbox((x - 0.11, yv_ - 0.11, z_kidan - 0.02), (x + 0.11, yv_ + 0.11, z_kidan + 0.07), 0.02))
    for sx in (-1, 1):
        for y in np.arange(-(Y0 + eo - 0.05) + p["en_tsuka_step"], Y0 + 0.35, p["en_tsuka_step"]):
            x = sx * (X0 + eo - 0.05)
            et.addt(G.cbox((x - 0.06, y - 0.06, z_kidan + 0.06), (x + 0.06, y + 0.06, ez - 0.15), 0.01))
            ets.addt(G.cbox((x - 0.11, y - 0.11, z_kidan - 0.02), (x + 0.11, y + 0.11, z_kidan + 0.07), 0.02))
    emit("En_Ita_VerandaBoards", en, "Kiji_Old_Wood", C)
    emit("En_Katsura_EdgeBeam", eg, "Nuri_Shu_Vermilion", C)
    emit("Entsuka_VerandaPost", et, "Nuri_Shu_Vermilion", C)
    emit("Entsuka_Ishi_PostStone", ets, "Ishi_Granite", C)

    # koran (擬宝珠高欄)
    kr_rail = G.MB(); kr_post = G.MB(); gbs = G.MB(); kr_to = G.MB()
    zk_ji = ez + 0.06
    zk_hira = ez + 0.40
    zk_kaki = ez + 0.74
    lo = X0 + eo - 0.06
    lyf = -(Y0 + eo - 0.06)
    stw = 1.08

    def rail_run(a, b, oyabashira_ends=(False, False)):
        a = np.asarray(a, float); b = np.asarray(b, float)
        for (z, w, h, rnd) in ((ez + 0.03, 0.08, 0.06, False), (zk_hira, 0.06, 0.05, False)):
            kr_rail.addt(G.beams([(a[0], a[1], z)], [(b[0], b[1], z)], w, h, 0.008))
        # kaki (round top rail)
        path = np.array([[a[0], a[1], zk_kaki], [b[0], b[1], zk_kaki]])
        V, F = G.sweep(path, G.circle_profile(0.034, 14), mode="normal")
        kr_rail.add(V, F)
        L = np.linalg.norm(b - a)
        n = max(1, int(L / 0.62))
        for k in range(1, n):
            q = a + (b - a) * k / n
            kr_post.addt(G.cbox((q[0] - 0.03, q[1] - 0.03, ez + 0.06), (q[0] + 0.03, q[1] + 0.03, zk_hira - 0.025), 0.006))
            kr_post.addt(G.cbox((q[0] - 0.022, q[1] - 0.022, zk_hira + 0.025), (q[0] + 0.022, q[1] + 0.022, zk_kaki - 0.07), 0.005))
            kr_to.addt(PT.to_block(q[0], q[1], zk_kaki - 0.075, 0.08, 0.045))
        for e_, flag in zip((a, b), oyabashira_ends):
            if flag:
                kr_post.addt(G.cbox((e_[0] - 0.055, e_[1] - 0.055, ez - 0.02), (e_[0] + 0.055, e_[1] + 0.055, zk_kaki + 0.06), 0.012))
                gbs.addt(PT.giboshi(e_[0], e_[1], zk_kaki + 0.06, 0.62, 24))

    rail_run((-lo - 0.12, lyf), (-stw, lyf), (False, True))
    rail_run((stw, lyf), (lo + 0.12, lyf), (True, False))
    for sx in (-1, 1):
        rail_run((sx * lo, lyf - 0.12), (sx * lo, Y0 + 0.30), (False, True))
    emit("Koran_Rails_Balustrade", kr_rail, "Nuri_Shu_Vermilion", C)
    emit("Koran_Tsuka_Posts", kr_post, "Nuri_Shu_Vermilion", C)
    emit("Koran_To_Blocks", kr_to, "Nuri_Shu_Vermilion", C)
    emit("Giboshi_Finial", gbs, "Seido_Bronze", C)

    # wakishoji (side screens at the back end of the side en)
    ws = G.MB(); wsf = G.MB()
    for sx in (-1, 1):
        xa, xb = sorted([sx * (X0 + pr), sx * (X0 + eo)])
        y = Y0 + 0.33
        wsf.addt(G.cbox((xa, y - 0.04, ez), (xb, y + 0.04, ez + 0.07), 0.008))
        wsf.addt(G.cbox((xa, y - 0.04, z_in1 - 0.07), (xb, y + 0.04, z_in1), 0.008))
        wsf.addt(G.cbox((xb - 0.07 if sx > 0 else xa, y - 0.045, ez), (xb if sx > 0 else xa + 0.07, y + 0.045, z_in1), 0.008))
        ws.addt(G.box((xa, y - 0.015, ez + 0.07), (xb, y + 0.015, z_in1 - 0.07)))
    emit("Wakishoji_Frame", wsf, "Nuri_Shu_Vermilion", C)
    emit("Wakishoji_Panel", ws, "Gofun_White", C)

    # hamayuka + kizahashi
    hy = G.MB(); kz = G.MB(); kzs = G.MB()
    y_ef = -(Y0 + eo)
    nst = 3
    rise = (ez - 0.58) / nst
    tread = 0.27
    y_hb = y_ef - tread * (nst - 1)
    hy_y0 = yk - 0.40
    for x in np.arange(-1.40, 1.40, 0.16):
        hy.addt(G.box((x + 0.004, hy_y0, 0.54), (x + 0.156, y_hb, 0.58)))
    hy.addt(G.cbox((-1.42, hy_y0 - 0.02, z_kidan), (1.42, y_hb, 0.54), 0.01))
    for k in range(1, nst):
        zt_ = 0.58 + rise * k
        kz.addt(G.cbox((-stw + 0.06, y_ef - tread * k, zt_ - 0.05), (stw - 0.06, y_ef - tread * (k - 1) + 0.02, zt_), 0.006))
        kz.addt(G.box((-stw + 0.06, y_ef - tread * (k - 1) - 0.03, zt_ - rise), (stw - 0.06, y_ef - tread * (k - 1) - 0.01, zt_ - 0.05)))
    for sx in (-1, 1):
        x = sx * (stw - 0.03)
        pts = np.array([[x, y_ef + 0.02, ez - 0.06], [x, y_hb - 0.02, 0.58 - 0.06]])
        V, F = G.sweep(pts, G.rect_profile(0.07, 0.26, 0.01), mode="vertical")
        kzs.add(V, F)
        # nobori koran (stair rail)
        a = np.array([x, y_ef, 0]); b = np.array([x, y_hb + 0.06, 0])
        for (dz, w, h) in ((0.06, 0.07, 0.05), (0.40, 0.06, 0.05)):
            kr_rail_s = G.beams([(a[0], a[1], ez + dz)], [(b[0], b[1], 0.58 + dz)], w, h, 0.008)
            kzs.addt(kr_rail_s)
        path = np.array([[a[0], a[1], zk_kaki], [b[0], b[1], 0.58 + 0.74]])
        V, F = G.sweep(path, G.circle_profile(0.034, 14), mode="normal")
        kzs.add(V, F)
        kzs.addt(G.cbox((b[0] - 0.055, b[1] - 0.055, 0.54), (b[0] + 0.055, b[1] + 0.055, 0.58 + 0.80), 0.012))
        gbs2 = one(PT.giboshi(b[0], b[1], 0.58 + 0.80, 0.62, 24))
        emit("Giboshi_Finial_Stair_%s" % ("L" if sx < 0 else "R"), gbs2, "Seido_Bronze", C)
    emit("Hamayuka_LowDeck", hy, "Kiji_Old_Wood", C)
    emit("Kizahashi_Treads", kz, "Kiji_Old_Wood", C)
    emit("Kizahashi_Stringer_Rail", kzs, "Nuri_Shu_Vermilion", C)

    # ================================================================ 10 Saigu (ritual furnishings)
    C = "10_Saigu_Ritual"
    # saisenbako
    sy0 = p["saisen_y"]
    sb = G.MB(); sbs = G.MB(); sbg = G.MB()
    w2, d2, h2 = 0.70, 0.30, 0.62
    sb.addt(G.cbox((-w2, sy0 - d2, z_kidan), (w2, sy0 + d2, z_kidan + h2 - 0.06), 0.012))
    for x in np.arange(-w2 + 0.05, w2 - 0.04, 0.09):
        # sloped slats (V troughs)
        for sgn in (-1, 1):
            p0 = (x, sy0 + sgn * 0.0, z_kidan + h2 - 0.10)
            sbs.addt(G.beams([(x, sy0 - d2 + 0.04, z_kidan + h2 - 0.03)], [(x, sy0 + d2 - 0.04, z_kidan + h2 - 0.03)], 0.03, 0.06, 0.006))
            break
    for sx in (-1, 1):
        for sy in (-1, 1):
            sbg.addt(G.box((sx * w2 - 0.01 * (sx > 0) - 0.0, sy0 + sy * d2 - 0.012, z_kidan + h2 - 0.15) if sx < 0 else (sx * w2 - 0.10, sy0 + sy * d2 - 0.012, z_kidan + h2 - 0.15),
                           (sx * w2 + 0.10 if sx < 0 else sx * w2 + 0.01, sy0 + sy * d2 + 0.012, z_kidan + h2 - 0.04)) if False else
                     G.box((min(sx * w2, sx * (w2 - 0.12)) - 0.006, sy0 + sy * d2 - 0.008, z_kidan + h2 - 0.16),
                           (max(sx * w2, sx * (w2 - 0.12)) + 0.006, sy0 + sy * d2 + 0.008, z_kidan + h2 - 0.04)))
    sbg.addt(PT.rokuyo((0, sy0 - d2 - 0.012, z_kidan + h2 * 0.5), (0, -1, 0), r=0.09, seg=32))
    emit("Saisenbako_OfferingBox", sb, "Kiji_Old_Wood", C)
    emit("Saisenbako_Slats", sbs, "Kiji_Hinoki_Wood", C)
    emit("Saisenbako_Kanagu", sbg, "Kanagu_Gold", C)

    # suzu + suzuo (bell & rope)
    zs = kzr0 - 0.30
    su = G.MB()
    su.addt(G.lathe([(0.0, -0.13), (0.06, -0.125), (0.10, -0.10), (0.125, -0.05), (0.13, 0.0), (0.12, 0.055), (0.09, 0.10), (0.05, 0.125), (0.0, 0.13)], (0, yk + 0.02, zs), 32))
    su.addt(G.lathe([(0.0, 0.11), (0.02, 0.12), (0.02, 0.20), (0.0, 0.21)], (0, yk + 0.02, zs), 12))
    su.addt(G.beams([(0, yk + 0.02, zs + 0.2)], [(0, yk + 0.02, kzr0 + 0.01)], 0.015, 0.015))
    emit("Suzu_Bell", su, "Kanagu_Gold", C)
    slit = G.MB().addt(G.box((-0.11, yk + 0.02 - 0.135, zs - 0.075), (0.11, yk + 0.02 - 0.09, zs - 0.06)))
    emit("Suzu_Bell_Slit", slit, "Uchi_Dark", C, smooth=0)
    rope_c = np.stack([np.zeros(60) + 0.005 * np.sin(np.linspace(0, 6, 60)), np.full(60, yk + 0.02 - 0.01 * np.linspace(0, 1, 60)), np.linspace(zs - 0.12, p["suzuo_bottom"] + z_kidan + 0.25, 60)], 1)
    for k, mat in enumerate(("Nuno_Red", "Nuno_White", "Nuno_Purple")):
        strands = G.helix_strands(rope_c, 0.022, 0.022, n_strands=3, twist_pitch=0.30, seg=10)
        mb = G.MB().addt(strands[k])
        emit("Suzuo_BellRope_%d" % (k + 1), mb, mat, C)
    # tassel at the bottom
    ts = G.MB().addt(G.lathe([(0.0, 0.0), (0.05, 0.02), (0.06, 0.15), (0.03, 0.25), (0.0, 0.26)], (0, yk + 0.01, p["suzuo_bottom"] + z_kidan + 0.0), 16))
    emit("Suzuo_Fusa_Tassel", ts, "Nuno_Red", C)

    # shimenawa along the kohai front
    sn_y = yk - 0.02
    c0 = np.array([kx[0] + 0.10, sn_y, kzr0 - 0.02]); c1 = np.array([kx[1] - 0.10, sn_y, kzr0 - 0.02])
    cen = G.catenary(c0, c1, p["shimenawa_sag"], 120)
    tt = np.linspace(0, 1, len(cen))
    scl = 0.45 + 0.55 * np.sin(np.pi * tt) ** 0.7
    strands = G.helix_strands(cen, 0.062, 0.068, n_strands=3, twist_pitch=0.36, seg=14, scale=scl)
    sm = G.MB()
    for s_ in strands:
        sm.addt(s_)
    emit("Shimenawa_SacredRope", sm, "Asa_Straw", C)
    # shide (zigzag paper) + shimenoko tassels
    sd = G.MB(); sk_ = G.MB()
    for k, f in enumerate((0.12, 0.28, 0.44, 0.56, 0.72, 0.88)):
        i = int(f * (len(cen) - 1))
        top = cen[i] - np.array([0, 0, 0.05 * scl[i]])
        w_ = 0.065
        zz_ = top[2]
        pts = []
        for j in range(4):
            off = 0.035 if j % 2 else -0.035
            pts.append(((top[0] + off, zz_), (top[0] + off + w_, zz_), (top[0] + off + w_, zz_ - 0.12), (top[0] + off, zz_ - 0.12)))
            zz_ -= 0.10
        for q in pts:
            ol = np.array([(a - top[0], b - top[2]) for a, b in q])
            sd.addt(G.extrude_poly(ol, 0.003, (np.array([top[0], top[1] - 0.06, top[2]]), np.array([1.0, 0, 0]), np.array([0, 0, 1.0]))))
    for f in (0.3, 0.5, 0.7):
        i = int(f * (len(cen) - 1))
        top = cen[i]
        sk_.addt(G.lathe([(0.0, 0.0), (0.03, 0.02), (0.035, 0.12), (0.045, 0.24), (0.0, 0.25)], (top[0], top[1], top[2] - 0.30), 12, cap_bottom=True))
    emit("Shide_PaperStreamers", sd, "Shide_Paper", C, smooth=0)
    emit("Shimenoko_StrawTassels", sk_, "Asa_Straw", C)

    # hengaku (name plaque) on the main front, centre bay
    hgz0 = KH["pillar_top"] + 0.02
    hgz1 = nk1 + 0.04
    hg = G.MB(); hgf = G.MB()
    hy_ = -Y0 - 0.20
    hg.addt(G.cbox((-0.24, hy_ - 0.03, hgz0), (0.24, hy_ + 0.02, hgz1), 0.01))
    for (a, b) in (((-0.31, hgz1 - 0.06), (0.31, hgz1 + 0.05)), ((-0.31, hgz0 - 0.05), (0.31, hgz0 + 0.06)),
                   ((-0.31, hgz0 - 0.05), (-0.22, hgz1 + 0.05)), ((0.22, hgz0 - 0.05), (0.31, hgz1 + 0.05))):
        hgf.addt(G.cbox((a[0], hy_ - 0.06, a[1]), (b[0], hy_ + 0.03, b[1]), 0.012))
    emit("Hengaku_Plaque", hg, "Kuro_Urushi_Lacquer", C)
    emit("Hengaku_Frame", hgf, "Nuri_Shu_Vermilion", C)
    if os.path.exists(FONT):
        name = p.get("shrine_name", "八幡宮")
        n_ch = len(name)
        step = (hgz1 - hgz0 - 0.12) / n_ch
        font = bpy.data.fonts.load(FONT)
        objs = []
        for k, ch in enumerate(name):
            cu = bpy.data.curves.new("Hengaku_Char", "FONT")
            cu.body = ch
            cu.font = font
            cu.size = step * 0.95
            cu.extrude = 0.006
            cu.align_x = "CENTER"
            cu.align_y = "CENTER"
            ob = bpy.data.objects.new("tmp_char", cu)
            bpy.context.scene.collection.objects.link(ob)
            ob.location = (0, hy_ - 0.04, hgz1 - 0.06 - step * (k + 0.5))
            ob.rotation_euler = (math.pi / 2, 0, 0)
            objs.append(ob)
        bpy.context.view_layer.update()
        dg_ = bpy.context.evaluated_depsgraph_get()
        tm = G.MB()
        for ob in objs:
            ev = ob.evaluated_get(dg_)
            me = bpy.data.meshes.new_from_object(ev)
            mw = np.array(ob.matrix_world)
            V = np.array([v.co[:] for v in me.vertices])
            if len(V):
                V = V @ mw[:3, :3].T + mw[:3, 3]
                tm.add(V, [list(pp.vertices) for pp in me.polygons])
            bpy.data.meshes.remove(me)
            cu = ob.data
            bpy.data.objects.remove(ob)
            bpy.data.curves.remove(cu)
        emit("Hengaku_Moji_Letters", tm, "Kanagu_Gold", C, smooth=0)

    info["heights"] = dict(z_kidan=z_kidan, z_ptop=z_ptop, zr0=zr0, Z0=Z0, z_apex=float(z_apex), kt=kt, Zk0=float(Zk0))
    return info


# ==========================================================================

def fix_normals():
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()


def scene_stats():
    tris = 0; verts = 0; objs = 0
    mats = set()
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        me = ob.data
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        verts += len(me.vertices)
        objs += 1
        for m in me.materials:
            if m:
                mats.add(m.name)
    return tris, verts, objs, sorted(mats)


def bbox_all():
    mn = np.full(3, 1e9); mx = np.full(3, -1e9)
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not len(ob.data.vertices):
            continue
        V = np.empty(len(ob.data.vertices) * 3)
        ob.data.vertices.foreach_get("co", V)
        V = V.reshape(-1, 3)
        mn = np.minimum(mn, V.min(0)); mx = np.maximum(mx, V.max(0))
    return mn, mx


def find_gltf_transform():
    for c in (os.environ.get("GLTF_TRANSFORM"), shutil.which("gltf-transform")):
        if c and os.path.exists(c):
            return c
    return None


def export_glb(path, draco=False, image_format="AUTO"):
    kw = dict(filepath=path, export_format="GLB", export_yup=True, export_apply=True,
              export_image_format=image_format, export_texcoords=True, export_normals=True,
              export_materials="EXPORT", export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError:
        kw.pop("export_image_format")
        bpy.ops.export_scene.gltf(**kw)


def main():
    global M, ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="haiden/out")
    ap.add_argument("--params", default=os.path.join(HERE, "params.json"))
    ap.add_argument("--no-glb", action="store_true")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    with open(a.params, encoding="utf-8") as f:
        p = json.load(f)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    ROOT = bpy.data.collections.new("Haiden")
    sc.collection.children.link(ROOT)
    M = Mats()

    info = build(p)
    fix_normals()
    tris, verts, objs, mats = scene_stats()
    mn, mx = bbox_all()
    print("built: %d tris, %d verts, %d objects in %.1fs" % (tris, verts, objs, time.time() - t0))

    blend = os.path.join(out, "haiden.blend")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)

    stats = {
        "name": "Haiden (拝殿) - 入母屋造・平入・桁行3間×梁間2間・1間向拝(軒唐破風)・銅板葺",
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "triangles": tris, "vertices": verts, "objects": objs,
        "materials": len(mats), "material_names": mats,
        "dimensions_m": {"width_x": round(float(mx[0] - mn[0]), 3), "depth_y": round(float(mx[1] - mn[1]), 3),
                         "height_z": round(float(mx[2] - mn[2]), 3)},
        "plan": {"keta_bays_m": p["bays_x"], "hari_bays_m": p["bays_y"], "kohai_depth_m": p["kohai"]["depth"],
                 "noki_de_m": p["noki_de"]},
        "heights_m": {k: round(float(v), 3) for k, v in info["heights"].items()},
        "renders": [],
    }
    if not a.no_glb:
        tex_dir = os.path.join(out, "textures")
        tiles = bake_tiles(BAKE, tex_dir, size=512)
        for ob in bpy.data.objects:
            if ob.type == "MESH":
                ob.data.materials[0] = glb_material(ob.data.materials[0], tiles)
        full = os.path.join(out, "haiden.glb")
        export_glb(full, image_format="AUTO")
        web = os.path.join(out, "haiden_web.glb")
        tmp = os.path.join(out, "_web_tmp.glb")
        export_glb(tmp, image_format="JPEG")
        gt = find_gltf_transform()
        compressed = False
        if gt:
            r = subprocess.run([gt, "draco", tmp, web, "--method", "edgebreaker"], capture_output=True, text=True)
            print(r.stdout[-400:], r.stderr[-400:])
            compressed = r.returncode == 0
        if not compressed:
            shutil.copy(tmp, web)
        os.remove(tmp)
        stats["glb_bytes"] = os.path.getsize(web)
        stats["glb_full_bytes"] = os.path.getsize(full)
        stats["web_draco"] = compressed
    old = os.path.join(out, "stats.json")
    if os.path.exists(old):
        try:
            prev = json.load(open(old, encoding="utf-8"))
            stats["renders"] = prev.get("renders", [])
        except Exception:
            pass
    with open(old, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
