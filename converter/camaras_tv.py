"""TV cameras like those of a Reiza oval: ALL the camera sets of the Assetto Corsa circuit,
each one as a broadcast group, and boxes (`COBBArea`) that cover the lap.

    python3 camaras_tv.py <AC folder> <layout> <cameras/track.xml> <track.aiw>   # writes
    python3 camaras_tv.py --comprobar <cameras/track.xml> <track.aiw>

What Daytona (official) does, measured in `cameras/daytona.xml`:

- **6 camera positions** with **two variants** each (`TrackingCam_01_L13` / `_L24`…) and
  12 `CamAreaOBB_*` boxes that cover **100 %** of the lap (738 of 738 waypoints).
- `CameraGroup` is a **4-bit mask**: L13 = 1+4 = 5, L24 = 2+8 = 10, L134 = 13…
  On each stretch the variants add up to 15, i.e.: **each group has a camera for every point
  of the lap**, and the director keeps switching between groups. That is the rule that
  `comprobar()` checks: coverage is measured PER GROUP, not in total.
- Each camera names ITS boxes (`ActiveAreas` → `areaIndexN`, up to 5).
- `Dimensions` are **half sides** (with full sides Daytona's boxes cover 34 %) and the long
  axis of the box is **row** 0 of `XForm` (72 of Daytona's 73 rotated boxes).
- Zoom: `FOVMin` 2-5° and `FOVMax` 45°. 🔴 With `FOVMin = FOVMax = 40°` (what came out of the
  template) the camera has **no zoom**: a wide, fixed shot. And `ForceKeep 950` (Daytona 0).

Assetto Corsa ships several sets (`cameras.ini`, `cameras_1.ini`… the ones you switch with F3),
each with its `IN_POINT`-`OUT_POINT` stretches covering the lap. All of them go in: the highest
one (the grandstand one, the TV shot) takes two groups, like Daytona's main variant.

The position is the author's, AS IS: in AC `y` is absolute. `altura_sobre_suelo()` is for
AMS1, where y is the height of the tower, and applied to AC it raised them by 1-4 m.
"""

import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_camaras as GC  # noqa: E402

LARGO_CAJA_M = 140.0        # a stretch is split into boxes of at most this (Daytona: 40-650)
MAX_CAJAS_POR_CAMARA = 5    # Daytona links up to 5; `_poner_areas` cuts off there
SOLAPE_M = 12.0             # lengthwise: so that no gap is left between neighbouring boxes
MARGEN_LADO_M = 30.0        # widthwise, from the outermost point of the racing line or the pits
MEDIA_ALTURA_MIN_M = 15.0

# Settings per camera type, copied from Daytona's (grandstand = TrackingCam_01_L13,
# trackside = TrackingCam_02_L12)
ESTILO = {
    "grada": {"FOVScalar": "1.7", "ForceKeepDistance": "100", "NearZ": "3", "LookAtOffset": "0;1;0"},
    "pista": {"FOVScalar": "2.3", "ForceKeepDistance": "90", "NearZ": "1", "LookAtOffset": "0;0.5;0"},
}
COMUNES = {"ForceKeep": "0", "FOVDelay": "0", "DOF": "0", "mBokehEnabled": "false",
           "ShakeMagnitude": "0.03", "ShakeFrequency": "1", "ShakeFrequencyMin": "0",
           "ShakeScreenVelocity": "1", "ShakeScreenVelocityMin": "0", "ZoomSpeed": "0.5",
           "LODDistanceMultiplier": "6", "FarZ": "4000", "bAutoZoom": "true"}
ALTURA_GRADA_M = 12.0       # a set averaging ≥ this above the racing line is a «grandstand» set


def _mascaras(n):
    """Group bits for n sets, ordered from highest to lowest."""
    return {1: [15], 2: [5, 10], 3: [5, 2, 8]}.get(n, [1, 2, 4, 8][:n])


def _acumulada(pts):
    acum = [0.0]
    for i in range(1, len(pts)):
        acum.append(acum[-1] + math.dist(pts[i], pts[i - 1]))
    return acum


def _cercano(pts, p):
    return min(range(len(pts)), key=lambda k: math.hypot(pts[k][0] - p[0], pts[k][2] - p[2]))


def _caja(puntos, direccion):
    """Box oriented in plan view (rotation only about Y) that contains the points, with a margin."""
    dx, dz = direccion
    L = math.hypot(dx, dz) or 1.0
    dx, dz = dx / L, dz / L
    u = [p[0] * dx + p[2] * dz for p in puntos]
    v = [-p[0] * dz + p[2] * dx for p in puntos]
    y = [p[1] for p in puntos]
    u0, u1 = min(u) - SOLAPE_M, max(u) + SOLAPE_M
    v0, v1 = min(v) - MARGEN_LADO_M, max(v) + MARGEN_LADO_M
    y0, y1 = min(y), max(y)
    uc, vc, yc = (u0 + u1) / 2, (v0 + v1) / 2, (y0 + y1) / 2
    # from (u, v) to (x, z): x = u·dx − v·dz, z = u·dz + v·dx
    cx, cz = uc * dx - vc * dz, uc * dz + vc * dx
    return {"eje": (dx, dz), "centro": (cx, yc, cz),
            "medios": ((u1 - u0) / 2, max(MEDIA_ALTURA_MIN_M, (y1 - y0) / 2 + 10.0), (v1 - v0) / 2)}


def _xml_caja(nombre, c, i):
    dx, dz = c["eje"]
    cx, cy, cz = c["centro"]
    a, b, h = c["medios"]
    xf = [dx, 0, dz, 0, 0, 1, 0, 0, -dz, 0, dx, 0, cx, cy, cz, 1]
    return (f'<data class="COBBArea" id="0x{0xA05B0000 + i:08X}">\n'
            f'                    <prop name="Name" data="{nombre}" />\n'
            f'                    <prop name="XForm" data="{";".join(f"{v:.6g}" for v in xf)}" />\n'
            f'                    <prop name="Dimensions" data="{a:.4f};{b:.4f};{h:.4f}" />\n'
            f'                    <prop name="DebugRenderColor" data="4294901760" />\n'
            f'                    <prop name="FOV" data="0" />\n'
            f'                    <prop name="FocusDelay" data="0" />\n'
            f'                    <prop name="ZoomSpeed" data="0" />\n'
            f'                </data>')


def juegos_ac(carpeta, trazado):
    """[(file, [raw cameras])] from `<trazado>/data/cameras*.ini`, with mirrored position."""
    import glob

    import cam_ac
    import kn5_read as K

    out = []
    for r in sorted(glob.glob(os.path.join(carpeta, trazado, "data", "cameras*.ini"))):
        cams = []
        for c in cam_ac._leer_ini(r):
            try:
                cams.append({"nombre": c.get("NAME", "cam"),
                             "pos": K._espejo(tuple(float(x) for x in c["POSITION"].split(","))),
                             "fov": (float(c.get("MIN_FOV") or 5), float(c.get("MAX_FOV") or 40)),
                             "tramo": (float(c.get("IN_POINT", 0)), float(c.get("OUT_POINT", 0)))})
            except (KeyError, ValueError):
                continue
        if cams:
            out.append((os.path.basename(r), cams))
    return out


def generar(carpeta, trazado, xml_path, aiw_path, trazada_ac):
    """Rewrites the XML's cameras and zones. `trazada_ac` is the one from `fast_lane.ai`
    (mirrored), which is what AC measures the `IN_POINT`/`OUT_POINT` fractions against."""
    import aiw_read as A

    aiw = A.parse(aiw_path)
    vuelta = [w.pos for w in aiw.main_path]
    boxes = [w.pos for w in aiw.pit_waypoints]
    juegos = juegos_ac(carpeta, trazado)
    if not juegos or len(vuelta) < 10:
        return {"ok": False, "error": "no cameras*.ini or no racing line"}

    acum_ac = _acumulada(trazada_ac)

    def punto_ac(f):
        objetivo = (f % 1.0) * acum_ac[-1]
        for i, a in enumerate(acum_ac):
            if a >= objetivo:
                return trazada_ac[i]
        return trazada_ac[-1]

    # pits: each point to the index of the lap beside it, so it falls in that stretch's box
    boxes_en = {}
    for p in boxes:
        boxes_en.setdefault(_cercano(vuelta, p), []).append(p)

    def altura_media(cams):
        return sum(c["pos"][1] - vuelta[_cercano(vuelta, c["pos"])][1] for c in cams) / len(cams)

    juegos.sort(key=lambda j: -altura_media(j[1]))
    mascaras = _mascaras(len(juegos))
    acum = _acumulada(vuelta)
    n = len(vuelta)

    texto = open(xml_path, encoding="utf-8", errors="ignore").read()
    cams_viejas = GC._bloques(texto, "CTrackingCamData")
    areas_viejas = GC._bloques(texto, "CSphereArea") or GC._bloques(texto, "COBBArea")
    if not cams_viejas or not areas_viejas:
        return {"ok": False, "error": "the template has no cameras or zones"}
    molde = cams_viejas[0][2]

    bloques_cam, bloques_caja, resumen = [], [], []
    for (fichero, cams), mascara in zip(juegos, mascaras):
        estilo = "grada" if altura_media(cams) >= ALTURA_GRADA_M else "pista"
        for c in cams:
            i0 = _cercano(vuelta, punto_ac(c["tramo"][0]))
            i1 = _cercano(vuelta, punto_ac(c["tramo"][1]))
            idx = [(i0 + k) % n for k in range(((i1 - i0) % n) + 1)]
            largo = sum(math.dist(vuelta[idx[k]], vuelta[idx[k - 1]]) for k in range(1, len(idx)))
            partes = max(1, min(MAX_CAJAS_POR_CAMARA, math.ceil(largo / LARGO_CAJA_M)))
            mias = []
            for p in range(partes):
                trozo = idx[len(idx) * p // partes: len(idx) * (p + 1) // partes + 1]
                pts = [vuelta[k] for k in trozo] + [q for k in trozo for q in boxes_en.get(k, ())]
                a, b = vuelta[trozo[0]], vuelta[trozo[-1]]
                eje = (b[0] - a[0], b[2] - a[2])
                if math.hypot(*eje) < 1.0:
                    m = trozo[0]
                    eje = (vuelta[(m + 1) % n][0] - vuelta[m - 1][0], vuelta[(m + 1) % n][2] - vuelta[m - 1][2])
                mias.append(len(bloques_caja))
                bloques_caja.append(_xml_caja(f"CamAreaOBB_{len(bloques_caja) + 1}", _caja(pts, eje),
                                              len(bloques_caja)))
            fmin = max(2.0, min(c["fov"][0], 10.0))
            fmax = min(45.0, max(c["fov"][1], 30.0))
            # resting heading towards the centre of its stretch (the TrackingCam follows the car on its own)
            medio = vuelta[idx[len(idx) // 2]]
            yaw = math.atan2(medio[0] - c["pos"][0], -(medio[2] - c["pos"][2]))
            nombre = f"TV{mascara:02d}_{os.path.splitext(fichero)[0]}_{c['nombre'].replace(' ', '')}"
            props = dict(COMUNES, **ESTILO[estilo])
            props.update(Name=nombre, Pos=f"{c['pos'][0]:.4f};{c['pos'][1]:.4f};{c['pos'][2]:.4f}",
                         QuatOri=f"{math.cos(yaw / 2):.6f};0;{math.sin(yaw / 2):.6f};0",
                         FOV=f"{math.radians(fmin):.6f}", FOVMin=f"{math.radians(fmin):.6f}",
                         FOVMax=f"{math.radians(fmax):.6f}", CameraGroup=str(mascara))
            bloque = GC._sustituir(molde, **props)
            bloque = GC._poner_areas(bloque, mias)
            bloques_cam.append(GC._id_unico(bloque, "A1C40000", len(bloques_cam)))
        resumen.append(f"{fichero}: {len(cams)} cameras, group {mascara}, {estilo}")

    texto = GC._reemplazar_lista(texto, areas_viejas, bloques_caja, "Areas")
    texto = GC._reemplazar_lista(texto, cams_viejas, bloques_cam, "Trackside Cams")
    open(xml_path, "w", encoding="utf-8").write(texto)
    return {"ok": True, "camaras": len(bloques_cam), "zonas": len(bloques_caja), "juegos": resumen}


def _leer_xml(xml_path):
    t = open(xml_path, encoding="utf-8", errors="ignore").read()
    cajas = []
    for a in re.findall(r'<data class="COBBArea"[^>]*>(.*?)</data>', t, re.S):
        x = [float(v) for v in re.search(r'XForm" data="([^"]*)"', a).group(1).split(";")]
        d = [abs(float(v)) for v in re.search(r'Dimensions" data="([^"]*)"', a).group(1).split(";")]
        cajas.append(([x[0:3], x[4:7], x[8:11]], x[12:15], d))
    cams = []
    for c in re.split(r'<data class="CTrackingCamData"', t)[1:]:
        g = re.search(r'name="CameraGroup" data="(\d+)"', c)
        fp = re.search(r'name="ActiveAreas" elements="\d+">\s*<funcpropdata ([^/]*)/>', c)
        idx = [int(v) for v in re.findall(r'"(\d+)"', fp.group(1))] if fp else []
        cams.append((int(g.group(1)) if g else 15, idx))
    return cajas, cams


def _dentro(p, caja):
    ejes, o, d = caja
    v = [p[i] - o[i] for i in range(3)]
    return all(abs(sum(v[i] * e[i] for i in range(3))) <= d[k] for k, e in enumerate(ejes))


def comprobar(xml_path, aiw_path, minimo=0.98):
    """For each of the 4 groups, what fraction of the lap and of the pits falls inside some box
    of a camera in THAT group. It is Daytona's rule (100 % in each group).

    It is not entirely tautological: the boxes are built from the lap's points, but the
    per-group coverage depends on the AC author's stretches covering the lap without gaps and
    on the cameras linking their boxes (the `areaIndex1="0"` bug, see
    `generar_camaras._poner_areas`). The measure was tested on Daytona: groups 2 and 8 at 100 %,
    **1 and 4 at 92 %** (its `5B` box is only linked by the L24 variant). In other words, the
    game tolerates gaps and Reiza leaves them; 98 % is required because here the boxes come from
    the author's stretches and a gap would be a conversion bug."""
    import aiw_read as A

    aiw = A.parse(aiw_path)
    vuelta = [w.pos for w in aiw.main_path]
    boxes = [w.pos for w in aiw.pit_waypoints]
    cajas, cams = _leer_xml(xml_path)
    cobert = {}
    for bit in (1, 2, 4, 8):
        mias = {i for g, idx in cams if g & bit for i in idx if i < len(cajas)}
        cv = sum(any(_dentro(p, cajas[i]) for i in mias) for p in vuelta) / max(1, len(vuelta))
        cb = sum(any(_dentro(p, cajas[i]) for i in mias) for p in boxes) / max(1, len(boxes)) if boxes else 1.0
        cobert[bit] = (cv, cb)
    sin_zoom = sum(1 for c in re.split(r'<data class="CTrackingCamData"', open(xml_path).read())[1:]
                   if re.search(r'FOVMin" data="([^"]*)"', c).group(1) == re.search(r'FOVMax" data="([^"]*)"', c).group(1))
    ok = all(cv >= minimo and cb >= minimo for cv, cb in cobert.values()) and sin_zoom == 0
    txt = " · ".join(f"group {b}: lap {cv:.0%} pits {cb:.0%}" for b, (cv, cb) in cobert.items())
    return ok, f"{len(cams)} cameras, {len(cajas)} boxes · {txt} · {sin_zoom} without zoom"


def main(argv):
    if len(argv) >= 4 and argv[1] == "--comprobar":
        ok, txt = comprobar(argv[2], argv[3])
        print(("✅ " if ok else "🔴 ") + txt)
        return 0 if ok else 1
    if len(argv) < 5:
        print(__doc__)
        return 2
    import ac_trazado as T

    tr = T.leer_ai(os.path.join(argv[1], argv[2], "ai", "fast_lane.ai"))["pos"]
    r = generar(argv[1], argv[2], argv[3], argv[4], tr)
    print(r)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
