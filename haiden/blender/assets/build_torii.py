#!/usr/bin/env python3
"""T-1 明神鳥居 (王道形・実寸) の手続き生成。仕様は haiden/docs/assets.md / research_torii.md。

    python3 haiden/blender/assets/build_torii.py --variant T-1 --out haiden/out/T-1

部材: 笠木(黒・甲板つき・反り増し・木口は反りに直交) / 島木(朱・笠木に沿う反り) /
貫(朱・柱を貫通して外へ出る・柱外側に楔) / 額束 + 扁額(黒地金文字「八幡宮」) /
柱(朱・内転び・わずかに上すぼまり・柱頭は島木に差し込み、台輪なし) /
根巻(黒・上端に帯) / 亀腹(白漆喰の饅頭形)。
座標: 原点=2本の柱脚の中点(地面 Z=0)、X=柱の並ぶ方向、正面=-Y、Z=上、m。
仕上げ: KHR_materials_variants  nuri=丹塗 / ishi=石(花崗岩)。各メッシュに finish_mats を付ける。
出力: <out>/haiden.blend, haiden.glb, haiden_web.glb (WebP+Draco), stats.json, textures/
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
BL = os.path.dirname(HERE)
sys.path.insert(0, BL)

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from hlib import geom as G  # noqa: E402
from hlib.materials import NB, SPEC, _periodic_noise, _ramp, _mul, make_material  # noqa: E402
from hlib import materials2 as M2  # noqa: E402  (bake_tiles2 / glb_material2 / make_material2 を利用。編集しない)

FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
FINISHES = [{"id": "nuri", "name": "丹塗"}, {"id": "ishi", "name": "石"}]

# ------------------------------------------------------------------ 寸法 (m)
P = dict(
    H=4.50,             # 笠木(甲板)上端の地上高(中央)
    S=3.60,             # 柱心間(柱脚)
    d=0.36,             # 柱径(柱脚) = S/10
    d_top=0.34,         # 柱径(柱頭) わずかに上すぼまり
    lean_deg=1.5,       # 内転び
    kasa_L=6.00,        # 笠木全長(柱心から各1.20の出)
    kasa_w=0.44,        # 笠木の幅(奥行)
    kasa_h=0.30,        # 笠木の成(中央、甲板を除く)
    kasa_sori_bot=0.20,  # 笠木下端(=島木上端)の端での反り上がり
    kasa_sori_add=0.10,  # 反り増し: 端で上端がさらに上がる量(成が増す)
    sori_pow=3.2,
    kou_t=0.040,        # 甲板の厚(中央)
    kou_crown=0.016,    # 甲板上面の流れ(中央の高まり)
    shima_L=5.70,       # 島木全長
    shima_w=0.38,
    shima_h=0.26,
    nuki_L=6.00,
    nuki_h=0.27,        # 貫の成 ≒ 0.75d
    nuki_t=0.16,        # 貫の厚 ≒ 0.45d
    nuki_gap=0.62,      # 貫上端〜島木下端(中央)の内法
    kusabi_w=0.055, kusabi_t=0.085, kusabi_up=0.065, kusabi_dn=0.035,
    gaku_w=0.22, gaku_t=0.14,
    hen_w=0.36, hen_h=0.50, hen_frame=0.052, hen_t=0.060,
    kame_r=0.43, kame_h=0.22,     # 亀腹(饅頭形)
    nemaki_top=0.66, nemaki_bot=0.12, nemaki_t=0.010, band_h=0.035, band_t=0.012,
)

UV_TILE = 2.0
ROOT = None
MATS = {}


# ------------------------------------------------------------------ materials

def _custom_material(name, col, rough, metal, kind):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = False
    nb = NB(m)
    bsdf = nb.N.get("Principled BSDF")
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    m["glb_color"] = list(col); m["glb_rough"] = rough; m["glb_metal"] = metal
    m.diffuse_color = (*col, 1)
    tc = nb.node("ShaderNodeTexCoord")
    sep = nb.node("ShaderNodeSeparateXYZ")
    nb.link(tc.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs[0], sep.outputs[1]
    bump_s = 0.2
    if kind == "granite":
        # 花崗岩(御影): 明るい灰の地に 黒雲母の黒い粒・長石の白い粒・石英の灰、ゆるい斑
        mott = _periodic_noise(nb, u, v, 3.0, 4, 0.55)
        blk = _periodic_noise(nb, u, v, 95.0, 1, 0.4)
        wht = _periodic_noise(nb, u, v, 70.0, 1, 0.4)
        mid = _periodic_noise(nb, u, v, 140.0, 2, 0.5)
        base = _ramp(nb, nb.math("ADD", nb.math("MULTIPLY", mott, 0.5), nb.math("MULTIPLY", mid, 0.5)),
                     _mul(col, 0.86), _mul(col, 1.10), 0.30, 0.72)
        rb = nb.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        nb._in(rb.inputs["Value"], blk); rb.inputs["From Min"].default_value = 0.64; rb.inputs["From Max"].default_value = 0.69
        rw = nb.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        nb._in(rw.inputs["Value"], wht); rw.inputs["From Min"].default_value = 0.62; rw.inputs["From Max"].default_value = 0.68
        c1 = M2._mix(nb, nb.math("MULTIPLY", rw.outputs["Result"], 0.7), base, _mul(col, 1.35))
        color = M2._mix(nb, rb.outputs["Result"], c1, (0.035, 0.034, 0.033))
        rough_f = nb.math("ADD", nb.math("MULTIPLY", rb.outputs["Result"], -0.25), rough)
        height = nb.math("ADD", nb.math("MULTIPLY", mid, 0.6), nb.math("MULTIPLY", rb.outputs["Result"], -0.4))
        bump_s = 0.30
    elif kind == "blackmetal":
        # 根巻(黒塗の銅板): ごく弱いむら・擦れ
        n1 = _periodic_noise(nb, u, v, 5.0, 5, 0.6)
        n2 = _periodic_noise(nb, u, v, 1.6, 4, 0.5, stretch=(1.0, 10.0))
        color = _ramp(nb, nb.math("ADD", nb.math("MULTIPLY", n1, 0.6), nb.math("MULTIPLY", n2, 0.4)),
                      _mul(col, 0.7), _mul(col, 1.6), 0.30, 0.75)
        rough_f = nb.math("ADD", nb.math("MULTIPLY", n1, 0.18), rough - 0.08)
        height = n1
        bump_s = 0.08
    else:  # "sumi": 扁額の地板(艶消しの黒)
        n1 = _periodic_noise(nb, u, v, 8.0, 4, 0.5)
        color = _ramp(nb, n1, _mul(col, 0.8), _mul(col, 1.3), 0.35, 0.7)
        rough_f = nb.math("ADD", nb.math("MULTIPLY", n1, 0.1), rough - 0.05)
        height = n1
        bump_s = 0.05
    m["_bake_color_node"] = color.node.name
    m["_bake_color_sock"] = color.name
    m["_bake_rough_node"] = rough_f.node.name
    m["_bake_rough_sock"] = rough_f.name
    ao = nb.node("ShaderNodeAmbientOcclusion", samples=6)
    ao.inputs["Distance"].default_value = 0.25
    grime = nb.node("ShaderNodeValToRGB")
    nb.link(ao.outputs["AO"], grime.inputs[0])
    g = grime.color_ramp.elements
    g[0].position = 0.0; g[0].color = (0.55, 0.53, 0.50, 1)
    g[1].position = 1.0; g[1].color = (1, 1, 1, 1)
    out_col = M2._mix(nb, 1.0, color, grime.outputs[0], blend="MULTIPLY")
    nb.link(out_col, bsdf.inputs["Base Color"])
    nb.link(rough_f, bsdf.inputs["Roughness"])
    bump = nb.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_s
    bump.inputs["Distance"].default_value = 0.003
    nb.link(height, bump.inputs["Height"])
    nb.link(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


CUSTOM = {
    "Torii_Granite":      ((0.40, 0.395, 0.375), 0.72, 0.0, "granite"),
    "Torii_Granite_Base": ((0.33, 0.320, 0.300), 0.78, 0.0, "granite"),
    "Torii_Granite_Dark": ((0.16, 0.155, 0.150), 0.80, 0.0, "granite"),
    "Torii_Kuro_Nemaki":  ((0.016, 0.015, 0.014), 0.42, 0.35, "blackmetal"),
    "Torii_Kuro_Kasagi":  ((0.014, 0.012, 0.011), 0.50, 0.0, "sumi"),
    "Torii_Kuro_Sumi":    ((0.022, 0.019, 0.017), 0.65, 0.0, "sumi"),
}
BAKE = ["Nuri_Shu_Vermilion", "Kuro_Urushi_Lacquer", "Shikkui_Plaster"] + list(CUSTOM)


def mat(name):
    if name not in MATS:
        if name in CUSTOM:
            MATS[name] = _custom_material(name, *CUSTOM[name])
        elif name in M2.SPEC2:
            MATS[name] = M2.make_material2(name)
        else:
            MATS[name] = make_material(name)
    return MATS[name]


# 部材ごとの仕上げ (nuri, ishi)
FIN = {
    "Hashira":       ("Nuri_Shu_Vermilion", "Torii_Granite"),
    "Shimaki":       ("Nuri_Shu_Vermilion", "Torii_Granite"),
    "Nuki":          ("Nuri_Shu_Vermilion", "Torii_Granite"),
    "Kusabi":        ("Nuri_Shu_Vermilion", "Torii_Granite"),
    "Gakuzuka":      ("Nuri_Shu_Vermilion", "Torii_Granite"),
    "Kasagi":        ("Torii_Kuro_Kasagi", "Torii_Granite"),
    "Kasagi_Kouita": ("Torii_Kuro_Nemaki", "Torii_Granite"),
    "Nemaki":        ("Torii_Kuro_Nemaki", "Torii_Granite"),
    "Kamebara":      ("Shikkui_Plaster", "Torii_Granite_Base"),
    "Hengaku_Frame": ("Kuro_Urushi_Lacquer", "Torii_Granite"),
    "Hengaku_Board": ("Torii_Kuro_Sumi", "Torii_Granite"),
    "Hengaku_Moji":  ("Kanagu_Gold", "Torii_Granite_Dark"),
}


# ------------------------------------------------------------------ geometry helpers

def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        ROOT.children.link(c)
    return c


def emit(name, mb, part, cname, smooth=35.0, uv_mode="grain", cyl=None):
    me = mb.to_mesh(name, uv_tile=UV_TILE, uv_mode=uv_mode)
    if cyl is not None:
        cyl_uv(me, *cyl)
    me.materials.append(mat(FIN[part][0]))
    if smooth:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(smooth))
    ob = bpy.data.objects.new(name, me)
    ob["part"] = part
    coll(cname).objects.link(ob)
    return ob


def cyl_uv(me, origin, axis):
    """円柱・回転体の UV: u = 軸方向(木目)、v = 周長。継ぎ目をまたぐ面は角度を補正。"""
    o = np.asarray(origin, float); a = G.nrm(np.asarray(axis, float))
    ref = G.nrm(np.cross(a, [0, 1.0, 0])) if abs(a[1]) < 0.9 else np.array([1.0, 0, 0])
    ref2 = np.cross(a, ref)
    nv = len(me.vertices)
    V = np.empty(nv * 3); me.vertices.foreach_get("co", V); V = V.reshape(-1, 3)
    nl = len(me.loops)
    lv = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
    np_ = len(me.polygons)
    st = np.empty(np_, np.int32); me.polygons.foreach_get("loop_start", st)
    tt = np.empty(np_, np.int32); me.polygons.foreach_get("loop_total", tt)
    D = V[lv] - o
    h = D @ a
    R = D - h[:, None] * a
    r = np.linalg.norm(R, axis=1)
    ang = np.arctan2(R @ ref2, R @ ref)
    fid = np.repeat(np.arange(np_), tt)
    amax = np.maximum.reduceat(ang, st); amin = np.minimum.reduceat(ang, st)
    wrap = (amax - amin) > math.pi
    ang = np.where(wrap[fid] & (ang < 0), ang + 2 * math.pi, ang)
    rm = np.maximum.reduceat(r, st)
    cap = np.zeros(np_, bool)
    # 端面(法線が軸方向)は平面投影
    Vf = V[lv]
    a0 = Vf[st]; a1 = Vf[st + 1]; a2 = Vf[st + np.minimum(2, tt - 1)]
    fn = G.nrm(np.cross(a1 - a0, a2 - a0))
    cap = np.abs(fn @ a) > 0.8
    u = np.where(cap[fid], R @ ref, h)
    v = np.where(cap[fid], R @ ref2, ang * np.maximum(rm[fid], 0.05))
    uv = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", (np.stack([u, v], 1) / UV_TILE).astype(np.float32).ravel())


def sori_g(t):
    return np.abs(t) ** P["sori_pow"]


def kasa_bot(x):
    """笠木下端(= 島木上端)の中心線 z(x)。中央から両端へ反り上がる。"""
    zb0 = P["H"] - P["kou_t"] - P["kasa_h"]
    return zb0 + P["kasa_sori_bot"] * sori_g(x / (P["kasa_L"] / 2))


def kasa_dz(x):
    h = 1e-4
    return (kasa_bot(x + h) - kasa_bot(x - h)) / (2 * h)


def curved_member(xs, prof, h_of_x, direction, flare=0.0):
    """反った横材: 基準線(笠木下端)から法線方向へ断面を立てる。端面は基準線に直交(反りに直交する木口)。

    prof: [(y, qa, qb)] -> 法線方向オフセット = qa*h(x) + qb (direction=+1 上へ / -1 下へ)。
    """
    rings = []
    for i, x in enumerate(xs):
        z = kasa_bot(x); m = kasa_dz(x)
        n = np.array([-m, 0.0, 1.0]) / math.hypot(1, m)
        tg = np.array([1.0, 0.0, m]) / math.hypot(1, m)
        h = h_of_x(x)
        Pp = np.array([x, 0.0, z])
        # 木口: 端の断面だけ、基準線からの高さに比例して外へ送る(上ほど外へ開く斜め切り)
        fl = flare * np.sign(x) if i in (0, len(xs) - 1) else 0.0
        ring = [Pp + n * direction * (qa * h + qb) + tg * fl * direction * (qa * h + qb) + np.array([0, y, 0])
                for (y, qa, qb) in prof]
        rings.append(ring)
    V = np.array(rings).reshape(-1, 3)
    k = len(prof); m_ = len(xs)
    F = G.grid_faces(m_, k, closed_c=True)
    Fl = [list(f) for f in F.tolist()]
    Fl.append(list(range(k))[::-1])
    Fl.append([(m_ - 1) * k + i for i in range(k)])
    return V, Fl


def xs_for(half, n=97):
    s = np.linspace(-1, 1, n)
    return half * np.sign(s) * np.abs(s) ** 0.85


def pillar_frame(side):
    """柱の軸: 柱脚 (side*S/2, 0, 0)、上で内側へ lean。返り値 (origin, axis)。"""
    th = math.radians(P["lean_deg"])
    return np.array([side * P["S"] / 2, 0, 0.0]), np.array([-side * math.sin(th), 0, math.cos(th)])


def axis_x_at(side, z):
    o, a = pillar_frame(side)
    return o[0] + a[0] / a[2] * z


def lathe_on_axis(profile, side, seg=40, cap_bottom=True, cap_top=True):
    """柱軸に沿う回転体。profile=[(r, 軸方向距離)]。"""
    V, F = G.lathe(profile, seg=seg, cap_bottom=cap_bottom, cap_top=cap_top)
    th = math.radians(P["lean_deg"]) * (-side)
    c, s = math.cos(th), math.sin(th)
    Rm = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    V = V @ Rm.T + np.array([side * P["S"] / 2, 0, 0])
    return V, F


def r_pillar(l):
    """柱の半径(軸方向距離 l)。"""
    return P["d"] / 2 - (P["d"] - P["d_top"]) / 2 * (l / 4.2)


# ------------------------------------------------------------------ build

def build():
    info = {}
    H = P["H"]
    kh = P["kasa_h"]
    half_k = P["kasa_L"] / 2
    half_s = P["shima_L"] / 2
    zb0 = kasa_bot(0.0)                       # 笠木下端(中央)
    zs_bot0 = zb0 - P["shima_h"]              # 島木下端(中央)
    nuki_top = zs_bot0 - P["nuki_gap"]
    nuki_bot = nuki_top - P["nuki_h"]
    info["heights"] = dict(kasagi_top_center=H, kasagi_bottom_center=zb0, shimaki_bottom_center=zs_bot0,
                           nuki_top=nuki_top, nuki_bottom=nuki_bot,
                           kasagi_end_top=float(kasa_bot(half_k) + kh + P["kasa_sori_add"] + P["kou_t"]))

    # --- 笠木 (反り増し: 成が端へ増す) ----------------------------------
    w = P["kasa_w"]; c = 0.018; c2 = 0.006
    prof_k = [(-w / 2 + c, 0, 0), (w / 2 - c, 0, 0), (w / 2, 0, c), (w / 2, 1, -c2), (w / 2 - c2, 1, 0),
              (-w / 2 + c2, 1, 0), (-w / 2, 1, -c2), (-w / 2, 0, c)]

    def kh_of(x):
        return kh + P["kasa_sori_add"] * sori_g(x / half_k)
    xk = xs_for(half_k)
    emit("Kasagi", G.MB().addt(curved_member(xk, prof_k, kh_of, +1, flare=0.35)), "Kasagi", "Kasagi")
    # 甲板(笠木上面の銅板): 笠木よりわずかに広く、上面に流れ(中央が高い)
    wk = w + 0.016; t = P["kou_t"]; cr = P["kou_crown"]
    prof_t = [(-wk / 2, 0, -0.004), (wk / 2, 0, -0.004), (wk / 2, 0, t - cr), (0.0, 0, t), (-wk / 2, 0, t - cr)]

    def base_of(x):
        return kh_of(x)
    xt = xs_for(half_k + 0.008)
    V, F = curved_member(xt, [(y, 1, q) for (y, _, q) in prof_t], base_of, +1, flare=0.35)
    emit("Kasagi_Kouita", G.MB().add(V, F), "Kasagi_Kouita", "Kasagi", smooth=50)

    # --- 島木 (笠木下端に沿う、下へ) -----------------------------------
    ws = P["shima_w"]; c = 0.012
    prof_s = [(-ws / 2, 0, 0), (ws / 2, 0, 0), (ws / 2, 1, -c), (ws / 2 - c, 1, 0), (-ws / 2 + c, 1, 0), (-ws / 2, 1, -c)]
    xsh = xs_for(half_s)
    emit("Shimaki", G.MB().addt(curved_member(xsh, prof_s, lambda x: P["shima_h"], -1, flare=0.30)), "Shimaki", "Kasagi")

    # --- 柱 (内転び・上すぼまり。柱頭は島木に差し込む) ------------------
    pil_info = []
    for side in (-1, 1):
        xa = axis_x_at(side, zs_bot0)
        zsb = kasa_bot(xa) - P["shima_h"] * 1.0 / math.hypot(1, kasa_dz(xa))   # 島木下端(柱心)
        top_z = zsb + 0.10                                                       # 枘差し 0.10
        th = math.radians(P["lean_deg"])
        Lp = top_z / math.cos(th)
        ls = np.linspace(0.05, Lp, 8)
        prof = [(r_pillar(l), l) for l in ls]
        V, F = lathe_on_axis(prof, side, seg=40)
        o, a = pillar_frame(side)
        nm = "Hashira_" + ("L" if side < 0 else "R")
        emit(nm, G.MB().add(V, F), "Hashira", "Hashira", smooth=60, uv_mode="triplanar", cyl=(o, a))
        pil_info.append(dict(side=side, top_z=top_z, shimaki_bottom_at_axis=float(zsb), axis_x_top=float(xa),
                             r_top=float(r_pillar(Lp))))

        # 根巻(黒い金属の巻き、上端に細い帯) ------------------------------
        nb_, nt_ = P["nemaki_bot"], P["nemaki_top"]
        t0 = P["nemaki_t"]
        prof = [(r_pillar(nb_) + t0, nb_), (r_pillar(nt_ - P["band_h"]) + t0, nt_ - P["band_h"]),
                (r_pillar(nt_) + t0 + P["band_t"], nt_ - P["band_h"]), (r_pillar(nt_) + t0 + P["band_t"], nt_),
                (r_pillar(nt_) + 0.001, nt_ + 0.004)]
        # 下端にも細い帯(亀腹の上に見える)
        zb_band = P["kame_h"] + 0.02
        prof = [(r_pillar(nb_) + t0, nb_), (r_pillar(zb_band) + t0, zb_band),
                (r_pillar(zb_band) + t0 + P["band_t"] * 0.8, zb_band + 0.004),
                (r_pillar(zb_band) + t0 + P["band_t"] * 0.8, zb_band + 0.024),
                (r_pillar(zb_band) + t0, zb_band + 0.028)] + prof[1:]
        V, F = lathe_on_axis(prof, side, seg=40, cap_bottom=False, cap_top=True)
        emit("Nemaki_" + ("L" if side < 0 else "R"), G.MB().add(V, F), "Nemaki", "Hashira", smooth=40,
             uv_mode="triplanar", cyl=(o, a))

        # 亀腹(白漆喰の饅頭形)。柱脚中心に鉛直 ------------------------------
        R0, hk = P["kame_r"], P["kame_h"]
        rp = r_pillar(hk) + 0.004
        tt = np.linspace(0, math.pi / 2, 12)
        prof = [(R0 + 0.01, 0.0), (R0, 0.025)]
        for a_ in tt[1:]:
            prof.append((rp + (R0 - rp) * math.cos(a_), 0.025 + (hk - 0.025) * math.sin(a_) ** 0.8))
        prof.append((rp - 0.03, hk))
        V, F = G.lathe(prof, center=(side * P["S"] / 2, 0, 0), seg=48, cap_bottom=False, cap_top=True)
        emit("Kamebara_" + ("L" if side < 0 else "R"), G.MB().add(V, F), "Kamebara", "Hashira", smooth=60,
             uv_mode="triplanar", cyl=((side * P["S"] / 2, 0, 0), (0, 0, 1)))
    info["pillars"] = pil_info

    # --- 貫 (直材、柱を貫通して外へ) -----------------------------------
    nl = P["nuki_L"] / 2
    zc = (nuki_top + nuki_bot) / 2
    V, F = G.beams([(-nl, 0, zc)], [(nl, 0, zc)], P["nuki_t"], P["nuki_h"], ch=0.008)
    emit("Nuki", G.MB().add(V, F), "Nuki", "Nuki")

    # --- 楔 (柱の外側、貫の溝に上から打ち込む。上下にわずかに出る) ----------
    mb = G.MB()
    kus = []
    for side in (-1, 1):
        xo = axis_x_at(side, zc) + side * r_pillar(zc)          # 柱の外面(貫の高さ)
        x_in = xo - side * 0.004
        x_out = xo + side * P["kusabi_w"]
        z0 = nuki_bot - P["kusabi_dn"]; z1 = nuki_top + P["kusabi_up"]
        ty = P["kusabi_t"] / 2
        # 上が厚い楔(外面が傾く)
        xo_b = xo + side * P["kusabi_w"] * 0.70
        xs4 = [(x_in, z0), (xo_b, z0), (x_out, z1), (x_in, z1)]
        Vk = []
        for y in (-ty, ty):
            for (x_, z_) in xs4:
                Vk.append((x_, y, z_))
        Fk = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
        mb.add(np.array(Vk), Fk)
        kus.append(dict(side=side, pillar_outer_x=float(xo), inner_x=float(x_in)))
    emit("Kusabi", mb, "Kusabi", "Nuki", smooth=0)
    info["kusabi"] = kus

    # --- 額束 -------------------------------------------------------------
    gw, gt = P["gaku_w"], P["gaku_t"]
    V, F = G.box((-gw / 2, -gt / 2, nuki_top - 0.03), (gw / 2, gt / 2, zs_bot0 + 0.03))
    emit("Gakuzuka", G.MB().add(V, F), "Gakuzuka", "Nuki", smooth=0)

    # --- 扁額 (額縁 + 地板 + 金文字「八幡宮」) ---------------------------
    hw, hh, fr, ht = P["hen_w"], P["hen_h"], P["hen_frame"], P["hen_t"]
    hz_top = zs_bot0 - 0.025
    hz_bot = hz_top - hh
    hz_c = (hz_top + hz_bot) / 2
    y_back = -gt / 2 - 0.002            # 額束の前面に掛ける(掛け金具は省略、2mm の目地)
    yc = y_back - ht / 2
    outer = G.rect_profile(hw, hh)
    inner = G.rect_profile(hw - 2 * fr, hh - 2 * fr)
    frame = (np.array([0, yc, hz_c]), np.array([1.0, 0, 0]), np.array([0, 0, 1.0]))
    V, F = G.extrude_poly(outer, ht, frame, holes=[inner], bevel=0.008)
    emit("Hengaku_Frame", G.MB().add(V, F), "Hengaku_Frame", "Hengaku", smooth=30)
    bt = 0.026
    yb = y_back - bt / 2 - 0.004
    V, F = G.box((-(hw / 2 - fr) - 0.002, yb - bt / 2, hz_bot + fr - 0.002), ((hw / 2 - fr) + 0.002, yb + bt / 2, hz_top - fr + 0.002))
    emit("Hengaku_Board", G.MB().add(V, F), "Hengaku_Board", "Hengaku", smooth=0)
    y_face = yb - bt / 2
    moji_text(["八", "幡", "宮"], hz_bot + fr, hz_top - fr, y_face, hw - 2 * fr)
    info["hengaku"] = dict(top=hz_top, bottom=hz_bot, y_back=y_back)
    return info


def moji_text(chars, z0, z1, y_face, width):
    font = bpy.data.fonts.load(FONT) if os.path.exists(FONT) else None
    n = len(chars)
    pitch = (z1 - z0) / n
    size = min(pitch * 0.92, width * 0.82)
    mb = G.MB()
    for i, ch in enumerate(chars):
        cu = bpy.data.curves.new("moji_%d" % i, "FONT")
        cu.body = ch
        if font:
            cu.font = font
        cu.size = size
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.extrude = 0.004
        cu.resolution_u = 4
        ob = bpy.data.objects.new("moji_%d" % i, cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(me); bm.free()
        nv = len(me.vertices)
        Vt = np.empty(nv * 3); me.vertices.foreach_get("co", Vt); Vt = Vt.reshape(-1, 3)
        Ft = [list(p.vertices) for p in me.polygons]
        zc = z1 - pitch * (i + 0.5)
        # 文字は XY 面・+Z 押出し -> 正面(-Y)を向くよう X-Z 面へ
        W = np.stack([Vt[:, 0], y_face + 0.0005 - (Vt[:, 2] + 0.004), Vt[:, 1] + zc], 1)
        mb.add(W, Ft)
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)
    emit("Hengaku_Moji", mb, "Hengaku_Moji", "Hengaku", smooth=0, uv_mode="triplanar")


# ------------------------------------------------------------------ checks

def bvh_of(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def check(info):
    """取合いの数値検査(浮き・めり込み)。"""
    res = {}
    pz = info["pillars"]
    res["pillar_tenon_into_shimaki_m"] = [round(p["top_z"] - p["shimaki_bottom_at_axis"], 4) for p in pz]
    res["pillar_r_top_vs_shimaki_half_w_m"] = [round(pz[0]["r_top"], 4), P["shima_w"] / 2]
    res["kasagi_bottom_eq_shimaki_top"] = "shared reference curve (gap 0)"
    res["kusabi_inner_vs_pillar_face_m"] = [round(abs(k["inner_x"] - k["pillar_outer_x"]), 4) for k in info["kusabi"]]
    nl = P["nuki_L"] / 2
    res["nuki_out_from_pillar_axis_m"] = round(nl - abs(axis_x_at(1, info["heights"]["nuki_top"])), 3)
    res["nuki_out_from_pillar_face_m"] = round(nl - abs(axis_x_at(1, info["heights"]["nuki_top"])) - r_pillar(3.3), 3)
    h = info["hengaku"]
    res["hengaku_top_below_shimaki_m"] = round(info["heights"]["shimaki_bottom_center"] - h["top"], 3)
    res["hengaku_back_gap_to_gakuzuka_face_m"] = round(-P["gaku_t"] / 2 - h["y_back"], 4)
    res["hengaku_bottom_above_nuki_top_m"] = round(h["bottom"] - info["heights"]["nuki_top"], 3)
    # BVH: 交差するオブジェクト対(想定内の差込み・貫通のみであること)と、どれとも接しない(浮いた)オブジェクト
    obs = [o for o in bpy.data.objects if o.type == "MESH"]
    T = {o.name: bvh_of(o) for o in obs}
    pairs = []
    for i, a in enumerate(obs):
        for b in obs[i + 1:]:
            if T[a.name].overlap(T[b.name]):
                pairs.append("%s x %s" % (a.name, b.name))
    res["intersecting_pairs"] = pairs
    # 浮き: 各オブジェクトの頂点から他オブジェクトへの最短距離の最小値
    floating = {}
    for a in obs:
        Va = [a.matrix_world @ v.co for v in a.data.vertices]
        best = 1e9
        for b in obs:
            if b is a:
                continue
            for v in Va[:: max(1, len(Va) // 400)]:
                f = T[b.name].find_nearest(v)
                if f[0] is not None:
                    best = min(best, f[3])
        floating[a.name] = round(best, 4)
    res["min_dist_to_other_m"] = floating
    return res


# ------------------------------------------------------------------ finishing / export

def fix_normals():
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()


def assign_finishes():
    for ob in bpy.data.objects:
        if ob.type != "MESH" or "part" not in ob:
            continue
        nu, ish = FIN[ob["part"]]
        for nm in (nu, ish):
            mat(nm).use_fake_user = True
        ob["finish_mats"] = json.dumps({"nuri": [nu], "ishi": [ish]})


def setup_gltf_variants(tiles):
    bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    sc = bpy.context.scene
    vs = sc.gltf2_KHR_materials_variants_variants
    vs.clear()
    for i, f in enumerate(FINISHES):
        v = vs.add()
        v.variant_idx = i
        v.name = f["id"]
    n_var = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH" or "finish_mats" not in ob:
            continue
        fm = json.loads(ob["finish_mats"])
        me = ob.data
        me.materials[0] = M2.glb_material2(fm[FINISHES[0]["id"]][0], tiles)
        me.gltf2_variant_mesh_data.clear()
        groups = {}
        for i, f in enumerate(FINISHES):
            groups.setdefault(fm[f["id"]][0], []).append(i)
        if len(groups) == 1:
            continue
        for mname, idxs in groups.items():
            d = me.gltf2_variant_mesh_data.add()
            d.material_slot_index = 0
            d.material = M2.glb_material2(mname, tiles)
            for i in idxs:
                vv = d.variants.add()
                vv.variant.variant_idx = i
        n_var += 1
    return n_var


def find_gltf_transform():
    for c in (os.environ.get("GLTF_TRANSFORM"), shutil.which("gltf-transform")):
        if c and os.path.exists(c):
            return c
    return None


def export_glb(path, image_format="AUTO"):
    kw = dict(filepath=path, export_format="GLB", export_yup=True, export_apply=True,
              export_image_format=image_format, export_texcoords=True, export_normals=True,
              export_materials="EXPORT", export_cameras=False, export_lights=False)
    bpy.ops.export_scene.gltf(**kw)


def export_all(out, size):
    t0 = time.time()
    tiles = M2.bake_tiles2([n for n in BAKE if n in bpy.data.materials], os.path.join(out, "textures"),
                           size=size, uv_tile=UV_TILE)
    print("baked %d materials in %.1fs" % (len(tiles), time.time() - t0), flush=True)
    nvar = setup_gltf_variants(tiles)
    full = os.path.join(out, "haiden.glb")
    export_glb(full, "AUTO")
    web = os.path.join(out, "haiden_web.glb")
    gt = find_gltf_transform()
    ok = False
    if gt:
        tmp = os.path.join(out, "_web_tmp.glb")
        r = subprocess.run([gt, "webp", full, tmp, "--quality", "82"], capture_output=True, text=True)
        print(r.stdout[-300:], r.stderr[-300:])
        if r.returncode == 0:
            r = subprocess.run([gt, "draco", tmp, web, "--method", "edgebreaker"], capture_output=True, text=True)
            print(r.stdout[-300:], r.stderr[-300:])
            ok = r.returncode == 0
        if os.path.exists(tmp):
            os.remove(tmp)
    if not ok:
        export_glb(web, "JPEG")
    return {"texture_size": size, "textured_materials": sorted(tiles), "variant_meshes": nvar,
            "glb_bytes": os.path.getsize(web), "glb_full_bytes": os.path.getsize(full),
            "web_draco": ok, "web_textures": "webp" if ok else "jpeg"}


def scene_stats():
    tris = verts = objs = 0
    mats = set()
    mn = np.full(3, 1e9); mx = np.full(3, -1e9)
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        me = ob.data
        me.calc_loop_triangles()
        tris += len(me.loop_triangles); verts += len(me.vertices); objs += 1
        for m in me.materials:
            if m:
                mats.add(m.name)
        V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", V); V = V.reshape(-1, 3)
        mn = np.minimum(mn, V.min(0)); mx = np.maximum(mx, V.max(0))
    return tris, verts, objs, sorted(mats), mn, mx


def main():
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="T-1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-glb", action="store_true")
    ap.add_argument("--tex-size", type=int, default=1024)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    vpath = os.path.join(HERE, "variants", "%s.json" % a.variant)
    with open(vpath, encoding="utf-8") as f:
        V = json.load(f)
    P.update(V.get("params", {}))
    out = os.path.abspath(a.out or os.path.join("haiden", "out", a.variant))
    os.makedirs(out, exist_ok=True)
    t0 = time.time()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    ROOT = bpy.data.collections.new("Torii")
    sc.collection.children.link(ROOT)

    info = build()
    fix_normals()
    assign_finishes()
    chk = check(info)
    tris, verts, objs, mats, mn, mx = scene_stats()
    print("built: %d tris, %d verts, %d objects in %.1fs" % (tris, verts, objs, time.time() - t0))
    print(json.dumps(chk, ensure_ascii=False, indent=1))

    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "haiden.blend"), compress=True)

    stats = {
        "id": V["id"], "name": V["name"], "version": V.get("version", "ver1"), "seq": V.get("seq", 0),
        "category": V.get("category", "torii"), "category_name": V.get("category_name", "鳥居"),
        "title": V.get("title", ""),
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tris": tris, "triangles": tris, "vertices": verts, "objects": objs,
        "materials": len(mats), "material_names": mats,
        "dimensions_m": {"width_x": round(float(mx[0] - mn[0]), 3), "depth_y": round(float(mx[1] - mn[1]), 3),
                         "height_z": round(float(mx[2] - mn[2]), 3)},
        "torii": {"pillar_span_m": P["S"], "pillar_dia_m": P["d"], "lean_deg": P["lean_deg"],
                  "kasagi_length_m": P["kasa_L"], "shimaki_length_m": P["shima_L"], "nuki_length_m": P["nuki_L"]},
        "heights_m": {k: round(float(v), 3) for k, v in info["heights"].items()},
        "checks": chk,
        "finishes": FINISHES, "finish_mode": "khr_variants", "uv_mode": "grain",
        "renders": [],
    }
    if not a.no_glb:
        stats.update(export_all(out, a.tex_size))
    sp = os.path.join(out, "stats.json")
    if os.path.exists(sp):
        try:
            prev = json.load(open(sp, encoding="utf-8"))
            if prev.get("id") == V["id"]:
                stats["renders"] = prev.get("renders", [])
                for k in ("render_quality", "render_seconds"):
                    if k in prev:
                        stats[k] = prev[k]
        except Exception:
            pass
    stats["build_seconds"] = round(time.time() - t0, 1)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
