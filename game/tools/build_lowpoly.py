#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""和風箱庭ゲーム用の超ローポリ モデル一式を生成する(Blender bpy・ヘッドレス)。

実行:
  python3 game/tools/build_lowpoly.py            全モデルを game/assets/models/*.glb に書き出し、game/data/catalog.json を作る
  python3 game/tools/build_lowpoly.py --preview  上に加えて確認用レンダを /tmp/lowpoly_preview/*.png に作る(リポジトリ外)
  python3 game/tools/build_lowpoly.py --only haiden,torii   指定モデルだけ書き出す(カタログは作らない)

座標: Blender は Z上・正面=-Y。glTF 書き出し(+Y up)後、Godot では正面=+Z。
原点=設置面の中心(地面 Z=0)。地面にめり込む部分は約0.3m下へ延ばす。
1モデル=1メッシュ(マテリアル別サーフェス)。Draco・テクスチャなし。フラットシェーディング。
カタログのコライダは Godot 座標: pos=[x, z, -y], size=[dx, dz, dy]。footprint=[x幅, y奥行] (Blender 軸のまま)。
"""

import argparse
import json
import math
import os
import random
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MODEL_DIR = os.path.join(ROOT, "game", "assets", "models")
CATALOG_PATH = os.path.join(ROOT, "game", "data", "catalog.json")
PREVIEW_DIR = "/tmp/lowpoly_preview"

PI = math.pi

# ---------------------------------------------------------------------------
# 材質(sRGB の色、ラフネス)。同じ名前は全モデルで同じ色。
# ---------------------------------------------------------------------------
PALETTE = {
    "wood_ni": ("#B8402A", 0.55),       # 丹塗(朱)
    "wood_dark": ("#4A3A2C", 0.7),      # 焦茶の木(扉・賽銭箱・木の電柱)
    "wood_plain": ("#D8C49A", 0.7),     # 白木
    "plaster": ("#E9E3D3", 0.9),        # 白壁
    "earth": ("#A08A68", 0.95),         # 土壁
    "roof_copper": ("#5C9E8B", 0.45),   # 緑青の銅板
    "roof_tile": ("#5E6368", 0.8),      # いぶし瓦
    "roof_thatch": ("#B39B5E", 0.95),   # 茅
    "stone": ("#9C9A93", 0.9),          # 石
    "stone_moss": ("#6E7F4A", 0.95),    # 苔
    "gold": ("#C9A227", 0.3),           # 宝珠・鈴
    "rope": ("#A8875A", 0.95),          # 縄
    "cloth_red": ("#B3262B", 0.9),      # 地蔵の前掛け
    "cloth_gray": ("#4B505C", 0.9),     # 作務衣(歩行用の人)
    "skin": ("#E2B994", 0.8),
    "glow_lantern": ("#F3C77A", 0.6),   # 灯籠の火袋(夜に灯る)
    "glow_window": ("#EFE7D0", 0.8),    # 障子・窓(夜に灯る。昼は和紙色)
    "water_basin": ("#5F8C98", 0.15),   # 手水の水面
    "trunk": ("#5A4632", 0.9),          # 木の幹
    "trunk_take": ("#8DB255", 0.85),    # 竹の稈(黄緑がかった緑)
    "leaf_sugi": ("#2E5B3A", 0.85),
    "leaf_matsu": ("#3A6E45", 0.85),
    "leaf_take": ("#6A9E4A", 0.85),
    "leaf_sakura": ("#7CAE5E", 0.85),   # 夏の葉色(季節色はゲーム側のシェーダ)
    "leaf_kaede": ("#5B9446", 0.85),
}


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear(h):
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# ベクトル補助(タプル)
# ---------------------------------------------------------------------------
def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vlen(a):
    return math.sqrt(dot(a, a))


def unit(a):
    l = vlen(a)
    if l < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / l, a[1] / l, a[2] / l)


def centroid(pts):
    n = float(len(pts))
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)


def newell(pts):
    nx = ny = nz = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1, z1 = pts[i]
        x2, y2, z2 = pts[(i + 1) % n]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return (nx, ny, nz)


def orient(P, away):
    """面の法線が away(点)から遠ざかる向きになるよう、頂点順を揃える。"""
    n = newell(P)
    if vlen(n) < 1e-12:
        return P
    if dot(n, sub(centroid(P), away)) < 0:
        return P[::-1]
    return P


def r2(x):
    v = round(float(x), 2)
    return 0.0 if v == 0 else v


# ---------------------------------------------------------------------------
# Mesh: 三角形の集まり。面ごとに材質名を持つ。
# mx=-1 で X 反転(阿/吽のミラー)。外向き法線は中心点との位置関係で判定する。
# ---------------------------------------------------------------------------
class Mesh:
    def __init__(self):
        self.verts = []
        self.tris = []
        self.tmat = []
        self.mats = []
        self.mx = 1.0

    def _mat(self, name):
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    def _mp(self, p):
        return (p[0] * self.mx, p[1], p[2])

    def _emit(self, P, mat):
        """既にミラー済みの多角形を扇形に三角形化して追加。"""
        mi = self._mat(mat)
        base = len(self.verts)
        self.verts.extend(P)
        for i in range(1, len(P) - 1):
            a, b, c = P[0], P[i], P[i + 1]
            if vlen(cross(sub(b, a), sub(c, a))) < 1e-9:
                continue
            self.tris.append((base, base + i, base + i + 1))
            self.tmat.append(mi)

    def poly(self, pts, mat, away):
        P = [self._mp(p) for p in pts]
        if self.mx < 0:
            P = P[::-1]
        self._emit(orient(P, self._mp(away)), mat)

    def hexa(self, c, mat):
        """c: 0-3 が底面の輪、4-7 が上面の輪(同じ対応順)。"""
        C = centroid(c)
        for f in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.poly([c[i] for i in f], mat, C)

    def box(self, c, size, mat, rz=0.0):
        sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
        cr, sr = math.cos(rz), math.sin(rz)
        pts = []
        for zz in (-sz, sz):
            for (x, y) in ((-sx, -sy), (sx, -sy), (sx, sy), (-sx, sy)):
                pts.append((c[0] + x * cr - y * sr, c[1] + x * sr + y * cr, c[2] + zz))
        self.hexa(pts, mat)

    def prism(self, quad, vec, mat):
        self.hexa(list(quad) + [add(q, vec) for q in quad], mat)

    def beam(self, p0, p1, w, h, mat, up=(0.0, 0.0, 1.0)):
        """断面 w(横) x h(上) の角材。p0-p1 の間。"""
        d = unit(sub(p1, p0))
        if abs(dot(d, unit(up))) > 0.95:
            up = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
        s = unit(cross(d, up))
        t = unit(cross(s, d))
        hw = mul(s, w / 2)
        hh = mul(t, h / 2)
        c = []
        for p in (p0, p1):
            c += [sub(sub(p, hw), hh), add(sub(p, hh), hw), add(add(p, hw), hh), add(sub(p, hw), hh)]
        self.hexa(c, mat)

    def rings(self, R, mat):
        """同じ点数のリング列を結ぶ立体。両端のリングは蓋。"""
        C = centroid([p for ring in R for p in ring])
        n = len(R[0])
        for k in range(len(R) - 1):
            A, B = R[k], R[k + 1]
            for i in range(n):
                j = (i + 1) % n
                self.poly([A[i], A[j], B[j], B[i]], mat, C)
        self.poly(R[0], mat, C)
        self.poly(R[-1], mat, C)

    def cyl(self, p0, p1, r0, r1, n, mat, phase=0.0):
        """任意方向の円柱・円錐台(r1=0 で錐)。"""
        d = unit(sub(p1, p0))
        ref = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
        u = unit(cross(d, ref))
        v = unit(cross(d, u))
        R = []
        for p, r in ((p0, r0), (p1, r1)):
            ring = []
            for i in range(n):
                a = phase + 2 * PI * i / n
                ring.append(add(p, add(mul(u, r * math.cos(a)), mul(v, r * math.sin(a)))))
            R.append(ring)
        self.rings(R, mat)

    def ellipsoid(self, c, rx, ry, rz, mat, nu=6, nv=3):
        R = []
        for k in range(nv + 1):
            th = PI * k / nv
            ring = []
            for i in range(nu):
                ph = 2 * PI * i / nu
                ring.append((c[0] + rx * math.sin(th) * math.cos(ph),
                             c[1] + ry * math.sin(th) * math.sin(ph),
                             c[2] + rz * math.cos(th)))
            R.append(ring)
        self.rings(R, mat)

    def grid(self, fn, nu, nv, mat, inside, thick=0.0, skip=()):
        """パラメトリック曲面 fn(u,v)->(x,y,z)。thick>0 なら裏面と側面も作る(屋根の板厚)。
        skip: 側面を作らない辺の名前 ('u0','u1','v0','v1')。他の面と接する内側の辺に使う。"""
        P = [[self._mp(fn(i / nu, j / nv)) for j in range(nv + 1)] for i in range(nu + 1)]
        ins = self._mp(inside)
        C = centroid([p for row in P for p in row])
        for i in range(nu):
            for j in range(nv):
                q = [P[i][j], P[i + 1][j], P[i + 1][j + 1], P[i][j + 1]]
                top = orient(q, ins)
                self._emit(top, mat)
                if thick > 0:
                    self._emit([(x, y, z - thick) for (x, y, z) in top][::-1], mat)
        if thick > 0:
            edges = []
            if "u0" not in skip:
                edges += [(P[0][j], P[0][j + 1]) for j in range(nv)]
            if "u1" not in skip:
                edges += [(P[nu][j], P[nu][j + 1]) for j in range(nv)]
            if "v0" not in skip:
                edges += [(P[i][0], P[i + 1][0]) for i in range(nu)]
            if "v1" not in skip:
                edges += [(P[i][nv], P[i + 1][nv]) for i in range(nu)]
            for A, B in edges:
                Ab = (A[0], A[1], A[2] - thick)
                Bb = (B[0], B[1], B[2] - thick)
                self._emit(orient([A, B, Bb, Ab], C), mat)

    def slab(self, pts, mat, inside, thick):
        """平面の多角形(板)。厚み付き。"""
        P = [self._mp(p) for p in pts]
        top = orient(P, self._mp(inside))
        self._emit(top, mat)
        self._emit([(x, y, z - thick) for (x, y, z) in top][::-1], mat)
        C = centroid(top)
        n = len(top)
        for i in range(n):
            A = top[i]
            B = top[(i + 1) % n]
            self._emit(orient([A, B, (B[0], B[1], B[2] - thick), (A[0], A[1], A[2] - thick)], C), mat)


def bbox(M):
    xs = [p[0] for p in M.verts]
    ys = [p[1] for p in M.verts]
    zs = [p[2] for p in M.verts]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def cb(x0, x1, y0, y1, z0, z1):
    """コライダ箱(Blender 座標の範囲)。"""
    return (x0, x1, y0, y1, z0, z1)


def hip_roof(M, rx, ry, ze, zr, mat, thick):
    """寄棟。軒は ±rx, ±ry の矩形、棟は X 方向に中央 zr。"""
    a = rx - ry
    ins = (0.0, 0.0, zr * 0.5)
    M.slab([(-rx, -ry, ze), (rx, -ry, ze), (a, 0, zr), (-a, 0, zr)], mat, ins, thick)
    M.slab([(-rx, ry, ze), (-a, 0, zr), (a, 0, zr), (rx, ry, ze)], mat, ins, thick)
    M.slab([(-rx, -ry, ze), (-a, 0, zr), (-rx, ry, ze)], mat, ins, thick)
    M.slab([(rx, -ry, ze), (rx, ry, ze), (a, 0, zr)], mat, ins, thick)


def frame(M, cx, cy, cz, w, h, t, mat, depth=0.08, face=-1):
    """窓枠(4本)。cy は面の位置、face=-1 なら手前(-Y)へ出る。"""
    yy = cy + face * depth / 2
    M.box((cx, yy, cz + h / 2 - t / 2), (w, depth, t), mat)
    M.box((cx, yy, cz - h / 2 + t / 2), (w, depth, t), mat)
    M.box((cx - w / 2 + t / 2, yy, cz), (t, depth, h), mat)
    M.box((cx + w / 2 - t / 2, yy, cz), (t, depth, h), mat)


# ---------------------------------------------------------------------------
# 神社: 拝殿
# ---------------------------------------------------------------------------
def build_haiden(M):
    W, DK, PL, PLA, ST, CU, GOLD, ROPE = ("wood_ni", "wood_dark", "wood_plain", "plaster",
                                          "stone", "roof_copper", "gold", "rope")
    XB, YB = 4.2, 2.8          # 身舎(壁)の半幅
    XE, YE = 5.3, 3.8          # 主屋根の軒の半幅
    X1, Y1 = 3.4, 2.2          # 入母屋の棟の肩(切妻の底)
    ZE, RISE = 4.25, 0.5       # 軒の高さ・四隅の反り上がり
    Z1, H = 5.5, 7.3           # 肩の高さ・棟の高さ
    SL, SU = 0.2, 0.25         # 照り(面のへこみ)
    T = 0.12                   # 銅板の厚み

    # 基壇・縁・階段
    M.box((0, 0, 0.15), (10.0, 6.8, 0.9), ST)
    M.box((0, -4.35, 0.15), (4.0, 2.0, 0.9), ST)
    M.box((0, -5.62, 0.0), (2.4, 0.55, 0.6), ST)
    M.box((0, -6.17, -0.15), (2.4, 0.55, 0.3), ST)
    M.box((0, 0, 0.675), (9.8, 6.6, 0.15), PL)
    M.box((0, -4.05, 0.675), (3.2, 2.5, 0.15), PL)
    for sx in (-1, 1):
        for y in (-3.0, -1.5, 0.0, 1.5, 3.0):
            M.box((sx * 4.85, y, 0.925), (0.08, 0.08, 0.35), W)
        M.box((sx * 4.85, 0, 1.12), (0.08, 6.2, 0.07), W)
    for x in (-4.5, -2.25, 0.0, 2.25, 4.5):
        M.box((x, 3.25, 0.925), (0.08, 0.08, 0.35), W)
    M.box((0, 3.25, 1.12), (9.8, 0.07, 0.07), W)

    # 身舎・柱・扉
    M.box((0, 0, (0.6 + 4.95) / 2), (2 * XB, 2 * YB, 4.95 - 0.6), PLA)
    M.box((0, -YB - 0.03, 2.2), (2.6, 0.06, 3.2), W)          # 扉(丹塗)
    for (x, y) in [(-XB, -YB), (-1.4, -YB), (1.4, -YB), (XB, -YB),
                   (-XB, YB), (-1.4, YB), (1.4, YB), (XB, YB), (-XB, 0), (XB, 0)]:
        M.cyl((x, y, 0.6), (x, y, 4.95), 0.16, 0.16, 8, W)

    # 向拝(1間): 柱・頭貫・注連縄・賽銭箱・鈴
    for x in (-1.4, 1.4):
        M.cyl((x, -5.2, 0.75), (x, -5.2, 4.0), 0.15, 0.15, 8, W)
    M.beam((-1.45, -5.2, 3.9), (1.45, -5.2, 3.9), 0.24, 0.24, W)
    M.beam((-1.35, -5.2, 3.4), (1.35, -5.2, 3.4), 0.1, 0.1, ROPE)
    M.box((0, -4.1, 1.0), (1.0, 0.5, 0.5), PL)                 # 賽銭箱(白木)
    M.cyl((0, -4.7, 3.35), (0, -4.7, 2.3), 0.03, 0.03, 5, ROPE)
    M.ellipsoid((0, -4.7, 2.2), 0.12, 0.12, 0.12, GOLD, 6, 3)

    # 向拝の屋根(唐破風の張り出し)
    WP = 1.9

    def porch(u, v):
        x = -WP + 2 * WP * u
        y = -6.2 + 3.4 * v
        s = abs(x) / WP
        zf = 3.85 + 1.25 * (1 - s * s) + 0.25 * s ** 4
        z = (1 - v) * zf + v * 3.95 - 0.15 * math.sin(PI * v)
        return (x, y, z)

    M.grid(porch, 8, 4, CU, (0, -3.9, 1.0), T)

    # 主屋根(入母屋): 下の寄棟 + 上の切妻 + 妻の破風
    def hip_front(sy):
        def f(u, v):
            xe = -XE + 2 * XE * u
            xt = -X1 + 2 * X1 * u
            x = xe + (xt - xe) * v
            y = sy * (YE + (Y1 - YE) * v)
            ze = ZE + RISE * (abs(xe) / XE) ** 2.2
            z = (1 - v) * ze + v * Z1 - SL * math.sin(PI * v)
            return (x, y, z)
        return f

    def hip_side(sx):
        def f(u, v):
            ye = -YE + 2 * YE * u
            yt = -Y1 + 2 * Y1 * u
            y = ye + (yt - ye) * v
            x = sx * (XE - (XE - X1) * v)
            ze = ZE + RISE * (abs(ye) / YE) ** 2.2
            z = (1 - v) * ze + v * Z1 - SL * math.sin(PI * v)
            return (x, y, z)
        return f

    def upper(sy):
        def f(u, v):
            x = -X1 + 2 * X1 * u
            y = sy * Y1 * (1 - v)
            z = Z1 + (H - Z1) * v - SU * math.sin(PI * v)
            return (x, y, z)
        return f

    ins = (0, 0, 2.5)
    # 肩(v1 の辺)と棟(upper の v1)は上下の面が接するので側面を作らない
    M.grid(hip_front(-1), 8, 4, CU, ins, T, skip=("v1",))
    M.grid(hip_front(1), 8, 4, CU, ins, T, skip=("v1",))
    M.grid(hip_side(-1), 8, 4, CU, ins, T, skip=("v1",))
    M.grid(hip_side(1), 8, 4, CU, ins, T, skip=("v1",))
    M.grid(upper(-1), 8, 4, CU, ins, T, skip=("v0", "v1", "u0", "u1"))
    M.grid(upper(1), 8, 4, CU, ins, T, skip=("v0", "v1", "u0", "u1"))
    M.box((0, 0, H + 0.05), (2 * X1 + 0.4, 0.26, 0.14), CU)   # 箱棟

    for sx in (-1, 1):
        x = sx * X1
        M.poly([(x, -Y1, Z1), (x, Y1, Z1), (x, 0, H)], PLA, (0, 0, 2.5))   # 妻壁
        for sy in (-1, 1):
            A = (x, sy * Y1, Z1)
            B = (x, 0, H)
            d = unit(sub(B, A))
            q = unit((0, -d[2], d[1]))
            if q[2] < 0:
                q = mul(q, -1)
            # 破風板(薄く、見付 0.24)
            M.prism([A, B, add(B, mul(q, 0.24)), add(A, mul(q, 0.24))], (sx * 0.05, 0, 0), PL)

    return dict(fp=(10.0, 10.8), col=[cb(-4.4, 4.4, -3.0, 3.0, 0, 4.95)])


# ---------------------------------------------------------------------------
# 神社: 本殿(流造・高床)
# ---------------------------------------------------------------------------
def build_honden(M):
    W, DK, PL, ST, TILE = "wood_ni", "wood_dark", "wood_plain", "stone", "roof_tile"
    SAG = 0.12
    T = 0.12

    # 石の基礎と丹塗の柱
    for x in (-2.4, 0.0, 2.4):
        for y in (-2.3, 1.8):
            M.box((x, y, -0.1), (0.4, 0.4, 0.4), ST)
            M.cyl((x, y, 0.1), (x, y, 1.0), 0.13, 0.13, 8, W)
    M.box((0, -0.2, 1.1), (5.4, 4.6, 0.2), PL)          # 床
    M.box((0, 0, 2.7), (4.4, 3.6, 3.0), PL)              # 身舎 1.2..4.2
    M.box((0, 0, 4.12), (4.6, 3.8, 0.26), W)             # 桁(屋根の下を埋める。屋根面の内側に収める)
    M.box((0, -1.83, 2.5), (1.6, 0.06, 2.6), DK)         # 扉

    # 階(3段)
    for k in range(3):
        top = 1.2 - 0.4 * (k + 1)
        y0 = -2.5 - 0.3 * (k + 1)
        y1 = -2.5 - 0.3 * k
        M.box((0, (y0 + y1) / 2, (top - 0.3) / 2), (1.6, y1 - y0, top + 0.3), ST)

    # 流造の屋根(前が長く、後ろは短い)
    XR = 2.8
    RY, RZ = 0.3, 5.8

    def roof_front(u, v):
        x = -XR + 2 * XR * u
        y = RY + (-3.4 - RY) * v
        z = RZ + (3.5 - RZ) * v - SAG * math.sin(PI * v)
        return (x, y, z)

    def roof_back(u, v):
        x = -XR + 2 * XR * u
        y = RY + (2.4 - RY) * v
        z = RZ + (3.9 - RZ) * v - SAG * math.sin(PI * v)
        return (x, y, z)

    M.grid(roof_front, 8, 4, TILE, (0, 0, 2.5), T, skip=("v0",))
    M.grid(roof_back, 8, 4, TILE, (0, 0, 2.5), T, skip=("v0",))
    M.box((0, RY, RZ + 0.06), (2 * XR, 0.22, 0.16), TILE)   # 棟

    # 鰹木(棟の上を横切る丸太)
    for x in (-2.0, -1.0, 0.0, 1.0, 2.0):
        M.cyl((x, -0.6, RZ + 0.14), (x, 1.2, RZ + 0.14), 0.09, 0.09, 6, PL)

    # 妻壁と千木
    for sx in (-1, 1):
        x = sx * 2.2
        M.poly([(x, -1.8, 4.2), (x, 1.8, 4.2), (x, RY, RZ)], PL, (0, 0, 2.5))
        xe = sx * (XR + 0.05)
        M.beam((xe, -0.9, 5.6), (xe, 1.5, 6.4), 0.12, 0.12, PL, up=(1.0, 0.0, 0.0))
        M.beam((xe, 1.5, 5.6), (xe, -0.9, 6.4), 0.12, 0.12, PL, up=(1.0, 0.0, 0.0))

    return dict(fp=(5.6, 6.8), col=[cb(-2.2, 2.2, -1.8, 1.8, 0, 4.2)])


# ---------------------------------------------------------------------------
# 鳥居(丹塗・石) 明神鳥居
# ---------------------------------------------------------------------------
def build_torii_common(M, pm):
    xs_top = 1.66
    for sx in (-1, 1):
        xb = sx * 1.8
        xt = sx * xs_top
        M.box((xb, 0, -0.1), (0.9, 0.9, 0.4), "stone")
        M.cyl((xb, 0, 0.2), (xb, 0, 0.5), 0.42, 0.32, 8, "stone")          # 亀腹
        M.cyl((xb, 0, 0.5), (xt, 0, 4.05), 0.18, 0.16, 8, pm)              # 柱(転び)
    def zk(x):
        return 4.1 + 0.22 * (abs(x) / 2.3) ** 2.2
    xs = [-2.3 + 4.6 * i / 6 for i in range(7)]
    for i in range(6):
        M.beam((xs[i], 0, zk(xs[i])), (xs[i + 1], 0, zk(xs[i + 1])), 0.42, 0.24, pm)   # 笠木(両端が反る)
    M.box((0, 0, 3.9), (4.0, 0.46, 0.14), pm)                                # 島木
    M.beam((-1.72, 0, 2.7), (1.72, 0, 2.7), 0.22, 0.24, pm)                  # 貫
    M.box((0, 0, 3.25), (0.7, 0.06, 0.5), pm)                                # 額
    return dict(fp=(4.6, 1.0), col=[cb(x - 0.2, x + 0.2, -0.2, 0.2, 0, 4.1) for x in (-1.75, 1.75)])


def build_torii(M):
    return build_torii_common(M, "wood_ni")


def build_torii_ishi(M):
    return build_torii_common(M, "stone")


# ---------------------------------------------------------------------------
# 灯籠(春日灯籠)
# ---------------------------------------------------------------------------
def build_toro(M):
    ST, GL, GOLD = "stone", "glow_lantern", "gold"
    M.box((0, 0, -0.03), (0.62, 0.62, 0.54), ST)              # 基礎 -0.3..0.24
    M.box((0, 0, 0.29), (0.5, 0.5, 0.1), ST)                  # 地蓋 0.24..0.34
    M.cyl((0, 0, 0.34), (0, 0, 1.02), 0.11, 0.09, 8, ST)      # 竿
    M.box((0, 0, 1.11), (0.46, 0.46, 0.18), ST)               # 中台 1.02..1.2
    M.box((0, 0, 1.41), (0.4, 0.4, 0.42), ST)                 # 火袋の枠 1.2..1.62
    for (dx, dy) in ((0, -0.2), (0, 0.2), (-0.2, 0), (0.2, 0)):   # 火袋の窓(灯る)
        if dy:
            M.box((dx, dy, 1.41), (0.2, 0.02, 0.26), GL)
        else:
            M.box((dx, dy, 1.41), (0.02, 0.2, 0.26), GL)
    M.rings([[(0.52 * math.cos(2 * PI * i / 6 + PI / 6), 0.52 * math.sin(2 * PI * i / 6 + PI / 6), 1.60)
              for i in range(6)],
             [(0.49 * math.cos(2 * PI * i / 6 + PI / 6), 0.49 * math.sin(2 * PI * i / 6 + PI / 6), 1.64)
              for i in range(6)],
             [(0.38 * math.cos(2 * PI * i / 6 + PI / 6), 0.38 * math.sin(2 * PI * i / 6 + PI / 6), 1.70)
              for i in range(6)],
             [(0.20 * math.cos(2 * PI * i / 6 + PI / 6), 0.20 * math.sin(2 * PI * i / 6 + PI / 6), 1.78)
              for i in range(6)],
             [(0.0, 0.0, 1.86)] * 6], ST)                     # 笠(六角・軒が反る)
    M.cyl((0, 0, 1.86), (0, 0, 1.93), 0.03, 0.03, 6, ST)
    M.ellipsoid((0, 0, 2.02), 0.09, 0.09, 0.09, GOLD, 6, 3)  # 宝珠
    return dict(fp=(0.62, 0.62), col=[cb(-0.32, 0.32, -0.32, 0.32, 0, 1.2)])


# ---------------------------------------------------------------------------
# 狛犬(阿)・ミラーで吽
# ---------------------------------------------------------------------------
def build_komainu(M):
    ST = "stone"
    M.box((0, 0, -0.05), (0.68, 0.62, 0.5), ST)               # 台座 -0.3..0.2
    M.box((0, 0.02, 0.5), (0.46, 0.5, 0.6), ST)               # 胴
    M.ellipsoid((0, 0.22, 0.36), 0.27, 0.26, 0.2, ST, 6, 3)    # 後脚・尻
    for sx in (-1, 1):
        M.box((sx * 0.15, -0.26, 0.3), (0.14, 0.16, 0.3), ST)    # 前脚
        M.box((sx * 0.15, -0.36, 0.14), (0.16, 0.2, 0.12), ST)   # 前足
        M.box((sx * 0.27, -0.2, 1.1), (0.08, 0.22, 0.34), ST)    # たてがみ(横)
        M.cyl((sx * 0.1, -0.2, 1.30), (sx * 0.1, -0.2, 1.5), 0.07, 0.0, 4, ST)   # 耳
    M.box((0, -0.12, 0.72), (0.42, 0.22, 0.4), ST)            # 胸
    M.box((0, -0.2, 1.14), (0.36, 0.34, 0.36), ST)            # 頭
    M.box((0, -0.40, 1.02), (0.26, 0.14, 0.2), ST)            # 鼻先
    M.box((0, 0.02, 1.14), (0.52, 0.2, 0.44), ST)             # たてがみ(後)
    M.beam((0.24, 0.3, 0.25), (0.26, 0.42, 0.75), 0.1, 0.1, ST, up=(1.0, 0.0, 0.0))   # 尾
    return dict(fp=(0.7, 0.7), col=[cb(-0.35, 0.35, -0.35, 0.35, 0, 1.4)])


# ---------------------------------------------------------------------------
# 手水舎
# ---------------------------------------------------------------------------
def build_chozuya(M):
    ST, TILE, W, PL, WB = "stone", "roof_tile", "wood_ni", "wood_plain", "water_basin"
    M.box((0, 0, -0.15), (3.2, 2.6, 0.3), ST)                 # 基壇
    for x in (-1.25, 1.25):
        for y in (-0.85, 0.85):
            M.cyl((x, y, 0.0), (x, y, 2.5), 0.1, 0.1, 8, W)
    # 水盤
    M.box((0, 0, 0.09), (1.6, 1.0, 0.18), ST)
    M.box((-0.74, 0, 0.39), (0.12, 1.0, 0.42), ST)
    M.box((0.74, 0, 0.39), (0.12, 1.0, 0.42), ST)
    M.box((0, -0.44, 0.39), (1.6, 0.12, 0.42), ST)
    M.box((0, 0.44, 0.39), (1.6, 0.12, 0.42), ST)
    M.box((0, 0, 0.5), (1.36, 0.76, 0.02), WB)
    # 切妻屋根(軒が四隅で反る)
    def roof(sy):
        def f(u, v):
            x = -1.7 + 3.4 * u
            y = sy * 1.5 * (1 - v)
            z = 2.5 + 1.0 * v + 0.12 * (abs(x) / 1.7) ** 3 * (1 - v) - 0.08 * math.sin(PI * v)
            return (x, y, z)
        return f
    M.grid(roof(-1), 6, 3, TILE, (0, 0, 2.0), 0.12, skip=("v1",))
    M.grid(roof(1), 6, 3, TILE, (0, 0, 2.0), 0.12, skip=("v1",))
    for sx in (-1, 1):
        x = sx * 1.7
        M.poly([(x, -1.5, 2.5), (x, 1.5, 2.5), (x, 0, 3.5)], PL, (0, 0, 2.0))
    return dict(fp=(3.2, 2.6),
                col=[cb(x - 0.15, x + 0.15, y - 0.15, y + 0.15, 0, 2.5) for x in (-1.25, 1.25) for y in (-0.85, 0.85)]
                + [cb(-0.8, 0.8, -0.5, 0.5, 0, 0.6)])


# ---------------------------------------------------------------------------
# 社務所(寄棟・瓦・授与所の窓)
# ---------------------------------------------------------------------------
def build_shamusho(M):
    ST, TILE, DK, PL, PLA, GL = "stone", "roof_tile", "wood_dark", "wood_plain", "plaster", "glow_window"
    M.box((0, 0, -0.1), (7.4, 4.4, 0.4), ST)
    M.box((0, 0, (0.1 + 3.2) / 2), (7.2, 4.2, 3.1), PLA)
    hip_roof(M, 4.0, 2.5, 2.8, 4.5, TILE, 0.14)
    M.box((0, 0, 4.5 + 0.04), (3.0, 0.3, 0.14), TILE)        # 棟
    M.box((-1.9, -2.12, 1.35), (1.6, 0.06, 2.5), PL)        # 引き戸
    M.box((2.1, -2.13, 1.7), (1.5, 0.04, 1.2), GL)          # 授与所の窓
    frame(M, 2.1, -2.12, 1.7, 1.7, 1.4, 0.12, DK)
    M.box((2.1, -2.45, 0.98), (1.7, 0.6, 0.1), PL)          # 授与台
    M.box((3.63, 0.0, 1.7), (0.04, 1.2, 1.2), GL)           # 側面の窓
    return dict(fp=(8.0, 5.0), col=[cb(-3.6, 3.6, -2.1, 2.1, 0, 3.2)])


# ---------------------------------------------------------------------------
# 玉垣・石段・太鼓橋・地蔵
# ---------------------------------------------------------------------------
def build_tamagaki(M):
    ST = "stone"
    for x in (-1.5, 1.5):
        M.box((x, 0, 0.35), (0.3, 0.3, 1.3), ST)               # 親柱 -0.3..1.0
    for i in range(9):
        x = -1.2 + 0.3 * i
        M.box((x, 0, 0.35), (0.14, 0.14, 1.3), ST)             # 小柱
    M.box((0, 0, 1.05), (3.04, 0.3, 0.1), ST)                  # 笠石 1.0..1.1
    return dict(fp=(3.0, 0.3), col=[cb(-1.5, 1.5, -0.15, 0.15, 0, 1.1)])


def build_ishidan(M):
    ST = "stone"
    for k in range(10):
        y0 = -1.5 + 0.3 * k
        top = 0.15 * (k + 1)
        M.box((0, y0 + 0.15, (top - 0.3) / 2), (3.0, 0.3, top + 0.3), ST)
    return dict(fp=(3.0, 3.0), col=[cb(-1.5, 1.5, -1.5, -0.6, 0, 0.45),
                                    cb(-1.5, 1.5, -0.6, 0.3, 0, 0.9),
                                    cb(-1.5, 1.5, 0.3, 1.5, 0, 1.5)])


def build_hashi(M):
    W, ST = "wood_ni", "stone"

    def zd(y):
        return 0.2 + 1.1 * (1 - (y / 3.0) ** 2)

    M.grid(lambda u, v: (-1.1 + 2.2 * u, -3.0 + 6.0 * v, zd(-3.0 + 6.0 * v)), 4, 12, W, (0, 0, -1.0), 0.12)
    for y in (-3.1, 3.1):
        M.box((0, y, -0.05), (2.4, 0.5, 0.5), ST)              # 橋詰め
    for sx in (-1, 1):
        ys = [-2.7 + 5.4 * i / 7 for i in range(8)]
        for y in ys:
            z = zd(y)
            M.box((sx * 1.05, y, z + 0.51), (0.08, 0.08, 0.78), W)   # 高欄の束
        pts = [(sx * 1.05, y, zd(y) + 0.9) for y in [-3.0 + 6.0 * i / 6 for i in range(7)]]
        for i in range(6):
            M.beam(pts[i], pts[i + 1], 0.1, 0.08, W, up=(0.0, 0.0, 1.0))   # 高欄の笠
    col = []
    for (a, b) in ((-3.0, -1.5), (-1.5, 0.0), (0.0, 1.5), (1.5, 3.0)):
        col.append(cb(-1.1, 1.1, a, b, 0, zd((a + b) / 2) + 0.12))
    for sx in (-1, 1):
        for (a, b) in ((-3.0, 0.0), (0.0, 3.0)):
            top = max(zd(a), zd(b), zd((a + b) / 2)) + 0.9
            x = sx * 1.05
            col.append(cb(x - 0.05, x + 0.05, a, b, 0, top))
    return dict(fp=(2.4, 6.4), col=col)


def build_jizo(M):
    ST = "stone"
    M.box((0, 0, -0.11), (0.42, 0.36, 0.38), ST)               # 台座 -0.3..0.08
    M.cyl((0, 0, 0.08), (0, 0, 0.6), 0.2, 0.14, 8, ST)          # 身
    M.ellipsoid((0, 0, 0.76), 0.13, 0.13, 0.14, ST, 8, 4)        # 頭
    M.box((0, -0.19, 0.42), (0.22, 0.04, 0.46), "cloth_red")     # 赤い前掛け
    return dict(fp=(0.5, 0.5), col=[cb(-0.25, 0.25, -0.25, 0.25, 0, 0.9)])


# ---------------------------------------------------------------------------
# 岩(icosphere を乱数で歪める)
# ---------------------------------------------------------------------------
def icosphere(sub):
    t = (1 + 5 ** 0.5) / 2
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
             (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    verts = [unit(v) for v in verts]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
             (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
             (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(sub):
        cache = {}

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                verts.append(unit(mul(add(verts[a], verts[b]), 0.5)))
                cache[key] = len(verts) - 1
            return cache[key]

        nf = []
        for a, b, c in faces:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = nf
    return verts, faces


def build_rock(M, seed, rx, ry, rz, sub):
    rng = random.Random(seed)
    V, F = icosphere(sub)
    P = []
    for v in V:
        r = 1 + rng.uniform(-0.2, 0.2)
        P.append((v[0] * rx * r, v[1] * ry * r, v[2] * rz * r))
    zmin = min(p[2] for p in P)
    P = [(p[0], p[1], p[2] - zmin - 0.3) for p in P]           # 底は地面の 0.3m 下
    C = centroid(P)
    for f in F:
        tri = [P[i] for i in f]
        n = unit(newell(tri))
        mat = "stone_moss" if n[2] > 0.6 else "stone"
        M.poly(tri, mat, C)
    bb = bbox(M)
    return dict(fp=(round(bb[1] - bb[0], 2) + 0.2, round(bb[3] - bb[2], 2) + 0.2),
                col=[cb(bb[0] + 0.1, bb[1] - 0.1, bb[2] + 0.1, bb[3] - 0.1, 0, bb[5] * 0.8)])


def build_iwa_l(M):
    return build_rock(M, 11, 1.3, 1.1, 1.0, 2)


def build_iwa_s(M):
    return build_rock(M, 23, 0.5, 0.45, 0.4, 1)


# ---------------------------------------------------------------------------
# 木: 幹 trunk、葉 leaf_<種>。1本 180 三角形以下。
# ---------------------------------------------------------------------------
def tree_col():
    return [cb(-0.2, 0.2, -0.2, 0.2, 0, 2.0)]


def blob(M, c, rx, ry, rz, mat, rng, nu=7, nv=3, j=0.14):
    """歪めた楕円体の葉塊(極は歪めない。乱数は seed 固定の rng)。"""
    R = []
    for k in range(nv + 1):
        th = PI * k / nv
        ring = []
        for i in range(nu):
            ph = 2 * PI * i / nu
            s = 1.0 if k in (0, nv) else 1.0 + rng.uniform(-j, j)
            ring.append((c[0] + rx * s * math.sin(th) * math.cos(ph),
                         c[1] + ry * s * math.sin(th) * math.sin(ph),
                         c[2] + rz * s * math.cos(th)))
        R.append(ring)
    M.rings(R, mat)


def jcyl(M, p0, p1, r0, r1, n, mat, rng, j=0.1):
    """わずかに歪めた円柱・円錐(r1=0 で錐)。"""
    d = unit(sub(p1, p0))
    ref = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = unit(cross(d, ref))
    v = unit(cross(d, u))
    R = []
    for p, r in ((p0, r0), (p1, r1)):
        ring = []
        for i in range(n):
            a = 2 * PI * i / n
            s = 1.0 + rng.uniform(-j, j)
            ring.append(add(p, add(mul(u, r * s * math.cos(a)), mul(v, r * s * math.sin(a)))))
        R.append(ring)
    M.rings(R, mat)


def build_sugi(M):
    rng = random.Random(301)
    M.cyl((0, 0, -0.3), (0, 0, 13.0), 0.22, 0.1, 6, "trunk")
    for z0, z1, R in [(1.5, 6.5, 2.5), (4.2, 9.5, 2.0), (7.5, 11.5, 1.4), (10.0, 14.0, 0.7)]:
        jcyl(M, (0, 0, z0), (0, 0, z1), R, 0.0, 8, "leaf_sugi", rng, j=0.12)
    return dict(fp=(1.2, 1.2), col=tree_col())


def build_matsu(M):
    rng = random.Random(302)
    M.cyl((0, 0, -0.3), (0.35, 0, 4.0), 0.2, 0.17, 5, "trunk")
    M.cyl((0.35, 0, 4.0), (-0.25, 0, 6.9), 0.17, 0.09, 5, "trunk")
    # 段違いの平たい葉塊 4 個(幅 2.5〜3.5m)
    blob(M, (1.2, 0.2, 6.5), 1.5, 1.3, 0.45, "leaf_matsu", rng, nu=7, nv=3)
    blob(M, (-1.3, -0.2, 6.9), 1.25, 1.2, 0.42, "leaf_matsu", rng, nu=7, nv=3)
    blob(M, (0.5, -0.4, 7.6), 1.75, 1.45, 0.45, "leaf_matsu", rng, nu=7, nv=3)
    blob(M, (-0.4, 0.4, 6.0), 1.4, 1.2, 0.4, "leaf_matsu", rng, nu=7, nv=3)
    return dict(fp=(1.2, 1.2), col=tree_col())


def build_take(M):
    rng = random.Random(303)
    # 稈 4 本。根元は外へ広がり、上へ行くほど少し外へしなる
    stems = [((0.35, 0.2), (0.45, 0.25)), ((-0.35, 0.25), (-0.5, 0.3)),
             ((0.1, -0.4), (0.15, -0.55)), ((-0.4, -0.2), (-0.55, -0.25))]
    for (bx, by), (tx, ty) in stems:
        jcyl(M, (bx, by, -0.3), (tx, ty, 7.5), 0.09, 0.06, 4, "trunk_take", rng, j=0.06)
    # 葉: 稈の上半分(3.5〜7.5m)を覆う縦長の紡錘形
    for (bx, by), (tx, ty) in stems:
        t = (5.5 + 0.3) / 7.8
        cx = bx + (tx - bx) * t
        cy = by + (ty - by) * t
        blob(M, (cx, cy, 5.5), 0.6, 0.6, 2.0, "leaf_take", rng, nu=5, nv=4, j=0.1)
    return dict(fp=(1.2, 1.2), col=tree_col())


def build_sakura(M):
    rng = random.Random(304)
    # 太い幹(根元径 0.35m)。1.8m あたりから 3 本に分かれる
    M.cyl((0, 0, -0.3), (0, 0, 1.8), 0.175, 0.13, 6, "trunk")
    M.beam((0, 0, 1.7), (1.6, 0.5, 3.2), 0.22, 0.22, "trunk")
    M.beam((0, 0, 1.7), (-1.5, -0.4, 3.4), 0.22, 0.22, "trunk")
    M.beam((0, 0, 1.7), (0.3, -1.2, 3.0), 0.2, 0.2, "trunk")
    # 横に広い傘形の樹冠(幅 6〜7m、厚み約 3m、下端 約 2m)
    blob(M, (0, 0, 4.5), 2.9, 2.5, 1.5, "leaf_sakura", rng, nu=7, nv=3)
    blob(M, (1.5, 0.4, 4.0), 2.1, 2.0, 1.3, "leaf_sakura", rng, nu=7, nv=3)
    blob(M, (-1.6, -0.3, 3.5), 2.0, 1.9, 1.3, "leaf_sakura", rng, nu=7, nv=3)
    blob(M, (0.2, -1.0, 3.2), 1.6, 1.5, 1.1, "leaf_sakura", rng, nu=7, nv=3)
    return dict(fp=(1.2, 1.2), col=tree_col())


def build_kaede(M):
    rng = random.Random(305)
    M.cyl((0, 0, -0.3), (0, 0, 2.2), 0.1, 0.07, 6, "trunk")
    M.beam((0, 0, 1.9), (1.2, 0.3, 3.0), 0.16, 0.16, "trunk")
    M.beam((0, 0, 1.9), (-1.1, -0.2, 3.2), 0.16, 0.16, "trunk")
    # 細い幹。やや平たい層状の樹冠(幅 5m、下端 約 1.8m)
    blob(M, (0, 0, 2.7), 2.5, 2.3, 0.9, "leaf_kaede", rng, nu=7, nv=3)
    blob(M, (0.6, 0.4, 3.9), 2.2, 2.0, 0.9, "leaf_kaede", rng, nu=7, nv=3)
    blob(M, (-0.5, -0.3, 4.9), 1.6, 1.5, 0.7, "leaf_kaede", rng, nu=7, nv=3)
    return dict(fp=(1.2, 1.2), col=tree_col())


# ---------------------------------------------------------------------------
# 街: 家(瓦)・家(茅葺)・電柱
# ---------------------------------------------------------------------------
def build_ie_kawara(M):
    ST, TILE, DK, PL, PLA, GL = "stone", "roof_tile", "wood_dark", "wood_plain", "plaster", "glow_window"
    M.box((0, 0, -0.05), (6.6, 4.6, 0.7), ST)                       # 基礎
    M.box((0, 0, (0.3 + 3.3) / 2), (6.4, 4.4, 3.0), PLA)            # 壁
    M.box((0, -2.6, 0.4), (6.4, 0.8, 0.2), PL)                      # 縁
    for x in (-3.0, 3.0):
        M.cyl((x, -2.95, 0.5), (x, -2.95, 2.7), 0.07, 0.07, 6, DK)  # 縁の柱
    zr, ze, ex, ey = 4.9, 2.9, 4.0, 2.9
    ins = (0, 0, 2.5)
    M.slab([(-ex, -ey, ze), (ex, -ey, ze), (ex, 0, zr), (-ex, 0, zr)], TILE, ins, 0.14)
    M.slab([(-ex, ey, ze), (-ex, 0, zr), (ex, 0, zr), (ex, ey, ze)], TILE, ins, 0.14)
    M.box((0, 0, zr + 0.02), (2 * ex + 0.1, 0.3, 0.14), TILE)      # 棟
    for sx in (-1, 1):
        M.poly([(sx * ex, -ey, ze), (sx * ex, ey, ze), (sx * ex, 0, zr)], PL, (0, 0, 2.5))
    # 窓(glow_window)・引き戸
    M.box((-1.55, -2.22, 1.7), (1.9, 0.04, 1.2), GL)
    M.box((1.55, -2.22, 1.7), (1.9, 0.04, 1.2), GL)
    frame(M, -1.55, -2.2, 1.7, 1.9, 1.2, 0.08, DK)
    frame(M, 1.55, -2.2, 1.7, 1.9, 1.2, 0.08, DK)
    M.box((0, -2.23, 1.45), (0.9, 0.05, 2.1), PL)
    M.box((3.22, 0, 1.7), (0.04, 1.3, 1.2), GL)
    frame(M, 3.2, 0.0, 1.7, 1.3, 1.2, 0.08, DK, face=1)
    return dict(fp=(8.0, 6.0), col=[cb(-3.2, 3.2, -2.2, 2.2, 0, 3.3)])


def build_ie_kayabuki(M):
    EARTH, THATCH, DK, GL = "earth", "roof_thatch", "wood_dark", "glow_window"
    M.box((0, 0, (0.0 + 3.7) / 2), (7.0, 4.4, 3.7), EARTH)           # 土壁
    hip_roof(M, 4.5, 3.0, 3.0, 6.2, THATCH, 0.6)                    # 厚い寄棟(茅)
    M.box((0, 0, 6.3), (3.0, 0.9, 0.4), THATCH)                     # 棟の茅
    M.box((-1.7, -2.22, 1.9), (1.2, 0.04, 1.1), GL)
    M.box((1.7, -2.22, 1.9), (1.2, 0.04, 1.1), GL)
    frame(M, -1.7, -2.2, 1.9, 1.2, 1.1, 0.08, DK)
    frame(M, 1.7, -2.2, 1.9, 1.2, 1.1, 0.08, DK)
    M.box((0, -2.23, 1.15), (0.9, 0.05, 2.3), DK)                   # 戸口
    return dict(fp=(9.0, 6.0), col=[cb(-3.5, 3.5, -2.2, 2.2, 0, 3.7)])


def build_denchu(M):
    DK, PLA, TILE = "wood_dark", "plaster", "roof_tile"
    M.cyl((0, 0, -0.3), (0, 0, 8.0), 0.14, 0.1, 8, DK)           # 電柱
    M.box((0, 0, 7.7), (1.8, 0.12, 0.12), DK)                     # 腕金
    M.box((0, 0, 7.1), (1.4, 0.12, 0.12), DK)
    for x in (-0.6, 0.6):
        M.ellipsoid((x, 0, 7.85), 0.07, 0.07, 0.08, PLA, 6, 3)   # 碍子
        M.ellipsoid((x, 0, 7.25), 0.07, 0.07, 0.08, PLA, 6, 3)
    M.box((0, 0.25, 5.2), (0.5, 0.4, 0.6), TILE)                  # 変圧器
    return dict(fp=(1.8, 0.6), col=[cb(-0.2, 0.2, -0.2, 0.2, 0, 8.0)])


# ---------------------------------------------------------------------------
# 歩行用の人(カタログ外)。身長 1.6m、作務衣風、正面=-Y
# ---------------------------------------------------------------------------
def build_avatar(M):
    CL, SK, DK = "cloth_gray", "skin", "wood_dark"
    M.box((-0.1, 0, 0.42), (0.16, 0.18, 0.84), CL)               # 脚
    M.box((0.1, 0, 0.42), (0.16, 0.18, 0.84), CL)
    M.box((0, 0, 1.12), (0.44, 0.24, 0.56), CL)                  # 胴(作務衣)
    M.box((0, 0, 1.42), (0.14, 0.14, 0.08), SK)                  # 首
    M.ellipsoid((0, 0, 1.48), 0.12, 0.12, 0.12, SK, 6, 3)        # 頭
    M.ellipsoid((0, 0.01, 1.52), 0.125, 0.125, 0.08, DK, 6, 3)   # 髪
    for sx in (-1, 1):
        M.beam((sx * 0.26, 0, 1.36), (sx * 0.28, 0, 0.85), 0.13, 0.13, CL, up=(0.0, 1.0, 0.0))
        M.ellipsoid((sx * 0.28, 0, 0.8), 0.05, 0.05, 0.05, SK, 4, 2)
    return dict(fp=None, col=None)


# ---------------------------------------------------------------------------
# モデル一覧(id, 名前, カテゴリ, 並び順, 関数, 追加属性)
# ---------------------------------------------------------------------------
MODELS = [
    dict(id="haiden", name="拝殿", cat="shrine", order=10, fn=build_haiden),
    dict(id="honden", name="本殿", cat="shrine", order=20, fn=build_honden),
    dict(id="torii", name="鳥居", cat="shrine", order=30, fn=build_torii),
    dict(id="torii_ishi", name="鳥居(石)", cat="shrine", order=40, fn=build_torii_ishi),
    dict(id="toro", name="灯籠", cat="shrine", order=50, fn=build_toro, glow="lantern"),
    dict(id="komainu_a", name="狛犬(阿)", cat="shrine", order=60, fn=build_komainu),
    dict(id="komainu_un", name="狛犬(吽)", cat="shrine", order=70, fn=build_komainu, mirror=True),
    dict(id="chozuya", name="手水舎", cat="shrine", order=80, fn=build_chozuya),
    dict(id="shamusho", name="社務所", cat="shrine", order=90, fn=build_shamusho, glow="window"),
    dict(id="tamagaki", name="玉垣", cat="shrine", order=100, fn=build_tamagaki),
    dict(id="ishidan", name="石段", cat="shrine", order=110, fn=build_ishidan),
    dict(id="hashi", name="太鼓橋", cat="shrine", order=120, fn=build_hashi),
    dict(id="jizo", name="地蔵", cat="shrine", order=130, fn=build_jizo),
    dict(id="sugi", name="杉", cat="nature", order=10, fn=build_sugi, tree=True),
    dict(id="sakura", name="桜", cat="nature", order=20, fn=build_sakura, tree=True),
    dict(id="kaede", name="楓", cat="nature", order=30, fn=build_kaede, tree=True),
    dict(id="matsu", name="松", cat="nature", order=40, fn=build_matsu, tree=True),
    dict(id="take", name="竹", cat="nature", order=50, fn=build_take, tree=True),
    dict(id="iwa_l", name="岩(大)", cat="nature", order=60, fn=build_iwa_l),
    dict(id="iwa_s", name="岩(小)", cat="nature", order=70, fn=build_iwa_s),
    dict(id="ie_kawara", name="家(瓦)", cat="town", order=10, fn=build_ie_kawara, glow="window"),
    dict(id="ie_kayabuki", name="家(茅葺)", cat="town", order=20, fn=build_ie_kayabuki, glow="window"),
    dict(id="denchu", name="電柱", cat="town", order=30, fn=build_denchu),
    dict(id="avatar", name="歩行用の人", cat=None, order=0, fn=build_avatar),
]


# ---------------------------------------------------------------------------
# Blender 出力
# ---------------------------------------------------------------------------
def bpy_modules():
    import bpy  # noqa: F401  (headless: pip install bpy)
    return bpy


def make_material(key):
    bpy = bpy_modules()
    hexcol, rough = PALETTE[key]
    mat = bpy.data.materials.get(key) or bpy.data.materials.new(key)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    rgba = hex_to_linear(hexcol) + (1.0,)
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = 0.0
    mat.diffuse_color = rgba
    return mat


def to_object(M, name):
    bpy = bpy_modules()
    me = bpy.data.meshes.new(name)
    me.from_pydata(M.verts, [], M.tris)
    me.update()
    for key in M.mats:
        me.materials.append(make_material(key))
    for poly, mi in zip(me.polygons, M.tmat):
        poly.material_index = mi
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def export_glb(path):
    bpy = bpy_modules()
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=False,
        export_yup=True,
        export_apply=False,
        export_materials="EXPORT",
        export_image_format="NONE",
        export_draco_mesh_compression_enable=False,
        export_animations=False,
        export_skins=False,
        export_lights=False,
        export_cameras=False,
    )


def reset_scene():
    bpy = bpy_modules()
    bpy.ops.wm.read_factory_settings(use_empty=True)


def godot_box(b):
    x0, x1, y0, y1, z0, z1 = b
    return {"pos": [r2((x0 + x1) / 2), r2((z0 + z1) / 2), r2(-(y0 + y1) / 2)],
            "size": [r2(x1 - x0), r2(z1 - z0), r2(y1 - y0)]}


def triangle_count(M):
    return len(M.tris)


def build_one(spec):
    M = Mesh()
    if spec.get("mirror"):
        M.mx = -1.0
    meta = spec["fn"](M)
    return M, meta


def render_sheets(sheets):
    """確認用レンダ(Workbench)。sheets: [(名前, [id...], 距離m, カメラ方向(x,y,z の比))]。
    カメラは -Y 側(正面)から見る。"""
    bpy = bpy_modules()
    from mathutils import Matrix, Vector
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    for name, ids, dist, offset in sheets:
        reset_scene()
        sc = bpy.context.scene
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.display.shading.light = "STUDIO"
        sc.display.shading.color_type = "MATERIAL"
        sc.display.shading.background_type = "WORLD"
        world = bpy.data.worlds.new("preview_world")
        world.color = (0.82, 0.84, 0.86)
        sc.world = world
        sc.render.resolution_x = 1400
        sc.render.resolution_y = 900
        sc.render.image_settings.file_format = "PNG"
        cols = 3 if len(ids) > 2 else len(ids)
        step = {"sheet_small_shrine": 2.6, "sheet_trees": 9.0}.get(name, 14.0) if len(ids) > 1 else 0.0
        for i, mid in enumerate(ids):
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=os.path.join(MODEL_DIR, mid + ".glb"))
            new = [o for o in bpy.data.objects if o not in before]
            ox = (i % cols) * step
            oy = (i // cols) * step
            for o in new:
                o.matrix_world = Matrix.Translation((ox, oy, 0.0)) @ o.matrix_world
        rows = (len(ids) + cols - 1) // cols
        cx = (cols - 1) * step / 2.0
        cy = (rows - 1) * step / 2.0
        cam_data = bpy.data.cameras.new("cam")
        cam_data.lens = 35
        cam = bpy.data.objects.new("cam", cam_data)
        bpy.context.scene.collection.objects.link(cam)
        target = Vector((cx, cy, 2.0))
        ox_, oy_, oz_ = offset
        d = Vector((ox_, oy_, oz_)).normalized()
        loc = target + d * dist
        cam.location = loc
        cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
        sc.camera = cam
        sc.render.filepath = os.path.join(PREVIEW_DIR, name + ".png")
        bpy.ops.render.render(write_still=True)
        print("preview:", sc.render.filepath, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="和風箱庭ゲームの超ローポリ モデルを生成")
    ap.add_argument("--preview", action="store_true", help="確認用レンダを /tmp/lowpoly_preview に作る")
    ap.add_argument("--only", default="", help="カンマ区切りの id だけ書き出す(カタログは作らない)")
    args = ap.parse_args()

    only = set(x for x in args.only.split(",") if x)
    os.makedirs(MODEL_DIR, exist_ok=True)
    catalog_items = []
    table = []

    for spec in MODELS:
        if only and spec["id"] not in only:
            continue
        reset_scene()
        M, meta = build_one(spec)
        obj = to_object(M, spec["id"])
        path = os.path.join(MODEL_DIR, spec["id"] + ".glb")
        export_glb(path)
        bb = bbox(M)
        zmax = math.ceil(bb[5] * 100) / 100.0
        width = bb[1] - bb[0]
        depth = bb[3] - bb[2]
        table.append((spec["id"], triangle_count(M), width, depth, zmax, list(M.mats)))
        if spec["cat"] is None:
            continue
        fp = meta["fp"]
        catalog_items.append({
            "id": spec["id"],
            "name": spec["name"],
            "category": spec["cat"],
            "model": "res://assets/models/%s.glb" % spec["id"],
            "footprint": [r2(fp[0]), r2(fp[1])],
            "colliders": [godot_box(b) for b in meta["col"]],
            "height": zmax,
            "walkable": False,
            **({"glow": spec["glow"]} if spec.get("glow") else {}),
            "tree": bool(spec.get("tree", False)),
            "order": spec["order"],
        })
        # 追加の検査: 三角形上限
        limit = 180 if spec.get("tree") else 4000
        if triangle_count(M) > limit:
            print("WARN triangle limit:", spec["id"], triangle_count(M), file=sys.stderr)

    if not only:
        os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
        with open(CATALOG_PATH, "w", encoding="utf-8") as fh:
            json.dump({"items": catalog_items}, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    print("%-14s %8s %8s %8s %8s  %s" % ("id", "tris", "w(x)", "d(y)", "h(z)", "materials"))
    for row in table:
        print("%-14s %8d %8.2f %8.2f %8.2f  %s" % (row[0], row[1], row[2], row[3], row[4], ",".join(row[5])))

    if args.preview:
        obl = (-0.45, -1.0, 0.55)
        sheets = [
            ("sheet_shrine_a", ["haiden", "honden", "torii", "torii_ishi", "toro", "komainu_a"], 40.0, obl),
            ("sheet_shrine_b", ["komainu_un", "chozuya", "shamusho", "tamagaki", "ishidan", "hashi"], 40.0, obl),
            ("sheet_haiden_obl", ["haiden"], 24.0, obl),
            ("sheet_haiden_front", ["haiden"], 24.0, (0.0, -1.0, 0.18)),
            ("sheet_honden_torii", ["honden", "torii"], 34.0, obl),
            ("sheet_small_shrine", ["komainu_a", "komainu_un", "toro", "jizo"], 16.0, obl),
            ("sheet_nature", ["sugi", "matsu", "take", "sakura", "kaede", "jizo"], 40.0, obl),
            ("sheet_trees", ["sugi", "sakura", "kaede", "matsu", "take", "avatar"], 40.0, obl),
            ("sheet_rock_town", ["iwa_l", "iwa_s", "ie_kawara", "ie_kayabuki", "denchu", "avatar"], 40.0, obl),
        ]
        render_sheets(sheets)


if __name__ == "__main__":
    main()
