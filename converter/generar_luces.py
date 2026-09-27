"""Generates `<track>_lights.sgx` from the circuit's own LIGHT TOWERS.

    python3 generar_luces.py <pack folder> --nombre <circuit id>

🔴 Why it exists: without it, `<track>_lights.sgx` is **byte for byte Meadowdale's** (the
template's): 21 spotlights at `Y≈0.25 m` (at ground level) scattered around the infield,
pointing at where something used to be on ANOTHER circuit.

🔴 Emptying it (`NumObjects="0"`) is worse: **it crashes AMS2**. Measured: Mid-Ohio ships 2
lights, GJ Kartway 6, the template 21; none of them ships zero.

The right way out is neither copying nor emptying: it is **reading the towers the circuit
already has**. Charlotte carries `LIGHTS01..12` in its AMS1 MAS —the oval's floodlight banks,
between 12 and 51 m high— and they are in the exported scene with their centre and radius.
One spotlight per tower, pointing at the ground.

⚠️ What this does NOT fix: **in daytime you notice nothing.** These lights are for night and
dusk. If the circuit looks flat at midday, the cause lies in the materials
(`globalSpecularFactor`, `specularPower`), not here.

⚠️ And the calibration is a starting value, not a measurement: the intensity and range of a
stadium floodlight cannot be checked without opening the game. The available references are
not consistent with each other (Meadowdale 4000/30 m at ground level, GJ Kartway 1500/8 m at
4 m), so it is scaled by the square of the range from Meadowdale's and **checked on track**.
"""

import math
import os
import re
import sys

# Copied from the template, not invented: it is the LIGHT form that the engine does read.
# 🔴🔴 EXCEPT THE CONE: the template carried `InnerAngle="-1.0" OuterAngle="180.0"` and with it NOT
# ONE generated light switched on (neither Meadowdale's 21, nor 9 tower ones, nor 255 of the
# author's). With 120/150 —Daytona's, decoded from its `_lights.sgb64`— the track lights up.
PLANTILLA = (
    '    <OBJ_ID no="{no}">\n'
    '      <LIGHT UID="0" Name="{nombre}" Type="SPOTLIGHT" Position="{x:.6f} {y:.6f} {z:.6f}"'
    ' Direction="0.000000 -1.000000 0.000000" Colour="1.0 0.98 0.92" Intensity="{intensidad:.1f}"'
    ' Range="{rango:.1f}" InnerAngle="120.0" OuterAngle="150.0" CastsShadows="FALSE"'
    ' NoSpecular="FALSE" NoSmoothDistAtten="TRUE" IncludeInLightMaps="FALSE"'
    ' LightIntensityTweakable="TRUE" LightGroup="3" GroundPlaneDistance="5.000000"'
    ' GroundPlaneNormal="0.0 1.0 0.0" GroundPlaneAutoSet="TRUE" GroundPlaneShow="TRUE" />\n'
    '    </OBJ_ID>\n'
)

CABECERA = ('<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
            '<SCENE FileVersion="0.1.0.0" ExporterVersion="Open Madness Track Tools 0.1.0"'
            ' NumObjects="{n}" Merged="1" NumPartitions="1">\n')

# 🔴 And the closing part: without it AMS2 crashes on load. The header declares
# `NumPartitions="1"`: if the body does not carry the partition, the engine goes looking for
# one that is not there. Mid-Ohio closes it this way, with the bounding box and the list of
# children. Same shape as the empty-file bug: **a header that promises what the body does not
# have**. A gate that only counts lights does not see it: 12 lights without a partition are
# still 12 lights.
PARTICION = ('  <PARTITION_ID no="0">\n'
             '    <AABBOX min="{x0:.6f} {y0:.6f} {z0:.6f}" max="{x1:.6f} {y1:.6f} {z1:.6f}" />\n'
             '    <CHILD_PARTITIONS IDs="NONE" />\n'
             '    <CHILD_OBJS IDs="{hijos}" />\n'
             '  </PARTITION_ID>\n')

# Meshes that are floodlight banks. `NIGHTLIGHT..GLOW` are the glow cards —the halo that is
# drawn, not the light— and their radii reach 240 m: they are no good as a position.
# And the Assetto Corsa ones: `FloodsINNER_01`, `FloodsOUTER_03`… split into
# `_SUB0/1/2` submeshes. They are grouped by the base name so that ONE light per tower comes
# out and not one per piece. Measured in Mountain Peak: 6 towers, 3 outer ones at 27-32 m and
# 3 ground-level spotlights in the infield.
TORRES = re.compile(r"^(LIGHTS\d+|PITLIGHT(?:IN|OUT)|Floods[A-Za-z]*_\d+)(?:_SUB\d+)?$", re.I)

# Meadowdale's scale: 4000 lm for 30 m -> 4.44 lm/m². The ratio is kept.
LUZ_POR_M2 = 4000.0 / (30.0 ** 2)
# Daytona (official, extracted from the game): ~76 lights, intensity ~15,000, range
# 100-175 m. The spotlights over the track are spaced out so as not to stack 150 m ranges.
INTENSIDAD_FOCO = 15000.0
ALCANCE_FOCO = 150.0
ESPACIADO_FOCOS = 50.0
MARGEN = 45.0      # metres of range below the foot of the tower


def torres_de(sgx_escena: str):
    """Centre of each floodlight bank, exactly as OMTT exported it."""
    texto = open(sgx_escena, encoding="utf-8", errors="replace").read()
    fuera = []
    por_torre = {}
    for m in re.finditer(
            r'Name="([^"]+)"[^>]*>\s*<RESOURCE[^>]*/>\s*<SPHERE Centre="([^"]+)"', texto):
        g = TORRES.match(m.group(1))
        if g:
            x, y, z = (float(v) for v in m.group(2).split()[:3])
            base = g.group(1)
            # of a tower's submeshes, the HIGHEST: it is the head with the spotlights
            if base not in por_torre or y > por_torre[base][2]:
                por_torre[base] = (base, x, y, z)
    fuera.extend(por_torre.values())
    return sorted(fuera)


def escribir(salida: str, nombre: str) -> dict:
    escena = os.path.join(salida, "Tracks", nombre, f"{nombre}.sgx")
    destino = os.path.join(salida, "Tracks", nombre, f"{nombre}_lights.sgx")
    if not os.path.exists(escena):
        return {"luces": 0, "motivo": "no exported scene"}

    torres = torres_de(escena)
    if not torres:
        # With no towers NOTHING is touched: the inherited file stays. An empty file crashes,
        # and inventing spotlights where the circuit has none is worse data than keeping the borrowed one.
        return {"luces": 0, "motivo": "the track has no light-tower meshes"}

    partes, cajas = [], []
    for i, (nom, x, y, z) in enumerate(torres, start=1):
        rango = max(20.0, y + MARGEN)
        partes.append(PLANTILLA.format(no=i, nombre=nom, x=x, y=y, z=z,
                                       intensidad=LUZ_POR_M2 * rango * rango, rango=rango))
        # Mid-Ohio's box is that of the positions WIDENED by the spotlight's range: its lights
        # are at x 74.69-74.98 with Range 30 and the box goes from 44.69 to 104.98.
        cajas.append((x - rango, y - rango, z - rango, x + rango, y + rango, z + rango))

    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(CABECERA.format(n=len(partes)))
        fh.writelines(partes)
        fh.write(PARTICION.format(
            x0=min(c[0] for c in cajas), y0=min(c[1] for c in cajas), z0=min(c[2] for c in cajas),
            x1=max(c[3] for c in cajas), y1=max(c[4] for c in cajas), z1=max(c[5] for c in cajas),
            hijos=" ".join(str(i) for i in range(1, len(partes) + 1))))
        fh.write("</SCENE>\n")
    return {"luces": len(torres), "alturas": (min(t[2] for t in torres),
                                              max(t[2] for t in torres)),
            "nombres": [t[0] for t in torres]}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    salida = argv[1].rstrip("/")
    nombre = argv[argv.index("--nombre") + 1] if "--nombre" in argv else "charlotte"
    r = escribir(salida, nombre)
    if not r["luces"]:
        print(f"lights: the inherited file stays — {r['motivo']}")
        return 1
    print(f"lights: {r['luces']} floodlights from the track's own towers "
          f"({', '.join(r['nombres'][:4])}…), at {r['alturas'][0]:.0f}-{r['alturas'][1]:.0f} m")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


# ── the lights that the AUTHOR of an Assetto Corsa circuit defined for the night ───────────
def series_ac(carpeta: str, trazado: str):
    """The `[LIGHT_SERIES_…]` entries of `extension/ext_config.ini` (Custom Shaders Patch), as spotlights.

    Measured example (Charlotte by «13x»): the author declares 8 series («~183 lights»):
    spotlights 30 m above the track (`MESHES = vis_rd?`, `OFFSET 0,30,0`, downwards, 180°,
    range 60), over the pits, the Ferris wheel, the buildings, the grandstand glows and the
    panels. CSP places one light per GROUP of vertices closer than `CLUSTER_THRESHOLD` (25 m
    here): one light per mesh would give 24 and one per vertex 48,880; grouping gives 255, the
    same order as the 183 declared.
    Coordinates: those of the `.kn5` with `kn5_read`'s mirroring, which are those of the
    exported scene (measured: centre of `1grass_red` 152.0 / −0.5 / −237.4 in both).
    """
    import fnmatch
    import math

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ac_trazado as T
    import kn5_read as K

    ini = os.path.join(carpeta, "extension", "ext_config.ini")
    if not os.path.exists(ini):
        return []
    texto = open(ini, encoding="utf-8", errors="replace").read()
    series = []
    for b in re.split(r"^\[", texto, flags=re.M):
        if not b.startswith("LIGHT_SERIES"):
            continue
        s = dict(re.findall(r"^(\w+)\s*=\s*(.*?)\s*$", b, re.M))
        # 🔴 A REPEATED key: the dict keeps the last one. In the Charlotte by «13x» the
        # grandstand series («high light casters», 71 spotlights) says `DIRECTION=0,-1,0` and
        # further down `DIRECTION=0,1,0` (a template leftover): they came out pointing UP with
        # a 150° cone and lit the sky, not the stand (the stands were left dark). With
        # different directions the FIRST one wins, which is the one the author wrote on
        # purpose; a warning is issued.
        dirs = re.findall(r"^DIRECTION\s*=\s*(.*?)\s*$", b, re.M)
        if len(set(dirs)) > 1:
            s["DIRECTION"] = dirs[0]
            s["_aviso"] = f"repeated DIRECTION {dirs}: the first one is used"
        series.append(s)
    series = [s for s in series if s.get("ACTIVE", "1") != "0"]
    if not series:
        return []
    mallas = []
    for p in T.modelos(carpeta, trazado):
        r = K.leer(p, con_geometria=True)
        mallas += [(m, r["materiales"][m.material].nombre) for m in r["mallas"]]

    def casa(patron, nombre):
        return any(fnmatch.fnmatch(nombre.lower(), x.strip().lower().replace("?", "*"))
                   for x in patron.split(",") if x.strip())

    def trio(v, defecto):
        try:
            return tuple(float(x) for x in v.split(",")[:3])
        except (AttributeError, ValueError):
            return defecto

    luces = []
    for s in series:
        sel = [m for m, mat in mallas
               if ("MESHES" in s and casa(s["MESHES"], m.nombre))
               or ("MATERIALS" in s and casa(s["MATERIALS"], mat))]
        umbral = float(s.get("CLUSTER_THRESHOLD") or 25)
        off = K._espejo(trio(s.get("OFFSET"), (0.0, 0.0, 0.0)))
        dire = K._espejo(trio(s.get("DIRECTION"), (0.0, -1.0, 0.0)))
        rango = float(s.get("RANGE") or 30)
        spot = float(s.get("SPOT") or 180)
        grupos, rej = [], {}
        for m in sel:
            for v in m.pos:
                k = tuple(int(c // umbral) for c in v)
                g = next((g for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                          for g in rej.get((k[0] + dx, k[1] + dy, k[2] + dz), ())
                          if math.dist(g["c"], v) < umbral), None)
                if g is None:
                    g = {"c": v, "suma": [0.0, 0.0, 0.0], "n": 0}
                    grupos.append(g)
                    rej.setdefault(k, []).append(g)
                g["suma"] = [g["suma"][i] + v[i] for i in range(3)]
                g["n"] += 1
        etiqueta = re.sub(r"[^A-Za-z0-9]", "", (s.get("MESHES") or s.get("MATERIALS") or "luz"))[:16]
        for i, g in enumerate(grupos):
            c = [g["suma"][k] / g["n"] + off[k] for k in range(3)]
            luces.append({"nombre": f"{etiqueta}_{i}", "pos": tuple(c), "dir": dire,
                          "rango": rango, "spot": spot})
    return luces


# GRANDSTAND SPOTLIGHTS, with Daytona's recipe: without them the crowd cannot be seen at night.
# Measured in the Charlotte by «13x»: the author's 71 grandstand lights are 11,111 with a
# RANGE of 50 m and hanging vertically: at 20 m less than a third of what the track receives
# gets there. Daytona has 313 lights and many are TILTED towards the stand (15,000-25,000,
# range up to 150). Here: one every `PASO_FOCO_GRADA` m along each large stand, IN FRONT of it
# (track side) and above its highest row, pointing at the centre of the crowd.
AREA_GRADA_GRANDE = 3000.0      # m² of crowd: below this they are loose figures or filler stands
PASO_FOCO_GRADA = 30.0
ADELANTE_FOCO_GRADA = 15.0      # m in front of the edge of the stand
SOBRE_GRADA = 10.0              # m above its highest row
INTENSIDAD_GRADA, ALCANCE_GRADA = 15000.0, 150.0


def focos_de_grada(carpeta: str, trazado: str) -> list:
    import generar_sonido as GS
    import ac_trazado as T
    tr = T.leer_ai(os.path.join(carpeta, trazado, "ai", "fast_lane.ai"))["pos"]
    fuera = []
    for gi, g in enumerate(x for x in GS.gradas(carpeta, trazado) if x["area"] >= AREA_GRADA_GRANDE):
        cx, cy, cz = g["centro"]
        ex, ez = g["eje"]
        q = min(tr, key=lambda p: (p[0] - cx) ** 2 + (p[2] - cz) ** 2)
        # towards the track, perpendicular to the stand's axis
        tx, tz = q[0] - cx, q[2] - cz
        a = tx * ex + tz * ez
        tx, tz = tx - a * ex, tz - a * ez
        n = math.hypot(tx, tz) or 1.0
        tx, tz = tx / n, tz / n
        largo = g["hasta"] - g["desde"]
        cuantos = max(1, int(largo // PASO_FOCO_GRADA))
        for k in range(cuantos):
            s = g["desde"] + largo * (k + 0.5) / cuantos
            bx, bz = cx + ex * s, cz + ez * s
            adel = g["fondo"] / 2 + ADELANTE_FOCO_GRADA
            pos = (bx + tx * adel, g["ymax"] + SOBRE_GRADA, bz + tz * adel)
            obj = (bx, (g["ymin"] + g["ymax"]) / 2, bz)
            d = [obj[i] - pos[i] for i in range(3)]
            dn = math.sqrt(sum(c * c for c in d)) or 1.0
            fuera.append({"nombre": f"GRgrada{gi}_{k}", "pos": pos, "dir": tuple(c / dn for c in d),
                          "rango": ALCANCE_GRADA, "spot": 150.0, "intensidad": INTENSIDAD_GRADA})
    return fuera


# SPOTLIGHTS ON THE DARK STRETCHES (measured on the Charlotte Roval). With the author's lights,
# 9 % of the Roval lap was almost dark (the infield: its spotlights are the oval's). Light at
# a point = Σ I·(1 − d/R)² of the lights closer than R (with this measure, Daytona's track
# gives a median of 28,382). Where the lap drops below `LUZ_MINIMA_PISTA`, a spotlight
# every `PASO_FOCO_OSCURO` m, to one side and high up, TILTED towards the racing line (Daytona recipe).
LUZ_MINIMA_PISTA = 15000.0   # with 8,000 it fell short: the Roval track was left with a median of 19,407
#                              and the darkest 10 % < 10,929 (oval 30,400 / 17,855)
PASO_FOCO_OSCURO = 40.0
LADO_FOCO_OSCURO, ALTO_FOCO_OSCURO = 14.0, 14.0
INTENSIDAD_OSCURO, ALCANCE_OSCURO = 15000.0, 75.0


def _luz(p, luces):
    s = 0.0
    for (x, y, z, i, r) in luces:
        d = math.dist(p, (x, y, z))
        if d < r:
            s += i * (1 - d / r) ** 2
    return s


def focos_para_tramos_oscuros(aiw_path: str, luces: list) -> list:
    """New spotlights for the points of the lap with less than `LUZ_MINIMA_PISTA`."""
    import aiw_read as A
    mp = [w.pos for w in A.parse(aiw_path).main_path]
    n = len(mp)
    fuera, ultimo = [], None
    acum = 0.0
    for k in range(n):
        if k:
            acum += math.dist(mp[k], mp[k - 1])
        if _luz(mp[k], luces + [(f["pos"][0], f["pos"][1], f["pos"][2], f["intensidad"], f["rango"])
                                for f in fuera]) >= LUZ_MINIMA_PISTA:
            continue
        if ultimo is not None and acum - ultimo < PASO_FOCO_OSCURO:
            continue
        a, b = mp[k - 1], mp[(k + 1) % n]
        tx, tz = b[0] - a[0], b[2] - a[2]
        tl = math.hypot(tx, tz) or 1.0
        lx, lz = -tz / tl, tx / tl                       # to the left of the direction of travel
        p = mp[k]
        pos = (p[0] + lx * LADO_FOCO_OSCURO, p[1] + ALTO_FOCO_OSCURO, p[2] + lz * LADO_FOCO_OSCURO)
        d = [p[i] - pos[i] for i in range(3)]
        dn = math.sqrt(sum(c * c for c in d)) or 1.0
        fuera.append({"nombre": f"GRoscuro_{len(fuera)}", "pos": pos, "dir": tuple(c / dn for c in d),
                      "rango": ALCANCE_OSCURO, "spot": 150.0, "intensidad": INTENSIDAD_OSCURO})
        ultimo = acum
    return fuera


# LOOSE CROWD IN THE DARK. Besides the 7 large stands, the mod has groups of spectators in the
# infield (around x 70, z 280 in the Charlotte): with the oval's lights, 24 % of the crowd
# points were almost dark. A spotlight above each group that does not reach
# `LUZ_MINIMA_PUBLICO`, pointing down.
LUZ_MINIMA_PUBLICO = 3000.0
CELDA_PUBLICO = 25.0
SOBRE_PUBLICO, INTENSIDAD_PUBLICO, ALCANCE_PUBLICO = 12.0, 15000.0, 50.0


def focos_para_publico_oscuro(carpeta: str, trazado: str, luces: list) -> list:
    import statistics
    import ac_trazado as T
    import kn5_read as K
    celdas = {}
    for p in T.modelos(carpeta, trazado):
        r = K.leer(p, con_geometria=True)
        for m in r["mallas"]:
            if "CROWD" not in r["materiales"][m.material].nombre.upper() or not m.dibuja:
                continue
            for v in m.pos[::7]:
                celdas.setdefault((int(v[0] // CELDA_PUBLICO), int(v[2] // CELDA_PUBLICO)), []).append(v)
    fuera = []
    for (cx, cz), pts in sorted(celdas.items()):
        luz = statistics.median(_luz(q, luces) for q in pts[::5])
        if luz >= LUZ_MINIMA_PUBLICO:
            continue
        c = [sum(q[i] for q in pts) / len(pts) for i in range(3)]
        fuera.append({"nombre": f"GRpublico_{len(fuera)}", "pos": (c[0], max(q[1] for q in pts) + SOBRE_PUBLICO, c[2]),
                      "dir": (0.0, -1.0, 0.0), "rango": ALCANCE_PUBLICO, "spot": 150.0, "intensidad": INTENSIDAD_PUBLICO})
    return fuera


# TRACK SPOTLIGHTS WITH DAYTONA'S RECIPE. With the author's spotlights, in the Charlotte the main
# straight at night came out BLACK except for the stands. Measured in `daytona_lights.sgb64` (the
# official circuit's `.sgb64`, decoded), not assumed:
#   A) 129 spotlights 15,000 / 150 m, cone 120/150, on BOTH sides ~23 m from the centreline, 24 m
#      high, TILTED 24° below the horizontal and pointing ACROSS the track (0.91), colour 0.70/0.84/1.0;
#   C) 57 short ones 15,000-25,000 / 45 m, cone 22/76, ABOVE the track at 39 m, straight down,
#      colour 0.88/0.94/1.0.
# The author's were 33 spotlights ABOVE the centreline at 30 m, straight down, every 69 m, warm
# colour: with the Σ I·(1−d/R)² yardstick they «lit more than Daytona» and in the game the
# straight came out black.
# ⚠️ The yardstick does not look at where the light points: that is why the GEOMETRY is copied, not the number.
# `--track-floodlights` replaces the author's spotlights over the track and those of the dark stretches.
FUERA_DEL_BORDE = 10.0          # m outside the edge of the asphalt (Daytona: ~23 m from the centreline)
ALTO_FOCO_PISTA = 24.0
BAJA_FOCO_PISTA = 24.0          # degrees below the horizontal
PASO_FOCO_PISTA = 60.0          # per side, alternating → one every 30 m (Daytona). With 90 there were loose circles of
#                                 light on the track. The yardstick without real attenuation was misleading:
#                                 23,663 «like Daytona» and in the game, little light.
INTENSIDAD_PISTA = 25000.0      # Daytona's high value (its 67 at 25,000); with 15,000 it fell short
COLOR_FOCO_PISTA = "0.70 0.84 1.0"
ALTO_CORTO, PASO_CORTO = 39.0, 60.0
INTENSIDAD_CORTO, ALCANCE_CORTO, CONO_CORTO = 25000.0, 45.0, (22.0, 76.0)
COLOR_CORTO = "0.88 0.94 1.0"
CERCA_DE_LA_PISTA = 15.0        # an author's spotlight closer than this to the racing line counts as a «track» one


# 🔴🔴 THE GROUND PLANE. With Daytona's recipe the track was still BLACK, the pits in total
# darkness and the stands lit, while the cars' headlights did light things up. What the lights
# that DO illuminate (headlights <1 m off the ground, grandstand spotlights ~10 m from the crowd)
# and those that do NOT (spotlights at 24-30 m, pit lights at ~20 m) have in common: the
# distance to the ground compared with `GroundPlaneDistance`, which was 5 in all of them. In the
# official binary field +60 = the light's HEIGHT above the ground, and Enna (official, SGX)
# carries 2.4-27 m with `GroundPlaneShow="FALSE"`. ⚠️ With the real height and
# `GroundPlaneShow="TRUE"` loading HANGS. Here: real height + Show FALSE, like Enna.
PLANO_MIN, PLANO_MAX = 1.0, 60.0


def _suelo_de_luz(col, x, y, z, d, suelos_ref):
    """The height of the ground the light illuminates: right below it; if there is no collision below
    (spotlights outside the wall, stands without physics), where its AXIS hits the ground; failing
    that, the nearest track."""
    g = col.debajo(x, z, y + 0.5)
    if g:
        return g[1]
    for k in range(1, 100):
        px, py, pz = x + d[0] * 2 * k, y + d[1] * 2 * k, z + d[2] * 2 * k
        g = col.debajo(px, pz, py + 1.0)
        if g and py - g[1] <= 1.0:
            return g[1]
    if suelos_ref:
        return min(suelos_ref, key=lambda q: (q[0] - x) ** 2 + (q[2] - z) ** 2)[1]
    return None


def _plano(bloque: str, col, x: float, y: float, z: float, suelos_ref=None) -> str:
    m = re.search(r'Direction="([-\d.]+) ([-\d.]+) ([-\d.]+)"', bloque)
    d = tuple(float(v) for v in m.groups()) if m else (0.0, -1.0, 0.0)
    sy = _suelo_de_luz(col, x, y, z, d, suelos_ref) if col is not None else None
    if sy is None:
        return bloque.replace('GroundPlaneShow="TRUE"', 'GroundPlaneShow="FALSE"')
    h = max(PLANO_MIN, min(PLANO_MAX, y - sy))
    return (bloque.replace('GroundPlaneDistance="5.000000"', f'GroundPlaneDistance="{h:.6f}"')
                  .replace('GroundPlaneShow="TRUE"', 'GroundPlaneShow="FALSE"'))


PRIORIDAD = ("GRpista", "GRcorto", "1pit")     # first in the file: in case the engine only uses the first N


def focos_daytona(aiw_path: str, col) -> list:
    """Track spotlights along the lap with Daytona's recipe (see above)."""
    import aiw_read as A
    import ac_trazado as T
    mp = [w.pos for w in A.parse(aiw_path).main_path]
    n = len(mp)
    acum = [0.0]
    for a, b in zip(mp, mp[1:]):
        acum.append(acum[-1] + math.dist((a[0], a[2]), (b[0], b[2])))
    vuelta = acum[-1] + math.dist((mp[-1][0], mp[-1][2]), (mp[0][0], mp[0][2]))
    bordes = T.bordes_carrera(col, mp)
    # each point's edge: median over ±40 m (the asphalt widens at the junctions with the pits)
    def borde(k, lado):
        cerca = [bordes[j][lado] for j in range(n)
                 if abs((acum[j] - acum[k] + vuelta / 2) % vuelta - vuelta / 2) <= 40.0]
        return min(sorted(cerca)[len(cerca) // 2], 25.0)
    fuera = []
    cb = math.cos(math.radians(BAJA_FOCO_PISTA))
    sb = math.sin(math.radians(BAJA_FOCO_PISTA))
    siguiente = {0: 0.0, 1: PASO_FOCO_PISTA / 2, "c": PASO_CORTO / 4}
    for k in range(n):
        a, b = mp[k - 1], mp[(k + 1) % n]
        tl = math.hypot(b[0] - a[0], b[2] - a[2]) or 1.0
        lx, lz = -(b[2] - a[2]) / tl, (b[0] - a[0]) / tl        # left of the direction of travel
        p = mp[k]
        for lado, sg in ((0, 1.0), (1, -1.0)):
            if acum[k] < siguiente[lado]:
                continue
            siguiente[lado] = acum[k] + PASO_FOCO_PISTA
            d = borde(k, lado) + FUERA_DEL_BORDE
            pos = (p[0] + sg * lx * d, p[1] + ALTO_FOCO_PISTA, p[2] + sg * lz * d)
            fuera.append({"nombre": f"GRpista{lado}_{len(fuera)}", "pos": pos,
                          "dir": (-sg * lx * cb, -sb, -sg * lz * cb), "rango": ALCANCE_FOCO,
                          "spot": 150.0, "intensidad": INTENSIDAD_PISTA, "color": COLOR_FOCO_PISTA})
        if acum[k] >= siguiente["c"]:
            siguiente["c"] = acum[k] + PASO_CORTO
            off = (borde(k, 0) - borde(k, 1)) / 2                 # over the centre of the asphalt
            fuera.append({"nombre": f"GRcorto_{len(fuera)}", "pos": (p[0] + lx * off, p[1] + ALTO_CORTO, p[2] + lz * off),
                          "dir": (0.0, -1.0, 0.0), "rango": ALCANCE_CORTO, "spot": 150.0,
                          "intensidad": INTENSIDAD_CORTO, "color": COLOR_CORTO, "cono": CONO_CORTO})
    return fuera


def escribir_series(salida: str, nombre: str, carpeta: str, trazado: str, focos_gradas: bool = False,
                    aiw_tramos_oscuros: str | None = None, aiw_daytona: str | None = None,
                    plano_real: bool = False) -> dict:
    """The `_lights.sgx` from the AC author's series. Without series, nothing is touched.
    `aiw_daytona`: track spotlights with Daytona's recipe (`--track-floodlights`)."""
    return _escribir_series(salida, nombre, carpeta, trazado, focos_gradas, aiw_tramos_oscuros, aiw_daytona,
                            plano_real)


def _escribir_series(salida, nombre, carpeta, trazado, focos_gradas, aiw_tramos_oscuros, aiw_daytona,
                     plano_real=False) -> dict:
    luces = series_ac(carpeta, trazado)
    if luces and focos_gradas:
        luces = luces + focos_de_grada(carpeta, trazado)
    if not luces:
        return {"luces": 0, "motivo": "the track declares no LIGHT_SERIES"}
    # 🔴 CALIBRATION against the OFFICIAL reference. Daytona (extracted from the game): ~76 lights
    # of ~15,000 with a RANGE of 100-175 m. With 16,000, range 60 and 255 lights the track did not
    # light up, and with intensity by I/h² against Mid-Ohio + the ground plane at the real height
    # (and `GroundPlaneShow="TRUE"`) loading HUNG: without `--plano-real`,
    # `GroundPlaneDistance` is left at 5, like all the references. The spotlights OVER drivable
    # ground (track, pits) get Daytona's recipe and are spaced at `ESPACIADO_FOCOS` (with a
    # 150 m range, one every 25 m is redundant); stands, Ferris wheel and buildings stay as they were.
    import ac_trazado as T
    import math as _m
    sup_ini = os.path.join(carpeta, trazado, "data", "surfaces.ini")
    claves = T.superficies(sup_ini) if os.path.exists(sup_ini) else dict(T.SISTEMA_AC)
    col = T.Colision(T.modelos(carpeta, trazado), claves)
    destino = os.path.join(salida, "Tracks", nombre, f"{nombre}_lights.sgx")
    partes, cajas, alturas, focos, escritas, emitidas = [], [], [], [], [], []
    suelos_ref = []
    for ruta_aiw in (aiw_daytona, aiw_tramos_oscuros):
        if ruta_aiw and os.path.exists(ruta_aiw):
            import aiw_read as _A0
            suelos_ref = [w.pos for w in _A0.parse(ruta_aiw).main_path]
            break
    trazada = []
    if aiw_daytona and os.path.exists(aiw_daytona):
        import aiw_read as _A
        trazada = [w.pos for w in _A.parse(aiw_daytona).main_path]
    quitadas = 0
    for l in luces:
        x, y, z = l["pos"]
        suelo = col.debajo(x, z, y - 30.0)
        sobre = bool(suelo and suelo[1] < y - 3.0) and not l.get("intensidad")
        if sobre and trazada and min(_m.dist((x, z), (q[0], q[2])) for q in trazada) < CERCA_DE_LA_PISTA:
            quitadas += 1                                   # Daytona's recipe replaces them
            continue
        if sobre:
            if not l["nombre"].startswith("1pit") and any(_m.dist((x, z), (f[0], f[2])) < ESPACIADO_FOCOS for f in focos):
                continue                                    # one nearby already lights this (in the pits all are kept)
            focos.append((x, y, z))
            alturas.append(y - suelo[1])
        dx, dy, dz = l["dir"]
        i_, r = ((l["intensidad"], l["rango"]) if l.get("intensidad") else
                 (INTENSIDAD_FOCO, ALCANCE_FOCO) if sobre else (LUZ_POR_M2 * l["rango"] ** 2, l["rango"]))
        n = len(partes) + 1
        bloque = PLANTILLA.format(no=n, nombre=l["nombre"], x=x, y=y, z=z, intensidad=i_, rango=r)
        bloque = bloque.replace('Direction="0.000000 -1.000000 0.000000"',
                                f'Direction="{dx:.6f} {dy:.6f} {dz:.6f}"')
        # the author's cone only if it is a narrow spotlight; 180 (hemisphere) switches the light off in AMS2
        if l["spot"] < 150:
            bloque = bloque.replace('InnerAngle="120.0" OuterAngle="150.0"',
                                    f'InnerAngle="-1.0" OuterAngle="{l["spot"]:.1f}"')
        partes.append(_plano(bloque, col, x, y, z, suelos_ref) if plano_real else bloque)
        escritas.append(l["nombre"])
        emitidas.append((x, y, z, i_, r))
        cajas.append((x - r, y - r, z - r, x + r, y + r, z + r))
    extra = []
    if trazada:
        extra = focos_daytona(aiw_daytona, col)
    elif aiw_tramos_oscuros and os.path.exists(aiw_tramos_oscuros):
        extra = focos_para_tramos_oscuros(aiw_tramos_oscuros, emitidas)
    # The new track spotlights point at the TRACK, not at the crowd; the yardstick ignores direction
    # and with them they «lit» the infield crowd: the 33 crowd spotlights disappeared.
    emitidas_sin_pista = list(emitidas)
    if extra:
        for l in extra:
            x, y, z = l["pos"]
            dx, dy, dz = l["dir"]
            i_, r = l["intensidad"], l["rango"]
            bloque = PLANTILLA.format(no=len(partes) + 1, nombre=l["nombre"], x=x, y=y, z=z, intensidad=i_, rango=r)
            bloque = bloque.replace('Direction="0.000000 -1.000000 0.000000"', f'Direction="{dx:.6f} {dy:.6f} {dz:.6f}"')
            if l.get("color"):
                bloque = bloque.replace('Colour="1.0 0.98 0.92"', f'Colour="{l["color"]}"')
            if l.get("cono"):
                bloque = bloque.replace('InnerAngle="120.0" OuterAngle="150.0"',
                                        f'InnerAngle="{l["cono"][0]:.1f}" OuterAngle="{l["cono"][1]:.1f}"')
            partes.append(_plano(bloque, col, x, y, z, suelos_ref) if plano_real else bloque)
            escritas.append(l["nombre"])
            emitidas.append((x, y, z, i_, r))
            cajas.append((x - r, y - r, z - r, x + r, y + r, z + r))
    if focos_gradas:
        for l in focos_para_publico_oscuro(carpeta, trazado, emitidas_sin_pista if trazada else emitidas):
            x, y, z = l["pos"]
            i_, r = l["intensidad"], l["rango"]
            b_ = PLANTILLA.format(no=len(partes) + 1, nombre=l["nombre"], x=x, y=y, z=z, intensidad=i_, rango=r)
            partes.append(_plano(b_, col, x, y, z, suelos_ref) if plano_real else b_)
            escritas.append(l["nombre"])
            emitidas.append((x, y, z, i_, r))
            cajas.append((x - r, y - r, z - r, x + r, y + r, z + r))
    if plano_real:
        orden = sorted(range(len(partes)), key=lambda i: next((k for k, p in enumerate(PRIORIDAD)
                                                              if escritas[i].startswith(p)), len(PRIORIDAD)))
        partes = [re.sub(r'<OBJ_ID no="\d+">', f'<OBJ_ID no="{j + 1}">', partes[i], count=1)
                  for j, i in enumerate(orden)]
        escritas = [escritas[i] for i in orden]
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(CABECERA.format(n=len(partes)))
        fh.writelines(partes)
        fh.write(PARTICION.format(
            x0=min(c[0] for c in cajas), y0=min(c[1] for c in cajas), z0=min(c[2] for c in cajas),
            x1=max(c[3] for c in cajas), y1=max(c[4] for c in cajas), z1=max(c[5] for c in cajas),
            hijos=" ".join(str(i) for i in range(1, len(partes) + 1))))
        fh.write("</SCENE>\n")
    import collections
    por = collections.Counter(n.rsplit("_", 1)[0] for n in escritas)
    alturas.sort()
    alturas = alturas or [0.0]
    return {"luces": len(escritas), "del_autor": len(luces), "focos_de_pista": len(focos),
            "daytona": {"quitados_del_autor": quitadas, "focos": sum(1 for e in extra if e["nombre"].startswith("GRpista")),
                        "cortos": sum(1 for e in extra if e["nombre"].startswith("GRcorto"))} if trazada else None,
            "series": dict(por),
            "alturas": (round(alturas[0], 1), round(alturas[len(alturas) // 2], 1), round(alturas[-1], 1)),
            "sobre_suelo": sum(1 for a in alturas if a > 0)}
