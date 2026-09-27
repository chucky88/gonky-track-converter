"""Writes the AMS2 camera XML with the cameras the circuit ALREADY had in AMS1.

    python3 generar_camaras.py <track.cam> <pack>/cameras/<name>.xml [<track>_physics.obj]

🔴 Why it exists: the package's camera XML is the SAMPLE circuit's with the name changed,
so the exterior camera looks from kilometres up and **the car seems to fall into the
void**. It is easy to mistake it for a physics bug.

No cameras are invented: AMS1 carries its `.cam` with each camera's position, its FOV and
the stretch where it activates. The coordinates **are not transformed** — both engines are
Y-up, as the AIW already proved.

The XML is not generated from scratch: the **lists are rewritten** in the existing one,
which carries the schemas and the dozens of per-camera fields (zoom curves, focus, DOF…)
that we do not know how to fill in and that do not need touching.

Size reference: Texas Motor Speedway, a well-made AMS2 oval, carries **24 cameras and 35
zones**. Charlotte carries 6 in its `.cam`: fewer, but in the right place.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cam_read as C  # noqa: E402


def _bloques(texto, clase):
    """All the top-level `<data class="X" …>…</data>` of that class."""
    out = []
    for m in re.finditer(rf'<data class="{clase}"[^>]*>', texto):
        i = m.start()
        prof, j = 0, i
        while j < len(texto):
            a = texto.find("<data", j)
            b = texto.find("</data>", j)
            if b == -1:
                break
            if a != -1 and a < b:
                prof += 1
                j = a + 5
            else:
                prof -= 1
                j = b + 7
                if prof == 0:
                    break
        out.append((i, j, texto[i:j]))
    return out


def _sustituir(bloque, **props):
    """Changes `<prop name="X" data="…"/>` inside a block, without touching anything else."""
    for clave, valor in props.items():
        nombre = clave.replace("_", " ")
        bloque = re.sub(
            rf'(<prop name="{re.escape(nombre)}" data=")[^"]*(")',
            lambda m: m.group(1) + str(valor) + m.group(2),
            bloque,
            count=1,
        )
    return bloque


def altura_sobre_suelo(camaras, obj_fisica: str, radio_m: float = 40.0):
    """Raises each camera to `ground + |y|`. Returns the list of heights set.

    ⚠️ **In the AMS1 `.cam` the camera height comes NEGATIVE.** As is, Charlotte's 6 ended
    up between 5 and 14 m **underground** — measured against the collision mesh. Read as
    «tower height» it fits: −10 is a camera at 10 m, which is how tall a TV tower is. It is
    placed on the LOCAL ground, which also absorbs the banking.
    """
    import math

    import verificar_fisica as V

    verts = V.leer_obj(obj_fisica)
    g, lado = V.rejilla(verts, 8.0)
    puestas, ampliadas, sin_suelo = [], [], []
    r = int(radio_m // lado) + 1
    for c in camaras:
        cx, cz = int(c.pos[0] // lado), int(c.pos[2] // lado)
        alturas = [
            v[1]
            for dx in range(-r, r + 1)
            for dz in range(-r, r + 1)
            for v in g.get((cx + dx, cz + dz), ())
            if math.hypot(v[0] - c.pos[0], v[2] - c.pos[2]) <= radio_m
        ]
        # ⚠️ If there is no collision within the radius, silently using 0.0 is an invented
        # ground. In Charlotte **3 of the 6 cameras** fell into that case (they are outside
        # the wall, 45-62 m from the nearest collision vertex) and got it right **by luck**,
        # because the terrain is almost flat. The radius is widened and, if there is still
        # nothing, a warning is issued: an invented ground that happens to work is not a
        # measured ground.
        if not alturas:
            r2 = int(radio_m * 3 // lado) + 1
            alturas = [
                v[1]
                for dx in range(-r2, r2 + 1)
                for dz in range(-r2, r2 + 1)
                for v in g.get((cx + dx, cz + dz), ())
                if math.hypot(v[0] - c.pos[0], v[2] - c.pos[2]) <= radio_m * 3
            ]
            if alturas:
                ampliadas.append(c.nombre)
            else:
                sin_suelo.append(c.nombre)
        suelo = sorted(alturas)[len(alturas) // 2] if alturas else 0.0
        c.pos = (c.pos[0], suelo + abs(c.pos[1]), c.pos[2])
        puestas.append(c.pos[1] - suelo)
    if ampliadas or sin_suelo:
        print(f"  ⚠️ cameras without collision within {radio_m:.0f} m: {len(ampliadas)} solved "
              f"by widening the radius"
              + (f" · 🔴 {len(sin_suelo)} WITHOUT GROUND ({', '.join(sin_suelo)}): "
                 f"height made up" if sin_suelo else ""))
    return puestas


def repartir_zonas(aiw_path: str, cuantas: int = 14, margen: float = 6.0):
    """Splits the lap into `cuantas` arcs and returns one spherical zone per arc.

    🔴 Why. The 6 zones that came from the AMS1 `.cam` covered **16 %** of the lap, and only
    one was linked, so the real coverage was **5.8 % (140 m out of 2,393)**. The norm,
    measured on their own AIWs: **Texas 100 %** (28 boxes in a row), Mid-Ohio 85.5 %,
    GJ Kartway 85.5 %.

    ⚠️ Multiplying the radii of the 6 zones up to 364 m left the circuit unable to load. The
    mistake is one of approach: you must not **enlarge** six zones, you must **split** the
    lap into more. Measured in Charlotte: with 14 zones the maximum radius needed is
    **88 m**, within the family of the AMS1 `.cam` itself (50-90 m) and below Mid-Ohio's
    (80-180 m).

    The centre's `y` comes from the layout itself, it is not 0: with small zones the
    elevation matters.
    """
    import math

    import aiw_read as A

    pts = [w.pos for w in A.parse(aiw_path).main_path]
    n = len(pts)
    if n < cuantas * 2:
        return []
    zonas = []
    corte = n / float(cuantas)
    for k in range(cuantas):
        tramo = pts[int(k * corte):int((k + 1) * corte)] or [pts[int(k * corte) % n]]
        cx = sum(p[0] for p in tramo) / len(tramo)
        cy = sum(p[1] for p in tramo) / len(tramo)
        cz = sum(p[2] for p in tramo) / len(tramo)
        radio = max(math.hypot(p[0] - cx, p[2] - cz) for p in tramo) + margen
        zonas.append({"centro": (cx, cy, cz), "radio": radio})
    return zonas


# The family of zone radii used by the files that work: the AMS1 `.cam` itself goes from
# 50 to 90 m and Mid-Ohio from 80 to 180 m. It is the ONLY non-tautological criterion
# available for choosing how many zones to place.
RADIO_MAXIMO_SANO = 180.0


def cobertura_de(aiw_path: str, zonas) -> float:
    """What fraction of the lap's waypoints falls inside some zone.

    ⚠️ **With the zones that `repartir_zonas` builds this is ALWAYS 1.0**, and it proves
    nothing. It is true by construction: each zone's radius is computed as the maximum
    distance from the centre to the points of its own stretch, so those points fall inside
    by definition. Measured in Charlotte: with 2 zones it gives 1.0 (radius 504 m), with 28
    too (radius 48 m). It is the same failure mode that `verificar_fisica` had: the
    reference comes from the same place as the data.

    It is kept because it does help to measure zones that this module does NOT build (the
    AMS1 `.cam` ones gave 16 %), but **the quality criterion is the RADIUS**, not this
    number.
    """
    import math

    import aiw_read as A

    pts = [w.pos for w in A.parse(aiw_path).main_path]
    if not pts or not zonas:
        return 0.0
    dentro = 0
    for p in pts:
        for z in zonas:
            c = z["centro"]
            if math.hypot(p[0] - c[0], p[2] - c[2]) <= z["radio"]:
                dentro += 1
                break
    return dentro / len(pts)


def repartir_camaras(camaras, zonas):
    """Which camera each zone belongs to: the nearest one. Returns a list of lists of indices.

    🔴 Without this the six cameras carried `areaIndex1="0"` —the template's value, cloned six
    times— because `_sustituir()` only rewrites `<prop name=… data=…>` and `areaIndex1` is an
    **attribute of `<funcpropdata>`**, not a prop. Result: 5 of the 6 zones orphaned.
    Texas links up to 5 zones per camera; Mid-Ohio, 12 zones for 12 cameras.
    """
    import math

    reparto = [[] for _ in camaras]
    if not camaras:
        return reparto
    for i, z in enumerate(zonas):
        c = z["centro"]
        mejor = min(range(len(camaras)),
                    key=lambda k: math.hypot(camaras[k].pos[0] - c[0], camaras[k].pos[2] - c[2]))
        reparto[mejor].append(i)
    return reparto


def _poner_areas(bloque, indices):
    """Rewrites a camera's `<prop name="ActiveAreas">` with ITS zones."""
    if not indices:
        indices = [0]
    dentro = " ".join(f'areaIndex{n + 1}="{v}"' for n, v in enumerate(indices[:5]))
    return re.sub(
        r'<prop name="ActiveAreas" elements="\d+">.*?</prop>',
        f'<prop name="ActiveAreas" elements="{min(len(indices), 5)}">\n'
        f'                        <funcpropdata {dentro} />\n'
        f'                    </prop>',
        bloque, count=1, flags=re.S)


def _id_unico(bloque, base_hex, i):
    """Each `<data>` with its own id. 5 out of 5 files that load have unique ids."""
    base = int(base_hex, 16)
    return re.sub(r'(<data class="[A-Za-z]+" id=")0x[0-9A-Fa-f]+(")',
                  lambda m: m.group(1) + f"0x{base + i:08X}" + m.group(2), bloque, count=1)


def generar(cam_path: str | None, xml_path: str, obj_fisica: str | None = None,
            aiw_path: str | None = None, camaras=None) -> dict:
    """Ready-made `camaras` (the Assetto Corsa ones, `cam_ac.camaras`) instead of a `.cam`."""
    if camaras is None:
        camaras = C.solo_tracking(C.parse(cam_path))
    if camaras and obj_fisica and os.path.exists(obj_fisica):
        altura_sobre_suelo(camaras, obj_fisica)
    # ⚠️ In Texas there is a 53×2.5×10 m box that looks like a camera zone that does not
    # cover the lap: it is `Tunnel_01`, which is NOT a camera zone. Texas's camera zones are
    # `cam_zone1a…8c`, 24 × 20 × 55-334 m boxes placed in a row, and they cover **100 %**
    # of its lap (430 of 430 waypoints). Also measured: Mid-Ohio 85.5 %, GJ Kartway
    # 85.5 %, the 6 zones of the AMS1 `.cam` **16 %**.
    #
    # Enlarging the six zones (radii up to 364 m) breaks loading. The right thing is to
    # **split the lap into more zones**: 14 are enough with a maximum radius of 88 m, within
    # the family of radii of the AMS1 `.cam` itself (50-90 m) and below Mid-Ohio's
    # (80-180 m). See `repartir_zonas`.
    if not camaras:
        return {"ok": False, "error": "there is no TrackingCam (neither in the .cam nor in AC)"}

    texto = open(xml_path, encoding="utf-8", errors="ignore").read()
    cams = _bloques(texto, "CTrackingCamData")
    areas = _bloques(texto, "CSphereArea")
    if not cams or not areas:
        return {"ok": False, "error": "the template has no cameras or zones to copy"}

    molde_cam, molde_area = cams[0][2], areas[0][2]

    # --- the ZONES: the lap is split up, the 6 from the .cam are not inherited ----------
    # 🔴 Zones cannot exceed **5 per camera**: `_poner_areas` cuts off there and the rest
    # were lost **silently**. Measured in the pack: ORP has 8 cameras and a distribution
    # `[1, 13, 0…]` → **8 of 14 zones lost, 57 % of the lap without a camera**, and the
    # message said «0 orphaned» because it counted before truncating.
    tope = max(1, len(camaras)) * 5
    zonas = repartir_zonas(aiw_path, cuantas=min(14, tope)) if aiw_path else []
    if not zonas:
        zonas = [{"centro": (c.activacion or c.pos), "radio": c.radio} for c in camaras]
    cobertura = cobertura_de(aiw_path, zonas) if aiw_path else None
    reparto = repartir_camaras(camaras, zonas)

    nuevos_cams = []
    for i, c in enumerate(camaras):
        w, x, y, z = c.quat_ori()
        bloque = _sustituir(
            molde_cam,
            Name=f"TrackingCam_{i + 1}",
            Pos=f"{c.pos[0]:.6f};{c.pos[1]:.6f};{c.pos[2]:.6f}",
            QuatOri=f"{w:.6f};{x:.6f};{y:.6f};{z:.6f}",
            FOV=f"{c.fov_rad:.6f}",
        )
        bloque = _poner_areas(bloque, reparto[i])
        nuevos_cams.append(_id_unico(bloque, "A1C311A0", i))

    nuevas_areas = []
    for i, z in enumerate(zonas):
        cx, cy, cz = z["centro"]
        bloque = _sustituir(
            molde_area,
            Name=f"CamZone{i}",
            Centre=f"{cx:.6f};{cy:.6f};{cz:.6f}",
            Radius=f"{z['radio']:.6f}",
        )
        nuevas_areas.append(_id_unico(bloque, "A04E2330", i))

    # replaced from back to front so as not to shift the indices
    texto = _reemplazar_lista(texto, areas, nuevas_areas, "Areas")
    texto = _reemplazar_lista(texto, cams, nuevos_cams, "Trackside Cams")

    open(xml_path, "w", encoding="utf-8").write(texto)
    return {"ok": True, "camaras": len(nuevos_cams), "zonas": len(nuevas_areas),
            "cobertura": cobertura,
            "radio": max(z["radio"] for z in zonas) if zonas else 0.0,
            # the REAL distribution, already truncated to 5 per camera: counting before the
            # truncation is what made it say «0 orphaned» with 8 zones thrown away.
            "reparto": [min(len(r), 5) for r in reparto]}


def _reemplazar_lista(texto, viejos, nuevos, etiqueta):
    """Changes the blocks and adjusts the list's `elements=`, which the engine does read."""
    ini, fin = viejos[0][0], viejos[-1][1]
    texto = texto[:ini] + "\n".join(nuevos) + texto[fin:]
    return re.sub(
        rf'(<prop name="{re.escape(etiqueta)}" elements=")\d+(")',
        lambda m: m.group(1) + str(len(nuevos)) + m.group(2),
        texto,
        count=1,
    )


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    r = generar(argv[1], argv[2], argv[3] if len(argv) > 3 else None,
                argv[4] if len(argv) > 4 else None)
    if not r["ok"]:
        print(f"🔴 {r['error']}")
        return 1
    radio = r.get("radio") or 0.0
    print(f"✅ {r['camaras']} cameras and {r['zonas']} zones written from the AMS1 .cam"
          f" · max radius {radio:.0f} m"
          + (f" · 🔴 outside the references' range (≤{RADIO_MAXIMO_SANO:.0f} m):"
             f" the lap would need splitting into more zones" if radio > RADIO_MAXIMO_SANO else ""))
    if r.get("reparto"):
        huerfanas = r["zonas"] - sum(r["reparto"])
        print(f"   zones per camera: {r['reparto']}"
              + (f" · 🔴 {huerfanas} zones WITHOUT a camera" if huerfanas else " · 0 orphans"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
