"""Writes `physics/triggers.xml` with the track's timing triggers.

    python3 generar_triggers.py <pack>/Tracks/<n>/physics/triggers.xml <aiw>
    python3 generar_triggers.py --auditar <aiw> <triggers.xml> [<aiw> <triggers.xml> …]

🔴 Why it exists: the template's `triggers.xml` is **byte for byte Meadowdale's**: the 5 planes
—finish line, the two split points and the pit entry and exit— were **between 272 and 862 m out
of place** on another track. Effect: **no lap time, no splits, no pit limiter**. And it raises no
error: the session starts and does not score.

The CRC of each trigger **cannot be computed**: the game uses a CRC32 variant that does not match
any standard one (zlib, MPEG-2, BZIP2, POSIX tried, with and without reflection). It was
**deduced** by cross-referencing the `triggers.xml` of Mid-Ohio and GJ Kartway with their own
AIWs: which one falls on the finish line, which ones far from the pit lane (the splits) and which
ones right at the pit entry and exit. **Both references agree on all five.**

And the orientation was also measured from Mid-Ohio: with `(dx, dz)` the direction of travel, the
matrix is always

    [ dx   0   dz ]
    [  0  -1    0 ]
    [ dz   0  -dx ]

No `bpy`: it is tested without Blender.
"""

import math
import os
import re
import sys

# Deduced, not computed. See the docstring.
CRC = {
    "TRG_START": 4110219313,
    "TRG_CHECKPOINT1": 2964580884,
    "TRG_CHECKPOINT2": 2964580887,
    "TRG_PITIN": 3836397042,
    "TRG_PITOUT": 3449420218,
}

ALTO = 100.0          # the references use 100-138 m
GRUESO = 1.0          # the "Width": the plane's size along the direction of travel


def _acumulado(pts):
    out = [0.0]
    for i in range(1, len(pts)):
        out.append(out[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][2] - pts[i - 1][2]))
    return out


def _en_la_distancia(pts, acum, d):
    """Point and direction of travel `d` metres from the finish line."""
    for i in range(1, len(acum)):
        if acum[i] >= d:
            a, b = pts[i - 1], pts[i]
            t = (d - acum[i - 1]) / max(acum[i] - acum[i - 1], 1e-6)
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
            return p, _dir(a, b)
    return pts[0], _dir(pts[0], pts[1])


def _dir(a, b):
    dx, dz = b[0] - a[0], b[2] - a[2]
    r = math.hypot(dx, dz) or 1.0
    return dx / r, dz / r


def matriz(dx, dz) -> str:
    """The orientation, measured at Mid-Ohio: row 0 the direction of travel, row 1 (0,-1,0), row 2 (dz,0,-dx)."""
    return ";".join(f"{v:.6f}" for v in (dx, 0.0, dz, 0.0, -1.0, 0.0, dz, 0.0, -dx))


def calcular(aiw) -> list:
    """The 5 triggers with their position, orientation and size, taken from the AIW."""
    pts = [w.pos for w in aiw.main_path]
    if len(pts) < 3:
        return []
    acum = _acumulado(pts)
    vuelta = acum[-1]
    anchos = [min(w.width[0], w.width[1]) for w in aiw.main_path
              if getattr(w, "width", None) and len(w.width) >= 2]
    largo = max(18.0, 2.2 * (sorted(anchos)[len(anchos) // 2] if anchos else 9.0))

    # `aiw_read` does not expose the sectors, so they are taken from the file's text. And mind
    # the format: the AMS1 original writes `sector_2_length` **CUMULATIVE from the finish line**
    # (799 and 1620 at Charlotte), while OMTT writes the length of the stretch. Both are accepted
    # and normalised to cumulative.
    s1 = s2 = 0.0
    ruta = getattr(aiw, "_ruta", None)
    if ruta and os.path.exists(ruta):
        txt = open(ruta, encoding="latin-1", errors="ignore").read()
        m1 = re.search(r"sector_1_length=([\d.]+)", txt)
        m2 = re.search(r"sector_2_length=([\d.]+)", txt)
        s1 = float(m1.group(1)) if m1 else 0.0
        s2 = float(m2.group(1)) if m2 else 0.0
    if s1 <= 0:
        s1 = vuelta / 3.0
    if s2 <= s1 + vuelta * 0.1:        # it came as a stretch length, not cumulative
        s2 = s1 + (s2 if s2 > 0 else vuelta / 3.0)

    fuera = []
    p, d = pts[0], _dir(pts[0], pts[1])
    fuera.append(("TRG_START", p, d, largo))
    for nombre, dist in (("TRG_CHECKPOINT1", s1), ("TRG_CHECKPOINT2", s2)):
        p, d = _en_la_distancia(pts, acum, min(dist, vuelta - 1))
        fuera.append((nombre, p, d, largo))

    pit = aiw.pit_path_ordered()
    if len(pit) >= 2:
        pp = [w.pos for w in pit]
        ancho_pit = max(12.0, largo * 0.5)
        i = _lejos_de_la_pista(pp, pts, ancho_pit, desde=0)
        j = _lejos_de_la_pista(pp, pts, ancho_pit, desde=len(pp) - 1)
        fuera.append(("TRG_PITIN", pp[i], _dir(pp[i], pp[min(i + 1, len(pp) - 1)]), ancho_pit))
        fuera.append(("TRG_PITOUT", pp[j], _dir(pp[max(j - 1, 0)], pp[j]), ancho_pit))
    return fuera


def _lejos_de_la_pista(pp, pista, ancho, desde):
    """First pit lane point, walking from one end, that does NOT touch the racing line.

    🔴 Why: the AI went into the pits after the first lap and lap times did not count. The pit
    triggers were placed on the **first and last waypoints** of the pit branch. But those two
    points are exactly where the pit lane **splits off from the track**: measured at Charlotte,
    **3.3 m** and **3.8 m** from the racing line. With a trigger **12 m** long, the racing line
    lies INSIDE it.

    And that produces both symptoms at once: a car going through there during the race fires
    "entered the pits", and **a car flagged as in the pits does not get its lap validated**. One
    single placement error explains both the AI entering the pits and the lap times not counting.

    It walks along the pit lane from the end until it finds a point that is further from the track
    than half the trigger length plus a margin. The median separation of that branch is 12.7 m, so
    such points exist; if none were found, the end point is returned.
    """
    import math

    minimo = ancho / 2.0 + 4.0
    paso = 1 if desde == 0 else -1
    i = desde
    while 0 <= i < len(pp):
        p = pp[i]
        d = min(math.dist((p[0], p[2]), (q[0], q[2])) for q in pista)
        if d >= minimo:
            return i
        i += paso
    return desde


def calcular_ac(trazado: dict) -> list:
    """The 5 triggers of an Assetto Corsa track, from its declared GATES.

    In AC nothing needs to be deduced: timing comes as pairs of posts `AC_TIME_n_L/R` (0 = finish
    line, 1 and 2 = splits). Measured on Mountain Peak: finish line at 0.2 % of the lap and **93 m
    wide** —it crosses the track AND the pit lane, which is correct: whoever leaves the pits also
    crosses the line—, splits at 41 % and 61 %.

    Each gate is reproduced exactly as the author placed it: centre between the two posts, width =
    distance between them, and plane perpendicular to the line joining them. The pits (entry and
    exit) are not in AC: they come from the pit lane, away from the racing line, with the same rule
    as for AMS1 (`_lejos_de_la_pista`).
    """
    tiempos = trazado["marcas"]["tiempos"]
    fuera = []
    for n, nombre in ((0, "TRG_START"), (1, "TRG_CHECKPOINT1"), (2, "TRG_CHECKPOINT2")):
        izq, der = tiempos.get(f"AC_TIME_{n}_L"), tiempos.get(f"AC_TIME_{n}_R")
        if not (izq and der):
            continue
        c = tuple((izq[i] + der[i]) / 2.0 for i in range(3))
        ax, az = der[0] - izq[0], der[2] - izq[2]
        ancho = math.hypot(ax, az)
        # the plane's normal (direction of travel) is perpendicular to the posts; it is oriented
        # with the racing line so it does not end up backwards
        nx, nz = -az / ancho, ax / ancho
        tr = trazado["trazada"]
        k = min(range(len(tr)), key=lambda i: (tr[i][0] - c[0]) ** 2 + (tr[i][2] - c[2]) ** 2)
        tx, tz = _dir(tr[k], tr[(k + 1) % len(tr)])
        if nx * tx + nz * tz < 0:
            nx, nz = -nx, -nz
        fuera.append((nombre, c, (nx, nz), ancho))

    pp = trazado.get("boxes_linea") or []
    if len(pp) >= 2:
        ancho_pit = 12.0
        # 🔴 Away from the RACING LINE AND from the CENTRE LINE, not just the racing line. On an
        # oval the racing line runs HIGH in the turns: a point 10 m from it was still inside a
        # 21 m wide track (measured: TRG_PITIN 2.4 m from the centre line).
        tr = trazado["trazada"]
        centros = []
        for k, (bi, bd, _mi, _md) in enumerate(trazado["bordes"]):
            dx, dz = _dir(tr[k], tr[(k + 1) % len(tr)])
            centros.append((tr[k][0] - dz * (bi - bd) / 2.0, tr[k][1], tr[k][2] + dx * (bi - bd) / 2.0))
        pista = list(tr) + centros
        i = _lejos_de_la_pista(pp, pista, ancho_pit, desde=0)
        j = _lejos_de_la_pista(pp, pista, ancho_pit, desde=len(pp) - 1)
        fuera.append(("TRG_PITIN", pp[i], _dir(pp[i], pp[min(i + 1, len(pp) - 1)]), ancho_pit))
        fuera.append(("TRG_PITOUT", pp[j], _dir(pp[max(j - 1, 0)], pp[j]), ancho_pit))
    return fuera


def escribir(ruta_xml: str, aiw, disparadores=None) -> dict:
    """Rewrites the template's 5 `ShapeDesc` blocks with the track's data."""
    if not os.path.exists(ruta_xml):
        return {"ok": False, "error": "there is no template triggers.xml"}
    texto = open(ruta_xml, encoding="utf-8", errors="ignore").read()
    bloques = list(re.finditer(r'<data class="ShapeDesc"[^>]*>.*?</data>', texto, re.S))
    disparadores = disparadores if disparadores is not None else calcular(aiw)
    if len(bloques) < len(disparadores):
        return {"ok": False, "error": f"the template has {len(bloques)} blocks and {len(disparadores)} are needed"}

    def poner(bloque, **props):
        for k, v in props.items():
            bloque = re.sub(rf'(<prop name="{re.escape(k)}" data=")[^"]*(")',
                            lambda m: m.group(1) + str(v) + m.group(2), bloque, count=1)
        return bloque

    nuevos = []
    for i, (nombre, p, (dx, dz), largo) in enumerate(disparadores):
        nuevos.append(poner(
            bloques[i].group(0),
            **{"Name": f"{0xA0000000 + i * 0x1111:08x}",
               "Material CRC": CRC[nombre],
               "Relative Position": f"{p[0]:.6f};{p[1]:.6f};{p[2]:.6f}",
               "Relative Orientation": matriz(dx, dz),
               "Width": f"{GRUESO:.6f}", "Height": f"{ALTO:.6f}", "Length": f"{largo:.6f}"}))

    for b, nuevo in zip(reversed(bloques[:len(nuevos)]), reversed(nuevos)):
        texto = texto[:b.start()] + nuevo + texto[b.end():]
    open(ruta_xml, "w", encoding="utf-8").write(texto)
    return {"ok": True, "disparadores": [(n, round(p[0], 1), round(p[2], 1))
                                         for n, p, _d, _l in disparadores]}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import aiw_read as A

    r = escribir(argv[1], A.parse(argv[2]))
    if not r["ok"]:
        print(f"🔴 {r['error']}")
        return 1
    print(f"✅ {len(r['disparadores'])} triggers from the AIW: "
          + " · ".join(f"{n.replace('TRG_', '')}" for n, _x, _z in r["disparadores"]))
    return 0


# ─────────────────────────────────────────────────────────────────────────────────────────
# 🔴 AUDIT: which part of the track does each trigger touch?
#
# It is a general problem, not a one-track one. What was measured on the Charlotte Roval: the
# author's `AC_TIME_1` gate sits on the line separating TWO stretches that share 29 m of asphalt
# WITHOUT a wall, in opposite directions (at 304 and 1,444 m into the lap). In Assetto Corsa the
# gate is a line with no thickness and the game knows where in the lap each car is; in AMS2 it is
# a box 100 m tall, and the outbound stretch touches it BACKWARDS. And `TRG_PITOUT` overlapped
# the edge by 1.2 m.
#
# Measuring against the racing LINE is not enough, you have to measure against the asphalt BAND:
# with the racing line 12 m away and a 12 m trigger, "it does not touch it" — and the track edge,
# 6 m away, does.
#
# Sides, measured with the Roval's ground cross-section (x = 190: asphalt from z = 128 to 157):
# `wp_width[0]` goes towards −`wp_perp` and `wp_width[1]` towards +`wp_perp`.
# ─────────────────────────────────────────────────────────────────────────────────────────

ESPERADO = {"TRG_START": 0, "TRG_CHECKPOINT1": 0, "TRG_CHECKPOINT2": 0, "TRG_PITIN": 1, "TRG_PITOUT": 1}
# Thresholds taken from Daytona, Mid-Ohio and GJ Kartway (Reiza) and the 3 COTA layouts:
#   finish line and splits: cover 100 % of the asphalt, with ≥ 3.3 m to spare on each side, and
#   the nearest stretch of track that is NOT theirs passes at ≥ 16.5 m (GJ Kartway, a tight kart track).
#   pits: cover ≥ 85 % of the pit lane and touch the track by at most 0.4 m (Mid-Ohio).
CUBRE_MIN_META = 0.99
SOBRA_MIN_META = 2.0      # m of trigger beyond the asphalt, on each side
HOLGURA_META = 10.0       # m clear up to any other stretch of track
CUBRE_MIN_BOXES = 0.80
ROCE_MAX_BOXES = 0.5      # m of track a pit trigger may overlap



def leer_aiw_bandas(ruta):
    """Waypoints with position, next, perpendicular, width on each side, branch and distance."""
    import aiw_puntuar as AP
    texto = open(ruta, encoding="latin-1").read()
    wps = []
    for a, b in AP._bloques(texto):
        bl = texto[a:b]
        p = AP._campo(bl, "WP_PTRS")
        wps.append({"pos": AP._campo(bl, "wp_pos"), "perp": AP._campo(bl, "wp_perp") or [0, 0, 0],
                    "ancho": AP._campo(bl, "wp_width") or [0, 0], "rama": int(AP._campo(bl, "wp_branchID")[0]),
                    "sig": int(p[1]) if p else -1, "d": (AP._campo(bl, "wp_score") or [0, 0])[1]})
    return wps


def leer_disparadores(ruta):
    inv = {v: k for k, v in CRC.items()}
    txt = open(ruta, encoding="utf-8", errors="ignore").read()
    fuera = []
    for m in re.finditer(r'<data class="ShapeDesc"[^>]*>(.*?)</data>', txt, re.S):
        b = m.group(1)
        g = lambda k: re.search(rf'name="{k}" data="([^"]*)"', b).group(1)  # noqa: E731
        c = [float(x) for x in g("Relative Position").split(";")]
        o = [float(x) for x in g("Relative Orientation").split(";")]
        fuera.append({"nombre": inv.get(int(g("Material CRC")), g("Material CRC")), "c": (c[0], c[2]),
                      "avance": (o[0], o[2]), "eje": (o[6], o[8]), "largo": float(g("Length"))})
    return fuera


def cruces(wps, trg):
    """Every pass of the track or the pit lane through the trigger's plane: where, in which
    direction, and which part of its asphalt band (along the trigger) lies inside."""
    (cx, cz), (nx, nz), (ex, ez), L = trg["c"], trg["avance"], trg["eje"], trg["largo"]
    fuera = []
    for i, w in enumerate(wps):
        j = w["sig"]
        if not (0 <= j < len(wps)) or wps[j]["rama"] != w["rama"]:
            continue
        p, q = w["pos"], wps[j]["pos"]
        sp = (p[0] - cx) * nx + (p[2] - cz) * nz
        sq = (q[0] - cx) * nx + (q[2] - cz) * nz
        if not ((sp < 0 <= sq) or (sp > 0 >= sq)):
            continue
        f = sp / (sp - sq)
        x, z = p[0] + (q[0] - p[0]) * f, p[2] + (q[2] - p[2]) * f
        lat = (x - cx) * ex + (z - cz) * ez
        # edges: centre − perp·ancho[0] and centre + perp·ancho[1], projected onto the axis
        pe = w["perp"]
        k = pe[0] * ex + pe[2] * ez
        b1, b2 = lat - k * w["ancho"][0], lat + k * w["ancho"][1]
        lo, hi = min(b1, b2), max(b1, b2)
        dentro = max(0.0, min(hi, L / 2) - max(lo, -L / 2))
        hueco = max(lo - L / 2, -L / 2 - hi, 0.0)            # distance to the end if it does not touch
        fuera.append({"rama": w["rama"], "d": w["d"] + f * math.dist(p, q), "sentido": 1 if sq > sp else -1,
                      "lat": lat, "banda": (lo, hi), "dentro": dentro, "cubre": dentro / max(hi - lo, 1e-6),
                      "hueco": hueco, "i": i})
    return fuera


def auditar(ruta_aiw, ruta_trg, wps=None, col=None):
    """[(trigger, problem)] — empty if everything is fine. Rules measured at Daytona, Mid-Ohio,
    GJ Kartway and COTA (see docs/LESSONS.md): the stretch it belongs to crosses it forwards and
    across all its asphalt; no other stretch comes close to it (thresholds above)."""
    wps = wps or leer_aiw_bandas(ruta_aiw)
    mal = []
    for t in leer_disparadores(ruta_trg):
        mal += [(t["nombre"], p) for p in evaluar(wps, t, col)]
    return mal


def _problemas(wps, t):
    """A trigger is a BOX: it has no direction of travel (COTA's split 2 is "backwards" and
    works). What matters is which stretch crosses it, over how much width, and that no OTHER
    stretch comes close to it."""
    es_meta = ESPERADO.get(t["nombre"]) == 0
    cs = cruces(wps, t)
    suyos = [c for c in cs if (c["rama"] == 0) == es_meta and c["dentro"] > 0]
    problemas = []
    mejor = max(suyos, key=lambda c: c["cubre"]) if suyos else None
    if mejor is None:
        return ["not crossed by " + ("the track" if es_meta else "the pit lane")]
    L = t["largo"]
    sobra = min(L / 2 - mejor["banda"][1], mejor["banda"][0] + L / 2)
    if es_meta and (mejor["cubre"] < CUBRE_MIN_META or sobra < SOBRA_MIN_META):
        problemas.append(f"at {mejor['d']:.0f} m it covers {100 * mejor['cubre']:.0f} % of the asphalt with "
                         f"{sobra:.1f} m to spare (official tracks: 100 % and ≥ 3.3 m)")
    if not es_meta and mejor["cubre"] < CUBRE_MIN_BOXES:
        problemas.append(f"it covers {100 * mejor['cubre']:.0f} % of the pit lane (official tracks: ≥ 85 %)")
    for c in cs:
        if c is mejor:
            continue
        # the same crossing counted twice (it falls on a vertex)
        if c["rama"] == mejor["rama"] and abs(c["lat"] - mejor["lat"]) < 10 and abs(c["d"] - mejor["d"]) < 15:
            continue
        # the pit lane may cross the finish line and the splits (Daytona, the oval)
        if es_meta and c["rama"] != 0:
            continue
        sentido = "the opposite way" if c["sentido"] * mejor["sentido"] < 0 else "the same way"
        roce = f"overlaps {c['dentro']:.1f} m" if c["dentro"] > 0 else f"is {c['hueco']:.1f} m away"
        if es_meta and c["hueco"] < HOLGURA_META:
            problemas.append(f"another stretch of track, at {c['d']:.0f} m along the lap, runs {sentido} and {roce} "
                             f"(official tracks: ≥ 16.5 m)")
        elif not es_meta and c["rama"] == 0 and c["dentro"] > ROCE_MAX_BOXES:
            problemas.append(f"the track, at {c['d']:.0f} m, {roce} (official tracks: ≤ 0.4 m)")
        elif not es_meta and c["rama"] != 0 and c["dentro"] > 0:
            problemas.append(f"the pit lane passes again at {c['d']:.0f} m and {roce}")
    return problemas


def _puerta_en(wps, i, f=0.0, margen=2.0):
    """Trigger perpendicular to the direction of travel on stretch i→next (fraction f), covering
    its whole asphalt band plus `margen` on each side."""
    w = wps[i]
    q = wps[w["sig"]]["pos"]
    p = w["pos"]
    x, y, z = (p[k] + (q[k] - p[k]) * f for k in range(3))
    dx, dz = _dir(p, q)
    ex, ez = dz, -dx                                      # row 2 of `matriz`
    pe = w["perp"]
    k = pe[0] * ex + pe[2] * ez
    b1, b2 = -k * w["ancho"][0], k * w["ancho"][1]
    lo, hi = min(b1, b2) - margen, max(b1, b2) + margen
    medio = (lo + hi) / 2
    return {"c": (x + ex * medio, z + ez * medio), "y": y, "avance": (dx, dz), "eje": (ex, ez), "largo": hi - lo}


HUECO_MIN_FISICO = 4.0    # m of NON-valid ground (grass, "OUT") between the track and the next asphalt


def banda_fisica(col, x, y, z, eje, alcance=60.0, paso=0.25):
    """Along the REAL ground (the collision), along `eje` from (x, z): where this stretch's valid
    asphalt ends on each side, and how much invalid ground there is until the next asphalt (that of
    another stretch), or `alcance` if there is none.

    🔴 Why the AIW width is not enough (measured on the Roval): at 1,476 m the AIW said ±7.8 m and
    the ground says −10 / +10.5, and at +13 m the asphalt of the opposite stretch begins, with only
    2.5 m of "OUT" in between. A trigger measured against the AIW overlapped it by 0.8 m."""
    validas = set(getattr(col, "validas", ()))
    fuera = []
    for s in (-1, 1):
        k, yy, borde, hueco = 0.0, y, None, None
        while k < alcance:
            k += paso
            h = col.debajo(x + eje[0] * k * s, z + eje[1] * k * s, yy)
            ok = h is not None and h[0] in validas
            if h is not None:
                yy = h[1]
            if borde is None and not ok:
                borde = k
            elif borde is not None and ok:
                hueco = k - borde
                break
        fuera.append((borde if borde is not None else alcance, hueco if hueco is not None else alcance))
    (bl, hl), (br, hr) = fuera
    return {"lo": -bl, "hi": br, "hueco_lo": hl, "hueco_hi": hr}


def _bandas_fisicas(col, wps, t, alcance=40.0, ramas=(0,)):
    """For each stretch (of the requested `ramas`) that crosses the trigger's LINE (extended, not
    just its box): its real asphalt along the axis, in trigger coordinates.
    [(cruce, lo, hi)]"""
    largo = dict(t, largo=4 * alcance + t["largo"])
    fuera = []
    for c in cruces(wps, largo):
        if c["rama"] not in ramas:
            continue
        w = wps[c["i"]]
        p, q = w["pos"], wps[w["sig"]]["pos"]
        sp = (p[0] - t["c"][0]) * t["avance"][0] + (p[2] - t["c"][1]) * t["avance"][1]
        sq = (q[0] - t["c"][0]) * t["avance"][0] + (q[2] - t["c"][1]) * t["avance"][1]
        f = sp / (sp - sq) if sp != sq else 0.0
        x, y, z = (p[k] + (q[k] - p[k]) * f for k in range(3))
        bf = banda_fisica(col, x, y, z, t["eje"], alcance=alcance)
        fuera.append((c, c["lat"] + bf["lo"], c["lat"] + bf["hi"]))
    return fuera


def problemas_fisicos(col, wps, t, holgura=2.0):
    """Finish line and splits against the GROUND: they cover the asphalt of their whole stretch,
    and do not reach the asphalt where ANOTHER stretch of the lap passes (with `holgura` of invalid
    ground)."""
    if ESPERADO.get(t["nombre"]) != 0:
        return _problemas_fisicos_boxes(col, wps, t)
    L = t["largo"]
    bandas = _bandas_fisicas(col, wps, t)
    # the stretch it BELONGS to is chosen with the real trigger: with the extended line of
    # `_bandas_fisicas` every crossing "covers 100 %" and the first one got picked
    reales = [c for c in cruces(wps, t) if c["rama"] == 0 and c["dentro"] > 0]
    if not reales:
        return ["the track doesn't cross it"]
    mejor = max(reales, key=lambda c: c["cubre"])
    suyo = min(bandas, key=lambda x: (x[0]["i"] != mejor["i"], abs(x[0]["lat"] - mejor["lat"])))
    fuera = []
    lo, hi = suyo[1], suyo[2]
    tope = 30.0      # the asphalt "of this stretch" that must be covered, at most 30 m from the racing line
    lo_c, hi_c = max(lo, suyo[0]["lat"] - tope), min(hi, suyo[0]["lat"] + tope)
    if lo_c < -L / 2 or hi_c > L / 2:
        fuera.append(f"it doesn't cover its stretch's real asphalt ({lo_c:.1f}…{hi_c:.1f} m, the trigger "
                     f"±{L / 2:.1f})")
    for c, olo, ohi in bandas:
        if c is suyo[0]:
            continue
        if c["rama"] == suyo[0]["rama"] and abs(c["lat"] - suyo[0]["lat"]) < 10 and abs(c["d"] - suyo[0]["d"]) < 15:
            continue
        hueco = max(olo - L / 2, -L / 2 - ohi)
        if hueco < holgura:
            sentido = "the opposite way" if c["sentido"] * suyo[0]["sentido"] < 0 else "the same way"
            fuera.append(f"the asphalt of the stretch at {c['d']:.0f} m (running {sentido}) is {hueco:.1f} m "
                         f"from the end (minimum {holgura:.0f} m)")
    return fuera


CARRIL_BOXES = 6.0        # m of lane on each side of the pit lane line that must be covered
MURO_MIN = 1.0            # m of NON-valid ground between pit lane and track for them to count as separate


def _separacion_boxes(col, wps, t):
    """Is there a WALL (or a gap) between the pit lane and the track where this pit trigger is?

    🔴 The AIW's pit lane has 6 m on each side BY DEFAULT from the exporter. At Jarama there is a
    2.5 m wall between the pit lane and the straight: against the AIW, a 12 m trigger "touched" the
    track and the rule sent it 235 m back, to the middle of the pit lane. But on an oval the pit
    lane and the track are ONE continuous asphalt (the apron joins them): there the ground
    separates nothing and the AIW rules.

    Returns None if there is no physical separation (or it cannot be measured), or
    {"lado": ±1 towards the track, "borde": m to the end of the pit ground, "muro": m without ground,
     "otro": m of pit ground on the other side (capped at 30), "lat": the pit lane in trigger coords}."""
    reales = [c for c in cruces(wps, t) if c["rama"] != 0 and c["dentro"] > 0]
    if not reales:
        return None
    mejor = max(reales, key=lambda c: c["cubre"])
    largo = dict(t, largo=80.0 + t["largo"])
    pistas = [c for c in cruces(wps, largo) if c["rama"] == 0]
    if not pistas:
        return None
    cercana = min(pistas, key=lambda c: abs(c["lat"] - mejor["lat"]))
    lado = 1 if cercana["lat"] > mejor["lat"] else -1
    w = wps[mejor["i"]]
    p, q = w["pos"], wps[w["sig"]]["pos"]
    sp = (p[0] - t["c"][0]) * t["avance"][0] + (p[2] - t["c"][1]) * t["avance"][1]
    sq = (q[0] - t["c"][0]) * t["avance"][0] + (q[2] - t["c"][1]) * t["avance"][1]
    f = sp / (sp - sq) if sp != sq else 0.0
    x, y, z = (p[k] + (q[k] - p[k]) * f for k in range(3))
    bf = banda_fisica(col, x, y, z, t["eje"], alcance=30.0)
    borde, muro = (bf["hi"], bf["hueco_hi"]) if lado > 0 else (-bf["lo"], bf["hueco_lo"])
    otro = -bf["lo"] if lado > 0 else bf["hi"]
    if muro < MURO_MIN or borde + muro >= 30.0:
        return None
    # 🔴 The wall has to be BETWEEN the pit lane and the track. On the Roval the pit lane and the
    # track are continuous asphalt and the first wall is on the OTHER side of the track: the rule
    # stretched the pit exit to 31 m above the racing line ("touches the racing line at 3.2 m").
    # If the track comes before the end of the wall, there is no separation.
    if abs(cercana["lat"] - mejor["lat"]) < borde + muro:
        return None
    return {"lado": lado, "borde": borde, "muro": muro, "otro": otro, "lat": mejor["lat"]}


def _problemas_fisicos_boxes(col, wps, t):
    """With a wall between pit lane and track: the trigger covers the lane up to the wall and ends
    INSIDE the wall (it does not reach the track asphalt). Without a wall: nothing to say (the AIW rules)."""
    s = _separacion_boxes(col, wps, t)
    if s is None:
        return []
    L = t["largo"]
    # trigger ends measured from the pit lane, towards the track (+) and towards the other side
    hacia_pista = (L / 2 - s["lat"]) if s["lado"] > 0 else (L / 2 + s["lat"])
    al_otro = L - hacia_pista
    fuera = []
    if hacia_pista > s["borde"] + s["muro"] - 0.5:
        fuera.append(f"it crosses the wall and reaches the track's asphalt ({hacia_pista:.1f} m towards it; "
                     f"the wall goes from {s['borde']:.1f} to {s['borde'] + s['muro']:.1f} m)")
    if hacia_pista < min(s["borde"], CARRIL_BOXES) - 0.01 or al_otro < min(s["otro"], CARRIL_BOXES) - 0.01:
        fuera.append(f"it doesn't cover the pit lane's width ({hacia_pista:.1f} m towards the track, {al_otro:.1f} to the other side)")
    return fuera


def _puerta_fisica_boxes(col, wps, i, f=0.5):
    """Pit trigger on stretch i→next of the pit lane, ONLY if there is a wall to the track: from
    the middle of the wall to the lane on the other side. None if there is no wall (then the AIW rules)."""
    base = _puerta_en(wps, i, f, margen=0.0)
    base["nombre"] = "TRG_PITOUT"
    base["largo"] = 2 * CARRIL_BOXES
    s = _separacion_boxes(col, wps, base)
    if s is None:
        return None
    hacia = s["borde"] + s["muro"] / 2
    otro = min(s["otro"], CARRIL_BOXES)
    medio = s["lat"] + s["lado"] * (hacia - otro) / 2
    ex, ez = base["eje"]
    base.update(c=(base["c"][0] + ex * medio, base["c"][1] + ez * medio), largo=hacia + otro)
    return base


def evaluar(wps, t, col=None):
    """All of a trigger's problems: the AIW ones and, with the collision, the GROUND ones. For pit
    triggers with a wall between pit lane and track, overlapping the AIW band does not count (the ground rules)."""
    probs = _problemas(wps, t)
    if col is None:
        return probs
    if ESPERADO.get(t["nombre"]) != 0 and _separacion_boxes(col, wps, t) is not None:
        probs = [p for p in probs if not p.startswith("the track, at ")]
    return probs + problemas_fisicos(col, wps, t)


def _puerta_fisica(col, wps, i, f=0.5, holgura=2.0, sobra=3.0):
    """Perpendicular trigger on stretch i→next that covers its real asphalt (+`sobra` m) and stops
    `holgura` m short of any other stretch's asphalt. None if it does not fit."""
    base = _puerta_en(wps, i, f, margen=0.0)
    base["largo"] = 1.0
    bandas = _bandas_fisicas(col, wps, base)
    suyos = [x for x in bandas if abs(x[0]["lat"]) < 1.0]
    if not suyos:
        return None
    suyo = min(suyos, key=lambda x: abs(x[0]["lat"]))
    lo = max(suyo[1], -30.0) - sobra
    hi = min(suyo[2], 30.0) + sobra
    for c, olo, ohi in bandas:
        if c is suyo[0]:
            continue
        if olo >= suyo[2]:
            hi = min(hi, olo - holgura)
        elif ohi <= suyo[1]:
            lo = max(lo, ohi + holgura)
        else:
            return None                      # shares asphalt with another stretch: not here
    if lo > max(suyo[1], -30.0) - 1.0 or hi < min(suyo[2], 30.0) + 1.0:
        return None                          # not even 1 m to spare on some side
    medio = (lo + hi) / 2
    ex, ez = base["eje"]
    base.update(c=(base["c"][0] + ex * medio, base["c"][1] + ez * medio), largo=hi - lo)
    return base


def recolocar(ruta_aiw, ruta_trg, alcance_m=250.0, paso=2, col=None):
    """Moves the SPLITS and PIT triggers that have problems to the nearest point of their stretch
    where they do not. The finish line is NOT moved (it is the author's): if it fails, the gate says so.

    A split moved a few dozen metres only changes where the sectors are divided; a split that
    another stretch touches backwards is an unknown on every lap."""
    wps = leer_aiw_bandas(ruta_aiw)
    trgs = leer_disparadores(ruta_trg)
    txt = open(ruta_trg, encoding="utf-8", errors="ignore").read()
    bloques = list(re.finditer(r'<data class="ShapeDesc"[^>]*>.*?</data>', txt, re.S))
    hechos = []
    for b, t in zip(bloques, trgs):
        if t["nombre"] == "TRG_START" or not evaluar(wps, t, col):
            continue
        rama = ESPERADO[t["nombre"]]
        cs = [c for c in cruces(wps, t) if (c["rama"] == 0) == (rama == 0) and c["dentro"] > 0]
        if cs:
            origen = max(cs, key=lambda c: c["cubre"])
        else:
            # its own stretch does not even cross it (measured at Jarama): the pit exit fell on the
            # LAST point of the pit lane, where it already merges with the track. Start from the nearest point.
            i0 = min((i for i, w in enumerate(wps) if (w["rama"] == 0) == (rama == 0)),
                     key=lambda i: math.dist((wps[i]["pos"][0], wps[i]["pos"][2]), t["c"]))
            origen = {"i": i0, "d": wps[i0]["d"]}
        # walk along its branch forwards and backwards, alternating, up to the range
        adelante, atras, d_ad, d_at, cand = origen["i"], origen["i"], 0.0, 0.0, [(0.0, origen["i"])]
        prev = {j: i for i, w in enumerate(wps) for j in [w["sig"]] if w["rama"] == rama and 0 <= j < len(wps)}
        for _ in range(int(alcance_m)):
            s = wps[adelante]["sig"]
            if 0 <= s < len(wps) and wps[s]["rama"] == rama and d_ad < alcance_m:
                d_ad += math.dist(wps[adelante]["pos"], wps[s]["pos"]); adelante = s; cand.append((d_ad, s))
            a = prev.get(atras)
            if a is not None and d_at < alcance_m:
                d_at += math.dist(wps[a]["pos"], wps[atras]["pos"]); atras = a; cand.append((d_at, a))
        # pit triggers only INTO the pit lane: the entry forwards, the exit backwards
        if t["nombre"] == "TRG_PITIN":
            cand = [c for c in cand if wps[c[1]]["d"] >= wps[origen["i"]]["d"]]
        elif t["nombre"] == "TRG_PITOUT":
            cand = [c for c in cand if wps[c[1]]["d"] <= wps[origen["i"]]["d"]]
        for dist, i in sorted(cand):
            if not (0 <= wps[i]["sig"] < len(wps)) or wps[wps[i]["sig"]]["rama"] != wps[i]["rama"]:
                continue                      # the segment that already leaves its branch (pit lane → track)
            # finish line/splits: as long as possible (Reiza leaves 3.3 to 33 m to spare: a car
            # that runs wide has to cross it too) without getting close to another stretch
            nuevo = None
            if rama != 0 and col is not None:
                prueba = _puerta_fisica_boxes(col, wps, i)
                if prueba is not None:
                    prueba["nombre"] = t["nombre"]
                    if not evaluar(wps, prueba, col):
                        nuevo = prueba
            if rama == 0 and col is not None:
                # with the collision the real ground rules; the AIW only as a second opinion
                prueba = _puerta_fisica(col, wps, i)
                if prueba is not None:
                    prueba["nombre"] = t["nombre"]
                    if not evaluar(wps, prueba, col):
                        nuevo = prueba
                if nuevo is None:
                    continue
            for margen in (() if nuevo is not None else (12.0, 9.0, 6.0, 4.5, 3.5) if rama == 0 else (0.0,)):
                prueba = _puerta_en(wps, i, 0.5, margen=margen)
                if rama != 0:
                    prueba["largo"] = min(prueba["largo"], t["largo"])   # like the original: 12 m
                prueba["nombre"] = t["nombre"]
                if not evaluar(wps, prueba, col):
                    nuevo = prueba
                    break
            if nuevo is None:
                continue
            dx, dz = nuevo["avance"]
            bloque = b.group(0)
            for k, v in (("Relative Position", f"{nuevo['c'][0]:.6f};{nuevo['y']:.6f};{nuevo['c'][1]:.6f}"),
                         ("Relative Orientation", matriz(dx, dz)), ("Length", f"{nuevo['largo']:.6f}")):
                bloque = re.sub(rf'(<prop name="{re.escape(k)}" data=")[^"]*(")',
                                lambda m, v=v: m.group(1) + v + m.group(2), bloque, count=1)
            hechos.append((t["nombre"], b, bloque, f"{t['nombre']}: moved {dist:.0f} m "
                           f"({origen['d']:.0f} → {wps[i]['d']:.0f} m), length {nuevo['largo']:.0f} m"))
            break
        else:
            hechos.append((t["nombre"], None, None, f"{t['nombre']}: no clean spot within ±{alcance_m:.0f} m"))
    for _n, b, bloque, _txt in sorted((h for h in hechos if h[1]), key=lambda h: -h[1].start()):
        txt = txt[:b.start()] + bloque + txt[b.end():]
    open(ruta_trg, "w", encoding="utf-8").write(txt)
    return [h[3] for h in hechos]


if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "--auditar":
    for ruta_aiw, ruta_trg in zip(sys.argv[2::2], sys.argv[3::2]):
        mal = auditar(ruta_aiw, ruta_trg)
        print(("✅ " if not mal else "🔴 ") + ruta_trg)
        for n, p in mal:
            print(f"   {n}: {p}")
elif __name__ == "__main__":
    sys.exit(main(sys.argv))
