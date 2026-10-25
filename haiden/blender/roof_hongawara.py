"""拝殿A-2: 本瓦葺 roof assembly (main irimoya roof, kohai with 軒唐破風, 千鳥破風).

Called from build_haiden.build() when params roof.type == "hongawara", after
the roof base slabs (野地/葺土) have been emitted. `c` is a namespace holding
build() locals (RF, Xe, Ye, Xg, ho, dg, Wk, yke, Zk0, bump, kfade, ...).

Tile layout rules (see haiden/docs/spec.md A-2):
- columns run up-slope; 丸瓦 on s = k*pitch, 平瓦 centred between them, the
  kohai shares the main front grid so its columns flow into the main roof;
- 平瓦 3-ply (葺足 = L/3) resting on the two courses below (tilted), 丸瓦 with
  玉縁 nested; eave course = 軒平瓦(唐草) / 軒丸瓦(巴・珠文) projecting over 瓦座;
- hips / valleys: tiles are clipped per vertex along their axis (diagonal cut)
  against the hip line (+ overlap under the 隅棟) or against the valley line
  (leaving a visible 谷板 strip);
- ridges: 面戸漆喰 + 熨斗瓦 n段 + 冠瓦, ends with 獅子口 / 鬼瓦 (+鳥衾).
"""
import math
from types import SimpleNamespace

import numpy as np

from hlib import geom as G
from hlib import parts as PT
from hlib import kawara as KW

ZV = np.array([0.0, 0.0, 1.0])


def build(c, emit):
    p, R = c.p, c.R
    KP = p["kawara"]
    RF = c.RF
    Xe, Ye, Xg, ho, dg, Z0 = c.Xe, c.Ye, c.Xg, c.ho, c.dg, c.Z0
    Wk, yke, Zk0, y_j, d_j, dk_j = c.Wk, c.yke, c.Zk0, c.y_j, c.d_j, c.dk_j
    bump, kfade = c.bump, c.kfade
    m0, m1 = c.m0, c.m1
    th = R["thick"]
    MAT = KP.get("material", "Kawara_Ibushi")
    counts = {}
    info = {}

    pitch = KP["pitch"]
    HK = dict(L=KP["hira_L"], W0=KP["hira_W0"], W1=KP["hira_W1"], sag=KP["hira_sag"], t=KP["hira_t"])
    MK = dict(L=KP["maru_L"], tama=KP["maru_tama"], Ro=KP["maru_R"], tm=KP["maru_t"], w0=KP["maru_w0"])
    ashi_h = KP["hira_ashi"]
    ashi_m = MK["L"] - MK["tama"]
    lift0 = 2 * HK["t"]
    proj = KP["noki_proj"]
    hw_h, hw_m = HK["W0"] / 2, MK["Ro"]
    t_hira = KW.hira_tpl(**HK).done()
    t_maru = KW.maru_tpl(**MK).done()
    t_nhira = KW.noki_hira_tpl(HK).done()
    t_nmaru = KW.noki_maru_tpl(MK).done()
    t_kake = KW.kake_tpl().done()
    tile_top = MK["w0"] + MK["Ro"]           # maru crown above the base surface
    rb = tile_top - 0.03                     # ridge base level above the surface
    info["template_tris"] = {t.name: int(t.ntris) for t in (t_hira, t_maru, t_nhira, t_nmaru, t_kake)}

    MB = {k: G.MB() for k in ("hira", "maru", "nhira", "nmaru", "kake", "mendo", "noshi", "kanmuri", "oni",
                              "kawaraza", "tani", "ch_slab", "ch_hafu", "ch_gold", "ch_wall", "ch_lattice",
                              "ch_gegyo")}
    ridge_parts = {"mendo": MB["mendo"], "noshi": MB["noshi"], "kanmuri": MB["kanmuri"]}

    # ------------------------------------------------------------ surfaces
    s_e = float(RF.slope(0.0))

    def Fext(d):
        d = np.asarray(d, float)
        return np.where(d < 0, s_e * d, RF.F(d))

    def zm(x, y):
        x = np.asarray(x, float); y = np.asarray(y, float)
        ax = Xe - np.abs(x); ay = Ye - np.abs(y)
        upper = (np.abs(x) <= Xg + ho + 1e-9) & (ay >= dg)
        d = np.where(upper, ay, np.minimum(ax, ay))
        return Z0 + Fext(d) + RF.S(x, y)

    def zk(x, y):
        x = np.asarray(x, float); y = np.asarray(y, float)
        dk = y - yke
        t = np.clip(dk / dk_j, 0, 1)
        z1 = RF.z(x, np.full_like(x, y_j), np.full_like(x, d_j), False)
        h00 = 2 * t ** 3 - 3 * t ** 2 + 1; h10 = t ** 3 - 2 * t ** 2 + t; h01 = -2 * t ** 3 + 3 * t ** 2; h11 = t ** 3 - t ** 2
        z = h00 * Zk0 + h10 * dk_j * m0 + h01 * z1 + h11 * dk_j * m1
        z = np.where(dk < 0, Zk0 + m0 * dk, z)
        return z + bump(x) * kfade(np.maximum(dk, 0))

    def zfront(x, y):
        x = np.asarray(x, float); y = np.asarray(y, float)
        return np.where((y < y_j) & (np.abs(x) <= Wk), zk(x, y), zm(x, y))

    # ------------------------------------------------------------ chidori-hafu geometry
    CH = p.get("chidori")
    ch = None
    if CH and CH.get("enabled", True):
        ch = SimpleNamespace()
        ch.w = CH["halfw"]
        ch.yf = -(Ye - CH["d_front"])
        ch.yh = ch.yf - CH["overhang"]
        ch.th = CH.get("thick", 0.10)
        ee = np.linspace(0, ch.w + 0.5, 600)
        sl = CH["slope_eave"] + (CH["slope_ridge"] - CH["slope_eave"]) * np.clip(ee / ch.w, 0, 1) ** CH["slope_pow"]
        Fc = np.concatenate([[0], np.cumsum((sl[1:] + sl[:-1]) / 2 * np.diff(ee))])
        ch.Ze = float(zm(0.0, ch.yf)) + CH["raise"]
        ch.Zapex = ch.Ze + float(np.interp(ch.w, ee, Fc))

        def zc(x, _ee=ee, _Fc=Fc):
            e = ch.w - np.abs(np.asarray(x, float))
            return ch.Ze + np.where(e < 0, CH["slope_eave"] * e, np.interp(e, _ee, _Fc))
        ch.zc = zc
        # main front centre line z(y) (no sori this far in) for valley solving
        yy = np.linspace(ch.yh - 0.5, 0.0, 1500)
        zmy = zm(np.zeros_like(yy), yy)
        ch.y_vs = float(np.interp(ch.Ze, zmy, yy))         # chidori eave meets main roof
        ch.y_r = float(np.interp(ch.Zapex, zmy, yy))       # chidori ridge meets main roof
        # x_v(y): half-width of the chidori roof above the main roof at y
        yv = np.linspace(ch.y_vs, ch.y_r, 300)
        ev = np.interp(zm(np.zeros_like(yv), yv) - ch.Ze, Fc, ee)
        xv = ch.w - ev
        ch.yv_tab, ch.xv_tab = yv, xv

        def x_v(y, _yv=yv, _xv=xv):
            y = np.asarray(y, float)
            r = np.interp(y, _yv, _xv)
            r = np.where(y < _yv[0], 99.0, r)
            return np.where(y > _yv[-1], -1.0, r)

        def y_v(ax, _yv=yv, _xv=xv):
            ax = np.asarray(ax, float)
            r = np.interp(-ax, -_xv, _yv)
            return np.where(ax >= ch.w, -99.0, r)
        ch.x_v, ch.y_v = x_v, y_v
        info["chidori"] = dict(y_front=round(ch.yf, 3), y_hafu=round(ch.yh, 3), y_valley_start=round(ch.y_vs, 3),
                               y_ridge_end=round(ch.y_r, 3), z_eave=round(ch.Ze, 3), z_apex=round(ch.Zapex, 3),
                               halfw=ch.w)

    # ------------------------------------------------------------ columns
    def make_col(axis, cpos, q0, q1, zf, step=0.025):
        n = max(3, int(abs(q1 - q0) / step) + 1)
        q = np.linspace(q0, q1, n)
        cc = np.full(n, float(cpos))
        eps = 0.01
        if axis == "x":
            P = np.stack([cc, q, zf(cc, q)], 1)
            Lat = np.stack([np.full(n, 2 * eps), np.zeros(n), zf(cc + eps, q) - zf(cc - eps, q)], 1)
        else:
            P = np.stack([q, cc, zf(q, cc)], 1)
            Lat = np.stack([np.zeros(n), np.full(n, 2 * eps), zf(q, cc + eps) - zf(q, cc - eps)], 1)
        return KW.Column(P, Lat)

    def lay(col, kind, eave, cuts=(), start=0.0, end=None):
        if kind == "hira":
            return KW.stamp_column(MB["hira"], col, t_hira, ashi_h, HK["L"],
                                   first=(MB["nhira"], t_nhira) if eave else None, lift0=lift0, cuts=cuts,
                                   start=start, end=end, counts=counts, key="hira")
        return KW.stamp_column(MB["maru"], col, t_maru, ashi_m, MK["L"],
                               first=(MB["nmaru"], t_nmaru) if eave else None, lift0=0.0, cuts=cuts,
                               start=start, end=end, counts=counts, key="maru")

    def count_eave(eave, kind):
        if eave:
            k = "noki_hira" if kind == "hira" else "noki_maru"
            counts[k] = counts.get(k, 0) + 1

    # cut factories: shift along D so that vertices satisfy a plan constraint
    def cut_upper_d(dfun, limit_fun, inward):
        """keep dfun(X) <= limit_fun(X); moving along D changes d at rate D.inward."""
        def f(X, D):
            e = dfun(X) - limit_fun(X)
            rate = np.abs(D @ inward)[:, None] + 1e-6
            return -np.maximum(e, 0) / rate
        return f

    def cut_lower_d(dfun, limit_fun, inward):
        def f(X, D):
            e = limit_fun(X) - dfun(X)
            rate = np.abs(D @ inward)[:, None] + 1e-6
            return np.maximum(e, 0) / rate
        return f

    hip_over = KP.get("hip_overlap", 0.07)
    grid = lambda A: np.arange(-math.floor(A / pitch * 2) - 1, math.floor(A / pitch * 2) + 2) * pitch / 2

    # ---- main roof, four sides
    for side in ("Front", "Back", "Right", "Left"):
        if side in ("Front", "Back"):
            axis, sg, A_e, W_e = "x", (-1 if side == "Front" else 1), Xe, Ye
            inward = np.array([0, -sg, 0.0])
            dfun = lambda X, _sg=sg: Ye - np.abs(X[..., 1])
            hipl = lambda X: Xe - np.abs(X[..., 0])
        else:
            axis, sg, A_e, W_e = "y", (1 if side == "Right" else -1), Ye, Xe
            inward = np.array([-sg, 0, 0.0])
            dfun = lambda X: Xe - np.abs(X[..., 0])
            hipl = lambda X: Ye - np.abs(X[..., 1])
        qd = lambda d, _sg=sg, _W=W_e: _sg * (_W - d)       # d -> plan coordinate
        hipcut = cut_upper_d(dfun, lambda X: hipl(X) + hip_over, inward)
        for k2, s in enumerate(grid(A_e)):
            kind = "maru" if (round(s / pitch * 2) % 2 == 0) else "hira"
            hw = hw_m if kind == "maru" else hw_h
            a = abs(s)
            if a > A_e - 0.02:
                continue
            zf = zm
            ivals = []          # (d0, d1, eave, cuts)
            if axis == "x":
                if a <= Xg:
                    ivals.append((-proj, Ye, True, []))
                else:
                    ivals.append((-proj, Xe - a + hw + hip_over, True, [hipcut]))
                    if a + hw <= Xg + ho - 0.15:
                        ivals.append((dg, Ye, False, []))
            else:
                ivals.append((-proj, min(dg, Ye - a + hw + hip_over), True, [hipcut]))
            for (d0, d1, eave, cuts) in ivals:
                if side == "Front":
                    # kohai: columns inside the kohai ride the kohai roof from its eave
                    y0 = qd(d0); y1 = qd(d1)
                    if a + hw <= Wk - 0.14 and d0 < 0.5:
                        y0 = yke - proj; zf = zfront
                    elif a < Wk and d0 < 0.5:
                        y0 = y_j; eave = False; zf = zfront
                    segs = [(y0, y1, eave, list(cuts))]
                    if ch is not None and a - hw < ch.w + 0.02:
                        segs2 = []
                        for (ya, yb, ev, cu) in segs:
                            yA = ch.yf - KP.get("chidori_foot_gap", 0.03)
                            front_cut = cut_upper_d(lambda X: X[..., 1], lambda X: np.full(X.shape[:-1], yA), np.array([0, 1.0, 0]))
                            if ya < yA:
                                segs2.append((ya, min(yb, yA), ev, cu + [front_cut]))
                            g2 = KP.get("valley_gap", 0.05)
                            yB = float(ch.y_v(min(a + hw, ch.w - 1e-3))) + g2 if a - hw < ch.w else yA
                            vcut = cut_lower_d(lambda X: X[..., 1], lambda X, _g=g2: np.where(np.abs(X[..., 0]) < ch.w, ch.y_v(np.abs(X[..., 0])) + _g, -99.0), np.array([0, 1.0, 0]))
                            if yb > yB:
                                segs2.append((max(ya, yB), yb, False, cu + [vcut]))
                        segs = segs2
                    for (ya, yb, ev, cu) in segs:
                        if yb - ya < 0.08:
                            continue
                        col = make_col("x", s, ya, yb, zf)
                        lay(col, kind, ev, cu); count_eave(ev, kind)
                else:
                    if d1 - d0 < 0.08:
                        continue
                    col = make_col(axis, s, qd(d0), qd(d1), zf)
                    lay(col, kind, eave, cuts); count_eave(eave, kind)

    # ---- 袖瓦 (sode) maru columns + 掛瓦 along the main gable edges
    def kake_run(P, out_dir, z_off=0.03):
        """掛瓦 pieces along an edge polyline P, outward horizontal out_dir."""
        P = G.resample(np.asarray(P, float), 0.02)
        D0 = G.nrm(P[-1] - P[0])
        if np.cross(out_dir, D0)[2] < 0:
            P = P[::-1]
        col = KW.Column(P + ZV * z_off, np.tile(out_dir, (len(P), 1)))
        a = np.arange(0, col.length - 0.05, 0.29)
        b = np.minimum(a + 0.30, col.length)
        PA, LA = col.at(a); PB, _ = col.at(b)
        D = G.nrm(PB - PA)
        N = G.nrm(np.cross(LA, D)); Lat = G.nrm(np.cross(D, N))
        KW.place(MB["kake"], t_kake, PA, D, Lat, N, (b - a) / 0.30)
        counts["kake"] = counts.get("kake", 0) + len(a)

    sode_off = KP.get("sode_inset", 0.075)
    for sx in (-1, 1):
        xs_ = sx * (Xg + ho - sode_off)
        for sy in (-1, 1):
            col = make_col("x", xs_, sy * (Ye - dg), sy * 0.0, zm)
            lay(col, "maru", False)
            counts["sode_maru_cols"] = counts.get("sode_maru_cols", 0) + 1
            yy = np.linspace(sy * (Ye - dg + 0.02), 0.0, 40)
            xe = np.full_like(yy, sx * (Xg + ho + 0.05))
            kake_run(np.stack([xe, yy, zm(np.full_like(yy, sx * (Xg + ho)), yy)], 1), np.array([sx, 0, 0.0]))

    # ---- kohai 袖 + 掛瓦 on its side bargeboards
    for sx in (-1, 1):
        col = make_col("x", sx * (Wk - sode_off), yke - proj, y_j, zfront)
        lay(col, "maru", True); count_eave(True, "maru")
        yy = np.linspace(yke - 0.02, -Ye + 0.15, 40)
        kake_run(np.stack([np.full_like(yy, sx * (Wk + 0.065)), yy, zk(np.full_like(yy, sx * Wk), yy)], 1),
                 np.array([sx, 0, 0.0]), z_off=0.03)

    # ---- 瓦座 strip along the main eaves (wood board fronting the base slab)
    for side in ("Front", "Back", "Right", "Left"):
        if side in ("Front", "Back"):
            sg = -1 if side == "Front" else 1
            ss = np.linspace(-Xe, Xe, 160)
            if side == "Front":
                parts_ = [ss[ss <= -Wk + 0.02], ss[ss >= Wk - 0.02]]
            else:
                parts_ = [ss]
            for q in parts_:
                if len(q) < 2:
                    continue
                pts = np.stack([q, np.full_like(q, sg * (Ye + 0.015)), zm(q, np.full_like(q, sg * Ye))], 1)
                pts[:, 2] += (lift0 - th) / 2
                V, F = G.sweep(pts, G.rect_profile(0.03, th + lift0, 0.004), mode="vertical")
                MB["kawaraza"].add(V, F)
        else:
            sg = 1 if side == "Right" else -1
            q = np.linspace(-Ye, Ye, 120)
            pts = np.stack([np.full_like(q, sg * (Xe + 0.015)), q, zm(np.full_like(q, sg * Xe), q)], 1)
            pts[:, 2] += (lift0 - th) / 2
            V, F = G.sweep(pts, G.rect_profile(0.03, th + lift0, 0.004), mode="vertical")
            MB["kawaraza"].add(V, F)
    # kohai 瓦座 sits behind the karahafu board (hidden) - lift the eave course
    q = np.linspace(-Wk, Wk, 90)
    pts = np.stack([q, np.full_like(q, yke + 0.02), zk(q, np.full_like(q, yke))], 1)
    pts[:, 2] += lift0 / 2
    V, F = G.sweep(pts, G.rect_profile(0.04, lift0 + 0.02, 0.004), mode="vertical")
    MB["kawaraza"].add(V, F)

    # ------------------------------------------------------------ ridges
    def surf_path(xy, zf, lift=rb):
        xy = np.asarray(xy, float)
        return np.stack([xy[:, 0], xy[:, 1], zf(xy[:, 0], xy[:, 1]) + lift], 1)

    # 大棟
    Lr = Xg + ho + 0.02
    xx = np.linspace(-Lr, Lr, 120)
    z_ridge0 = float(zm(0.0, 0.0))
    P = np.stack([xx, np.zeros_like(xx), np.full_like(xx, z_ridge0 + KP["omune_base"])], 1)
    om = KP["omune"]
    ztop, _ = KW.ridge(ridge_parts, P, n_layers=om["layers"], w0=om["w0"], hn=om["hn"], inset=om["inset"],
                       base_h=om["base_h"], bury=0.35, counts=counts, key="omune")
    for sx in (-1, 1):
        KW.shishiguchi(MB["oni"], (sx * (Lr + 0.10), 0, z_ridge0 + KP["omune_base"] - 0.06), (sx, 0),
                       W=om["shishi_W"], H=ztop - KP["omune_base"] + 0.30, depth=0.42)
        counts["shishiguchi"] = counts.get("shishiguchi", 0) + 1
    info["omune_top"] = round(z_ridge0 + KP["omune_base"] + ztop, 3)

    # 降棟 (along the gable edges) + 降り鬼 at the feet
    kd = KP["kudari"]
    for sx in (-1, 1):
        x_k = sx * (Xg + ho - kd["inset"])
        for sy in (-1, 1):
            yy = np.linspace(sy * 0.22, sy * (Ye - dg - kd.get("foot_extra", 0.0)), 50)
            P = surf_path(np.stack([np.full_like(yy, x_k), yy], 1), zm)
            zt, Pr = KW.ridge(ridge_parts, P, n_layers=kd["layers"], w0=kd["w0"], hn=kd["hn"], inset=0.01,
                              base_h=0.06, counts=counts, key="kudari")
            foot = Pr[-1]
            KW.oni(MB["oni"], foot + np.array([0, sy * 0.10, -0.05]), (0, sy), W=kd["oni_W"], H=kd["oni_H"],
                   t=0.09, ridge_top=foot[2] + zt)
            counts["kudari_oni"] = counts.get("kudari_oni", 0) + 1

    # 隅棟 + 隅鬼(二の鬼) + 稚児棟 + 一の鬼 + 巴蓋 at the four corners
    sm = KP["sumi"]
    for sx in (-1, 1):
        for sy in (-1, 1):
            g = np.array([sx, sy, 0.0]) / math.sqrt(2)
            dd = np.linspace(sm["d_oni"], sm["d_top"], 40)
            xy = np.stack([sx * (Xe - dd), sy * (Ye - dd)], 1)
            P = surf_path(xy, zm)
            zt, Pr = KW.ridge(ridge_parts, P, n_layers=sm["layers"], w0=sm["w0"], hn=sm["hn"], inset=0.01,
                              base_h=0.06, counts=counts, key="sumi", end_pad=(0.0, 0.0))
            base = Pr[0]
            KW.oni(MB["oni"], base + g * 0.05 + ZV * (-0.03), g[:2], W=sm["oni_W"], H=sm["oni_H"], t=0.09,
                   ridge_top=base[2] + zt)
            # 稚児棟
            dd = np.linspace(sm["d_chigo_tip"], sm["d_oni"] - 0.05, 20)
            xy = np.stack([sx * (Xe - dd), sy * (Ye - dd)], 1)
            P = surf_path(xy, zm, lift=rb - 0.01)
            zt2, Pr2 = KW.ridge(ridge_parts, P, n_layers=sm["chigo_layers"], w0=sm["chigo_w0"], hn=sm["hn"],
                                inset=0.01, base_h=0.05, counts=counts, key="chigo")
            tip = Pr2[0]
            KW.oni(MB["oni"], tip + g * 0.04 + ZV * (-0.03), g[:2], W=sm["ichi_W"], H=sm["ichi_H"], t=0.07,
                   ridge_top=tip[2] + zt2)
            # 巴蓋 at the corner eave (隅巴)
            cpt = np.array([sx * (Xe + proj * 0.7), sy * (Ye + proj * 0.7), 0.0])
            cpt[2] = float(zm(cpt[0], cpt[1])) + MK["w0"] + 0.01
            KW.tomoebuta(MB["oni"], cpt, g + ZV * (-0.25), r=0.085, L=0.45)
            counts["sumi_oni"] = counts.get("sumi_oni", 0) + 1
            counts["ichi_oni"] = counts.get("ichi_oni", 0) + 1
            counts["tomoebuta"] = counts.get("tomoebuta", 0) + 1

    # 雨押え (along the foot of the main gable walls, on the side slopes)
    ao = KP["amaosae"]
    for sx in (-1, 1):
        yy = np.linspace(-(Ye - dg - ao["end"]), Ye - dg - ao["end"], 40)
        P = surf_path(np.stack([np.full_like(yy, sx * (Xg + ao["off"])), yy], 1), zm)
        KW.ridge(ridge_parts, P, n_layers=ao["layers"], w0=ao["w0"], hn=0.04, inset=0.01, base_h=0.05,
                 counts=counts, key="amaosae")

    # 唐破風: apex 棟 + 鬼 (唐破風鬼) and the curved front course already laid by the kohai columns
    kr = KP["karahafu"]
    yy = np.linspace(yke - 0.03, yke + kr["mune_len"], 30)
    P = surf_path(np.stack([np.zeros_like(yy), yy], 1), zk)
    zt, Pr = KW.ridge(ridge_parts, P, n_layers=kr["layers"], w0=kr["w0"], hn=0.04, inset=0.01, base_h=0.05,
                      counts=counts, key="karahafu")
    KW.oni(MB["oni"], Pr[0] + np.array([0, -0.07, -0.06]), (0, -1), W=kr["oni_W"], H=kr["oni_H"], t=0.08,
           ridge_top=Pr[0][2] + zt)
    counts["karahafu_oni"] = 1

    # ------------------------------------------------------------ 千鳥破風
    if ch is not None:
        build_chidori(c, ch, CH, KP, MB, ridge_parts, counts, zm, make_col, lay, kake_run, surf_path, proj,
                      hw_h, hw_m, pitch, sode_off, rb)

    # ------------------------------------------------------------ emit
    C = "05_Yane_Roof"
    emit("Kawara_Hiragawara_FlatTiles", MB["hira"], MAT, C, smooth=40)
    emit("Kawara_Marugawara_RoundTiles", MB["maru"], MAT, C, smooth=50)
    emit("Kawara_Nokihira_EaveFlat_Karakusa", MB["nhira"], MAT, C, smooth=40)
    emit("Kawara_Nokimaru_EaveRound_Tomoe", MB["nmaru"], MAT, C, smooth=50)
    emit("Kawara_Kakegawara_Keraba", MB["kake"], MAT, C, smooth=40)
    emit("Kawara_Mune_Noshi_Stack", MB["noshi"], MAT, C, smooth=20)
    emit("Kawara_Mune_Ganburi_Cap", MB["kanmuri"], MAT, C, smooth=50)
    emit("Kawara_Mune_Mendo_Shikkui", MB["mendo"], "Shikkui_Plaster", C, smooth=20)
    emit("Kawara_Onigawara_Shishiguchi_Tomoebuta", MB["oni"], MAT, C, smooth=40)
    emit("Kawaraza_EaveTileBoard", MB["kawaraza"], "Kiji_Hinoki_Wood", C, smooth=20)
    if ch is not None:
        C2 = "11_Chidori_Hafu"
        emit("Chidori_Yane_Base", MB["ch_slab"], "Kawara_Base", C2, smooth=40)
        emit("Chidori_Tani_ValleyCopper", MB["tani"], "Doban_Rokusho_Copper", C2, smooth=40)
        emit("Chidori_Hafu_Bargeboard", MB["ch_hafu"], "Nuri_Shu_Vermilion", C2)
        emit("Chidori_Hafu_Kanagu_GoldTrim", MB["ch_gold"], "Kanagu_Gold", C2)
        emit("Chidori_Tsuma_GableBoard", MB["ch_wall"], "Kuro_Urushi_Lacquer", C2)
        emit("Chidori_Kitsuregoshi_Lattice", MB["ch_lattice"], "Nuri_Shu_Vermilion", C2)
        emit("Chidori_Gegyo_Pendant", MB["ch_gegyo"], "Kiji_Hinoki_Wood", C2)
    tiles = sum(v for k, v in counts.items() if k in ("hira", "maru"))
    info["counts"] = counts
    info["tiles_total"] = int(tiles)
    return info


def build_chidori(c, ch, CH, KP, MB, ridge_parts, counts, zm, make_col, lay, kake_run, surf_path, proj,
                  hw_h, hw_m, pitch, sode_off, rb):
    R = c.R
    w = ch.w
    zc = ch.zc
    zcf = lambda x, y: zc(x)
    g2 = KP.get("valley_gap", 0.05)

    # base slab (野地) over the whole chidori footprint; parts below the main roof are buried
    nx = 2 * int(w / 0.04) + 1
    xs = np.linspace(-w - 0.02, w + 0.02, nx)
    xs = np.unique(np.concatenate([xs, [0.0]]))
    ys = np.linspace(ch.yh - 0.02, ch.y_r + 0.4, 24)
    X, Y = np.meshgrid(xs, ys)
    Zt = zc(X)
    slab_grid = c.slab_grid
    MB["ch_slab"].addt(slab_grid(X, Y, Zt, Zt - ch.th))

    # tile columns (run from the eave/valley up to the chidori ridge at x=0)
    y0 = ch.yh + sode_off + 0.075
    s_list = np.arange(y0, ch.y_r - 0.05, pitch / 2)
    for i, s in enumerate(s_list):
        kind = "hira" if i % 2 == 0 else "maru"
        hw = hw_h if kind == "hira" else hw_m
        for sx in (-1, 1):
            front = s + hw < ch.y_vs + 0.02
            if front:
                xa = sx * (w + proj)
            else:
                xa_abs = min(w + proj, float(ch.x_v(max(s - hw, ch.y_vs))))
                if xa_abs < 0.08:
                    continue
                xa = sx * xa_abs

            def vc(X, D, _sx=sx):
                lim = ch.x_v(X[..., 1]) - g2
                e = np.abs(X[..., 0]) - lim
                rate = np.abs(D[:, 0])[:, None] + 1e-6
                return np.maximum(e, 0) / rate
            col = make_col("y", s, xa, 0.0, zcf)
            if col.length < 0.1:
                continue
            lay(col, kind, front, [vc])
            if front:
                counts["chidori_noki"] = counts.get("chidori_noki", 0) + 1
    # 袖 maru + 掛瓦 along the hafu
    for sx in (-1, 1):
        col = make_col("y", ch.yh + sode_off, sx * (w + proj), 0.0, zcf)
        lay(col, "maru", True)
        xx = np.linspace(sx * (w + 0.06), 0.0, 40)
        kake_run(np.stack([xx, np.full_like(xx, ch.yh - 0.05), zc(xx)], 1), np.array([0, -1.0, 0]))

    # valley boards (谷板): strip following max(main, chidori) across the crease
    for sx in (-1, 1):
        yv = np.linspace(ch.y_vs + 1e-3, ch.y_r, 40)
        xv = ch.x_v(yv)
        offs = np.linspace(-0.16, 0.16, 7)
        Xg_ = sx * (xv[:, None] + offs[None, :])
        Yg_ = np.repeat(yv[:, None], len(offs), 1)
        Zt = np.maximum(zm(Xg_, Yg_), zc(Xg_)) + 0.012
        if sx < 0:
            Xg_, Yg_, Zt = Xg_[:, ::-1], Yg_[:, ::-1], Zt[:, ::-1]
        MB["tani"].addt(slab_grid(Xg_, Yg_, Zt, Zt - 0.01))

    # gable wall (妻) at y_f + 木連格子 + 懸魚
    xsw = np.linspace(-w, w, 81)
    ztp = zc(xsw) - ch.th - 0.005
    zb = float(zm(0.0, ch.yf)) - 0.06
    m = ztp > zb + 0.03
    xv_, zv_ = xsw[m], ztp[m]
    outline = np.array([(xv_[0], zb), (xv_[-1], zb)] + [(a, b) for a, b in zip(xv_[::-1], zv_[::-1])])
    o2 = outline.copy(); o2[:, 1] -= zb
    MB["ch_wall"].addt(G.extrude_poly(o2, 0.04, (np.array([0, ch.yf, zb]), np.array([1.0, 0, 0]), np.array([0, 0, 1.0]))))
    for x_ in np.arange(xv_[0] + 0.07, xv_[-1], 0.13):
        zt_ = np.interp(x_, xsw, ztp)
        if zt_ - zb < 0.08:
            continue
        MB["ch_lattice"].addt(G.beams([(x_, ch.yf - 0.035, zb + 0.06)], [(x_, ch.yf - 0.035, zt_)], 0.035, 0.035))
    for z_ in np.arange(zb + 0.16, zv_.max(), 0.13):
        inside = xv_[zv_ > z_ + 0.01]
        if len(inside) < 2:
            continue
        MB["ch_lattice"].addt(G.beams([(inside[0], ch.yf - 0.055, z_)], [(inside[-1], ch.yf - 0.055, z_)], 0.035, 0.035))
    # bargeboard (破風) with taper toward the ends + gold trim
    hh0, hh1, ht = CH["hafu_h"], CH["hafu_h_end"], R["hafu_t"]
    xh = np.linspace(-w - 0.06, w + 0.06, 121)
    ztop = zc(xh) + 0.035
    hh = hh1 + (hh0 - hh1) * (1 - np.abs(xh) / (w + 0.06)) ** 0.6
    for half in (xh <= 0, xh >= 0):
        x_ = xh[half]
        pts = np.stack([x_, np.full_like(x_, ch.yh - ht / 2 + 0.01), ztop[half] - hh[half] / 2], 1)
        sc = np.stack([np.ones_like(x_), hh[half]], 1)
        V, F = G.sweep(pts, G.rect_profile(ht, 1.0, 0.0), mode="vertical", scale=sc)
        MB["ch_hafu"].add(V, F)
        pts2 = np.stack([x_, np.full_like(x_, ch.yh - ht / 2 + 0.008), ztop[half] - 0.012], 1)
        V, F = G.sweep(pts2, G.rect_profile(ht + 0.006, 0.026), mode="vertical")
        MB["ch_gold"].add(V, F)
    # 懸魚 at the apex (猪目懸魚) + 六葉
    Wg, Hg = CH["gegyo_W"], CH["gegyo_H"]
    org = np.array([0.0, ch.yh - ht - 0.02, ch.Zapex + 0.035 - hh0 + 0.06])
    U = np.array([1.0, 0, 0])
    MB["ch_gegyo"].addt(G.extrude_poly(PT.gegyo_outline(Wg, Hg), 0.05, (org, U, np.array([0, 0, 1.0])),
                                       holes=[PT.heart(0, -Hg * 0.42, 0.15), PT.heart(-Wg * 0.17, -Hg * 0.65, 0.11),
                                              PT.heart(Wg * 0.17, -Hg * 0.65, 0.11)]))
    for sd in (1, -1):
        MB["ch_gegyo"].addt(G.extrude_poly(PT.gegyo_fin(Wg, Hg, sd), 0.035, (org + np.array([0, 0.01, 0]), U, np.array([0, 0, 1.0]))))
    MB["ch_gold"].addt(PT.rokuyo(org + np.array([0, -0.03, -Hg * 0.12]), (0, -1, 0), r=0.07, seg=24))
    MB["ch_gold"].addt(PT.rokuyo(org + np.array([0, -0.03, -Hg * 0.85]), (0, -1, 0), r=0.05, seg=24))

    # ridge (棟) along x=0, dies into the main roof; 鬼瓦 at the front
    cm = KP["chidori_mune"]
    yy = np.linspace(ch.yh - 0.03, ch.y_r + cm["tail"], 40)
    P = np.stack([np.zeros_like(yy), yy, np.full_like(yy, ch.Zapex + rb + 0.02)], 1)
    zt, Pr = KW.ridge(ridge_parts, P, n_layers=cm["layers"], w0=cm["w0"], hn=cm["hn"], inset=0.01, base_h=0.06,
                      bury=0.3, counts=counts, key="chidori_mune")
    KW.oni(MB["oni"], Pr[0] + np.array([0, -0.10, -0.05]), (0, -1), W=cm["oni_W"], H=cm["oni_H"], t=0.10,
           ridge_top=Pr[0][2] + zt)
    counts["chidori_oni"] = 1
    # 降棟 along the hafu with small 鬼 at the lower ends
    for sx in (-1, 1):
        xx = np.linspace(sx * 0.25, sx * (w - cm["kudari_end"]), 30)
        yk_ = ch.yh + cm["kudari_inset"]
        P = np.stack([xx, np.full_like(xx, yk_), zc(xx) + rb], 1)
        zt, Pr = KW.ridge(ridge_parts, P, n_layers=cm["kudari_layers"], w0=cm["kudari_w0"], hn=0.04, inset=0.01,
                          base_h=0.05, counts=counts, key="chidori_kudari")
        KW.oni(MB["oni"], Pr[-1] + np.array([sx * 0.08, 0, -0.05]), (sx, 0), W=cm["kudari_oni_W"],
               H=cm["kudari_oni_H"], t=0.07, ridge_top=Pr[-1][2] + zt)
        counts["chidori_kudari_oni"] = counts.get("chidori_kudari_oni", 0) + 1
    # 雨押え熨斗 at the gable foot (main roof side)
    ao = KP["chidori_amaosae"]
    xx = np.linspace(-(w - ao["end"]), w - ao["end"], 30)
    P = surf_path(np.stack([xx, np.full_like(xx, ch.yf - ao["off"])], 1), zm)
    KW.ridge(ridge_parts, P, n_layers=ao["layers"], w0=ao["w0"], hn=0.04, inset=0.01, base_h=0.04,
             kan=ao.get("kan", True), counts=counts, key="chidori_amaosae")
