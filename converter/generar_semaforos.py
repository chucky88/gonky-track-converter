"""Start lights and pit entry/exit lights, generated from scratch.

How the engine knows which face is light 1, 2, 3… (worked out on Enna Pergusa, built with
OMTT, and on Daytona): **the 2nd UV set of the lamp's faces carries the ID in `u`, as an
integer**; `u = 0` = not a light. The material is `basic.fx` with `USE_LIGHT_CONTROL`, and the
glow is another mesh with `lightglow_billboard.fx` whose 2nd UV carries the billboard's
corners. `_data/tracklights/<t>.xml` switches each ID on and off per event (countdown, pits
open/closed).

⚠️ The meshes and materials go IN the package (Enna carries its own): you cannot reference
`Tracks\\Daytona\\…`, which is only loaded with Daytona. And the AC author's traffic-light
textures are grey: there the colour is provided by Custom Shaders Patch. That is why
everything is generated here.

The geometry is computed in GAME space (the AIW's: AC mirrored, and Y-up) without `bpy`, so
that it can be tested; `crear_en_blender` only dumps it into the scene.
"""

import math
import os
import subprocess
import rutas as _R  # noqa: E402  (ImageMagick: see rutas.py)

# ── the IDs and names, those of Enna / Daytona (the game's XML expects them this way) ──────
MALLA_SALIDA, MALLA_ENTRADA, MALLA_BOXES_SALIDA = "Startlight_LODA", "Pitlight_LODA", "Pitlight_exit_LODA"
MAT_SALIDA, MAT_SALIDA_ROJO, MAT_SALIDA_VERDE = ("Generic_Startlight", "Generic_Startlight_redglow",
                                                 "Generic_Startlight_greenglow")
MAT_BOXES, MAT_BOXES_ROJO, MAT_BOXES_VERDE = "Generic_Pitlight", "PITLIGHT_Exit_GLOWRED", "PITLIGHT_EXIT_GlowGreen"
ID_ENTRADA_VERDE, ID_ENTRADA_ROJO, ID_SALIDA_VERDE, ID_SALIDA_ROJO = 1, 3, 2, 4

TEX_DIFUSO, TEX_EMISIVO, TEX_DESTELLO = "gr_semaforo_difuso.dds", "gr_semaforo_emisivo.dds", "gr_semaforo_destello.dds"

# dimensions (m)
DIST_A_LA_BOCA = 30.0      # the pit light, at this distance inside the lane
ALTO_POSTE_BOXES = 2.0
ALTO_POSTE_SALIDA = 4.5
LADO_LAMPARA = 0.32
LADO_DESTELLO = 0.9
HOLGURA_MURO = 0.4         # clearance from the wall on the track side
LATERAL_SIN_MURO = 5.0     # if the wall is not found

# UV1 regions in FILE SPACE (v pointing down, like the .dds). Top left the red lens, top
# right the green one; bottom, the housing (black emissive).
UV_ROJO, UV_VERDE, UV_CARCASA = (0.02, 0.02, 0.48, 0.48), (0.52, 0.02, 0.98, 0.48), (0.1, 0.6, 0.4, 0.9)
UV_DESTELLO_ROJO, UV_DESTELLO_VERDE = (0.0, 0.0, 0.5, 1.0), (0.5, 0.0, 1.0, 1.0)


def _norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


def _suma(*vs):
    return tuple(sum(c) for c in zip(*vs))


def _por(v, k):
    return tuple(c * k for c in v)


class Malla:
    """Vertices in game space, faces, UV1/UV2 per vertex (file space) and material per face.
    Each face is included TWICE, once per winding: the move to Blender changes the
    orientation and the game discards back faces; this way it is visible from any side."""

    def __init__(self, nombre):
        self.nombre, self.v, self.uv1, self.uv2, self.caras, self.mat = nombre, [], [], [], [], []
        self.materiales = []

    def _m(self, mat):
        if mat not in self.materiales:
            self.materiales.append(mat)
        return self.materiales.index(mat)

    def quad(self, esquinas, uv1, uv2, mat):
        i = len(self.v)
        self.v += esquinas
        self.uv1 += uv1
        self.uv2 += uv2
        m = self._m(mat)
        for cara in ((i, i + 1, i + 2, i + 3), (i + 3, i + 2, i + 1, i)):
            self.caras.append(cara)
            self.mat.append(m)


def _rect_uv(r):
    u0, v0, u1, v1 = r
    return [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]      # bottom-left, bottom-right, top-right, top-left


def _cara(centro, der, arriba, ancho, alto):
    a, h = _por(der, ancho / 2), _por(arriba, alto / 2)
    return [_suma(centro, _por(a, -1), _por(h, -1)), _suma(centro, a, _por(h, -1)),
            _suma(centro, a, h), _suma(centro, _por(a, -1), h)]


def _caja(m, centro, frente, ancho, alto, fondo, mat):
    """A box with housing UVs (ID 0). `frente` = the direction it faces."""
    arriba = (0.0, 1.0, 0.0)
    der = _norm((frente[2], 0.0, -frente[0]))
    uv, sin_id = _rect_uv(UV_CARCASA), [(0.0, 1.0)] * 4
    for n, d1, d2, w, h, prof in ((frente, der, arriba, ancho, alto, fondo),
                                  (der, _por(frente, -1), arriba, fondo, alto, ancho),
                                  (arriba, der, _por(frente, -1), ancho, fondo, alto)):
        for s in (1, -1):
            c = _suma(centro, _por(n, s * prof / 2))
            m.quad(_cara(c, d1, d2, w, h), uv, sin_id, mat)


def _lampara(m, centro, frente, luz_id, rojo, mat, mat_destello):
    """The lens (the face with the ID) and its glow (billboard with the corners in UV2)."""
    arriba = (0.0, 1.0, 0.0)
    der = _norm((frente[2], 0.0, -frente[0]))
    c = _suma(centro, _por(frente, 0.01))
    m.quad(_cara(c, der, arriba, LADO_LAMPARA, LADO_LAMPARA), _rect_uv(UV_ROJO if rojo else UV_VERDE),
           [(float(luz_id), 0.1)] * 4, mat)
    d, k = _suma(centro, _por(frente, 0.03)), LADO_DESTELLO / 2
    m.quad(_cara(d, der, arriba, LADO_DESTELLO, LADO_DESTELLO),
           _rect_uv(UV_DESTELLO_ROJO if rojo else UV_DESTELLO_VERDE),
           [(-k, -k), (k, -k), (k, k), (-k, k)], mat_destello)


def semaforo_boxes(nombre, base, frente, id_verde, id_rojo):
    """Pole + housing + red on top and green below, facing whoever is arriving."""
    m = Malla(nombre)
    _caja(m, _suma(base, (0.0, ALTO_POSTE_BOXES / 2, 0.0)), frente, 0.12, ALTO_POSTE_BOXES, 0.12, MAT_BOXES)
    centro = _suma(base, (0.0, ALTO_POSTE_BOXES + 0.45, 0.0))
    _caja(m, centro, frente, 0.6, 0.9, 0.25, MAT_BOXES)
    cara = _suma(centro, _por(frente, 0.125))
    _lampara(m, _suma(cara, (0.0, 0.2, 0.0)), frente, id_rojo, True, MAT_BOXES, MAT_BOXES_ROJO)
    _lampara(m, _suma(cara, (0.0, -0.2, 0.0)), frente, id_verde, False, MAT_BOXES, MAT_BOXES_VERDE)
    return m, centro


def semaforo_salida(base, frente):
    """Four lamps stacked vertically: 1-3 red, 4 green (like Enna)."""
    m = Malla(MALLA_SALIDA)
    _caja(m, _suma(base, (0.0, ALTO_POSTE_SALIDA / 2, 0.0)), frente, 0.15, ALTO_POSTE_SALIDA, 0.15, MAT_SALIDA)
    centro = _suma(base, (0.0, ALTO_POSTE_SALIDA + 0.9, 0.0))
    _caja(m, centro, frente, 0.55, 1.8, 0.3, MAT_SALIDA)
    cara = _suma(centro, _por(frente, 0.15))
    for i, dy in enumerate((0.6, 0.2, -0.2, -0.6), start=1):
        rojo = i < 4
        _lampara(m, _suma(cara, (0.0, dy, 0.0)), frente, i, rojo, MAT_SALIDA,
                 MAT_SALIDA_ROJO if rojo else MAT_SALIDA_VERDE)
    return m, centro


# ── where they go ─────────────────────────────────────────────────────────────────────────
def _en_la_calle(linea, dist):
    """Point and direction of travel `dist` metres from the start of the lane."""
    acum = 0.0
    for a, b in zip(linea, linea[1:]):
        paso = math.dist(a, b)
        if acum + paso >= dist and paso > 0:
            k = (dist - acum) / paso
            return _suma(a, _por(_suma(b, _por(a, -1)), k)), _norm((b[0] - a[0], 0.0, b[2] - a[2]))
        acum += paso
    return linea[-1], _norm((linea[-1][0] - linea[-2][0], 0.0, linea[-1][2] - linea[-2][2]))


def _lado_pista(p, lateral, trazada):
    """+1 if the track lies towards `lateral`, −1 if it lies on the other side."""
    q = min(trazada, key=lambda t: (t[0] - p[0]) ** 2 + (t[2] - p[2]) ** 2)
    return 1 if (q[0] - p[0]) * lateral[0] + (q[2] - p[2]) * lateral[2] > 0 else -1


def _junto_al_muro(p, lateral, col):
    """The foot of the pole, right against the wall on that side (or at LATERAL_SIN_MURO if there is none)."""
    d = col.muro(_suma(p, (0.0, 0.5, 0.0)), lateral, maxd=15.0) if col is not None else None
    dist = (d - HOLGURA_MURO) if d else LATERAL_SIN_MURO
    pie = _suma(p, _por(lateral, dist))
    if col is not None:
        h = col.debajo(pie[0], pie[2], p[1])
        if h:
            pie = (pie[0], h[1], pie[2])
    return pie, dist, bool(d)


SUPERFICIES_DE_BOXES = {"PIT", "PITS"}


def _tramo_de_boxes(calle, acum, col):
    """Where the PIT ground starts and ends in the trimmed lane (metres).

    Measured in the Charlotte by «13x»: the trimmed lane is 1,471 m long, but the `PIT` ground
    only goes from 219 to 681 m; before and after it is `APRON`. And the author put his pit
    light box at 215 m: the light goes where the pit ground starts, not at a fixed distance
    from the lane mouth."""
    if col is not None:
        dentro = [i for i, p in enumerate(calle)
                  if (col.debajo(p[0], p[2], p[1]) or ("--",))[0] in SUPERFICIES_DE_BOXES]
        if dentro:
            return acum[dentro[0]], acum[dentro[-1]]
    return DIST_A_LA_BOCA, acum[-1] - DIST_A_LA_BOCA


def colocar(t: dict) -> dict:
    """The three meshes from what `ac_trazado.construir` already provides: the trimmed lane,
    the racing line, the finish line (`AC_TIME_0_L/R`) and the collision."""
    calle, trazada, col = t["boxes_linea"], t["trazada"], t.get("colision")
    if len(calle) < 3:
        return {"motivo": "no pit lane"}
    fuera = {}
    acum = [0.0]
    for a, b in zip(calle, calle[1:]):
        acum.append(acum[-1] + math.dist(a, b))
    entrada, salida = _tramo_de_boxes(calle, acum, col)
    for nombre, dist, id_v, id_r in ((MALLA_ENTRADA, entrada, ID_ENTRADA_VERDE, ID_ENTRADA_ROJO),
                                     (MALLA_BOXES_SALIDA, salida, ID_SALIDA_VERDE, ID_SALIDA_ROJO)):
        p, marcha = _en_la_calle(calle, dist)
        lateral = (-marcha[2], 0.0, marcha[0])
        lateral = _por(lateral, _lado_pista(p, lateral, trazada))     # towards the track: the pit wall
        pie, d, con_muro = _junto_al_muro(p, lateral, col)
        if not con_muro:
            # no wall towards the track, so the other side: never a pole on top of the asphalt
            pie, d, con_muro = _junto_al_muro(p, _por(lateral, -1), col)
        m, centro = semaforo_boxes(nombre, pie, _por(marcha, -1), id_v, id_r)
        fuera[nombre] = {"malla": m, "centro": centro, "lateral_m": round(d, 1), "muro": con_muro,
                         "a_m": round(dist)}
    tiempos = t["marcas"].get("tiempos", {})
    izq, der = tiempos.get("AC_TIME_0_L"), tiempos.get("AC_TIME_0_R")
    if izq and der:
        # the side of the finish line furthest from the inside of the oval: where the flag is
        cx = sum(p[0] for p in trazada) / len(trazada)
        cz = sum(p[2] for p in trazada) / len(trazada)
        ext, inte = (der, izq) if math.dist((der[0], der[2]), (cx, cz)) > math.dist((izq[0], izq[2]), (cx, cz)) else (izq, der)
        hacia_fuera = _norm((ext[0] - inte[0], 0.0, ext[2] - inte[2]))
        i = min(range(len(trazada)), key=lambda k: math.dist(trazada[k], ext))
        a, b = trazada[i - 1], trazada[i]
        marcha = _norm((b[0] - a[0], 0.0, b[2] - a[2]))
        pie = _suma(ext, _por(hacia_fuera, 1.5))
        if col is not None:
            h = col.debajo(pie[0], pie[2], ext[1])
            if h:
                pie = (pie[0], h[1], pie[2])
        m, centro = semaforo_salida(pie, _por(marcha, -1))
        fuera[MALLA_SALIDA] = {"malla": m, "centro": centro}
    return fuera


# ── the events XML, with the Enna / Daytona structure ──────────────────────────────────────
def xml_tracklights(colocadas: dict) -> str:
    def pos(n):
        c = colocadas.get(n, {}).get("centro")
        return f'{c[0]:.1f} {c[1]:.1f} {c[2]:.1f}' if c else "0 0 0"

    s = ['<?xml version="1.0" encoding="utf-8" ?>', "<TRACKLIGHTS>", ""]
    if MALLA_SALIDA in colocadas:
        g = pos(MALLA_SALIDA)
        for i in range(1, 5):
            glow = MAT_SALIDA_VERDE if i == 4 else MAT_SALIDA_ROJO
            s.append(f'\t<LIGHT name="StartLight{i}" mesh="{MALLA_SALIDA}.meb" material="{MAT_SALIDA}" '
                     f'glowmaterial="{glow}" glowtestposition="{g}" ID="{i}" intensity="0.0"/>')
        s += ['\t<EVENT type="Countdown" param="4" lights="StartLight1: 100.0, 0.1"/>',
              '\t<EVENT type="Countdown" param="3" lights="StartLight2: 100.0, 0.1"/>',
              '\t<EVENT type="Countdown" param="2" lights="StartLight3: 100.0, 0.1"/>',
              '\t<EVENT type="Countdown" param="1" lights="StartLight4: 100.0, 0.1 ; StartLight1: 0.0, 0.2; '
              'StartLight2: 0.0, 0.2; StartLight3: 0.0, 0.2"/>', ""]
    if MALLA_ENTRADA in colocadas and MALLA_BOXES_SALIDA in colocadas:
        e, x = pos(MALLA_ENTRADA), pos(MALLA_BOXES_SALIDA)
        s += [f'\t<LIGHT name="PitEntryGreen" mesh="{MALLA_ENTRADA}.meb" material="{MAT_BOXES}" '
              f'glowmaterial="{MAT_BOXES_VERDE}" glowtestposition="{e}" ID="{ID_ENTRADA_VERDE}" intensity="0.0"/>',
              f'\t<LIGHT name="PitEntryRed" mesh="{MALLA_ENTRADA}.meb" material="{MAT_BOXES}" '
              f'glowmaterial="{MAT_BOXES_ROJO}" glowtestposition="{e}" ID="{ID_ENTRADA_ROJO}" intensity="0.0"/>',
              f'\t<LIGHT name="PitExitGreen" mesh="{MALLA_BOXES_SALIDA}.meb" material="{MAT_BOXES}" '
              f'glowmaterial="{MAT_BOXES_VERDE}" glowtestposition="{x}" ID="{ID_SALIDA_VERDE}" intensity="0.0"/>',
              f'\t<LIGHT name="PitExitRed" mesh="{MALLA_BOXES_SALIDA}.meb" material="{MAT_BOXES}" '
              f'glowmaterial="{MAT_BOXES_ROJO}" glowtestposition="{x}" ID="{ID_SALIDA_ROJO}" intensity="0.0"/>',
              '\t<EVENT type="PitEntry" param="1" lights="PitEntryGreen: 100.0, ; PitEntryRed: 0.0"/>',
              '\t<EVENT type="PitEntry" param="2" lights="PitEntryRed: 100.0 ; PitEntryGreen: 0.0"/>',
              '\t<EVENT type="PitExit" param="1" lights="PitExitGreen: 100.0, ; PitExitRed: 0.0"/>',
              '\t<EVENT type="PitExit" param="2" lights="PitExitRed: 100.0 ; PitExitGreen: 0.0"/>', ""]
    s.append("</TRACKLIGHTS>")
    return "\n".join(s) + "\n"


# ── materials: Enna's (decoded from its .bmt files with bmt_read.py), our own textures ─────
def _param_tex(nombre, ruta):
    return (f'  <shaderparam name="{nombre}" type="EPT_TEXTURE">\n    <type t="ET_STANDARD" />\n'
            f'    <value v="{ruta}" />\n  </shaderparam>\n')


def _param_f(nombre, v):
    return f'  <shaderparam name="{nombre}" type="EPT_F32">\n    <value v="{v}" />\n  </shaderparam>\n'


def mtx(nombre_mat: str, pista: str) -> str:
    t = lambda f: f"tracks\\textures\\{pista}\\{f}"   # noqa: E731
    if nombre_mat in (MAT_SALIDA, MAT_BOXES):
        cuerpo = (_param_tex("diffuseTexture", t(TEX_DIFUSO)) + _param_tex("emissiveTexture", t(TEX_EMISIVO))
                  + _param_f("minSpecPower", 1) + _param_f("maxSpecPower", 32) + _param_f("globalSpecularFactor", 0.3))
        return (f'<material VERSION="v1.0.0.1" name="{nombre_mat}" shader="Render\\Shaders\\basic.fx" technique="Basic" '
                f'supportsSpecialisedLighting="true" fog="false" antialias="1" numparams="5" cull="EBFCT_ANTICLOCKWISE">\n'
                + cuerpo +
                '  <depthparams>\n    <enabled e="true" />\n    <writeenabled w="true" />\n  </depthparams>\n'
                '  <alphablendparams>\n    <enabled e="false" />\n  </alphablendparams>\n'
                '  <define name="USE_LIGHT_CONTROL" />\n</material>\n')
    # glow: ADDITIVE blending. The tag names come from the hash in Enna's .bmt
    # (`mtx2bmt.hash_string`): sourceblend/sb, destblend/db, blendop/bo.
    return (f'<material VERSION="v1.0.0.1" name="{nombre_mat}" shader="Render\\Shaders\\lightglow_billboard.fx" '
            f'technique="Lightglow" supportsSpecialisedLighting="false" fog="false" antialias="1" numparams="2" '
            f'cull="EBFCT_ANTICLOCKWISE">\n'
            + _param_tex("diffuseTexture", t(TEX_DESTELLO)) + _param_f("distanceScale", 0) +
            '  <depthparams>\n    <enabled e="false" />\n    <writeenabled w="false" />\n  </depthparams>\n'
            '  <alphablendparams>\n    <enabled e="true" />\n    <sourceblend sb="EBF_SOURCE_ALPHA" />\n'
            '    <destblend db="EBF_ONE" />\n    <blendop bo="EBO_ADD" />\n  </alphablendparams>\n'
            '  <define name="TRACKSIDE_LIGHT" />\n</material>\n')


MATERIALES = (MAT_SALIDA, MAT_SALIDA_ROJO, MAT_SALIDA_VERDE, MAT_BOXES, MAT_BOXES_ROJO, MAT_BOXES_VERDE)


# The glow profile, measured on Reiza's (Enna's `tracklight_lightflares.dds`): a SMALL star
# in the centre of each half —a ~12 px core with alpha 0.59, falling to 0 at around 40 px—
# and the rest transparent. Mean alpha 0.034 (ours, without rays and falling to 0 over
# 32 px: 0.04).
# 🔴 A gradient that fills the card with alpha 1 in the centre (mean alpha 0.257, 7.7 times
# more, and on both faces) gives, in the menu, with the pit-box camera a few metres from the
# start light, a green flash that covers the screen; on the zoomed TV cameras, half the
# screen red.
NUCLEO_PX, BORDE_PX, ALFA_NUCLEO = 12, 32, 0.59


def _destello(color):
    # ⚠️ ImageMagick 6 does not accept variables in -fx (`r=…;` gives constant alpha): the distance inline
    r = "hypot(i-63.5,j-63.5)"
    fx = (f"{r}<{NUCLEO_PX}?{ALFA_NUCLEO}:"
          f"({r}<{BORDE_PX}?{ALFA_NUCLEO}*pow(1-({r}-{NUCLEO_PX})/{BORDE_PX - NUCLEO_PX},2):0)")
    return ["(", "-size", "128x128", f"xc:{color}", "(", "-size", "128x128", "xc:black", "-fx", fx, ")",
            "-alpha", "off", "-compose", "CopyOpacity", "-composite", ")"]


def texturas(destino: str) -> list:
    """The three textures, drawn here (nobody else's work). DXT5 with mipmaps."""
    os.makedirs(destino, exist_ok=True)
    dds = "-define dds:compression=dxt5 -define dds:mipmaps=8".split()
    lente = lambda color, x0: ["-fill", color, "-draw", f"circle {x0 + 64},64 {x0 + 64},10"]   # noqa: E731
    ordenes = {
        TEX_EMISIVO: ["-size", "256x256", "xc:black", *lente("#ff2010", 0), *lente("#20ff40", 128)],
        TEX_DIFUSO: ["-size", "256x256", "xc:#1c1c1c", *lente("#401010", 0), *lente("#104018", 128)],
        TEX_DESTELLO: [*_destello("#ff3020"), *_destello("#30ff50"), "+append"],
    }
    hechas = []
    for f, o in ordenes.items():
        ruta = os.path.join(destino, f)
        subprocess.run([*_R.IM_CONVERT, *o, "-alpha", "set", *dds, ruta], check=True, capture_output=True)
        hechas.append(ruta)
    return hechas


# ── Blender ───────────────────────────────────────────────────────────────────────────────
def crear_en_blender(colocadas: dict, coleccion=None):
    import bpy
    import aiw_read as A

    col = coleccion or bpy.context.scene.collection
    hechas = []
    for info in colocadas.values():
        m = info.get("malla")
        if m is None:
            continue
        # 🔴 Origin AT the light and vertices in local space, like Enna, COTA and Daytona
        # (±0.5 m). With the vertices in world coordinates and the origin at the centre of the
        # circuit (x ≈ 232 m), at night a huge red or green sheet could be seen in the sky,
        # only in one area, which suddenly disappeared. It was the only thing in which this
        # light differed from the three references: the XML and the glow material are identical.
        c = info.get("centro") or m.v[0]
        me = bpy.data.meshes.new(m.nombre)
        me.from_pydata([A.to_blender(tuple(a - b for a, b in zip(v, c))) for v in m.v], [], m.caras)
        uv1, uv2 = me.uv_layers.new(name="UVMap"), me.uv_layers.new(name="UV2")
        for loop in me.loops:
            u, v = m.uv1[loop.vertex_index]
            uv1.data[loop.index].uv = (u, 1.0 - v)      # the exporter writes 1 − v
            u, v = m.uv2[loop.vertex_index]
            uv2.data[loop.index].uv = (u, 1.0 - v)
        for nombre_mat in m.materiales:
            mat = bpy.data.materials.get(nombre_mat) or bpy.data.materials.new(nombre_mat)
            mat["gr_semaforo"] = 1
            me.materials.append(mat)
        for poly, k in zip(me.polygons, m.mat):
            poly.material_index = k
        me.update()
        # 🔴 The exporter writes ONLY UV0 unless the mesh says which slots it carries
        # (`meb_export_settings.uv1..uv6`, from 1): without this the light ID does not reach
        # the .meb (measured: `Startlight_LODA` with IDs []).
        me.meb_export_settings.uv1 = 1
        me.meb_export_settings.uv2 = 2
        obj = bpy.data.objects.new(m.nombre, me)
        obj.location = A.to_blender(c)
        col.objects.link(obj)
        hechas.append(m.nombre)
    return hechas


def escribir(salida: str, pista: str, colocadas: dict) -> dict:
    """After the scene export: our own MTX files (the exporter cannot write additive
    blending), the textures and the events XML."""
    carpeta = os.path.join(salida, "Tracks", pista)
    for nombre_mat in MATERIALES:
        # ⚠️ the exporter writes them in UPPERCASE; on Linux another name would be ANOTHER file
        open(os.path.join(carpeta, f"{nombre_mat.upper()}.mtx"), "w", encoding="utf-8").write(mtx(nombre_mat, pista))
    tex = texturas(os.path.join(salida, "Tracks", "textures", pista))
    xml = os.path.join(salida, "Tracks", "_data", "tracklights", f"{pista}.xml")
    os.makedirs(os.path.dirname(xml), exist_ok=True)
    open(xml, "w", encoding="utf-8").write(xml_tracklights(colocadas))
    return {"mtx": len(MATERIALES), "texturas": len(tex), "xml": xml}


# ── check what was EXPORTED, not what was requested ────────────────────────────────────────
ESPERADOS = {MALLA_SALIDA: {1, 2, 3, 4}, MALLA_ENTRADA: {ID_ENTRADA_VERDE, ID_ENTRADA_ROJO},
             MALLA_BOXES_SALIDA: {ID_SALIDA_VERDE, ID_SALIDA_ROJO}}


def ids_de_malla(ruta: str) -> set:
    """The integer `u` values > 0 of the 2nd UV of a `.meb` (the light ID the engine will read)."""
    import struct
    b = open(ruta, "rb").read()
    # ⚠️ The name is padded to a multiple of 4, and the exporter adds 4 MORE zeros if it
    # already was one (meb_writer.write_mesh_name). «Skipping zeros» does not work: a vertex
    # count whose first byte is 0 (3,584 = 0x0E00) swallows the counter and reads garbage.
    nombre = b[8:b.index(b"\0", 8)]
    o = 8 + len(nombre) + ((4 - len(nombre) % 4) % 4) + (4 if len(nombre) % 4 == 0 else 0)
    n, nparams, _nmat = struct.unpack_from("<iii", b, o)
    o += 12 + 40
    tam = {(2, 0, 0): 12, (2, 2, 0): 12, (4, 6, 0): 4, (2, 4, 0): 12, (2, 5, 0): 12, (0, 3, 3): 4, (20, 0, 0): 12}
    ids = set()
    for _ in range(nparams):
        h = struct.unpack_from("<3i", b, o)
        o += 12
        t = tam.get(h) or (8 if h[0] == 1 else 12)
        if h[1] == 3 and h[2] == 1 and h[0] in (1, 2):          # UV (or UVW) number 1 = the 2nd one
            for k in range(n):
                u = struct.unpack_from("<f", b, o + k * t)[0]
                if u > 0 and float(u).is_integer():
                    ids.add(int(u))
        o += n * t
    return ids


def radio_local(ruta: str) -> float:
    """Maximum distance of a vertex from the object's origin, in the exported `.meb`."""
    import struct
    b = open(ruta, "rb").read()
    nombre = b[8:b.index(b"\0", 8)]
    o = 8 + len(nombre) + ((4 - len(nombre) % 4) % 4) + (4 if len(nombre) % 4 == 0 else 0)
    n, nparams, _nmat = struct.unpack_from("<iii", b, o)
    o += 12 + 40
    tam = {(2, 0, 0): 12, (2, 2, 0): 12, (4, 6, 0): 4, (2, 4, 0): 12, (2, 5, 0): 12, (0, 3, 3): 4, (20, 0, 0): 12}
    for _ in range(nparams):
        h = struct.unpack_from("<3i", b, o)
        o += 12
        t = tam.get(h) or (8 if h[0] == 1 else 12)
        if h == (2, 0, 0):
            return max(math.sqrt(sum(c * c for c in struct.unpack_from("<3f", b, o + k * t))) for k in range(n))
        o += n * t
    return float("inf")


RADIO_LOCAL_MAX = 8.0      # the exit light pole is 4.5 m tall; the references, ±0.5 m


def comprobar(salida: str, pista: str) -> tuple:
    carpeta = os.path.join(salida, "Tracks", pista)
    xml = os.path.join(salida, "Tracks", "_data", "tracklights", f"{pista}.xml")
    if not os.path.exists(xml):
        return False, "there is no _data/tracklights"
    mebs = {f.lower(): f for f in os.listdir(carpeta)}
    partes = []
    for malla, esperados in ESPERADOS.items():
        f = mebs.get(f"{malla.lower()}.meb")
        if not f:
            return False, f"{malla}.meb was NOT exported"
        ids = ids_de_malla(os.path.join(carpeta, f))
        if ids != esperados:
            return False, f"{malla}: IDs in the .meb {sorted(ids)}, expected {sorted(esperados)}"
        r = radio_local(os.path.join(carpeta, f))
        if r > RADIO_LOCAL_MAX:
            return False, f"{malla}: vertices {r:.0f} m from its origin (in world coordinates, not local)"
        partes.append(f"{malla} {sorted(ids)} r={r:.1f} m")
    for nombre_mat in MATERIALES:
        f = mebs.get(f"{nombre_mat.lower()}.mtx")
        texto = open(os.path.join(carpeta, f), encoding="utf-8").read() if f else ""
        if "USE_LIGHT_CONTROL" not in texto and "TRACKSIDE_LIGHT" not in texto:
            return False, f"{nombre_mat}.mtx is not ours (another step overwrote it)"
    return True, "light IDs in the exported .meb: " + " · ".join(partes)
