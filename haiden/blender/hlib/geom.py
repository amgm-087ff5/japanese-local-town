"""Procedural geometry helpers (numpy based) for the haiden builder.

All builders return (V, F) where V is (n,3) float array and F is either an int
ndarray (m,k) or a list of index lists. MB accumulates them and turns them into
a bpy mesh with per-loop triplanar UVs (so baked tile textures work in glTF).
"""
import math
import numpy as np
import bpy
from mathutils.geometry import tessellate_polygon
from mathutils import Vector

Z = np.array([0.0, 0.0, 1.0])


def nrm(v, axis=-1):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=axis, keepdims=True)
    n[n < 1e-12] = 1.0
    return v / n


class MB:
    """Mesh builder: accumulate vertex/face chunks, emit a bpy mesh."""

    def __init__(self):
        self.V = []
        self.Fa = []      # ndarray chunks (m,k)
        self.Fl = []      # python list faces (ngons)
        self.n = 0

    def add(self, V, F):
        V = np.asarray(V, float).reshape(-1, 3)
        if isinstance(F, np.ndarray):
            if F.size:
                self.Fa.append(F.astype(np.int64) + self.n)
        else:
            self.Fl.extend([[i + self.n for i in f] for f in F])
        self.V.append(V)
        self.n += len(V)
        return self

    def addt(self, VF):
        return self.add(*VF)

    def empty(self):
        return self.n == 0

    def to_mesh(self, name, uv_tile=2.0, uv_mode="triplanar"):
        V = np.concatenate(self.V) if self.V else np.zeros((0, 3))
        loops, totals = [], []
        for f in self.Fa:
            loops.append(f.ravel())
            totals.append(np.full(len(f), f.shape[1]))
        if self.Fl:
            loops.append(np.array([i for f in self.Fl for i in f], np.int64))
            totals.append(np.array([len(f) for f in self.Fl]))
        lv = np.concatenate(loops) if loops else np.zeros(0, np.int64)
        tot = np.concatenate(totals) if totals else np.zeros(0, np.int64)
        starts = np.zeros(len(tot), np.int64)
        if len(tot):
            starts[1:] = np.cumsum(tot)[:-1]
        me = bpy.data.meshes.new(name)
        me.vertices.add(len(V))
        me.vertices.foreach_set("co", V.astype(np.float32).ravel())
        me.loops.add(len(lv))
        me.loops.foreach_set("vertex_index", lv.astype(np.int32))
        me.polygons.add(len(tot))
        me.polygons.foreach_set("loop_start", starts.astype(np.int32))
        me.polygons.foreach_set("loop_total", tot.astype(np.int32))
        me.update(calc_edges=True)
        me.validate(clean_customdata=False)
        if len(tot) and uv_mode == "grain":
            uv = me.uv_layers.new(name="UVMap")
            uv.data.foreach_set("uv", grain_uv(V, lv, starts, tot, uv_tile).astype(np.float32).ravel())
            return me
        # triplanar per-face UV
        if len(tot):
            P = V[lv]
            a = V[lv[starts]]
            b = V[lv[starts + 1]]
            c = V[lv[starts + np.minimum(2, tot - 1)]]
            fn = np.abs(np.cross(b - a, c - a))
            ax = np.argmax(fn, axis=1)
            axl = np.repeat(ax, tot)
            u = np.where(axl == 0, P[:, 1], P[:, 0])
            v = np.where(axl == 2, P[:, 1], P[:, 2])
            uv = me.uv_layers.new(name="UVMap")
            uv.data.foreach_set("uv", (np.stack([u, v], 1) / uv_tile).astype(np.float32).ravel())
        return me


def grain_uv(V, lv, starts, tot, uv_tile=2.0):
    """Per-loop UV following each member's long axis (木目方向).

    Each connected part (a member: beam, board, rafter, tile ...) gets a local
    PCA frame (g = longest axis, e2, e3). Side faces map u along g (the grain
    runs along the member), v along whichever of e2/e3 lies in the face; end
    faces (normal ~ g) map (e2, e3) = end grain. A per-part random offset keeps
    neighbouring members from showing the same stretch of the tile.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    nv = len(V)
    nxt = np.arange(len(lv)) + 1
    ends = starts + tot
    nxt[ends - 1] = starts
    a_, b_ = lv, lv[nxt]
    g = coo_matrix((np.ones(len(a_), np.int8), (a_, b_)), shape=(nv, nv))
    ncomp, lab = connected_components(g, directed=False)
    cnt = np.bincount(lab, minlength=ncomp).astype(float)
    cnt[cnt == 0] = 1
    mu = np.stack([np.bincount(lab, V[:, i], ncomp) for i in range(3)], 1) / cnt[:, None]
    D = V - mu[lab]
    C = np.zeros((ncomp, 3, 3))
    for i in range(3):
        for j in range(i, 3):
            C[:, i, j] = C[:, j, i] = np.bincount(lab, D[:, i] * D[:, j], ncomp) / cnt
    C += np.eye(3)[None] * 1e-12
    w, E = np.linalg.eigh(C)                     # ascending eigenvalues
    gax, e2, e3 = E[:, :, 2], E[:, :, 1], E[:, :, 0]
    fc = lab[lv[starts]]                         # component of each face
    a = V[lv[starts]]; b = V[lv[starts + 1]]; c = V[lv[starts + np.minimum(2, tot - 1)]]
    fn = nrm(np.cross(b - a, c - a))
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
    u = (u + off[fc[lf], 0]) / uv_tile
    v = (v + off[fc[lf], 1]) / uv_tile
    return np.stack([u, v], 1)


# ---------------------------------------------------------------- primitives

def grid_faces(nr, nc, closed_c=False, flip=False):
    """Quad faces for a nr x nc vertex grid (row-major)."""
    cols = nc if closed_c else nc - 1
    r, c = np.meshgrid(np.arange(nr - 1), np.arange(cols), indexing="ij")
    r = r.ravel(); c = c.ravel()
    c2 = (c + 1) % nc
    a = r * nc + c; b = r * nc + c2; d = (r + 1) * nc + c; e = (r + 1) * nc + c2
    F = np.stack([a, b, e, d], 1)
    return F[:, ::-1] if flip else F


def cap_faces(ring2d, offset, reverse=False):
    tris = tessellate_polygon([[Vector((p[0], p[1], 0.0)) for p in ring2d]])
    F = [[offset + t[0], offset + t[1], offset + t[2]] for t in tris]
    if reverse:
        F = [f[::-1] for f in F]
    return F


def poly_area(p):
    p = np.asarray(p)
    return 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])


def ccw(p):
    p = np.asarray(p, float)
    return p if poly_area(p) > 0 else p[::-1]


def rect_profile(w, h, ch=0.0, cx=0.0, cy=0.0):
    """Centered rectangle (optionally chamfered = 8-gon) profile, CCW."""
    a, b = w / 2, h / 2
    if ch <= 0:
        P = [(-a, -b), (a, -b), (a, b), (-a, b)]
    else:
        ch = min(ch, a * 0.45, b * 0.45)
        P = [(-a + ch, -b), (a - ch, -b), (a, -b + ch), (a, b - ch), (a - ch, b), (-a + ch, b), (-a, b - ch), (-a, -b + ch)]
    return np.array(P) + [cx, cy]


def circle_profile(r, n=12):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.stack([r * np.cos(t), r * np.sin(t)], 1)


def sweep(path, prof, mode="vertical", closed_path=False, cap=True, scale=None, up=None):
    """Sweep a closed 2D profile (u,v) along a 3D path.

    mode="vertical": u = horizontal side (right of travel, mitred), v = world Z.
    mode="normal":   rotation-minimising frames, profile perpendicular to path.
    scale: optional per-point (m,) or (m,2) scale of the profile.
    """
    P = np.asarray(path, float)
    prof = np.asarray(prof, float)
    m, k = len(P), len(prof)
    if scale is None:
        S = np.ones((m, 2))
    else:
        S = np.asarray(scale, float)
        S = np.stack([S, S], 1) if S.ndim == 1 else S
    if mode == "vertical":
        T = np.diff(P, axis=0)
        if closed_path:
            T = np.vstack([T, P[0] - P[-1]])
        Th = T.copy(); Th[:, 2] = 0
        Th = nrm(Th)
        side_seg = np.stack([Th[:, 1], -Th[:, 0], np.zeros(len(Th))], 1)
        side = np.zeros((m, 3))
        for i in range(m):
            if closed_path:
                s0, s1 = side_seg[i - 1], side_seg[i % len(side_seg)]
            else:
                s0 = side_seg[max(i - 1, 0)]
                s1 = side_seg[min(i, len(side_seg) - 1)]
            sm = s0 + s1
            ln = np.linalg.norm(sm)
            if ln < 1e-6:
                side[i] = s1
            else:
                sm /= ln
                side[i] = sm / max(np.dot(sm, s1), 0.3)
        U = side
        Vv = np.tile(Z, (m, 1))
    else:
        T = np.gradient(P, axis=0) if m > 2 else np.tile(P[-1] - P[0], (m, 1))
        if closed_path:
            T = np.roll(P, -1, 0) - np.roll(P, 1, 0)
        T = nrm(T)
        u0 = np.cross(T[0], up if up is not None else Z)
        if np.linalg.norm(u0) < 1e-6:
            u0 = np.cross(T[0], [1.0, 0, 0])
        u0 = nrm(u0)
        U = np.zeros((m, 3)); U[0] = u0
        for i in range(1, m):  # double reflection RMF
            v1 = P[i] - P[i - 1]
            c1 = np.dot(v1, v1)
            if c1 < 1e-14:
                U[i] = U[i - 1]; continue
            rL = U[i - 1] - (2 / c1) * np.dot(v1, U[i - 1]) * v1
            tL = T[i - 1] - (2 / c1) * np.dot(v1, T[i - 1]) * v1
            v2 = T[i] - tL
            c2 = np.dot(v2, v2)
            U[i] = rL - (2 / c2) * np.dot(v2, rL) * v2 if c2 > 1e-14 else rL
        U = nrm(U)
        Vv = nrm(np.cross(T, U))
    pu = prof[None, :, 0] * S[:, 0:1]
    pv = prof[None, :, 1] * S[:, 1:2]
    V = P[:, None, :] + U[:, None, :] * pu[..., None] + Vv[:, None, :] * pv[..., None]
    V = V.reshape(-1, 3)
    F = grid_faces(m, k, closed_c=True)
    if closed_path:
        r = np.arange(k); r2 = (r + 1) % k
        last = (m - 1) * k
        F = np.vstack([F, np.stack([last + r, last + r2, r2, r], 1)])
    Fl = []
    if cap and not closed_path:
        Fl += cap_faces(prof, 0, reverse=False)
        Fl += cap_faces(prof, (m - 1) * k, reverse=True)
    if mode == "vertical":
        # orientation check: our side vector is right-handed -> flip if needed
        pass
    return V, _merge_faces(F, Fl)


def _merge_faces(F, Fl):
    if not Fl:
        return F
    return [list(f) for f in F.tolist()] + Fl


def beams(P0, P1, w, h, ch=0.0, up=None, roll_side=None):
    """Vectorised straight beams with a (chamfered) rectangular section.

    w: size along the 'side' axis, h: size along the 'up' axis. up default Z;
    for near-vertical beams the side axis becomes X.
    """
    P0 = np.atleast_2d(np.asarray(P0, float)); P1 = np.atleast_2d(np.asarray(P1, float))
    n = len(P0)
    D = nrm(P1 - P0)
    upv = np.tile(Z if up is None else np.asarray(up, float), (n, 1))
    side = np.cross(D, upv)
    bad = np.linalg.norm(side, axis=1) < 1e-6
    if roll_side is not None:
        side[:] = roll_side
    side[bad] = np.cross(D[bad], [0, 1.0, 0]) if bad.any() else side[bad]
    side = nrm(side)
    uu = nrm(np.cross(side, D))
    W = np.broadcast_to(np.asarray(w, float), (n,))
    H = np.broadcast_to(np.asarray(h, float), (n,))
    C = np.broadcast_to(np.asarray(ch, float), (n,))
    prof0 = rect_profile(1, 1, 0.0 if np.all(C <= 0) else 0.2)
    k = len(prof0)
    Vs = []
    for i in range(n):
        pr = rect_profile(W[i], H[i], C[i]) if k == 8 else rect_profile(W[i], H[i])
        a = P0[i][None] + side[i] * pr[:, 0:1] + uu[i] * pr[:, 1:2]
        b = P1[i][None] + side[i] * pr[:, 0:1] + uu[i] * pr[:, 1:2]
        Vs.append(np.vstack([a, b]))
    V = np.concatenate(Vs)
    r = np.arange(k); r2 = (r + 1) % k
    side_f = np.stack([r, r2, r2 + k, r + k], 1)
    capA = np.arange(k)[::-1][None]
    capB = (np.arange(k) + k)[None]
    off = (np.arange(n) * 2 * k)[:, None, None]
    Fs = (side_f[None] + off).reshape(-1, 4)
    if k == 4:
        Fc = np.vstack([(capA[None] + off).reshape(-1, 4), (capB[None] + off).reshape(-1, 4)])
        return V, np.vstack([Fs, Fc])
    # octagon caps -> ngon list
    Fl = Fs.tolist()
    for i in range(n):
        o = i * 2 * k
        Fl.append(list(o + np.arange(k)[::-1]))
        Fl.append(list(o + k + np.arange(k)))
    return V, Fl


def box(mn, mx):
    mn = np.asarray(mn, float); mx = np.asarray(mx, float)
    x0, y0, z0 = mn; x1, y1, z1 = mx
    V = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    F = np.array([[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]])
    return V, F


def cbox(mn, mx, ch):
    """Chamfered box (all 12 edges chamfered) via loft of 8-gon sections."""
    mn = np.asarray(mn, float); mx = np.asarray(mx, float)
    c = (mn + mx) / 2; s = mx - mn
    ch = min(ch, s.min() * 0.45)
    secs = [(s[0] / 2 - ch, s[1] / 2 - ch, mn[2]), (s[0] / 2, s[1] / 2, mn[2] + ch),
            (s[0] / 2, s[1] / 2, mx[2] - ch), (s[0] / 2 - ch, s[1] / 2 - ch, mx[2])]
    return loft_rect(secs, c[:2], ch=ch)


def loft_rect(sections, center=(0, 0), ch=0.0, rot=0.0, cap=True):
    """Stack of (chamfered) rectangles: sections = [(hx, hy, z), ...]."""
    cx, cy = center
    cr, sr = math.cos(rot), math.sin(rot)
    rings = []
    for hx, hy, z in sections:
        pr = rect_profile(2 * hx, 2 * hy, ch)
        x = pr[:, 0] * cr - pr[:, 1] * sr + cx
        y = pr[:, 0] * sr + pr[:, 1] * cr + cy
        rings.append(np.stack([x, y, np.full(len(pr), z)], 1))
    k = len(rings[0]); m = len(rings)
    V = np.concatenate(rings)
    F = grid_faces(m, k, closed_c=True)
    Fl = []
    if cap:
        Fl.append(list(np.arange(k)[::-1]))
        Fl.append(list((m - 1) * k + np.arange(k)))
    return V, _merge_faces(F, Fl)


def lathe(profile, center=(0, 0, 0), seg=32, cap_bottom=True, cap_top=True, axis="z"):
    """Revolve [(r, h), ...] around a vertical axis at center."""
    prof = np.asarray(profile, float)
    t = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    ct, st = np.cos(t), np.sin(t)
    m = len(prof)
    R = prof[:, 0:1]; H = prof[:, 1:2]
    X = R * ct[None]; Y = R * st[None]; Zh = np.broadcast_to(H, X.shape)
    if axis == "z":
        V = np.stack([X, Y, Zh], -1)
    elif axis == "x":
        V = np.stack([Zh, X, Y], -1)
    else:
        V = np.stack([X, Zh, Y], -1)
    V = V.reshape(-1, 3) + np.asarray(center, float)
    F = grid_faces(m, seg, closed_c=True)[:, ::-1]
    Fl = []
    if cap_bottom and prof[0, 0] > 1e-6:
        Fl.append(list(np.arange(seg)[::-1]))
    if cap_top and prof[-1, 0] > 1e-6:
        Fl.append(list((m - 1) * seg + np.arange(seg)))
    return V, _merge_faces(F, Fl)


def offset_poly(p, d):
    """Offset a CCW polygon inward by d (simple miter)."""
    p = np.asarray(p, float)
    prv = np.roll(p, 1, 0); nxt = np.roll(p, -1, 0)
    e0 = nrm(p - prv); e1 = nrm(nxt - p)
    n0 = np.stack([-e0[:, 1], e0[:, 0]], 1)
    n1 = np.stack([-e1[:, 1], e1[:, 0]], 1)
    mm = n0 + n1
    dd = 1 + np.sum(n0 * n1, 1)
    dd[dd < 0.25] = 0.25
    return p + mm / dd[:, None] * d


def extrude_poly(outline, thick, frame, holes=(), bevel=0.0):
    """Extrude a 2D outline (with optional holes) to a slab.

    frame = (origin, U, V): world origin and the world vectors of local 2D
    axes; thickness goes along W = U x V, centered.
    """
    o, U, Vv = (np.asarray(a, float) for a in frame)
    W = nrm(np.cross(U, Vv))
    outer = ccw(outline)
    hs = [ccw(h)[::-1] for h in holes]   # holes CW
    t2 = thick / 2
    rings = []   # list of (pts2d, w)
    if bevel > 0:
        inset = offset_poly(outer, bevel)
        rings = [(inset, -t2), (outer, -t2 + bevel), (outer, t2 - bevel), (inset, t2)]
    else:
        rings = [(outer, -t2), (outer, t2)]

    def to3(p2, w):
        return o + p2[:, 0:1] * U + p2[:, 1:2] * Vv + w * W

    Vs = [to3(p, w) for p, w in rings]
    k = len(outer)
    V = np.concatenate(Vs)
    F = grid_faces(len(rings), k, closed_c=True)
    Fl = F.tolist()
    base = len(V)
    # holes walls
    hole_rings_front, hole_rings_back = [], []
    Vh = []
    for h in hs:
        kb = len(h)
        a = to3(h, -t2); b = to3(h, t2)
        ia = base; ib = base + kb
        Vh += [a, b]
        for i in range(kb):
            j = (i + 1) % kb
            Fl.append([ia + i, ia + j, ib + j, ib + i])
        hole_rings_back.append((h, ia)); hole_rings_front.append((h, ib))
        base += 2 * kb
    if Vh:
        V = np.concatenate([V] + Vh)
    # caps with holes
    front_outer = rings[-1][0]; back_outer = rings[0][0]
    fo = (len(rings) - 1) * k; bo = 0
    for (outer2d, oidx, hl, rev) in ((front_outer, fo, hole_rings_front, False), (back_outer, bo, hole_rings_back, True)):
        polys = [[Vector((p[0], p[1], 0)) for p in outer2d]] + [[Vector((p[0], p[1], 0)) for p in h] for h, _ in hl]
        idxmap = [oidx + i for i in range(len(outer2d))]
        for h, hi in hl:
            idxmap += [hi + i for i in range(len(h))]
        for t in tessellate_polygon(polys):
            f = [idxmap[t[0]], idxmap[t[1]], idxmap[t[2]]]
            # make orientation consistent with W
            Fl.append(f[::-1] if rev else f)
    return V, Fl


def fix_tri_orientation(V, Fl, W):
    return Fl


# --------------------------------------------------------------- curves

def bezier(p0, p1, p2, p3, n=24):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, float) for p in (p0, p1, p2, p3))
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def catenary(p0, p1, sag, n=40):
    t = np.linspace(0, 1, n)[:, None]
    p0 = np.asarray(p0, float); p1 = np.asarray(p1, float)
    P = p0 + (p1 - p0) * t
    P[:, 2] -= sag * (1 - (2 * t[:, 0] - 1) ** 2)
    return P


def resample(P, step):
    P = np.asarray(P, float)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = max(2, int(math.ceil(s[-1] / step)) + 1)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, P[:, i]) for i in range(3)], 1)


def helix_strands(center, radius, r_strand, n_strands=3, twist_pitch=0.25, seg=10, scale=None):
    """Return list of sweeps (V,F) for twisted strands around a centre path."""
    C = np.asarray(center, float)
    T = nrm(np.gradient(C, axis=0))
    up = np.array([0, 0, 1.0])
    U = nrm(np.cross(T, up))
    bad = np.linalg.norm(np.cross(T, up), axis=1) < 1e-6
    U[bad] = [1, 0, 0]
    Vv = nrm(np.cross(T, U))
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))])
    R = np.ones(len(C)) * radius if scale is None else radius * np.asarray(scale)
    Rs = np.ones(len(C)) * r_strand if scale is None else r_strand * np.asarray(scale)
    out = []
    for k in range(n_strands):
        ang = 2 * np.pi * (s / twist_pitch + k / n_strands)
        P = C + U * (R * np.cos(ang))[:, None] + Vv * (R * np.sin(ang))[:, None]
        out.append(sweep(P, circle_profile(1.0, seg), mode="normal", scale=Rs))
    return out
