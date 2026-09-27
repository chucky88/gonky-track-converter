"""The lap distance (`wp_score`) of the points that are NOT the track: pit lane and grid.

🔴 Symptom: cars the game put on lap 2 without having completed any lap, and positions mixed up.
OMTT's exporter leaves `wp_score` at (0, 0) on the 323 pit lane points and at (2, 0) on the 75
standalone ones (32 grid slots and 43 pit boxes): for the game, a car on the grid or in the pits is
**at the finish line**. At the start, 5 cars showed up one lap ahead of the rest, and the same
happened when going through the pits.

The rule, measured on the (official) **Daytona** AIW: each point that is not on the track inherits
the SECTOR of the point it hangs from (`WP_PTRS[0]`) and its distance is that point's distance PLUS
the metres between them. That way the pit lane keeps adding up from the entry, and goes past the lap
length if it crosses the finish line (Daytona: from 2,853 to 6,152 m on a 3,987 m lap). Track
points (branch 0) are not touched.
"""

import math
import re


def _bloques(texto):
    """[(start, end)] of each waypoint in the text: from one `wp_pos=` to the next."""
    ini = [m.start() for m in re.finditer(r"(?m)^wp_pos=", texto)]
    return list(zip(ini, ini[1:] + [len(texto)]))


def _campo(bloque, nombre):
    m = re.search(rf"(?m)^{nombre}=\(([^)]*)\)", bloque)
    return [float(x) for x in m.group(1).split(",")] if m else None


def puntuar(ruta: str, escribir: bool = True) -> dict:
    texto = open(ruta, encoding="latin-1").read()
    bloques = _bloques(texto)
    wps = []
    for a, b in bloques:
        bl = texto[a:b]
        wps.append({"pos": _campo(bl, "wp_pos"), "score": _campo(bl, "wp_score"),
                    "rama": int(_campo(bl, "wp_branchID")[0]), "prev": int(_campo(bl, "WP_PTRS")[0])})
    hecho = {}

    def score(i, pila=()):
        if i in hecho:
            return hecho[i]
        w = wps[i]
        if w["rama"] == 0 or not (0 <= w["prev"] < len(wps)) or i in pila:
            hecho[i] = (int(w["score"][0]), w["score"][1])
            return hecho[i]
        sp, dp = score(w["prev"], pila + (i,))
        hecho[i] = (sp, dp + math.dist(w["pos"], wps[w["prev"]]["pos"]))
        return hecho[i]

    cambios = 0
    trozos, cursor = [], 0
    for i, (a, b) in enumerate(bloques):
        s, d = score(i)
        bl = texto[a:b]
        if wps[i]["rama"] != 0:
            nuevo = re.sub(r"(?m)^wp_score=\([^)]*\)", f"wp_score=({s},{d:.3f})", bl, count=1)
            cambios += nuevo != bl
            bl = nuevo
        trozos.append(texto[cursor:a])
        trozos.append(bl)
        cursor = b
    trozos.append(texto[cursor:])
    if escribir:
        open(ruta, "w", encoding="latin-1").write("".join(trozos))
    fuera = [hecho[i] for i in range(len(wps)) if wps[i]["rama"] != 0]
    return {"tocados": cambios, "no_pista": len(fuera),
            "a_cero": sum(1 for _s, d in fuera if d <= 0.0),
            "calle": [hecho[i] for i in range(len(wps)) if wps[i]["rama"] == 1]}


def comprobar(ruta: str) -> tuple:
    """No pit/grid point with a zero distance, and the pit lane increasing."""
    r = puntuar(ruta, escribir=False)
    calle = [d for _s, d in r["calle"]]
    # what gets checked is what was WRITTEN: the file is re-read, not the computed values
    texto = open(ruta, encoding="latin-1").read()
    ceros = 0
    for a, b in _bloques(texto):
        bl = texto[a:b]
        if int(_campo(bl, "wp_branchID")[0]) != 0 and _campo(bl, "wp_score")[1] <= 0.0:
            ceros += 1
    return (ceros == 0, f"{r['no_pista']} pit and grid points · {ceros} with the distance at zero"
            + (f" · pit lane from {calle[0]:.0f} to {max(calle):.0f} m" if calle else ""))
