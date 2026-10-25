#!/usr/bin/env python3
"""Render the haiden with Cycles (CPU) in a simple shrine precinct.

    HAIDEN_QUALITY=preview|final python3 haiden/blender/render.py --out haiden/out/A-2 [--only front,side]

Loads <out>/haiden.blend, adds ground (gravel), sando (stone path), cedars,
stone lanterns, sky + sun, and renders the views of the variant (stats.json
"id": A-1 -> VIEWS, A-2 -> VIEWS_A2) to <out>/renders/*.png.
Updates <out>/stats.json "renders" with site-root paths renders/<id>/<view>.png.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from hlib import geom as G  # noqa: E402
from hlib.materials import Mats  # noqa: E402

QUALITY = {
    "draft": dict(res=(640, 360), samples=12, bounces=3),
    "preview": dict(res=(960, 540), samples=24, bounces=4),
    "final": dict(res=(1600, 900), samples=64, bounces=6),
}
# A-2: ~1M tris of glossy tiles + 5 views (A-1: 4) -> slightly fewer samples (OIDN denoised)
QUALITY_OVERRIDE = {"A-2v1": {"final": dict(samples=56)}, "A-2": {"final": dict(samples=32)}}

DEBUG_VIEWS = {
    "debug_back": ("背面(確認用)", (13.0, 15.0, 9.0), (0.0, 0.0, 4.5), 28, 40, 30, 2.4, 0.45),
    "debug_top": ("俯瞰(確認用)", (-8.0, -12.0, 13.0), (0.0, -0.5, 4.5), 30, 40, 215, 2.4, 0.45),
    "debug_front": ("正面(確認用)", (0.0, -10.5, 2.4), (0.0, -2.0, 3.3), 30, 45, 200, 2.4, 0.45),
    "debug_under": ("軒下(確認用)", (-6.2, -4.8, 2.4), (-4.5, -3.2, 4.4), 22, 40, 215, 2.4, 0.45),
}

VIEWS = {
    # name: (title, camera loc, target, lens, sun elevation deg, sun azimuth deg, sun strength, sky strength)
    "front_oblique": ("正面斜め", (-9.5, -16.5, 2.6), (0.4, -1.4, 3.9), 30, 38, 215, 2.4, 0.45),
    "side": ("側面", (19.0, -3.5, 3.0), (0.0, -0.8, 4.1), 32, 40, 200, 2.4, 0.45),
    "kohai_closeup": ("向拝アップ", (2.4, -9.8, 1.8), (0.0, -4.3, 3.6), 26, 42, 220, 2.4, 0.45),
    "sunset": ("夕景", (11.0, -15.5, 2.2), (0.0, -1.0, 4.2), 30, 4, 262, 4.5, 0.22),
}

# A-2 (本瓦葺 + 千鳥破風): edge/eave close-ups are the point of this variant
VIEWS_A2 = {
    "front_oblique": ("正面斜め", (-9.5, -16.5, 2.6), (0.4, -1.4, 4.0), 30, 38, 215, 2.4, 0.45),
    "side": ("側面", (19.0, -3.5, 3.0), (0.0, -0.8, 4.2), 32, 40, 200, 2.4, 0.45),
    "kohai_chidori": ("向拝アップ(唐破風と千鳥破風)", (2.8, -11.8, 3.3), (0.0, -3.4, 4.85), 28, 42, 220, 2.4, 0.45),
    "noki_sumi": ("軒先・隅の瓦アップ", (8.6, -7.6, 3.5), (4.55, -3.45, 4.95), 34, 40, 215, 2.4, 0.45),
    "mune_tsuma": ("棟・妻・降棟と鬼瓦", (10.5, -7.8, 9.6), (3.4, -1.2, 6.2), 34, 44, 230, 2.4, 0.45),
}
DEBUG_VIEWS_A2 = {
    "dbg_chidori_top": ("千鳥破風 俯瞰(確認用)", (5.5, -9.0, 10.5), (0.0, -2.0, 5.6), 30, 44, 230, 2.4, 0.45),
    "dbg_valley": ("谷(確認用)", (3.5, -5.0, 8.5), (1.2, -2.0, 5.5), 30, 44, 230, 2.4, 0.45),
    "dbg_karahafu": ("唐破風正面(確認用)", (0.0, -9.5, 4.2), (0.0, -5.0, 4.4), 35, 42, 220, 2.4, 0.45),
    "dbg_gable_foot": ("妻下・箕甲(確認用)", (8.0, -5.5, 6.2), (4.0, -2.2, 5.4), 30, 40, 215, 2.4, 0.45),
    "dbg_back": ("背面(確認用)", (13.0, 15.0, 9.0), (0.0, 0.0, 4.5), 28, 40, 30, 2.4, 0.45),
    "dbg_noki_macro": ("軒先マクロ(確認用)", (3.0, -5.4, 4.25), (2.4, -3.9, 4.55), 40, 40, 215, 2.4, 0.45),
    "dbg_sumi_macro": ("隅マクロ(確認用)", (6.9, -5.9, 5.0), (4.85, -3.65, 5.05), 35, 40, 215, 2.4, 0.45),
    "dbg_kohai_side": ("向拝側面の取合い(確認用)", (5.8, -7.8, 4.8), (1.9, -3.6, 4.7), 30, 40, 215, 2.4, 0.45),
}
# A-2 ver2: finishes (9th field = finish id: nuri 丹塗 / shiraki 白木 / koshoku 古色) + 破風板 close-ups
VIEWS_A2V2 = {
    "front_oblique": ("正面斜め(丹塗)", (-9.5, -16.5, 2.6), (0.4, -1.4, 4.0), 30, 38, 215, 2.4, 0.45, "nuri"),
    "front_oblique_shiraki": ("正面斜め(白木)", (-9.5, -16.5, 2.6), (0.4, -1.4, 4.0), 30, 38, 215, 2.4, 0.45, "shiraki"),
    "front_oblique_koshoku": ("正面斜め(古色)", (-9.5, -16.5, 2.6), (0.4, -1.4, 4.0), 30, 38, 215, 2.4, 0.45, "koshoku"),
    "hafu_kohai": ("唐破風・千鳥破風の破風板(丹塗)", (2.75, -7.6, 4.15), (1.25, -4.6, 4.72), 38, 40, 215, 2.4, 0.45, "nuri"),
    "hafu_kohai_koshoku": ("唐破風・千鳥破風の破風板(古色)", (2.75, -7.6, 4.15), (1.25, -4.6, 4.72), 38, 40, 215, 2.4, 0.45, "koshoku"),
    "hafu_tsuma_shiraki": ("妻の破風板・拝み(白木)", (6.6, -3.9, 6.0), (3.7, -1.1, 6.15), 36, 40, 215, 2.4, 0.45, "shiraki"),
}
DEBUG_VIEWS_A2V2 = dict(DEBUG_VIEWS_A2, **{
    "dbg_hafu_jiri": ("破風尻マクロ(確認用)", (2.9, -6.4, 3.95), (2.0, -5.3, 4.05), 40, 40, 215, 2.4, 0.45, "nuri"),
    "dbg_chidori_ogami": ("千鳥破風 拝み(確認用)", (0.9, -5.6, 5.9), (0.0, -2.95, 6.1), 40, 40, 215, 2.4, 0.45, "nuri"),
    "dbg_tsuma_jiri": ("妻 破風尻(確認用)", (5.4, -3.6, 5.3), (3.7, -2.0, 5.3), 40, 40, 215, 2.4, 0.45, "nuri"),
})
VIEW_SETS = {"A-1": (VIEWS, DEBUG_VIEWS), "A-2v1": (VIEWS_A2, DEBUG_VIEWS_A2), "A-2": (VIEWS_A2V2, DEBUG_VIEWS_A2V2)}


def link(ob, cname="Env"):
    c = bpy.data.collections.get(cname)
    if c is None:
        c = bpy.data.collections.new(cname)
        bpy.context.scene.collection.children.link(c)
    c.objects.link(ob)


def emit(name, mb, mat, M, smooth=30):
    me = mb.to_mesh(name, uv_tile=2.0)
    me.materials.append(M[mat])
    if smooth:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(smooth))
    ob = bpy.data.objects.new(name, me)
    link(ob)
    return ob


def build_env(stats):
    M = Mats()
    rng = np.random.default_rng(3)
    # ground: large gravel plane with mild undulation
    n = 120
    xs = np.linspace(-250, 250, n)
    X, Y = np.meshgrid(xs, xs)
    Z = 0.03 * np.sin(X * 0.7) * np.cos(Y * 0.5) - 0.01
    V = np.stack([X, Y, Z], -1).reshape(-1, 3)
    F = G.grid_faces(n, n)
    emit("Env_Ground_Gravel", G.MB().add(V, F), "Env_Gravel", M, smooth=60)
    # sando: stone paving from the front steps toward the camera
    mb = G.MB()
    y0 = stats.get("_kidan_front", -5.95)
    y = y0
    k = 0
    while y > -40:
        L = rng.uniform(0.55, 0.75)
        if k % 2 == 0:
            mb.addt(G.cbox((-1.25, y - L + 0.01, -0.05), (1.25, y - 0.01, 0.04 + rng.uniform(-0.006, 0.006)), 0.02))
        else:
            mid = rng.uniform(-0.3, 0.3)
            mb.addt(G.cbox((-1.25, y - L + 0.01, -0.05), (mid - 0.01, y - 0.01, 0.04 + rng.uniform(-0.006, 0.006)), 0.02))
            mb.addt(G.cbox((mid + 0.01, y - L + 0.01, -0.05), (1.25, y - 0.01, 0.04 + rng.uniform(-0.006, 0.006)), 0.02))
        y -= L
        k += 1
    # curb stones
    for sx in (-1, 1):
        y = y0
        while y > -40:
            L = rng.uniform(0.8, 1.2)
            mb.addt(G.cbox((sx * 1.25 - 0.09, y - L + 0.01, -0.05), (sx * 1.25 + 0.09, y - 0.01, 0.07), 0.02))
            y -= L
    emit("Env_Sando_StonePath", mb, "Env_Sando_Stone", M)
    # stone lanterns (toro) flanking the sando
    tor = G.MB(); fire = G.MB()
    for sx in (-1, 1):
        for yy in (-9.0, -15.0):
            x = sx * 3.0
            tor.addt(G.cbox((x - 0.42, yy - 0.42, 0), (x + 0.42, yy + 0.42, 0.22), 0.03))
            tor.addt(G.cbox((x - 0.30, yy - 0.30, 0.22), (x + 0.30, yy + 0.30, 0.42), 0.03))
            tor.addt(G.lathe([(0.12, 0.42), (0.11, 1.25), (0.13, 1.30)], (x, yy, 0), 20))
            tor.addt(G.cbox((x - 0.32, yy - 0.32, 1.30), (x + 0.32, yy + 0.32, 1.45), 0.03))
            for px in (-1, 1):
                for py in (-1, 1):
                    tor.addt(G.cbox((x + px * 0.22 - 0.05 * (px > 0), yy + py * 0.22 - 0.05 * (py > 0), 1.45),
                                    (x + px * 0.22 + 0.05 * (px < 0), yy + py * 0.22 + 0.05 * (py < 0), 1.80), 0.01))
            fire.addt(G.box((x - 0.17, yy - 0.17, 1.47), (x + 0.17, yy + 0.17, 1.78)))
            tor.addt(G.loft_rect([(0.52, 0.52, 1.80), (0.50, 0.50, 1.86), (0.12, 0.12, 2.10), (0.05, 0.05, 2.14)], (x, yy), ch=0.04))
            tor.addt(G.lathe([(0.0, 2.12), (0.07, 2.16), (0.06, 2.26), (0.0, 2.34)], (x, yy, 0), 16))
    emit("Env_Toro_StoneLanterns", tor, "Ishi_Granite", M)
    fm = bpy.data.materials.new("Env_Hibukuro_Paper")
    fm.use_nodes = True
    b = fm.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.8, 0.75, 0.6, 1)
    b.inputs["Emission Color"].default_value = (1.0, 0.45, 0.15, 1)
    b.inputs["Emission Strength"].default_value = 0.0
    me = fire.to_mesh("Env_Toro_Hibukuro")
    me.materials.append(fm)
    link(bpy.data.objects.new("Env_Toro_Hibukuro", me))
    # cedars (sugi): straight reddish trunks, irregular dark foliage clumps
    trunk = G.MB(); leaf = G.MB()
    spots = []
    for k in range(150):
        ang = rng.uniform(0, 2 * np.pi)
        r = rng.uniform(17, 70)
        x, y = r * math.cos(ang), r * math.sin(ang) * 0.9 + 4
        if y < 1.5 and abs(x) < 24:
            continue
        if any((x - a) ** 2 + (y - b) ** 2 < 9 for a, b in spots):
            continue
        spots.append((x, y))
    for (x, y) in spots:
        h = rng.uniform(22, 34)
        rb = rng.uniform(0.35, 0.65)
        trunk.addt(G.lathe([(rb * 1.5, -0.1), (rb * 1.1, 0.8), (rb, 2.0), (rb * 0.55, h * 0.8), (0.05, h)], (x, y, 0), 12))
        nl = 30
        for i in range(nl):
            t = i / nl
            z0 = h * (0.50 + 0.48 * t) + rng.uniform(-0.3, 0.3)
            rr = (1 - t) ** 0.9 * rng.uniform(1.5, 2.1) + 0.3
            a2 = rng.uniform(0, 2 * np.pi)
            cx_ = x + math.cos(a2) * rr * 0.55
            cy_ = y + math.sin(a2) * rr * 0.55
            r2 = rr * rng.uniform(0.45, 0.7)
            V, F = G.lathe([(0.0, -0.35), (r2, -0.1), (r2 * 0.55, 0.35), (r2 * 0.18, 0.9), (0.0, 1.25)], (0, 0, 0), 7)
            V[:, 2] *= rng.uniform(1.0, 1.5)
            V += rng.normal(0, 0.10, V.shape)
            V[:, 2] -= 0.35 * (np.hypot(V[:, 0], V[:, 1]) / max(r2, 0.1)) ** 2   # droop
            V += (cx_, cy_, z0)
            leaf.add(V, F)
    emit("Env_Sugi_Trunks", trunk, "Env_Bark", M)
    emit("Env_Sugi_Foliage", leaf, "Env_Cedar_Leaf", M, smooth=0)


def toro_light(on):
    """Glowing paper fire-box of the stone lanterns (evening only)."""
    m = bpy.data.materials.get("Env_Hibukuro_Paper")
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 6.0 if on else 0.0


def setup_world(sun_el, sun_az, sun_strength, sky_strength):
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(sun_el)
    sky.sun_rotation = math.radians(sun_az)
    sky.altitude = 50
    try:
        sky.air_density = 1.0
        sky.aerosol_density = 1.6 if sun_el < 10 else 1.0
    except Exception:
        pass
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = sky_strength
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    # sun lamp aligned with sky sun
    sun = bpy.data.objects.get("Sun")
    if sun is None:
        ld = bpy.data.lights.new("Sun", "SUN")
        sun = bpy.data.objects.new("Sun", ld)
        link(sun)
    sun.data.energy = sun_strength
    sun.data.angle = math.radians(1.5)
    if sun_el < 12:
        sun.data.color = (1.0, 0.52, 0.26)
    else:
        sun.data.color = (1.0, 0.96, 0.9)
    # direction: light travels opposite to the sun vector
    el, az = math.radians(sun_el), math.radians(sun_az)
    d = Vector((math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)))
    sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def setup_camera(loc, target, lens):
    cam = bpy.data.objects.get("Camera")
    if cam is None:
        cd = bpy.data.cameras.new("Camera")
        cam = bpy.data.objects.new("Camera", cd)
        link(cam)
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens
    cam.data.clip_end = 300
    bpy.context.scene.camera = cam


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="haiden/out")
    ap.add_argument("--only", default="")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    out = os.path.abspath(a.out)
    q = os.environ.get("HAIDEN_QUALITY", "preview")
    Q = dict(QUALITY.get(q, QUALITY["preview"]))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(out, "haiden.blend"))
    stats_path = os.path.join(out, "stats.json")
    stats = json.load(open(stats_path, encoding="utf-8")) if os.path.exists(stats_path) else {}
    # per-variant render budget (CI: all final renders together within 60 min)
    Q.update(QUALITY_OVERRIDE.get(stats.get("id", "A-1"), {}).get(q, {}))
    build_env(stats)

    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = Q["samples"]
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = Q["bounces"]
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 3
    sc.cycles.transparent_max_bounces = 4
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = Q["res"]
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    sc.render.threads_mode = "AUTO"

    rdir = os.path.join(out, "renders")
    os.makedirs(rdir, exist_ok=True)
    vid = stats.get("id", "A-1")
    views, dbg_views = VIEW_SETS.get(vid, (VIEWS, DEBUG_VIEWS))
    ALL = dict(views, **dbg_views)
    names = [n for n in ALL if (not a.only and n in views) or n in a.only.split(",")]
    timing = {}
    cur_finish = None
    for n in names:
        title, loc, tgt, lens, el, az, ss, sk = ALL[n][:8]
        fin = ALL[n][8] if len(ALL[n]) > 8 else None
        if fin and fin != cur_finish:
            from hlib import materials2 as M2
            M2.apply_finish(fin)
            cur_finish = fin
        setup_world(el, az, ss, sk)
        setup_camera(loc, tgt, lens)
        sc.view_settings.exposure = 0.0 if el > 10 else 0.2
        toro_light(el <= 10)
        t0 = time.time()
        ddir = os.path.join(out, "debug")
        os.makedirs(ddir, exist_ok=True)
        sc.render.filepath = os.path.join(ddir if n in dbg_views else rdir, n + ".png")
        bpy.ops.render.render(write_still=True)
        timing[n] = round(time.time() - t0, 1)
        print("rendered %s in %.1fs" % (n, timing[n]), flush=True)
    # update stats.json renders list (all pngs present)
    present = [v for v in views if os.path.exists(os.path.join(rdir, v + ".png"))]
    stats["renders"] = [dict({"src": "renders/%s/%s.png" % (vid, v), "title": views[v][0]},
                             **({"finish": views[v][8]} if len(views[v]) > 8 else {})) for v in present]
    stats["render_quality"] = q
    stats.setdefault("render_seconds", {}).update(timing)
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
