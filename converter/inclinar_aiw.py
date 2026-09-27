"""Puts the BANKING back into the exported AIW: `wp_perp` tilted with the surface.

    python3 inclinar_aiw.py <track.aiw> <physics.obj> [--escribir]

🔴🔴 Why it exists: at Mountain Peak the AI braked from 250 to 140 km/h in the oval's turns.
OMTT's AIW exporter writes `wp_perp` HORIZONTAL. Charlotte's original AMS1 AIW has it tilted
with the track —**a median of +24.0° in the turns and +5.0° on the straights**, which are exactly
the real banking angles— and the exported one came out with **0.0° all the way round**. Texas's
(an official Reiza oval) is tilted too. The AI believed it was on a FLAT oval and braked as it
would in an unbanked corner of that radius.

How it is computed: for each waypoint the COLLISION (the same `.obj` that gets cooked) is queried
for the ground height at ±`D` m along the horizontal perpendicular, and the angle comes from the
difference. The vector is tilted without changing its direction in plan view.

Validated against an independent source before being used: at Charlotte, what is computed from the
collision has to reproduce the ORIGINAL AMS1 AIW (and in AC, the `camber` of its `fast_lane.ai`).
See the `peralte en el AIW` (banking in the AIW) gates of both pipelines.

⚠️ The physics OBJ has its Z NEGATED relative to the AIW (`test_gcl_vs_fisica`): this is undone
when reading it.
"""

import math
import re
import sys
from collections import defaultdict

D = 3.0          # metres on each side of the waypoint where the height is measured
CELDA = 8.0


class Suelo:
    def __init__(self, obj_path):
        vs, self.rej = [], defaultdict(list)
        for ln in open(obj_path, encoding="utf-8", errors="ignore"):
            if ln.startswith("v "):
                _, x, y, z = ln.split()[:4]
                vs.append((float(x), float(y), -float(z)))       # into AIW space
            elif ln.startswith("f "):
                idx = [int(q.split("/")[0]) - 1 for q in ln.split()[1:]]
                for k in range(1, len(idx) - 1):
                    t = (vs[idx[0]], vs[idx[k]], vs[idx[k + 1]])
                    xs = [p[0] for p in t]
                    zs = [p[2] for p in t]
                    for cx in range(int(min(xs) // CELDA), int(max(xs) // CELDA) + 1):
                        for cz in range(int(min(zs) // CELDA), int(max(zs) // CELDA) + 1):
                            self.rej[(cx, cz)].append(t)

    def altura(self, x, z, y_ref):
        mejor = None
        for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in self.rej.get(
                (int(x // CELDA), int(z // CELDA)), ()):
            d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(d) < 1e-9:
                continue
            w1 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d
            w2 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d
            w3 = 1 - w1 - w2
            if min(w1, w2, w3) < -1e-6:
                continue
            y = w1 * ay + w2 * by + w3 * cy
            if mejor is None or abs(y - y_ref) < abs(mejor - y_ref):
                mejor = y
        return mejor


_NUM = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_POS = re.compile(r"(wp_pos=\()(" + _NUM + r"),(" + _NUM + r"),(" + _NUM + r")(\))")
_PERP = re.compile(r"(wp_perp=\()(" + _NUM + r"),(" + _NUM + r"),(" + _NUM + r")(\))")


_PATH = re.compile(r"wp_path=\((" + _NUM + r")")


def inclinar(texto: str, suelo: Suelo):
    """Returns (new text, [angle per waypoint], how many had no ground).

    It is measured on the RACING LINE (`pos + perp·wp_path[0]`), not on the centre line: that is
    the banking where the AI drives. Measured at Mountain Peak: the centre line falls on the
    transition to the apron (almost flat) and gave 17.3° in the turns; on the racing line, 21.7°,
    0.8° away from the `camber` in Assetto Corsa's own AI (22.5°). At Charlotte both rules give
    24.0°, the same as its original AIW: the banking of that model is flat across.

    `wp_path` comes AFTER `wp_perp` in each waypoint, so it works block by block.
    """
    angulos, sin = [], 0
    # each waypoint STARTS with `wp_pos=` (they are separated by a `\\\\0`, `\\\\1`… line); there
    # is no `[Waypoint]` header per waypoint — splitting on that only touched ONE waypoint
    partes = re.split(r"(?=wp_pos=)", texto)
    salida = []
    for bloque in partes:
        mp, mq = _POS.search(bloque), _PERP.search(bloque)
        if not (mp and mq):
            salida.append(bloque)
            continue
        x, y, z = float(mp.group(2)), float(mp.group(3)), float(mp.group(4))
        px, pz = float(mq.group(2)), float(mq.group(4))
        h = math.hypot(px, pz)
        if h < 1e-6:
            salida.append(bloque)
            continue
        ux, uz = px / h, pz / h                     # direction in plan view, untouched
        mpath = _PATH.search(bloque)
        lat = float(mpath.group(1)) if mpath else 0.0
        cx, cz = x + ux * lat, z + uz * lat          # the RACING LINE point
        a = suelo.altura(cx + ux * D, cz + uz * D, y)
        b = suelo.altura(cx - ux * D, cz - uz * D, y)
        if a is None or b is None:
            sin += 1
            salida.append(bloque)
            continue
        th = math.atan2(a - b, 2 * D)
        angulos.append(math.degrees(th))
        nuevo = f"wp_perp=({ux * math.cos(th):.6f},{math.sin(th):.6f},{uz * math.cos(th):.6f})"
        salida.append(bloque[:mq.start()] + nuevo + bloque[mq.end():])
    return "".join(salida), angulos, sin


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    texto = open(argv[1], encoding="latin-1").read()
    nuevo, ang, sin = inclinar(texto, Suelo(argv[2]))
    ang_s = sorted(ang)
    print(f"perp tilted on {len(ang)} waypoints ({sin} without ground underneath) · "
          f"median {ang_s[len(ang_s) // 2]:+.1f}° · max {ang_s[-1]:+.1f}°" if ang else "nothing to tilt")
    if "--escribir" in argv:
        open(argv[1], "w", encoding="latin-1").write(nuevo)
        print(f"  -> {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
