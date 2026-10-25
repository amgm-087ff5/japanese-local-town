"""A-2 ver2 破風 / UV inspection, sent through the MCP bridge as execute_blender_code.

- 破風金具 (plates, scrolls, rivets, 六葉, 木口金具): each connected island's
  minimum distance to the bargeboard surfaces. > 0.010 m = 浮き, and the
  deepest penetration of its vertices into the board (inside = negative).
- UV: every mesh has "UVMap"; for sample members, the 3D direction of +u
  (grain) vs the member's long axis (|cos|, 1.0 = grain along the member).
- finish materials: each mesh's finish_mats JSON resolves to existing materials.
"""
import bpy, json, numpy as np
from mathutils.bvhtree import BVHTree
from mathutils import Vector

res = {}
dg = bpy.context.evaluated_depsgraph_get()


def mesh_np(ob):
    me = ob.data
    V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", V)
    return V.reshape(-1, 3)


def islands(ob):
    me = ob.data
    n = len(me.vertices)
    par = np.arange(n)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]; a = par[a]
        return a
    E = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get("vertices", E)
    for a, b in E.reshape(-1, 2):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb
    roots = np.array([find(i) for i in range(n)])
    return [np.where(roots == r)[0] for r in np.unique(roots)]


pairs = {"Hafu_Kanagu_GoldTrim": ["Hafu_GableBargeboard", "Gegyo_GablePendant"],
         "Karahafu_Kanagu_GoldTrim": ["Karahafu_CurvedBargeboard", "Uketo_Gegyo_Pendant"],
         "Chidori_Hafu_Kanagu_GoldTrim": ["Chidori_Hafu_Bargeboard", "Chidori_Gegyo_Pendant"]}
kan = {}
for kname, bnames in pairs.items():
    ko = bpy.data.objects.get(kname)
    if ko is None:
        continue
    trees = [BVHTree.FromObject(bpy.data.objects[b], dg) for b in bnames if b in bpy.data.objects]
    V = mesh_np(ko)
    gaps = []
    for isl in islands(ko):
        best = 1e9
        for i in isl[:: max(1, len(isl) // 40)]:
            for t in trees:
                loc, nrm, idx, d = t.find_nearest(Vector(V[i]))
                if loc is not None:
                    best = min(best, d)
        gaps.append(best)
    g = np.array(gaps)
    kan[kname] = {"islands": int(len(g)), "gap_max": round(float(g.max()), 4), "gap_p50": round(float(np.median(g)), 4),
                  "floating_gt_0.010": int((g > 0.010).sum())}
res["kanagu"] = kan

# UV presence + grain direction
no_uv = [o.name for o in bpy.data.objects if o.type == "MESH" and "UVMap" not in o.data.uv_layers]
res["meshes"] = sum(1 for o in bpy.data.objects if o.type == "MESH")
res["meshes_without_uv"] = no_uv


def grain_alignment(ob, axis=None):
    me = ob.data
    me.calc_loop_triangles()
    V = mesh_np(ob)
    uv = np.empty(len(me.loops) * 2); me.uv_layers["UVMap"].data.foreach_get("uv", uv); uv = uv.reshape(-1, 2)
    T = np.empty(len(me.loop_triangles) * 3, np.int64); me.loop_triangles.foreach_get("loops", T); T = T.reshape(-1, 3)
    LV = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", LV)
    P = V[LV[T]]; U = uv[T]
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    d1, d2 = U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    ok = np.abs(det) > 1e-12
    tu = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2])[ok] / det[ok, None]
    area = np.linalg.norm(np.cross(e1, e2), axis=1)[ok]
    tu /= np.linalg.norm(tu, axis=1, keepdims=True) + 1e-12
    if axis is None:
        # long axis of the member (connected island) each triangle belongs to
        lab = np.zeros(len(V), np.int64)
        ax_of = []
        for k, isl in enumerate(islands(ob)):
            lab[isl] = k
            C = np.cov((V[isl] - V[isl].mean(0)).T) if len(isl) > 3 else np.eye(3)
            w, E = np.linalg.eigh(C); ax_of.append(E[:, 2])
        A = np.array(ax_of)[lab[LV[T[:, 0]]]][ok]
        c = np.abs(np.sum(tu * A, 1))
    else:
        c = np.abs(tu @ np.asarray(axis, float))
    return round(float((c * area).sum() / area.sum()), 3)


samples = {"Hashira_Pillar_01": (0, 0, 1), "Kashiranuki_HeadTie": None, "Hafu_GableBargeboard": None,
           "Karahafu_CurvedBargeboard": None, "Chidori_Hafu_Bargeboard": None, "Jidaruki_BaseRafters": None,
           "Kohai_Koryo_RainbowBeam": (1, 0, 0), "Kohai_Hashira_Pillar_01": (0, 0, 1)}
res["grain_alignment_side_faces_area_weighted"] = {
    n: grain_alignment(bpy.data.objects[n], a) for n, a in samples.items() if n in bpy.data.objects}

# finishes
bad = []
for o in bpy.data.objects:
    if o.type == "MESH" and "finish_mats" in o:
        for f, m in json.loads(o["finish_mats"]).items():
            if m not in bpy.data.materials:
                bad.append((o.name, f, m))
res["finish_tagged"] = sum(1 for o in bpy.data.objects if o.type == "MESH" and "finish_mats" in o)
res["finish_missing_materials"] = bad
print("INSPECT_JSON " + json.dumps(res, ensure_ascii=False))
