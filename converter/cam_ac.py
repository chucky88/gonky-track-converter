"""The TV cameras of an ASSETTO CORSA circuit, as `cam_read.Camara`.

    python3 cam_ac.py <AC circuit folder> <layout>

AC stores its cameras in `<layout>/data/cameras*.ini` (several SETS: `cameras.ini`,
`cameras_1.ini`…). Each camera carries `POSITION`, `FORWARD`, `MIN_FOV`/`MAX_FOV` and the
stretch of the lap where it is active, `IN_POINT`–`OUT_POINT`, as a FRACTION of the lap
(0–1).

They are returned in the same shape as the AMS1 ones (`cam_read.Camara`) so that
`generar_camaras` does not need two code paths: the position, the FOV and an ACTIVATION
point, which here is the racing-line point halfway through its stretch.

⚠️ The coordinates are in the space of the exported AIW, which is the MIRRORED one
(`kn5_read._espejo`), the same as the racing line from `ac_trazado.leer_ai` and the grid.
Measured against the AIW of the Charlotte by «13x»: mirrored racing line at a 6.4 m median
(racing line vs. centre), 79 m without mirroring. Looking at a single coordinate it seems
no mirroring is needed, and without it the activation points end up 23-163 m off the
track.

The set with the MOST cameras is used: they are alternative views of the same lap, and
AMS2 wants a single list.
"""

import glob
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cam_read as C  # noqa: E402
import kn5_read as K  # noqa: E402


def _leer_ini(ruta):
    camaras, actual = [], None
    for ln in open(ruta, encoding="utf-8", errors="replace"):
        ln = ln.strip()
        if re.match(r"^\[CAMERA_\d+\]$", ln):
            actual = {}
            camaras.append(actual)
        elif ln.startswith("["):
            actual = None
        elif actual is not None and "=" in ln:
            k, v = (x.strip() for x in ln.split("=", 1))
            actual[k.upper()] = v
    return camaras


def _punto_a_fraccion(trazada, fraccion):
    """The racing-line point at that fraction of the lap, by distance travelled."""
    acum = [0.0]
    for i in range(1, len(trazada)):
        acum.append(acum[-1] + math.dist(trazada[i], trazada[i - 1]))
    objetivo = (fraccion % 1.0) * acum[-1]
    for i, a in enumerate(acum):
        if a >= objetivo:
            return trazada[i]
    return trazada[-1]


def camaras(carpeta, trazado, trazada):
    """[cam_read.Camara] from the most complete set, or [] if the circuit has no cameras."""
    juegos = sorted(glob.glob(os.path.join(carpeta, trazado, "data", "cameras*.ini")))
    # By DISTINCT positions, not by count: `cameras_1.ini` of the Charlotte by «13x»
    # has 9 cameras in 5 spots (pairs covering before and after the car passes). In AMS2 a
    # TrackingCam already follows the car: the pair adds nothing, and it is merged below.
    def sitios(c):
        return len({x.get("POSITION") for x in c})
    juegos = [(sitios(c), len(c), r, c) for r in juegos for c in [_leer_ini(r)] if c]
    if not juegos or not trazada:
        return [], None
    _s, _n, ruta, crudas = max(juegos)
    fuera = []
    for i, c in enumerate(crudas):
        try:
            pos = K._espejo(tuple(float(x) for x in c["POSITION"].split(",")))
            fov = float(c.get("MAX_FOV") or c.get("MIN_FOV") or 40)
            ini, fin = float(c.get("IN_POINT", 0)), float(c.get("OUT_POINT", 0))
        except (KeyError, ValueError):
            continue
        if fin < ini:                       # the stretch crosses the finish line
            fin += 1.0
        medio = (ini + fin) / 2
        largo = (fin - ini) * sum(math.dist(trazada[k], trazada[k - 1])
                                  for k in range(1, len(trazada)))
        fuera.append(C.Camara(nombre=c.get("NAME", f"Camera {i}"), tipo="TrackingCam",
                              pos=pos, fov_h=fov, fov_v=fov * 0.6,
                              activacion=tuple(_punto_a_fraccion(trazada, medio)),
                              radio=max(40.0, min(150.0, largo / 2))))
    # cameras at the same position are merged into one, active halfway through their stretches
    por_sitio = {}
    for c in fuera:
        por_sitio.setdefault(tuple(round(v, 1) for v in c.pos), []).append(c)
    unidas = []
    for grupo in por_sitio.values():
        c = grupo[0]
        if len(grupo) > 1:
            n = len(grupo)
            c.activacion = tuple(sum(g.activacion[k] for g in grupo) / n for k in range(3))
            c.radio = max(g.radio for g in grupo)
        unidas.append(c)
    return unidas, os.path.basename(ruta)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    import ac_trazado as T

    tr = T.leer_ai(os.path.join(argv[1], argv[2], "ai", "fast_lane.ai"))["pos"]
    cams, juego = camaras(argv[1], argv[2], tr)
    print(f"{len(cams)} cameras from {juego}")
    for c in cams:
        print(f"  {c.nombre:12} pos=({c.pos[0]:.0f},{c.pos[1]:.0f},{c.pos[2]:.0f}) "
              f"fov {c.fov_h:.0f}° · activates towards ({c.activacion[0]:.0f},{c.activacion[2]:.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
