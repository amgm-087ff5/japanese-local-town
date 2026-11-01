#!/usr/bin/env python3
"""L-1 春日灯籠 (六角石灯籠) builder. 仕様は haiden/docs/assets.md、形の根拠は research_toro.md + 一般的な春日灯籠の構成。

    python3 haiden/blender/assets/build_toro.py --variant L-1 --out haiden/out/L-1

上から 宝珠・請花 / 笠(六角・降棟・蕨手) / 火袋(火口2面・鹿2面・日月) / 中台(請花・格狭間) /
竿(上中下の節) / 基礎(格狭間・反花) / 基壇。各部は別の石(別オブジェクト)として積む。
原点 = 地面の竿中心、Z 上、正面 = -Y (火口が正面と背面)。

材質 (KHR_materials_variants): shin=御影石 / koshoku=古色。
  - 御影石: numpy で作る周期タイル (base / metallicRoughness / normal 1K、UVMap = 石の目に沿う grain UV)。
  - 古色: 全体アトラス (UVAtlas) に焼き込み。上向き面の苔・雨だれの筋・彫りの凹部の暗さ・黄ばみ。
  - AO はアトラスに焼き、御影石の occlusionTexture (TEXCOORD_1) に使う。
出力: <out>/haiden.blend, haiden.glb, haiden_web.glb (gltf-transform があれば WebP + Draco), stats.json, textures/
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

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
from mathutils.geometry import tessellate_polygon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TAN30 = math.tan(math.pi / 6)
COS30 = math.cos(math.pi / 6)

# ============================================================== dimensions (m)
# 全高 2.10。高さ配分(要確認値): 基壇0.11 基礎0.23 竿0.70 中台0.15 火袋0.33 笠0.26 請花+宝珠0.32
D = dict(
    kidan=(0.00, 0.11), kiso=(0.11, 0.34), sao=(0.34, 1.04), chudai=(1.04, 1.19),
    hibukuro=(1.19, 1.52), kasa=(1.52, 1.78), hoju=(1.78, 2.10),
    a_kidan=0.36,      # 基壇 apothem (対辺/2)
    a_kiso=0.27,       # 基礎
    r_sao=0.140,       # 竿 半径 (径0.28 = 笠対角幅0.72 の約0.39)
    a_chudai=0.24,
    a_hib=0.155, a_hib_in=0.118,
    a_kasa=0.312,      # 笠 軒 apothem (対角幅 0.72 = 全高の0.34)
)


# ============================================================== mesh builder
class MB:
    def __init__(self):
        self.V = []
        self.F = []
        self.n = 0

    def add(self, V, F):
        V = np.asarray(V, float).reshape(-1, 3)
        self.V.append(V)
        self.F.extend([[int(i) + self.n for i in f] for f in F])
        self.n += len(V)
        return self

    def addt(self, VF):
        return self.add(*VF)


def grid_faces(nr, nc, closed=False):
    F = []
    cols = nc if closed else nc - 1
    for r in range(nr - 1):
        for c in range(cols):
            c2 = (c + 1) % nc
            F.append([r * nc + c, r * nc + c2, (r + 1) * nc + c2, (r + 1) * nc + c])
    return F


def loft(rings, cap0=True, cap1=True):
    """rings: list of (m,3) closed CCW rings (same m). Quads between consecutive rings + fan caps."""
    R = np.asarray(rings, float)
    nr, m = R.shape[0], R.shape[1]
    V = R.reshape(-1, 3)
    F = grid_faces(nr, m, closed=True)
    extra = []
    if cap0:
        c = R[0].mean(0)
        extra.append(c)
        ci = len(V)
        F += [[ci, (j + 1) % m, j] for j in range(m)]
    if cap1:
        c = R[-1].mean(0)
        ci = len(V) + len(extra)
        extra.append(c)
        base = (nr - 1) * m
        F += [[ci, base + j, base + (j + 1) % m] for j in range(m)]
    if extra:
        V = np.vstack([V, np.array(extra)])
    return V, F


def lathe(prof, seg=64, cap0=True, cap1=True, phase=0.0):
    """prof [(r, z)...] bottom -> top, revolved around Z."""
    t = phase + np.linspace(0, 2 * np.pi, seg, endpoint=False)
    rings = [np.stack([r * np.cos(t), r * np.sin(t), np.full(seg, z)], 1) for r, z in prof]
    return loft(rings, cap0 and prof[0][0] > 1e-6, cap1 and prof[-1][0] > 1e-6)


def catmull(P, n_per=6):
    """Smooth a polyline (Catmull-Rom), keeps end points."""
    P = np.asarray(P, float)
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        for t in np.linspace(0, 1, n_per, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-1])
    return np.array(out)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------- hexagon helpers
# corners at angles k*60deg (k=0..5) -> a face normal points to -Y (face 4) = 正面, face 1 = 背面
def corner(k, a):
    th = math.radians(60 * (k % 6))
    return np.array([math.cos(th), math.sin(th)]) * a / COS30


def face_frame(k, a):
    """(origin xy at the face centre, tangent t (CCW = right as seen from outside), outward n)."""
    ph = math.radians(60 * k + 30)
    n = np.array([math.cos(ph), math.sin(ph)])
    t = np.array([-math.sin(ph), math.cos(ph)])
    return (n * a, t, n)


def hex_ring(a, cham, z):
    """12 points: after corner k, before corner k+1 ... (chamfered hexagon), CCW."""
    pts = []
    for k in range(6):
        c0, c1 = corner(k, a), corner(k + 1, a)
        e = (c1 - c0) / np.linalg.norm(c1 - c0)
        pts.append(c0 + e * cham)
        pts.append(c1 - e * cham)
    P = np.array(pts)
    return np.column_stack([P, np.full(12, z)])


def P3(frame, x, z, d):
    o, t, n = frame
    return np.array([o[0] + t[0] * x + n[0] * d, o[1] + t[1] * x + n[1] * d, z])


def area2(P):
    P = np.asarray(P)
    x, y = P[:, 0], P[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def ccw(P):
    P = np.asarray(P, float)
    return P if area2(P) > 0 else P[::-1].copy()


def tess(loops):
    return tessellate_polygon([[Vector((float(p[0]), float(p[1]), 0.0)) for p in L] for L in loops])


def face_with_holes(mb, frame, outer, holes, sign=1.0):
    """Planar face (local x along t, y = world z) at d=0 with holes, + recess walls/floors.

    holes: dicts {pts (CCW), depth, floor: None|'flat'|'grid', grid: (xs, zs, H) heights (m, outward)}
    sign: +1 the face looks along +n, -1 along -n (inner wall of a hollow).
    """
    loops = [ccw(outer)] + [ccw(h["pts"]) for h in holes]
    pts2 = np.concatenate(loops)
    V = [P3(frame, x, z, 0.0) for x, z in pts2]
    F = []
    for a, b, c in tess(loops):
        ar = (pts2[b][0] - pts2[a][0]) * (pts2[c][1] - pts2[a][1]) - (pts2[b][1] - pts2[a][1]) * (pts2[c][0] - pts2[a][0])
        F.append([a, b, c] if ar * sign > 0 else [a, c, b])
    mb.add(V, F)
    for h, L in zip(holes, loops[1:]):
        dep = h["depth"]
        fl = h.get("floor", "flat")
        hf = h.get("hfun")

        def dz(x, z):
            return -dep + (hf(x, z) if hf is not None else 0.0)
        m = len(L)
        top = [P3(frame, x, z, 0.0) for x, z in L]
        bot = [P3(frame, x, z, dz(x, z)) for x, z in L]
        WF = []
        for i in range(m):
            j = (i + 1) % m
            # CCW hole: interior on the left; wall normal points to the hole interior (away from the solid)
            WF.append([i, m + i, m + j, j] if sign > 0 else [i, j, m + j, m + i])
        mb.add(top + bot, WF)
        if fl == "flat":
            FV = [P3(frame, x, z, -dep) for x, z in L]
            FF = []
            for a, b, c in tess([L]):
                FF.append([a, b, c] if sign > 0 else [a, c, b])
            mb.add(FV, FF)
        elif fl == "grid":
            xs, zs = h["xs"], h["zs"]
            nx, nz = len(xs), len(zs)
            GV = [P3(frame, x, z, dz(x, z)) for z in zs for x in xs]
            GF = []
            for r in range(nz - 1):
                for c in range(nx - 1):
                    q = [r * nx + c, r * nx + c + 1, (r + 1) * nx + c + 1, (r + 1) * nx + c]
                    GF.append(q if sign > 0 else q[::-1])
            mb.add(GV, GF)


def rect_loop(x0, x1, z0, z1, xs=None, zs=None):
    """CCW rectangle boundary; with xs/zs the edges are subdivided like a grid."""
    if xs is None:
        return np.array([[x0, z0], [x1, z0], [x1, z1], [x0, z1]])
    b = [(x, z0) for x in xs[:-1]] + [(x1, z) for z in zs[:-1]] + [(x, z1) for x in xs[::-1][:-1]] + \
        [(x0, z) for z in zs[::-1][:-1]]
    return np.array(b)


def paneled_band(mb, a, cham, z0, z1, panel):
    """Vertical faces of a chamfered hex prism between z0 and z1. panel(k, hw) -> list of hole dicts."""
    hw = a * TAN30 - cham
    for k in range(6):
        fr = face_frame(k, a)
        outer = rect_loop(-hw, hw, z0, z1)
        face_with_holes(mb, fr, outer, panel(k, hw))
    r0, r1 = hex_ring(a, cham, z0), hex_ring(a, cham, z1)
    F = []
    for k in range(6):     # chamfer quads at corner k+1: idx 2k+1 -> 2k+2
        i, j = 2 * k + 1, (2 * k + 2) % 12
        F.append([i, j, 12 + j, 12 + i])
    mb.add(np.vstack([r0, r1]), F)


# ============================================================== 2D art (格狭間, 浮彫, 蓮弁)
def bez(p0, p1, p2, p3, n):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = map(np.asarray, (p0, p1, p2, p3))
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3


def koza_outline(w, h, n=9):
    """格狭間: closed CCW outline, x in [-w/2, w/2], y in [0, h]."""
    segs = [
        ((0.0, 0.0), (0.3, 0.0), (0.6, 0.0), (0.78, 0.0)),
        ((0.78, 0.0), (0.88, 0.0), (0.97, 0.06), (0.95, 0.17)),
        ((0.95, 0.17), (0.93, 0.26), (0.84, 0.30), (0.86, 0.42)),
        ((0.86, 0.42), (0.88, 0.56), (1.0, 0.60), (0.96, 0.72)),
        ((0.96, 0.72), (0.93, 0.82), (0.80, 0.80), (0.72, 0.76)),
        ((0.72, 0.76), (0.66, 0.86), (0.52, 0.90), (0.40, 0.84)),
        ((0.40, 0.84), (0.30, 0.80), (0.18, 0.86), (0.12, 0.93)),
        ((0.12, 0.93), (0.07, 0.98), (0.03, 1.0), (0.0, 1.0)),
    ]
    pts = []
    for s in segs:
        pts.extend(bez(*s, n)[:-1])
    pts.append((0.0, 1.0))
    right = np.array(pts)
    left = right[::-1].copy()
    left[:, 0] *= -1
    P = np.concatenate([right, left[1:-1]])
    keep = [0]
    for i in range(1, len(P)):
        if np.linalg.norm(P[i] - P[keep[-1]]) > 1e-4:
            keep.append(i)
    P = P[keep]
    P[:, 0] *= w / 2
    P[:, 1] *= h
    return P


def sd_circle(x, y, cx, cy, r):
    return np.hypot(x - cx, y - cy) - r


def sd_ellipse(x, y, cx, cy, rx, ry, rot=0.0):
    c, s = np.cos(rot), np.sin(rot)
    dx, dy = x - cx, y - cy
    u = (dx * c + dy * s) / rx
    v = (-dx * s + dy * c) / ry
    return (np.hypot(u, v) - 1.0) * min(rx, ry)


def sd_capsule(x, y, ax, ay, bx, by, ra, rb=None):
    rb = ra if rb is None else rb
    px, py = x - ax, y - ay
    vx, vy = bx - ax, by - ay
    h = np.clip((px * vx + py * vy) / (vx * vx + vy * vy), 0, 1)
    return np.hypot(px - vx * h, py - vy * h) - (ra + (rb - ra) * h)


def sd_chain(x, y, pts, ra, rb=None):
    rb = ra if rb is None else rb
    n = len(pts) - 1
    d = np.full(np.shape(x), 1e9)
    for i in range(n):
        r0 = ra + (rb - ra) * i / n
        r1 = ra + (rb - ra) * (i + 1) / n
        d = np.minimum(d, sd_capsule(x, y, *pts[i], *pts[i + 1], r0, r1))
    return d


def smin(a, b, k=0.04):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def dome(d, r=0.07):
    t = np.clip(-d / r, 0, 1)
    return np.sqrt(1 - (1 - t) ** 2)


def cloud(x, y, cx, cy, s, flip=False):
    """瑞雲: three lobes + trailing tail; groove = curl inside the main lobe."""
    f = -1 if flip else 1
    d = sd_circle(x, y, cx, cy, 0.15 * s)
    d = smin(d, sd_circle(x, y, cx + f * 0.19 * s, cy + 0.06 * s, 0.18 * s))
    d = smin(d, sd_circle(x, y, cx + f * 0.38 * s, cy - 0.01 * s, 0.13 * s))
    d = smin(d, sd_chain(x, y, [(cx - f * 0.05 * s, cy - 0.1 * s), (cx - f * 0.30 * s, cy - 0.15 * s),
                                (cx - f * 0.52 * s, cy - 0.09 * s)], 0.07 * s, 0.02 * s))
    g = np.abs(sd_circle(x, y, cx + f * 0.19 * s, cy + 0.06 * s, 0.085 * s)) - 0.014
    return d, g


def art(kind, x, y):
    """Relief height 0..1 on a panel, x in [-0.75, 0.75], y in [-1, 1] (normalised by half height)."""
    if kind == "oshika":       # 雄鹿: 立ち姿、首を上げ角を持つ (右向き)
        x = x * 1.08 + 0.02
        body = sd_ellipse(x, y, -0.05, -0.12, 0.46, 0.20, 0.05)
        neck = sd_capsule(x, y, 0.28, -0.02, 0.48, 0.34, 0.13, 0.085)
        head = sd_ellipse(x, y, 0.59, 0.40, 0.15, 0.075, -0.45)
        ear = sd_ellipse(x, y, 0.47, 0.52, 0.075, 0.032, 0.6)
        tail = sd_ellipse(x, y, -0.51, 0.0, 0.06, 0.035, 0.7)
        near = smin(smin(smin(smin(body, neck, 0.08), head, 0.05), tail, 0.03), ear, 0.02)
        legs_n = np.minimum(sd_chain(x, y, [(0.27, -0.20), (0.32, -0.55), (0.31, -0.86)], 0.065, 0.032),
                            sd_chain(x, y, [(-0.34, -0.18), (-0.26, -0.50), (-0.34, -0.86)], 0.09, 0.032))
        near = smin(near, legs_n, 0.05)
        legs_f = np.minimum(sd_chain(x, y, [(0.15, -0.22), (0.11, -0.55), (0.09, -0.86)], 0.055, 0.03),
                            sd_chain(x, y, [(-0.46, -0.18), (-0.38, -0.50), (-0.48, -0.86)], 0.075, 0.03))
        ant = np.minimum.reduce([
            sd_chain(x, y, [(0.51, 0.48), (0.45, 0.66), (0.36, 0.84), (0.25, 0.95)], 0.036, 0.020),
            sd_chain(x, y, [(0.46, 0.64), (0.60, 0.76), (0.65, 0.90)], 0.028, 0.017),
            sd_chain(x, y, [(0.39, 0.80), (0.47, 0.94)], 0.026, 0.016),
            sd_chain(x, y, [(0.45, 0.52), (0.33, 0.62), (0.22, 0.73)], 0.028, 0.017),
        ])
        h = np.maximum(dome(near, 0.09), 0.6 * dome(legs_f, 0.04))
        h = np.maximum(h, 0.8 * dome(ant, 0.025))
        h = h - 0.3 * (sd_circle(x, y, 0.58, 0.44, 0.026) < 0)
        ground = sd_chain(x, y, [(-0.75, -0.9), (-0.3, -0.87), (0.4, -0.9), (0.75, -0.88)], 0.035)
        h = np.maximum(h, 0.35 * dome(ground, 0.03))
        return np.clip(h, 0, 1)
    if kind == "meshika":      # 雌鹿: 脚を折って伏せ、首を上げる (左向き)
        x = x * 1.08
        body = sd_ellipse(x, y, 0.08, -0.42, 0.50, 0.24, -0.04)
        neck = sd_capsule(x, y, -0.23, -0.30, -0.40, 0.06, 0.15, 0.09)
        head = sd_ellipse(x, y, -0.53, 0.14, 0.16, 0.08, 0.4)
        ear = sd_ellipse(x, y, -0.38, 0.27, 0.08, 0.032, -0.7)
        tail = sd_ellipse(x, y, 0.58, -0.30, 0.06, 0.035, -0.6)
        near = smin(smin(smin(smin(body, neck, 0.08), head, 0.05), ear, 0.02), tail, 0.03)
        fold = np.minimum(sd_chain(x, y, [(-0.25, -0.58), (-0.46, -0.66), (-0.60, -0.62)], 0.05, 0.034),
                          sd_chain(x, y, [(0.40, -0.55), (0.25, -0.68), (0.0, -0.70)], 0.065, 0.034))
        h = np.maximum(dome(near, 0.09), 0.75 * dome(fold, 0.03))
        h = h - 0.3 * (sd_circle(x, y, -0.53, 0.18, 0.026) < 0)
        for (sx, sy) in [(0.1, -0.30), (0.28, -0.32), (-0.05, -0.29), (0.42, -0.36), (0.18, -0.40)]:
            h = h - 0.14 * (sd_circle(x, y, sx, sy, 0.035) < 0) * (near < -0.02)
        ground = sd_chain(x, y, [(-0.75, -0.86), (0.0, -0.84), (0.75, -0.86)], 0.035)
        h = np.maximum(h, 0.35 * dome(ground, 0.03))
        for gx in (-0.66, 0.68):
            for dx in (-0.05, 0.0, 0.05):
                h = np.maximum(h, 0.5 * dome(sd_capsule(x, y, gx, -0.84, gx + dx * 1.6, -0.64 + abs(dx), 0.026, 0.01), 0.014))
        return np.clip(h, 0, 1)
    if kind == "hi":           # 日: 円相 + 雲
        disc = sd_circle(x, y, 0.0, 0.32, 0.40)
        h = dome(disc, 0.06) * 0.9
        rim = np.abs(sd_circle(x, y, 0.0, 0.32, 0.32)) - 0.028
        h = h + 0.1 * dome(rim, 0.02)
        c1, g1 = cloud(x, y, -0.30, -0.45, 0.95)
        c2, g2 = cloud(x, y, 0.30, -0.68, 0.75, flip=True)
        hc = 0.7 * np.maximum(dome(c1, 0.05) - 0.3 * (g1 < 0), dome(c2, 0.05) - 0.3 * (g2 < 0))
        return np.clip(np.maximum(h, hc), 0, 1)
    if kind == "tsuki":        # 月: 三日月 + 雲
        d = np.maximum(sd_circle(x, y, -0.05, 0.32, 0.40), -sd_circle(x, y, 0.14, 0.44, 0.34))
        h = dome(d, 0.05)
        c1, g1 = cloud(x, y, 0.28, -0.40, 0.95, flip=True)
        c2, g2 = cloud(x, y, -0.30, -0.68, 0.75)
        hc = 0.7 * np.maximum(dome(c1, 0.05) - 0.3 * (g1 < 0), dome(c2, 0.05) - 0.3 * (g2 < 0))
        return np.clip(np.maximum(h, hc), 0, 1)
    raise KeyError(kind)


def petal_w(s):
    """蓮弁の半幅 (0..1) along s in [0,1]: rounded body, pointed tip at s=1."""
    s = np.clip(s, 0, 1)
    body = np.sin(np.pi * s ** 0.75) ** 0.6
    pointed = np.clip((1.0 - s) / 0.35, 0, 1) ** 0.55
    return np.maximum(body * np.minimum(1.0, 0.25 + pointed), 0.035)


def petal_ring(mb, n, prof, T, phase=0.0, span=0.96, s0=0.0, curl=0.0, ns=16, nu=11, embed=0.003, base_w=1.0,
               s1=1.0, zmin=None):
    """n lotus petals, each a closed solid lying on a revolved core surface.

    prof(s) -> (r, z) on the core meridian, s=0 base, s=1 tip. The outward normal of the
    meridian is taken to the side away from the axis/up (rotated tangent).
    """
    ss = np.linspace(s0, s1, ns)
    us = np.linspace(-1, 1, nu)
    eps = 1e-3
    for k in range(n):
        phc = phase + 2 * np.pi * k / n
        rings = []
        for s in ss:
            r, z = prof(s)
            r2, z2 = prof(min(1.0, s + eps)) if s < 1 - eps else prof(s)
            r1, z1 = prof(max(0.0, s - eps)) if s > eps else prof(s)
            tr, tz = r2 - r1, z2 - z1
            L = math.hypot(tr, tz) or 1.0
            nr, nz = tz / L, -tr / L          # tangent rotated -90deg
            if nr < 0 or (abs(nr) < 1e-6 and nz < 0):
                nr, nz = -nr, -nz
            w = petal_w(s / s1) * base_w
            hs = span * np.pi / n * w
            env = smoothstep(0.0, 0.18, s) * (1.0 - 0.35 * smoothstep(0.85, 1.0, s / s1)) * 0.85 + 0.15
            lift = curl * smoothstep(0.72, 1.0, s / s1) ** 2
            top, bot = [], []
            for u in us:
                au = abs(u)
                th = T * env * (0.7 * math.sqrt(max(0.0, 1 - au * au)) + 0.18 * (1 - au) + 0.12)
                th += 0.28 * T * env * math.exp(-((au - 0.80) / 0.09) ** 2)      # 覆輪 (raised rim)
                ph = phc + u * hs
                c, sn = math.cos(ph), math.sin(ph)
                dn = th + lift
                top.append((((r + nr * dn) * c), ((r + nr * dn) * sn), z + nz * dn))
                db = -embed + lift
                bot.append((((r + nr * db) * c), ((r + nr * db) * sn), z + nz * db))
            R_ = np.array(top + bot[::-1])
            if zmin is not None:
                R_[:, 2] = np.maximum(R_[:, 2], zmin)
            rings.append(R_)
        V, F = loft(rings, cap0=True, cap1=True)
        mb.add(V, F)


# ============================================================== parts
def part_kidan():
    """基壇: 低い六角の台石。上端に小さな面取り。"""
    a, (z0, z1) = D["a_kidan"], D["kidan"]
    ch = 0.014
    rings = [hex_ring(a, ch, z0), hex_ring(a, ch, z1 - 0.010), hex_ring(a - 0.010, ch * 0.7, z1)]
    return MB().addt(loft(rings))


def part_kiso():
    """基礎: 六角の台(側面に格狭間) + 反花(下向きの蓮弁 12 + 間弁) + 竿を受ける円座。"""
    a, (z0, z3) = D["a_kiso"], D["kiso"]
    mb = MB()
    ch = 0.010
    zb, zt = z0 + 0.006, 0.224
    loft_lo = [hex_ring(a - 0.006, ch * 0.6, z0), hex_ring(a, ch, zb)]
    V, F = loft(loft_lo, cap0=True, cap1=False)
    mb.add(V, F)
    kw, kh = 0.235, 0.072
    K = koza_outline(kw, kh) + np.array([0.0, 0.140])

    def panel(k, hw):
        return [dict(pts=K, depth=0.012, floor="flat")]
    paneled_band(mb, a, ch, zb, zt, panel)
    V, F = loft([hex_ring(a, ch, zt), hex_ring(a - 0.007, ch * 0.6, 0.230)], cap0=False, cap1=True)
    mb.add(V, F)
    # 反花 core (convex, quarter ellipse from r_in,z_hi down to r_out,z_lo)
    r_in, z_hi, r_out, z_lo = 0.170, 0.312, 0.236, 0.236

    def prof_core(s):      # s=0 inner/top -> s=1 outer/bottom
        th = s * np.pi / 2
        return (r_in + (r_out - r_in) * math.sin(th), z_lo + (z_hi - z_lo) * math.cos(th))
    core = [(r_out + 0.004, 0.2301)] + [prof_core(s) for s in np.linspace(1, 0, 14)] + \
           [(0.170, 0.316), (0.170, 0.326), (0.162, 0.326), (0.162, z3)]
    mb.addt(lathe(core, seg=72, cap0=True, cap1=True))
    # main petals (pointing down/outward), tips at the hex edge; 間弁 between them
    petal_ring(mb, 12, prof_core, T=0.014, phase=0.0, span=0.98, curl=0.004, ns=16, nu=11, s1=0.97)
    petal_ring(mb, 12, prof_core, T=0.009, phase=np.pi / 12, span=0.55, s0=0.45, curl=0.002, ns=9, nu=7,
               embed=0.004, s1=0.95)
    return mb


def part_sao():
    """竿: 円柱。下端・上端の節(玉縁の帯)と中央の節(玉縁2本 + 帯)。"""
    z0, z1 = D["sao"]
    r = D["r_sao"]
    zm = (z0 + z1) / 2

    def bead(zc, r0, hh, dr, n=7):
        return [(r0 + dr * math.sin(math.pi * i / (n - 1)), zc - hh / 2 + hh * i / (n - 1)) for i in range(n)]
    P = [(0.150, z0), (0.156, z0 + 0.005), (0.156, z0 + 0.030), (0.151, z0 + 0.036),
         (0.143, z0 + 0.040)] + bead(z0 + 0.050, r, 0.012, 0.006)[1:-1] + [(r, z0 + 0.062)]
    P += [(r, zm - 0.040)] + bead(zm - 0.030, r, 0.014, 0.008)[1:-1] + \
        [(r, zm - 0.022), (r + 0.006, zm - 0.020), (r + 0.006, zm + 0.020), (r, zm + 0.022)] + \
        bead(zm + 0.030, r, 0.014, 0.008)[1:-1] + [(r, zm + 0.040)]
    P += [(r, z1 - 0.062)] + bead(z1 - 0.050, r, 0.012, 0.006)[1:-1] + \
        [(0.143, z1 - 0.040), (0.151, z1 - 0.036), (0.156, z1 - 0.030), (0.156, z1 - 0.005), (0.150, z1)]
    return MB().addt(lathe(P, seg=72))


def part_chudai():
    """中台: 下に請花(上向きの蓮弁 12)、六角の胴(格狭間)、上に二段の座。"""
    z0, z3 = D["chudai"]
    a = D["a_chudai"]
    mb = MB()
    r0, zc0, r1, zc1 = 0.152, z0 + 0.003, 0.238, 1.099

    def prof_core(s):      # bowl: s=0 bottom/inner -> s=1 rim/outer
        th = s * np.pi / 2
        return (r0 + (r1 - r0) * math.sin(th), zc0 + (zc1 - zc0) * (1 - math.cos(th)))
    core = [(0.148, z0)] + [prof_core(s) for s in np.linspace(0, 1, 14)] + [(r1 - 0.01, 1.1025)]
    mb.addt(lathe(core, seg=72, cap0=True, cap1=True))
    petal_ring(mb, 12, prof_core, T=0.014, phase=0.0, span=0.98, curl=0.007, ns=16, nu=11, s0=0.16, zmin=z0 + 0.001)
    petal_ring(mb, 12, prof_core, T=0.009, phase=np.pi / 12, span=0.55, s0=0.5, curl=0.003, ns=9, nu=7,
               embed=0.004, zmin=z0 + 0.001)
    ch = 0.009
    zb, zt = 1.105, 1.165
    V, F = loft([hex_ring(a - 0.005, ch * 0.6, 1.100), hex_ring(a, ch, zb)], cap0=True, cap1=False)
    mb.add(V, F)
    K = koza_outline(0.19, 0.040) + np.array([0.0, 1.115])

    def panel(k, hw):
        return [dict(pts=K, depth=0.008, floor="flat")]
    paneled_band(mb, a, ch, zb, zt, panel)
    rings = [hex_ring(a, ch, zt), hex_ring(a - 0.006, ch * 0.6, 1.170), hex_ring(0.200, 0.006, 1.170),
             hex_ring(0.200, 0.006, 1.178), hex_ring(0.196, 0.005, 1.181), hex_ring(0.176, 0.005, 1.181),
             hex_ring(0.176, 0.005, z3)]
    V, F = loft(rings, cap0=False, cap1=True)
    mb.add(V, F)
    return mb


RELIEF = {5: "oshika", 3: "meshika", 0: "hi", 2: "tsuki"}   # face index -> 図柄 (4=正面 1=背面 は火口)


def part_hibukuro(relief_px=0.0024):
    """火袋: 六角の中空。正面・背面に火口、他4面に浮彫(雄鹿・雌鹿・日・月)。地覆・長押の帯、腰の羽目板。"""
    z0, z1 = D["hibukuro"]
    a, ai = D["a_hib"], D["a_hib_in"]
    ch, chi = 0.006, 0.005
    mb = MB()
    hw = a * TAN30 - ch
    wall = a - ai
    px0, px1 = -0.0635, 0.0635
    pz0, pz1 = z0 + 0.100, z1 - 0.060
    s = (pz1 - pz0) / 2
    zc = (pz0 + pz1) / 2
    koshi = rect_loop(-hw + 0.022, hw - 0.022, z0 + 0.040, z0 + 0.076)
    nx = int(round((px1 - px0) / relief_px)) + 1
    nz = int(round((pz1 - pz0) / relief_px)) + 1
    xs = np.linspace(px0, px1, nx)
    zs = np.linspace(pz0, pz1, nz)
    depth, rh = 0.013, 0.010
    for k in range(6):
        fr = face_frame(k, a)
        holes = [dict(pts=koshi, depth=0.005, floor="flat")]
        if k in (1, 4):
            holes.append(dict(pts=rect_loop(px0, px1, pz0, pz1), depth=wall, floor=None))
        else:
            kind = RELIEF[k]
            Xg, Zg = np.meshgrid(xs, zs)
            H = art(kind, Xg / s, (Zg - zc) / s) * rh
            Hd = {(round(x, 7), round(z, 7)): H[j, i] for j, z in enumerate(zs) for i, x in enumerate(xs)}

            def hfun(x, z, Hd=Hd):
                return Hd.get((round(x, 7), round(z, 7)), 0.0)
            holes.append(dict(pts=rect_loop(px0, px1, pz0, pz1, xs, zs), depth=depth, floor="grid",
                              xs=xs, zs=zs, hfun=hfun))
        face_with_holes(mb, fr, rect_loop(-hw, hw, z0, z1), holes)
        # inner wall
        hwi = ai * TAN30 - chi
        fri = face_frame(k, ai)
        ih = [dict(pts=rect_loop(px0, px1, pz0, pz1), depth=0.0, floor=None)] if k in (1, 4) else []
        face_with_holes(mb, fri, rect_loop(-hwi, hwi, z0, z1), [], sign=-1.0) if not ih else \
            _inner_with_hole(mb, fri, rect_loop(-hwi, hwi, z0, z1), rect_loop(px0, px1, pz0, pz1))
    # chamfers (outer / inner) and top/bottom annuli
    for (aa, cc, sg) in ((a, ch, 1), (ai, chi, -1)):
        r0, r1 = hex_ring(aa, cc, z0), hex_ring(aa, cc, z1)
        F = []
        for k in range(6):
            i, j = 2 * k + 1, (2 * k + 2) % 12
            F.append([i, j, 12 + j, 12 + i] if sg > 0 else [i, 12 + i, 12 + j, j])
        mb.add(np.vstack([r0, r1]), F)
    for z, up in ((z0, False), (z1, True)):
        ro, ri = hex_ring(a, ch, z), hex_ring(ai, chi, z)
        F = []
        for j in range(12):
            q = [j, (j + 1) % 12, 12 + (j + 1) % 12, 12 + j]
            F.append(q[::-1] if up else q)
        mb.add(np.vstack([ro, ri]), F)
    # 地覆 (bottom band) and 長押 (top band): thin hex rings standing proud of the faces
    for (zb, zt, dd) in ((z0, z0 + 0.028, 0.006), (z1 - 0.040, z1, 0.007)):
        aa = a + dd
        rings = [hex_ring(aa - 0.003, ch, zb), hex_ring(aa, ch + 0.002, zb + 0.003),
                 hex_ring(aa, ch + 0.002, zt - 0.003), hex_ring(aa - 0.003, ch, zt)]
        V, F = loft(rings, cap0=False, cap1=False)
        # close to the face with inward rings
        rin_b, rin_t = hex_ring(a - 0.002, ch, zb), hex_ring(a - 0.002, ch, zt)
        V2, F2 = loft([rin_b] + rings + [rin_t], cap0=False, cap1=False)
        mb.add(V2, F2)
    return mb


def _inner_with_hole(mb, fr, outer, hole):
    loops = [ccw(outer), ccw(hole)]
    pts2 = np.concatenate(loops)
    V = [P3(fr, x, z, 0.0) for x, z in pts2]
    F = []
    for a, b, c in tess(loops):
        ar = (pts2[b][0] - pts2[a][0]) * (pts2[c][1] - pts2[a][1]) - (pts2[b][1] - pts2[a][1]) * (pts2[c][0] - pts2[a][0])
        F.append([a, c, b] if ar > 0 else [a, b, c])
    mb.add(V, F)


# ----------------------------------------------------------------- 笠
KASA = dict(z_u=1.545, z_et=1.588, rise=0.034, z_p=1.765, a_p=0.105, a_u=0.235, d_in=0.006,
            h_r=0.019, prof_exp=1.45)


def kasa_eave_top(v):
    return KASA["z_et"] + KASA["rise"] * np.abs(2 * v - 1) ** 2.2


def kasa_ztop(t, v):
    zt = kasa_eave_top(v)
    return zt + (KASA["z_p"] - zt) * (1 - t) ** KASA["prof_exp"]


def part_kasa(M=30):
    """笠: 六角。軒は薄く隅で反り上がり、上面は凹曲面で頂部の座へ。各隅に降棟、軒先の隅に蕨手。"""
    z_bot = D["kasa"][0]
    z_top = D["kasa"][1]
    a_e, a_p, a_u = D["a_kasa"], KASA["a_p"], KASA["a_u"]
    uu = np.arange(M) / M
    vv = 0.55 * uu + 0.45 * (0.5 - 0.5 * np.cos(np.pi * uu))
    per = []                       # (k, v, unit-hex point (apothem 1), side normal)
    for k in range(6):
        c0, c1 = corner(k, 1.0), corner(k + 1, 1.0)
        ph = math.radians(60 * k + 30)
        nk = np.array([math.cos(ph), math.sin(ph)])
        for v in vv:
            per.append((k, v, c0 + (c1 - c0) * v, nk))
    N = len(per)
    Hp = np.array([p[2] for p in per])
    Vv = np.array([p[1] for p in per])
    Nk = np.array([p[3] for p in per])
    bow = (KASA["d_in"] * np.sin(np.pi * Vv))[:, None] * Nk
    Pe = a_e * Hp - bow
    rad = Pe / np.linalg.norm(Pe, axis=1)[:, None]
    Pe_in = Pe - 0.004 * rad
    Pp = a_p * Hp
    # corner ray of each perimeter sample (nearest corner)
    kk = np.array([p[0] for p in per])
    kc = np.where(Vv < 0.5, kk, kk + 1) % 6
    th = np.radians(60 * kc)
    E = np.stack([np.cos(th), np.sin(th)], 1)

    def ridge(P, t):
        d = np.abs(E[:, 0] * P[:, 1] - E[:, 1] * P[:, 0])
        wr = 0.017 + 0.007 * t
        b = np.clip(1 - (d / wr) ** 2, 0, 1) ** 0.6
        return KASA["h_r"] * b * (1 - smoothstep(0.80, 0.93, t))

    rings = []
    zp = KASA["z_p"]
    rings.append(np.column_stack([0.092 * Hp, np.full(N, z_top)]))
    rings.append(np.column_stack([0.092 * Hp, np.full(N, zp + 0.0025)]))
    tl = np.concatenate([np.linspace(0, 0.1, 4)[:-1], np.linspace(0.1, 1.0, 22)])
    for t in tl:
        P = Pp + (Pe_in - Pp) * t
        z = kasa_ztop(t, Vv) + ridge(P, t)
        rings.append(np.column_stack([P, z]))
    zet = kasa_eave_top(Vv)
    zeb = KASA["z_u"] + KASA["rise"] * 0.85 * np.abs(2 * Vv - 1) ** 2.2
    rings.append(np.column_stack([Pe, zet - 0.004]))
    rings.append(np.column_stack([Pe, zeb + 0.004]))
    Pu0 = a_u * Hp
    for t in np.linspace(1.0, 0.0, 9):
        P = Pu0 + (Pe_in - Pu0) * t
        z = KASA["z_u"] + (zeb - KASA["z_u"]) * t ** 2
        rings.append(np.column_stack([P, z]))
    rings.append(np.column_stack([a_u * Hp, np.full(N, 1.5345)]))
    rings.append(np.column_stack([0.190 * Hp, np.full(N, 1.5345)]))
    rings.append(np.column_stack([0.190 * Hp, np.full(N, z_bot)]))
    mb = MB().addt(loft(rings, cap0=True, cap1=True))
    for k in range(6):
        warabite(mb, k)
    return mb


def kasa_surface_along_corner(rho):
    """top-surface z on the corner ray at plan radius rho (no ridge)."""
    r_p = KASA["a_p"] / COS30
    r_e = (D["a_kasa"] - 0.0) / COS30 - 0.004
    t = np.clip((rho - r_p) / (r_e - r_p), 0, 1)
    return kasa_ztop(t, 0.0), t


def superellipse_section(nseg=14, p=0.55):
    b = np.linspace(0, 2 * np.pi, nseg, endpoint=False)
    c, s = np.cos(b), np.sin(b)
    return np.sign(c) * np.abs(c) ** p, np.sign(s) * np.abs(s) ** p


def warabite(mb, k):
    """蕨手: 降棟の先が軒の隅で外へ出て渦状に巻き上がる。太さは渦の中心へ細る。"""
    th = math.radians(60 * k)
    e = np.array([math.cos(th), math.sin(th), 0.0])
    nperp = np.array([-math.sin(th), math.cos(th), 0.0])
    zax = np.array([0.0, 0.0, 1.0])
    r_e = D["a_kasa"] / COS30
    rho_c = r_e - 0.030
    R0 = 0.043
    kexp = 0.185
    # lead-in along the ridge
    path, wd, dp = [], [], []
    rho_s = None
    for rho in np.linspace(KASA["a_p"] / COS30 + 0.70 * (r_e - 0.004 - KASA["a_p"] / COS30), rho_c, 12):
        zs, t = kasa_surface_along_corner(rho)
        f = (rho - (rho_c - 0.10)) / 0.10
        f = float(np.clip(f, 0, 1))
        d_here = 0.017 + 0.005 * f
        path.append((rho, zs + 0.45 * d_here))
        wd.append(0.032 + 0.002 * f)
        dp.append(d_here)
    rho0, z0 = path[-1]
    zc = z0 + R0
    al = np.radians(np.linspace(-90, 450, 90))[1:]
    for a in al:
        R = R0 * math.exp(-kexp * (a + math.pi / 2))
        path.append((rho_c + R * math.cos(a), zc + R * math.sin(a)))
        f = (a + math.pi / 2) / (al[-1] + math.pi / 2)
        wd.append(0.034 - 0.012 * f)
        dp.append(min(0.022, 0.52 * R))
    path = np.array(path)
    P3d = path[:, 0:1] * e + path[:, 1:2] * zax
    # tangent frames in the corner plane
    T = np.gradient(P3d, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    cu, cv = superellipse_section()
    rings = []
    for i in range(len(P3d)):
        Nn = np.cross(nperp, T[i])
        Nn /= np.linalg.norm(Nn)
        ring = P3d[i] + np.outer(cu * wd[i] / 2, nperp) + np.outer(cv * dp[i] / 2, Nn)
        rings.append(ring)
    mb.addt(loft(rings, cap0=True, cap1=True))
    # web: thin plate filling the first turn (the stone between the spiral grooves)
    nlead = 12
    sp = path[nlead - 1: nlead - 1 + 68]            # one turn (~360deg)
    c2 = np.array([rho_c, zc])
    tw = 0.55 * 0.032
    m = len(sp)
    Vw = []
    for side in (-1, 1):
        for q in sp:
            Vw.append(q[0] * e + q[1] * zax + nperp * side * tw / 2)
        Vw.append(c2[0] * e + c2[1] * zax + nperp * side * tw / 2)
    Fw = []
    ca, cb = m, 2 * m + 1
    for i in range(m - 1):
        Fw.append([ca, i, i + 1])
        Fw.append([cb, m + 1 + i + 1, m + 1 + i])
        Fw.append([i, m + 1 + i, m + 1 + i + 1, i + 1])
    Fw.append([ca, m - 1, 0])
    Fw.append([cb, m + 1, m + 1 + m - 1])
    Fw.append([m - 1, m + 1 + m - 1, m + 1, 0])
    mb.add(Vw, Fw)


def part_hoju():
    """請花(一重の蓮弁 8) + 宝珠(玉ねぎ形、先が尖る)。一石。"""
    z0 = D["hoju"][0]
    mb = MB()
    r0, zc0, r1, zc1 = 0.066, z0 + 0.004, 0.116, z0 + 0.068

    def prof_core(s):
        th = s * np.pi / 2
        return (r0 + (r1 - r0) * math.sin(th), zc0 + (zc1 - zc0) * (1 - math.cos(th)))
    core = [(0.064, z0), (0.066, z0 + 0.004)] + [prof_core(s) for s in np.linspace(0.05, 1, 12)] + \
           [(0.110, zc1 + 0.004), (0.070, zc1 + 0.006), (0.056, zc1 + 0.010), (0.052, zc1 + 0.018)]
    mb.addt(lathe(core, seg=64, cap0=True, cap1=False))
    petal_ring(mb, 8, prof_core, T=0.011, phase=np.pi / 8, span=0.98, curl=0.008, ns=14, nu=11, s0=0.22, zmin=z0 + 0.001)
    zh = zc1 + 0.018
    h = D["hoju"][1] - zh
    pts = [(0.052, 0.0), (0.064, 0.012), (0.086, 0.036), (0.101, 0.068), (0.105, 0.095), (0.099, 0.122),
           (0.083, 0.148), (0.060, 0.170), (0.038, 0.188), (0.024, 0.204), (0.015, 0.219), (0.008, 0.230),
           (0.0025, 0.236)]
    P = catmull(np.array(pts), 5)
    P[:, 1] = P[:, 1] / 0.236 * (h - 0.002)
    prof = [(r, zh + z) for r, z in P] + [(0.0, zh + h)]
    V, F = lathe(prof, seg=64, cap0=False, cap1=False)
    mb.add(V, F)
    return mb


# ============================================================== bpy objects / UV
OBJ_DEF = [  # name, builder, 部材名
    ("Toro_Kidan", part_kidan, "基壇"),
    ("Toro_Kiso", part_kiso, "基礎"),
    ("Toro_Sao", part_sao, "竿"),
    ("Toro_Chudai", part_chudai, "中台"),
    ("Toro_Hibukuro", part_hibukuro, "火袋"),
    ("Toro_Kasa", part_kasa, "笠"),
    ("Toro_Hoju", part_hoju, "請花・宝珠"),
]
# 雨だれ: (上端 z, 減衰長 m, 強さ) per stone
DRIP = {"Toro_Kidan": (0.11, 0.06, 0.8), "Toro_Kiso": (0.34, 0.10, 1.0), "Toro_Sao": (1.04, 0.40, 1.0),
        "Toro_Chudai": (1.19, 0.08, 1.0), "Toro_Hibukuro": (1.52, 0.22, 0.7), "Toro_Kasa": (1.78, 0.10, 0.6),
        "Toro_Hoju": (2.10, 0.12, 0.5)}


def grain_uv(V, lv, starts, tot, uv_tile):
    """Per-loop UV along each connected part's long axis (石の目), PCA frame per component."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    nv = len(V)
    nxt = np.arange(len(lv)) + 1
    ends = starts + tot
    nxt[ends - 1] = starts
    g = coo_matrix((np.ones(len(lv), np.int8), (lv, lv[nxt])), shape=(nv, nv))
    ncomp, lab = connected_components(g, directed=False)
    cnt = np.bincount(lab, minlength=ncomp).astype(float)
    cnt[cnt == 0] = 1
    mu = np.stack([np.bincount(lab, V[:, i], ncomp) for i in range(3)], 1) / cnt[:, None]
    Dd = V - mu[lab]
    C = np.zeros((ncomp, 3, 3))
    for i in range(3):
        for j in range(i, 3):
            C[:, i, j] = C[:, j, i] = np.bincount(lab, Dd[:, i] * Dd[:, j], ncomp) / cnt
    C += np.eye(3)[None] * 1e-12
    w, E = np.linalg.eigh(C)
    gax, e2, e3 = E[:, :, 2], E[:, :, 1], E[:, :, 0]
    fc = lab[lv[starts]]
    a = V[lv[starts]]; b = V[lv[starts + 1]]; c = V[lv[starts + np.minimum(2, tot - 1)]]
    fn = np.cross(b - a, c - a)
    fn /= np.maximum(np.linalg.norm(fn, axis=1), 1e-12)[:, None]
    dg = np.abs(np.sum(fn * gax[fc], 1))
    d2 = np.abs(np.sum(fn * e2[fc], 1))
    d3 = np.abs(np.sum(fn * e3[fc], 1))
    end = (dg > d2) & (dg > d3)
    U_ax = np.where(end[:, None], e2[fc], gax[fc])
    V_ax = np.where(end[:, None], e3[fc], np.where((d3 > d2)[:, None], e2[fc], e3[fc]))
    lf = np.repeat(np.arange(len(tot)), tot)
    P = V[lv] - mu[fc[lf]]
    u = np.sum(P * U_ax[lf], 1)
    v = np.sum(P * V_ax[lf], 1)
    rng = np.random.default_rng(1234)
    off = rng.uniform(0, uv_tile, (ncomp, 2))
    return np.stack([(u + off[fc[lf], 0]) / uv_tile, (v + off[fc[lf], 1]) / uv_tile], 1)


def make_object(name, mb, coll, uv_tile, dissolve=False):
    V = np.concatenate(mb.V)
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], mb.F)
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-5)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
    if dissolve:
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.3), verts=bm.verts, edges=bm.edges,
                                 delimit={'NORMAL'})
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    # grain UV (UVMap)
    n = len(me.vertices)
    Vv = np.empty(n * 3)
    me.vertices.foreach_get("co", Vv)
    Vv = Vv.reshape(-1, 3)
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    st = np.empty(len(me.polygons), np.int64)
    tt = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", st)
    me.polygons.foreach_get("loop_total", tt)
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", grain_uv(Vv, lv, st, tt, uv_tile).astype(np.float32).ravel())
    me.uv_layers.new(name="UVAtlas")
    me.uv_layers.active = me.uv_layers["UVMap"]
    me.uv_layers["UVMap"].active_render = True
    # 雨だれ係数 (point attribute "drip")
    ztop, L, k = DRIP[name]
    dr = k * np.exp(-np.clip(ztop - Vv[:, 2], 0, None) / L)
    at = me.color_attributes.new("drip", "FLOAT_COLOR", "POINT")
    col = np.repeat(dr[:, None], 4, 1)
    col[:, 3] = 1.0
    at.data.foreach_set("color", col.astype(np.float32).ravel())
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(38))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def atlas_unwrap(obs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
        o.data.uv_layers.active = o.data.uv_layers["UVAtlas"]
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.003, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in obs:
        o.data.uv_layers.active = o.data.uv_layers["UVMap"]


# ============================================================== textures (numpy, periodic)
def fft_noise(n, f0, seed, f_hp=0.0):
    rng = np.random.default_rng(seed)
    w = rng.standard_normal((n, n))
    F = np.fft.fft2(w)
    f = np.fft.fftfreq(n) * n
    fx, fy = np.meshgrid(f, f)
    fr = np.hypot(fx, fy)
    filt = np.exp(-(fr / f0) ** 2)
    if f_hp > 0:
        filt *= 1 - np.exp(-(fr / f_hp) ** 2)
    o = np.real(np.fft.ifft2(F * filt))
    return (o - o.mean()) / (o.std() + 1e-12)


def granite_tile(n, tile_m):
    """御影石 (明るい灰色 + 黒雲母の黒点 + 長石・石英の白): base (linear), rough, height (m)."""
    cells = tile_m / 0.0042                      # crystal ~4 mm
    n_blk = fft_noise(n, cells, 11)
    n_wht = fft_noise(n, cells * 0.85, 12)
    n_mid = fft_noise(n, cells * 0.45, 13)
    n_mot = fft_noise(n, tile_m / 0.15, 14)
    n_fine = fft_noise(n, cells * 2.5, 15)
    blk = smoothstep(1.35, 1.75, n_blk)
    wht = smoothstep(0.95, 1.45, n_wht) * (1 - blk)
    base = 0.165 + 0.018 * n_mid + 0.012 * n_mot + 0.008 * n_fine
    g = base * (1 - wht) + (0.27 + 0.02 * n_fine) * wht
    g = g * (1 - 0.85 * blk) + 0.03 * blk
    tint = np.array([1.0, 0.985, 0.955])
    col = np.clip(g[..., None] * tint, 0, 1)
    rough = np.clip(0.66 - 0.16 * wht - 0.06 * blk + 0.04 * n_fine, 0.3, 1)
    height = (0.30 * wht - 0.20 * blk + 0.25 * n_fine + 0.15 * n_mid) * 0.00025
    return col, rough, height


def normal_from_height(h, px_m, strength=1.0):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * px_m)
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * px_m)
    nx, ny = -dx * strength, -dy * strength
    nz = np.ones_like(h)
    L = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / L, ny / L, nz / L], -1) * 0.5 + 0.5


def save_img(name, arr, path, colorspace):
    """arr (n,n,3|4) float 0..1, row 0 = bottom (v=0)."""
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h, w, 1))], 2)
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(arr.astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


def make_tiles(tex_dir, n, tile_m):
    os.makedirs(tex_dir, exist_ok=True)
    col, rough, height = granite_tile(n, tile_m)
    srgb = np.where(col <= 0.0031308, col * 12.92, 1.055 * np.power(np.clip(col, 0, 1), 1 / 2.4) - 0.055)
    # bpy stores sRGB images' pixels as display values when colorspace is sRGB
    paths = {}
    paths["base"] = os.path.join(tex_dir, "T_Toro_Mikage_base.png")
    save_img("T_Toro_Mikage_base", srgb, paths["base"], "sRGB")
    mr = np.stack([np.ones_like(rough), rough, np.zeros_like(rough)], -1)
    paths["mr"] = os.path.join(tex_dir, "T_Toro_Mikage_mr.png")
    save_img("T_Toro_Mikage_mr", mr, paths["mr"], "Non-Color")
    nm = normal_from_height(height, tile_m / n, 1.0)
    paths["normal"] = os.path.join(tex_dir, "T_Toro_Mikage_normal.png")
    save_img("T_Toro_Mikage_normal", nm, paths["normal"], "Non-Color")
    return paths


# ============================================================== materials
class NB:
    def __init__(self, mat):
        self.nt = mat.node_tree
        self.N = self.nt.nodes
        self.L = self.nt.links

    def node(self, t, **kw):
        n = self.N.new(t)
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def _in(self, sock, v):
        if isinstance(v, (int, float, tuple)):
            sock.default_value = v
        else:
            self.L.new(v, sock)

    def math(self, op, a, b=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        return n.outputs[0]

    def smooth(self, x, a, b):
        n = self.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        self._in(n.inputs["Value"], x)
        n.inputs["From Min"].default_value = a
        n.inputs["From Max"].default_value = b
        return n.outputs["Result"]

    def maprange(self, x, a, b, c, d):
        n = self.node("ShaderNodeMapRange")
        self._in(n.inputs["Value"], x)
        n.inputs["From Min"].default_value = a
        n.inputs["From Max"].default_value = b
        n.inputs["To Min"].default_value = c
        n.inputs["To Max"].default_value = d
        return n.outputs["Result"]

    def mix(self, fac, a, b, blend="MIX"):
        a = (*a, 1.0) if isinstance(a, tuple) and len(a) == 3 else a
        b = (*b, 1.0) if isinstance(b, tuple) and len(b) == 3 else b
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        self._in(n.inputs["Factor"], fac)
        self._in(n.inputs["A"], a)
        self._in(n.inputs["B"], b)
        return n.outputs["Result"]

    def img(self, path, cs, uvname):
        im = bpy.data.images.load(path, check_existing=True)
        im.colorspace_settings.name = cs
        t = self.node("ShaderNodeTexImage")
        t.image = im
        u = self.node("ShaderNodeUVMap")
        u.uv_map = uvname
        self.L.new(u.outputs[0], t.inputs[0])
        return t

    def noise(self, vec, scale, detail=4.0, rough=0.55, dims="3D"):
        n = self.node("ShaderNodeTexNoise", noise_dimensions=dims)
        if vec is not None:
            self.L.new(vec, n.inputs["Vector"])
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        return n.outputs["Fac"]

    def vscale(self, vec, s):
        n = self.node("ShaderNodeVectorMath", operation="MULTIPLY")
        self.L.new(vec, n.inputs[0])
        n.inputs[1].default_value = s
        return n.outputs[0]


def mat_mikage(tiles):
    """御影石 (render material = the same tile textures as the GLB)."""
    m = bpy.data.materials.new("Toro_Mikage")
    m.use_nodes = True
    nb = NB(m)
    bs = nb.N["Principled BSDF"]
    tb = nb.img(tiles["base"], "sRGB", "UVMap")
    nb.L.new(tb.outputs["Color"], bs.inputs["Base Color"])
    tm = nb.img(tiles["mr"], "Non-Color", "UVMap")
    sp = nb.node("ShaderNodeSeparateColor")
    nb.L.new(tm.outputs["Color"], sp.inputs[0])
    nb.L.new(sp.outputs["Green"], bs.inputs["Roughness"])
    tn = nb.img(tiles["normal"], "Non-Color", "UVMap")
    nm = nb.node("ShaderNodeNormalMap", uv_map="UVMap")
    nb.L.new(tn.outputs["Color"], nm.inputs["Color"])
    nb.L.new(nm.outputs["Normal"], bs.inputs["Normal"])
    m.diffuse_color = (0.6, 0.6, 0.58, 1)
    return m


def mat_koshoku(tiles, ao_large, ao_small):
    """古色: 黄ばみ・地衣の斑・雨だれの黒い筋(下向き)・上向き面の苔・彫りの凹部の暗さ。
    AO はアトラスに焼いた画像を使う(GLB 用の焼き込みと Cycles 描画で同じ見え方にする)。"""
    m = bpy.data.materials.new("Toro_Koshoku")
    m.use_nodes = True
    nb = NB(m)
    bs = nb.N["Principled BSDF"]
    geo = nb.node("ShaderNodeNewGeometry")
    pos, nrm = geo.outputs["Position"], geo.outputs["Normal"]
    sepn = nb.node("ShaderNodeSeparateXYZ")
    nb.L.new(nrm, sepn.inputs[0])
    nz = sepn.outputs["Z"]
    drip = nb.node("ShaderNodeAttribute", attribute_name="drip").outputs["Fac"]
    aoL = nb.img(ao_large, "Non-Color", "UVAtlas").outputs["Color"]
    aoS = nb.img(ao_small, "Non-Color", "UVAtlas").outputs["Color"]
    aoLf = nb.node("ShaderNodeSeparateColor")
    nb.L.new(aoL, aoLf.inputs[0])
    aoSf = nb.node("ShaderNodeSeparateColor")
    nb.L.new(aoS, aoSf.inputs[0])
    aoL, aoS = aoLf.outputs["Red"], aoSf.outputs["Red"]
    granite = nb.img(tiles["base"], "sRGB", "UVMap").outputs["Color"]
    # yellowed / greyed-down granite
    c = nb.mix(1.0, granite, (0.86, 0.74, 0.48), blend="MULTIPLY")
    mott = nb.noise(pos, 2.2, 5.0, 0.6)
    c = nb.mix(nb.math("MULTIPLY", nb.smooth(mott, 0.40, 0.66), 0.6), c, (0.12, 0.105, 0.065))
    # dark lichen / soot patches (more on vertical faces)
    vert = nb.math("SUBTRACT", 1.0, nb.math("ABSOLUTE", nz))
    blk = nb.smooth(nb.noise(pos, 7.0, 6.0, 0.65), 0.60, 0.70)
    c = nb.mix(nb.math("MULTIPLY", blk, 0.55), c, (0.045, 0.045, 0.038))
    # pale lichen rosettes (Voronoi spots)
    vor = nb.node("ShaderNodeTexVoronoi", feature="F1")
    nb.L.new(pos, vor.inputs["Vector"])
    vor.inputs["Scale"].default_value = 16.0
    rnd = nb.node("ShaderNodeSeparateColor")
    nb.L.new(vor.outputs["Color"], rnd.inputs[0])
    spot = nb.math("MULTIPLY", nb.smooth(vor.outputs["Distance"], 0.22, 0.14),
                   nb.smooth(rnd.outputs["Red"], 0.80, 0.84))
    spot = nb.math("MULTIPLY", spot, nb.smooth(nb.noise(pos, 40.0, 3.0), 0.35, 0.55))
    c = nb.mix(nb.math("MULTIPLY", spot, 0.75), c, (0.42, 0.43, 0.37))
    # 雨だれ: vertical streaks, strongest just under each stone's top edge
    sv = nb.node("ShaderNodeVectorMath", operation="MULTIPLY")
    nb.L.new(pos, sv.inputs[0])
    sv.inputs[1].default_value = (16.0, 16.0, 0.9)
    streak = nb.smooth(nb.noise(sv.outputs[0], 1.0, 4.0, 0.6), 0.56, 0.72)
    streak = nb.math("MULTIPLY", streak, nb.smooth(nb.noise(pos, 3.0, 2.0), 0.40, 0.60))
    st = nb.math("MULTIPLY", nb.math("MULTIPLY", streak, drip), nb.smooth(vert, 0.3, 0.8))
    st = nb.math("MINIMUM", nb.math("MULTIPLY", st, 1.3), 0.92)
    c = nb.mix(st, c, (0.028, 0.027, 0.022))
    # 苔: upward faces + crevices, clumpy
    up = nb.smooth(nz, 0.25, 0.75)
    mn = nb.noise(pos, 6.0, 8.0, 0.62)
    crev = nb.math("SUBTRACT", 1.0, aoS)
    mval = nb.math("ADD", mn, nb.math("MULTIPLY", crev, 0.55))
    moss = nb.math("MULTIPLY", up, nb.smooth(mval, 0.44, 0.58))
    moss = nb.math("MAXIMUM", moss, nb.math("MULTIPLY", nb.smooth(aoS, 0.55, 0.25), 0.6))
    mfine = nb.noise(pos, 90.0, 4.0, 0.7)
    mcol = nb.mix(nb.smooth(mfine, 0.35, 0.65), (0.022, 0.045, 0.010), (0.085, 0.13, 0.022))
    c = nb.mix(moss, c, mcol)
    # cavities and general occlusion
    c = nb.mix(1.0, c, nb.node_color(nb.maprange(aoS, 0.0, 1.0, 0.30, 1.0)), blend="MULTIPLY")
    c = nb.mix(1.0, c, nb.node_color(nb.maprange(aoL, 0.0, 1.0, 0.55, 1.0)), blend="MULTIPLY")
    rough = nb.maprange(moss, 0.0, 1.0, 0.78, 0.95)
    nb.L.new(c, bs.inputs["Base Color"])
    nb.L.new(rough, bs.inputs["Roughness"])
    tn = nb.img(tiles["normal"], "Non-Color", "UVMap")
    nm = nb.node("ShaderNodeNormalMap", uv_map="UVMap")
    nb.L.new(tn.outputs["Color"], nm.inputs["Color"])
    bump = nb.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    nb.L.new(nb.math("MULTIPLY", moss, mfine), bump.inputs["Height"])
    nb.L.new(nm.outputs["Normal"], bump.inputs["Normal"])
    nb.L.new(bump.outputs["Normal"], bs.inputs["Normal"])
    m["_bake_color"] = c.node.name
    m.diffuse_color = (0.4, 0.38, 0.3, 1)
    return m


def _node_color(self, f):
    n = self.node("ShaderNodeCombineColor")
    for i in range(3):
        self.L.new(f, n.inputs[i])
    return n.outputs[0]


NB.node_color = _node_color


# ============================================================== baking
def bake_atlas(obs, mat, size, path, btype, emit_socket=None, samples=1, ao_dist=None):
    """Bake into a shared atlas image (UVAtlas) over all objects carrying `mat`."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    img = bpy.data.images.new(os.path.splitext(os.path.basename(path))[0], size, size, alpha=False)
    img.colorspace_settings.name = "Non-Color" if btype == "AO" else "sRGB"
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "UVAtlas"
    nt.links.new(uvn.outputs[0], tex.inputs[0])
    nt.nodes.active = tex
    out = nt.nodes["Material Output"]
    old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].links else None
    em = None
    if emit_socket is not None:
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(emit_socket, em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    if ao_dist is not None:
        sc.world.light_settings.distance = ao_dist
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.bake(type=btype, margin=6, use_clear=True, uv_layer="UVAtlas")
    if em is not None:
        nt.nodes.remove(em)
        if old is not None:
            nt.links.new(old, out.inputs["Surface"])
    nt.nodes.remove(tex)
    nt.nodes.remove(uvn)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return path


# ============================================================== glTF
def glb_material(name, base, base_uv, mr, normal, occ=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nb = NB(m)
    bs = nb.N["Principled BSDF"]
    tb = nb.img(base, "sRGB", base_uv)
    nb.L.new(tb.outputs["Color"], bs.inputs["Base Color"])
    tm = nb.img(mr, "Non-Color", "UVMap")
    sp = nb.node("ShaderNodeSeparateColor")
    nb.L.new(tm.outputs["Color"], sp.inputs[0])
    nb.L.new(sp.outputs["Green"], bs.inputs["Roughness"])
    nb.L.new(sp.outputs["Blue"], bs.inputs["Metallic"])
    tn = nb.img(normal, "Non-Color", "UVMap")
    nm = nb.node("ShaderNodeNormalMap", uv_map="UVMap")
    nb.L.new(tn.outputs["Color"], nm.inputs["Color"])
    nb.L.new(nm.outputs["Normal"], bs.inputs["Normal"])
    if occ:
        g = bpy.data.node_groups.get("glTF Material Output")
        if g is None:
            g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
            g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        gn = nb.node("ShaderNodeGroup")
        gn.node_tree = g
        to = nb.img(occ, "Non-Color", "UVAtlas")
        so = nb.node("ShaderNodeSeparateColor")
        nb.L.new(to.outputs["Color"], so.inputs[0])
        nb.L.new(so.outputs["Red"], gn.inputs[0])
    return m


def setup_variants(obs, finishes, mats_by_finish):
    try:
        bpy.context.preferences.addons["io_scene_gltf2"].preferences.KHR_materials_variants_ui = True
    except Exception:
        pass
    sc = bpy.context.scene
    vs = sc.gltf2_KHR_materials_variants_variants
    vs.clear()
    for i, f in enumerate(finishes):
        v = vs.add()
        v.variant_idx = i
        v.name = f["id"]
    for ob in obs:
        me = ob.data
        me.materials[0] = mats_by_finish[finishes[0]["id"]]
        me.gltf2_variant_mesh_data.clear()
        for i, f in enumerate(finishes):
            d = me.gltf2_variant_mesh_data.add()
            d.material_slot_index = 0
            d.material = mats_by_finish[f["id"]]
            vv = d.variants.add()
            vv.variant.variant_idx = i


def find_gltf_transform():
    for c in (os.environ.get("GLTF_TRANSFORM"), shutil.which("gltf-transform")):
        if c and os.path.exists(c):
            return c
    return None


def export_glb(path, image_format="AUTO"):
    kw = dict(filepath=path, export_format="GLB", export_yup=True, export_apply=True,
              export_image_format=image_format, export_texcoords=True, export_normals=True,
              export_materials="EXPORT", export_cameras=False, export_lights=False,
              export_vertex_color="NONE", export_all_vertex_colors=False)
    bpy.ops.export_scene.gltf(**kw)


# ============================================================== checks
def contact_report(obs):
    """各段の積み重ね: 上の石の下端と下の石の上端の差 (mm)、および隣接する石どうしの三角形の交差数。"""
    by = {o.name: o for o in obs}
    order = [o[0] for o in OBJ_DEF]
    res = []
    for lo, hi in zip(order[:-1], order[1:]):
        a, b = by[lo], by[hi]
        Va = np.array([v.co for v in a.data.vertices])
        Vb = np.array([v.co for v in b.data.vertices])
        zb = Vb[:, 2].min()
        bot = Vb[Vb[:, 2] < zb + 1e-4]
        rmax = np.hypot(bot[:, 0], bot[:, 1]).max()
        near = Va[np.hypot(Va[:, 0], Va[:, 1]) <= rmax + 1e-4]
        za = near[:, 2].max() if len(near) else Va[:, 2].max()
        # めり込み: 下の石の頂点のうち、上の石の内部にあるもの(上の石の下面より上にある点の最大量)
        bvb = BVHTree.FromObject(b, bpy.context.evaluated_depsgraph_get())
        bva = BVHTree.FromObject(a, bpy.context.evaluated_depsgraph_get())
        pen = 0.0
        for P_, bv in ((Va, bvb), (Vb, bva)):
            for p in P_:
                q = Vector(p)
                loc, nrm_, _i, dist = bv.find_nearest(q)
                if loc is not None and dist > 1e-4 and (q - loc).dot(nrm_) < 0:
                    hit, _n, _j, _d = bv.ray_cast(q, Vector((0.0, 0.0, 1.0)))
                    hit2, _n2, _j2, _d2 = bv.ray_cast(q, Vector((0.0, 0.0, -1.0)))
                    if hit is not None and hit2 is not None:
                        pen = max(pen, dist)
        res.append({"lower": lo, "upper": hi, "gap_mm": round(float(zb - za) * 1000, 2),
                    "upper_bottom_r_m": round(float(rmax), 3), "penetration_mm": round(pen * 1000, 2)})
    return res


# ============================================================== main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="L-1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-glb", action="store_true")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    vpath = os.path.join(HERE, "variants", "%s.json" % a.variant)
    with open(vpath, encoding="utf-8") as f:
        VD = json.load(f)
    P = VD.get("params", {})
    out = os.path.abspath(a.out or os.path.join("haiden", "out", a.variant))
    os.makedirs(out, exist_ok=True)
    tex_dir = os.path.join(out, "textures")
    t0 = time.time()
    finishes = VD.get("finishes") or [{"id": "shin", "name": "御影石"}, {"id": "koshoku", "name": "古色"}]
    tile_n = int(P.get("tile_size", 1024))
    tile_m = float(P.get("uv_tile_m", 0.6))
    atlas_n = int(P.get("atlas_size", 2048))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("World")
    root = bpy.data.collections.new("Toro")
    sc.collection.children.link(root)

    obs = []
    timing = {}
    for name, fn, _jp in OBJ_DEF:
        t1 = time.time()
        mb = fn()
        obs.append(make_object(name, mb, root, tile_m, dissolve=False))
        timing[name] = round(time.time() - t1, 2)
    print("geometry %.1fs %s" % (time.time() - t0, timing), flush=True)
    atlas_unwrap(obs)
    print("atlas unwrap done %.1fs" % (time.time() - t0), flush=True)

    tiles = make_tiles(tex_dir, tile_n, tile_m)
    m_shin = mat_mikage(tiles)
    for o in obs:
        o.data.materials.append(m_shin)
    # AO atlases (large = general occlusion, small = 彫りの凹部)
    tb = time.time()
    ao_large = bake_atlas(obs, m_shin, atlas_n // 2, os.path.join(tex_dir, "T_Toro_AO.png"), "AO",
                          samples=int(P.get("ao_samples", 48)), ao_dist=0.35)
    ao_small = bake_atlas(obs, m_shin, atlas_n, os.path.join(tex_dir, "T_Toro_Cavity.png"), "AO",
                          samples=int(P.get("cavity_samples", 24)), ao_dist=0.025)
    print("AO baked %.1fs" % (time.time() - tb), flush=True)
    m_ko = mat_koshoku(tiles, ao_large, ao_small)
    m_ko.use_fake_user = True
    m_shin.use_fake_user = True
    fm = {"shin": [m_shin.name], "koshoku": [m_ko.name]}
    for o in obs:
        o["finish_mats"] = json.dumps(fm)

    contacts = contact_report(obs)
    for c in contacts:
        print("contact", c, flush=True)

    tris = verts = 0
    for o in obs:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
        verts += len(o.data.vertices)
    allV = np.concatenate([np.array([v.co for v in o.data.vertices]) for o in obs])
    mn, mx = allV.min(0), allV.max(0)
    print("built: %d tris, %d verts, %d objects, %.1fs" % (tris, verts, len(obs), time.time() - t0), flush=True)

    sc.render.engine = "CYCLES"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "haiden.blend"), compress=True)

    stats = {
        "id": VD["id"], "name": VD["name"], "version": VD.get("version", "ver1"), "seq": VD.get("seq", 0),
        "category": VD.get("category", "toro"), "category_name": VD.get("category_name", "灯籠"),
        "title": VD.get("title", ""),
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "triangles": tris, "tris": tris, "vertices": verts, "objects": len(obs),
        "materials": 2, "material_names": [m_shin.name, m_ko.name],
        "dimensions_m": {"width_x": round(float(mx[0] - mn[0]), 3), "depth_y": round(float(mx[1] - mn[1]), 3),
                         "height_z": round(float(mx[2] - mn[2]), 3)},
        "parts_m": {jp: {"object": n, "z": [round(D[k][0], 3), round(D[k][1], 3)]}
                    for (n, _f, jp), k in zip(OBJ_DEF, ["kidan", "kiso", "sao", "chudai", "hibukuro", "kasa", "hoju"])},
        "contacts": contacts,
        "finishes": finishes, "finish_mode": "khr_variants", "uv_mode": "grain+atlas",
        "renders": [],
    }
    if not a.no_glb:
        tb = time.time()
        ko_base = bake_atlas(obs, m_ko, atlas_n, os.path.join(tex_dir, "T_Toro_Koshoku_base.png"), "EMIT",
                             emit_socket=m_ko.node_tree.nodes[m_ko["_bake_color"]].outputs["Result"], samples=1)
        print("koshoku atlas baked %.1fs" % (time.time() - tb), flush=True)
        g_shin = glb_material("GLB_Toro_Mikage", tiles["base"], "UVMap", tiles["mr"], tiles["normal"], occ=ao_large)
        g_ko = glb_material("GLB_Toro_Koshoku", ko_base, "UVAtlas", tiles["mr"], tiles["normal"])
        setup_variants(obs, finishes, {"shin": g_shin, "koshoku": g_ko})
        full = os.path.join(out, "haiden.glb")
        export_glb(full)
        web = os.path.join(out, "haiden_web.glb")
        gt = find_gltf_transform()
        ok = False
        if gt:
            tmp = os.path.join(out, "_web_tmp.glb")
            r = subprocess.run([gt, "webp", full, tmp, "--quality", str(P.get("webp_quality", 80))],
                               capture_output=True, text=True)
            print(r.stdout[-300:], r.stderr[-300:])
            if r.returncode == 0:
                r = subprocess.run([gt, "draco", tmp, web, "--method", "edgebreaker"], capture_output=True, text=True)
                print(r.stdout[-300:], r.stderr[-300:])
                ok = r.returncode == 0
            if os.path.exists(tmp):
                os.remove(tmp)
        if not ok:
            export_glb(web, image_format="JPEG")
        stats.update({"texture_size": tile_n, "atlas_size": atlas_n, "glb_bytes": os.path.getsize(web),
                      "glb_full_bytes": os.path.getsize(full), "web_draco": ok,
                      "web_textures": "webp" if ok else "jpeg"})
    sp = os.path.join(out, "stats.json")
    if os.path.exists(sp):
        try:
            prev = json.load(open(sp, encoding="utf-8"))
            if prev.get("id") == VD["id"]:
                stats["renders"] = prev.get("renders", [])
        except Exception:
            pass
    stats["build_seconds"] = round(time.time() - t0, 1)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("done in %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
