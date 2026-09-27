"""What you SEE versus what you DRIVE ON across the whole track: holes, sinking, floating.

    python3 auditar_suelo.py <AC folder> <layout> <physics.obj> <aiw> [output.json]

🔴 Why it exists: at Jarama the car sank into the asphalt. The painted-line area at
2,512-2,534 m was left out of the physics and no gate saw it: they measured against the same
surface table that had left it out. This compares the author's DRAWN ground meshes with the OBJ
that gets cooked (no table), across the width of the track and 12 m beyond on each side, every
4 m of the lap and every 2 m across:

- agujero (hole): ground is visible and there is no physics underneath (the car falls);
- hundido (sunk): the physics is > 15 cm BELOW what you see (the car sinks into the asphalt);
- flota (floats): the physics is > 15 cm ABOVE (the car floats over what you see).
"""
import collections
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ac_trazado as T  # noqa: E402
import aiw_puntuar as AP  # noqa: E402
import kn5_read as K  # noqa: E402

# 🔴 Memory: with 4 m cells and every large TERRAIN triangle registered in thousands of cells,
# RAM went from 3.9 to 17.4 GB and hung the machine (without the OOM killer kicking in). 8 m cells
# (16× fewer entries per large triangle) and the grid stores INDICES, not the triangles.
CEL = 8.0
PASO_M, ANCHO_M, FUERA_M = 4, 2, 12     # every 4 m of lap, every 2 m across, 12 m beyond the edge
# ⚠️ With `^…` (the START of the name) no Charlotte material matched (`las_road…`,
# `low_grassColmap…`, `charlotte_roval_tarmac`): 0 points everywhere and "clean" in seconds — a
# false green. The word is searched ANYWHERE in the name, and if there is no ground, it says so.
SUELO = re.compile(r'(road|gras|sand|kerb|rmbl|rdlt|background|tierra|curb|apron|tarmac|asph|line|terrain|gravel)', re.I)
NO_SUELO = re.compile(r'(groove|skid|wear|blend|logo|glass|window|sign|board|fence|wall|stair|crew)', re.I)


def _rejilla(tris):
    r = collections.defaultdict(list)
    for i, t in enumerate(tris):
        xs = [p[0] for p in t[1:]]
        zs = [p[2] for p in t[1:]]
        for cx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
            for cz in range(int(min(zs) // CEL), int(max(zs) // CEL) + 1):
                r[(cx, cz)].append(i)
    return (tris, r)


def _alturas(r, x, z):
    out = []
    tris, celdas = r
    for i in celdas.get((int(x // CEL), int(z // CEL)), ()):
        et, (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tris[i]
        d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
        if abs(d) < 1e-9:
            continue
        w1 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d
        w2 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d
        if min(w1, w2, 1 - w1 - w2) < -1e-6:
            continue
        out.append((w1 * ay + w2 * by + (1 - w1 - w2) * cy, et))
    return out


def fisica_obj(obj):
    """Ground triangles of the cooked OBJ (no walls), in game coordinates (Z negated)."""
    vs, fis, g = [], [], None
    for ln in open(obj, encoding="utf-8", errors="ignore"):
        if ln.startswith("v "):
            _, x, y, z = ln.split()[:4]
            vs.append((float(x), float(y), -float(z)))
        elif ln.startswith("o "):
            g = ln.split()[1].strip()
        elif ln.startswith("f "):
            i = [int(q.split("/")[0]) - 1 for q in ln.split()[1:]]
            for k in range(1, len(i) - 1):
                fis.append((g, vs[i[0]], vs[i[k]], vs[i[k + 1]]))
    return [t for t in fis if not t[0].startswith("CEMENTWALLS")]


def suelo_visible(carpeta, trazado):
    vis = []
    for f in T.modelos(carpeta, trazado):
        r = K.leer(f, con_geometria=True)
        for m in r["mallas"]:
            if not m.dibuja:
                continue
            mat = r["materiales"][m.material].nombre
            if not SUELO.search(mat) or NO_SUELO.search(mat):
                continue
            for a, b, c in m.caras:
                vis.append((mat, m.pos[a], m.pos[b], m.pos[c]))
    return vis


def auditar(carpeta, trazado, obj, aiw):
    vis = suelo_visible(carpeta, trazado)
    if not vis:
        raise SystemExit("🔴 no GROUND material recognised: the audit can't measure anything")
    print(f"visible ground: {len(vis)} triangles from {len({t[0] for t in vis})} materials", flush=True)
    RF, RV = _rejilla(fisica_obj(obj)), _rejilla(vis)
    texto = open(aiw, encoding="latin-1").read()
    wps = []
    for a, b in AP._bloques(texto):
        bl = texto[a:b]
        if int(AP._campo(bl, "wp_branchID")[0]) != 0:
            continue
        wps.append((AP._campo(bl, "wp_pos"), AP._campo(bl, "wp_perp"), AP._campo(bl, "wp_width"),
                    AP._campo(bl, "wp_score")[1]))
    res = collections.defaultdict(list)
    for i in range(len(wps)):
        p, pe, w, d = wps[i]
        q = wps[(i + 1) % len(wps)][0]
        seg = math.dist((p[0], p[2]), (q[0], q[2]))
        pasos = max(1, int(seg / PASO_M))
        for s in range(pasos):
            f = s / pasos
            x0, y0, z0 = (p[j] + (q[j] - p[j]) * f for j in range(3))
            dist = d + seg * f
            for lat in range(-int(w[0]) - FUERA_M, int(w[1]) + FUERA_M + 1, ANCHO_M):
                x, z = x0 + pe[0] * lat, z0 + pe[2] * lat
                hv = [h for h in _alturas(RV, x, z) if abs(h[0] - y0) < 6]
                if not hv:
                    continue
                top = max(hv)
                hf = [h for h in _alturas(RF, x, z) if abs(h[0] - top[0]) < 3]
                en_pista = -w[0] <= lat <= w[1]
                if not hf:
                    res["agujero"].append((dist, lat, top[1], en_pista, 0.0, x, z))
                    continue
                dy = min(hf, key=lambda h: abs(h[0] - top[0]))[0] - top[0]
                if dy < -0.15:
                    res["hundido"].append((dist, lat, top[1], en_pista, dy, x, z))
                elif dy > 0.15:
                    res["flota"].append((dist, lat, top[1], en_pista, dy, x, z))
    return res


def zonas(lista):
    out = []
    for e in sorted(lista):
        if out and e[0] - out[-1]["fin"] <= 4:
            z = out[-1]
            z["fin"] = e[0]; z["n"] += 1; z["lat"].add(e[1]); z["mat"][e[2]] += 1
            z["pista"] |= e[3]; z["dy"] = max(z["dy"], abs(e[4]))
        else:
            out.append({"ini": e[0], "fin": e[0], "n": 1, "lat": {e[1]}, "mat": collections.Counter({e[2]: 1}),
                        "pista": e[3], "dy": abs(e[4]), "x": e[5], "z": e[6]})
    return out


def main(argv):
    carpeta, trazado, obj, aiw = argv[1:5]
    res = auditar(carpeta, trazado, obj, aiw)
    informe = {}
    for tipo in ("agujero", "hundido", "flota"):
        zs = zonas(res[tipo])
        informe[tipo] = zs
        enp = [z for z in zs if z["pista"]]
        print(f"\n== {tipo}: {len(res[tipo])} points in {len(zs)} zones ({len(enp)} touch the TRACK)")
        for z in sorted(zs, key=lambda z: (-z["pista"], -z["n"]))[:14]:
            print(f"   {z['ini']:6.0f}-{z['fin']:6.0f} m · {z['n']:4d} points · lateral {min(z['lat']):+d}…{max(z['lat']):+d} m"
                  f" · {'TRACK' if z['pista'] else 'off'} · {dict(z['mat'].most_common(3))}"
                  + (f" · up to {100 * z['dy']:.0f} cm" if z["dy"] else "") + f" · ({z['x']:.0f}, {z['z']:.0f})")
    if len(argv) > 5:
        json.dump({k: [{**z, "lat": sorted(z["lat"]), "mat": dict(z["mat"])} for z in v] for k, v in informe.items()},
                  open(argv[5], "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
