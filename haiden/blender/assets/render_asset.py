#!/usr/bin/env python3
"""境内アセット(鳥居・灯籠ほか)の汎用レンダラ。仕様は haiden/docs/assets.md。

    HAIDEN_QUALITY=draft|preview|final python3 haiden/blender/assets/render_asset.py --out haiden/out/T-1 [--only a,b]

<out>/haiden.blend を開き、<out>/stats.json の id から haiden/blender/assets/variants/<id>.json の
`views` を読んで <out>/renders/<view>.png を描く。stats.json の renders / render_quality /
render_seconds を更新する(render.py と同じ形式。src は サイトルート基準 renders/<id>/<view>.png)。

視点 `views` の書き方(どちらでもよい):
  - render.py と同じタプル: [title, [cam x,y,z], [target x,y,z], lens, sun_elev, sun_azim, sun_strength, sky_strength]
    仕上げを指定する場合は 9 番目に finish id を入れる
  - オブジェクト: {"title", "loc", "target", "lens", "sun_elev", "sun_azim", "sun_strength", "sky_strength", "finish"}
    (lens 省略 30 / sun_elev 40 / sun_azim 215 / sun_strength 2.4 / sky_strength 0.45)
  `views` は {"<view名>": ...} の辞書、または [{"name": "<view名>", ...}, ...] の配列。

仕上げ: ビルドスクリプトが材質の変わるオブジェクトに付けたカスタムプロパティ `finish_mats`
(JSON: {"<finish id>": ["<slot0の材質名>", "<slot1の材質名>", ...]}) を読んで material_slots を差し替える。
finish 無しの視点は stats.json の先頭の仕上げ(.blend 保存時の既定)で描く。

地面は砂利色の平面(原点中心・約400m角)、背景は Sky + Sun(Cycles CPU + OIDN)。
"""
import argparse
import json
import math
import os
import re
import sys
import time

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
VARIANTS = os.path.join(HERE, "variants")

QUALITY = {
    "draft": dict(res=(640, 360), samples=12, bounces=3),
    "preview": dict(res=(960, 540), samples=24, bounces=4),
    "final": dict(res=(1600, 900), samples=48, bounces=6),
}
GROUND_HALF = 200.0  # 地平線まで床を延ばす(20m 角だと手前で切れて暗い空が見える)
GRAVEL_DARK = (0.30, 0.28, 0.26, 1.0)
GRAVEL_LIGHT = (0.55, 0.52, 0.48, 1.0)


def link(ob, cname="Env"):
    c = bpy.data.collections.get(cname)
    if c is None:
        c = bpy.data.collections.new(cname)
        bpy.context.scene.collection.children.link(c)
    if ob.name not in c.objects:
        c.objects.link(ob)


def build_ground():
    """砂利色の平面(原点中心・約400m角)。色のむらだけノイズで付ける(形は平ら)。"""
    s = GROUND_HALF
    me = bpy.data.meshes.new("Env_Ground_Gravel")
    me.from_pydata([(-s, -s, 0.0), (s, -s, 0.0), (s, s, 0.0), (-s, s, 0.0)], [], [(0, 1, 2, 3)])
    me.update()
    m = bpy.data.materials.new("Env_Gravel")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.9
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = GRAVEL_DARK
    ramp.color_ramp.elements[1].color = GRAVEL_LIGHT
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    me.materials.append(m)
    me.shade_smooth()
    ob = bpy.data.objects.new("Env_Ground_Gravel", me)
    link(ob)


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
    # 太陽ランプ(Sky の太陽と同じ向き)
    sun = bpy.data.objects.get("Sun")
    if sun is None:
        ld = bpy.data.lights.new("Sun", "SUN")
        sun = bpy.data.objects.new("Sun", ld)
        link(sun)
    sun.data.energy = sun_strength
    sun.data.angle = math.radians(1.5)
    sun.data.color = (1.0, 0.52, 0.26) if sun_el < 12 else (1.0, 0.96, 0.9)
    # 光の向きは太陽ベクトルの逆
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


def apply_finish(fid):
    """finish_mats を読んで各オブジェクトの material_slots を差し替える。"""
    hit = 0
    for ob in bpy.data.objects:
        if ob.type != "MESH" or "finish_mats" not in ob:
            continue
        fm = json.loads(ob["finish_mats"])
        names = fm.get(fid)
        if names is None:
            continue
        if isinstance(names, str):
            names = [names]
        for i, nm in enumerate(names):
            if i >= len(ob.material_slots):
                break
            m = bpy.data.materials.get(nm)
            if m is None:
                raise SystemExit("finish %s: material %r not found (object %s)" % (fid, nm, ob.name))
            ob.material_slots[i].material = m
        hit += 1
    if hit == 0:
        raise SystemExit("finish %r: no object has it in finish_mats" % fid)


def parse_views(raw):
    """views を正規化: [{"name","title","loc","target","lens","sun_elev","sun_azim","sun_strength","sky_strength","finish"}]"""
    if isinstance(raw, dict):
        pairs = list(raw.items())
    else:
        pairs = [(v.get("name"), v) for v in raw]
    out = []
    for name, v in pairs:
        if not name or not re.fullmatch(r"[A-Za-z0-9_\-]+", str(name)):
            raise SystemExit("bad view name: %r" % (name,))
        if isinstance(v, (list, tuple)):
            title, loc, tgt, lens, el, az, ss, sk = v[:8]
            fin = v[8] if len(v) > 8 else None
        else:
            title = v.get("title", name)
            loc, tgt = v["loc"], v["target"]
            lens = v.get("lens", 30)
            el, az = v.get("sun_elev", 40), v.get("sun_azim", 215)
            ss, sk = v.get("sun_strength", 2.4), v.get("sky_strength", 0.45)
            fin = v.get("finish")
        out.append(dict(name=str(name), title=title, loc=tuple(loc), target=tuple(tgt), lens=lens,
                        el=el, az=az, ss=ss, sk=sk, finish=fin))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="出力ディレクトリ(haiden.blend と stats.json がある)")
    ap.add_argument("--only", default="", help="描く視点名をカンマ区切りで限定")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

    out = os.path.abspath(a.out)
    q = os.environ.get("HAIDEN_QUALITY", "preview")
    if q not in QUALITY:
        raise SystemExit("HAIDEN_QUALITY must be draft|preview|final (got %r)" % q)
    Q = QUALITY[q]

    stats_path = os.path.join(out, "stats.json")
    with open(stats_path, encoding="utf-8") as f:
        stats = json.load(f)
    vid = stats["id"]
    vpath = os.path.join(VARIANTS, "%s.json" % vid)
    if not os.path.exists(vpath):
        raise SystemExit("variant definition not found: %s" % vpath)
    with open(vpath, encoding="utf-8") as f:
        views = parse_views(json.load(f).get("views", []))
    if not views:
        raise SystemExit("no views in %s" % vpath)

    only = [s for s in a.only.split(",") if s]
    if only:
        known = {v["name"] for v in views}
        bad = [s for s in only if s not in known]
        if bad:
            raise SystemExit("unknown view(s): %s" % ",".join(bad))
        views = [v for v in views if v["name"] in only]

    bpy.ops.wm.open_mainfile(filepath=os.path.join(out, "haiden.blend"))
    build_ground()

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

    finishes = [f["id"] for f in stats.get("finishes", [])]
    default_fin = finishes[0] if finishes else None
    rdir = os.path.join(out, "renders")
    os.makedirs(rdir, exist_ok=True)
    timing = {}
    for v in views:
        fin = v["finish"] or default_fin
        if fin:
            apply_finish(fin)
        setup_world(v["el"], v["az"], v["ss"], v["sk"])
        setup_camera(v["loc"], v["target"], v["lens"])
        sc.view_settings.exposure = 0.0 if v["el"] > 10 else 0.2
        sc.render.filepath = os.path.join(rdir, v["name"] + ".png")
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        timing[v["name"]] = round(time.time() - t0, 1)
        print("rendered %s (%s, finish=%s) in %.1fs" % (v["name"], q, fin, timing[v["name"]]), flush=True)

    # stats.json の renders を更新(拝殿 render.py と同じ形式。存在する PNG だけ載せる)
    with open(vpath, encoding="utf-8") as f:
        all_views = {v["name"]: v for v in parse_views(json.load(f).get("views", []))}
    present = [n for n in all_views if os.path.exists(os.path.join(rdir, n + ".png"))]
    renders = []
    for n in present:
        e = {"src": "renders/%s/%s.png" % (vid, n), "title": all_views[n]["title"]}
        if all_views[n]["finish"]:
            e["finish"] = all_views[n]["finish"]
        renders.append(e)
    stats["renders"] = renders
    stats["render_quality"] = q
    stats.setdefault("render_seconds", {}).update(timing)
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("done: %d view(s), stats.json renders=%d" % (len(views), len(renders)))


if __name__ == "__main__":
    main()
