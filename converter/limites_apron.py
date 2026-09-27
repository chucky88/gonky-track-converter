"""How much of the APRON (and of the asphalt) lies INSIDE the track limits (`.gcl`)?

🔴 When the width the AI sees was narrowed to the racing asphalt, the `.gcl` trimming —which used
that same width— left a quarter of the apron outside: driving on it would have counted as going
off track. This measures it on the EXPORTED `.gcl`, using the centres of the collision triangles,
and only what lies within 60 m of the centre line (the oval itself).
"""
import math

import gcl_read as G


def cobertura(ruta_gcl: str, col, central: list, superficies=("ROAD", "APRON"), cerca_m=60.0,
              signo_z=None) -> dict:
    tris = [(a, b, c) for a, b, c, _f in G.triangulos(ruta_gcl)]
    CEL = 8.0
    rej = {}
    for i, (a, b, c) in enumerate(tris):
        xs, zs = (a[0], b[0], c[0]), (a[2], b[2], c[2])
        for gx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
            for gz in range(int(min(zs) // CEL), int(max(zs) // CEL) + 1):
                rej.setdefault((gx, gz), []).append(i)

    def dentro(x, z):
        for i in rej.get((int(x // CEL), int(z // CEL)), ()):
            a, b, c = tris[i]
            d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-9:
                continue
            w1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
            w2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
            if min(w1, w2, 1 - w1 - w2) >= -1e-4:
                return True
        return False

    rc = {}
    for p in central:
        rc.setdefault((int(p[0] // 16), int(p[2] // 16)), []).append(p)

    def cerca(x, z):
        cx, cz = int(x // 16), int(z // 16)
        r = int(cerca_m // 16) + 1
        return any(math.hypot(q[0] - x, q[2] - z) <= cerca_m
                   for dx in range(-r, r + 1) for dz in range(-r, r + 1) for q in rc.get((cx + dx, cz + dz), ()))

    puntos = {s: set() for s in superficies}
    for lista in col.suelo.values():
        for sup, a, b, c in lista:
            if sup in puntos:
                puntos[sup].add((round((a[0] + b[0] + c[0]) / 3, 1), round((a[2] + b[2] + c[2]) / 3, 1)))
    fuera = {}
    signos = (signo_z,) if signo_z else (1, -1)
    mejor = None
    for sz in signos:
        r = {}
        for sup, ps in puntos.items():
            ps = [p for p in ps if cerca(*p)]
            r[sup] = (len(ps), 100.0 * sum(dentro(x, sz * z) for x, z in ps) / max(len(ps), 1))
        if mejor is None or r[superficies[0]][1] > mejor[1][superficies[0]][1]:
            mejor = (sz, r)
    fuera["signo_z"], fuera["pct"] = mejor
    return fuera
