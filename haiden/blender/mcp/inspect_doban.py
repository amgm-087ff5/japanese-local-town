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


def contact(upper, lowers, maxd=0.25, sel=None):
    up = bpy.data.objects.get(upper)
    los = [bpy.data.objects[n] for n in lowers if n in bpy.data.objects]
    if up is None or not los:
        return None
    trees = [BVHTree.FromObject(o, dg) for o in los]
    V = verts(up)
    if sel is not None:
        V = V[sel(V)]
    gaps = {}
    for p in V:
        best = None
        for t in trees:
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
            "pen_bins_lt_m20mm": int((g < -0.020).sum())}


C = {}
C["roof_edge_on_nokitsuke"] = contact("Yane_Doban_Ichimonji_Main", ["Nokitsuke_Doban_EaveStack"], 0.05)
C["nokitsuke_on_uragou"] = contact("Nokitsuke_Doban_EaveStack", ["Uragou_EaveBoard", "Kayaoi_EaveRail"], 0.10)
C["nobori_on_hafu"] = contact("Nobori_Nokitsuke_Doban_Verge", ["Hafu_GableBargeboard"], 0.10)
C["gable_verge_on_nobori"] = contact("Yane_Doban_Ichimonji_Tsuma", ["Nobori_Nokitsuke_Doban_Verge"], 0.05)
C["gable_foot_on_lower_roof"] = contact("Yane_Doban_Ichimonji_Tsuma", ["Yane_Doban_Ichimonji_Main"], 0.15)
C["kohai_roof_on_nokitsuke"] = contact("Kohai_Yane_Doban_Ichimonji", ["Kohai_Nokitsuke_Doban"], 0.05)
C["kohai_nokitsuke_on_karahafu"] = contact("Kohai_Nokitsuke_Doban", ["Karahafu_CurvedBargeboard"], 0.10)
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
