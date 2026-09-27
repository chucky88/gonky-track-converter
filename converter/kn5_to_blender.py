"""Blender scene from an Assetto Corsa circuit, with the SAME shape as the AMS1 one.

    blender -b --factory-startup --python kn5_to_blender.py -- \\
        --carpeta <AC circuit> --trazado layout_speedway --tex <textures> --save <scene.blend>

The goal is not «importing a kn5», it is producing the scene that `construir_paquete.py`
already knows how to convert: the same `SMS_AIW_*` curves, the same markers, the same
materials with an image node named after its `.dds`. That way the 12 gates work without
knowing where the circuit comes from. What changes compared with `aiw_to_blender.py`:

| | AMS1 | Assetto Corsa |
|---|---|---|
| geometry | `.GMT` via the addon | `.kn5` with `kn5_read` |
| collision | GUESSED from the `.scn` | `FISICA_AC` collection from `phy*.kn5` |
| edges and walls | come in the AIW | COMPUTED by `ac_trazado.py` |
| grid / pits | `[GRID]`/`[PIT]` from the AIW | `AC_START_n`/`AC_PIT_n` empties |

🔴 Three things copied from the AMS1 pipeline ON PURPOSE, because each of them had a costly
bug that raised no error:

1. **Axes `(x, z, y)`**, the same as `aiw_read.to_blender`. Assetto Corsa and gMotor2 are
   both DirectX Y-up. This is not reasoned out: it is checked by the `gcl ↔ csm` and
   `grid heading` gates, which caught a mirroring that had gone unnoticed across many
   Charlotte conversions.
2. **The racing line is MIRRORED** with respect to the centreline: OMTT negates the offset
   on export (`aiw_read.Waypoint.racing_line`). Passing it as is sends the AI into the wall
   in the corners.
3. **The grid and pit heading comes from the TANGENT** of the racing line, with the
   `parrilla_desde_la_linea` formula (0.0° of measured error), instead of deciphering the
   AC matrix.
"""

import json
import math
import os
import re
import sys

import bpy

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import aiw_read as A  # noqa: E402
import ac_trazado as T  # noqa: E402
import kn5_read as K  # noqa: E402
import rutas as _R  # noqa: E402  (ImageMagick: see rutas.py)

COLECCION_AIW = "SMS_AIW"
COLECCION_FISICA = "FISICA_AC"
TECHO_PARRILLA = A.TECHO_PARRILLA
SIN_CURVAS_EN_OVALOS = True     # see construir_trazada: copied from Texas


def _argv():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    fuera = {}
    for i, x in enumerate(a):
        if x.startswith("--"):
            fuera[x[2:]] = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith("--") else True
    return fuera


def _coleccion(nombre):
    col = bpy.data.collections.get(nombre)
    if col is None:
        col = bpy.data.collections.new(nombre)
        bpy.context.scene.collection.children.link(col)
    return col


def a_blender(p):
    return A.to_blender(p)


# ── materials ─────────────────────────────────────────────────────────────────────────
def material(m: K.Material, tex_dir: str):
    """A Blender material with an image node named AFTER ITS `.dds`.

    It is the contract of `construir_paquete.poner_texturas_propias`: it looks up the name of
    the material's first image in the textures folder and repoints the MTX's diffuse.
    """
    # 🔴 The material's name IS the `.mtx` name, and the exporter does not write it for those
    # containing spaces or dots: `oval line` —the rubber on the oval of the Charlotte by
    # «13x»— and `Tex_4887_0.dds` were left WITHOUT an MTX, and their mesh with a material
    # that does not exist. Only letters, digits and `_`.
    limpio = re.sub(r"[^A-Za-z0-9_]", "_", m.nombre)
    mat = bpy.data.materials.get(limpio) or bpy.data.materials.new(limpio)
    mat.use_nodes = True
    # AC's blend mode (1 = semi-transparent) travels with the material up to
    # `construir_paquete.poner_mezcla_ac`, which copies it to the MTX.
    mat["ac_mezcla"] = int(m.mezcla_alfa)
    tx = m.texturas.get("txDiffuse") or next(iter(m.texturas.values()), None)
    if tx and not any(n.type == "TEX_IMAGE" for n in mat.node_tree.nodes):
        img = bpy.data.images.get(tx)
        if img is None:
            ruta = os.path.join(tex_dir, tx)
            if os.path.exists(ruta):
                img = bpy.data.images.load(ruta, check_existing=True)
            else:
                img = bpy.data.images.new(tx, 8, 8)
            img.name = tx
        nodo = mat.node_tree.nodes.new("ShaderNodeTexImage")
        nodo.image = img
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            mat.node_tree.links.new(nodo.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# ── meshes ────────────────────────────────────────────────────────────────────────────
MARCA_AC = re.compile(r"^AC_(START|PIT|TIME|HOTLAP_START)_", re.I)
INVISIBLE_DDS = "marca_invisible.dds"


def material_invisible(tex_dir):
    """A material with an alpha-0 texture: the mesh stays in the scene and is not visible.

    `construir_paquete.poner_alfatest` gives it `USE_ALPHATEST` when it measures its alpha (mean 0).
    """
    import subprocess
    mat = bpy.data.materials.get("MARCA_AC_INVISIBLE")
    if mat:
        return mat
    ruta = os.path.join(tex_dir, INVISIBLE_DDS)
    if not os.path.exists(ruta):
        subprocess.run([*_R.IM_CONVERT, "-size", "16x16", "xc:none", "-define", "dds:compression=dxt5",
                        "-define", "dds:mipmaps=0", ruta], check=True)
    fake = K.Material(nombre="MARCA_AC_INVISIBLE", shader="ksPerPixelAT",
                      texturas={"txDiffuse": INVISIBLE_DDS})
    return material(fake, tex_dir)


def importar(ruta_kn5: str, col, tex_dir: str, excluir=lambda nombre: False, props=None,
             solo_dibujables=False) -> dict:
    """All the meshes of a `.kn5`, with UVs, their own normals and material.

    `solo_dibujables`: drops those the author marks as invisible or non-renderable (the
    asphalt physics `1road_*`, the `1WALL_invisible*`, the seams of `tarphys.kn5`). For the
    VISIBLE geometry; the collision wants all of them.
    """
    r = K.leer(ruta_kn5, con_geometria=True)
    mats = [material(m, tex_dir) for m in r["materiales"]]
    hechas = saltadas = verts = ocultas = 0
    signos = {+1: 0, -1: 0}
    for mk in r["mallas"]:
        if solo_dibujables and not (mk.visible and mk.dibuja):
            ocultas += 1
            continue
        # 🔴 The AC editor MARKERS. Symptom: red «no entry» cubes in the pits of the Charlotte
        # by «13x». `AC_START_n`, `AC_PIT_n`, `AC_TIME_n`… are 2.5 m cubes with `node.dds`
        # («FRONTAL», «TOP» arrow, no entry): AC recognises them by name and does NOT draw
        # them. They become visible once the parents' transform is composed; without composing
        # it they are piled up where they cannot be seen. Their position is still used for the
        # grid and the pits (`ac_trazado.vacios`). `AC_POBJECT_*` (physical objects, a cone)
        # and `AC_CREW_*` are NOT touched: in that mod they are the pit crew figures.
        # 🔴 And they are NOT removed: they are made INVISIBLE. Measured in the Charlotte by
        # «13x»: without them loading hangs (three tests) and with them it loads (two tests),
        # with the SAME AIW. We do not know what the game needs them for; it is a measured
        # fact, without an explanation. See docs/LESSONS.md.
        invisible = solo_dibujables and MARCA_AC.match(mk.nombre)
        if excluir(mk.nombre) or not mk.caras:
            saltadas += 1
            continue
        me = bpy.data.meshes.new(mk.nombre)
        # 🔴 FACE WINDING. The (x, z, y) conversion swaps two axes and inverts the handedness:
        # in AMS1 that left the ground facing up, but with AC, uncorrected, it leaves it facing
        # DOWN. Measured uncorrected: collision 0 faces up / 24,521 down, visible asphalt
        # 0 / 14,193. AMS2 discards back faces (`cull=ANTICLOCKWISE`): the asphalt would look
        # transparent and you would fall through it.
        # ⚠️ Flipping the normals to match the faces HIDES it (579 of 581 meshes): everything
        # stays consistent… and upside down. It is not a winding problem but a MIRRORING, and
        # it is fixed at the source, in `kn5_read.ESPEJO_Z`; the author's normals then match
        # on their own.
        me.from_pydata([a_blender(p) for p in mk.pos], [], mk.caras)
        me.update()
        me.validate(verbose=False)
        if me.vertices and len(me.vertices) == len(mk.pos):
            uv = me.uv_layers.new(name="UVMap")
            for loop in me.loops:
                u, v = mk.uv[loop.vertex_index]
                uv.data[loop.index].uv = (u, 1.0 - v)
            # The author's normals, with their DIRECTION checked against the faces: the
            # (x, z, y) conversion swaps two axes and inverts the orientation. Same criterion
            # as the GMT importer patch.
            nor = [a_blender(n) for n in mk.nor]
            acuerdo = 0.0
            for poly in me.polygons:
                pn = poly.normal
                for vi in poly.vertices:
                    n = nor[vi]
                    acuerdo += n[0] * pn.x + n[1] * pn.y + n[2] * pn.z
            s = -1.0 if acuerdo < 0 else 1.0
            signos[int(s)] += 1
            me.normals_split_custom_set_from_vertices([(n[0] * s, n[1] * s, n[2] * s)
                                                       for n in nor])
        if invisible:
            me.materials.append(material_invisible(tex_dir))
        elif 0 <= mk.material < len(mats):
            me.materials.append(mats[mk.material])
        for poly in me.polygons:
            poly.use_smooth = True
        obj = bpy.data.objects.new(mk.nombre, me)
        for k, v in (props or {}).items():
            obj[k] = v
        col.objects.link(obj)
        hechas += 1
        verts += len(mk.pos)
    return {"mallas": hechas, "saltadas": saltadas, "vertices": verts, "ocultas": ocultas,
            "materiales": len(mats), "signos": signos}


# ── the racing line, with the AMS1 shape ──────────────────────────────────────────────
def linea(nombre, puntos_ac, col, cerrada=False):
    me = bpy.data.meshes.new(nombre)
    vs = [a_blender(p) for p in puntos_ac]
    es = [(i, i + 1) for i in range(len(vs) - 1)]
    if cerrada and len(vs) > 2:
        es.append((len(vs) - 1, 0))
    me.from_pydata(vs, es, [])
    me.update()
    obj = bpy.data.objects.new(nombre, me)
    col.objects.link(obj)
    return obj


def atributo_entero(obj, nombre, valores):
    attr = obj.data.attributes.new(name=nombre, type="INT", domain="POINT")
    for i, v in enumerate(valores):
        attr.data[i].value = int(v)


def _tangente(puntos, k):
    a, b = puntos[k], puntos[(k + 1) % len(puntos)]
    dx, dz = b[0] - a[0], b[2] - a[2]
    L = math.hypot(dx, dz) or 1.0
    return dx / L, dz / L


def _mas_cercano(puntos, p):
    return min(range(len(puntos)),
               key=lambda i: (puntos[i][0] - p[0]) ** 2 + (puntos[i][2] - p[2]) ** 2)


def puesto(i, pos, linea_ref):
    """Placement with the heading of the reference line's TANGENT at that point.

    Formula from `aiw_read.parrilla_desde_la_linea`: `yaw = atan2(dx, dz) + π`, which with
    `blender_rotation()` (`-yaw + π`) leaves the slot facing forward. Measured on Charlotte:
    0.0° of error.
    """
    k = _mas_cercano(linea_ref, pos)
    dx, dz = _tangente(linea_ref, k)
    return A.Placement(i, tuple(pos), (0.0, math.atan2(dx, dz) + math.pi, 0.0))


# 🔴 AT THE AMS1 DENSITY. The Assetto Corsa racing line has a point every 1.6 m; the AMS1
# Charlotte one, one every 5.15 m (463 over 2,386 m). The corner classifier measures its
# smoothing window in WAYPOINTS, not metres, so at 1.6 m the window is three times shorter
# and noise counts as a corner: it produced **186 corners** on an oval that has 4. And it is
# not just a number in the TRD: that same classification sets `corner_type`/`corner_state`
# on the centreline, which is what the AI uses to brake. Instead of retuning thresholds
# measured with AMS1, it is given the density they were measured with. Copy what works.
ESPACIADO_AMS1 = 5.15
CENTRAL_ASFALTO = False     # `--central-asfalto` (see construir_trazada); one novelty per version
ANCHO_ASFALTO = False       # `--ancho-asfalto`: the width the AI sees, without the apron (like Daytona)
PARRILLA_EN_META = False    # `--parrilla-en-meta`: the author's grid, moved to the main straight
# `--parrilla-de <trazado>` (measured case: the Charlotte Roval): the grid is formed with the racing
# line of ANOTHER layout of the same circuit. On the Roval, the 290 m before the finish line contain
# the chicane on the straight (the racing line moves up to 25 m away from the oval between 3,316 and
# 3,500 m): half the grid fell inside it, crooked, with slot 14 1.5 m from the edge. The finish line
# (`AC_TIME_0`) is the SAME in both layouts, so the grid forms on the oval straight, as in the real race.
PARRILLA_DE = None


def _indices_cada(puntos, paso):
    """Indices of `puntos` spaced ~`paso` metres apart along the route."""
    idx, acum = [0], 0.0
    for k in range(1, len(puntos)):
        acum += math.dist((puntos[k - 1][0], puntos[k - 1][2]), (puntos[k][0], puntos[k][2]))
        if acum >= paso:
            idx.append(k)
            acum = 0.0
    return idx


def construir_trazada(t: dict, col, oval: bool = False) -> dict:
    tr = t["trazada"]
    sel = _indices_cada(tr, ESPACIADO_AMS1)
    # 🔴 The centreline, SMOOTHED. The midpoint between the edges snaked: where the apron
    # widens for the pit entry the width jumps from 15 to 41 m, the centreline goes with it,
    # and each wiggle counted as a corner (17 on an oval with 4, already resampled). The AMS1
    # centreline was smooth by construction. The lateral OFFSET is smoothed over ±7 samples
    # (≈ ±45 m); the edges stay where they are, since they are the real ones.
    VENT = 7
    caja = lambda x: [sum(x[(j + d) % len(x)] for d in range(-VENT, VENT + 1)) / (2 * VENT + 1)   # noqa: E731
                      for j in range(len(x))]
    tope_i = tope_d = None
    if (CENTRAL_ASFALTO or ANCHO_ASFALTO) and t.get("colision") is not None:
        import statistics
        bc = T.bordes_carrera(t["colision"], tr, sel)
        mi_c = statistics.median(bc[k][0] for k in sel)
        md_c = statistics.median(bc[k][1] for k in sel)
        tope_i = lambda k: min(bc[k][0], T.TOPE_ANCHO_CENTRAL * mi_c)   # noqa: E731
        tope_d = lambda k: min(bc[k][1], T.TOPE_ANCHO_CENTRAL * md_c)   # noqa: E731
    if CENTRAL_ASFALTO and t.get("colision") is not None:
        # 🔴 The centreline, from the RACING asphalt (no apron or pits), each side capped
        # at 1.3× its usual width and smoothed TWICE: a moving average of a step is a ramp
        # with two corners, and each corner was a 7-12° kink that the AI read as a bend
        # (Charlotte by «13x»: 25 kinks > 2°, the worst 11.9°). Measured outside Blender
        # with the same racing line: maximum kink 0.5°, none > 2°.
        crudo = [(tope_i(k) - tope_d(k)) / 2.0 for k in sel]
        liso = caja(caja(crudo))
    else:
        crudo = [(t["bordes"][k][0] - t["bordes"][k][1]) / 2.0 for k in sel]
        liso = caja(crudo)
    centro, cut_i, cut_d, wall_i, wall_d, reflejada = [], [], [], [], [], []
    for j, k in enumerate(sel):
        p = tr[k]
        dx, dz = _tangente(tr, k)
        ix, iz = -dz, dx                               # «left», in the ground plane
        bi, bd, mi, md = t["bordes"][k]
        c = (p[0] + ix * liso[j], p[1], p[2] + iz * liso[j])
        centro.append(c)
        # 🔴 The track WIDTH the AI sees (`wp_width`) comes from these lines. With the
        # apron included, the Charlotte told it 23.3 m median (up to 46.7); Daytona, 11.2,
        # only the racing asphalt, and it leaves the apron as «can be driven on» in `dwidth`
        # (up to 30 m). With `--ancho-asfalto`, the same: the cut at the racing asphalt and
        # the walls as they were. The AI uses this width to look for alternative lines.
        ci, cd = (tope_i(k), tope_d(k)) if (ANCHO_ASFALTO and tope_i) else (bi, bd)
        cut_i.append((p[0] + ix * ci, p[1], p[2] + iz * ci))
        cut_d.append((p[0] - ix * cd, p[1], p[2] - iz * cd))
        # where there is no wall (the infield), a distant wall: the AI must not hug the edge
        # out of fear of something that does not exist
        mi_ = mi if mi is not None else bi + 20.0
        md_ = md if md is not None else bd + 20.0
        wall_i.append((p[0] + ix * mi_, p[1], p[2] + iz * mi_))
        wall_d.append((p[0] - ix * md_, p[1], p[2] - iz * md_))
        # 🔴 the racing line, MIRRORED with respect to the centreline: OMTT negates the offset
        reflejada.append((2 * c[0] - p[0], p[1], 2 * c[2] - p[2]))

    # 🔴 The margin used to trim the `.gcl` (track limits) came from `wp_width`. With
    # `--ancho-asfalto` that width no longer includes the apron, the margin dropped from 34 to
    # 17.9 m and the apron inside the limits from 94.5 % to 75.3 % (measured): driving on it
    # would have counted as going off. That is why the trim uses the width WITH the apron.
    anchos_con_apron = sorted(max(t["bordes"][k][0] - liso[j], t["bordes"][k][1] + liso[j])
                              for j, k in enumerate(sel))
    bpy.context.scene["gr_margen_gcl"] = anchos_con_apron[int(len(anchos_con_apron) * 0.9)] + 8.0

    obj_c = linea("SMS_AIW_CENTERLINE", centro, col, cerrada=True)
    wps = [A.Waypoint(pos=c) for c in centro]
    tipos, estados = A.classify_corners(wps)
    n_curvas = A.numero_de_curvas(estados)
    # EXPERIMENT, only confirmable on track. Symptom: the AI braked too much in the oval
    # corners. The AIW of Texas —Reiza's oval, which works— carries NO corner data:
    # CornerType/CornerState at 0 in all 1,285 waypoints. The AMS2 AI brakes at corner
    # ENTRY, and the automatic classification left Mountain Peak with 45 entry waypoints
    # versus 55 apex ones (Charlotte, already resampled: 37 versus 146). On an oval we copy
    # Texas. To revert: `SIN_CURVAS_EN_OVALOS = False`.
    if oval and SIN_CURVAS_EN_OVALOS:
        tipos = [0] * len(tipos)
        estados = [0] * len(estados)
    atributo_entero(obj_c, "corner_type", tipos)
    atributo_entero(obj_c, "corner_state", estados)
    linea("SMS_AIW_RACINGLINE", reflejada, col, cerrada=True)
    linea("SMS_AIW_CUTLINE_LEFT", cut_i, col, cerrada=True)
    linea("SMS_AIW_CUTLINE_RIGHT", cut_d, col, cerrada=True)
    linea("SMS_AIW_WALLLINE_LEFT", wall_i, col, cerrada=True)
    linea("SMS_AIW_WALLLINE_RIGHT", wall_d, col, cerrada=True)
    if t["boxes_linea"]:
        linea("SMS_AIW_PITLINE", t["boxes_linea"], col)

    # 🔴 `--parrilla-en-meta`: the author's grid is ~1,000 m from the finish line and the game
    # does not count the lap until the line is crossed (see `ac_trazado.parrilla_en_meta`).
    base = PARRILLA_DE or t
    marcas_parrilla = T.parrilla_en_meta(base) if PARRILLA_EN_META else t["marcas"]["parrilla"]
    ref = base["trazada"] if PARRILLA_DE else tr
    parrilla = [puesto(i, pos, ref) for i, (pos, _m) in
                enumerate(marcas_parrilla[:TECHO_PARRILLA])]
    pit_ref = t["boxes_linea"] or tr
    boxes = [puesto(i, pos, pit_ref) for i, (pos, _m) in enumerate(t["marcas"]["boxes"])]

    n = len(centro)
    espaciado = sum(math.dist((centro[k][0], centro[k][2]),
                              (centro[(k + 1) % n][0], centro[(k + 1) % n][2]))
                    for k in range(n)) / n
    return {"parrilla": parrilla, "boxes": boxes, "centerline": n,
            "curvas": n_curvas, "waypoint_span": espaciado,
            "pitline": len(t["boxes_linea"])}


def marcador(nombre, place, col, tamano=1.2):
    obj = bpy.data.objects.new(nombre, None)
    obj.empty_display_type = "SINGLE_ARROW"
    obj.empty_display_size = tamano
    obj.location = a_blender(place.pos)
    obj.rotation_euler = place.blender_rotation()
    col.objects.link(obj)
    return obj


# 🔴 THE SPAWN HEIGHT. Reiza, in Mid-Ohio, puts the grid, TELEPORT and the 40 pit boxes
# **3.0 m** above the track (measured against its GCL: 2.96-3.04); the game drops the car.
# With 7.5 cm (the AMS1 clearance), in Mountain Peak some ended up at −1 cm: the car spawned
# INSIDE the ground. Measured in the Charlotte by «13x»: at 8 cm it stayed on the loading
# screen; at 2.1 m (raised by accident on top of the editor markers) it loaded first time.
# Mountain Peak only loaded sometimes. Reiza's figure is copied.
ALTURA_SALIDA = 3.0
# 🔴 THE PIT BOXES DO NOT GO AT 3 m. Symptom: on entering the pits the mechanics appeared in
# the air, about 5 m up, and the car was lifted, teleported to the stop and lowered. The 43
# pit boxes came out at 3.00 m, like the grid, and the game's animated crew stands ON the
# box. Official Daytona puts them **0.05 m** above its GCL. The grid stays at 3 m, which
# loads; this is only for pit boxes and garages.
ALTURA_BOXES = 0.05


def posar(puestos, margen=3.0, holgura=ALTURA_SALIDA):
    """Lowers each slot onto the COLLISION surface beneath it (AMS1-style clearance).

    🔴 With the ray cast against THE WHOLE scene (`scene.ray_cast`) anything above the
    asphalt counts: in the Charlotte by «13x» the AC editor markers —2 m cubes right on each
    slot— left the grid **2.4 m in the air**, and an awning or a cable would do the same.
    Only the collision collection counts, which is where the car really rests.
    """
    import mathutils
    col = bpy.data.collections.get(COLECCION_FISICA)
    objs = [o for o in (col.all_objects if col else []) if o.type == "MESH"]
    ok_ = sin = 0
    for p in puestos:
        o = a_blender(p.pos)
        origen = mathutils.Vector((o[0], o[1], o[2] + margen))
        mejor = None
        for ob in objs:
            inv = ob.matrix_world.inverted()
            lo = inv @ origen
            ld = (inv.to_3x3() @ mathutils.Vector((0, 0, -1))).normalized()
            hit, loc, _n, _i = ob.ray_cast(lo, ld)
            if hit:
                w = ob.matrix_world @ loc
                if mejor is None or w.z > mejor.z:
                    mejor = w
        if mejor is not None:
            p.pos = (mejor.x, mejor.z + holgura, mejor.y)
            ok_ += 1
        else:
            sin += 1
    return ok_, sin


def kn5_principal(carpeta):
    """The rule lives in `ac_trazado.kn5_principal` (a single copy)."""
    return T.kn5_principal(carpeta)


def superficie_por_material(piezas, claves) -> dict:
    """AC material → the physical surface that most of its triangles sit on.

    Why: the Charlotte by «13x» came out with its 453 materials as `rz_basic` when the family
    was decided by the START of the name (`ROAD`, `RDHI`, `GRASS`… from AMS1) and here they are
    called `las_road_NoWearLine_02` or `low_grassColmap01_D`. In AC the surface is in the MESH
    name (`1ROAD_0`), and the visible asphalt's material is the same as the physics one
    (`1road_*` and `vis_rd_*` share `las_road_NoWearLine_02`). That is why ALL meshes are
    counted, renderable or not.
    """
    import collections
    cuenta = collections.defaultdict(collections.Counter)
    for p in piezas:
        r = K.leer(p)
        for m in r["mallas"]:
            sup = T.superficie_de(m.nombre, claves)
            if sup and 0 <= m.material < len(r["materiales"]):
                cuenta[r["materiales"][m.material].nombre][sup] += m.indices // 3
    return {n: c.most_common(1)[0][0] for n, c in cuenta.items()}


def _sumar(partes):
    total = {"mallas": 0, "saltadas": 0, "vertices": 0, "materiales": 0, "ocultas": 0,
             "signos": {+1: 0, -1: 0}}
    for r in partes:
        for k in ("mallas", "saltadas", "vertices", "materiales", "ocultas"):
            total[k] += r[k]
        for k in (+1, -1):
            total["signos"][k] += r["signos"][k]
    return total


def principal(carpeta, trazado, tex_dir, fisica=None, semaforos=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.preferences.addon_enable(module="trackcompiler")
    except Exception as e:
        print(f"  (trackcompiler didn't load: {e})")

    resumen = {}
    # 1) visible geometry: ALL the layout's pieces (`models_<trazado>.ini`), or the big
    #    .kn5 + the layout's one when the circuit does not carry that list
    piezas = T.modelos(carpeta, trazado)
    principal_kn5 = piezas[0]
    col_vis = bpy.context.scene.collection
    partes = [importar(p, col_vis, tex_dir, solo_dibujables=True) for p in piezas]
    resumen["geometria"] = _sumar(partes)
    resumen["piezas"] = [(os.path.basename(p), r["mallas"]) for p, r in zip(piezas, partes)]

    # 1b) each material's SURFACE: in AC it is the reliable way to know what the asphalt is
    #     (each author picks the names: `las_road_…`, `low_grassColmap…`)
    sup_ini_ = os.path.join(carpeta, trazado, "data", "surfaces.ini")
    claves_ = set(T.superficies(sup_ini_) if os.path.exists(sup_ini_) else T.SISTEMA_AC) | {"WALL"}
    for nombre_mat, sup in superficie_por_material(piezas, claves_).items():
        mat = bpy.data.materials.get(re.sub(r"[^A-Za-z0-9_]", "_", nombre_mat))
        if mat is not None:
            mat["ac_superficie"] = sup
    resumen["superficies_de_material"] = sum(1 for m in bpy.data.materials if m.get("ac_superficie"))

    # 2) collision separately: `construir_paquete` cooks it, it is not exported as visual
    t = T.construir(carpeta, trazado, fisica)
    col_f = _coleccion(COLECCION_FISICA)
    resumen["fisica_superficies"] = t["superficies_colision"]
    sup_ini = os.path.join(carpeta, trazado, "data", "surfaces.ini")
    claves = set(T.superficies(sup_ini) if os.path.exists(sup_ini) else T.SISTEMA_AC) | {"WALL"}
    no_fisica = lambda n: T.superficie_de(n, claves) is None   # noqa: E731
    if not t["fisica"]:
        # Physics INSIDE the geometry (Charlotte by «13x»): there is no `phy*.kn5`, and the
        # `1ROAD`, `3GRASS`, `1wall`… meshes of each piece are both what you see and what you
        # drive on. Here they DO define the track (limits included): no `solo_colision`.
        # ⚠️ But the main file also carries the ROVAL roads; `construir_paquete` trims that
        # against the racing line (scene flag `ac_fisica_en_geometria`).
        resumen["fisica"] = _sumar([importar(p, col_f, tex_dir, excluir=no_fisica) for p in piezas])
        bpy.context.scene["ac_fisica_en_geometria"] = 1
        resumen["fisica_principal"] = {"mallas": 0}
        return _semaforos(_trazada(resumen, t, trazado), t, semaforos)
    resumen["fisica"] = importar(os.path.join(carpeta, t["fisica"]), col_f, tex_dir)
    # 🔴 AND THE PHYSICS IN THE MAIN FILE. Symptom: when leaving the road the car fell into the
    # void. In Assetto Corsa ANY mesh whose numeric prefix is followed by a declared surface is
    # physics —whichever .kn5 it is in—, and the grass (`3GRASS`, 51 meshes) is in the main
    # file, not in `phyoval.kn5`. Off the asphalt there was no ground. Measured overlap with
    # the oval's collision: grass 3.5 % (the seams), ROAD and PITS 0 % — they are other roads,
    # not duplicates.
    # ⚠️ The rule is «declared surface», not «has a prefix»: `3DPANO` (the background
    # panorama) starts with 3 and is NOT physics; cooked, it would have been a wall of mountains.
    # COLLISION ONLY, not track limits: this also includes the roads of the infield road
    # course, which `surfaces.ini` marks as valid track. Counted as track, the oval would have
    # the infield inside its limits (measured: the limits' box went from 479 to 699 m wide)
    # and cutting through the inside would not count as going off. The author defines the
    # oval's track in `phyoval.kn5`; this is so that the car does not fall into the void.
    extra = importar(principal_kn5, col_f, tex_dir, excluir=no_fisica, props={"solo_colision": 1})
    resumen["fisica_principal"] = extra
    return _semaforos(_trazada(resumen, t, trazado), t, semaforos)


def _semaforos(resumen, t, pedir):
    """Start and pit lights, generated (`generar_semaforos`). Optional while being tested:
    one novelty per version."""
    if not pedir:
        return resumen
    import json
    import generar_semaforos as GS
    colocadas = GS.colocar(t)
    hechas = GS.crear_en_blender(colocadas, _coleccion("SEMAFOROS"))
    bpy.context.scene["gr_semaforos"] = json.dumps(
        {n: {"centro": i["centro"]} for n, i in colocadas.items() if "centro" in i})
    resumen["semaforos"] = ", ".join(
        f"{n} at {[round(x, 1) for x in i['centro']]}"
        + (f" ({i['a_m']} m along the pit lane, {'next to the wall' if i['muro'] else 'NO wall'})" if "a_m" in i else "")
        for n, i in colocadas.items() if "centro" in i) or colocadas.get("motivo", "ninguno")
    return resumen


def es_ovalo(trazado: str) -> bool:
    """⚠️ «oval» is INSIDE «r**oval**»: with `"oval" in nombre` the roval of the Charlotte by
    «13x» would have been treated as an oval, with no corner data for the AI.
    Oval = the name STARTS with «oval», or says «speedway» (Mountain Peak)."""
    t = trazado.lower().replace("layout_", "")
    return t.startswith("oval") or "speedway" in t


def _trazada(resumen, t, trazado):
    # 3) the racing line with the AMS1 shape
    col_a = _coleccion(COLECCION_AIW)
    es_oval = es_ovalo(trazado)
    tz = construir_trazada(t, col_a, oval=es_oval)
    posados, sin_suelo = posar(tz["parrilla"])
    pb, sb = posar(tz["boxes"], holgura=ALTURA_BOXES)
    for i, g in enumerate(tz["parrilla"]):
        marcador(f"SMS_AIW_START_{i}", g, col_a)
        # TELEPORT = a copy of the grid, like Mid-Ohio (40 of 40 identical). The AC pipeline
        # left it EMPTY; the AMS1 one fills it from the original AIW.
        marcador(f"SMS_AIW_TELEPORT_{i}", g, col_a)
    for i, b in enumerate(tz["boxes"]):
        marcador(f"SMS_AIW_PITBOX_{i}", b, col_a)
        marcador(f"SMS_AIW_GARAGE_{i}A", b, col_a)
    resumen["parrilla"] = f"{len(tz['parrilla'])} slots · placed {posados} · without ground {sin_suelo}"
    resumen["boxes"] = f"{len(tz['boxes'])} · placed {pb} · without ground {sb}"
    resumen["centerline"] = tz["centerline"]
    resumen["curvas"] = tz["curvas"]
    resumen["waypoint_span"] = round(tz["waypoint_span"], 2)

    try:
        feats = bpy.context.scene.aiw_properties.track_features
        feats.waypoint_span = tz["waypoint_span"]
        feats.oval = es_ovalo(trazado)
        resumen["oval"] = feats.oval
    except AttributeError:
        resumen["oval"] = "not set (TrackCompiler not loaded)"
    return resumen


def main():
    global CENTRAL_ASFALTO, ANCHO_ASFALTO, PARRILLA_EN_META, PARRILLA_DE
    a = _argv()
    if a.get("parrilla-de"):
        PARRILLA_DE = T.construir(a["carpeta"], a["parrilla-de"])
    CENTRAL_ASFALTO = bool(a.get("central-asfalto"))
    ANCHO_ASFALTO = bool(a.get("ancho-asfalto"))
    PARRILLA_EN_META = bool(a.get("parrilla-en-meta"))
    r = principal(a["carpeta"], a.get("trazado", "layout_speedway"), a["tex"], a.get("fisica"),
                  semaforos=bool(a.get("semaforos")))
    g = r["geometria"]
    print(f"GEOMETRY: {g['mallas']} meshes imported · {g['vertices']:,} vertices · "
          f"{g['materiales']} materials · normals flipped on {g['signos'][-1]} · "
          f"{g['ocultas']} not drawable (collision only)")
    f = r["fisica"]
    print(f"AC PHYSICS: {f['mallas']} meshes · surfaces {r['fisica_superficies']}")
    fp = r.get("fisica_principal") or {}
    print(f"AC PHYSICS from the main file: {fp.get('mallas', 0)} meshes (grass and so on)")
    print("PIECES: " + ", ".join(f"{n} ({m})" for n, m in r["piezas"]))
    print(f"MATERIAL SURFACE: {r.get('superficies_de_material', 0)} materials with a physical surface")
    etiquetas = {"parrilla": "grid", "boxes": "pits", "centerline": "centerline", "curvas": "corners",
                 "waypoint_span": "waypoint_span", "oval": "oval", "semaforos": "start lights"}
    for k in ("parrilla", "boxes", "centerline", "curvas", "waypoint_span", "oval", "semaforos"):
        if k in r:
            print(f"  {etiquetas[k]}: {r[k]}")
    if a.get("pancartas"):
        # custom banners on the author's banner meshes (`pancartas.py`)
        import pancartas as PC
        cfg = PC.leer(a["pancartas"])
        PC.texturas(cfg, a["tex"])
        hechas = PC.aplicar(cfg, lambda n, dds: material(
            K.Material(nombre=n, shader="ksPerPixel", texturas={"txDiffuse": dds}), a["tex"]))
        print("BANNERS: " + " · ".join(hechas))
    if a.get("save"):
        bpy.ops.wm.save_as_mainfile(filepath=a["save"])
        print(f"  -> {a['save']}")


if __name__ == "__main__":
    main()
