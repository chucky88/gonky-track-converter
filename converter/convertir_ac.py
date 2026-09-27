"""Converts an ASSETTO CORSA track to Automobilista 2 in one go, and does NOT deliver if something is wrong.

Usage:

    python3 convert_ac.py --folder <AC track folder> --layout <layout> --name <AMS2 id> [options]

    python3 convert_ac.py --folder ~/ac/tracks/my_track --layout layout_gp \\
                          --name mytrack --title "My Track" \\
                          --geo 40.6170,-3.5857,620,1 --pit-limiter 60

  --folder   the AC track folder (the one with the `.kn5` files and the `models_*.ini`)
  --layout   the layout subfolder (`layout_gp`, `oval`…); defaults to `layout_speedway`
  --name     the track id in AMS2: lowercase, no spaces or dots

Every other option (grid, AI, asphalt, lights, cameras, sound…) is listed by `--help` and described in
docs/OPTIONS.md. The original Spanish option names (`--carpeta`, `--trazado`…) still work as aliases.

How it works: a chain of steps (textures → Blender scene → package → images, lights, LiveTrack,
cameras, timing, AIW) followed by a battery of GATES. Each gate measures something that has already
broken silently at some point (a mirrored racing line, the grid far from the finish line, missing
ground under the racing line…). If a single one turns red, **the zip is not written**: it prints which
gate failed and why.

Whenever possible, the gates compare the export with a source INDEPENDENT of it in the AC track itself
(the `.kn5`, the `fast_lane.ai` racing line, the `ui_track.json`), not with something derived from the
same data: two things that come from the same place always agree.

The result is `<work folder>/<name>/<name>.zip`, with a CREDITS.txt at its root (original author +
tool; `--no-credits` removes it) and a REPORT.md next to it.
"""

import json
import math
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import cadena as C  # noqa: E402  (corre, blender and the shared gates)

import rutas as _R  # noqa: E402
TRABAJO = _R.TRABAJO


def _capas_ac(carpeta, trazado, nombre):
    """The layers of AC's multilayer asphalt (`capas_ac.py`), read from the textures already extracted
    into `work/<name>/tex`, so the mod's own asphalt is used instead of a generic one."""
    import ac_trazado as T
    import capas_ac as CA
    return CA.guardar(T.modelos(carpeta, trazado), os.path.join(TRABAJO, nombre, "tex"),
                      os.path.join(TRABAJO, nombre, "capas_ac.json"))


def _brillo_ac(carpeta, trazado, nombre):
    """{material: ksSpecular} from the layout's `.kn5` files, so the asphalt gloss is the ORIGINAL's
    (at Jarama, dirt with the road shader reflected like a mirror)."""
    import ac_trazado as T
    import kn5_read as K
    brillo = {}
    for f in T.modelos(carpeta, trazado):
        for m in K.leer(f)["materiales"]:
            if "ksSpecular" in m.props:
                brillo.setdefault(m.nombre, m.props["ksSpecular"])
    ruta = os.path.join(TRABAJO, nombre, "brillo_ac.json")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    json.dump(brillo, open(ruta, "w"), indent=1)
    return ruta


# ── the three gates that differ ──────────────────────────────────────────────────────
def puerta_geometria_ac(ctx):
    """Compares the imported meshes with those in the `.kn5`: a package can come out with a fraction
    of the geometry (51 of 207 meshes was measured) without any error."""
    import kn5_read as K
    piezas = [ctx["kn5"]] if isinstance(ctx["kn5"], str) else ctx["kn5"]
    # only the ones the author lets be drawn: the others go to collision, not to what is seen
    import re as _re
    marca = _re.compile(r"^AC_(START|PIT|TIME|HOTLAP_START)_", _re.I)
    declaradas = sum(1 for p in piezas for m in K.leer(p)["mallas"]
                     if m.indices and m.visible and m.dibuja)
    importadas = ctx.get("mallas", 0)
    return importadas >= declaradas, (f"{importadas} meshes imported of {declaradas} "
                                      f"in {len(piezas)} .kn5")


def puerta_trazada_ac(ctx):
    """🔴 A mirrored racing line sends the AI into the wall. It is compared AGAINST THE SOURCE ONE.

    An "external" yardstick (negative in corners, as on official ovals: Texas −4.02) does not work: it
    passed (−2.62) with the whole track MIRRORED. Without the mirror it is +2.62, which is correct:
    Assetto Corsa's AI drives at 62 % of the width in corners (upper half of the banking) while other
    AIs run low (7 %). Those are two driving styles; the yardstick measured how an AI drives, not
    whether the racing line was copied correctly.

    So the EXPORTED sign must match the ORIGINAL racing line's (`fast_lane.ai`) relative to the centre
    line, and the magnitude cannot be more than 3 m off. (+ = outwards, where `wp_perp` points.)
    """
    import aiw_read as A
    import ac_trazado as T
    t = ctx["trazado_ac"]
    tr = t["trazada"]
    # the ORIGINAL: the racing line's outward offset, in corners
    _ty, est_o, _u = A.curvas_adaptativo([A.Waypoint(pos=p) for p in tr[::4]])
    ks = [j * 4 for j, e in enumerate(est_o) if e != A.STATE_STRAIGHT]
    if ctx.get("central_asfalto"):
        # 🔴 Against the SAME centre line that gets exported. With `--ai-centre-asphalt` the
        # centre line comes from the racing asphalt, and measured against the old one (with apron) the
        # author's racing line "switched sides" without moving: +2.19 against −1.23. On the same
        # basis: original −1.25, exported −1.23.
        import statistics
        bc = T.bordes_carrera(t["colision"], tr, list(range(0, len(tr), 4)))
        mi = statistics.median(v[0] for v in bc.values())
        md = statistics.median(v[1] for v in bc.values())
        orig = sorted((min(bc[k][1], T.TOPE_ANCHO_CENTRAL * md) - min(bc[k][0], T.TOPE_ANCHO_CENTRAL * mi)) / -2.0
                      for k in ks)
    else:
        orig = sorted((t["bordes"][k][1] - t["bordes"][k][0]) / -2.0 for k in ks)
    # (bordes = (left, right, …); left is the inside on an anticlockwise oval, so
    #  outwards = (left − right) / 2)
    if not orig:
        return False, "no corners in the original racing line"
    o = orig[len(orig) // 2]
    mp = ctx["aiw_obj"].main_path
    _ty, est, _u = A.curvas_adaptativo(mp)
    vals = sorted(w.path[0] for w, e in zip(mp, est) if e != A.STATE_STRAIGHT and w.path)
    if not vals:
        return False, "no corner waypoints with a lateral racing line in the export"
    n = vals[len(vals) // 2]
    ok = (o * n > 0 or abs(o) < 0.5) and abs(o - n) < 3.0
    return ok, f"original {o:+.2f} · exported {n:+.2f} (in corners; + = outwards)"


def puerta_espacios_ac(ctx):
    """🔴 Collision MIRRORED relative to the track limits raises no error: the game loads and the fault
    only shows when driving.

    Comparing the BOUNDING BOXES of the `.gcl` and the `.csm` assumes they cover the same area. In AC
    they do not: the collision includes walls, infield and run-offs that stick out 1.6–2 m beyond the
    valid track, and the box gives a false red ("negated Z 2.03 m" with direct Z at 96 m, i.e. with the
    correct relation). Loosening the tolerance is how problems get hidden; this is STRICTER: it takes
    vertices of the track limits and checks that they fall ON the collision. With a mirror or an offset
    they would hang in the air.

    The wrong relation (direct Z) is measured too: if both came out fine, the test would not be telling
    anything apart.
    """
    import itertools
    from collections import defaultdict

    import gcl_read as GCL

    tris, vs = [], []
    for ln in open(ctx["obj"], encoding="utf-8", errors="ignore"):
        if ln.startswith("v "):
            _, x, y, z = ln.split()[:4]
            vs.append((float(x), float(y), float(z)))
        elif ln.startswith("f "):
            idx = [int(q.split("/")[0]) - 1 for q in ln.split()[1:]]
            for k in range(1, len(idx) - 1):
                tris.append((vs[idx[0]], vs[idx[k]], vs[idx[k + 1]]))
    CEL = 8.0
    rej = defaultdict(list)
    for t in tris:
        xs = [p[0] for p in t]
        zs = [p[2] for p in t]
        for cx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
            for cz in range(int(min(zs) // CEL), int(max(zs) // CEL) + 1):
                rej[(cx, cz)].append(t)

    def altura(x, z, y_ref):
        mejor = None
        for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in rej.get((int(x // CEL), int(z // CEL)), ()):
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

    muestras = [v for t in itertools.islice(GCL.triangulos(ctx["gcl"]), 0, None, 7) for v in t[:3]]
    def encaje(signo):
        ok = 0
        for gx, gy, gz in muestras:
            h = altura(gx, signo * gz, gy)
            if h is not None and abs(h - gy) < 0.30:
                ok += 1
        return ok / len(muestras) if muestras else 0.0
    negada, directa = encaje(-1), encaje(+1)
    bien = negada > 0.95 and directa < 0.5
    return bien, (f"{100 * negada:.1f} % of the gcl vertices fall on the collision with Z "
                  f"negated · {100 * directa:.1f} % with it direct ({len(muestras):,} points)")


def puerta_cronometraje_ac(ctx):
    """🔴 Without the track's own triggers there are no timed laps, and the pit triggers must NOT touch
    the racing line (the AI pitted and laps did not count)."""
    import re
    import generar_triggers as G

    ruta = os.path.join(ctx["pack"], "Tracks", ctx["nombre"], "physics", "triggers.xml")
    if not os.path.exists(ruta):
        return False, "there is no triggers.xml"
    txt = open(ruta, encoding="utf-8", errors="ignore").read()
    tr = [w.pos for w in ctx["aiw_obj"].main_path]
    inv = {v: k for k, v in G.CRC.items()}
    mal, vistos = [], set()

    def cruza(c, n, largo):
        """Does any stretch of the racing line cross the gate's plane within its width?"""
        nx, nz = n
        px, pz = -nz, nx                         # along the gate
        for i in range(len(tr)):
            a, b = tr[i - 1], tr[i]
            da = (a[0] - c[0]) * nx + (a[2] - c[2]) * nz
            db = (b[0] - c[0]) * nx + (b[2] - c[2]) * nz
            if da * db > 0 or da == db:
                continue
            t = da / (da - db)
            x, z = a[0] + (b[0] - a[0]) * t, a[2] + (b[2] - a[2]) * t
            if abs((x - c[0]) * px + (z - c[2]) * pz) <= largo / 2.0:
                return True
        return False

    for m in re.finditer(r'<data class="ShapeDesc"[^>]*>(.*?)</data>', txt, re.S):
        b = m.group(1)
        crc = int(re.search(r'name="Material CRC" data="(\d+)"', b).group(1))
        nombre = inv.get(crc, str(crc))
        vistos.add(nombre)
        pos = [float(x) for x in re.search(r'name="Relative Position" data="([^"]*)"', b).group(1).split(";")]
        largo = float(re.search(r'name="Length" data="([\d.]+)"', b).group(1))
        ori = [float(x) for x in re.search(r'name="Relative Orientation" data="([^"]*)"', b).group(1).split(";")]
        n = (ori[0], ori[2])                     # `matriz(dx, dz)` starts with (dx, 0, dz)
        if nombre in ("TRG_START", "TRG_CHECKPOINT1", "TRG_CHECKPOINT2"):
            if not cruza(pos, n, largo):
                mal.append(f"the racing line doesn't cross {nombre}")
        else:
            d = min(math.hypot(q[0] - pos[0], q[2] - pos[2]) for q in tr)
            if d < largo / 2.0:
                mal.append(f"🔴 {nombre} touches the racing line (at {d:.1f} m)")
    faltan = set(G.CRC) - vistos
    if faltan:
        mal.append(f"faltan {sorted(faltan)}")
    # The above measures against the racing LINE; this, against the asphalt BAND (AIW) and
    # against the real ground, with the thresholds of the official tracks
    col = (ctx.get("trazado_ac") or {}).get("colision")
    mal += [f"{n}: {p}" for n, p in G.auditar(ctx["aiw_out"], ruta, col=col)]
    return (not mal), ("5 triggers: each is crossed by its stretch across the whole asphalt and no other stretch "
                       "touches it (AIW and ground)" if not mal else " · ".join(mal))


def puerta_sentido_ac(ctx):
    """🔴 The track can come out MIRRORED: in AMS2 it is driven the opposite way to the real one.

    The other gates pass because a mirrored world is consistent with itself. This one compares the
    EXPORTED AIW's direction with what the author declares in `ui_track.json` ("counter clockwise"), an
    independent source — which is why it works. Comparing with something derived from the same AIW
    would measure nothing: two things that come from the same place always agree.
    """
    import aiw_read as A
    try:
        run = str(json.load(open(ctx["ui"], encoding="utf-8-sig")).get("run", "")).lower()
    except (OSError, ValueError):
        return True, "the track declares no direction: nothing to compare"
    if not run:
        return True, "the track declares no direction: nothing to compare"
    declarado_horario = "counter" not in run and "anti" not in run
    derecha = A.gira_a_derechas(ctx["aiw_obj"].main_path)
    ok = derecha == declarado_horario
    return ok, (f"the author declares «{run}» and the AIW turns "
                f"{'right (clockwise)' if derecha else 'left (anticlockwise)'}")


def puerta_suelo_fuera_ac(ctx):
    """🔴 Going off track, the car fell into the void.

    The collision only had the physics `.kn5` (`phyoval.kn5`), and the grass (`3GRASS`) is in the main
    `.kn5`. It probes 3 m beyond the edge, ONLY on the sides without a wall (where you can go off), and
    requires collision underneath.
    """
    import ac_trazado as T
    tris, vs = [], []
    for ln in open(ctx["obj"], encoding="utf-8", errors="ignore"):
        if ln.startswith("v "):
            _, x, y, z = ln.split()[:4]
            vs.append((float(x), float(y), float(-float(z))))   # the OBJ has Z negated
        elif ln.startswith("f "):
            idx = [int(q.split("/")[0]) - 1 for q in ln.split()[1:]]
            for k in range(1, len(idx) - 1):
                tris.append((vs[idx[0]], vs[idx[k]], vs[idx[k + 1]]))
    from collections import defaultdict
    CEL = 8.0
    rej = defaultdict(list)
    for t in tris:
        xs = [p[0] for p in t]; zs = [p[2] for p in t]
        for cx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
            for cz in range(int(min(zs) // CEL), int(max(zs) // CEL) + 1):
                rej[(cx, cz)].append(t)
    def hay(x, z):
        for (ax, _ay, az), (bx, _by, bz), (cx, _cy, cz) in rej.get((int(x // CEL), int(z // CEL)), ()):
            d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(d) < 1e-9:
                continue
            w1 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d
            w2 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d
            if min(w1, w2, 1 - w1 - w2) >= -1e-6:
                return True
        return False
    t = ctx["trazado_ac"]
    tr = t["trazada"]
    probadas = sin = 0
    for k in range(0, len(tr), 5):
        p, q = tr[k], tr[(k + 1) % len(tr)]
        dx, dz = q[0] - p[0], q[2] - p[2]
        L = math.hypot(dx, dz) or 1.0
        ix, iz = -dz / L, dx / L
        bi, bd, mi, md = t["bordes"][k]
        for borde, muro, sx in ((bi, mi, 1), (bd, md, -1)):
            if muro is not None:
                continue            # there is a wall: you cannot go off there
            probadas += 1
            s_ = borde + 3.0
            if not hay(p[0] + sx * ix * s_, p[2] + sx * iz * s_):
                sin += 1
    if not probadas:
        return True, "wall all around: nowhere to go off"
    return sin <= probadas * 0.02, (f"{probadas - sin} of {probadas} points 3 m beyond the edge "
                                    f"(where there's no wall) have ground")


def puerta_suelo_bajo_trazada_ac(ctx):
    """🔴🔴 Ground in the DELIVERED physics under the racing line and the pit lane, every 0.5 m.

    Measured at Jarama: the car sank into the asphalt and flipped. The LINE surface was not in AC's
    built-in table, and the painted-line area at 2,512–2,534 m was left OUT of the physics: the racing
    line with nothing under it, cars sunk and flipped, one stuck since lap 1. No gate saw it: the
    "ground" one looked 3 m OUTSIDE the edge, and the ones that measure the track used the same surface
    table that had left the line out — the yardstick had the same flaw as what it measured. This one
    reads the OBJ that gets cooked, with no table, and requires ground within 2 m of the racing line's
    height (a bridge does not count)."""
    from collections import defaultdict
    vs, rej, CEL = [], defaultdict(list), 8.0
    for ln in open(ctx["obj"], encoding="utf-8", errors="ignore"):
        if ln.startswith("v "):
            _, x, y, z = ln.split()[:4]
            vs.append((float(x), float(y), -float(z)))       # the OBJ has Z negated
        elif ln.startswith("f "):
            idx = [int(q.split("/")[0]) - 1 for q in ln.split()[1:]]
            for k in range(1, len(idx) - 1):
                tri = (vs[idx[0]], vs[idx[k]], vs[idx[k + 1]])
                xs = [p[0] for p in tri]; zs = [p[2] for p in tri]
                for cx in range(int(min(xs) // CEL), int(max(xs) // CEL) + 1):
                    for cz in range(int(min(zs) // CEL), int(max(zs) // CEL) + 1):
                        rej[(cx, cz)].append(tri)

    def suelo(x, y, z):
        for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in rej.get((int(x // CEL), int(z // CEL)), ()):
            d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(d) < 1e-9:
                continue
            w1 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d
            w2 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d
            if min(w1, w2, 1 - w1 - w2) >= -1e-6 and abs(w1 * ay + w2 * by + (1 - w1 - w2) * cy - y) < 2.0:
                return True
        return False

    def recorrer(linea, cerrada):
        huecos, n, acc, zona = [], 0, 0.0, None
        tramos = range(len(linea) if cerrada else len(linea) - 1)
        for i in tramos:
            a, b = linea[i], linea[(i + 1) % len(linea)]
            dd = math.dist((a[0], a[2]), (b[0], b[2]))
            pasos = max(1, int(dd / 0.5))
            for k in range(pasos):
                f = k / pasos
                x, y, z = (a[j] + (b[j] - a[j]) * f for j in range(3))
                n += 1
                if not suelo(x, y, z):
                    if zona and acc + dd * f - zona[1] < 2.0:
                        zona[1] = acc + dd * f
                    else:
                        zona = [acc + dd * f, acc + dd * f]
                        huecos.append(zona)
            acc += dd
        return n, huecos

    t = ctx["trazado_ac"]
    n1, h1 = recorrer(t["trazada"], True)
    n2, h2 = recorrer(t.get("boxes_linea") or [], False) if t.get("boxes_linea") else (0, [])
    txt = f"racing line {n1} points, {len(h1)} gaps · pit lane {n2} points, {len(h2)} gaps"
    if h1 or h2:
        txt += " · " + ", ".join(f"{a:.0f}-{b:.0f} m" for a, b in (h1 + h2)[:8])
    return not (h1 or h2), txt


def puerta_livetrack_ac(ctx):
    """🔴 The LiveTrack `.mrdf` must be the TRACK's own: every package used to carry Meadowdale's (the
    template's). And the racing line must fall inside the rubber band."""
    import hashlib
    import mrdf_read as MR
    import ac_trazado as T
    ruta = os.path.join(ctx["pack"], "Tracks", "_data", "livetrack", f"{ctx['nombre']}.mrdf")
    ejemplo = os.path.join(C.EJEMPLO, "Automobilista 2", "Tracks", "_data", "livetrack", "Meadowdale.mrdf")
    if not os.path.exists(ruta):
        return False, "there is no .mrdf"
    md5 = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()   # noqa: E731
    if os.path.exists(ejemplo) and md5(ruta) == md5(ejemplo):
        return False, "it's the EXAMPLE's .mrdf (Meadowdale)"
    r = MR.leer(ruta, celdas=True)
    x0, y0, _x1, _y1 = r["limites"]
    c = r["celda"]
    d = {(gx, gy): fl for gx, gy, _f, _a, _g, fl in r["lista"]}
    tr = ctx["trazado_ac"]["trazada"]
    en = sum(1 for p in tr if d.get((int(round((p[0] - x0) / c)), int(round((p[2] - y0) / c)))) == 3)
    return en >= 0.95 * len(tr), f"{r['celdas']} cells · racing line inside the rubber band: {en}/{len(tr)}"


QUIEBRO_MAX = 2.0


def quiebros_de_central(ruta_aiw):
    """Per waypoint, how far its turn departs from the median of its 6 neighbours (degrees)."""
    import statistics
    import aiw_read as A
    m = A.parse(ruta_aiw).main_path
    n = len(m)
    g = []
    for i in range(n):
        a0, a1, a2 = m[i - 1].pos, m[i].pos, m[(i + 1) % n].pos
        v1, v2 = (a1[0] - a0[0], a1[2] - a0[2]), (a2[0] - a1[0], a2[2] - a1[2])
        g.append(math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1])))
    return [abs(g[i] - statistics.median([g[(i + d) % n] for d in (-3, -2, -1, 1, 2, 3)])) for i in range(n)]


def _central_muestreada(tr, paso):
    """The author's racing line resampled every `paso` m (the exported AIW's step) so it's measured the same way."""
    acum = [0.0]
    for i in range(1, len(tr)):
        acum.append(acum[-1] + math.dist(tr[i], tr[i - 1]))
    fuera, t, k = [], 0.0, 0
    while t < acum[-1]:
        while acum[k + 1] < t:
            k += 1
        f = (t - acum[k]) / ((acum[k + 1] - acum[k]) or 1.0)
        fuera.append(tuple(tr[k][c] + (tr[k + 1][c] - tr[k][c]) * f for c in range(3)))
        t += paso
    return fuera


def _quiebros_de_puntos(pts):
    import statistics
    n = len(pts)
    g = []
    for i in range(n):
        a0, a1, a2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        v1, v2 = (a1[0] - a0[0], a1[2] - a0[2]), (a2[0] - a1[0], a2[2] - a1[2])
        g.append(math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1])))
    return [abs(g[i] - statistics.median([g[(i + d) % n] for d in (-3, -2, -1, 1, 2, 3)])) for i in range(n)]


MARGEN_SOBRE_EL_AUTOR = 1.0


def puerta_quiebros_ac(ctx):
    """🔴 The EXPORTED AIW centre line cannot have kinks: a 9° turn at one waypoint in the middle of a
    2°/waypoint corner is, to the AI, a hairpin — and it brakes (measured: the AI braked hard in a
    corner; the centre line had 25 kinks > 2°, the worst 11.9°). Red only with `--ai-centre-asphalt`,
    which is the fix; without it, it warns."""
    q = quiebros_de_central(ctx["aiw_out"])
    # 🔴 Against the AUTHOR's racing line, not a fixed threshold (measured on the Roval): in a chicane
    # or a hairpin the turn really changes within a few metres and the author has the same "kinks"
    # (Roval: author 5 > 2°, worst 2.9°; export 6, worst 3.1°, in the same places). A kink belongs to
    # the CONVERSION if it exceeds 2° and the author's there + 1°.
    import aiw_read as A
    mp = A.parse(ctx["aiw_out"]).main_path
    paso = sum(math.dist(mp[i].pos, mp[i - 1].pos) for i in range(1, len(mp))) / max(1, len(mp) - 1)
    rs = _central_muestreada(ctx["trazado_ac"]["trazada"], paso)
    qa = _quiebros_de_puntos(rs)

    def del_autor(i):
        p = mp[i].pos
        j = min(range(len(rs)), key=lambda k: (rs[k][0] - p[0]) ** 2 + (rs[k][2] - p[2]) ** 2)
        return max(qa[(j + d) % len(rs)] for d in range(-2, 3))

    brutos = [i for i, x in enumerate(q) if x > QUIEBRO_MAX]
    malos = [i for i in brutos if q[i] > del_autor(i) + MARGEN_SOBRE_EL_AUTOR]
    texto = (f"{len(malos)} waypoints with a kink > {QUIEBRO_MAX:.0f}° and > the author's + "
             f"{MARGEN_SOBRE_EL_AUTOR:.0f}° (worst {max(q):.1f}°; {len(brutos) - len(malos)} come from the "
             f"track's shape)")
    if not ctx.get("central_asfalto"):
        return True, ("⚠️ " if malos else "") + texto + " — without --ai-centre-asphalt"
    return not malos, texto


def puerta_ancho_ia_ac(ctx):
    """🔴 The track width the AI sees (`wp_width`, both sides) cannot exceed the racing asphalt plus its
    cap: with the apron included, Charlotte gave a 23.3 m median and up to 46.7, and the AI looked for
    alternative lines on the apron. Daytona (official): 11.2 m, asphalt only. Red with `--asphalt-width`."""
    import statistics
    import aiw_read as A
    import ac_trazado as T
    t = ctx["trazado_ac"]
    bc = T.bordes_carrera(t["colision"], t["trazada"], list(range(0, len(t["trazada"]), 4)))
    asf = statistics.median(v[0] for v in bc.values()) + statistics.median(v[1] for v in bc.values())
    tot = [w.width[0] + w.width[1] for w in ctx["aiw_obj"].main_path]
    med, mx = statistics.median(tot), max(tot)
    ok = med <= 1.1 * asf and mx <= T.TOPE_ANCHO_CENTRAL * asf + 1.0
    texto = f"median {med:.1f} m, max {mx:.1f} · racing asphalt {asf:.1f} m"
    if not ctx.get("ancho_asfalto"):
        return True, ("" if ok else "⚠️ ") + texto + " — without --asphalt-width"
    return ok, texto


SALTO_COLUMNA_M = 2.0      # m off the straight line joining the slots in front and behind in its column


def puerta_parrilla_en_meta_ac(ctx):
    """🔴 Pole must be JUST BEFORE the finish line: the game does not count the lap until the line is
    crossed, and with the grid ~1,000 m away (the AC mod's) the order was scrambled for the whole first
    lap (measured in a race). Red with `--grid-at-finish`."""
    import math
    import re
    import aiw_read as A
    m = ctx["aiw_obj"].main_path
    d = [0.0]
    for p, q in zip(m, m[1:]):
        d.append(d[-1] + math.dist(p.pos, q.pos))
    vuelta = d[-1] + math.dist(m[-1].pos, m[0].pos)
    texto = open(ctx["aiw_out"], encoding="latin-1").read()
    grid = texto[texto.index("[GRID]"):texto.index("[ROLLING START]")]
    ps = [tuple(map(float, x)) for x in re.findall(r"^Pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)", grid, re.M)]
    antes = [vuelta - d[min(range(len(m)), key=lambda i: (m[i].pos[0] - p[0]) ** 2 + (m[i].pos[2] - p[2]) ** 2)]
             for p in ps]
    antes = [a if a < vuelta - 1 else 0.0 for a in antes]
    ok = bool(antes) and 3.0 <= antes[0] <= 60.0 and max(antes) < 0.25 * vuelta
    texto = f"pole {antes[0]:.0f} m before the finish line · last slot at {max(antes):.0f} m"
    # 🔴 The FORMATION. Measured at Charlotte: slot 11 started 11.4 m inwards, off the racing surface,
    # with this gate green, because it only looked at the DISTANCE to the finish line. Measuring it
    # against the RACING LINE does not work either: on the Roval the line moves 25 m away through the
    # chicane while the grid runs straight along the oval, and it went red with a good grid. It checks
    # that each COLUMN is straight: every slot against the line joining the ones in front and behind (i±2).
    def fuera_de_recta(a, p, b):
        dx, dz = b[0] - a[0], b[2] - a[2]
        L = math.hypot(dx, dz) or 1.0
        return abs((p[0] - a[0]) * dz - (p[2] - a[2]) * dx) / L
    saltos = [(j + 1, fuera_de_recta(ps[j - 2], ps[j], ps[j + 2])) for j in range(2, len(ps) - 2)]
    malos = [(j, round(x, 1)) for j, x in saltos if x > SALTO_COLUMNA_M]
    if malos:
        ok = False
    texto += (f" · formation: a slot sticks out at most {max((x for _, x in saltos), default=0):.1f} m from its column's line"
              + (f" · 🔴 out of their column: {malos}" if malos else ""))
    if not ctx.get("parrilla_en_meta"):
        return True, ("" if ok else "⚠️ ") + texto + " — without --grid-at-finish"
    return ok, texto


APRON_EN_LIMITES_MIN = 80.0


def puerta_apron_en_limites_ac(ctx):
    """🔴 The apron must stay INSIDE the track limits (`.gcl`): when the apron was removed from the AI
    width, the `.gcl` cut (which used that width) kept only 68 % of the apron inside, against 86.9 %
    before. Measured on the exported `.gcl`."""
    import limites_apron as L
    r = L.cobertura(ctx["gcl"], ctx["trazado_ac"]["colision"], [w.pos for w in ctx["aiw_obj"].main_path])
    n, pct = r["pct"]["APRON"]
    na, pa = r["pct"]["ROAD"]
    # a track WITHOUT an apron (Jarama) has nothing to measure here
    if not ctx["trazado_ac"]["colision"].cuenta.get("APRON"):
        return True, f"the track has no apron · asphalt inside the limits {pa:.1f} %"
    return pct >= APRON_EN_LIMITES_MIN, f"apron inside the limits {pct:.1f} % ({n} triangles) · asphalt {pa:.1f} %"


def puerta_distancias_boxes_ac(ctx):
    """🔴 No pit or grid point with its lap distance at ZERO: to the game it would be at the finish line
    and it counts extra laps. Red with `--pit-distances`."""
    import aiw_puntuar as AP
    ok, texto = AP.comprobar(ctx["aiw_out"])
    if not ctx.get("distancias_boxes"):
        return True, ("" if ok else "⚠️ ") + texto + " — without --pit-distances"
    return ok, texto


def puerta_semaforos_ac(ctx):
    """Start lights (`--start-lights`): each lamp's ID must REACH the exported `.meb` — it is the only
    thing the engine looks at — and the materials must be the generated ones."""
    if not ctx.get("semaforos"):
        return True, "not requested (--start-lights)"
    import generar_semaforos as GS
    return GS.comprobar(ctx["pack"], ctx["nombre"])


def puerta_camaras_tv_ac(ctx):
    """📺 With `--tv-cameras`: each of the 4 broadcast groups covers the lap and the pit lane (≥ 98 %),
    and no camera is left without zoom. Measured on the written XML."""
    if not ctx.get("camaras_tv"):
        return True, "not requested (--tv-cameras)"
    import camaras_tv as CT
    return CT.comprobar(os.path.join(ctx["pack"], "cameras", f"{ctx['nombre']}.xml"), ctx["aiw_out"])


def puerta_pancartas_ac(ctx):
    """Own banners (`--banners <json>`): each material generated in the package, opaque and
    pointing to its DDS, and the DDS inside. Measured on what was exported."""
    if not ctx.get("pancartas"):
        return True, "not requested (--banners)"
    import pancartas as PC
    return PC.comprobar(ctx["pack"], ctx["nombre"], PC.leer(ctx["pancartas"]),
                        "\n".join(ctx.get("salidas_blender", [])))


def puerta_calle_boxes_ac(ctx):
    """🔴 The pit lane cannot be half a lap: AC's `pit_lane.ai` records the WHOLE lap (Charlotte: 2,186 m
    on a 2,343 m lap) and that is how it came out, with the AI entering the pits and staying "in the
    pits" for almost a lap. Mid-Ohio (official): its pit lane is 16 % of the lap. Cap: 70 % (Charlotte's
    pit exit runs along the apron of turns 1 and 2)."""
    import aiw_read as A

    a = A.parse(ctx["aiw_out"])
    def largo(ps):
        return sum(math.dist(ps[i], ps[i - 1]) for i in range(1, len(ps)))
    vuelta = largo([w.pos for w in a.main_path] + [a.main_path[0].pos])
    boxes = largo([w.pos for w in a.pit_path_ordered()]) if a.pit_waypoints else 0.0
    if not boxes:
        return False, "there is no pit path"
    frac = boxes / vuelta
    return frac <= 0.70, f"{boxes:.0f} m of pit lane for a {vuelta:.0f} m lap ({frac:.0%})"


def puerta_peralte_ac(ctx):
    """🔴🔴 OMTT flattens `wp_perp`: the AI braked from 250 to 140 on a 24° oval.

    The independent yardstick in AC is the `camber` the author's own AI carries in block 2 of
    `fast_lane.ai` (radians). Measured on Mountain Peak: 22.5° in corners, 5.1° on straights.
    """
    import aiw_read as A
    fl = ctx["trazado_ac"].get("extra") or []
    tr = ctx["trazado_ac"]["trazada"]
    if not fl:
        return True, "the AC racing line carries no camber: nothing to compare"
    _t, est, _u = A.curvas_adaptativo([A.Waypoint(pos=p) for p in tr[::4]])
    cc = sorted(abs(math.degrees(fl[j * 4][7])) for j, e in enumerate(est) if e != A.STATE_STRAIGHT)
    rr = sorted(abs(math.degrees(fl[j * 4][7])) for j, e in enumerate(est) if e == A.STATE_STRAIGHT)
    oc, orr = cc[len(cc) // 2], rr[len(rr) // 2]
    nc, nr = C._peralte(A.parse(ctx["aiw_out"]))
    # 🔴 POINT BY POINT and signed (measured on the Roval). The medians above compare AC's camber in
    # ABSOLUTE VALUE with the exported one SIGNED: on an oval it makes no difference (everything slopes
    # inwards), but on the Roval's straights the crown falls both ways and the gate went red
    # (straights +1.3° vs 4.9°) with a real median error of 0.25°.
    mp = A.parse(ctx["aiw_out"]).main_path
    err, nuestro_abs, suyo_abs = [], [], []
    for w in mp[::3]:
        j = min(range(0, len(tr), 2), key=lambda k: (tr[k][0] - w.pos[0]) ** 2 + (tr[k][2] - w.pos[2]) ** 2)
        nn = math.sqrt(sum(x * x for x in w.perp)) or 1.0
        nuestro = math.degrees(math.asin(max(-1.0, min(1.0, w.perp[1] / nn))))
        err.append(abs(nuestro - math.degrees(fl[j][7])))
        nuestro_abs.append(abs(nuestro))
        suyo_abs.append(abs(math.degrees(fl[j][7])))
    err.sort()
    med = err[len(err) // 2]
    # 🔴 The second condition is absolute against absolute. Comparing the SIGNED median in corners
    # (−0.2°) with AC's in ABSOLUTE VALUE (2.4°) went red on a flat track with corners sloping both
    # ways (Jarama), with a point-by-point error of 0.72°.
    mediana = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
    ok = med < PERALTE_ERROR_MEDIANO_MAX and abs(mediana(nuestro_abs) - mediana(suyo_abs)) < 2.5
    return ok, (f"point-by-point error: median {med:.2f}°, p90 {err[int(len(err) * 0.9)]:.1f}° · "
                f"corners {nc:+.1f}° (AC camber {oc:.1f}°) · straights {nr:+.1f}° (|camber| {orr:.1f}°)")


PERALTE_ERROR_MEDIANO_MAX = 1.0


PUERTAS_AC = [
    ("geometry", puerta_geometria_ac),
    ("TRD identity", C.puerta_identidad),
    ("pit limiter", C.puerta_limite_boxes),
    ("start height", C.puerta_altura_salida),
    ("grid ≤ 32", C.puerta_parrilla),
    ("grid heading", C.puerta_rumbo),
    ("direction of travel", puerta_sentido_ac),
    ("racing line sign", puerta_trazada_ac),
    ("banking in the AIW", puerta_peralte_ac),
    ("ground faces up", C.puerta_suelo),
    ("ground off the track", puerta_suelo_fuera_ac),
    ("gcl ↔ csm", puerta_espacios_ac),
    ("the track is in the gcl", C.puerta_suelo_en_el_gcl),
    ("textures both ways", C.puerta_texturas),
    ("UI images", C.puerta_interfaz),
    ("grey ground layers", C.puerta_moduladores),
    ("lights not empty", C.puerta_luces),
    ("timing", puerta_cronometraje_ac),
    ("ground under the racing line", puerta_suelo_bajo_trazada_ac),
    ("pit lane", puerta_calle_boxes_ac),
    ("own LiveTrack", puerta_livetrack_ac),
    ("start lights", puerta_semaforos_ac),
    ("TV cameras", puerta_camaras_tv_ac),
    ("banners", puerta_pancartas_ac),
    ("centre line without kinks", puerta_quiebros_ac),
    ("pit distances", puerta_distancias_boxes_ac),
    ("AI width", puerta_ancho_ia_ac),
    ("apron within the limits", puerta_apron_en_limites_ac),
    ("grid at the finish", puerta_parrilla_en_meta_ac),
    ("nothing from the engine", C.puerta_globales),
    ("inherited from the example", C.puerta_heredados),
]


def main(argv):
    import opciones as OP
    if "--help" in argv or "-h" in argv:
        print(OP.ayuda())
        return 0
    argv = OP.normalizar(argv)              # English names → internal ones (`--folder` → `--carpeta`…)
    malas = OP.desconocidas(argv)
    if malas:
        # 🔴 every option is read with `"--x" in argv`: a typo or a retired option used to be ignored silently
        print(f"🔴 options that don't exist: {' '.join(malas)}   (python3 convert_ac.py --help)")
        return 2
    # 🔴 every step runs with `converter/` as its working folder: a relative path (`--photo my.jpg`,
    # `--folder ../my_track`) must become absolute here, where it still means what the user typed
    for k in ("--carpeta", "--foto", "--texturas"):
        if k in argv[:-1]:
            i = argv.index(k) + 1
            argv[i] = os.path.abspath(os.path.expanduser(argv[i]))

    def arg(k, defecto=None):
        return argv[argv.index(k) + 1] if k in argv else defecto

    carpeta = arg("--carpeta")
    if not carpeta:
        print(OP.ayuda())
        return 2
    trazado = arg("--trazado", "layout_speedway")
    nombre = arg("--nombre", os.path.basename(os.path.normpath(carpeta)).lower()).lower()
    w = os.path.join(TRABAJO, nombre)
    os.makedirs(w, exist_ok=True)
    tex = os.path.join(w, "tex")

    ctx = {"nombre": nombre, "pack": os.path.join(w, "limpio"),
           "obj": os.path.join(w, f"fisica-{nombre}", f"{nombre}_physics.obj")}
    ctx["aiw_out"] = os.path.join(ctx["pack"], "Tracks", "_data", "aiw", f"{nombre}.aiw")
    ctx["gcl"] = os.path.join(ctx["pack"], "Tracks", nombre, "track_cut", f"{nombre}.gcl")
    sup = os.path.join(carpeta, trazado, "data", "surfaces.ini")
    ui = os.path.join(carpeta, "ui", trazado, "ui_track.json")

    print(f"══ {os.path.basename(os.path.normpath(carpeta))} / {trazado} → {nombre} ══")

    # 0) the textures, out of the .kn5 files (once) — from ALL the layout's pieces
    import ac_trazado as T
    ctx["kn5"] = T.modelos(carpeta, trazado)
    if not os.path.isdir(tex) or not os.listdir(tex):
        for pieza in ctx["kn5"]:
            rc, s = C.corre([sys.executable, "kn5_read.py", pieza, "--volcar", tex])
            print(f"   textures from {os.path.basename(pieza)}: "
                  f"{s.strip().splitlines()[0] if s.strip() else rc}")

    blend = os.path.join(w, f"{nombre}.blend")
    pasos = [
        ("Blender scene", lambda: C.blender(
            "kn5_to_blender.py", "--carpeta", carpeta, "--trazado", trazado, "--tex", tex,
            *(["--semaforos", "1"] if "--semaforos" in argv else []),
            *(["--central-asfalto", "1"] if "--central-asfalto" in argv else []),
            *(["--ancho-asfalto", "1"] if "--ancho-asfalto" in argv else []),
            *(["--parrilla-en-meta", "1"] if "--parrilla-en-meta" in argv else []),
            *(["--parrilla-de", arg("--parrilla-de")] if arg("--parrilla-de") else []),
            *(["--pancartas", os.path.abspath(arg("--pancartas"))] if arg("--pancartas") else []),
            "--save", blend)),
        ("package", lambda: C.blender(
            "construir_paquete.py", "--blend", blend, "--nombre", nombre, "--salida", ctx["pack"],
            "--dds", tex, "--superficies", sup, "--ui", ui,
            *(["--geo", arg("--geo")] if arg("--geo") else []),
            *(["--titulo", arg("--titulo")] if arg("--titulo") else []),
            *(["--limite-boxes", arg("--limite-boxes")] if arg("--limite-boxes") else []),
            *(["--fecha", arg("--fecha")] if arg("--fecha") else []),
            *(["--max-ia", arg("--max-ia")] if arg("--max-ia") else []),
            *(["--curvas", arg("--curvas")] if arg("--curvas") else []),
            *(["--grupo", arg("--grupo")] if arg("--grupo") else []),
            *(["--variante", arg("--variante")] if arg("--variante") else []),
            *(["--orden", arg("--orden")] if arg("--orden") else []),
            *(["--ambiente", arg("--ambiente")] if arg("--ambiente") else []),
            *(["--ovalo", "1"] if "--ovalo" in argv else []),
            *(["--vallas-translucidas", "1"] if "--vallas-translucidas" in argv else []),
            *(["--relieve-asfalto", "1"] if "--relieve-asfalto" in argv else []),
            *(["--fresnel-asfalto", arg("--fresnel-asfalto")] if arg("--fresnel-asfalto") else []),
            *(["--brillo-asfalto", _brillo_ac(carpeta, trazado, nombre)] if "--brillo-asfalto" in argv else []),
            *(["--capas-ac", _capas_ac(carpeta, trazado, nombre)] if "--capas-ac" in argv else []),
            *(["--brillos-nocturnos", arg("--brillos-nocturnos"),
               "--config-csp", os.path.join(carpeta, "extension", "ext_config.ini")] if arg("--brillos-nocturnos") else []),
            *(["--publicidad", _publicidad(arg("--publicidad"))] if arg("--publicidad") else []),
            *(["--texturas", arg("--texturas")] if arg("--texturas") else []),
            *(["--familias-cc0", arg("--familias-cc0")] if arg("--familias-cc0") else []))),
    ]
    for etiqueta, fn in pasos:
        rc, salida = fn()
        ctx.setdefault("salidas_blender", []).append(salida)
        for ln in salida.splitlines():
            if any(k in ln for k in ("🔴", "⚠️", "GEOMETRY", "PHYSICS", "grid:", "pits:",
                                     "corners:", "TRACK LIMITS", "OWN textures", "textures converted", "new textures",
                                     "textures no material", "TRD", "gloss",
                                     "ALPHATEST", "orphan", "lights", "UV tightened", "recalibrated", "PACKAGE",
                                     "PIECES", "trimmed", "alpha blending", "mipmaps", "WITHOUT .mtx", "LiveTrack",
                                     "author's lights", "asphalt detail", "start lights", "pit distances",
                                     "translucent fences", "own ads", "asphalt relief", "night glows", "BANNERS:",
                                     "report",
                                     # without this one, "MULTILAYER asphalt … in 0 materials" never reached the log
                                     "MULTILAYER")):
                print(f"   {ln.strip()}")
            if ln.startswith("GEOMETRY:"):
                try:
                    ctx["mallas"] = int(ln.split(":")[1].split()[0])
                except (IndexError, ValueError):
                    pass
        if rc != 0:
            # The filter above only lets the 🔴 line through: the traceback was lost and there was no
            # way to know why it had failed. The tail is shown.
            print(f"🔴 step «{etiqueta}» failed — end of its output:")
            print("\n".join("      " + x for x in salida.strip().splitlines()[-25:]))
            return 1

    # images, from the EXPORTED AIW (AC ships no original AIW)
    render = os.path.join(carpeta, "ui", trazado, "preview.png")
    rc, s = C.corre([sys.executable, "generar_mapa.py", ctx["aiw_out"], os.path.join(ctx["pack"], "GUI"),
                     "--nombre", nombre, "--titulo", arg("--titulo") or _titulo(ui, nombre)]
                    + (["--render", render] if os.path.exists(render) else [])
                    + (["--foto", arg("--foto")] if arg("--foto") else [])
                    + (["--estilo-reiza"] if "--estilo-reiza" in argv else []))
    print(f"   images: {'✅' if rc == 0 else '🔴 ' + s.strip()[-200:]}")

    # night lights: the series the AUTHOR defined for Custom Shaders Patch (optional)
    if "--luces-autor" in argv:
        import generar_luces as GLZ
        rz = GLZ.escribir_series(ctx["pack"], nombre, carpeta, trazado,
                                 focos_gradas="--focos-gradas" in argv,
                                 aiw_tramos_oscuros=ctx["aiw_out"] if "--focos-oscuros" in argv else None,
                                 aiw_daytona=ctx["aiw_out"] if "--focos-daytona" in argv else None,
                                 plano_real="--plano-real" in argv)
        print(f"   author's lights: {rz.get('luces')} · {rz.get('series') or rz.get('motivo')}"
              f" · height above the ground min/median/max {rz.get('alturas')}"
              + (f" · Daytona recipe {rz['daytona']}" if rz.get("daytona") else ""))

    # LiveTrack: the TRACK's own rubber and puddle grid, not Meadowdale's
    import generar_livetrack as GL
    ruta_mrdf = os.path.join(ctx["pack"], "Tracks", "_data", "livetrack", f"{nombre}.mrdf")
    if os.path.isdir(os.path.dirname(ruta_mrdf)):
        rl = GL.generar(carpeta, trazado, ruta_mrdf)
        print(f"   LiveTrack: {rl['celdas']} cells of {rl['rejilla'][0]}x{rl['rejilla'][1]} "
              f"· {rl['goma']} in the rubber band")

    # sound: crowd along the grandstands, announcers, pit ambience and echo, like Daytona
    if "--sonido-propio" in argv:
        import generar_sonido as GSN
        ruta_lsd = os.path.join(ctx["pack"], "Tracks", "_data", "audio", f"{nombre}.lsd")
        if os.path.exists(ruta_lsd):
            rs = GSN.generar(carpeta, trazado, ruta_lsd, ruta_lsd, T.construir(carpeta, trazado), nombre)
            print(f"   own sound: {rs['publico']} cheers in {rs['gradas']} grandstands · {rs['locutores']} announcers · "
                  f"{rs['ecos']} grandstand echoes · pits in {rs['boxes']} stretches")

    # TV cameras: the track's own (`<layout>/data/cameras*.ini`), not the template's Meadowdale ones
    import cam_ac
    import generar_camaras as GC
    xml_cam = os.path.join(ctx["pack"], "cameras", f"{nombre}.xml")
    cams, juego = cam_ac.camaras(carpeta, trazado, T.leer_ai(os.path.join(
        carpeta, trazado, "ai", "fast_lane.ai"))["pos"])
    if "--camaras-tv" in argv and os.path.exists(xml_cam):
        # 📺 every AC camera set as a broadcast group, with boxes that cover the lap and zoom
        # (`camaras_tv.py`, measured against the official Daytona)
        import camaras_tv as CT
        rtv = CT.generar(carpeta, trazado, xml_cam, ctx["aiw_out"], T.leer_ai(os.path.join(
            carpeta, trazado, "ai", "fast_lane.ai"))["pos"])
        print(f"   TV cameras: {rtv.get('camaras')} cameras · {rtv.get('zonas')} boxes · "
              + " · ".join(rtv.get("juegos", [])) if rtv.get("ok") else f"   🔴 TV cameras: {rtv.get('error')}")
    elif cams and os.path.exists(xml_cam):
        rcam = GC.generar(None, xml_cam, ctx["obj"], ctx["aiw_out"], camaras=cams)
        print(f"   cameras: {rcam.get('camaras')} from {juego} · {rcam.get('zonas')} zones · "
              f"coverage {rcam.get('cobertura')}" if rcam.get("ok")
              else f"   🔴 cameras: {rcam.get('error')}")
    else:
        print(f"   ⚠️ cameras: the example's stay ({'no cameras*.ini' if not cams else 'no XML'})")

    # timing, from the author's gates
    import ac_trazado as T
    import generar_triggers as G
    t = T.construir(carpeta, trazado)
    rt = G.escribir(os.path.join(ctx["pack"], "Tracks", nombre, "physics", "triggers.xml"),
                    None, disparadores=G.calcular_ac(t))
    print(f"   cronometraje: {'✅ ' + str(len(rt['disparadores'])) + ' disparadores' if rt.get('ok') else '🔴 ' + rt.get('error', '')}")

    import aiw_read as A
    n_inc, sin_suelo = C.inclinar_perp(ctx)
    print(f"   banking put back into the AIW: {n_inc} waypoints ({sin_suelo} with no ground under them)")
    if "--distancias-boxes" in argv:
        import aiw_puntuar as AP
        rp = AP.puntuar(ctx["aiw_out"])
        print(f"   pit and grid distances: {rp['tocados']} points recalculated (Daytona rule)")
    if "--ovalo" in argv:
        import ovalo as OV
        print(f"   OVAL AIW: {', '.join(OV.aiw_de_ovalo(ctx['aiw_out']))}")
    # 🔴 sector and pit triggers touched by another stretch, repositioned (on the Roval the author's
    # sector 1 sat on the line between two stretches sharing asphalt in opposite directions). With
    # the final AIW (distances set) and against the GROUND; the finish line is never moved.
    for h in G.recolocar(ctx["aiw_out"], os.path.join(ctx["pack"], "Tracks", nombre, "physics", "triggers.xml"),
                         col=t["colision"]):
        print(f"   timing moved: {h}")
    ctx["aiw_obj"] = A.parse(ctx["aiw_out"])
    ctx["ui"] = ui
    ctx["trazado_ac"] = t
    ctx["semaforos"] = "--semaforos" in argv
    ctx["camaras_tv"] = "--camaras-tv" in argv
    ctx["grupo"], ctx["variante"] = arg("--grupo"), arg("--variante")
    ctx["pancartas"] = os.path.abspath(arg("--pancartas")) if arg("--pancartas") else None
    ctx["central_asfalto"] = "--central-asfalto" in argv
    ctx["distancias_boxes"] = "--distancias-boxes" in argv
    ctx["ancho_asfalto"] = "--ancho-asfalto" in argv
    ctx["parrilla_en_meta"] = "--parrilla-en-meta" in argv
    ctx["puestos"] = min(A.TECHO_PARRILLA, len(t["marcas"]["parrilla"]))

    import empaquetar as E
    apartados = E.apartar_globales(ctx["pack"], nombre)
    if apartados:
        print(f"   GAME files set aside: {len(apartados)}")

    print("\n── gates ──")
    rojas, resultados = [], []
    import time as _time
    for etiqueta, fn in PUERTAS_AC:
        _t0 = _time.time()
        try:
            ok, detalle = fn(ctx)
        except Exception as e:  # noqa: BLE001
            ok, detalle = False, f"the gate blew up: {e}"
        _dt = _time.time() - _t0
        print(f"   {'✅' if ok else '🔴'} {etiqueta}: {detalle}" + (f"  ⏱ {_dt:.0f} s" if _dt >= 3 else ""))
        resultados.append((etiqueta, ok, detalle))
        if not ok:
            rojas.append(etiqueta)
    import creditos as CR
    import informe as INF

    def _informe(zip_ok):
        try:
            r = INF.escribir(os.path.join(w, "REPORT.md"), ctx, argv, resultados, carpeta, trazado,
                             CR.leer_ui(ui), zip_ok)
            print(f"   report: {r}  (share it in an issue to improve the tool)")
        except Exception as e:  # noqa: BLE001  (the report never brings the conversion down)
            print(f"   ⚠️ report: could not be written ({e})")
    if rojas:
        print(f"\n🔴 NOT packed: {len(rojas)} gate(s) in red — {', '.join(rojas)}")
        _informe(False)
        return 1

    rc, salida = C.corre([sys.executable, "empaquetar.py", ctx["pack"], "--nombre", nombre])
    print("\n" + salida.strip().splitlines()[-1] if salida.strip() else "")
    # CREDITS.txt at the zip root: original author + "converted using Gonky Track Converter" (see creditos.py)
    zip_mod = os.path.join(TRABAJO, nombre, f"{nombre}.zip")
    if rc == 0 and "--sin-creditos" not in argv:
        if os.path.exists(zip_mod):
            CR.poner(zip_mod, CR.texto(arg("--titulo") or _titulo(ui, nombre), CR.leer_ui(ui)))
            print(f"   credits: {CR.NOMBRE} at the zip root (original author + {CR.HERRAMIENTA})")
        else:
            print(f"   ⚠️ credits: can't find {zip_mod}")
    _informe(rc == 0)
    return rc


def _publicidad(valor):
    """`MATERIAL[,MATERIAL…]=image` with the image path made absolute (Blender runs in another folder)."""
    mats, sep, img = valor.partition("=")
    if not sep or not img:
        raise SystemExit("🔴 --ads expects MATERIAL[,MATERIAL…]=image.png")
    if not os.path.isfile(img):
        raise SystemExit(f"🔴 --ads: the image {img} doesn't exist")
    return f"{mats}={os.path.abspath(img)}"


def _titulo(ui_path, defecto):
    try:
        return json.load(open(ui_path, encoding="utf-8-sig")).get("name") or defecto
    except (OSError, ValueError):
        return defecto


if __name__ == "__main__":
    sys.exit(main(sys.argv))
