"""The racing line of an Assetto Corsa track, in the shape the conversion pipeline expects.

    python3 ac_trazado.py <AC track folder> --trazado layout_speedway [--fisica phyoval.kn5]

It returns (and with `--json` writes) the same as what `aiw_read` extracts from an AMS1 AIW: centre
line, racing line, pit lane, track edges and walls on each side, grid and pit boxes. That way
`construir_paquete.py` and the gates work without knowing where the track came from.

Where each piece comes from, and why almost everything is DIRECT:

| piece | source in Assetto Corsa |
|---|---|
| racing line, speed, banking | `ai/fast_lane.ai` (block 1: positions; block 2: 18 floats per point) |
| pit lane | `ai/pit_lane.ai` |
| grid / pit boxes | `AC_START_n` / `AC_PIT_n` empties in the layout's `.kn5` |
| **track edges and walls** | **COMPUTED** against the collision mesh — the only thing AC does not ship |

🔴 The edges, measured on Mountain Peak. Finding them by looking at "which surface is underneath"
while walking perpendicular to the track fails in two ways that raise no error:

1. **Walls are vertical.** A wall has no surface seen from above, so it was almost never hit:
   0 of 98 points found a wall on both sides. They are found with a **horizontal ray** against
   their triangles in 3D (Möller–Trumbore).
2. **A gap is an edge too.** On the inside of the oval: `ROAD → APRON` at 2-8 m, then NOTHING at
   13 m, and the infield does not reappear until 42 m. Skipping the gaps, the width came out at
   34.5 m; treating them as an edge, **a median of 21.2 m on 147 of 147 points**.

And the third one, a matter of logic: the collision ground can continue **behind** the wall (on
the outside the wall came out at 4.5 m and the ground at 6.2). The real edge is the nearer of the
two.

No `bpy`: only `struct` and `kn5_read`.
"""

from __future__ import annotations

import json
import math
import os
import re
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kn5_read as K  # noqa: E402

# Surfaces you can drive on. `surfaces.ini` marks them with IS_VALID_TRACK=1,
# and LINES are the ones painted on top of the asphalt.
SUPERFICIE_DE_PISTA = {"ROAD", "APRON", "LINES", "PITS"}
PASO = 0.25            # metres between samples when walking towards the edge
ALCANCE = 60.0         # how far to look for an edge or a wall
CELDA = 6.0
TRAMO_MURO = 2.0       # every how many metres along the path to the edge a wall is looked for


# ── Assetto Corsa's .ai files ─────────────────────────────────────────────────────────
def leer_ai(ruta: str) -> dict:
    """Positions and, if present, the 18 floats per point from block 2."""
    d = open(ruta, "rb").read()
    version, n = struct.unpack_from("<ii", d, 0)
    pos = [K._espejo(struct.unpack_from("<fff", d, 16 + k * 20)) for k in range(n)]   # see kn5_read.ESPEJO_Z
    extra = []
    o = 16 + n * 20
    if o + 4 <= len(d):
        cnt = struct.unpack_from("<i", d, o)[0]
        if cnt == n and o + 4 + cnt * 72 <= len(d):
            extra = [struct.unpack_from("<18f", d, o + 4 + k * 72) for k in range(cnt)]
    return {"version": version, "pos": pos, "extra": extra}


# The surfaces Assetto Corsa ships AS STANDARD (`system/data/surfaces.ini`), which a track uses
# without declaring them. The Charlotte by "13x and someguys" only declares APRON, PIT, OUT and
# CURB, and its meshes are named `1ROAD` (23), `3GRASS` (7), `1KERB` (24): without this table,
# the whole track had no physics. ⚠️ APPROXIMATE values (the game's file cannot be
# redistributed): they only decide valid/not valid and grass yes/no, which is what
# `construir_paquete.fisica_ac` uses. Whatever the track declares takes precedence over this.
SISTEMA_AC = {
    "ROAD": {"valida": True, "boxes": False, "rozamiento": 1.0},
    "KERB": {"valida": True, "boxes": False, "rozamiento": 0.92},
    "GRASS": {"valida": False, "boxes": False, "rozamiento": 0.6},
    "SAND": {"valida": False, "boxes": False, "rozamiento": 0.6},
    # 🔴 The painted LINE areas (`1LINE_000`) are track surface in AC even if the track does not
    # declare them. It was missing here → out of the physics → between 2,512 and 2,534 m at Jarama
    # the racing line had NOTHING underneath: cars sank and rolled over.
    "LINE": {"valida": True, "boxes": False, "rozamiento": 1.0},
}


def superficies(ruta_ini: str) -> dict:
    """KEY -> {valida, boxes, rozamiento}: AC's standard ones + those in `surfaces.ini`."""
    fuera, actual = {}, None
    for linea in open(ruta_ini, encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if linea.startswith("[SURFACE"):
            actual = {}
        elif "=" in linea and actual is not None:
            k, v = linea.split("=", 1)
            actual[k.strip()] = v.strip()
            if k.strip() == "KEY":
                fuera[v.strip()] = actual
    propias = {k.upper(): {"valida": v.get("IS_VALID_TRACK") == "1",
                           "boxes": v.get("IS_PITLANE") == "1",
                           "rozamiento": float(v.get("FRICTION") or 0)} for k, v in fuera.items()}
    return {**SISTEMA_AC, **propias}


PIEZAS_FUERA = {"ac_crew.kn5"}


def modelos(carpeta: str, trazado: str) -> list:
    """The `.kn5` files that make up the track in that layout, as absolute paths.

    If there is a `models_<trazado>.ini`, it rules: it is the list Assetto Corsa loads. The
    Charlotte by "13x" splits the track into 9 files —track, grid, grandstands, walls,
    advertising, Ferris wheel…— and the old rule ("the largest `.kn5`") would have picked the
    grandstands (295 MB) and left out THE TRACK (73 MB). `DYNAMIC_OBJECT`s (planes flying across
    the sky) are not included: they move, and in AMS2 they would be a plane frozen in mid-air.

    Without that file, Mountain Peak's convention: the largest one + `<trazado>.kn5`.
    🔴 A non-zero `POSITION`/`ROTATION` is REFUSED instead of ignored: the piece would end up
    somewhere else without saying anything.
    """
    corto = trazado.replace("layout_", "")
    ini = os.path.join(carpeta, f"models_{corto}.ini")
    if os.path.exists(ini):
        fuera, actual = [], None
        for ln in open(ini, encoding="utf-8", errors="replace"):
            ln = ln.strip()
            if ln.startswith("["):
                actual = ln.startswith("[MODEL_")
            elif actual and "=" in ln:
                k, v = (x.strip() for x in ln.split("=", 1))
                if k == "FILE":
                    fuera.append(os.path.join(carpeta, v))
                elif k in ("POSITION", "ROTATION") and any(float(x) for x in v.split(",")):
                    raise SystemExit(f"{ini}: {k}={v} — placing pieces is not supported")
        # `ac_crew.kn5` is left out: AC's 660 STATIC pit crew figures. AMS2 puts its own ANIMATED
        # crew at every stop (the one with the jacks), and both could be seen.
        return [r for r in dict.fromkeys(fuera)
                if os.path.basename(r).lower() not in PIEZAS_FUERA]
    grande = kn5_principal(carpeta)
    lay = os.path.join(carpeta, corto + ".kn5")
    return [grande] + ([lay] if os.path.exists(lay) else [])


def kn5_principal(carpeta: str) -> str:
    """The largest `.kn5` that is not physics, rubber (groove) or layout (Mountain Peak)."""
    trazados = {d.replace("layout_", "") for d in os.listdir(carpeta) if d.startswith("layout_")}
    cands = [(os.path.getsize(os.path.join(carpeta, f)), f) for f in os.listdir(carpeta)
             if f.lower().endswith(".kn5") and not f.lower().startswith("phy")
             and "groove" not in f.lower() and os.path.splitext(f)[0].lower() not in trazados]
    if not cands:
        raise SystemExit(f"no geometry .kn5 in {carpeta}")
    return os.path.join(carpeta, max(cands)[1])


def superficie_de(nombre_malla: str, claves=None) -> str | None:
    """`01ROAD.005` -> `ROAD`; `1apron_RaceSurface_Oval_01` -> `APRON`.

    🔴 CASE-INSENSITIVE: when leaving the road, the car fell into the void. The rule looked for
    the numeric prefix followed by UPPERCASE letters, and the apron on the main straight is named
    `1apron_…`: it was left out of the collision and that is exactly where the car fell. Assetto
    Corsa is case-insensitive on the key. This is the ONLY copy of the rule:
    `construir_paquete.superficie_ac` calls it, it does not repeat it.

    With `claves` (those from `surfaces.ini`) it returns the longest key the name STARTS with, or
    None if it is none of them — so `3DPANO` (the background panorama) is not physics.
    """
    g = re.match(r"^\d+([A-Za-z]+)", nombre_malla)
    if not g:
        return None
    resto = g.group(1).upper()
    if claves:
        cands = [k for k in claves if resto.startswith(k.upper())]
        return max(cands, key=len).upper() if cands else None
    return resto


# ── the collision, indexed so it can be queried quickly ──────────────────────────────
class Colision:
    """The collision, from a `phy*.kn5` or from the physics meshes of SEVERAL `.kn5` files.

    With `claves` only what is a declared (or standard) surface counts: when the physics lives
    inside the visible geometry, `3DPANO` or `1_LOGO` are not ground.
    """
    def __init__(self, kn5_fisica, claves=None):
        rutas = [kn5_fisica] if isinstance(kn5_fisica, str) else list(kn5_fisica)
        self.suelo = defaultdict(list)
        self.muros = defaultdict(list)
        self.cuenta = defaultdict(int)
        # What you can drive on without going off: what the track declares valid. The fixed list
        # (`SUPERFICIE_DE_PISTA`) does not know `KERB`, `CURB` or `PIT`, and in the Charlotte by
        # "13x" the edge stopped at the first kerb, at 1.5 m, in every corner.
        self.validas = ({k.upper() for k, v in claves.items() if v.get("valida")}
                        if isinstance(claves, dict) else set(SUPERFICIE_DE_PISTA))
        claves = (set(claves) | {"WALL"}) if claves else None
        mallas = [m for ruta in rutas for m in K.leer(ruta, con_geometria=True)["mallas"]]
        for m in mallas:
            sup = superficie_de(m.nombre, claves)
            if not sup:
                continue
            destino = self.muros if sup == "WALL" else self.suelo
            for a, b, c in m.caras:
                self.cuenta[sup] += 1
                _indexar(destino, (sup, m.pos[a], m.pos[b], m.pos[c]))

    def debajo(self, x, z, y_ref):
        """Surface (and its height) closest in height to `y_ref` under (x, z)."""
        mejor = None
        for sup, (ax, ay, az), (bx, by, bz), (cx, cy, cz) in self.suelo.get(
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
            if mejor is None or abs(y - y_ref) < abs(mejor[1] - y_ref):
                mejor = (sup, y)
        return mejor

    def muro(self, origen, direccion, maxd=ALCANCE):
        """Distance to the first wall triangle in that direction (3D ray), or None."""
        # 🔴 Sampling every 3 m and only the cell of each sample, a ray cutting DIAGONALLY across
        # the corner of a cell hit it in no sample, and the inner wall did not exist (Charlotte by
        # "13x": wall 2.49 m from the racing line, "no wall", 7 red points in the `ground off the
        # track` gate). Half-cell step and the 8 neighbours of each sample: no cell the ray touches is
        # left out.
        paso = CELDA / 2
        celdas = set()
        for i in range(int(maxd / paso) + 2):
            k = i * paso
            bx = int((origen[0] + direccion[0] * k) // CELDA)
            bz = int((origen[2] + direccion[2] * k) // CELDA)
            celdas.update((bx + dx, bz + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1))
        mejor = None
        for c in celdas:
            for _s, a, b, cc in self.muros.get(c, ()):
                e1 = [b[i] - a[i] for i in range(3)]
                e2 = [cc[i] - a[i] for i in range(3)]
                p = [direccion[1] * e2[2] - direccion[2] * e2[1],
                     direccion[2] * e2[0] - direccion[0] * e2[2],
                     direccion[0] * e2[1] - direccion[1] * e2[0]]
                det = sum(e1[i] * p[i] for i in range(3))
                if abs(det) < 1e-9:
                    continue
                inv = 1 / det
                tv = [origen[i] - a[i] for i in range(3)]
                u = sum(tv[i] * p[i] for i in range(3)) * inv
                if u < 0 or u > 1:
                    continue
                q = [tv[1] * e1[2] - tv[2] * e1[1], tv[2] * e1[0] - tv[0] * e1[2],
                     tv[0] * e1[1] - tv[1] * e1[0]]
                v = sum(direccion[i] * q[i] for i in range(3)) * inv
                if v < 0 or u + v > 1:
                    continue
                t = sum(e2[i] * q[i] for i in range(3)) * inv
                if 0 < t < maxd and (mejor is None or t < mejor):
                    mejor = t
        return mejor


def _indexar(rejilla, t):
    """Puts triangle `t = (sup, a, b, c)` into every cell its bounding box touches."""
    xs = (t[1][0], t[2][0], t[3][0])
    zs = (t[1][2], t[2][2], t[3][2])
    for cx in range(int(min(xs) // CELDA), int(max(xs) // CELDA) + 1):
        for cz in range(int(min(zs) // CELDA), int(max(zs) // CELDA) + 1):
            rejilla[(cx, cz)].append(t)


NO_ES_CARRERA = {"APRON", "PIT", "PITS"}
TOPE_ANCHO_CENTRAL = 1.3   # each side, at most 1.3× its usual width (AI centre line)


def bordes_carrera(col: Colision, trazada: list, indices=None) -> dict:
    """{k: (izq, der)}: the width of the RACING asphalt (no apron, no pits) on each side.

    🔴 For the AI's CENTRE LINE, not for the limits (symptom: the AI braked suddenly in a corner).
    With the apron counted as track, in turns 3-4 of the Charlotte the inner edge jumped from 13.5
    to 37 m (the apron widens towards the pit entry), the centre line moved 12 m towards it and
    the smoothing turned the jump into a ramp with two 7° KINKS in the middle of the banking (at
    1,729 and 1,816 m). The limits (`bordes`) still count the apron."""
    carrera = set(getattr(col, "validas", SUPERFICIE_DE_PISTA)) - NO_ES_CARRERA
    n = len(trazada)
    fuera = {}
    for k in (indices if indices is not None else range(n)):
        p, q = trazada[k], trazada[(k + 1) % n]
        fx, fz = q[0] - p[0], q[2] - p[2]
        L = math.hypot(fx, fz) or 1.0
        fx, fz = fx / L, fz / L
        fila = []
        for px, pz in ((-fz, fx), (fz, -fx)):
            y, s, borde = p[1], PASO, ALCANCE
            while s < ALCANCE:
                h = col.debajo(p[0] + px * s, p[2] + pz * s, y)
                if h is None or h[0] not in carrera:
                    borde = s
                    break
                y = h[1]
                s += PASO
            fila.append(borde)
        fuera[k] = tuple(fila)
    return fuera


POLE_ANTES_DE_META_M = 20.0
VENTANA_CENTRO_M = 40.0     # the centre of the grid's asphalt: median of the edges within ±40 m


def parrilla_en_meta(t: dict, pole_m: float = POLE_ANTES_DE_META_M) -> list:
    """The author's grid, MOVED to the main straight: same formation, pole `pole_m` metres
    before the line.

    🔴 Symptom: the race leader showed up 6th in the standings. The Charlotte by "13x" has the grid
    on the BACK straight, ~1,000 m from the finish line (an Assetto Corsa trick, since it has no
    rolling start). AMS2 does not count a car's lap until it crosses the line: measured in a race,
    throughout the whole first lap **18 of 23 cars** had a distance of 0 and the order came out
    mixed up; from the first pass over the line on, 0 out of order.

    The formation is kept: each slot keeps its distance to the pole along the racing line and its
    lateral offset relative to the CENTRE OF THE ASPHALT (not to the racing line, which on the main
    straight runs somewhere else). The author's racing line starts at the finish line (`tr[0]`)."""
    tr, col = t["trazada"], t["colision"]
    n = len(tr)
    acum = [0.0]
    for a, b in zip(tr, tr[1:]):
        acum.append(acum[-1] + math.dist((a[0], a[2]), (b[0], b[2])))
    vuelta = acum[-1] + math.dist((tr[-1][0], tr[-1][2]), (tr[0][0], tr[0][2]))

    def tangente(k):
        a, b = tr[k], tr[(k + 1) % n]
        dx, dz = b[0] - a[0], b[2] - a[2]
        L = math.hypot(dx, dz) or 1.0
        return dx / L, dz / L

    # 🔴 The centre of the asphalt is not measured at ONE point. Measured that way on the
    # Charlotte, where the asphalt widens towards the pit junction (the inner edge jumps from 9 to
    # 21-36 m at 2,155 and 2,234 m), the "centre" moved 6-14 m inwards and slots 10, 11, 20-23, 30
    # and 31 fell outside the racing surface — slot 11, 11.4 m to the left of the racing line, on
    # the junction. Median of the edges within ±VENTANA_CENTRO_M.
    todos = bordes_carrera(col, tr)

    def centro_asfalto(k):
        cerca = [j for j in range(n) if abs((acum[j] - acum[k] + vuelta / 2) % vuelta - vuelta / 2) <= VENTANA_CENTRO_M]
        bi = sorted(todos[j][0] for j in cerca)[len(cerca) // 2]
        bd = sorted(todos[j][1] for j in cerca)[len(cerca) // 2]
        dx, dz = tangente(k)
        ix, iz = -dz, dx
        off = (bi - bd) / 2.0
        return (tr[k][0] + ix * off, tr[k][1], tr[k][2] + iz * off), (ix, iz)

    def k_en(s):
        s %= vuelta
        return min(range(n), key=lambda k: abs(acum[k] - s))

    fuera = []
    puestos = t["marcas"]["parrilla"]
    if not puestos:
        return puestos
    ks = [min(range(n), key=lambda k: (tr[k][0] - p[0]) ** 2 + (tr[k][2] - p[2]) ** 2) for p, _m in puestos]
    s_pole = acum[ks[0]]
    for (p, m), k in zip(puestos, ks):
        c, (ix, iz) = centro_asfalto(k)
        lateral = (p[0] - c[0]) * ix + (p[2] - c[2]) * iz
        atras = (s_pole - acum[k]) % vuelta           # metres behind the pole
        k2 = k_en(vuelta - pole_m - atras)
        c2, (ix2, iz2) = centro_asfalto(k2)
        x, z = c2[0] + ix2 * lateral, c2[2] + iz2 * lateral
        h = col.debajo(x, z, c2[1])
        fuera.append(((x, h[1] if h else c2[1], z), m))
    return fuera


def bordes(col: Colision, trazada: list) -> list:
    """For each point: (borde_izq, borde_der, muro_izq, muro_der) in metres from the racing line.

    `muro_*` is None where there is no wall (an oval's infield). `borde_*` is never None: at most
    it is ALCANCE.
    """
    n = len(trazada)
    fuera = []
    for k in range(n):
        p, q = trazada[k], trazada[(k + 1) % n]
        fx, fz = q[0] - p[0], q[2] - p[2]
        L = math.hypot(fx, fz) or 1.0
        fx, fz = fx / L, fz / L
        fila = []
        for px, pz in ((-fz, fx), (fz, -fx)):           # left, right
            borde, y = ALCANCE, p[1]
            s = PASO
            candidatos = []
            while s < ALCANCE:
                h = col.debajo(p[0] + px * s, p[2] + pz * s, y)
                if h is None or h[0] not in getattr(col, "validas", SUPERFICIE_DE_PISTA):
                    borde = s                            # the gap is ALSO an edge
                    break
                y = h[1]
                # 🔴 Short ray every `TRAMO_MURO`, at the ground height THERE: it follows the
                # banking. In the Charlotte by "13x" the physical asphalt continues UNDER the wall
                # (wall at 8.3 m, ground up to 9.75 m), and the ray from "the edge − 1 m" started
                # behind the wall: no wall in any corner.
                if not candidatos and abs(s / TRAMO_MURO - round(s / TRAMO_MURO)) < 1e-6:
                    mc = col.muro((p[0] + px * s, y + 0.6, p[2] + pz * s), (px, 0.0, pz),
                                  maxd=TRAMO_MURO + 0.5)
                    if mc is not None:
                        candidatos.append(s + mc)
                s += PASO
            # ⚠️ THE BANKING. A single horizontal ray from the racing line passed UNDER the outer
            # wall: at 24° the asphalt rises 4.5 m over 10 m, and the wall is up there. Measured:
            # the outer wall was found on only 80 % of the lap of an oval that has it all the way
            # round. An extra ray is cast from the EDGE, at the ground height there (`y` is the
            # last track height that was hit).
            m1 = col.muro((p[0], p[1] + 0.6, p[2]), (px, 0.0, pz))
            if m1 is not None:
                candidatos.append(m1)
            atras = max(borde - 1.0, 0.0)
            m2 = col.muro((p[0] + px * atras, y + 0.6, p[2] + pz * atras), (px, 0.0, pz),
                          maxd=ALCANCE - atras)
            if m2 is not None:
                candidatos.append(atras + m2)
            muro = min(candidatos) if candidatos else None
            if muro is not None:
                borde = min(borde, muro)                 # the ground can continue behind the wall
            fila.append((borde, muro))
        fuera.append((fila[0][0], fila[1][0], fila[0][1], fila[1][1]))
    return fuera


def vacios(kn5_trazado) -> dict:
    """Grid, pit boxes and timing gates declared as `AC_*` empties.

    Accepts one or several `.kn5` files: in the Charlotte by "13x" they are in
    `grid_pit_oval.kn5`, which is not named after the layout.
    """
    rutas = [kn5_trazado] if isinstance(kn5_trazado, str) else list(kn5_trazado)
    r = {"vacios": [v for ruta in rutas for v in K.leer(ruta)["vacios"]]}
    def lista(prefijo):
        filas = [(int(re.search(r"_(\d+)", n).group(1)), pos, m16)
                 for n, pos, m16 in r["vacios"]
                 if re.match(rf"^{prefijo}_\d+$", n)]
        return [(pos, m16) for _i, pos, m16 in sorted(filas)]
    tiempos = {n: pos for n, pos, _m in r["vacios"] if n.startswith("AC_TIME_")}
    return {"parrilla": lista("AC_START"), "boxes": lista("AC_PIT"), "tiempos": tiempos}


def construir(carpeta: str, trazado: str, fisica: str | None = None) -> dict:
    base = os.path.join(carpeta, trazado)
    fast = leer_ai(os.path.join(base, "ai", "fast_lane.ai"))
    pit_ruta = os.path.join(base, "ai", "pit_lane.ai")
    pit = leer_ai(pit_ruta) if os.path.exists(pit_ruta) else {"pos": []}

    piezas = modelos(carpeta, trazado)
    sup_ini = os.path.join(base, "data", "surfaces.ini")
    claves = superficies(sup_ini) if os.path.exists(sup_ini) else dict(SISTEMA_AC)

    # the physics: the one requested, or the layout's if there is one (`phyoval.kn5`, `phyrc.kn5`…)
    if not fisica:
        cands = sorted(f for f in os.listdir(carpeta) if f.lower().startswith("phy")
                       and f.lower().endswith(".kn5"))
        fisica = cands[0] if cands else None
    if fisica:
        col = Colision(os.path.join(carpeta, fisica), claves)
    else:
        # no `phy*.kn5`: the physics lives INSIDE the visible geometry (`1ROAD`, `3GRASS`…),
        # spread across the layout's pieces. `fisica = None` tells the scene that those meshes
        # ARE the track (limits included), not just filler collision.
        col = Colision(piezas, claves)

    kn5_layout = os.path.join(carpeta, trazado.replace("layout_", "") + ".kn5")
    fuentes_marcas = list(dict.fromkeys(piezas + ([kn5_layout] if os.path.exists(kn5_layout) else [])))
    marcas = vacios(fuentes_marcas)

    b = bordes(col, fast["pos"])
    boxes_linea, corte = (recortar_boxes(pit["pos"], fast["pos"], col) if pit["pos"]
                          else (pit["pos"], None))
    return {"trazada": fast["pos"], "extra": fast["extra"], "boxes_linea": boxes_linea,
            "boxes_corte": corte, "boxes_original": len(pit["pos"]),
            "colision": col,
            "bordes": b, "marcas": marcas, "fisica": fisica, "piezas": piezas,
            "superficies_colision": dict(col.cuenta)}


def recortar_boxes(pit: list, fast: list, col: "Colision", margen_m: float = 15.0,
                   paso_m: float = 4.5):
    """The stretch of `pit_lane.ai` that is the PIT LANE, not the whole lap.

    🔴 Symptom: the AI entered the pits and stopped, or teleported to its box. AC's `pit_lane.ai`
    records the COMPLETE lap including the pit pass: the Charlotte by "13x" has 1,431 points and
    2,186 m, Mountain Peak 1,084 and 1,677 m. Copied as is, AMS2's pit path left the track at
    point 261 and came back at 250: **a whole lap "in the pits"**. Mid-Ohio: 154 points.

    The cut is decided by the SURFACE underneath, not by a distance: both tracks give the same
    structure — track → apron → pits → apron → track — and the pit lane runs from the first point
    that leaves the racing line's surface to the last one before returning to it. A fixed distance
    does not work: the exit apron is 9-10 m from the racing line, the same as the track's low line.

    Returns (points, (start, end)). With no clear cut, the original path and None.
    """
    import collections

    def sup(p):
        h = col.debajo(p[0], p[2], p[1])
        return h[0] if h else "--"

    cuenta = collections.Counter(sup(p) for p in fast[::3])
    total = sum(cuenta.values()) or 1
    principal = {k for k, v in cuenta.items() if v >= 0.05 * total}
    fuera = [sup(p) not in principal for p in pit]
    if not any(fuera) or all(fuera):
        return pit, None
    primero = fuera.index(True)
    ultimo_fuera = len(fuera) - 1 - fuera[::-1].index(True)
    # margin: `margen_m` over the track on each side, so it connects with the racing line
    acum = [0.0]
    for i in range(1, len(pit)):
        acum.append(acum[-1] + math.dist(pit[i], pit[i - 1]))
    ini = primero
    while ini > 0 and acum[primero] - acum[ini - 1] <= margen_m:
        ini -= 1
    fin = ultimo_fuera
    while fin < len(pit) - 1 and acum[fin + 1] - acum[ultimo_fuera] <= margen_m:
        fin += 1
    tramo = pit[ini:fin + 1]
    # resample to ~`paso_m` (AC records every 1.5 m)
    fuera_pts, ultimo = [tramo[0]], 0.0
    ac = [0.0]
    for i in range(1, len(tramo)):
        ac.append(ac[-1] + math.dist(tramo[i], tramo[i - 1]))
    for i in range(1, len(tramo) - 1):
        if ac[i] - ultimo >= paso_m:
            fuera_pts.append(tramo[i])
            ultimo = ac[i]
    fuera_pts.append(tramo[-1])
    return fuera_pts, (ini, fin)


def resumen(r: dict) -> str:
    b = r["bordes"]
    ancho = sorted(x[0] + x[1] for x in b)
    muro_i = sum(1 for x in b if x[2] is not None)
    muro_d = sum(1 for x in b if x[3] is not None)
    n = len(b)
    return (f"racing line {n} points · pit lane {len(r['boxes_linea'])} · "
            f"grid {len(r['marcas']['parrilla'])} · pit boxes {len(r['marcas']['boxes'])} · "
            f"timing {len(r['marcas']['tiempos'])}\n"
            f"  track width: median {ancho[n // 2]:.1f} m · p5 {ancho[n // 20]:.1f} · "
            f"p95 {ancho[19 * n // 20]:.1f}\n"
            f"  wall found: left {muro_i}/{n} · right {muro_d}/{n}")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    carpeta = argv[1]
    trazado = argv[argv.index("--trazado") + 1] if "--trazado" in argv else "layout_speedway"
    fisica = argv[argv.index("--fisica") + 1] if "--fisica" in argv else None
    r = construir(carpeta, trazado, fisica)
    print(resumen(r))
    if "--json" in argv:
        destino = argv[argv.index("--json") + 1]
        with open(destino, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in r.items() if k != "extra"}, fh)
        print(f"  -> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
