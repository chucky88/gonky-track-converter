"""Is there ground where the game is going to place the car? — in ENGINE coordinates.

    python3 verificar_fisica.py <pack>/Tracks/_data/aiw/X.aiw  <physics>/X_physics.obj

`verificar_encaje.py` checks the alignment INSIDE Blender. This checks what actually gets
installed: the `.aiw` exported by OMTT against the OBJ that is cooked into `.csm`. They are two
files of the package, written through different paths, and **if they do not match, the car sinks
into the void without anything raising an error**.

🔴 Why it exists: it happened. The OBJ came out with Blender's axes (Z up) and the AIW with the
engine's (Y up): the collision ended up rotated 90°. The track loaded, looked fine, and on entering
you fell into the void.

No Blender and no dependencies: it runs anywhere.
"""

import math
import re
import sys

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
TOLERANCIA_M = 2.0


def leer_obj(path, al_espacio_del_aiw: bool = True):
    """Reads the physics OBJ and, by default, brings it **into AIW space**.

    🔴 Why: the physics OBJ and the AIW **are not in the same space**: the OBJ is exported with
    Blender's default axes `(x, z, −y)` and the AIW with `(x, z, y)`. They differ in the sign of
    Z, i.e. **they are mirrored**.

    Measured on the toolkit's example project, which works in the game: of its 28 grid slots,
    with the OBJ as is only **8** have asphalt underneath; **with Z flipped, all 28 do**, at a
    height of 0.00 m.

    ⚠️ Without that correction the check gave ✅ with mirrored physics: it compared the exported
    AIW against the exported OBJ, both written with the SAME wrong convention. Consistent with each
    other, and mirrored relative to the track you see.
    """
    verts = []
    with open(path, errors="ignore") as fh:
        for l in fh:
            if l.startswith("v "):
                p = l.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
    if al_espacio_del_aiw:
        verts = [(x, y, -z) for x, y, z in verts]
    return verts


def leer_aiw(path):
    pos = []
    with open(path, errors="ignore") as fh:
        for l in fh:
            if l.lower().startswith("wp_pos"):
                n = [float(x) for x in _NUM.findall(l.split("=", 1)[1])]
                if len(n) >= 3:
                    pos.append(tuple(n[:3]))
    return pos


def rangos(pts):
    ejes = list(zip(*pts))
    return [(min(e), max(e), max(e) - min(e)) for e in ejes]


def rejilla(verts, lado=4.0):
    """HORIZONTAL (X,Z) index: cell of `lado` metres -> vertices that fall inside it.

    The question is not "which vertex is closest?" —that measures the mesh density, not whether
    the place is right— but **"is there anything right underneath?"**. That is why the index
    ignores height: it searches around in the plane and looks at the height difference.
    """
    g = {}
    for v in verts:
        g.setdefault((int(v[0] // lado), int(v[2] // lado)), []).append(v)
    return g, lado


def desnivel_al_suelo(g, lado, p, radio_m=3.0):
    """Smallest HEIGHT difference to the collision under the point (within `radio_m`).

    Returns infinity if there is no collision at all within that horizontal radius: that is a
    real hole, not a sparse mesh.
    """
    r = int(radio_m // lado) + 1
    cx, cz = int(p[0] // lado), int(p[2] // lado)
    mejor = float("inf")
    for dx in range(-r, r + 1):
        for dz in range(-r, r + 1):
            for v in g.get((cx + dx, cz + dz), ()):
                if math.hypot(v[0] - p[0], v[2] - p[2]) <= radio_m:
                    d = abs(v[1] - p[1])
                    if d < mejor:
                        mejor = d
    return mejor


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    aiw, obj = leer_aiw(argv[1]), leer_obj(argv[2])
    if not aiw or not obj:
        print(f"missing data: {len(aiw)} waypoints, {len(obj)} vertices")
        return 2

    ra, ro = rangos(aiw), rangos(obj)
    print(f"AIW  {len(aiw):>6} waypoints   X {ra[0][2]:7.1f} · Y {ra[1][2]:7.1f} · Z {ra[2][2]:7.1f} m")
    print(f"OBJ  {len(obj):>6} vertices    X {ro[0][2]:7.1f} · Y {ro[1][2]:7.1f} · Z {ro[2][2]:7.1f} m")

    # 1) Is height on Y in both? In the engine Y is vertical, and a track's elevation change is
    #    always much smaller than its extent.
    fallos = []
    for nom, r in (("AIW", ra), ("OBJ", ro)):
        if r[1][2] > min(r[0][2], r[2][2]):
            fallos.append(f"{nom}: height is NOT on Y (Y={r[1][2]:.1f} m is the largest axis)")

    # 2) Does every waypoint fall on something solid?
    g, lado = rejilla(obj)
    dists = sorted(desnivel_al_suelo(g, lado, p) for p in aiw)
    n = len(dists)
    finitas = [d for d in dists if math.isfinite(d)]
    lejos = n - len(finitas)
    if finitas:
        p50 = finitas[len(finitas) // 2]
        p95 = finitas[int(len(finitas) * 0.95)]
        fuera = sum(1 for d in finitas if d > TOLERANCIA_M) + lejos
        print(f"drop to the collision below -> median {p50:.2f} m · p95 {p95:.2f} m")
        print(f"NO GROUND underneath (>{TOLERANCIA_M} m drop or nothing within 3 m): {fuera} of {n} "
              f"({100 * fuera / n:.1f} %)")
        if fuera > n * 0.05:
            fallos.append(f"{fuera} waypoints with no collision nearby: the car would sink")
    else:
        fallos.append("NO waypoint has collision nearby")

    print()
    if fallos:
        for f in fallos:
            print(f"🔴 {f}")
        return 1
    print("✅ the collision is where the game will put the car")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


def normales_del_suelo(obj_path):
    """Which way do the ground faces point? UPWARDS, or the car goes through them.

    🔴 It exists because this was wrong for a long time and no check saw it: they all measured
    where the collision is (and it was where it should be), not which way it faces. It counts
    faces, which is the only thing that tells "right way up" from "upside down".
    """
    verts, caras, act = [], [], None
    for ln in open(obj_path):
        if ln.startswith("o "):
            act = ln[2:].strip()
        elif ln.startswith("v "):
            verts.append(tuple(float(x) for x in ln.split()[1:4]))
        elif ln.startswith("f ") and act and act.startswith(("ROADS", "GRASS", "GRAVEL")):
            idx = [int(t.split("/")[0]) for t in ln.split()[1:]]
            caras.append([i - 1 if i > 0 else len(verts) + i for i in idx])
    arriba = abajo = 0
    for f in caras:
        if len(f) < 3:
            continue
        a, b, c = verts[f[0]], verts[f[1]], verts[f[2]]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        ny = u[2] * v[0] - u[0] * v[2]
        if ny > 0:
            arriba += 1
        elif ny < 0:
            abajo += 1
    return {"arriba": arriba, "abajo": abajo, "total": len(caras)}
