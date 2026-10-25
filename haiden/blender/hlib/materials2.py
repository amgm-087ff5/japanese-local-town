"""拝殿A-2 ver2 materials: finishes (丹塗 / 白木 / 古色), 1K texture bake
(baseColor + normal + roughness/metallic) and glTF export materials with
KHR_materials_variants.

v1 variants (A-1, A-2v1) keep using hlib.materials unchanged.

UV convention (geom.grain_uv): u runs along the member (grain direction),
1 UV unit = 2 m (uv_tile). Procedurals are periodic in (u, v) so they bake to
seamless tiles.
"""
import json
import math
import os

import bpy
import numpy as np

from .materials import NB, SPEC, TAU, _mul, _periodic_noise, _ramp, make_material

FINISHES = [{"id": "nuri", "name": "丹塗"}, {"id": "shiraki", "name": "白木"}, {"id": "koshoku", "name": "古色"}]

# name: (base color (linear), roughness, metallic, kind)
SPEC2 = {
    "Nuri_Shu_Vermilion": ((0.56, 0.060, 0.020), 0.52, 0.0, "nuri2"),
    "Shiraki_Hinoki":     ((0.56, 0.385, 0.215), 0.60, 0.0, "shiraki"),
    "Koshoku_Kiji":       ((0.118, 0.078, 0.048), 0.80, 0.0, "koshoku"),
    "Koshoku_Kiji_Dark":  ((0.080, 0.054, 0.034), 0.82, 0.0, "koshoku"),
    "Kanagu_Koshoku":     ((0.15, 0.115, 0.07), 0.60, 0.60, "metal_old"),
}

# base material -> material per finish (same material = common to all finishes)
FINISH_MAP = {
    "Nuri_Shu_Vermilion": {"shiraki": "Shiraki_Hinoki", "koshoku": "Koshoku_Kiji"},
    "Kiji_Hinoki_Wood":   {"shiraki": "Shiraki_Hinoki", "koshoku": "Koshoku_Kiji"},
    "Kiji_Old_Wood":      {"shiraki": "Shiraki_Hinoki", "koshoku": "Koshoku_Kiji_Dark"},
    "Ki_Ochre":           {"shiraki": "Shiraki_Hinoki", "koshoku": "Koshoku_Kiji"},
    "Kanagu_Gold":        {"koshoku": "Kanagu_Koshoku"},
}
# per-object overrides (black-lacquered boards/lattice become plain wood; the 扁額 stays black)
OBJ_MAP = {
    "Koshido_Lattice_Bars": {"shiraki": "Shiraki_Hinoki", "koshoku": "Koshoku_Kiji_Dark"},
    "Tsuma_GableBoard": {"shiraki": "Shiraki_Hinoki", "koshoku": "Koshoku_Kiji_Dark"},
    "Chidori_Tsuma_GableBoard": {"shiraki": "Shiraki_Hinoki", "koshoku": "Koshoku_Kiji_Dark"},
}

BAKE2 = ["Nuri_Shu_Vermilion", "Shiraki_Hinoki", "Koshoku_Kiji", "Koshoku_Kiji_Dark", "Kiji_Hinoki_Wood",
         "Kiji_Old_Wood", "Gofun_White", "Shikkui_Plaster", "Kawara_Ibushi", "Doban_Rokusho_Copper", "Ishi_Granite"]


def finish_mats(obj_name, base):
    m = {"nuri": base, "shiraki": base, "koshoku": base}
    m.update(FINISH_MAP.get(base, {}))
    m.update(OBJ_MAP.get(obj_name, {}))
    return m


def _smooth(nb, x, a, b):
    """smoothstep(a, b, x) via map range."""
    n = nb.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    nb._in(n.inputs["Value"], x)
    n.inputs["From Min"].default_value = a
    n.inputs["From Max"].default_value = b
    return n.outputs["Result"]


def _mix(nb, fac, a, b, blend="MIX"):
    a = (*a, 1.0) if isinstance(a, tuple) and len(a) == 3 else a
    b = (*b, 1.0) if isinstance(b, tuple) and len(b) == 3 else b
    n = nb.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
    nb._in(n.inputs["Factor"], fac)
    nb._in(n.inputs["A"], a)
    nb._in(n.inputs["B"], b)
    return n.outputs["Result"]


def _grain(nb, u, v, rings, distort, seed_R=2.0):
    """Ring/grain field along u: sine bands across v, distorted by low-frequency noise."""
    dn = _periodic_noise(nb, u, v, seed_R, 3, 0.5, stretch=(0.35, 2.0))
    ph = nb.math("ADD", nb.math("MULTIPLY", v, TAU * rings), nb.math("MULTIPLY", dn, distort))
    g = nb.math("MULTIPLY", nb.math("ADD", nb.math("SINE", ph), 1.0), 0.5)
    return g


def make_material2(name):
    if name not in SPEC2:
        m = make_material(name)
        m["v2"] = 1
        return m
    col, rough, metal, kind = SPEC2[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = False
    nb = NB(m)
    bsdf = nb.N.get("Principled BSDF")
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    m["glb_color"] = list(col)
    m["glb_rough"] = rough
    m["glb_metal"] = metal
    m["v2"] = 1
    m.diffuse_color = (*col, 1)
    tc = nb.node("ShaderNodeTexCoord")
    sep = nb.node("ShaderNodeSeparateXYZ")
    nb.link(tc.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs[0], sep.outputs[1]
    edge_wear = None
    bump_strength = 0.2
    if kind == "nuri2":
        # 丹塗: brush streaks along the grain, faded (退色) patches, worn spots showing the dark ground
        streak = _periodic_noise(nb, u, v, 1.6, 4, 0.55, stretch=(1.0, 14.0))
        mott = _periodic_noise(nb, u, v, 1.4, 5, 0.6)
        fine = _periodic_noise(nb, u, v, 22.0, 3, 0.5)
        wearn = _periodic_noise(nb, u, v, 5.0, 6, 0.65)
        base = _ramp(nb, nb.math("ADD", nb.math("MULTIPLY", streak, 0.6), nb.math("MULTIPLY", fine, 0.4)),
                     _mul(col, 0.80), _mul(col, 1.10), 0.32, 0.70)
        fade = _smooth(nb, mott, 0.56, 0.78)
        faded = (0.58, 0.13, 0.060)
        c1 = _mix(nb, nb.math("MULTIPLY", fade, 0.55), base, faded)
        wear = _smooth(nb, wearn, 0.70, 0.76)
        ground = (0.075, 0.040, 0.022)
        color = _mix(nb, wear, c1, ground)
        rough_f = nb.math("ADD", nb.math("ADD", nb.math("MULTIPLY", streak, 0.10), nb.math("MULTIPLY", fade, 0.20)),
                          nb.math("ADD", nb.math("MULTIPLY", wear, 0.22), rough - 0.07))
        height = nb.math("SUBTRACT", nb.math("MULTIPLY", streak, 0.5), nb.math("MULTIPLY", wear, 0.6))
        bump_strength = 0.25
        edge_wear = (wearn, ground)
    elif kind == "shiraki":
        # 白木 (檜): pale, straight fine grain (柾目〜板目), faint wide figure, rare small knots
        g_fine = nb.math("POWER", _grain(nb, u, v, 150, 5.0, 2.0), 2.0)
        g_fig = _grain(nb, u, v, 19, 7.0, 1.3)
        mott = _periodic_noise(nb, u, v, 3.0, 4, 0.55)
        knotn = _periodic_noise(nb, u, v, 2.2, 2, 0.4, stretch=(1.0, 1.6))
        tone = nb.math("ADD", nb.math("MULTIPLY", g_fig, 0.35), nb.math("MULTIPLY", mott, 0.65))
        base = _ramp(nb, tone, _mul(col, 1.10), _mul(col, 0.80), 0.25, 0.80)
        late = (0.34, 0.19, 0.085)
        c1 = _mix(nb, nb.math("MULTIPLY", g_fine, 0.60), base, late)
        knot = _smooth(nb, knotn, 0.80, 0.83)
        color = _mix(nb, knot, c1, (0.26, 0.13, 0.055))
        rough_f = nb.math("ADD", nb.math("MULTIPLY", g_fine, 0.08), rough - 0.03)
        height = nb.math("ADD", nb.math("MULTIPLY", g_fine, 0.6), nb.math("MULTIPLY", knot, 0.4))
        bump_strength = 0.12
    elif kind == "koshoku":
        # 古色: weathered grey-brown, raised grain (木目の浮き), rain streaks along the member
        g_r = _grain(nb, u, v, 46, 8.0, 1.7)
        g_ridge = nb.math("POWER", g_r, 3.0)
        g_fine = nb.math("POWER", _grain(nb, u, v, 130, 4.0, 2.6), 3.0)
        mott = _periodic_noise(nb, u, v, 2.0, 5, 0.6)
        rain = _periodic_noise(nb, u, v, 1.4, 4, 0.55, stretch=(0.6, 18.0))
        grey = (min(1, col[0] * 1.55), min(1, col[1] * 1.58), min(1, col[2] * 1.62))
        base = _ramp(nb, mott, _mul(col, 0.85), grey, 0.30, 0.75)
        c1 = _mix(nb, nb.math("MULTIPLY", g_ridge, 0.55), base, _mul(col, 0.55))
        c1 = _mix(nb, nb.math("MULTIPLY", g_fine, 0.25), c1, _mul(col, 0.65))
        streakm = _smooth(nb, rain, 0.55, 0.80)
        color = _mix(nb, nb.math("MULTIPLY", streakm, 0.6), c1, _mul(col, 0.50))
        rough_f = nb.math("ADD", nb.math("MULTIPLY", g_ridge, -0.08), rough + 0.04)
        height = nb.math("ADD", nb.math("MULTIPLY", g_ridge, 0.8), nb.math("MULTIPLY", g_fine, 0.25))
        bump_strength = 0.40
    else:  # metal_old
        n1 = _periodic_noise(nb, u, v, 6.0, 5, 0.6)
        n2 = _periodic_noise(nb, u, v, 2.0, 4, 0.55)
        c1 = _ramp(nb, n1, _mul(col, 0.70), col, 0.3, 0.7)
        color = _mix(nb, nb.math("MULTIPLY", _smooth(nb, n2, 0.55, 0.75), 0.6), c1, (0.12, 0.13, 0.08))
        rough_f = nb.math("ADD", nb.math("MULTIPLY", n1, 0.2), rough - 0.08)
        height = n1
        bump_strength = 0.1
    m["_bake_color_node"] = color.node.name
    m["_bake_color_sock"] = color.name
    m["_bake_rough_node"] = rough_f.node.name
    m["_bake_rough_sock"] = rough_f.name
    out_col = color
    if edge_wear is not None:
        # render only (Cycles): corners rubbed through to the ground (bevel normal vs true normal)
        bev = nb.node("ShaderNodeBevel", samples=4)
        bev.inputs["Radius"].default_value = 0.012
        geo = nb.node("ShaderNodeNewGeometry")
        dp = nb.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
        nb.link(bev.outputs["Normal"], dp.inputs[0])
        nb.link(geo.outputs["Normal"], dp.inputs[1])
        edge = _smooth(nb, nb.math("SUBTRACT", 1.0, dp.outputs["Value"]), 0.02, 0.10)
        wn, ground = edge_wear
        chip = _smooth(nb, nb.math("ADD", wn, nb.math("MULTIPLY", edge, 0.5)), 0.78, 0.82)
        out_col = _mix(nb, nb.math("MULTIPLY", edge, chip), color, ground)
    if kind in ("nuri2", "shiraki", "koshoku"):
        ao = nb.node("ShaderNodeAmbientOcclusion", samples=6)
        ao.inputs["Distance"].default_value = 0.35
        grime = nb.node("ShaderNodeValToRGB")
        nb.link(ao.outputs["AO"], grime.inputs[0])
        g = grime.color_ramp.elements
        g[0].position = 0.0; g[0].color = (0.45, 0.42, 0.38, 1)
        g[1].position = 1.0; g[1].color = (1, 1, 1, 1)
        out_col = _mix(nb, 1.0, out_col, grime.outputs[0], blend="MULTIPLY")
    nb.link(out_col, bsdf.inputs["Base Color"])
    nb.link(rough_f, bsdf.inputs["Roughness"])
    bump = nb.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.004
    nb.link(height, bump.inputs["Height"])
    nb.link(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


class Mats2:
    def __init__(self):
        self.cache = {}

    def __getitem__(self, name):
        if name not in self.cache:
            self.cache[name] = make_material2(name)
        return self.cache[name]


def assign_finishes(M):
    """Tag every mesh object with its per-finish materials (JSON custom prop) and create them."""
    used = set()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not ob.data.materials:
            continue
        base = ob.data.materials[0].name
        fm = finish_mats(ob.name, base)
        for v in fm.values():
            M[v].use_fake_user = True      # keep unassigned finish materials in the .blend
            used.add(v)
        ob["finish_mats"] = json.dumps(fm)
    return sorted(used)


def apply_finish(fid):
    """Switch the scene materials to finish `fid` (used by render.py)."""
    for ob in bpy.data.objects:
        if ob.type != "MESH" or "finish_mats" not in ob:
            continue
        name = json.loads(ob["finish_mats"]).get(fid)
        m = bpy.data.materials.get(name) if name else None
        if m is not None:
            ob.data.materials[0] = m


# ----------------------------------------------------------------- baking (1K tiles, 3 maps)

def _socket(m, key):
    nt = m.node_tree
    if "_bake_%s_node" % key in m:
        return nt.nodes[m["_bake_%s_node" % key]].outputs[m["_bake_%s_sock" % key]]
    if key == "rough":
        bs = nt.nodes.get("Principled BSDF")
        if bs and bs.inputs["Roughness"].links:
            return bs.inputs["Roughness"].links[0].from_socket
    return None


def bake_tiles2(names, out_dir, size=1024, uv_tile=2.0):
    """Bake baseColor (sRGB), roughness (-> metallicRoughness: G=rough, B=metal) and tangent normal."""
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    prev_engine = sc.render.engine
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.cycles.device = "CPU"
    L = uv_tile
    me = bpy.data.meshes.new("BakePlane")
    me.from_pydata([(0, 0, 0), (L, 0, 0), (L, L, 0), (0, L, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[i].uv = c
    ob = bpy.data.objects.new("BakePlane", me)
    sc.collection.objects.link(ob)
    result = {}
    for name in names:
        m = bpy.data.materials.get(name)
        if m is None:
            continue
        nt = m.node_tree
        out = nt.nodes.get("Material Output")
        old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].links else None
        me.materials.clear()
        me.materials.append(m)
        for o in sc.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        paths = {}

        def bake_into(kind, src, colorspace, btype):
            img = bpy.data.images.new("T2_%s_%s" % (name, kind), size, size, alpha=False, float_buffer=False)
            img.colorspace_settings.name = colorspace
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            nt.nodes.active = tex
            em = None
            if src is not None:
                em = nt.nodes.new("ShaderNodeEmission")
                nt.links.new(src, em.inputs["Color"])
                nt.links.new(em.outputs[0], out.inputs["Surface"])
            elif old is not None:
                nt.links.new(old, out.inputs["Surface"])
            if btype == "NORMAL":
                bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", margin=0, use_clear=True)
            else:
                bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
            nt.nodes.remove(tex)
            if em is not None:
                nt.nodes.remove(em)
            return img

        col = _socket(m, "color")
        if col is None:
            continue
        img_c = bake_into("base", col, "sRGB", "EMIT")
        rs = _socket(m, "rough")
        img_r = bake_into("rough", rs, "Non-Color", "EMIT") if rs is not None else None
        img_n = bake_into("normal", None, "Non-Color", "NORMAL")
        if old is not None:
            nt.links.new(old, out.inputs["Surface"])
        # save
        p = os.path.join(out_dir, "T_%s_base.png" % name)
        img_c.filepath_raw = p; img_c.file_format = "PNG"; img_c.save()
        paths["base"] = p
        p = os.path.join(out_dir, "T_%s_normal.png" % name)
        img_n.filepath_raw = p; img_n.file_format = "PNG"; img_n.save()
        paths["normal"] = p
        # metallicRoughness: R=1 (unused), G=roughness, B=metallic
        mr = bpy.data.images.new("T2_%s_mr" % name, size, size, alpha=False)
        mr.colorspace_settings.name = "Non-Color"
        px = np.ones(size * size * 4, np.float32)
        if img_r is not None:
            rp = np.empty(size * size * 4, np.float32)
            img_r.pixels.foreach_get(rp)
            px[1::4] = np.clip(rp[0::4], 0.03, 1.0)
        else:
            px[1::4] = float(m.get("glb_rough", 0.6))
        px[2::4] = float(m.get("glb_metal", 0.0))
        px[0::4] = 1.0
        mr.pixels.foreach_set(px)
        p = os.path.join(out_dir, "T_%s_mr.png" % name)
        mr.filepath_raw = p; mr.file_format = "PNG"; mr.save()
        paths["mr"] = p
        for im in (img_c, img_n, img_r, mr):
            if im is not None:
                bpy.data.images.remove(im)
        result[name] = paths
        print("baked", name, flush=True)
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    sc.render.engine = prev_engine
    return result


def glb_material2(name, tiles):
    """Export material: baseColor / metallicRoughness / normal textures (or scalars)."""
    gname = "GLB_" + name
    m = bpy.data.materials.get(gname)
    if m:
        return m
    src = bpy.data.materials[name]
    m = bpy.data.materials.new(gname)
    m.use_nodes = True
    m.use_backface_culling = False
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    col = src.get("glb_color", (0.5, 0.5, 0.5))
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    bsdf.inputs["Roughness"].default_value = float(src.get("glb_rough", 0.6))
    bsdf.inputs["Metallic"].default_value = float(src.get("glb_metal", 0.0))
    t = tiles.get(name)
    if t:
        uvn = nt.nodes.new("ShaderNodeUVMap")
        uvn.uv_map = "UVMap"

        def teximg(path, cs):
            img = bpy.data.images.load(path, check_existing=True)
            img.colorspace_settings.name = cs
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            nt.links.new(uvn.outputs[0], tex.inputs[0])
            return tex
        tb = teximg(t["base"], "sRGB")
        nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
        tm = teximg(t["mr"], "Non-Color")
        sp = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tm.outputs["Color"], sp.inputs[0])
        nt.links.new(sp.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sp.outputs["Blue"], bsdf.inputs["Metallic"])
        tn = teximg(t["normal"], "Non-Color")
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = 1.0
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def setup_gltf_variants(tiles):
    """Assign GLB materials (default = 丹塗) and KHR_materials_variants mappings to every mesh."""
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
        if ob.type != "MESH" or not ob.data.materials:
            continue
        me = ob.data
        if "finish_mats" in ob:
            fm = json.loads(ob["finish_mats"])
        else:
            b = me.materials[0].name
            fm = {f["id"]: b for f in FINISHES}
        me.materials[0] = glb_material2(fm["nuri"], tiles)
        me.gltf2_variant_mesh_data.clear()
        # group finishes by material
        groups = {}
        for i, f in enumerate(FINISHES):
            groups.setdefault(fm[f["id"]], []).append(i)
        if len(groups) == 1:
            continue
        for mname, idxs in groups.items():
            d = me.gltf2_variant_mesh_data.add()
            d.material_slot_index = 0
            d.material = glb_material2(mname, tiles)
            for i in idxs:
                vv = d.variants.add()
                vv.variant.variant_idx = i
        n_var += 1
    return n_var
