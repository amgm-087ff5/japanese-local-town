"""Ornamental / joinery part outlines (2D) and placed solids."""
import math
import numpy as np
from .geom import extrude_poly, loft_rect, lathe, nrm

Zv = np.array([0, 0, 1.0])


def hframe(origin, direction):
    """Frame whose U is a horizontal direction, V is world up."""
    d = np.array([direction[0], direction[1], 0.0])
    d = d / np.linalg.norm(d)
    return (np.asarray(origin, float), d, Zv)


def vframe_face(origin, normal_xy):
    """Frame for a vertical board facing normal_xy: U = horizontal along board, V = up."""
    n = np.array([normal_xy[0], normal_xy[1], 0.0]); n /= np.linalg.norm(n)
    u = np.array([n[1], -n[0], 0.0])  # u x Z = n ?  check: (ny,-nx,0)x(0,0,1) = (-nx,-ny,0) -> -n
    u = -u                              # so that W = U x V = n
    return (np.asarray(origin, float), u, Zv)


# ------------------------------------------------------------ outlines

def hijiki_outline(L, h, curl=0.55, nseg=8):
    """Bracket arm in elevation, centred at 0, bottom ends curved up."""
    a = L / 2
    r = h * curl
    pts = [(-a, h / 2), (a, h / 2), (a, h / 2 - (h - r))]
    # right end bottom curve: quarter arc from (a, -h/2 + r) to (a - r*1.2, -h/2)
    for i in range(1, nseg + 1):
        t = i / nseg * math.pi / 2
        pts.append((a - r * 1.2 * math.sin(t), -h / 2 + r * math.cos(t)))
    for i in range(0, nseg + 1):
        t = math.pi / 2 - i / nseg * math.pi / 2
        pts.append((-a + r * 1.2 * math.sin(t), -h / 2 + r * math.cos(t)))
    pts.append((-a, h / 2 - (h - r)))
    return np.array(pts)


def kibana_outline(L, h, nseg=10):
    """Carved beam-end (木鼻) in elevation from l=0 (beam) to l=L (nose)."""
    pts = [(0, -h / 2), (0, h / 2)]
    # top: straight then roll down into the nose
    pts.append((L * 0.72, h / 2))
    for i in range(1, nseg + 1):
        t = i / nseg * math.pi * 0.9
        pts.append((L * 0.72 + (L * 0.28) * math.sin(t), h / 2 - h * 0.42 * (1 - math.cos(t)) / 2 * 1.2))
    # nose down and scalloped underside back to l=0
    nb = 24
    for i in range(nb + 1):
        l = L * 0.97 * (1 - i / nb)
        z = -h / 2 + 0.06 * h + 0.13 * h * abs(math.sin(3.2 * math.pi * l / L)) * (l / L) ** 0.3
        if i == 0:
            z = -h * 0.05
        pts.append((l, z))
    pts[-1] = (0.0, -h / 2)
    pts = pts[:-1]
    return np.array(pts)


def kaerumata_outline(W, H, n=20):
    """Frog-leg strut: legs spread at the bottom, arch opening inside."""
    pts = []
    tw = 0.07 * W / 0.9 + 0.05
    for i in range(n + 1):      # right outer curve, bottom -> top
        t = i / n
        z = H * t
        x = tw + (W / 2 - tw) * (1 - t) ** 1.7 + 0.03 * math.sin(math.pi * t) * W
        pts.append((x, z))
    for i in range(n, -1, -1):  # left outer curve, top -> bottom
        t = i / n
        z = H * t
        x = tw + (W / 2 - tw) * (1 - t) ** 1.7 + 0.03 * math.sin(math.pi * t) * W
        pts.append((-x, z))
    leg = 0.10 * W
    # inner arch (left foot -> apex -> right foot)
    ah = H * 0.68
    for i in range(n + 1):
        t = i / n
        ang = math.pi * (1 - t)
        x = (W / 2 - leg) * math.cos(ang) * (1 - 0.15 * math.sin(ang))
        z = ah * math.sin(ang) ** 0.8
        pts.append((x, max(z, 0.0)))
    out = []
    for p in pts:
        if not out or (abs(out[-1][0] - p[0]) + abs(out[-1][1] - p[1])) > 1e-5:
            out.append(p)
    if abs(out[0][0] - out[-1][0]) + abs(out[0][1] - out[-1][1]) < 1e-5:
        out.pop()
    return np.array(out)


def heart(cx, cy, s, n=20, invert=True):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    y = -y if invert else y
    return np.stack([cx + x * s / 32, cy + y * s / 32], 1)


def gegyo_outline(W, H, n=16):
    """Inome-gegyo body hanging from y=0 down to -H."""
    pts = [(-W * 0.2, 0.0), (W * 0.2, 0.0)]
    for i in range(1, n + 1):
        t = i / n
        x = W * 0.2 + (W * 0.32) * math.sin(math.pi * t * 0.75) * (1 - t) ** 0.4
        pts.append((x, -H * t))
    for i in range(n - 1, 0, -1):
        t = i / n
        x = W * 0.2 + (W * 0.32) * math.sin(math.pi * t * 0.75) * (1 - t) ** 0.4
        pts.append((-x, -H * t))
    return np.array(pts)


def gegyo_fin(W, H, side=1):
    """Side fin (鰭) of the gegyo, waves."""
    pts = []
    n = 14
    for i in range(n + 1):
        t = i / n
        pts.append((side * (W * 0.22 + W * 0.25 * t), -H * 0.05 - H * 0.35 * t + 0.03 * math.sin(6 * t)))
    for i in range(n, -1, -1):
        t = i / n
        pts.append((side * (W * 0.22 + W * 0.25 * t), -H * 0.18 - H * 0.35 * t - 0.04 * math.sin(5 * t)))
    return np.array(pts) if side > 0 else np.array(pts)[::-1]


def onita_outline(W, H, n=24):
    pts = [(-W / 2, 0), (W / 2, 0), (W / 2, H * 0.18)]
    # shoulder in, then arch over the top with a small point
    r = W * 0.42
    cz = H - r
    for i in range(n + 1):
        a = -math.pi * 0.15 + (math.pi * 1.3) * i / n
        x = r * math.cos(a)
        z = cz + r * math.sin(a)
        if abs(x) < W * 0.05:
            z += 0.06 * H
        pts.append((x, z))
    pts.append((-W / 2, H * 0.18))
    return np.array(pts)


def tabasami_outline(L, H0, H1, n=24):
    """Wedge filling between bracket (bottom, length L) and sloped rafters.
    l=0 at pillar, top edge rises from H0 to H1 at l=L; scroll cut-outs."""
    pts = [(0, 0), (L, 0)]
    for i in range(n + 1):
        t = 1 - i / n
        l = L * t
        z = H0 + (H1 - H0) * t
        wav = 0.025 * math.sin(t * math.pi * 5) * (1 - t)
        pts.append((l, z + wav - 0.01))
    return np.array(pts)


# ------------------------------------------------------------ solids

def to_block(cx, cy, z0, w, h, rot=0.0, ch=0.006):
    """Bearing block (斗): tapered bottom (斗尻), straight top."""
    hw = w / 2
    secs = [(hw * 0.74, hw * 0.74, z0), (hw * 0.80, hw * 0.80, z0 + h * 0.18),
            (hw * 0.90, hw * 0.90, z0 + h * 0.34), (hw * 0.98, hw * 0.98, z0 + h * 0.44),
            (hw, hw, z0 + h * 0.48), (hw, hw, z0 + h)]
    return loft_rect(secs, (cx, cy), ch=ch, rot=rot)


def giboshi(cx, cy, z0, s=1.0, seg=24):
    prof = [(0.050, 0), (0.054, 0.012), (0.054, 0.03), (0.046, 0.036), (0.046, 0.05), (0.056, 0.058),
            (0.056, 0.07), (0.040, 0.078), (0.036, 0.09), (0.060, 0.115), (0.078, 0.15), (0.080, 0.17),
            (0.070, 0.20), (0.050, 0.23), (0.030, 0.255), (0.016, 0.28), (0.007, 0.30), (0.0, 0.315)]
    prof = [(r * s, h * s) for r, h in prof]
    return lathe(prof, (cx, cy, z0), seg)


def orient(V, center, n):
    """Rotate vertices (built around +Z at center) so +Z maps to n."""
    n = nrm(np.asarray(n, float))
    z = np.array([0, 0, 1.0])
    v = np.cross(z, n)
    c = float(np.dot(z, n))
    if np.linalg.norm(v) < 1e-9:
        R = np.eye(3) if c > 0 else np.diag([1, -1, -1])
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + vx + vx @ vx * (1 / (1 + c))
    C = np.asarray(center, float)
    return (np.asarray(V) - C) @ R.T + C


def rokuyo(center, normal, r=0.06, seg=24):
    """Six-leaf nail cover (六葉) disc facing `normal`."""
    t = np.linspace(0, 2 * np.pi, 13)
    prof = [(r * 0.99, 0), (r, 0.004), (r * 0.8, 0.01), (r * 0.45, 0.014), (r * 0.35, 0.024),
            (r * 0.18, 0.03), (0.0, 0.034)]
    V, F = lathe(prof, (0, 0, 0), seg, cap_bottom=True)
    # petal scallop: modulate radius by 6-lobe
    ang = np.arctan2(V[:, 1], V[:, 0])
    k = 1 + 0.12 * np.cos(6 * ang)
    V[:, 0] *= k; V[:, 1] *= k
    V = orient(V, (0, 0, 0), normal) + np.asarray(center, float)
    return V, F
