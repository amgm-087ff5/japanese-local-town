"""拝殿A-1 ver2: 銅板葺(檜皮葺写しの銅板一文字葺) roof (params "doban_v2").

Research: haiden/docs/research.md §7, modelling notes: haiden/docs/knowledge.md.

* 大屋根 (lower hipped part, d = 0 .. irimoya_d) is ONE closed ring grid around
  the four slopes, so smooth normals run across the hips. No 隅棟: the hip is
  rounded with a smooth-min of the two slope depths (width grows from 0 at the
  sharp eave corner) and keeps the corner 反り (RoofFn.S).
* 入母屋の妻 (upper gable part): the verge rolls down to the 破風 in a convex
  むくり = 箕甲 (minokō); at the gable foot the roll deepens so the verge meets
  the lower roof (箕甲の裾). The 破風板 ends where it would cut into the lower roof.
* 軒先 (eave): 軒付 = 3 copper-clad layers (唐破風 4) with crisp chamfered
  edges, each layer projecting a little more than the one below, a 水切り plate
  with a drip on top. Eave = sharp stack, verge = rolled 箕甲 + thin 登り軒付.
* 一文字葺: the surface steps by `hem` at every row (葺足 `ashi` along the slope);
  vertical joints (staggered, 千鳥) + patina are in a numpy-generated texture
  (base / normal / metallicRoughness) whose UV rows line up with the steps.
"""
import math
import os

import bpy
import numpy as np

from . import geom as G

DEF = dict(
    th=0.05,                     # slab thickness (野地+銅板) of the copper roof
    ashi=0.18,                   # 一文字葺 葺足 (row height along the slope)
    plate_L=0.60,                # plate length (vertical joints, 千鳥)
    hem=0.005, hem_eps=0.003,    # step height at each row / row pair spacing (along the slope)
    col=0.06, row=0.07,          # base grid spacing (m)
    tile=1.8,                    # UV: 1 unit = 1.8 m (10 rows x 3 plates per texture tile)
    hip_k=0.70, hip_kd=1.0,      # rounded hip: smooth-min width, distance from the eave where it is reached
    mino_h=0.12, mino_w=0.40, mino_p=2.2,   # 箕甲: roll depth at the verge, width, exponent
    mino_foot=0.55, mino_clear=0.025, overlap=0.03,
    nobori_t=0.045, nobori_n=2,  # 登り軒付 (verge copper edge) height / layers
    nk_layers=3, nk_proj=0.014, nk_lean=0.006, nk_ch=0.003, nk_depth=0.30,
    mz_t=0.007, mz_out=0.032, mz_drip=0.014,   # 水切り plate
    kara_layers=4,
    hafu=dict(t=0.055, d1=0.024, p1=0.030, d2=0.032, p2a=0.026, p2b=0.014, d3=0.012, p3=0.008,
              mayu_h=0.040, mayu_step=0.008, grooves=[0.022, 0.044], groove_w=0.011, groove_d=0.007,
              kuri_L=0.22, kuri_H=0.42, plate_L=0.28, ogami_L=0.26, mid_L=0.20, rokuyo_r=0.036),
    hafu_h=0.24, kara_h=0.27, kara_t=0.065, side_h=0.22, side_t=0.055,
    k_mino_h=0.05, k_mino_w=0.22, k_nobori_t=0.04,
    tex_size=1024,
)

MAT_ROOF = "Doban_Ichimonji_Copper"
MAT_TRIM = "Doban_Rokusho_Trim"
TILES = {}


def cfg_of(p):
    c = dict(DEF)
    over = dict(p.get("doban_v2") or {})
    if "hafu" in over:
        h = dict(DEF["hafu"]); h.update(over.pop("hafu")); c["hafu"] = h
    c.update(over)
    return c


def sstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def smin(a, b, k):
    a = np.asarray(a, float); b = np.asarray(b, float)
    k = np.maximum(np.asarray(k, float), 1e-9)
    h = np.maximum(k - np.abs(a - b), 0) / k
    return np.minimum(a, b) - h * h * k * 0.25


class Arc:
    """Arc length along a 1D height profile (rows of 一文字葺, UV v)."""

    def __init__(self, d, slope):
        d = np.asarray(d, float); s = np.asarray(slope, float)
        self.d = d
        self.L = np.concatenate([[0.0], np.cumsum(np.sqrt(1 + ((s[1:] + s[:-1]) / 2) ** 2) * np.diff(d))])

    def L_of(self, d):
        return np.interp(d, self.d, self.L)

    def d_of(self, L):
        return np.interp(L, self.L, self.d)


def lip(c, L):
    return c["hem"] * (1.0 - np.mod(L, c["ashi"]) / c["ashi"])


def rows_with_steps(c, arc, d0, d1, extra=(), base=None):
    base = base or c["row"]
    rows = list(np.linspace(d0, d1, max(2, int(math.ceil((d1 - d0) / base)) + 1)))
    L0, L1 = float(arc.L_of(d0)), float(arc.L_of(d1))
    for k in range(int(math.floor(L0 / c["ashi"])), int(math.ceil(L1 / c["ashi"])) + 1):
        for Lv in (k * c["ashi"], k * c["ashi"] - c["hem_eps"]):
            dv = float(arc.d_of(Lv))
            if d0 + 1e-5 < dv < d1 - 1e-5:
                rows.append(dv)
    rows += [e for e in extra if d0 < e < d1]
    return np.unique(np.round(rows, 6))


def refine(n_base, Ls, offs, lo=True, hi=True):
    """t in [0,1], uniform + refined near the ends (offsets in metres along a side of length Ls)."""
    t = list(np.linspace(0, 1, max(3, n_base) + 1))
    for o in offs:
        if o < Ls * 0.45:
            if lo:
                t.append(o / Ls)
            if hi:
                t.append(1 - o / Ls)
    return np.unique(np.round(t, 7))


HIP_OFF = [0.004, 0.012, 0.024, 0.04, 0.06, 0.085, 0.115, 0.15, 0.2, 0.26, 0.34, 0.44, 0.56, 0.7, 0.86, 1.05]
VERGE_OFF = [0.0, 0.006, 0.015, 0.027, 0.042, 0.06, 0.08, 0.105, 0.135, 0.17, 0.21, 0.26, 0.32, 0.39, 0.47, 0.56]


# ----------------------------------------------------------------- mesh helpers

def slab(nr, nc, top, th, uv_of, closed_c=False, keep=None):
    """Closed slab from a top grid (nr*nc,3): bottom = top - th (vertical), walls on the boundary.
    uv_of(Fidx (m,4) into top, face ids) -> (m,4,2) per-loop UV."""
    n = nr * nc
    thv = np.broadcast_to(np.asarray(th, float), (nr, nc)).ravel()
    bot = top.copy(); bot[:, 2] -= thv
    F = G.grid_faces(nr, nc, closed_c=closed_c)
    fid = np.arange(len(F))
    if keep is not None:
        k = np.asarray(keep).ravel()
        F = F[k]; fid = fid[k]
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 3]], F[:, [3, 0]]])
    Ef = np.concatenate([fid] * 4)
    _, inv, cnt = np.unique(np.sort(E, 1), axis=0, return_inverse=True, return_counts=True)
    bm = cnt[np.asarray(inv).reshape(-1)] == 1
    b = E[bm]; bf = Ef[bm]
    Fw = np.stack([b[:, 1], b[:, 0], b[:, 0] + n, b[:, 1] + n], 1)
    Fb = F[:, ::-1] + n
    UVt = uv_of(F, fid)
    UVb = uv_of(Fb - n, fid)
    UVw = uv_of(Fw % n, bf)
    UVw[:, 2:, 1] += 0.004
    return np.vstack([top, bot]), np.vstack([F, Fb, Fw]), np.concatenate([UVt, UVb, UVw])


class Acc:
    """Accumulate quad meshes with per-loop UV."""

    def __init__(self):
        self.V, self.F, self.UV, self.n = [], [], [], 0

    def add(self, V, F, UV):
        self.V.append(V); self.F.append(F + self.n); self.UV.append(UV); self.n += len(V)
        return self

    def empty(self):
        return self.n == 0

    def to_mesh(self, name):
        V = np.concatenate(self.V); F = np.concatenate(self.F); UV = np.concatenate(self.UV)
        me = bpy.data.meshes.new(name)
        me.vertices.add(len(V))
        me.vertices.foreach_set("co", V.astype(np.float32).ravel())
        lv = F.ravel().astype(np.int32)
        me.loops.add(len(lv))
        me.loops.foreach_set("vertex_index", lv)
        me.polygons.add(len(F))
        me.polygons.foreach_set("loop_start", (np.arange(len(F)) * 4).astype(np.int32))
        me.polygons.foreach_set("loop_total", np.full(len(F), 4, np.int32))
        me.update(calc_edges=True)
        uv = me.uv_layers.new(name="UVMap")
        uv.data.foreach_set("uv", UV.reshape(-1, 2).astype(np.float32).ravel())
        return me


def sweep_scaled(P, prof, scale_v=None, side=None):
    """Vertical sweep (profile u = horizontal side, v = world z) with an optional per-point v scale."""
    S = None
    if scale_v is not None:
        S = np.stack([np.ones(len(P)), np.asarray(scale_v, float)], 1)
    V, F = G.sweep(P, prof, mode="vertical", scale=S)
    return V, F


# ----------------------------------------------------------------- profiles

def nokitsuke_profile(c, H, layers, depth=None, u0=-0.005, mizukiri=True):
    """軒付 section (u outward, v up from the 裏甲 top), CCW. H = total height to the roof surface."""
    depth = depth or c["nk_depth"]
    ch = c["nk_ch"]
    top = H - 0.003
    hl = (top - (c["mz_t"] if mizukiri else 0.0)) / layers
    P = [(-depth, 0.0)]
    for i in range(layers):
        ui = u0 + i * c["nk_proj"]
        v0, v1 = i * hl, (i + 1) * hl
        P += [(ui - ch, v0), (ui, v0 + ch), (ui + c["nk_lean"], v1 - ch), (ui + c["nk_lean"] - ch, v1)]
    if mizukiri:
        ut = u0 + (layers - 1) * c["nk_proj"] + c["nk_lean"]
        um = ut + c["mz_out"]
        vb = layers * hl
        P += [(um - 0.004, vb), (um - 0.004, vb - c["mz_drip"]), (um, vb - c["mz_drip"]), (um, top), (-depth, top)]
    else:
        P += [(-depth, top)]
    return G.ccw(np.array(P))


def nobori_profile(c, H, n, u_face, depth=0.25):
    """登り軒付 section (normalised height H) on top of the 破風板."""
    ch = min(c["nk_ch"], H / n * 0.3)
    hl = H / n
    P = [(-depth, 0.0)]
    for i in range(n):
        ui = u_face + i * 0.008
        P += [(ui - ch, i * hl), (ui, i * hl + ch), (ui + 0.003, (i + 1) * hl - ch), (ui + 0.003 - ch, (i + 1) * hl)]
    P += [(-depth, H)]
    return G.ccw(np.array(P))


# ----------------------------------------------------------------- main roof

class Roof:
    def __init__(self, ctx, c):
        self.x = ctx
        self.c = c
        RF = ctx.RF
        self.RF = RF
        self.arc = Arc(RF.dd, RF.sv)
        self.Xe, self.Ye, self.Z0, self.dg = ctx.Xe, ctx.Ye, ctx.Z0, ctx.dg
        self.xv = ctx.Xg + ctx.ho          # verge line |x|
        self.Wk = ctx.Wk
        self.d_j = ctx.d_j
        self.lift = 0.003
        self.G_foot = 0.0
        self.G_foot = self._foot_gap()

    # -- heights
    def hip_k(self, d_row):
        c = self.c
        return c["hip_k"] * sstep(0.0, c["hip_kd"], d_row) * (1 - sstep(self.dg - 0.45, self.dg, d_row))

    def ring_z(self, x, y, d_row=None, with_lip=True):
        x = np.asarray(x, float); y = np.asarray(y, float)
        ax = self.Xe - np.abs(x); ay = self.Ye - np.abs(y)
        if d_row is None:
            d_row = np.minimum(ax, ay)
        dd = smin(ax, ay, self.hip_k(d_row))
        z = self.Z0 + self.RF.F(dd) + self.RF.S(x, y)
        if with_lip:
            z = z + lip(self.c, self.arc.L_of(d_row))
        return z

    def Mh(self, d):
        c = self.c
        return c["mino_h"] + self.G_foot * (1 - np.clip((np.asarray(d, float) - self.dg) / c["mino_foot"], 0, 1)) ** 2

    def gable_z(self, x, d, sy):
        c = self.c
        x = np.asarray(x, float); d = np.asarray(d, float)
        y = sy * (self.Ye - d)
        e = self.xv - np.abs(x)
        roll = self.Mh(d) * np.clip(1 - e / c["mino_w"], 0, 1) ** c["mino_p"]
        return self.Z0 + self.RF.F(d) + self.RF.S(x, y) + lip(c, self.arc.L_of(d)) + self.lift - roll

    def VT(self, d):
        """verge top (top of the 登り軒付) at gable row d."""
        return self.gable_z(np.full_like(np.asarray(d, float), self.xv), d, 1)

    def _foot_gap(self):
        c = self.c
        dg = self.dg
        z_low = float(self.ring_z(self.xv, self.Ye - dg))
        top = float(self.Z0 + self.RF.F(dg) + self.RF.S(self.xv, self.Ye - dg) + lip(c, self.arc.L_of(dg)) + self.lift)
        return max(0.0, top - c["mino_h"] - (z_low + c["mino_clear"]))

    def hafu_end(self, h, hcfg):
        """largest a (= |y|) along the gable verge where the 破風尻 still clears the lower roof."""
        c = self.c
        a = np.linspace(0.2, self.Ye - self.dg + 0.02, 400)
        d = self.Ye - a
        top = self.VT(d) - c["nobori_t"]
        steps = hcfg["d1"] + hcfg["d2"] + hcfg["d3"]
        bottom_end = top - (h - hcfg["kuri_H"] * (h - steps))
        z_low = self.ring_z(np.full_like(a, self.xv - 0.02), a)
        ok = bottom_end >= z_low + 0.006
        if not ok.any():
            return float(a[0])
        return float(a[np.where(ok)[0].max()])

    # -- meshes
    def ring_mesh(self, acc):
        c = self.c
        Xe, Ye, Wk = self.Xe, self.Ye, self.Wk
        rows = rows_with_steps(c, self.arc, 0.0, self.dg, extra=[self.d_j])
        nr = len(rows)
        cols = []    # (side, seg, t)
        # front: three segments split at the kohai (|x| = Wk)
        LA = Xe - Wk
        tA = refine(int(math.ceil(LA / c["col"])), LA, HIP_OFF, lo=True, hi=False)
        tB = np.linspace(0, 1, int(math.ceil(2 * Wk / c["col"])) + 1)
        cols += [(0, 0, t) for t in tA[:-1]] + [(0, 1, t) for t in tB[:-1]] + [(0, 2, t) for t in (1 - tA[::-1])[:-1]]
        for side, Ls in ((1, 2 * Ye), (2, 2 * Xe), (3, 2 * Ye)):
            ts = refine(int(math.ceil(Ls / c["col"])), Ls, HIP_OFF)
            cols += [(side, 0, t) for t in ts[:-1]]
        nc = len(cols)
        sideA = np.array([s for s, _, _ in cols]); segA = np.array([g for _, g, _ in cols]); tA_ = np.array([t for _, _, t in cols])
        X = np.zeros((nr, nc)); Y = np.zeros((nr, nc)); Sc = np.zeros((nr, nc))
        for i, d in enumerate(rows):
            Ax, Ay = Xe - d, Ye - d
            s = np.zeros(nc)
            f = sideA == 0
            s = np.where(f & (segA == 0), -Ax + (Ax - Wk) * tA_, s)
            s = np.where(f & (segA == 1), -Wk + 2 * Wk * tA_, s)
            s = np.where(f & (segA == 2), Wk + (Ax - Wk) * tA_, s)
            s = np.where(sideA == 1, -Ay + 2 * Ay * tA_, s)
            s = np.where(sideA == 2, -Ax + 2 * Ax * tA_, s)
            s = np.where(sideA == 3, -Ay + 2 * Ay * tA_, s)
            X[i] = np.select([sideA == 0, sideA == 1, sideA == 2, sideA == 3], [s, np.full(nc, Ax), -s, np.full(nc, -Ax)])
            Y[i] = np.select([sideA == 0, sideA == 1, sideA == 2, sideA == 3], [np.full(nc, -Ay), s, np.full(nc, Ay), -s])
            Sc[i] = s
        D = np.repeat(rows[:, None], nc, 1)
        Z = self.ring_z(X, Y, D)
        top = np.stack([X, Y, Z], -1).reshape(-1, 3)
        # kohai hole: front middle segment below d_j
        rr = np.arange(nr - 1)[:, None]; cc = np.arange(nc)[None, :]
        hole = (sideA[cc] == 0) & (segA[cc] == 1) & (rows[rr + 1] <= self.d_j + 1e-7)
        keep = ~hole
        fside = np.tile(sideA, nr - 1)
        Lr = self.arc.L_of(rows)
        Lv = np.repeat(Lr[:, None], nc, 1).ravel()
        Xf, Yf = X.ravel(), Y.ravel()
        tile = c["tile"]

        def uv_of(Fi, fid):
            sd = fside[fid][:, None]
            u = np.select([sd == 0, sd == 1, sd == 2, sd == 3], [Xf[Fi], Yf[Fi], -Xf[Fi], -Yf[Fi]])
            return np.stack([u / tile, Lv[Fi] / tile], -1)
        V, F, UV = slab(nr, nc, top, c["th"], uv_of, closed_c=True, keep=keep)
        acc.add(V, F, UV)
        self.ring_rows = rows
        return nr * nc

    def gable_mesh(self, acc):
        c = self.c
        xv = self.xv
        d0 = self.dg - c["overlap"]
        rows = rows_with_steps(c, self.arc, d0, self.Ye, extra=[self.dg])
        half = refine(int(math.ceil(xv / c["col"])), xv, VERGE_OFF, lo=True, hi=False)
        xs = np.unique(np.concatenate([-xv + xv * half, xv - xv * half]))
        nr, nc = len(rows), len(xs)
        tile = c["tile"]
        for sy in (-1, 1):
            X = np.repeat(xs[None, :], nr, 0)
            D = np.repeat(rows[:, None], nc, 1)
            Y = sy * (self.Ye - D)
            Z = self.gable_z(X, D, sy)
            e = xv - np.abs(X)
            th = c["th"] * (0.4 + 0.6 * sstep(0.0, 0.06, e))
            top = np.stack([X, Y, Z], -1).reshape(-1, 3)
            Lv = self.arc.L_of(D).ravel(); Xf = X.ravel()

            def uv_of(Fi, fid, _sy=sy):
                return np.stack([-_sy * Xf[Fi] / tile, Lv[Fi] / tile], -1)
            V, F, UV = slab(nr, nc, top, th, uv_of)
            acc.add(V, F, UV)

    # -- eave stacks / verge edges (trim, MB meshes)
    def nokitsuke(self, mb, ura_top):
        """軒付 along the eave of the lower roof (front split at the kohai)."""
        c = self.c
        Xe, Ye, Wk = self.Xe, self.Ye, self.Wk
        H = self.Z0 - ura_top
        prof = nokitsuke_profile(c, H, c["nk_layers"])
        x0 = Wk + 0.11

        def seg(a, b, n):
            return np.linspace(a, b, n)
        pts = []
        pts += [np.stack([seg(x0, Xe, 60), np.full(60, -Ye)], 1)]
        pts += [np.stack([np.full(90, Xe), seg(-Ye, Ye, 90)], 1)[1:]]
        pts += [np.stack([seg(Xe, -Xe, 140), np.full(140, Ye)], 1)[1:]]
        pts += [np.stack([np.full(90, -Xe), seg(Ye, -Ye, 90)], 1)[1:]]
        pts += [np.stack([seg(-Xe, -x0, 60), np.full(60, -Ye)], 1)[1:]]
        xy = np.concatenate(pts)
        z = ura_top + self.RF.S(xy[:, 0], xy[:, 1])
        P = np.stack([xy[:, 0], xy[:, 1], z], 1)
        mb.addt(G.sweep(P, prof, mode="vertical"))

    def nobori(self, mb, a_end):
        c = self.c
        u_face = c["hafu"]["t"] - 0.01 + c["hafu"]["p1"] + 0.004
        prof = nobori_profile(c, c["nobori_t"], c["nobori_n"], u_face)
        for sx in (-1, 1):
            ys = np.linspace(-a_end, a_end, 161)
            ys = np.unique(np.concatenate([ys, [0.0]]))
            if sx < 0:
                ys = ys[::-1]
            d = self.Ye - np.abs(ys)
            z = self.VT(d) - c["nobori_t"]
            P = np.stack([np.full_like(ys, sx * self.xv), ys, z], 1)
            mb.addt(G.sweep(P, prof, mode="vertical"))


# ----------------------------------------------------------------- kohai roof

class Kohai:
    def __init__(self, ctx, c, roof):
        self.x = ctx; self.c = c; self.roof = roof
        self.Wk = ctx.Wk
        dks = np.linspace(0, ctx.dk_j + 0.3, 3000)
        zz = self.zbase(np.zeros_like(dks), dks)
        self.arc = Arc(dks, np.gradient(zz, dks))

    def zbase(self, x, dk):
        x = np.asarray(x, float); dk = np.asarray(dk, float)
        X = self.x
        dkj = X.dk_j
        t = np.clip(dk, 0, dkj) / dkj
        z1 = X.zj_main(x)
        zh = (2 * t ** 3 - 3 * t ** 2 + 1) * X.Zk0 + (t ** 3 - 2 * t ** 2 + t) * dkj * X.m0 + \
             (-2 * t ** 3 + 3 * t ** 2) * z1 + (t ** 3 - t ** 2) * dkj * X.m1
        ext = np.maximum(dk - dkj, 0)
        return zh + ext * X.m1 - 0.004 * (ext > 0)

    def z(self, x, dk, with_roll=True):
        X = self.x; c = self.c
        x = np.asarray(x, float); dk = np.asarray(dk, float)
        z = self.zbase(x, dk) + X.bump(x) * X.kfade(dk) + lip(c, self.arc.L_of(dk))
        if with_roll:
            e = self.Wk - np.abs(x)
            z = z - c["k_mino_h"] * np.clip(1 - e / c["k_mino_w"], 0, 1) ** c["mino_p"] * sstep(0.05, 0.45, dk)
        return z

    def VTk(self, dk):
        return self.z(np.full_like(np.asarray(dk, float), self.Wk), dk)

    def Hn(self, dk, H_front):
        c = self.c
        return c["k_nobori_t"] + (H_front - c["k_nobori_t"]) * (1 - sstep(0.0, 0.35, dk))

    def mesh(self, acc):
        X = self.x; c = self.c
        Wk = self.Wk
        rows = rows_with_steps(c, self.arc, 0.0, X.dk_j + 0.06, extra=[X.dk_j], base=0.06)
        xs = list(np.linspace(-Wk, Wk, int(math.ceil(2 * Wk / 0.04)) + 1))
        for o in VERGE_OFF[:12]:
            xs += [-Wk + o, Wk - o]
        xs += [-X.kh_w, X.kh_w]
        xs = np.unique(np.round(xs, 6))
        nr, nc = len(rows), len(xs)
        XX = np.repeat(xs[None, :], nr, 0)
        DK = np.repeat(rows[:, None], nc, 1)
        YY = X.yke + DK
        ZZ = self.z(XX, DK)
        e = Wk - np.abs(XX)
        th = c["th"] * (0.4 + 0.6 * sstep(0.0, 0.05, e))
        top = np.stack([XX, YY, ZZ], -1).reshape(-1, 3)
        Lv = self.arc.L_of(DK).ravel(); Xf = XX.ravel(); tile = c["tile"]

        def uv_of(Fi, fid):
            return np.stack([Xf[Fi] / tile, Lv[Fi] / tile], -1)
        V, F, UV = slab(nr, nc, top, th, uv_of)
        acc.add(V, F, UV)

    def front_nokitsuke(self, mb):
        """唐破風の軒付: 4 layers following the 起り・反り (vertical sweep so its top meets the roof edge)."""
        X = self.x; c = self.c
        H = X.Zk0 - X.EK_ura_top
        prof = nokitsuke_profile(c, H, c["kara_layers"], depth=0.28)
        xe = self.Wk + 0.11
        xs = np.unique(np.concatenate([np.linspace(-xe, xe, 241), [-X.kh_w, X.kh_w]]))
        z = X.EK_ura_top + X.bump(xs)
        P = np.stack([xs, np.full_like(xs, X.yke), z], 1)
        mb.addt(G.sweep(P, prof, mode="vertical"))
        return H

    def side_nobori(self, mb, H_front, y_end):
        X = self.x; c = self.c
        u_face = c["side_t"] + 0.005 + c["hafu"]["p1"] + 0.004
        prof = nobori_profile(c, 1.0, c["nobori_n"], u_face, depth=0.22)
        for sx in (-1, 1):
            ys = np.linspace(X.yke + 0.02, y_end, 90)
            if sx < 0:
                ys = ys[::-1]
            dk = ys - X.yke
            Hn = self.Hn(dk, H_front)
            z = self.VTk(dk) - Hn
            P = np.stack([np.full_like(ys, sx * self.Wk), ys, z], 1)
            mb.addt(sweep_scaled(P, prof, scale_v=Hn))

    def toriai(self, mb, roof, H_front):
        """取合い: copper flashing closing the step between the main roof edge (hole boundary) and the kohai verge."""
        X = self.x
        for sx in (-1, 1):
            ys = np.linspace(-roof.Ye, X.y_j, 40)
            d = roof.Ye - np.abs(ys)
            ztop = roof.ring_z(np.full_like(ys, sx * self.Wk), ys, d) - 0.004
            dk = ys - X.yke
            zbot = self.VTk(dk) - self.Hn(dk, H_front) - 0.01
            ok = ztop > zbot + 0.01
            if ok.sum() < 2:
                continue
            ys, ztop, zbot = ys[ok], ztop[ok], zbot[ok]
            ol = np.concatenate([np.stack([ys, zbot], 1), np.stack([ys[::-1], ztop[::-1]], 1)])
            mb.addt(G.extrude_poly(ol, 0.008, (np.array([sx * (self.Wk - 0.008), 0, 0]),
                                               np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))))


# ----------------------------------------------------------------- textures / materials (numpy, periodic)

def _pnoise(N, sig_u, sig_v, rng):
    w = rng.standard_normal((N, N))
    ky = np.fft.fftfreq(N)[:, None]; kx = np.fft.fftfreq(N)[None, :]
    g = np.exp(-2 * np.pi ** 2 * ((kx * sig_u) ** 2 + (ky * sig_v) ** 2))
    r = np.real(np.fft.ifft2(np.fft.fft2(w) * g))
    return (r - r.mean()) / (r.std() + 1e-12)


def _fbm(N, rng, sigs, amps, aniso=1.0):
    out = np.zeros((N, N))
    for s, a in zip(sigs, amps):
        out += a * _pnoise(N, s, s * aniso, rng)
    return out


def _lerp(a, b, t):
    t = np.asarray(t)[..., None]
    return np.asarray(a) * (1 - t) + np.asarray(b) * t


PALE = np.array([0.20, 0.40, 0.31])      # 緑青 pale (linear)
TEAL = np.array([0.065, 0.20, 0.145])
DARK = np.array([0.035, 0.07, 0.05])
BROWN = np.array([0.10, 0.045, 0.022])


def _patina(N, rng, streak_len=70.0):
    cov = _fbm(N, rng, [60, 18, 5], [0.6, 0.3, 0.15])
    cov = sstep(-0.9, 0.7, cov)
    col = _lerp(TEAL, PALE, cov)
    brown = sstep(1.5, 2.3, _fbm(N, rng, [14, 4], [0.8, 0.3]))
    col = _lerp(col, BROWN, brown * 0.85)
    streak = _pnoise(N, 2.5, streak_len, rng)
    col = col * (1 + 0.10 * np.tanh(streak))[..., None]
    dark = sstep(0.8, 2.0, _pnoise(N, 30, 90, rng))
    col = _lerp(col, DARK, dark * 0.35)
    return col, cov, brown, streak


def _save(name, arr, colorspace, out_dir):
    N = arr.shape[0]
    img = bpy.data.images.new(name, N, N, alpha=False)
    img.colorspace_settings.name = colorspace
    px = np.ones((N, N, 4), np.float32)
    px[..., :3] = np.clip(arr, 0, 1)
    img.pixels.foreach_set(px.ravel())
    p = os.path.join(out_dir, name + ".png")
    img.filepath_raw = p
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return p


def _normal_from_height(h, metres_per_px, strength=1.0):
    dhdu = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * metres_per_px)
    dhdv = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * metres_per_px)
    n = np.stack([-dhdu * strength, -dhdv * strength, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def make_textures(out_dir, size=1024, tile=1.8, ashi=0.18, plate_L=0.60):
    """一文字葺 tile (rows/plates aligned with the geometry) + plain patina trim tile."""
    os.makedirs(out_dir, exist_ok=True)
    N = size
    rng = np.random.default_rng(20261025)
    R = int(round(tile / ashi)); Pn = int(round(tile / plate_L))
    v = (np.arange(N) + 0.5) / N
    u = (np.arange(N) + 0.5) / N
    U, Vv = np.meshgrid(u, v)            # [row=v, col=u]; row 0 = v=0 (Blender pixel order)
    row = np.floor(Vv * R).astype(int)
    fr = Vv * R - row                     # 0 at the lower edge (hem) of a plate row
    q = U * Pn + 0.5 * (row % 2)
    colp = np.floor(q).astype(int) % Pn
    fc = q - np.floor(q)
    pid = row * Pn + colp
    tone = rng.standard_normal(R * Pn)[pid]
    col, cov, brown, streak = _patina(N, rng)
    col = col * (1 + 0.06 * tone)[..., None]
    mpp = tile / N
    w_hem = 0.006 / (ashi)                # hem width as a fraction of the row
    hem = sstep(w_hem, 0.0, fr)
    under = sstep(1 - 0.05, 1.0, fr)     # dirt line just under the next hem
    dj = np.minimum(fc, 1 - fc) * plate_L / mpp   # distance (px) to a vertical joint
    joint = np.exp(-(dj / 1.2) ** 2)
    col = col * (1 + 0.16 * hem)[..., None]
    col = col * (1 - 0.42 * under)[..., None]
    col = col * (1 - 0.35 * joint)[..., None]
    h = 0.0012 * hem - 0.0006 * under + 0.0008 * joint + 0.00012 * _pnoise(N, 1.2, 1.2, rng)
    nrm = _normal_from_height(h, mpp)
    rough = 0.70 + 0.06 * (1 - cov) - 0.22 * brown + 0.03 * np.tanh(streak)
    metal = 0.35 * brown
    mr = np.stack([np.ones_like(rough), np.clip(rough, 0.05, 1), np.clip(metal, 0, 1)], -1)
    out = {}
    out[MAT_ROOF] = {"base": _save("T_%s_base" % MAT_ROOF, col, "sRGB", out_dir),
                     "normal": _save("T_%s_normal" % MAT_ROOF, nrm, "Non-Color", out_dir),
                     "mr": _save("T_%s_mr" % MAT_ROOF, mr, "Non-Color", out_dir)}
    # trim (軒付・箱棟・鬼板・水切り): patina, vertical rain streaks along v
    col2, cov2, brown2, streak2 = _patina(N, rng, streak_len=110.0)
    h2 = 0.00015 * _pnoise(N, 1.5, 1.5, rng) + 0.0002 * np.tanh(streak2) * 0.3
    nrm2 = _normal_from_height(h2, 2.0 / N)
    rough2 = 0.68 + 0.06 * (1 - cov2) - 0.2 * brown2
    mr2 = np.stack([np.ones_like(rough2), np.clip(rough2, 0.05, 1), np.clip(0.35 * brown2, 0, 1)], -1)
    out[MAT_TRIM] = {"base": _save("T_%s_base" % MAT_TRIM, col2, "sRGB", out_dir),
                     "normal": _save("T_%s_normal" % MAT_TRIM, nrm2, "Non-Color", out_dir),
                     "mr": _save("T_%s_mr" % MAT_TRIM, mr2, "Non-Color", out_dir)}
    return out


def _tex_material(name, paths, col, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = False
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "UVMap"

    def tex(p, cs):
        img = bpy.data.images.load(p, check_existing=True)
        img.colorspace_settings.name = cs
        img.pack()
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img
        nt.links.new(uvn.outputs[0], t.inputs[0])
        return t
    tb = tex(paths["base"], "sRGB")
    nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
    tm = tex(paths["mr"], "Non-Color")
    sp = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(tm.outputs["Color"], sp.inputs[0])
    nt.links.new(sp.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sp.outputs["Blue"], bsdf.inputs["Metallic"])
    tn = tex(paths["normal"], "Non-Color")
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    m["glb_color"] = list(col); m["glb_rough"] = rough; m["glb_metal"] = 0.0; m["v2"] = 1
    m.diffuse_color = (*col, 1)
    return m


def make_materials(M, out_dir, size=1024, c=None):
    """Create the copper materials (image textures, identical in Cycles and in the GLB) and register them in M."""
    c = c or DEF
    tiles = make_textures(out_dir, size=size, tile=c["tile"], ashi=c["ashi"], plate_L=c["plate_L"])
    M.cache[MAT_ROOF] = _tex_material(MAT_ROOF, tiles[MAT_ROOF], (0.12, 0.28, 0.21), 0.7)
    M.cache[MAT_TRIM] = _tex_material(MAT_TRIM, tiles[MAT_TRIM], (0.12, 0.28, 0.21), 0.68)
    TILES.clear(); TILES.update(tiles)
    return tiles
