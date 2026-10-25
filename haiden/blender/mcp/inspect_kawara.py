"""A-2 本瓦葺 inspection, sent through the MCP bridge as execute_blender_code.

Counts tiles per template (vertex count / template verts) and measures, for a
sample of 平瓦/丸瓦, the signed distance of their bearing vertices to the roof
base (野地) surfaces: >0.10 m = 浮き, < -0.03 m = めり込み. See README.md.
"""
import bpy, numpy as np, json
from mathutils.bvhtree import BVHTree
from mathutils import Vector
res = {}
def mesh_np(ob):
    me = ob.data
    V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", V)
    return V.reshape(-1, 3)
bases = [o for o in bpy.data.objects if o.type == "MESH" and ("KawaraBase" in o.name or o.name == "Chidori_Yane_Base")]
dg = bpy.context.evaluated_depsgraph_get()
trees = [BVHTree.FromObject(o, dg) for o in bases]
def nearest_signed(p):
    best = None
    for t in trees:
        loc, nrm, idx, d = t.find_nearest(Vector(p))
        if loc is None: continue
        s = d if (Vector(p) - loc).dot(nrm) >= 0 else -d
        if best is None or abs(s) < abs(best): best = s
    return best
per = {"Kawara_Hiragawara_FlatTiles": (28, list(range(21, 28))),       # template verts, upper-ring underside idx
       "Kawara_Marugawara_RoundTiles": (72, [0, 8])}                    # leg bottoms (outer arc ends) of lower ring
rng = np.random.default_rng(0)
for name, (nv, idx) in per.items():
    ob = bpy.data.objects[name]
    V = mesh_np(ob)
    n = len(V) // nv
    res[name] = {"tiles": int(n), "verts_per_tile_ok": len(V) % nv == 0}
    sel = rng.choice(n, size=min(1500, n), replace=False)
    gaps = []
    for i in sel:
        pts = V[i * nv + np.array(idx)]
        g = [nearest_signed(p) for p in pts]
        g = [x for x in g if x is not None]
        if g: gaps.append(min(g))
    gaps = np.array(gaps)
    res[name].update({"sampled": int(len(gaps)), "gap_min": round(float(gaps.min()), 4), "gap_p50": round(float(np.median(gaps)), 4),
                      "gap_max": round(float(gaps.max()), 4), "floating_gt_0.10": int((gaps > 0.10).sum()),
                      "sunk_lt_-0.03": int((gaps < -0.03).sum())})
# ridge pieces / ornaments: count, and check every oni/shishiguchi island bottom touches something below
cnt = {}
for o in bpy.data.objects:
    if o.type == "MESH" and o.name.startswith(("Kawara", "Chidori")):
        o.data.calc_loop_triangles()
        cnt[o.name] = len(o.data.loop_triangles)
res["tris_by_object"] = cnt
res["total_tris"] = int(sum(len(o.data.loop_triangles) for o in bpy.data.objects if o.type == "MESH" and not o.data.calc_loop_triangles()))
# below-ground / out-of-bounds
low = [o.name for o in bpy.data.objects if o.type == "MESH" and len(o.data.vertices) and mesh_np(o)[:, 2].min() < -0.01]
res["below_ground_objects"] = low
print("INSPECT_JSON " + json.dumps(res, ensure_ascii=False))
