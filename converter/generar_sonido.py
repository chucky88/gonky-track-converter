"""The circuit's sound (`_data/audio/<track>.lsd`), placed the way Daytona does it.

Why: without this step the packages carry the `.lsd` of Meadowdale —OMTT's sample
circuit—: its 4 garage ambiences, a forest, 3 crowd sounds and a commentator, at
Meadowdale's positions. Daytona (official) carries ~30 cheers spread across the stands,
26 commentator points, the pit-lane ambience along it and the echo of the main-straight
stands. The SOUNDS belong to the game (`LevelSounds/AMS2/…`): here they are only placed.

The stands come from the circuit itself: the author's CROWD meshes (material with «CROWD»
and a grandstand surface, not the loose figures). The pit lane, from the `PIT` ground.

Format (measured in `Daytona_Physics`… `daytona.lsd`): the Reflection schema is copied from
the template; the areas are `SoundArea2DOBB` with `Direction` = the `Length` axis and
`Width` perpendicular to it (Daytona's pit lane: `Length` 6 across, `Width` 200 along it).
"""

import math
import os
import re

GRADA_GRANDE_M2 = 3000.0      # from here up, a big «NEAR» cheer and a commentator
PASO_PUBLICO_M = 60.0
PASO_LOCUTOR_M = 45.0
TROZO_BOXES_M = 150.0

S_OVACION_GRANDE = "LevelSounds/AMS2/Ambient/crowd/Near/crowd_big_cheer_spot_01_150m_NEAR"
S_OVACION_PEQUENA = "LevelSounds/AMS2/Ambient/crowd/spot/crowd_small_cheer_spot_01"
S_OVACION_MEDIA = "LevelSounds/AMS2/Ambient/crowd/spot/crowd_medium_cheer_spot_01"
S_LOCUTORES = ("LevelSounds/AMS2/Ambient/Announcer/Spot/announcer_01_200m",
               "LevelSounds/AMS2/Ambient/Announcer/Spot/announcer_02_200m",
               "LevelSounds/AMS2/Ambient/Announcer/Spot/announcer_03_200m")
S_AMBIENTE = "LevelSounds/AMS2/Ambient/General/Ambience_countryside_North"
S_BOXES = "LevelSounds/AMS2/Ambient/Pits/Ambient_pitlane"
R_GLOBAL, R_GRADAS = "AMBIENT_Reverb_GLOBAL", "LOCAL_Reverb_StartLaneGrandstands"


def _area_malla(m) -> float:
    a = 0.0
    for i, j, k in m.caras:
        A, B, C = m.pos[i], m.pos[j], m.pos[k]
        u = [B[n] - A[n] for n in range(3)]
        v = [C[n] - A[n] for n in range(3)]
        a += math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                       + (u[0] * v[1] - u[1] * v[0]) ** 2) / 2
    return a


def gradas(carpeta: str, trazado: str) -> list:
    """[{"centro", "eje", "ancho", "largo", "altura", "area"}] for each crowd mesh."""
    import ac_trazado as T
    import kn5_read as K
    fuera = []
    for p in T.modelos(carpeta, trazado):
        k = K.leer(p, con_geometria=True)
        for m in k["mallas"]:
            mat = k["materiales"][m.material].nombre.upper()
            if "CROWD" not in mat or not m.pos or not m.dibuja:
                continue
            area = _area_malla(m)
            if area < 150:           # loose figures are not a grandstand
                continue
            xs, zs = [v[0] for v in m.pos], [v[2] for v in m.pos]
            cx, cz = sum(xs) / len(xs), sum(zs) / len(zs)
            sxx = sum((x - cx) ** 2 for x in xs)
            szz = sum((z - cz) ** 2 for z in zs)
            sxz = sum((x - cx) * (z - cz) for x, z in zip(xs, zs))
            ang = 0.5 * math.atan2(2 * sxz, sxx - szz)
            ex, ez = math.cos(ang), math.sin(ang)
            proy = [(x - cx) * ex + (z - cz) * ez for x, z in zip(xs, zs)]
            trans = [-(x - cx) * ez + (z - cz) * ex for x, z in zip(xs, zs)]
            fuera.append({"centro": (cx, sum(v[1] for v in m.pos) / len(m.pos), cz), "eje": (ex, ez),
                          "desde": min(proy), "hasta": max(proy), "fondo": max(trans) - min(trans),
                          "area": area, "ymin": min(v[1] for v in m.pos), "ymax": max(v[1] for v in m.pos)})
    return fuera


def _xml_env(nombre, sonido, pos, rango, vol=1.0):
    return (f'                <data class="EnvironmentSound" id="{_id()}">\n'
            f'                    <prop name="Name" data="{nombre}" />\n'
            f'                    <prop name="SoundName" data="{sonido}" />\n'
            f'                    <prop name="Position" data="{pos[0]:.3f};{pos[1]:.3f};{pos[2]:.3f}" />\n'
            '                    <prop name="Velocity" data="0;0;0" />\n'
            '                    <prop name="Orientation" data="0;0;1" />\n'
            f'                    <prop name="Volume" data="{vol:g}" />\n'
            '                    <prop name="FadeInTime" data="0" />\n'
            '                    <prop name="FadeOutTime" data="0" />\n'
            f'                    <prop name="Range" data="{rango:g}" />\n'
            '                </data>\n')


def _xml_obb(nombre, centro, direccion, largo, ancho, sangria):
    s = " " * sangria
    return (f'{s}<data class="SoundArea2DOBB" id="{_id()}">\n'
            f'{s}    <prop name="Name" data="{nombre}" />\n'
            f'{s}    <prop name="Centre" data="{centro[0]:.3f};{centro[1]:.3f};{centro[2]:.3f}" />\n'
            f'{s}    <prop name="Direction" data="{direccion[0]:.5f};{direccion[1]:.5f}" />\n'
            f'{s}    <prop name="Length" data="{largo:.1f}" />\n'
            f'{s}    <prop name="Width" data="{ancho:.1f}" />\n'
            f'{s}</data>\n')


_CONTADOR = [0x5A000000]


def _id():
    _CONTADOR[0] += 0x40
    return f"0x{_CONTADOR[0]:08X}"


def _ambiente(nombre, sonido, area_xml):
    return (f'                <data class="AmbientSound" id="{_id()}">\n'
            f'                    <prop name="Name" data="{nombre}" />\n'
            f'                    <prop name="SoundName" data="{sonido}" />\n'
            '                    <prop name="DefaultAmbient" data="false" />\n'
            '                    <prop name="FadeInTime" data="0.5" />\n'
            '                    <prop name="FadeOutTime" data="0.5" />\n'
            '                    <prop name="VelocityMinVolume" data="112" />\n'
            '                    <prop name="VelocityMaxVolume" data="0" />\n'
            '                    <prop name="SoundAreaDef">\n'
            '                        <funcpropdata>\n' + area_xml +
            '                        </funcpropdata>\n'
            '                    </prop>\n'
            '                    <prop name="DynamicParameters" />\n'
            '                </data>\n')


def generar(carpeta: str, trazado: str, plantilla_lsd: str, salida_lsd: str, t: dict, nombre: str) -> dict:
    tr = t["trazada"]
    xs, zs = [p[0] for p in tr], [p[2] for p in tr]
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    cy = sum(p[1] for p in tr) / len(tr)

    def lado_pista(p):
        q = min(tr, key=lambda s: (s[0] - p[0]) ** 2 + (s[2] - p[2]) ** 2)
        return q

    ambientes = [_ambiente("Ambient_global", S_AMBIENTE,
                           f'                            <data class="SoundAreaSpherical" id="{_id()}">\n'
                           '                                <prop name="Name" data="Ambient_global" />\n'
                           f'                                <prop name="Centre" data="{cx:.3f};{cy:.3f};{cz:.3f}" />\n'
                           '                                <prop name="Radius" data="5000" />\n'
                           '                                <prop name="Flat" data="false" />\n'
                           '                            </data>\n')]
    # the pit lane, in chunks (it is curved), only where the ground is pit surface
    calle, col = t.get("boxes_linea") or [], t.get("colision")
    boxes = [p for p in calle if col is not None and (col.debajo(p[0], p[2], p[1]) or ("--",))[0] in {"PIT", "PITS"}]
    trozos, actual, acum = [], [], 0.0
    for a, b in zip(boxes, boxes[1:]):
        actual.append(a)
        acum += math.dist(a, b)
        if acum >= TROZO_BOXES_M:
            actual.append(b)
            trozos.append(actual)
            actual, acum = [], 0.0
    if len(actual) > 1:
        trozos.append(actual)
    for n, tz in enumerate(trozos, start=1):
        a, b = tz[0], tz[-1]
        largo = math.dist((a[0], a[2]), (b[0], b[2]))
        if largo < 5:
            continue
        dx, dz = (b[0] - a[0]) / largo, (b[2] - a[2]) / largo
        centro = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
        ambientes.append(_ambiente(f"Ambient_pitlane_{n}", S_BOXES,
                                   _xml_obb(f"Ambient_pitlane_{n}", centro, (-dz, dx), 12.0, largo + 10.0, 28)))

    entorno, reverbs = [], []
    gs = sorted(gradas(carpeta, trazado), key=lambda g: -g["area"])
    n_pub = n_loc = 0
    for i, g in enumerate(gs):
        ex, ez = g["eje"]
        grande = g["area"] >= GRADA_GRANDE_M2
        largo = g["hasta"] - g["desde"]
        pasos = max(1, int(largo // PASO_PUBLICO_M))
        for k in range(pasos):
            s = g["desde"] + (k + 0.5) * largo / pasos
            p = (g["centro"][0] + ex * s, g["centro"][1], g["centro"][2] + ez * s)
            n_pub += 1
            sonido = S_OVACION_GRANDE if grande else (S_OVACION_MEDIA if g["area"] > 800 else S_OVACION_PEQUENA)
            entorno.append(_xml_env(f"Crowd_{n_pub}", sonido, p, 150))
        if grande:
            pasos = max(1, int(largo // PASO_LOCUTOR_M))
            for k in range(pasos):
                s = g["desde"] + (k + 0.5) * largo / pasos
                p = (g["centro"][0] + ex * s, g["centro"][1] + 4.0, g["centro"][2] + ez * s)
                entorno.append(_xml_env(f"Announcer_{n_loc + 1}", S_LOCUTORES[n_loc % 3], p, 200))
                n_loc += 1
            # the grandstand echo: between the stand and the track, along it
            q = lado_pista(g["centro"])
            centro = ((g["centro"][0] * 0.4 + q[0] * 0.6), q[1], (g["centro"][2] * 0.4 + q[2] * 0.6))
            reverbs.append(
                f'                <data class="LocalReverb" id="{_id()}">\n'
                f'                    <prop name="Name" data="LocalReverb_{len(reverbs) + 1}" />\n'
                f'                    <prop name="ReverbName" data="{R_GRADAS}" />\n'
                '                    <prop name="ReverbInfluence" data="1" />\n'
                '                    <prop name="FadeRange" data="1" />\n'
                '                    <prop name="SoundAreaDef">\n'
                '                        <funcpropdata>\n'
                + _xml_obb(f"grandstand_{len(reverbs) + 1}", centro, (-ez, ex), 25.0, largo, 28) +
                '                        </funcpropdata>\n'
                '                    </prop>\n'
                '                </data>\n')

    cabecera = open(plantilla_lsd, encoding="utf-8", errors="ignore").read()
    cabecera = cabecera[:cabecera.index('    <data class="LevelSoundDefinition"')]
    ancho_x = max(xs) - min(xs) + 1200
    ancho_z = max(zs) - min(zs) + 1200
    cuerpo = (
        f'    <data class="LevelSoundDefinition" id="{_id()}">\n'
        f'        <prop name="Name" data="{nombre}SoundDefinition" />\n'
        '        <prop name="LevelSoundAreaDef">\n'
        '            <funcpropdata>\n'
        + _xml_obb(f"{nombre}Level", (cx, cy, cz), (1.0, 0.0), ancho_x, ancho_z, 16) +
        '            </funcpropdata>\n'
        '        </prop>\n'
        f'        <prop name="AmbientSounds" elements="{len(ambientes)}">\n'
        '            <funcpropdata>\n' + "".join(ambientes) +
        '            </funcpropdata>\n'
        '        </prop>\n'
        f'        <prop name="EnvironmentSounds" elements="{len(entorno)}">\n'
        '            <funcpropdata>\n' + "".join(entorno) +
        '            </funcpropdata>\n'
        '        </prop>\n'
        '        <prop name="AmbientReverb">\n'
        '            <funcpropdata>\n'
        f'                <data class="AmbientReverb" id="{_id()}">\n'
        '                    <prop name="Name" data="Ambient_global" />\n'
        f'                    <prop name="ReverbName" data="{R_GLOBAL}" />\n'
        '                    <prop name="ReverbInfluence" data="1" />\n'
        '                </data>\n'
        '            </funcpropdata>\n'
        '        </prop>\n'
        f'        <prop name="LocalReverbs" elements="{len(reverbs)}">\n'
        '            <funcpropdata>\n' + "".join(reverbs) +
        '            </funcpropdata>\n'
        '        </prop>\n'
        '    </data>\n'
        '</Reflection>\n')
    open(salida_lsd, "w", encoding="utf-8").write(cabecera + cuerpo)
    return {"gradas": len(gs), "publico": n_pub, "locutores": n_loc, "ecos": len(reverbs),
            "boxes": len(ambientes) - 1}
