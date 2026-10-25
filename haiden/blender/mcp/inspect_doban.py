"""A-1 ver2 銅板葺 inspection, sent through the MCP bridge as execute_blender_code.

Contact pairs (upper sits on lower): for every vertex of the upper object a ray
is cast down onto the lower object (and up, to detect being inside = めり込み).
Vertices are binned on a 10 cm plan grid; per bin the smallest gap is the
contact gap. Reported: bins, worst float (max of bin minima), deepest
penetration, median. 浮き = bin gap > 0.010 m.

Also: no 隅棟/隅鬼 objects, every mesh has UVMap, the 一文字葺 rows of the roof
(geometric steps) line up with the texture rows (v*10 integer at step rows).
"""
import bpy, json, numpy as np
from mathutils.bvhtree import BVHTree
from mathutils import Vector

dg = bpy.context.evaluated_depsgraph_get()
res = {}


def verts(ob):
    me = ob.data
    V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", V)
    return V.reshape(-1, 3)


def contact(upper, lowers, maxd=0.25, sel=None, up=False):
    uo = bpy.data.objects.get(upper)
    los = [bpy.data.objects[n] for n in lowers if n in bpy.data.objects]
    if uo is None or not los:
        return None
    trees = [BVHTree.FromObject(o, dg) for o in los]
    V = verts(uo)
    if sel is not None:
        V = V[sel(V)]
    gaps = {}
    for p in V:
        best = None
        for t in trees:
            if up:                                        # 'upper' is below: cast upward onto 'lowers'
                hit = t.ray_cast(Vector(p) - Vector((0, 0, 0.002)), Vector((0, 0, 1)), maxd)
                if hit[0] is not None:
                    g = hit[3] - 0.002
                    best = g if best is None else min(best, g)
                continue
            hit = t.ray_cast(Vector(p) + Vector((0, 0, 0.002)), Vector((0, 0, -1)), maxd)
            if hit[0] is not None:
                g = hit[3] - 0.002
                best = g if best is None else min(best, g)
            hu = t.ray_cast(Vector(p), Vector((0, 0, 1)), 0.08)
            if hu[0] is not None and hu[1].z > 0:        # leaving the solid upward -> p is inside
                g = -hu[3]
                best = g if best is None else min(best, g)
        if best is None:
            continue
        k = (int(round(p[0] / 0.1)), int(round(p[1] / 0.1)))
        gaps[k] = min(gaps.get(k, 9), best)
    if not gaps:
        return {"bins": 0}
    g = np.array(list(gaps.values()))
    return {"bins": int(len(g)), "float_max": round(float(g.max()), 4), "pen_min": round(float(g.min()), 4),
            "median": round(float(np.median(g)), 4), "float_bins_gt10mm": int((g > 0.010).sum()),
            "pen_bins_lt_m20mm": int((g < -0.020).sum()),
            "float_where_m": sorted({(round(k[0] * 0.1, 1), round(k[1] * 0.1, 1)) for k, v in gaps.items() if v > 0.010})[:8]}


C = {}
TOP = lambda V: V[:, 2] > -1e9


def edge_top(name, test):
    """top-surface vertices of a roof object on an edge (test(V) mask), highest per plan position."""
    def sel(V):
        m = test(V)
        k = np.round(V[:, :2] / 0.002).astype(np.int64)
        keep = np.zeros(len(V), bool)
        order = np.lexsort((-V[:, 2], k[:, 1], k[:, 0]))
        ks = k[order]
        first = np.ones(len(order), bool); first[1:] = np.any(ks[1:] != ks[:-1], 1)
        keep[order[first]] = True                      # highest vertex of each plan position = top surface
        return m & keep
    return sel


ob = bpy.data.objects["Yane_Doban_Ichimonji_Main"]; Vr = verts(ob)
Xe, Ye = np.abs(Vr[:, 0]).max(), np.abs(Vr[:, 1]).max()
eave = lambda V: (np.abs(np.abs(V[:, 0]) - Xe) < 1e-3) | (np.abs(np.abs(V[:, 1]) - Ye) < 1e-3)
C["eave_edge_over_nokitsuke (expect +0.008)"] = contact("Yane_Doban_Ichimonji_Main", ["Nokitsuke_Doban_EaveStack"], 0.05,
                                                        edge_top("Main", eave))
C["nokitsuke_on_uragou"] = contact("Nokitsuke_Doban_EaveStack", ["Uragou_EaveBoard", "Kayaoi_EaveRail"], 0.10)
Vg = verts(bpy.data.objects["Yane_Doban_Ichimonji_Tsuma"]); xv = np.abs(Vg[:, 0]).max()
verge = lambda V: np.abs(np.abs(V[:, 0]) - xv) < 1e-3
C["gable_verge_over_nobori (expect ~0)"] = contact("Yane_Doban_Ichimonji_Tsuma", ["Nobori_Nokitsuke_Doban_Verge"], 0.05,
                                                   edge_top("Tsuma", verge))
Vn = verts(bpy.data.objects["Nobori_Nokitsuke_Doban_Verge"])
C["hafu_top_under_nobori (expect ~0)"] = contact("Hafu_GableBargeboard", ["Nobori_Nokitsuke_Doban_Verge"], 0.03, up=True)
Vk = verts(bpy.data.objects["Kohai_Yane_Doban_Ichimonji"]); ykmin = Vk[:, 1].min()
C["kohai_front_edge_over_nokitsuke (expect +0.008)"] = contact("Kohai_Yane_Doban_Ichimonji", ["Kohai_Nokitsuke_Doban"], 0.05,
                                                               edge_top("Kohai", lambda V: np.abs(V[:, 1] - ykmin) < 1e-3))
C["karahafu_top_under_nokitsuke (expect ~0)"] = contact("Karahafu_CurvedBargeboard", ["Kohai_Nokitsuke_Doban"], 0.03, up=True)
C["hakomune_on_roof"] = contact("Hakomune_BoxRidge", ["Yane_Doban_Ichimonji_Tsuma"], 0.6)
res["contact"] = C

res["no_sumimune"] = not any(n in bpy.data.objects for n in ("Sumimune_HipRidge", "Sumioni_HipEndBoard"))
res["meshes_without_uv"] = [o.name for o in bpy.data.objects if o.type == "MESH" and not o.data.uv_layers]

# 一文字葺 rows: top-surface vertices on a step row (lip at its maximum) must sit on a texture row line
ob = bpy.data.objects["Yane_Doban_Ichimonji_Main"]
me = ob.data
uv = np.empty(len(me.loops) * 2); me.uv_layers[0].data.foreach_get("uv", uv); uv = uv.reshape(-1, 2)
lv = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", lv)
fr = np.mod(uv[:, 1] * 10.0, 1.0)
dist = np.minimum(fr, 1 - fr)
res["uv_rows"] = {"loops": int(len(uv)), "on_row_lines(<0.002)": int((dist < 0.002).sum()),
                  "row_pitch_m": 0.18}

# triangle counts of the copper objects
tri = {}
for o in bpy.data.objects:
    if o.type == "MESH" and ("Doban" in o.name or "Nokitsuke" in o.name or o.name.startswith("Hakomune")):
        o.data.calc_loop_triangles(); tri[o.name] = len(o.data.loop_triangles)
res["tris"] = tri
print("INSPECT_JSON " + json.dumps(res, ensure_ascii=False))
