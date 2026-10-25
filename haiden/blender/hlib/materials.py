"""Procedural materials (UV-periodic so they can be baked to small tiles).

Every mesh gets a triplanar UV with a 2 m tile (geom.MB.to_mesh), so a
procedural evaluated on UV in [0,1) and made periodic (4D noise on a torus)
bakes into a seamless tile that the glTF export reuses with REPEAT wrap.
"""
import math
import os
import bpy

TAU = 2 * math.pi

# name: (base sRGB-ish linear color, roughness, metallic, kind)
SPEC = {
    "Nuri_Shu_Vermilion":   ((0.56, 0.055, 0.018), 0.55, 0.0, "paint"),
    "Gofun_White":          ((0.80, 0.78, 0.72), 0.80, 0.0, "plaster"),
    "Kuro_Urushi_Lacquer":  ((0.012, 0.010, 0.009), 0.22, 0.0, "lacquer"),
    "Kiji_Hinoki_Wood":     ((0.40, 0.25, 0.13), 0.60, 0.0, "wood"),
    "Kiji_Old_Wood":        ((0.30, 0.22, 0.15), 0.70, 0.0, "wood"),
    "Doban_Rokusho_Copper": ((0.10, 0.30, 0.23), 0.62, 0.0, "copper"),
    "Kanagu_Gold":          ((0.95, 0.66, 0.26), 0.28, 1.0, "metal"),
    "Seido_Bronze":         ((0.45, 0.30, 0.14), 0.40, 1.0, "metal"),
    "Ishi_Granite":         ((0.22, 0.21, 0.195), 0.85, 0.0, "stone"),
    "Shikkui_Plaster":      ((0.78, 0.77, 0.73), 0.85, 0.0, "plaster"),
    "Ki_Ochre":             ((0.62, 0.42, 0.08), 0.6, 0.0, "paint"),
    "Uchi_Dark":            ((0.03, 0.022, 0.016), 0.8, 0.0, "flat"),
    "Asa_Straw":            ((0.55, 0.45, 0.22), 0.85, 0.0, "straw"),
    "Shide_Paper":          ((0.85, 0.85, 0.82), 0.9, 0.0, "flat"),
    "Nuno_Red":             ((0.55, 0.03, 0.03), 0.8, 0.0, "flat"),
    "Nuno_White":           ((0.82, 0.80, 0.76), 0.8, 0.0, "flat"),
    "Nuno_Purple":          ((0.18, 0.04, 0.22), 0.8, 0.0, "flat"),
    # A-2 本瓦葺: いぶし銀 (smoked silver-grey clay tile) / roof base (葺土・野地)
    "Kawara_Ibushi":        ((0.075, 0.078, 0.084), 0.36, 0.42, "kawara"),
    "Kawara_Base":          ((0.035, 0.034, 0.033), 0.9, 0.0, "flat"),
    # environment only
    "Env_Gravel":           ((0.115, 0.105, 0.09), 0.9, 0.0, "gravel"),
    "Env_Sando_Stone":      ((0.17, 0.165, 0.155), 0.85, 0.0, "stone"),
    "Env_Cedar_Leaf":       ((0.018, 0.038, 0.02), 0.85, 0.0, "leaf"),
    "Env_Bark":             ((0.16, 0.075, 0.045), 0.9, 0.0, "wood"),
    "Env_Moss":             ((0.08, 0.13, 0.04), 0.9, 0.0, "leaf"),
}

BAKE = ["Nuri_Shu_Vermilion", "Kiji_Hinoki_Wood", "Kiji_Old_Wood", "Doban_Rokusho_Copper",
        "Ishi_Granite", "Gofun_White", "Shikkui_Plaster", "Kawara_Ibushi"]   # (absent materials are skipped)


class NB:
    def __init__(self, mat):
        self.nt = mat.node_tree
        self.N = self.nt.nodes
        self.L = self.nt.links
        self.x = -1200

    def node(self, t, **kw):
        n = self.N.new(t)
        n.location = (self.x, len(self.N) * -40 % 800)
        self.x += 60
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def math(self, op, a, b=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._in(n.inputs[0], a)
        if b is not None:
            self._in(n.inputs[1], b)
        return n.outputs[0]

    def _in(self, sock, v):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, tuple):
            sock.default_value = v
        else:
            self.L.new(v, sock)

    def link(self, a, b):
        self.L.new(a, b)


def _periodic_noise(nb, u, v, R, detail=4.0, rough=0.55, out="Fac", stretch=(1.0, 1.0)):
    """4D noise on a torus -> periodic in u,v with period 1."""
    au = nb.math("MULTIPLY", u, TAU)
    av = nb.math("MULTIPLY", v, TAU)
    cu = nb.math("MULTIPLY", nb.math("COSINE", au), R * stretch[0])
    su = nb.math("MULTIPLY", nb.math("SINE", au), R * stretch[0])
    cv = nb.math("MULTIPLY", nb.math("COSINE", av), R * stretch[1])
    sv = nb.math("MULTIPLY", nb.math("SINE", av), R * stretch[1])
    cmb = nb.node("ShaderNodeCombineXYZ")
    nb.link(cu, cmb.inputs[0]); nb.link(su, cmb.inputs[1]); nb.link(cv, cmb.inputs[2])
    nz = nb.node("ShaderNodeTexNoise", noise_dimensions="4D")
    nb.link(cmb.outputs[0], nz.inputs["Vector"])
    nb.link(sv, nz.inputs["W"])
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = detail
    nz.inputs["Roughness"].default_value = rough
    return nz.outputs[out]


def _ramp(nb, fac, c0, c1, p0=0.0, p1=1.0):
    r = nb.node("ShaderNodeValToRGB")
    nb.link(fac, r.inputs[0])
    e = r.color_ramp.elements
    e[0].position = p0; e[0].color = (*c0, 1)
    e[1].position = p1; e[1].color = (*c1, 1)
    return r.outputs[0]


def _mul(c, k):
    return tuple(max(0.0, min(1.0, x * k)) for x in c)


def make_material(name, use_ao=True):
    col, rough, metal, kind = SPEC[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = False
    nb = NB(m)
    bsdf = nb.N.get("Principled BSDF")
    out = nb.N.get("Material Output")
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    m["glb_color"] = list(col)
    m["glb_rough"] = rough
    m["glb_metal"] = metal
    m.diffuse_color = (*col, 1)
    if kind == "flat":
        return m
    tc = nb.node("ShaderNodeTexCoord")
    sep = nb.node("ShaderNodeSeparateXYZ")
    nb.link(tc.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs[0], sep.outputs[1]
    color = None
    height = None
    rough_f = None
    if kind == "paint":
        n1 = _periodic_noise(nb, u, v, 3.0, 6, 0.6)
        n2 = _periodic_noise(nb, u, v, 25.0, 3, 0.5)
        mix = nb.math("ADD", nb.math("MULTIPLY", n1, 0.7), nb.math("MULTIPLY", n2, 0.3))
        color = _ramp(nb, mix, _mul(col, 0.72), _mul(col, 1.12), 0.3, 0.72)
        rough_f = nb.math("ADD", nb.math("MULTIPLY", n2, 0.25), rough - 0.12)
        height = n2
    elif kind == "plaster":
        n1 = _periodic_noise(nb, u, v, 4.0, 5, 0.6)
        n2 = _periodic_noise(nb, u, v, 40.0, 2, 0.5)
        mix = nb.math("ADD", nb.math("MULTIPLY", n1, 0.6), nb.math("MULTIPLY", n2, 0.4))
        color = _ramp(nb, mix, _mul(col, 0.85), _mul(col, 1.05), 0.35, 0.7)
        height = n2
    elif kind == "lacquer":
        n1 = _periodic_noise(nb, u, v, 6.0, 4, 0.5)
        color = _ramp(nb, n1, _mul(col, 0.7), (0.04, 0.03, 0.025), 0.4, 0.75)
        rough_f = nb.math("ADD", nb.math("MULTIPLY", n1, 0.25), 0.12)
    elif kind in ("wood",):
        # grain: sine bands along v (u = along-grain) distorted by periodic noise
        dn = _periodic_noise(nb, u, v, 2.0, 3, 0.5, stretch=(0.3, 2.5))
        ph = nb.math("ADD", nb.math("MULTIPLY", v, TAU * 46), nb.math("MULTIPLY", dn, 9.0))
        g = nb.math("MULTIPLY", nb.math("ADD", nb.math("SINE", ph), 1.0), 0.5)
        g = nb.math("POWER", g, 3.0)
        n2 = _periodic_noise(nb, u, v, 6.0, 5, 0.6)
        mix = nb.math("ADD", nb.math("MULTIPLY", g, 0.45), nb.math("MULTIPLY", n2, 0.55))
        color = _ramp(nb, mix, _mul(col, 1.15), _mul(col, 0.62), 0.25, 0.8)
        height = g
        rough_f = nb.math("ADD", nb.math("MULTIPLY", g, 0.15), rough - 0.05)
    elif kind == "copper":
        n1 = _periodic_noise(nb, u, v, 2.5, 6, 0.62)
        n2 = _periodic_noise(nb, u, v, 18.0, 4, 0.6)
        streak = _periodic_noise(nb, u, v, 3.0, 3, 0.5, stretch=(8.0, 0.4))
        mix = nb.math("ADD", nb.math("MULTIPLY", n1, 0.5), nb.math("MULTIPLY", n2, 0.25))
        mix = nb.math("ADD", mix, nb.math("MULTIPLY", streak, 0.25))
        r = nb.node("ShaderNodeValToRGB")
        nb.link(mix, r.inputs[0])
        e = r.color_ramp.elements
        e[0].position = 0.30; e[0].color = (0.04, 0.11, 0.08, 1)
        e[1].position = 0.72; e[1].color = (0.20, 0.42, 0.33, 1)
        e3 = r.color_ramp.elements.new(0.52); e3.color = (*col, 1)
        e4 = r.color_ramp.elements.new(0.38); e4.color = (0.16, 0.11, 0.07, 1)
        e4.position = 0.33
        color = r.outputs[0]
        height = n2
        rough_f = nb.math("ADD", nb.math("MULTIPLY", n2, 0.2), rough - 0.1)
    elif kind == "kawara":
        # いぶし瓦: carbon film = silvery sheen with blotchy darker / lighter firing marks
        n1 = _periodic_noise(nb, u, v, 3.5, 5, 0.6)
        n2 = _periodic_noise(nb, u, v, 30.0, 3, 0.55)
        mix = nb.math("ADD", nb.math("MULTIPLY", n1, 0.7), nb.math("MULTIPLY", n2, 0.3))
        color = _ramp(nb, mix, _mul(col, 0.62), _mul(col, 1.55), 0.3, 0.72)
        rough_f = nb.math("ADD", nb.math("MULTIPLY", n1, 0.30), rough - 0.12)
        height = n2
    elif kind == "metal":
        n1 = _periodic_noise(nb, u, v, 8.0, 4, 0.5)
        color = _ramp(nb, n1, _mul(col, 0.75), col, 0.35, 0.7)
        rough_f = nb.math("ADD", nb.math("MULTIPLY", n1, 0.2), rough - 0.08)
    elif kind in ("stone", "gravel"):
        n1 = _periodic_noise(nb, u, v, 5.0, 6, 0.65)
        n2 = _periodic_noise(nb, u, v, 60.0 if kind == "stone" else 120.0, 2, 0.5)
        mix = nb.math("ADD", nb.math("MULTIPLY", n1, 0.55), nb.math("MULTIPLY", n2, 0.45))
        color = _ramp(nb, mix, _mul(col, 0.6), _mul(col, 1.35), 0.3, 0.75)
        height = n2
    elif kind == "straw":
        n2 = _periodic_noise(nb, u, v, 3.0, 3, 0.5, stretch=(0.2, 12.0))
        color = _ramp(nb, n2, _mul(col, 0.7), _mul(col, 1.2), 0.3, 0.7)
        height = n2
    elif kind == "leaf":
        n1 = _periodic_noise(nb, u, v, 20.0, 4, 0.6)
        color = _ramp(nb, n1, _mul(col, 0.6), _mul(col, 1.6), 0.3, 0.75)
        height = n1
    base = color
    if use_ao and kind in ("paint", "copper", "plaster", "wood", "stone", "kawara"):
        ao = nb.node("ShaderNodeAmbientOcclusion", samples=6)
        ao.inputs["Distance"].default_value = 0.35
        mixn = nb.node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        mixn.inputs["Factor"].default_value = 1.0
        nb.link(color, mixn.inputs["A"])
        grime = nb.node("ShaderNodeValToRGB")
        nb.link(ao.outputs["AO"], grime.inputs[0])
        g = grime.color_ramp.elements
        g[0].position = 0.0; g[0].color = (0.45, 0.42, 0.38, 1)
        g[1].position = 1.0; g[1].color = (1, 1, 1, 1)
        nb.link(grime.outputs[0], mixn.inputs["B"])
        base = mixn.outputs["Result"]
        m["bake_src"] = "pre_ao"
    nb.link(base, bsdf.inputs["Base Color"])
    # keep a handle to the pre-AO color for baking
    m["_bake_color_node"] = color.node.name
    m["_bake_color_sock"] = color.name
    if rough_f is not None:
        nb.link(rough_f, bsdf.inputs["Roughness"])
    if height is not None:
        bump = nb.node("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.15 if kind != "stone" else 0.35
        bump.inputs["Distance"].default_value = 0.004
        nb.link(height, bump.inputs["Height"])
        nb.link(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if kind == "lacquer":
        bsdf.inputs["Coat Weight"].default_value = 0.6
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    return m


class Mats:
    def __init__(self):
        self.cache = {}

    def __getitem__(self, name):
        if name not in self.cache:
            self.cache[name] = make_material(name)
        return self.cache[name]


# ----------------------------------------------------------------- baking

def bake_tiles(names, out_dir, size=512):
    """Bake the pre-AO procedural color of each material to a seamless tile."""
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    prev_engine = sc.render.engine
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.cycles.device = "CPU"
    me = bpy.data.meshes.new("BakePlane")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[i].uv = c
    ob = bpy.data.objects.new("BakePlane", me)
    sc.collection.objects.link(ob)
    result = {}
    for name in names:
        m = bpy.data.materials.get(name)
        if m is None or "_bake_color_node" not in m:
            continue
        nt = m.node_tree
        src = nt.nodes[m["_bake_color_node"]].outputs[m["_bake_color_sock"]]
        out = nt.nodes.get("Material Output")
        old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].links else None
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(src, em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        img = bpy.data.images.new("T_" + name, size, size, alpha=False)
        img.colorspace_settings.name = "sRGB"
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.nodes.active = tex
        me.materials.clear()
        me.materials.append(m)
        for o in sc.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
        path = os.path.join(out_dir, "T_%s.png" % name)
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        result[name] = path
        nt.nodes.remove(tex)
        nt.nodes.remove(em)
        if old is not None:
            nt.links.new(old, out.inputs["Surface"])
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    sc.render.engine = prev_engine
    return result


def glb_material(src, tiles):
    """Simple export material: baked tile (or flat color) + scalar rough/metal."""
    name = "GLB_" + src.name
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = False
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    col = src.get("glb_color", (0.5, 0.5, 0.5))
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    bsdf.inputs["Roughness"].default_value = float(src.get("glb_rough", 0.6))
    bsdf.inputs["Metallic"].default_value = float(src.get("glb_metal", 0.0))
    if src.name in tiles:
        img = bpy.data.images.load(tiles[src.name], check_existing=True)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        uvn = nt.nodes.new("ShaderNodeUVMap")
        uvn.uv_map = "UVMap"
        nt.links.new(uvn.outputs[0], tex.inputs[0])
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m
