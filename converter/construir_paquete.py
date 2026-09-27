"""Builds the AMS2 package from the already converted Blender scene.

    blender -b --factory-startup --python construir_paquete.py -- \\
        --blend charlotte_aiw.blend --nombre Charlotte --salida .../pack

Skeleton strategy: start from the Example Project template (Meadowdale), which is content the game is
known to load, and replace what belongs to the track. Anything without its own recipe is solved with a
material borrowed from the example: first make it load; the look is refined afterwards, by family.

⚠️ The scene exporter takes EVERYTHING that is enabled, so the AIW collection has to be switched off
first, or the waypoints would end up as visible geometry.
"""

import os
import re
import shutil
import subprocess
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import familias as F  # noqa: E402
import ovalo as OV  # noqa: E402

import rutas as _R  # noqa: E402
EJEMPLO = _R.EJEMPLO
PLANTILLA = os.path.join(EJEMPLO, "Automobilista 2")
ORIGEN_NOMBRE = "Meadowdale"


def _args():
    a = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return {a[i][2:]: a[i + 1] for i in range(0, len(a) - 1) if a[i].startswith("--")}


def preparar_plantilla(salida: str, nombre: str):
    """Copies the template renaming Meadowdale -> <nombre> and empties its meshes."""
    if os.path.exists(salida):
        shutil.rmtree(salida)
    shutil.copytree(PLANTILLA, salida)

    # rename the track's folders and files
    for raiz, dirs, _ in os.walk(salida, topdown=False):
        for d in dirs:
            if ORIGEN_NOMBRE in d:
                os.rename(os.path.join(raiz, d), os.path.join(raiz, d.replace(ORIGEN_NOMBRE, nombre)))
    for raiz, _, ficheros in os.walk(salida):
        for f in ficheros:
            if ORIGEN_NOMBRE in f:
                os.rename(os.path.join(raiz, f), os.path.join(raiz, f.replace(ORIGEN_NOMBRE, nombre)))

    # out with the example track's meshes and materials: the scene export puts the track's own
    pista = os.path.join(salida, "Tracks", nombre)
    borrados = 0
    for f in os.listdir(pista):
        if f.lower().endswith((".meb", ".mtx")):
            os.remove(os.path.join(pista, f))
            borrados += 1
    return borrados


SIN_CLASIFICAR_AC = "sin clasificar"
SUPERFICIES_ASFALTO_AC = {"ROAD", "APRON", "PIT", "PITS"}


def asignar_shaders():
    """Gives each material the Madness shader of its family, and checks the permutation.

    A material imported from AMS1 carries no Madness shader: the add-on assigns it `LightMap.fx` by
    default and the database warns that this combination of defines **does not exist among the game's
    compiled permutations** — i.e. an invisible mesh. Assigning the family's shader makes the
    permutation valid by construction.
    """
    from trackcompiler.materials import mtx_material_system as M

    donantes = os.path.join(PLANTILLA, "Tracks", ORIGEN_NOMBRE)
    resumen = {"ok": 0, "avisos": [], "prestados": 0}
    for mat in bpy.data.materials:
        fam, shader, _fisica, donante = F.familia_de(mat.name)
        # In AC the material's physical SURFACE decides, not its name (see
        # `kn5_to_blender.superficie_por_material`). For now ONLY the asphalt: grass and the
        # rest separately, one change per version.
        if fam == SIN_CLASIFICAR_AC and mat.get("ac_superficie") in SUPERFICIES_ASFALTO_AC:
            fam, shader, _fisica, donante = F.familia_por_nombre("asfalto")
        ruta = os.path.join(donantes, donante)
        if os.path.exists(ruta):
            M.read_mtx_file(__import__("pathlib").Path(ruta), mat)  # copies the whole recipe
            resumen["prestados"] += 1
        else:
            mat.mtx_settings.shader_path = F.ruta_shader(shader)
        aviso = _seguir_la_sugerencia(M, mat.mtx_settings)
        if aviso:
            resumen["avisos"].append((mat.name, fam, shader, aviso))
        else:
            resumen["ok"] += 1
    return resumen


def poner_texturas_propias(dds_dir: str):
    """Points each material's diffuse at THE TRACK'S OWN TEXTURE.

    🔴 Charlotte looked grey with Meadowdale's skin **while having its 217 textures decrypted from day
    one**. The GMT importer had linked them to each material; what was missing was telling the MTX,
    because the borrowed recipe carries the example track's paths.

    ONLY the diffuse is touched: the detail, the normal and the LiveTrack masks stay as they are,
    because AMS1 has no equivalent and they are generic. The exporter copies into the package whatever
    it is pointed at, so pointing at the file on disk is enough.
    """
    import glob

    disco = {os.path.basename(f).lower(): f for f in glob.glob(os.path.join(dds_dir, "*"))}
    puestas, sin = [], []
    for mat in bpy.data.materials:
        nodos = mat.node_tree.nodes if (mat.use_nodes and mat.node_tree) else []
        imgs = [n.image.name for n in nodos if n.type == "TEX_IMAGE" and n.image]
        ruta = disco.get(imgs[0].lower()) if imgs else None
        if not ruta:
            sin.append(mat.name)
            continue
        params = list(mat.mtx_settings.shader_params)
        difuso = next((x for x in params if x.name.lower() in ("diffuse1texture", "diffusetexture")), None)
        if difuso is None:
            difuso = next((x for x in params if "diffuse" in x.name.lower()), None)
        if difuso is None:
            sin.append(mat.name)
            continue
        difuso.texture_value = ruta
        difuso.enabled = True
        puestas.append((mat.name, os.path.basename(ruta)))
    return puestas, sin


def _seguir_la_sugerencia(M, ajustes, vueltas: int = 4):
    """Applies what the shader database suggests, until it stops warning.

    The warning carries the recipe: "... Try: Enable USE_TERRAIN_BLEND, USE_DIFFUSE2". It is the
    harvest of the game's own 39,187 MTX files saying which permutations really exist, so it is
    followed instead of guessing. Returns the remaining warning, or None.
    """
    import re

    for _ in range(vueltas):
        aviso = M.packed_permutation_warning_for_settings(ajustes)
        if not aviso:
            return None
        m = re.search(r"Try:\s*Enable\s+(.+?)\s*$", aviso)
        if not m:
            return aviso  # warns but suggests nothing: nothing to apply
        sugerencia = m.group(1)
        activos = [d.name for d in ajustes.defines if d.enabled]
        conocidos = {d.name for d in ajustes.defines}
        if sugerencia.lower().startswith("reorder"):
            # THE ORDER IS PART OF THE RECIPE. The engine ships precompiled permutation
            # binaries: the same defines in another order are ANOTHER permutation, and if it
            # doesn't exist the mesh becomes invisible WITHOUT AN ERROR. The right order comes
            # from the game's own harvest.
            deseados = _en_orden_del_juego(ajustes, activos)
        else:
            sugeridos = [n.strip() for n in sugerencia.split(",") if n.strip()]
            fuera = [n for n in sugeridos if n not in conocidos]
            if fuera:
                M.apply_packed_param_names(ajustes, fuera)
            deseados = _en_orden_del_juego(ajustes, activos + [n for n in sugeridos if n in conocidos])
        M.apply_packed_define_names(ajustes, deseados)
    return M.packed_permutation_warning_for_settings(ajustes)


def _en_orden_del_juego(ajustes, nombres):
    """Orders the defines the way AMS2 orders them, not in the order they were added."""
    from trackcompiler.materials import shader_definitions as SD

    orden = SD._packed_define_order(ajustes.shader_path, ajustes.technique) or []
    pos = {n: i for i, n in enumerate(orden)}
    unicos = list(dict.fromkeys(nombres))
    return sorted(unicos, key=lambda n: pos.get(n, len(pos) + unicos.index(n)))


def arreglar_sectores(ruta_aiw: str) -> dict:
    """`sector_2_length` must be CUMULATIVE, not the length of the stretch.

    🔴 Measured. The original AMS1 AIW declares `sector_1_length=799.45` and
    `sector_2_length=1619.70` — the second is the distance **from the finish line**, not what the
    sector measures. Texas does the same (1544.11 declared, real change at 1532). OMTT writes the
    stretch length: it came out at **796.91**, i.e. the sector 2 line **two metres** after sector 1's.

    ⚠️ The two references made with OMTT have it equally wrong, so it's an exporter defect — but that
    doesn't make it right: the two files that do NOT come from OMTT (the AMS1 original and Texas) agree
    on the cumulative value. It is fixed in the already exported `.aiw`.

    Suspected of the absurd sector times and, possibly, of the car starting with an almost empty tank:
    if the game derives the lap distance from the sectors, it gets an 800 m lap instead of 2,393.
    """
    import re

    if not os.path.exists(ruta_aiw):
        return {"tocado": False}
    txt = open(ruta_aiw, encoding="latin-1").read()
    m1 = re.search(r"sector_1_length=([\d.]+)", txt)
    m2 = re.search(r"sector_2_length=([\d.]+)", txt)
    if not m1 or not m2:
        return {"tocado": False}
    s1, s2 = float(m1.group(1)), float(m2.group(1))
    ml = re.search(r"lap_length=([\d.]+)", txt)
    lap = float(ml.group(1)) if ml else 0.0
    # ⚠️ The condition `if s2 > s1` **is not enough**: 796.91 IS greater than 794.82, so it took the
    # cumulative value as done and fixed nothing. Truly cumulative means the second cut is FAR ahead
    # of the first, not two metres.
    if s2 > s1 + lap * 0.1:
        return {"tocado": False, "s1": s1, "s2": s2}
    nuevo = s1 + s2
    txt = txt[:m2.start(1)] + f"{nuevo:.6f}" + txt[m2.end(1):]
    open(ruta_aiw, "w", encoding="latin-1").write(txt)
    return {"tocado": True, "s1": s1, "s2": s2, "acumulado": nuevo}


def identidad_trd(nombre: str) -> dict:
    """The TRD fields that say WHICH track it is. One single list, for BOTH chains.

    🔴 Why it exists. The Assetto Corsa chain had its own TRD patch, half copied from this one: it
    wrote the length, the country, the coordinates… and NOT the identity. Mountain Peak came out with
    `ScenegraphFile = meadowdale.sgx` (the game tried to load a scenery that doesn't exist: **it didn't
    load**) and `ShortTrackName = Meadowdale_Raceway` (it looked for the images under that name:
    **white squares**). Two lists of the same thing end up diverging; this is the only one.
    """
    return {
        "Name": nombre,
        "ShortTrackName": nombre,
        "Track Group": nombre,
        "Track_Variation": nombre,
        "ScenegraphFile": f"{nombre}.sgx",
    }


def parchear_trd(ruta: str, nombre: str, aiw, gdb, args=None):
    """Writes into the TRD what the track IS. The TRD is flat XML: `<prop name data />`.

    Whatever isn't touched keeps Meadowdale's value, which is valid content — better than inventing a
    value and having the game reject it without saying why.
    """
    import re

    import aiw_read as A
    import gdb_read as G

    vueltas = {
        **identidad_trd(nombre),
        "TrackName": (gdb or {}).get("trackname", nombre),
        "Track_Location": (gdb or {}).get("location", ""),
        "Length": str(int(aiw.lap_length)),
        "Number Of Turns": str(_curvas(aiw)),
        # ⚠️ The template says `Circuit` and Charlotte is an OVAL. Texas — a well-made AMS2 oval —
        # says `Oval`, and the game only accepts 5 values in this field. Declaring an oval as a
        # circuit changes the behaviour of the AI and of the start.
        # 🔴 IT STAYS `Circuit` EVEN FOR AN OVAL. Setting it to `Oval` without `Oval Type` leaves the
        # track **loading forever** (measured by bisection: with `Circuit` it loaded, with `Oval` it
        # didn't). Texas has BOTH fields; `Oval Type` isn't declared in the template's schema. Until
        # it is declared, `Circuit`.
        "Track Type": "Circuit",
        # ⏳ `Oval Type` (U32; Texas uses 6 for a 1.5-mile quad-oval) is NOT declared: it isn't in the
        # template's schema, and adding a property to the Reflection is exactly the kind of change
        # that leaves the track not loading if it goes wrong. To be done with an in-game test behind it.
        # ⚠️ It is written, but **never reaches the file**: the property isn't declared in the
        # template's Reflection schema, so the `subn` finds 0 matches. Kept here for the day it is.
        "Oval Type": "1" if (gdb and G.es_oval(gdb)) else "0",
        # --- data found in the AMS1 .gdb ---
        # 🔴 The TRD carried Meadowdale's coordinates: Illinois, **1,000 km** from Charlotte and one
        # hour apart. The game uses them for the sun.
        # ⚠️ HARD-CODING them with one track's values is the same failure with another constant: the
        # other 31 tracks would come out in Concord. They come from `gdb_read.COORDENADAS`, and if
        # the track isn't in the table they **are not touched** (None) and the build says so.
        "Track_Latitude": f"{_geo(gdb, args)[0]:.4f}" if _geo(gdb, args) else None,
        "Track_Longitude": f"{_geo(gdb, args)[1]:.4f}" if _geo(gdb, args) else None,
        "Track_Altitude": str(_geo(gdb, args)[2]) if _geo(gdb, args) else None,
        "Track_TimeZone": str(_geo(gdb, args)[3]) if _geo(gdb, args) else None,
        # `Location` is the COUNTRY (the 4 references say "USA"); `Track_Location`, the place.
        "Location": G.pais(gdb) or (gdb or {}).get("location", ""),
        # 🔴 `PitSpeedLimit_HighKPH=240` exists on no stock track. The track itself says it:
        # `RacePitKPH = 100`.
        "PitSpeedLimit_HighKPH": f"{G.limite_de_boxes(gdb):.1f}" if G.limite_de_boxes(gdb) else None,
        # 🔴 53 opponents on a 40-slot grid. The exported grid rules.
        "Max AI participants": str(_puestos_de_parrilla(aiw, gdb)),
        # 🔴 The date was Meadowdale's (20-Jun-1963) with the right one next to it: "August 11".
        "Race_Date_Month": str(G.fecha_de_carrera(gdb)[0]) if G.fecha_de_carrera(gdb) else None,
        "Race_Date_Day": str(G.fecha_de_carrera(gdb)[1]) if G.fecha_de_carrera(gdb) else None,
        # 🔴 The direction, which the template gave as CLOCKWISE (Meadowdale) while Charlotte turns
        # LEFT, like every American oval. The generated AIW already said so — 199 corner waypoints, all
        # 199 of type LEFT — and the TRD said the opposite: the AI reads both and believes both. It is
        # taken from the SAME classification that writes the AIW, so they can't contradict each other.
        # `None` = could not be determined -> NOT written, whatever is there stays.
        "Is Clockwise": {True: "true", False: "false"}.get(A.gira_a_derechas(aiw.main_path)),
    }
    texto = open(ruta, encoding="utf-8").read()
    tocados = []
    for clave, valor in vueltas.items():
        if valor is None:      # the .gdb doesn't have it: leave what was there, don't invent it
            continue
        pat = re.compile(r'(<prop name="' + re.escape(clave) + r'" data=")[^"]*(")')
        texto, n = pat.subn(lambda m: m.group(1) + valor + m.group(2), texto)
        if n:
            tocados.append(f"{clave}={valor}")
    open(ruta, "w", encoding="utf-8").write(texto)
    return tocados


def _geo(gdb, args=None):
    """The track's coordinates from its .gdb name, or None if it isn't in the table."""
    import os

    import gdb_read as G

    ruta = (args or {}).get("gdb", "")
    nombre = os.path.splitext(os.path.basename(ruta))[0] if ruta else ""
    return G.coordenadas(nombre)


def _puestos_de_parrilla(aiw, gdb=None) -> int:
    """How many cars fit: the slots REALLY exported, not an inherited number.

    🔴 The TRD said `Max AI participants=53` (Meadowdale's value) on a 40-slot grid. Asking the game
    for more cars than slots is asking it to invent places.
    """
    import aiw_read as A

    import gdb_read as G

    if A.parrilla_fuera_de_pista(aiw) > 2.0:
        # same cap as `aiw_to_blender`: 32, AMS2's maximum.
        return len(A.parrilla_desde_la_linea(
            aiw, puestos=min(G.maximo_de_coches(gdb) or A.TECHO_PARRILLA, A.TECHO_PARRILLA)))
    return len(aiw.grid)


def _curvas(aiw):
    import aiw_read as A

    _t, estados, _u = A.curvas_adaptativo(aiw.main_path)
    # ⚠️ NOT `estados.count(STATE_APEX)`: since the apex became a plateau that would give **146**
    # corners at Charlotte instead of 4. Stretches are counted, not points.
    return A.numero_de_curvas(estados)


def escribir_tracks_lod(salida: str, nombre: str) -> str:
    """`tracks.lod`: the track's LOD distances. **Both working mods have it and the OMTT template does
    NOT.**

    Comparing the three packages by file type: `tracks.lod` appears in Enna Pergusa and in Texas Motor
    Speedway, and not in the Example Project we start from. It's the ONLY file in that situation —
    `tracks.cul` and `cameraconfig.xml` are only in Enna.

    The last entry, the one **without `substring`**, is the default LOD for everything else. Without
    the file the engine has no distances for any object.

    Our own is written with gMotor2 object names (TRACK, WALLS, GRASS, FENCE, OUT); nobody's is copied.
    """
    entradas = [
        ('substring="TRACK"', "2000.0", "4000.0"),
        ('substring="WALL"', "1500.0", "3000.0"),
        ('substring="FENCE"', "800.0", "1500.0"),
        ('substring="GRASS"', "1500.0", "3000.0"),
        ('substring="OUT"', "2000.0", "4000.0"),
        ('substring="BRAKEMARKER"', "500.0", "1000.0"),
    ]
    lineas = [f'  <ENTRY {sub} LODA="{a}" LODB="{b}" />' for sub, a, b in entradas]
    lineas.append('  <ENTRY LODA="1000.0" LODB="2500.0" LODC="4000.0" />')  # the default one
    texto = ('<?xml version="1.0" encoding="utf-8" ?>\n'
             f'<LODCONTROL entries="{len(lineas)}">\n' + "\n".join(lineas) + "\n</LODCONTROL>\n")
    ruta = os.path.join(salida, "Tracks", nombre, "tracks.lod")
    open(ruta, "w", encoding="utf-8").write(texto)
    return ruta


def escribir_auxiliares(salida: str, nombre: str) -> list:
    """The configuration files the OMTT template does NOT ship and the working mods DO.

    Comparing the FULL set of **Enna Pergusa** — made with the SAME toolkit (`ExporterVersion = Open
    Madness Track Tools 0.1.0`) and working — against the package generated from the template:
    `tracks.lod`, `tracks.cul` and `_data/tracklights/<track>.xml` are missing.

    `tracklights` is the serious suspect: it defines the START LIGHTS, and a race doesn't start without
    them. It is written **empty but valid**: the file exists and references no meshes the package
    doesn't ship, which would be trading one failure for another.

    All are written from scratch with the documented structure; nobody's is copied.
    """
    hechos = []

    cul = os.path.join(salida, "Tracks", nombre, "tracks.cul")
    open(cul, "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="utf-8" ?>\n<CULCONTROL>\n'
        '\t<MAINSCENE>\n\t\t<ENTRY SPLIT="800.0" SIZE="6.0"/>\n'
        '\t\t<ENTRY SPLIT="600.0" SIZE="1.0" />\n\t\t<ENTRY SPLIT="300.0" SIZE="0.2" />\n\t</MAINSCENE>\n'
        '\t<REARVIEW>\n\t\t<ENTRY SPLIT="60.0" SIZE="8.0"/>\n\t\t<ENTRY SPLIT="50.0" SIZE="7.0" />\n'
        '\t\t<ENTRY SPLIT="40.0" SIZE="6.4" />\n\t</REARVIEW>\n'
        '\t<SHADOWS>\n\t\t<ENTRY SIZE="0.0" />\n\t\t<ENTRY SIZE="0.0" />\n'
        '\t\t<ENTRY SIZE="0.5" />\n\t\t<ENTRY SIZE="5.0" />\n\t</SHADOWS>\n'
        '\t<VEHICLESHADOWS>\n\t\t<ENTRY SIZE="0.0" />\n\t\t<ENTRY SIZE="0.0" />\n'
        '\t\t<ENTRY SIZE="1.5" />\n\t\t<ENTRY SIZE="12.0" />\n\t</VEHICLESHADOWS>\n'
        '\t<ENVMAP>\n\t\t<ENTRY SIZE="6.0" />\n\t</ENVMAP>\n'
        '\t<SCALECULLING_DAY>\n\t\t<ENTRY SCALE="1.0" />\n\t\t<ENTRY COCKPIT="1.25" />\n\t</SCALECULLING_DAY>\n'
        '\t<SCALECULLING_NIGHT>\n\t\t<ENTRY SCALE="1.5" />\n\t\t<ENTRY COCKPIT="1.25" />\n\t</SCALECULLING_NIGHT>\n'
        '\t<SCALECULLING_DUSK>\n\t\t<ENTRY SCALE="1.0" />\n\t\t<ENTRY COCKPIT="1.25" />\n\t</SCALECULLING_DUSK>\n'
        '</CULCONTROL>\n')
    hechos.append("tracks.cul")

    tl_dir = os.path.join(salida, "Tracks", "_data", "tracklights")
    os.makedirs(tl_dir, exist_ok=True)
    open(os.path.join(tl_dir, f"{nombre}.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="utf-8" ?>\n'
        "<!-- No start lights of its own: the file EXISTS, which is what the engine looks for,\n"
        "     and it references no meshes this package doesn't ship. -->\n"
        "<TRACKLIGHTS>\n</TRACKLIGHTS>\n")
    hechos.append(f"_data/tracklights/{nombre}.xml")
    return hechos


COCINERO = _R.COCINERO


# Example Project textures that are reused, with the role they play. They're copied under their own
# name and the material that uses them is re-pointed.
#
# 🔴 The asphalt's `normalTexture` pointed at `color_normal_7F7FFF.dds`, which is **1 KB of flat
# blue**: ZERO relief. That's why the asphalt looked smooth and matte. Mid-Ohio uses 2048² normals,
# GJ Kartway 4096².
# ⏳ EMPTY on purpose. With `Meadowdale_Banking_NormalAC.dds` here, the asphalt came out WORSE: ugly
# on track and awful in the pits.
#
# ⚠️ That texture isn't a tileable asphalt pattern, it's a normal **baked for Meadowdale's banking
# geometry**. Applied to other UVs and to everything in the "asphalt" family — which includes the
# **pit road** — it paints the relief of somewhere else. "Having relief" isn't better than "having
# none" if the relief belongs to another track: it's the same mistake as the example's `.mrdf` and
# LiveTrack masks.
#
# Fixing it properly is a CONTENT problem, not a code one: it needs a **tileable** asphalt normal.
# Mid-Ohio uses its own 2048², GJ Kartway 4096².
RELIEVES = {}


# 🔴 How many world metres ONE repetition of the texture covers. Measured at Charlotte, compared
# with Texas's resolution:
#
#   track (RDHI/RDMID/RDLOW)    16 m  -> 128 texels/m with a 2048² texture.  ✅
#   grass (GRASSA)              45 m  ->  45 texels/m.                        🔴
#   outer terrain (OUTFIELD)    65 m  ->  32 texels/m.                        🔴
#
# And what settles it: **Texas doesn't get sharper with bigger textures.** Of its 561 textures only
# 19 are 2048², most are 1024². It gets sharpness by repeating them more times per metre. So this
# isn't fixed with a better texture: it's fixed with the UV.
#
# ⚠️ The ground shader multiplies the UV by `detailUScale/VScale` for its close-up layer (15 at
# Charlotte). If you tighten the UV by k and leave that number alone, the detail layer ALSO tightens
# by k and goes from repeating every 3 m to every 0.8 m, which is noise. That's why it's divided by k
# on the way out.
# Target per family, in world metres per full repetition of the texture.
# With 2048² textures that's 2048/N texels per metre:
#   10 m -> 205 texels/m     12 m -> 171     16 m -> 128     45 m -> 45     65 m -> 32
#
# The reference above: Texas's road is a 1024 px strip for about 20 m of track width, i.e.
# **51 texels/m**. Tightening to 10 m gives 205, four times more. What Texas gains isn't density,
# it's that its strip has the variation painted in (repairs, the polished racing line) and never
# repeats.
#
# ⚠️ Tightening the UV is only safe if the texture leaves NO seam. The included CC0 one is the least
# blotchy of those measured (0.71 at 8x8 scale, against 0.78 for AMS2's own asphalt and 3.86 for
# Texas's), so 205 repetitions per lap draw no pattern. With a blotchy texture, this SAME thing would
# look tiled.
METROS_POR_REPETICION = {"hierba": 12.0, "asfalto": 10.0}


# ── DOES THIS MATERIAL GET THE CC0 TEXTURE? — one single rule, for two steps ────────────────
#
# 🔴 Why. Symptom on Mountain Peak: the infield grass came out a flat green. `apretar_uv` tightened
# EVERY material in the "grass" family, and tightening the UV assumes the texture repeats without a
# seam. At Charlotte that was true because the CC0 grass was there; in Assetto Corsa the infield
# (`GRASS_NATURAL2SOIL`) carries a LARGE-scale colour map that does NOT repeat, and it ended up 7
# times in a row (`detailUScale` 15 → 2.1). Tileable is a property of the TEXTURE, not of the family.
# So it's only tightened where the CC0 is going to go, and the decision is THIS function, the same one
# `poner_texturas_por_familia` uses — if there were two, they would end up contradicting each other.
# ⚠️ And a texture with alpha cutout doesn't get CC0: AC's verges and grass tufts
# (`GRASS_TRACKVERGES01`, `GRASSES02`) would come out as solid squares.
CC0_CARPETA = None          # --texturas
CC0_FAMILIAS = None         # --cc0-families (None = every family found in the folder)
_CACHE_AGUJEROS = {}


def _con_agujeros(ruta_dds: str) -> bool:
    if ruta_dds in _CACHE_AGUJEROS:
        return _CACHE_AGUJEROS[ruta_dds]
    import subprocess
    ok = False
    if ruta_dds and os.path.exists(ruta_dds):
        r = subprocess.run([*_R.IM_CONVERT, ruta_dds, "-alpha", "extract", "-format", "%[fx:mean]", "info:"],
                           capture_output=True, text=True)
        try:
            ok = float(r.stdout.strip()) < 0.98
        except ValueError:
            ok = False
    _CACHE_AGUJEROS[ruta_dds] = ok
    return ok


def recibe_cc0(mat_nombre: str, ruta_textura_original: str | None):
    """The material's family if it is going to get the CC0 texture, or None."""
    import unicodedata
    if not CC0_CARPETA or not os.path.isdir(CC0_CARPETA):
        return None
    fam = "".join(c for c in unicodedata.normalize("NFD", F.familia_de(mat_nombre)[0])
                  if unicodedata.category(c) != "Mn").split("/")[0].lower()
    if CC0_FAMILIAS is not None and fam not in CC0_FAMILIAS:
        return None
    if not os.path.exists(os.path.join(CC0_CARPETA, f"{fam}_diffuse.dds")):
        return None
    if ruta_textura_original and _con_agujeros(ruta_textura_original):
        return None
    return fam


def apretar_uv(objetivos=None, dds_dir=None) -> dict:
    """Scales each material's UV so its texture repeats every N metres.

    Aggregated **per material**, not per object: `GRASSA` appears in several meshes and all three must
    end up with the same factor, or the seam between them shows.

    Returns the factor applied to each material, needed later to compensate `detailUScale/VScale` in
    the `.mtx`.
    """
    import math
    import unicodedata
    from collections import defaultdict

    objetivos = objetivos or METROS_POR_REPETICION

    def sin_tildes(x):
        return "".join(c for c in unicodedata.normalize("NFD", x)
                       if unicodedata.category(c) != "Mn")

    def area_uv(uv, poly):
        pts = [uv[l].uv for l in poly.loop_indices]
        a = 0.0
        for i in range(1, len(pts) - 1):
            x1, y1 = pts[i][0] - pts[0][0], pts[i][1] - pts[0][1]
            x2, y2 = pts[i + 1][0] - pts[0][0], pts[i + 1][1] - pts[0][1]
            a += abs(x1 * y2 - x2 * y1) / 2
        return a

    # --- 1st pass: how big each material is now
    medida = defaultdict(lambda: [0.0, 0.0])
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.data.uv_layers:
            continue
        m = o.data
        uv = m.uv_layers[0].data
        for poly in m.polygons:
            if not m.materials or poly.material_index >= len(m.materials):
                continue
            mat = m.materials[poly.material_index]
            if mat is None:
                continue
            r = medida[mat.name]
            r[0] += poly.area
            r[1] += area_uv(uv, poly)

    factores = {}
    for mat_nombre, (am, au) in medida.items():
        if am < 100 or au <= 0:
            continue
        mat = bpy.data.materials.get(mat_nombre)
        img = next((n.image.name for n in (mat.node_tree.nodes if mat and mat.node_tree else [])
                    if n.type == "TEX_IMAGE" and n.image), None)
        fam = recibe_cc0(mat_nombre, os.path.join(dds_dir, img) if (dds_dir and img) else None)
        if fam is None:
            continue           # no tileable CC0 on top: its UV is the author's and is respected
        objetivo = objetivos.get(fam)
        if not objetivo:
            continue
        actual = math.sqrt(am / au)
        k = actual / objetivo
        if k <= 1.05:          # already equal or tighter: left alone
            continue
        factores[mat_nombre] = (k, actual, objetivo)

    # --- 2nd pass: apply
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.data.uv_layers:
            continue
        m = o.data
        uv = m.uv_layers[0].data
        for poly in m.polygons:
            if not m.materials or poly.material_index >= len(m.materials):
                continue
            mat = m.materials[poly.material_index]
            if mat is None or mat.name not in factores:
                continue
            k = factores[mat.name][0]
            for l in poly.loop_indices:
                uv[l].uv[0] *= k
                uv[l].uv[1] *= k

    # --- 3rd pass: CHECK. A scale that is applied and never measured again is exactly the kind of
    # step that passes while being wrong. The same thing is re-measured and compared with the target.
    comprobado = defaultdict(lambda: [0.0, 0.0])
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.data.uv_layers:
            continue
        m = o.data
        uv = m.uv_layers[0].data
        for poly in m.polygons:
            if not m.materials or poly.material_index >= len(m.materials):
                continue
            mat = m.materials[poly.material_index]
            if mat is None or mat.name not in factores:
                continue
            r = comprobado[mat.name]
            r[0] += poly.area
            r[1] += area_uv(uv, poly)
    for mat_nombre, (am, au) in comprobado.items():
        logrado = math.sqrt(am / au) if au > 0 else 0.0
        objetivo = factores[mat_nombre][2]
        factores[mat_nombre] = factores[mat_nombre] + (logrado,)
        if abs(logrado - objetivo) > objetivo * 0.02:
            print(f"  🔴 {mat_nombre}: it wanted {objetivo:.1f} m per repetition and got "
                  f"{logrado:.1f} m — the scale was NOT applied as it should")
    return factores


def compensar_detalle(salida: str, nombre: str, factores: dict) -> int:
    """Divides `detailUScale/VScale` by the same factor the UV was tightened by.

    Without it, tightening the UV also tightens the detail layer and the ground turns into noise.
    """
    import re

    pista = os.path.join(salida, "Tracks", nombre)
    tocados = 0
    for mat_nombre, valores in factores.items():
        k = valores[0]
        ruta = os.path.join(pista, f"{mat_nombre}.mtx")
        if not os.path.exists(ruta):
            continue
        txt = original = open(ruta, encoding="utf-8", errors="ignore").read()
        # The general rule: **every parameter that multiplies the UV** must be divided by k, not just
        # the detail layer's. On the road shader they're `detailTilingX/Y` (40 at Charlotte) and the
        # two puddle ones; on the ground shader, `detailUScale/VScale`. Compensate one and forget the
        # others, and tightening the UV shrinks the LiveTrack puddles and nobody connects it to this.
        claves = re.findall(r'<shaderparam name="([A-Za-z0-9_]*(?:Scale|TilingX|TilingY))"'
                            r' type="EPT_F32">', txt)
        for clave in claves:
            def _baja(m, _k=k):
                try:
                    return m.group(1) + f"{float(m.group(2)) / _k:.4f}" + m.group(3)
                except ValueError:
                    return m.group(0)
            txt = re.sub(r'(<shaderparam name="' + clave + r'" type="EPT_F32">\s*<value v=")'
                         r'([^"]*)(")', _baja, txt, count=1)
        if txt != original:
            open(ruta, "w", encoding="utf-8").write(txt)
            tocados += 1
    return tocados


def poner_alfatest(salida: str, nombre: str) -> dict:
    """Sets `USE_ALPHATEST` on the materials whose texture really has holes.

    🔴 Symptom: signs and fences that looked odd or didn't show. Measured: **31 materials** in the
    package had a texture with real transparency and NO `define`: they were drawn solid. The worst:

    | material | transparent pixels |
    |---|---|
    | `GARAGEDOORB` | **96 %** — a slab instead of a door |
    | `FENCENEW` / `FENCETOP` | 80 % |
    | `FENCEINF` | 78 % · `FENCE02` 72 % |
    | `ANIMCROWDA/B/C`, `CROWDANMID` | 34-39 % — the crowd, on solid cards |

    Of the 32 materials with alpha, **only one** had it. The recipe is copied whole from GJ Kartway's
    `FENCE_CHAINLINK.mtx` — the toolkit author's own track —: alpha blending off (already there)
    **plus** the line `<define name="USE_ALPHATEST" />`. No other parameter is needed.

    ⚠️ It's easy to rule it out *"because the material recipe is identical to GJ Kartway's"*: it is,
    in everything **except the one line that matters**. Comparing recipes "in general" isn't comparing;
    that's why this is decided **by measuring the texture's alpha**, not by the material's name or a
    template likeness.
    """
    import re
    import subprocess

    pista = os.path.join(salida, "Tracks", nombre)
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    if not os.path.isdir(tex):
        return {"puestos": []}

    cache = {}

    def tiene_agujeros(dds):
        """Mean of the alpha channel. 1.0 = fully opaque; below 0.98 there's a cutout."""
        if dds in cache:
            return cache[dds]
        ruta = os.path.join(tex, dds)
        ok = False
        if os.path.exists(ruta):
            r = subprocess.run([*_R.IM_CONVERT, ruta, "-alpha", "extract",
                                "-format", "%[fx:mean]", "info:"],
                               capture_output=True, text=True)
            try:
                ok = float(r.stdout.strip()) < 0.98
            except ValueError:
                ok = False
        cache[dds] = ok
        return ok

    puestos = []
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8", errors="ignore").read()
        if "USE_ALPHATEST" in txt:
            continue
        # 🔴 The ROAD shader reads the diffuse alpha as GLOSS (`DiffuseSpecAlpha` in the `ROAD.mtx`
        # donor), not as holes: Charlotte's asphalt has alpha < 1 and with a cutout it would come out
        # in pieces. And `USE_ALPHATEST` isn't among its defines: a permutation that doesn't exist
        # leaves the mesh invisible without warning.
        if "rz_road_main" in txt:
            continue
        m = re.search(r'name="diffuse1Texture".*?<value v="([^"]*)"', txt, re.S)
        if not m or not m.group(1):
            continue
        if not tiene_agujeros(os.path.basename(m.group(1).replace("\\", "/"))):
            continue
        txt = txt.replace("</material>", '  <define name="USE_ALPHATEST" />\n</material>')
        open(ruta, "w", encoding="utf-8").write(txt)
        puestos.append(f[:-4])
    return {"puestos": puestos}


def _fraccion_horizontal(mat_nombre: str) -> float:
    """Share of the faces (by area) with that material that face up or down (|n.z| > 0.9)."""
    tot = hor = 0.0
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        idx = [i for i, ms in enumerate(obj.data.materials) if ms and ms.name.upper() == mat_nombre.upper()]
        if not idx:
            continue
        rot = obj.matrix_world.to_3x3()
        for poly in obj.data.polygons:
            if poly.material_index in idx:
                n = (rot @ poly.normal).normalized()
                tot += poly.area
                hor += poly.area if abs(n.z) > 0.9 else 0.0
    return hor / tot if tot else 0.0


def _alfa_medio(dds: str) -> float:
    import subprocess
    r = subprocess.run([*_R.IM_CONVERT, dds + "[0]", "-alpha", "extract", "-format", "%[fx:mean]", "info:"],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 1.0


def _opacidad_textura(ruta: str):
    """(share of pixels with alpha ≥ 0.5, mean alpha) of a texture, or None."""
    import subprocess
    if not ruta or not os.path.exists(ruta):
        return None
    r1 = subprocess.run([*_R.IM_CONVERT, ruta + "[0]", "-alpha", "extract", "-threshold", "50%", "-format",
                         "%[fx:mean]", "info:"], capture_output=True, text=True)
    r2 = subprocess.run([*_R.IM_CONVERT, ruta + "[0]", "-alpha", "extract", "-format", "%[fx:mean]", "info:"],
                        capture_output=True, text=True)
    try:
        return float(r1.stdout.strip()), float(r2.stdout.strip())
    except ValueError:
        return None


UV_SIN_COMPRIMIR = 2.0     # |u| or |v| above this: the mesh is exported with `_no_uv_comp`


def sin_compresion_uv() -> list:
    """Sets `skip_uv_compression` (suffix `_no_uv_comp`) on meshes with large texture coordinates.

    🔴 Symptom (Jarama): next to the finish line the asphalt looked fine and on the rest of the track
    the texture came and went. The game converts each `.meb`'s UV to 16-bit floats unless the file
    name ends in `_no_uv_comp` (OMTT, `Docs/Formats/MEB.md`, and the author's thread on Reiza's forum:
    "compression will cause quantization artifacts at large distances away from 0,0 - 1,1"). Jarama's
    asphalt goes from v = −55 to 205: at 200 a float16 only moves in steps of 0.125 → the coordinate
    jumps every 1.9 m, the base breaks up and the grain (UV × 15) vanishes; next to the finish line
    (v ≈ 0) the precision is a thousand times better. With |uv| ≤ 2 the step is ≤ 0.002 (negligible
    even × 15). See docs/LESSONS.md."""
    # ⚠️ NOT on meshes another file references by their `.meb` name: `tracklights/<n>.xml` says
    # `mesh="Startlight_LODA.meb"`; with the suffix the game wouldn't find them and the start lights
    # would stop working without an error. Their 2nd UV are integer IDs 1-4, exact in float16: they
    # don't need this.
    import generar_semaforos as _GS
    citadas = {str(getattr(_GS, k)).lower() for k in dir(_GS) if k.startswith("MALLA_")}
    marcadas = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.data.uv_layers:
            continue
        if obj.name.lower() in citadas or obj.data.name.lower() in citadas:
            continue
        me = obj.data
        maximo = 0.0
        for capa in me.uv_layers:
            for d in capa.data:
                maximo = max(maximo, abs(d.uv[0]), abs(d.uv[1]))
                if maximo > UV_SIN_COMPRIMIR:
                    break
            if maximo > UV_SIN_COMPRIMIR:
                break
        if maximo > UV_SIN_COMPRIMIR and hasattr(me, "meb_export_settings"):
            me.meb_export_settings.skip_uv_compression = True
            marcadas.append(obj.name)
    return marcadas


def quitar_goma_ac() -> list:
    """Removes AC's RUBBER layers (horizontal and almost transparent) from the scene, BEFORE exporting.

    🔴 Symptom (Jarama): at times the whole track looked smooth and WITHOUT the grid markings, which are
    another material → something was covering the whole track. The rubber (`groove`, 10,240 faces over
    the whole lap, 1-2 cm above) was left with an INVISIBLE texture: if that texture isn't loaded at
    some moment, the game puts an opaque fallback in its place, and the layer covers the asphalt. No
    mesh, nothing to cover. AMS2's LiveTrack draws the rubber.
    Only the HORIZONTAL ones (≥ 90 % of the area); other semi-transparent layers stay as they were."""
    quitadas = []
    for mat in list(bpy.data.materials):
        if not mat.get("ac_mezcla"):
            continue
        img = next((n.image for n in (mat.node_tree.nodes if mat.node_tree else [])
                    if n.type == "TEX_IMAGE" and n.image), None)
        op = _opacidad_textura(bpy.path.abspath(img.filepath)) if img and img.filepath else None
        if op is None:
            continue
        opacos, media = op
        if not (opacos < 0.10 and media < 0.3) or _fraccion_horizontal(mat.name) < 0.9:
            continue
        for obj in list(bpy.data.objects):
            if obj.type != "MESH" or not obj.data.materials:
                continue
            if all(ms is not None and ms.name == mat.name for ms in obj.data.materials):
                quitadas.append(obj.name)
                bpy.data.objects.remove(obj, do_unlink=True)
    return quitadas


def poner_mezcla_ac(salida: str, nombre: str) -> dict:
    """Copies the SEMI-TRANSPARENCY of Assetto Corsa's materials into the MTX.

    🔴 Symptom (Charlotte): black stripes on the asphalt. The racing-line rubber (`Roval_WearLine`,
    `oval line`) is `ksPerPixelAlpha` with blending in AC: `roadwear2.dds` is **pure black with alpha
    ≤ 0.44**, which darkens the asphalt by 24 %. Here it came out OPAQUE — blending off and
    `USE_ALPHATEST` —: solid black bands.

    The recipe is Reiza's for GJ Kartway's painted lines (`PAINTLINE_WHITE.mtx`):
    `alphablendparams enabled=true`, depth as it is. With ONE measured difference: if the texture's
    alpha doesn't reach 0.5, `USE_ALPHATEST` is removed — with it, a threshold above 0.44 would cut
    the whole rubber layer. The SHARE of pixels with alpha ≥ 0.5 is measured: below 5 % it's a soft
    layer and goes without cutout. The others (fences, glass) keep it, like GJ.
    """
    import re
    import subprocess

    pista = os.path.join(salida, "Tracks", nombre)
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    mezcla = {m.name.upper() for m in bpy.data.materials if m.get("ac_mezcla")}
    puestos, sin_recorte = [], []
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx") or f[:-4].upper() not in mezcla:
            continue
        ruta = os.path.join(pista, f)
        txt = original = open(ruta, encoding="utf-8", errors="ignore").read()
        txt = re.sub(r"(<alphablendparams>\s*<enabled e=\")false(\")", r"\1true\2", txt)
        m = re.search(r'name="diffuse1Texture".*?<value v="([^"]*)"', txt, re.S)
        # By the SHARE of pixels that would pass the cutout, not by the maximum: the oval's rubber
        # (`grooveend.dds`) has a maximum alpha of 0.57 — just over 0.5 — and with the maximum rule it
        # kept the cutout, which ate almost all of it.
        opacos = 1.0
        if m and m.group(1):
            dds = os.path.join(tex, os.path.basename(m.group(1).replace("\\", "/")))
            if os.path.exists(dds):
                r = subprocess.run([*_R.IM_CONVERT, dds + "[0]", "-alpha", "extract", "-threshold",
                                    "50%", "-format", "%[fx:mean]", "info:"],
                                   capture_output=True, text=True)
                try:
                    opacos = float(r.stdout.strip())
                except ValueError:
                    pass
        # 🔴 The cutout is NEVER removed. Symptom: BLACK stains on the banking. With blending and no
        # `USE_ALPHATEST`, `rz_basic` painted the asphalt's rubber and blend layers OPAQUE, and their
        # colour where alpha is 0 is BLACK. Reiza's recipe (GJ, `PAINTLINE_WHITE`) has both; it's copied
        # whole. What's lost: the rubber barely shows (only 4 % of its pixels pass the cutout).
        # 🔴 And the "almost invisible" ones are HIDDEN. Symptom: a white stripe on Charlotte's
        # straight. `oval line` (the oval's rubber, 4 % opaque) sits 1 cm above the asphalt right on the
        # high lane; with blending + cutout AMS2 doesn't blend it like AC and paints it light grey,
        # white in the sun. Measured under the grid: the right column has `groove_oval` on top, the
        # left one asphalt. AMS2's LiveTrack draws the rubber; these AC layers are surplus.
        # 🔴 Symptom (Jarama): the asphalt texture came and went, and at times the whole track came out
        # dark blue and smooth. `skidmark` (`tyres_add1.dds`) has 7.1 % opaque pixels: it fell outside
        # the 5 % and was drawn with a cutout. The cutout is decided with the REDUCED version of the
        # texture, which changes with distance: from afar the layer turns opaque and covers the
        # asphalt; up close it disappears. ⚠️ Simply raising the threshold would have hidden two thin
        # wire FENCES (10 and 14 %) and a tank (7 %) at Charlotte: what sets the rubber apart is its
        # SHAPE — a horizontal layer stuck to the track, barely opaque. Painted lines are horizontal
        # too, but they're around 23-27 % opaque.
        horizontal = _fraccion_horizontal(f[:-4]) if 0.05 <= opacos < 0.10 else 0.0
        media = _alfa_medio(dds) if 0.05 <= opacos < 0.10 and m and m.group(1) and os.path.exists(dds) else 1.0
        if opacos < 0.05 or (opacos < 0.10 and horizontal >= 0.9 and media < 0.3):
            txt = re.sub(r'(name="diffuse1Texture".*?<value v=")[^"]*(")',
                         lambda mm: mm.group(1) + f"tracks\\textures\\{nombre}\\marca_invisible.dds"
                         + mm.group(2), txt, count=1, flags=re.S)
            sin_recorte.append(f[:-4])
        if txt != original:
            open(ruta, "w", encoding="utf-8").write(txt)
            puestos.append(f[:-4])
    return {"puestos": puestos, "sin_recorte": sin_recorte, "declarados": len(mezcla)}


def quitar_defines_huerfanos(salida: str, nombre: str) -> dict:
    """Removes the `define`s that ask for a texture the material doesn't have bound.

    🔴 Symptom: the pit-lane floor showed odd reflections. The **10 road materials** — `RDHI/RDMID/
    RDLOW`, `APRONA` and the four `PITROAD*` — declared `USE_DIFFUSE2` and `USE_TERRAIN_BLEND` with
    `diffuse2Texture=""` and `terrainBlendTexture=""`. The shader is compiled asking for two samples
    nobody has bound.

    The reference settles it: **Mid-Ohio**'s `ASPHALTOLD.mtx`, same shader
    (`rz_road_main_3diffuse.fx`), declares `DEFAULTLIVETRACKRENDERING`, `APPLYLIVETRACKMASKS`,
    `USESURFACECAMERAFACINGNORMALBIAS`, `BLEND_DIFFUSE_WITH_PUDDLE_MAP`, `USE_FRESNEL` and
    `FULL_TANGENT` — and **neither `USE_DIFFUSE2` nor `USE_TERRAIN_BLEND`**. The example's template
    adds them, not the track.
    """
    import re

    pareja = {"USE_DIFFUSE2": "diffuse2Texture", "USE_TERRAIN_BLEND": "terrainBlendTexture"}
    pista = os.path.join(salida, "Tracks", nombre)
    quitados = {}
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        ruta = os.path.join(pista, f)
        txt = original = open(ruta, encoding="utf-8", errors="ignore").read()
        for define, textura in pareja.items():
            if define not in txt:
                continue
            m = re.search(r'name="' + textura + r'".*?<value v="([^"]*)"', txt, re.S)
            if m and m.group(1).strip():
                continue          # the texture IS there: the define is legitimate
            txt = re.sub(r'\s*<define name="' + define + r'" />', "", txt, count=1)
            quitados.setdefault(define, []).append(f[:-4])
        if txt != original:
            open(ruta, "w", encoding="utf-8").write(txt)
    return {"quitados": quitados}


# FENCES the way Reiza does them. At Daytona the fence meshes use `basic_translucent.fx`
# (42 materials) and the posts `basic.fx`, instead of `rz_basic` + cutout. Recipe copied WHOLE from
# `d8_wcb01_text.bmt` (Daytona): the simplest define combination of that shader that only asks for
# the diffuse texture — a permutation the game certainly has compiled —, with SOURCE_ALPHA/
# INV_SOURCE_ALPHA blending, no depth write and `USE_ALPHATEST`.
# ⚠️ The cutout STAYS: without it AC's blending painted black rectangles (see docs/LESSONS.md).
VALLA = re.compile(r"FENCE|CHAIN|CABLE|WIRE|NET", re.I)
NO_VALLA = re.compile(r"SIGN|BANNERS_B", re.I)


def vallas_translucidas(salida: str, nombre: str) -> dict:
    pista = os.path.join(salida, "Tracks", nombre)
    hechas, saltadas = [], []
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx") or not VALLA.search(f) or NO_VALLA.search(f):
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8", errors="ignore").read()
        dif = re.search(r'name="diffuse1?Texture".*?<value v="([^"]*)"', txt, re.S)
        if "USE_ALPHATEST" not in txt or not dif or "marca_invisible" in dif.group(1):
            saltadas.append(f[:-4])        # no holes (opaque) or hidden on purpose
            continue
        nom = re.search(r'name="([^"]+)"', txt).group(1)
        open(ruta, "w", encoding="utf-8").write(
            f'<material VERSION="v1.0.0.1" name="{nom}" shader="Render\\Shaders\\basic_translucent.fx" '
            'technique="Basic_Translucent" supportsSpecialisedLighting="true" fog="false" antialias="1" '
            'numparams="1" cull="EBFCT_ANTICLOCKWISE">\n'
            '  <shaderparam name="diffuseTexture" type="EPT_TEXTURE">\n    <type t="ET_STANDARD" />\n'
            f'    <value v="{dif.group(1)}" />\n  </shaderparam>\n'
            '  <depthparams>\n    <enabled e="true" />\n    <writeenabled w="false" />\n  </depthparams>\n'
            '  <alphablendparams>\n    <enabled e="true" />\n    <sourceblend sb="EBF_SOURCE_ALPHA" />\n'
            '    <destblend db="EBF_INV_SOURCE_ALPHA" />\n    <blendop bo="EBO_ADD" />\n  </alphablendparams>\n'
            '  <define name="USE_ALPHATEST" />\n</material>\n')
        hechas.append(f[:-4])
    return {"hechas": hechas, "saltadas": saltadas}


# NIGHT GLOWS. At Daytona the 50 materials that light up at night (`USE_EMISSIVEASLIGHTMAP`) ALL use
# `basic_windows.fx` and a control map in `emissiveTexture2`. Daytona's recipes:
# `d19_bigtoilet_alphaname` (with cutout) and `nascar_interior1` (without), MINUS
# `USE_COLOURISATION`/`TINT_USE_SIMPLE` (see below). The control map is Reiza's and each track ships
# its own in its pak: we DRAW our own with the same shape (128x128; columns 0-119, a stepped ramp
# x<y; 120-127, a smooth ramp). The generated emissive is opaque, like Daytona's.
# ⚠️ Both recipes carry `USE_AO_UVS`: a second UV (a copy of the first) on those meshes.
# What lights up and in which colour is said by the author in their Custom Shaders Patch
# `ext_config.ini` (`ksEmissive` = r,g,b,intensity).
BRILLO_SOLO_LO_CLARO = {"CHARLOTTEFERRISWHEELBUCKET"}   # only the bulbs, not the whole gondola
ESCALA_SOLO_BOMBILLAS = 2.0      # Daytona uses 0.25-0.7, but with emissives of the WHOLE material


def segundo_uv_para(materiales: set) -> int:
    n = 0
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.data.uv_layers:
            continue
        if not any(ms.material and ms.material.name.upper() in materiales for ms in o.material_slots):
            continue
        me = o.data
        if len(me.uv_layers) < 2:
            nueva = me.uv_layers.new(name="UV2")
            for i, l in enumerate(me.uv_layers[0].data):
                nueva.data[i].uv = l.uv
        me.meb_export_settings.uv1 = 1
        me.meb_export_settings.uv2 = 2
        n += 1
    return n


CONDICIONES_NOCHE = {"", "LIGHTS_CHARLOTTE", "NIGHT_SHARP", "NIGHT_SMOOTH", "ALWAYS_ON"}


def brillos_csp(ruta: str) -> dict:
    """{MATERIAL: {"color": (r,g,b), "intensidad": i, "fichero": author's emissive or None}}
    from the author's CSP `ext_config.ini`.

    Takes the `MATERIAL_ADJUSTMENT`s with `ksEmissive` that light up AT NIGHT (no condition,
    `LIGHTS_*`, `NIGHT_*`, `ALWAYS_ON`). Left out: `RACING_FLAG_LOCAL` (yellow-flag lights aren't
    night lights), the `BLINK*` ones and anything by `MESHES` or with wildcards (`?`, `$`): this works
    per material. The author's own emissive comes from the `SHADER_REPLACEMENT`s with
    `RESOURCE_FILE_4 = …` (txEmissive)."""
    if not ruta or not os.path.exists(ruta):
        return {}
    txt = open(ruta, encoding="utf-8", errors="ignore").read()
    ficheros, fuera = {}, {}
    secs = re.split(r"\n(?=\[)", txt)
    for sec in secs:
        mats = re.search(r"(?m)^\s*MATERIALS\s*=\s*(.+)$", sec)
        if not mats:
            continue
        nombres = [m.strip().upper() for m in mats.group(1).split(",") if m.strip()]
        rf = re.search(r"(?m)^\s*RESOURCE_FILE_4\s*=\s*(\S+)", sec)
        if sec.startswith("[SHADER_REPLACEMENT") and rf:
            for m in nombres:
                ficheros[m] = rf.group(1).strip()
    for sec in secs:
        if not sec.startswith("[MATERIAL_ADJUSTMENT") or "ksEmissive" not in sec:
            continue
        if re.search(r"(?m)^\s*ACTIVE\s*=\s*0", sec):
            continue
        cond = re.search(r"(?m)^\s*CONDITION\s*=\s*(\S+)", sec)
        if (cond.group(1).upper() if cond else "") not in CONDICIONES_NOCHE:
            continue
        mats = re.search(r"(?m)^\s*MATERIALS\s*=\s*(.+)$", sec)
        val = re.search(r"(?m)^\s*VALUE_(?:0|\.\.\.)\s*=\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", sec)
        if not mats or not val:
            continue
        r, g, b, i = (float(x) for x in val.groups())
        for m in mats.group(1).split(","):
            m = m.strip().upper()
            if m and "?" not in m and "$" not in m:
                fuera.setdefault(m, {"color": (min(r, 255.0), min(g, 255.0), min(b, 255.0)),
                                     "intensidad": i, "fichero": ficheros.get(m)})
    # 🔴 AND WHAT THE AUTHOR LIGHTS PER MESH. 16 of the author's 47 glow adjustments (Charlotte) go by
    # `MESHES`, and without this they were discarded: among them the 12 MUSCO floodlight heads on the
    # towers. This works per material, so it's only taken when ALL the meshes of that material are on
    # the author's list (musco: 12 of 12; `Charlotte_Logos_A`: 1 of 1). If other meshes share the
    # material (`Day_base_Ads`: 1 of 11; the crane's lights with its body) lighting it would light
    # what the author doesn't: it's left alone.
    if MALLAS_POR_MATERIAL:
        import fnmatch
        for sec in secs:
            if not sec.startswith("[MATERIAL_ADJUSTMENT") or "ksEmissive" not in sec:
                continue
            if re.search(r"(?m)^\s*ACTIVE\s*=\s*0", sec) or re.search(r"(?m)^\s*MATERIALS\s*=", sec):
                continue
            cond = re.search(r"(?m)^\s*CONDITION\s*=\s*(\S+)", sec)
            if (cond.group(1).upper() if cond else "") not in CONDICIONES_NOCHE:
                continue
            ms = re.search(r"(?m)^\s*MESHES\s*=\s*(.+)$", sec)
            val = re.search(r"(?m)^\s*VALUE_(?:0|\.\.\.)\s*=\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", sec)
            if not ms or not val:
                continue
            pats = [x.strip().lower().replace("?", "*") for x in ms.group(1).split(",") if x.strip()]
            r, g, b, i = (float(x) for x in val.groups())
            for mat, mallas in MALLAS_POR_MATERIAL.items():
                if mat in fuera or not mallas:
                    continue
                if all(any(fnmatch.fnmatch(mm, pt) for pt in pats) for mm in mallas):
                    fuera[mat] = {"color": (min(r, 255.0), min(g, 255.0), min(b, 255.0)), "intensidad": i,
                                  "fichero": ficheros.get(mat), "por_malla": True}
    return fuera


# {MATERIAL in upper case: {mesh names in lower case}}: filled by the Blender step
# (`mapa_mallas_por_material`) before asking for the glow list; empty outside Blender.
MALLAS_POR_MATERIAL: dict = {}


def mapa_mallas_por_material() -> dict:
    """From the scene: which meshes use each material (object name without the `.001` suffix)."""
    import bpy
    fuera = {}
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        base = re.sub(r"\.\d{3}$", "", ob.name).lower()
        for slot in ob.material_slots:
            if slot.material:
                fuera.setdefault(slot.material.name.upper(), set()).add(base)
    return fuera


def luces_por_rectangulos(ruta: str) -> dict:
    """{MATERIAL: {"res": (w, h), "rects": [(channel, x, y, w, h)], "canales": {channel: (r, g, b, i)}}}

    The `[CustomEmissive]` sections of the author's CSP mark EXACTLY which rectangles of the texture
    are lights (the Ferris wheel frame, the TV cameraman's red tally light), and the same material's
    `MATERIAL_ADJUSTMENT` gives each channel's colour (`ksEmissive`, `ksEmissive1`…). With that the
    mask is just the lights, not the whole material."""
    if not ruta or not os.path.exists(ruta):
        return {}
    txt = open(ruta, encoding="utf-8", errors="ignore").read()
    secs = re.split(r"\n(?=\[)", txt)
    fuera = {}
    for sec in secs:
        if not sec.upper().startswith("[CUSTOMEMISSIVE"):
            continue
        mats = re.search(r"(?mi)^\s*MATERIALS\s*=\s*(.+)$", sec)
        res = re.search(r"(?mi)^\s*RESOLUTION\s*=\s*([\d.]+)\s*,\s*([\d.]+)", sec)
        rects = [(int(c), float(x), float(y), float(w), float(h)) for c, x, y, w, h in re.findall(
            r'Channel\s*=\s*(\d+)\s*,\s*Start\s*=\s*"([\d.]+)\s*,\s*([\d.]+)"\s*,\s*Size\s*=\s*"([\d.]+)\s*,\s*([\d.]+)"', sec)]
        if not mats or not res or not rects:
            continue
        for m in mats.group(1).split(","):
            fuera[m.strip().upper()] = {"res": (float(res.group(1)), float(res.group(2))), "rects": rects, "canales": {}}
    for sec in secs:
        if not sec.startswith("[MATERIAL_ADJUSTMENT"):
            continue
        mats = re.search(r"(?m)^\s*MATERIALS\s*=\s*(.+)$", sec)
        if not mats:
            continue
        pares = re.findall(r"(?m)^\s*KEY_\S*\s*=\s*ksEmissive(\d?)\s*$\s*^\s*VALUE_\S*\s*=\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", sec)
        for m in mats.group(1).split(","):
            m = m.strip().upper()
            if m in fuera:
                for canal, r, g, b, i in pares:
                    fuera[m]["canales"].setdefault(int(canal or 0), (float(r), float(g), float(b), float(i)))
    return fuera


GROSOR_MIN_LUZ = 1 / 48     # of the texture: at 256 px, 5 px; survives the mid-distance mipmaps
BRILLO_MIN_CANAL = 0.8


def emisiva_por_rectangulos(origen: str, destino_png: str, datos: dict):
    """The emissive built from the author's rectangles, at the diffuse's size."""
    import subprocess
    from PIL import Image, ImageDraw
    w, h = (int(v) for v in subprocess.run([*_R.IM_IDENTIFY, "-format", "%w %h", origen + "[0]"],
                                             capture_output=True, text=True).stdout.split())
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    sx, sy = w / datos["res"][0], h / datos["res"][1]
    imax = max((c[3] for c in datos["canales"].values()), default=1.0) or 1.0
    # 🔴 Symptom (Charlotte): the Ferris wheel didn't light up at night. Two things measured in its
    # emissive: (1) the author's lights are 1-8 px STRIPS (1.5 % of the texture): up close you see
    # them, but the mipmaps blend them with the black and at distance they vanish → a minimum
    # thickness `GROSOR_MIN_LUZ` of the texture; (2) each channel was scaled by its intensity against
    # the largest (0.05 / 0.75 = 7 %), while in AC the CSP flashes them at full with its colour table
    # → each channel at its colour at full brightness, with a floor of `BRILLO_MIN_CANAL`.
    grosor = max(4.0, min(w, h) * GROSOR_MIN_LUZ)
    for canal, x, y, rw, rh in datos["rects"]:
        r, g, b, i = datos["canales"].get(canal, (255.0, 255.0, 255.0, imax))
        k = max(BRILLO_MIN_CANAL, i / imax) / (max(r, g, b) or 1.0)
        color = tuple(int(round(min(255.0, 255.0 * c * k))) for c in (r, g, b)) + (255,)
        x0, y0, x1, y1 = x * sx, y * sy, (x + rw) * sx, (y + rh) * sy
        if x1 - x0 < grosor:
            x0, x1 = (x0 + x1 - grosor) / 2, (x0 + x1 + grosor) / 2
        if y1 - y0 < grosor:
            y0, y1 = (y0 + y1 - grosor) / 2, (y0 + y1 + grosor) / 2
        d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=color)
    im.save(destino_png)
    return imax


def colores_csp(ruta: str) -> dict:
    return {m: v["color"] for m, v in brillos_csp(ruta).items()}


def escala_emisiva(intensidad: float, color) -> float:
    """From AC's intensity (`ksEmissive` 4th value, multiplies the colour) to AMS2's `emissive_scale`,
    within the range Daytona uses (0.25-0.7): the ads (0.01) come out soft and the lamps (0.8-1)
    strong, the way the author left them."""
    brillo = intensidad * max(color) / 255.0
    return round(min(0.7, max(0.2, 0.2 + 0.5 * min(1.0, brillo * 4.0))), 2)


def lista_de_brillos(pedido: str, config_csp: str, existentes: set) -> list:
    """`todo` = everything the author lights at night that exists in the package."""
    if pedido.strip().lower() == "todo":
        todos = set(brillos_csp(config_csp)) | set(luces_por_rectangulos(config_csp))
        return sorted(m for m in todos if m in existentes)
    return [x.strip().upper() for x in pedido.split(",") if x.strip()]


def mapa_de_control(destino: str):
    from PIL import Image
    im = Image.new("RGBA", (128, 128))
    for y in range(128):
        for x in range(128):
            v = (255 if x < y else 0) if x < 120 else int(round(255 * min(1.0, y / 112.0) ** 1.25))
            im.putpixel((x, y), (v, v, v, 255))
    tmp = destino.replace(".dds", ".png")
    im.save(tmp)
    subprocess.run([*_R.IM_CONVERT, tmp, "-define", "dds:compression=none", "-define", "dds:mipmaps=0", destino],
                   check=True, capture_output=True)
    os.remove(tmp)


def brillos_nocturnos(salida: str, nombre: str, materiales: str, config_csp: str = None) -> dict:
    import subprocess
    import generar_mapa as GM
    pista = os.path.join(salida, "Tracks", nombre)
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    control = os.path.join(tex, "gr_control_emisivo.dds")
    mapa_de_control(control)
    datos = brillos_csp(config_csp)
    rects = luces_por_rectangulos(config_csp)
    extension = os.path.dirname(config_csp) if config_csp else None
    mtx = {f[:-4].upper(): f for f in os.listdir(pista) if f.lower().endswith(".mtx")}
    hechos, faltan = [], []
    for m in lista_de_brillos(materiales, config_csp, set(mtx)):
        f = mtx.get(m)
        if not f:
            faltan.append(m)
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8", errors="ignore").read()
        dif = re.search(r'name="diffuse1?Texture".*?<value v="([^"]*)"', txt, re.S)
        origen = os.path.join(tex, dif.group(1).split("\\")[-1]) if dif else None
        if not origen or not os.path.exists(origen):
            faltan.append(m + " (no diffuse)")
            continue
        d = datos.get(m, {"color": (255.0, 255.0, 255.0), "intensidad": 0.5, "fichero": None})
        rect = rects.get(m) if m not in BRILLO_SOLO_LO_CLARO else None
        r, g, b = d["color"]
        k = max(r, g, b) or 1.0
        emis = os.path.join(tex, f"{m.lower()}_emisivo.dds")
        png = emis.replace(".dds", ".png")
        # if the author ships their own emissive (`RESOURCE_FILE_4` in CSP), it rules: it marks
        # EXACTLY what lights up (headlights, signs). Otherwise, the tinted diffuse itself.
        propia = None
        if extension and d.get("fichero") and os.path.isdir(extension):
            # ⚠️ case-insensitively: the CSP says `RV10_emiss.dds` and the file is `rv10_emiss.dds`;
            # on Windows it's the same file, on Linux it isn't (the RV would have lit up entirely
            # with its own diffuse)
            propia = next((os.path.join(extension, f) for f in os.listdir(extension)
                           if f.lower() == d["fichero"].lower()), None)
        base = propia if propia else origen
        orden = [*_R.IM_CONVERT, base + "[0]", "-alpha", "off"]
        if m in BRILLO_SOLO_LO_CLARO:
            orden += ["-colorspace", "gray", "-threshold", "85%", "-colorspace", "sRGB"]
        orden += ["-fill", f"rgb({round(255 * r / k)},{round(255 * g / k)},{round(255 * b / k)})",
                  "-colorize", "0", "(", "+clone", "-fill",
                  f"rgb({round(255 * r / k)},{round(255 * g / k)},{round(255 * b / k)})", "-colorize", "100", ")",
                  "-compose", "multiply", "-composite", "-alpha", "set", "-channel", "A", "-evaluate", "set", "100%",
                  "+channel", png]
        if rect:
            # only the rectangles the author marked as lights
            imax = emisiva_por_rectangulos(origen, png, rect)
            canal0 = rect["canales"].get(0) or next(iter(rect["canales"].values()), (255.0, 255.0, 255.0, imax))
            d = {"color": canal0[:3], "intensidad": imax, "fichero": None}
            base = None
        else:
            subprocess.run(orden, check=True, capture_output=True)
        ok, err = GM.a_dds(png, emis, "dxt5", mipmaps=True)
        os.remove(png)
        if not ok:
            faltan.append(f"{m} ({err})")
            continue
        recorte = "USE_ALPHATEST" in txt
        t = lambda p: f"tracks\\textures\\{nombre}\\{os.path.basename(p)}"   # noqa: E731
        # 🔴 WITHOUT `USE_COLOURISATION` or `TINT_USE_SIMPLE`, even though Daytona's recipes have
        # them: they tint with a colour these meshes don't carry, and the game picks a different one
        # on every load. At night the WHOLE track came out green or red with the exterior cameras
        # (the tint goes into the environment capture: reflections and fog), not in the cockpit.
        # Isolated by bisection: without glows, clean; with glows but without these two defines, clean.
        defs = (["USE_EMISSIVEASLIGHTMAP", "USE_ALPHATEST", "USE_AO_UVS"] if recorte else
                ["USE_EMISSIVEASLIGHTMAP", "USE_FRESNEL", "USE_AO_UVS"])
        cuerpo = ('' if recorte else '  <shaderparam name="fresnelFactor" type="EPT_F32">\n    <value v="0.55" />\n  </shaderparam>\n')
        # 🔴 When the emissive is ONLY the bulbs (the author's rectangles or "only the bright
        # part"), the scale can go much higher without lighting anything else: at 0.7 the Ferris
        # wheel looked off, because only 15 % of its structure glows. In AC CSP's far halo also
        # helps, which AMS2 doesn't have.
        escala = ESCALA_SOLO_BOMBILLAS if (rect or m in BRILLO_SOLO_LO_CLARO) else escala_emisiva(d["intensidad"], d["color"])
        cuerpo += f'  <shaderparam name="emissive_scale" type="EPT_F32">\n    <value v="{escala}" />\n  </shaderparam>\n'
        for par, v in (("diffuseTexture", dif.group(1)), ("emissiveTexture", t(emis)), ("emissiveTexture2", t(control))):
            cuerpo += (f'  <shaderparam name="{par}" type="EPT_TEXTURE">\n    <type t="ET_STANDARD" />\n'
                       f'    <value v="{v}" />\n  </shaderparam>\n')
        nom = re.search(r'name="([^"]+)"', txt).group(1)
        open(ruta, "w", encoding="utf-8").write(
            f'<material VERSION="v1.0.0.1" name="{nom}" shader="Render\\Shaders\\basic_windows.fx" technique="Basic" '
            f'supportsSpecialisedLighting="false" fog="false" antialias="1" numparams="{4 if recorte else 5}" '
            'cull="EBFCT_ANTICLOCKWISE">\n' + cuerpo +
            '  <depthparams>\n    <enabled e="true" />\n    <writeenabled w="true" />\n  </depthparams>\n'
            '  <alphablendparams>\n    <enabled e="false" />\n  </alphablendparams>\n'
            + "".join(f'  <define name="{d}" />\n' for d in defs) + '</material>\n')
        hechos.append((m, f"({round(d['color'][0])},{round(d['color'][1])},{round(d['color'][2])}) "
                       f"×{escala}"
                       + (" [author's rectangles]" if rect else (" [author's emissive]" if propia else ""))))
    return {"hechos": hechos, "faltan": faltan}


def publicidad(salida: str, nombre: str, materiales: str, imagen: str) -> dict:
    """Your own image (`imagen`, e.g. a league's banner) on one or several of the author's ADS.
    It changes the material's texture, not the geometry: it shows wherever the author put that ad.
    `materiales` = MTX names separated by commas (at Charlotte, `N19_CHARLOTTE_TOYOTA_WALL`: ~145 m of
    wall with ~20 different ads). The image, in the proportions of the ad it replaces (Charlotte's
    Toyota one is 1024x256). DXT5 with mipmaps, like every track texture.
    ⚠️ The track belongs to its original author: changing its ads requires their permission."""
    import generar_mapa as GM
    pista = os.path.join(salida, "Tracks", nombre)
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    base = os.path.splitext(os.path.basename(imagen))[0]
    dds = os.path.join(tex, base + ".dds")
    ok, err = GM.a_dds(imagen, dds, "dxt5", mipmaps=True)
    if not ok:
        return {"puestos": [], "faltan": [f"(conversion: {err})"]}
    mtx = {f[:-4].upper(): f for f in os.listdir(pista) if f.lower().endswith(".mtx")}
    puestos, faltan = [], []
    for m in [x.strip().upper() for x in materiales.split(",") if x.strip()]:
        f = mtx.get(m)
        if not f:
            faltan.append(m)
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8", errors="ignore").read()
        nuevo, n = re.subn(r'(name="diffuse1?Texture".*?<value v=")[^"]*(")',
                           lambda mm: mm.group(1) + f"tracks\\textures\\{nombre}\\{base}.dds" + mm.group(2),
                           txt, count=1, flags=re.S)
        if n:
            open(ruta, "w", encoding="utf-8").write(nuevo)
            puestos.append(m)
        else:
            faltan.append(m + " (no diffuse)")
    return {"puestos": puestos, "faltan": faltan}


RELIEVE_ASFALTO_CC0 = os.path.join(_R.TEXTURAS, "asfalto_normal.dds")   # Asphalt031, ambientCG, CC0
LADO_RELIEVE_ASFALTO = 2048


def relieve_de_asfalto(salida: str, nombre: str) -> dict:
    """The RELIEF (normal map) of the racing asphalt.

    Daytona puts a real relief in `normalTexture` (`rz_shared\\tarmac_7_nmp8888`), repeated with the
    same `detailTiling` as the detail; without this step the asphalt carries the example's,
    `color_normal_7F7FFF.dds`: a FLAT colour, zero relief. The library's CC0 normal (Asphalt031 from
    ambientCG, DirectX convention, AMS2's) goes in at 2048 with mipmaps. The author's diffuse stays:
    it's what makes it look like the real track."""
    import subprocess
    import generar_mapa as GM
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    destino = os.path.join(tex, f"{nombre}_asfalto_relieve.dds")
    if not os.path.exists(RELIEVE_ASFALTO_CC0):
        return {"materiales": [], "motivo": f"{RELIEVE_ASFALTO_CC0} is missing"}
    tmp = destino.replace(".dds", "_tmp.png")
    subprocess.run([*_R.IM_CONVERT, RELIEVE_ASFALTO_CC0 + "[0]", "-resize",
                    f"{LADO_RELIEVE_ASFALTO}x{LADO_RELIEVE_ASFALTO}", tmp], check=True, capture_output=True)
    ok, err = GM.a_dds(tmp, destino, "dxt5", mipmaps=True)
    os.remove(tmp)
    if not ok:
        return {"materiales": [], "motivo": err}
    pista = os.path.join(salida, "Tracks", nombre)
    hechos = []
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8", errors="ignore").read()
        if "rz_road_main" not in txt:
            continue
        nuevo, n = re.subn(r'(name="normalTexture".*?<value v=")[^"]*(")',
                           lambda m: m.group(1) + f"tracks\\textures\\{nombre}\\{nombre}_asfalto_relieve.dds" + m.group(2),
                           txt, count=1, flags=re.S)
        if n:
            open(ruta, "w", encoding="utf-8").write(nuevo)
            hechos.append(f[:-4])
    return {"materiales": hechos, "textura": os.path.basename(destino)}


def detalle_de_asfalto(salida: str, nombre: str) -> dict:
    """The asphalt's DETAIL texture, with Daytona's alpha.

    🔴 Symptom (Charlotte): the asphalt burned WHITE under headlights and floodlights; by day, fine.
    Daytona's `roadc.bmt` (read with `bmt_read.py`) has the SAME gloss as the generated one (1 / 18 /
    0.67): what differs is its `tarmac_7_detail`, **mean alpha 0.11**, against the example's
    `AsphaltDynamic_Albedo`, **alpha 1.00**. A copy is made with the example's colour and Daytona's
    alpha, and the road shader uses it as detail.
    """
    import re
    import subprocess

    pista = os.path.join(salida, "Tracks", nombre)
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    origen = os.path.join(tex, "AsphaltDynamic_Albedo.dds")
    propia = f"{nombre}_asfalto_detalle.dds"
    if not os.path.exists(origen):
        return {"materiales": [], "motivo": "AsphaltDynamic_Albedo.dds is missing"}
    subprocess.run([*_R.IM_CONVERT, origen + "[0]", "-alpha", "set", "-channel", "A", "-evaluate",
                    "set", f"{ALFA_DETALLE_ASFALTO * 100:.1f}%", "+channel", "-define",
                    "dds:compression=dxt5", os.path.join(tex, propia)], check=True)
    tocados = []
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8", errors="ignore").read()
        if "rz_road_main" not in txt:
            continue
        nuevo = re.sub(r'(name="detailTexture".*?<value v=")[^"]*(")',
                       lambda m: m.group(1) + f"tracks\\textures\\{nombre}\\{propia}" + m.group(2),
                       txt, count=1, flags=re.S)
        if nuevo != txt:
            open(ruta, "w", encoding="utf-8").write(nuevo)
            tocados.append(f[:-4])
    return {"materiales": tocados, "textura": propia}


ALFA_DETALLE_ASFALTO = 0.113     # Daytona, `rz_shared/tarmac_7_detail.dds` (measured)

from brillo_asfalto import ALFA_BRILLO_ASFALTO, brillo_de_asfalto  # noqa: E402,F401  (sin bpy)


def afinar_brillo(salida: str, nombre: str, fresnel: str = "0.2") -> dict:
    """Sets the asphalt gloss to the references' values, not the add-on's.

    🔴 Symptom on track: the asphalt looked very flat. The Blender add-on writes
    `globalSpecularFactor=0.5` and `specularPower=8.0`, and **both available references agree on
    something else**:

    | | globalSpecularFactor | specularPower | fresnelFactor |
    |---|---|---|---|
    | Texas Motor Speedway (`road_dbv.fx`) | 1.0 | 19 | 0.67 |
    | Mid-Ohio (`rz_road_main_3diffuse.fx`, the same shader as here) | 1.0 | 18 | 0.65 |
    | Charlotte without this step | **0.5** | **8** | 0.60 |

    Two different toolchains and the same value: the odd one out was the add-on. Mid-Ohio's is copied
    because it shares the shader; Texas only confirms.

    ⚠️ It's a change judged **by eye, in game**. There's no way to measure here whether it looks
    right; what can be said is that without it the asphalt falls outside both references. ONLY the
    road shader is touched: grass carries `globalSpecularFactor=0.0` on purpose, and shiny grass looks
    worse than matte.
    """
    import re

    # 🔴 `fresnelFactor` 0.2, not 0.65. With 0.65 — Mid-Ohio's/Texas's, and Daytona's 0.67 — Charlotte
    # came out with almost WHITE asphalt at night, all the way into the distance: it's the
    # environment reflection, which grows towards grazing angles. Bisection in game: without relief
    # still white; with 0.2 and nothing else, grey like Daytona. It wasn't the light: Daytona has 313
    # floodlights and gives MORE light to its track (median 28,382 vs 19,329). ⏳ Still open: why
    # Daytona doesn't suffer from 0.67: its `StaticEnvMapLocation` is its own, and in that test the
    # generated one was still Meadowdale's, moved.
    # `--asphalt-fresnel` exists to TEST that hypothesis: the reflection point is now the track's own
    # (`poner_envmap`), and the 8 tracks measured (Daytona, Mid-Ohio, COTA, GJ, Enna, Sonoma, Willow
    # Springs, Mugello) use 0.55-0.8 with a gloss mask in the diffuse. The default stays 0.2: it only
    # changes on the track built with the option.
    valores = {"globalSpecularFactor": "1.0", "specularPower": "18.0",
               "fresnelFactor": fresnel}
    pista = os.path.join(salida, "Tracks", nombre)
    tocados, antes = [], {}
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        ruta = os.path.join(pista, f)
        txt = original = open(ruta, encoding="utf-8", errors="ignore").read()
        if "rz_road_main" not in txt:
            continue
        for clave, valor in valores.items():
            def _cambia(m, _v=valor, _k=clave):
                antes.setdefault(_k, m.group(2))
                return m.group(1) + _v + m.group(3)
            txt = re.sub(
                r'(<shaderparam name="' + clave + r'" type="EPT_F32">\s*<value v=")'
                r'([^"]*)(")', _cambia, txt, count=1)
        if txt != original:
            open(ruta, "w", encoding="utf-8").write(txt)
            tocados.append(f)
    return {"materiales": tocados, "antes": antes, "ahora": valores}


def _parametros_de(mtx_texto: str):
    """How THIS material names its diffuse and its relief, looking at what it declares.

    It isn't guessed from the shader name: the `shaderparam`s the material really has are read. That
    way a new shader breaks nothing; it just doesn't get a replacement.
    """
    import re as _re

    declarados = set(_re.findall(r'shaderparam name="([A-Za-z0-9_]+)" type="EPT_TEXTURE"',
                                 mtx_texto))
    pares = []
    # 🔴 `detailDiffuseTexture` is the layer seen UP CLOSE (repeated 15 times: the shader has it in
    # `detailUScale/VScale`), and it was being left out. Measured result: the four ground families —
    # grass, terrain and also **the gravel** — carried `GrassDynamic_Albedo` from the Meadowdale
    # template. So up close **the gravel looked like grass**, and from afar it didn't, because the
    # broad layer was its own.
    # 🔴 ONLY the BROAD layer carries colour. Symptom: the grass came out dark, almost black.
    # Reiza's recipe, measured in the two grass materials of the Example Project:
    #   broadDiffuseTexture   Meadowdale_GrassNear_Diffuse   saturation 0.24 · lum 0.22 (COLOUR)
    #   middleDiffuseTexture  GrassDynamic_Albedo_BWHC        saturation 0.00 · lum 0.51 (GREY)
    #   detailDiffuseTexture  GrassDynamic_Albedo_BWHC        saturation 0.00 · lum 0.51 (GREY)
    # The middle and detail ones are MODULATORS (the shader multiplies, ×2 with mean 0.5). With the
    # grass IN COLOUR in the broad, middle and detail layers you get green × green × green: BLACK
    # grass. Fixing only the detail isn't enough, because the middle remains. The recipe is COPIED: the
    # middle and detail layers keep AMS2's generic grass from the template, and they aren't touched
    # here.
    for p in ("diffuse1Texture", "broadDiffuseTexture"):
        if p in declarados:
            pares.append((p, "diffuse"))
    for p in ("normalTexture",):
        if p in declarados:
            pares.append((p, "normal"))
    return pares


def poner_texturas_por_familia(salida: str, nombre: str, carpeta: str) -> dict:
    """Replaces each family's textures with those in `carpeta`, if there are any.

    Looks for `<familia>_diffuse.dds` and `<familia>_normal.dds` — with the family name as
    `familias.py` writes it, without accents: `asfalto`, `hierba`, `muros`, `hormigon`, `vallas`,
    `grava`, `lineas`.

    🔴 Why (measured). The gap wasn't the diffuse resolution but **the relief**: ten asphalt materials
    pointed at `color_normal_7F7FFF.dds`, **16×16 pixels of flat blue**. And there were more very
    visible, very poor AMS1 ones left: the grass at 1024² without a normal, the grandstands at
    256×512, the railing at **8×8**.

    ⚠️ The failed attempt worth remembering: using **Meadowdale's banking** normal, baked for ITS
    geometry, made it worse — the pits looked awful —. **Relief from somewhere else is no better than
    none.** That's why this is an entry point: whoever has a **tileable** texture passes it through
    here; no content is invented or taken from the track next door.

    And where they do NOT come from: another track. Texas's, for instance, are SMS's according to its
    own readme ("All files by SMS"), so whoever converted it can't license them. What's used here is
    **CC0** — see docs/TEXTURES.md.
    """
    import re
    import shutil
    import unicodedata

    if not carpeta or not os.path.isdir(carpeta):
        return {"puestas": {}}

    def sin_tildes(x):
        return "".join(c for c in unicodedata.normalize("NFD", x)
                       if unicodedata.category(c) != "Mn")

    tex = os.path.join(salida, "Tracks", "textures", nombre)
    pista = os.path.join(salida, "Tracks", nombre)
    os.makedirs(tex, exist_ok=True)

    disponibles = {}
    for f in os.listdir(carpeta):
        m = re.match(r"(\w+?)_(diffuse|normal|detalle)\.dds$", f, re.I)
        if m:
            disponibles.setdefault(m.group(1).lower(), {})[m.group(2).lower()] = os.path.join(carpeta, f)

    puestas = {}
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        ruta = os.path.join(pista, f)
        txt = original = open(ruta, encoding="utf-8", errors="ignore").read()
        # the SAME decision as `apretar_uv` (see `recibe_cc0`): if it wasn't tightened there, it isn't
        # set here — or a tileable texture would end up on an untightened UV, or the other way round
        m_dif = re.search(r'name="(?:diffuse1Texture|broadDiffuseTexture)".*?<value v="([^"]*)"', txt, re.S)
        original_tex = (os.path.join(tex, os.path.basename(m_dif.group(1).replace("\\", "/")))
                        if m_dif and m_dif.group(1) else None)
        fam = recibe_cc0(os.path.splitext(f)[0], original_tex)
        recambio = disponibles.get(fam) if fam else None
        if not recambio:
            continue
        # ⚠️ Not every material names its textures the same way, and looking for a single parameter
        # name **doesn't warn** when it isn't found: it replaced asphalt and concrete
        # (`rz_road_main_3diffuse.fx`, which does have `diffuse1Texture`/`normalTexture`) and silently
        # skipped the 11 grass materials and the gravel one, which use `new_ground.fx` and call theirs
        # `broadDiffuseTexture`/`middleDiffuseTexture`. The summary said "asfalto: 10 · hormigon: 5"
        # and looked complete.
        # And there's a case where there's NOTHING to do: walls use `rz_basic.fx`, which **has no
        # relief channel**. It's counted separately so it shows that it was checked.
        for param, clave in _parametros_de(txt):
            if clave not in recambio:
                continue
            base = f"{nombre}_{fam}_{clave}.dds"
            destino = os.path.join(tex, base)
            if not os.path.exists(destino):
                shutil.copy(recambio[clave], destino)
            txt = re.sub(
                r'(<shaderparam name="' + param + r'"[^>]*>.*?<value v=")[^"]*(")',
                lambda m: m.group(1) + f"tracks\\textures\\{nombre}\\{base}" + m.group(2),
                txt, count=1, flags=re.S)
        if txt != original:
            open(ruta, "w", encoding="utf-8").write(txt)
            puestas.setdefault(fam, []).append(f)
    # 🔴 GRAVEL with the GRASS modulator (measured at Jarama): the family's template (`NEARGRASS.mtx`)
    # carries `GrassDynamic_Albedo_BWHC` in the middle and detail layers, so up close the run-off had a
    # grass pattern. Only those two are replaced with `grava_detalle.dds` (CC0, GREY with mean 0.5, as
    # the modulator recipe requires); the author's broad layer stays.
    grava = disponibles.get("grava", {}).get("detalle")
    if grava:
        base = f"{nombre}_grava_detalle.dds"
        for f in sorted(os.listdir(pista)):
            if not f.lower().endswith(".mtx") or F.familia_de(os.path.splitext(f)[0])[0] != "grava":
                continue
            ruta = os.path.join(pista, f)
            txt = original = open(ruta, encoding="utf-8", errors="ignore").read()
            for param in ("middleDiffuseTexture", "detailDiffuseTexture"):
                txt = re.sub(r'(<shaderparam name="' + param + r'"[^>]*>.*?<value v=")[^"]*(")',
                             lambda m: m.group(1) + f"tracks\\textures\\{nombre}\\{base}" + m.group(2),
                             txt, count=1, flags=re.S)
            if txt != original:
                if not os.path.exists(os.path.join(tex, base)):
                    shutil.copy(grava, os.path.join(tex, base))
                open(ruta, "w", encoding="utf-8").write(txt)
                puestas.setdefault("gravel (detail only)", []).append(f)
    return {"puestas": puestas}


def quitar_texturas_huerfanas(salida: str, nombre: str) -> dict:
    """Deletes from the package the textures no material references.

    🔴 Why. Without this step **17 textures nobody asks for, 179 MB**, were being shipped, and almost
    all of them were the example track's **renamed** `charlotte_*`: the grass, the pit wall, the
    banking and even `charlotte_Pray_Graffiti.dds`, which is graffiti on a Meadowdale building. They
    carry the track's name and a picture from somewhere else, the most misleading form of all: it looks
    like work done.

    The references are clean: Mid-Ohio ships 31 and references 28.

    It deletes by the **file → material** relation, the missing one: `verificar_texturas()` already
    checked the opposite (material → file) and that's why it saw nothing. Only what NO `.mtx` names is
    deleted, so it's checkable and safe.
    """
    import re

    pista = os.path.join(salida, "Tracks", nombre)
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    if not os.path.isdir(tex) or not os.path.isdir(pista):
        return {"borradas": [], "bytes": 0}

    citadas = set()
    for f in os.listdir(pista):
        if not f.lower().endswith(".mtx"):
            continue
        txt = open(os.path.join(pista, f), encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r'v="([^"]*\.(?:dds|tga|png))"', txt, re.I):
            citadas.add(m.group(1).replace("\\", "/").split("/")[-1].lower())

    borradas, bytes_ = [], 0
    for f in sorted(os.listdir(tex)):
        if f.lower() in citadas:
            continue
        ruta = os.path.join(tex, f)
        if os.path.isfile(ruta):
            bytes_ += os.path.getsize(ruta)
            os.remove(ruta)
            borradas.append(f)
    return {"borradas": borradas, "bytes": bytes_}


def vaciar_luces(salida: str, nombre: str) -> int:
    """Leaves the `<track>_lights.sgx` EMPTY but valid, instead of another track's lights.

    🔴 Why. `charlotte_lights.sgx` was **byte for byte Meadowdale's**: 21 floodlights with `Position`
    at ground level (Y≈0.25 m) spread over Charlotte's infield, pointing at where something was on
    ANOTHER track.

    No lights are invented: Charlotte has its towers (`nightlight01..07` in the AMS1 MAS) and taking
    the floodlights from there is separate work. The idea was **to stop shipping someone else's**: an
    empty, valid file is worse lighting and better data.
    """
    # ⏳ DISABLED. **Nobody ships an empty lights file**: measured, Mid-Ohio has 2 lights, GJ Kartway 6
    # and the example 21; `NumObjects="0"` without a single `<OBJ_ID>` is a file shape the engine sees
    # in no working content. With it empty **AMS2 crashed**, also with the grid already fixed to 32.
    # See docs/LESSONS.md.
    #
    # So either the inherited one is shipped — Meadowdale's lights at ground level in the infield, bad
    # data — or the one `generar_luces` builds. The right thing isn't emptying it: it's **generating it
    # from the track's own lights**.
    return 0

    ruta = os.path.join(salida, "Tracks", nombre, f"{nombre}_lights.sgx")
    if not os.path.exists(ruta):
        return 0
    antes = open(ruta, encoding="utf-8", errors="ignore").read().count("<LIGHT")
    open(ruta, "w", encoding="utf-8").write(
        "<?xml version='1.0' encoding='utf-8'?>\n"
        '<SCENE FileVersion="0.1.0.0" ExporterVersion="Open Madness Track Tools 0.1.0"'
        ' NumObjects="0" Merged="1" NumPartitions="1">\n</SCENE>\n')
    return antes


def reparar_referencias(salida: str, nombre: str):
    """Rewrites inside the MTX files the paths that still point at the example track.

    ⚠️ **Renaming files doesn't rename what POINTS at them.** The template renames
    `textures/Meadowdale/` to `textures/<name>/`, but the MTX files are written AFTERWARDS by the
    exporter, copied from the borrowed recipes, and still say
    `tracks/textures/Meadowdale/Meadowdale_Surfaces…`. Result: the 32 textures point at files that
    don't exist in the package.
    """
    import re

    pista = os.path.join(salida, "Tracks", nombre)
    tocados = 0
    for f in os.listdir(pista):
        if not f.lower().endswith(".mtx"):
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8").read()
        nuevo = txt.replace(f"textures/{ORIGEN_NOMBRE}/", f"textures/{nombre}/")
        nuevo = nuevo.replace(f"textures\\{ORIGEN_NOMBRE}\\", f"textures\\{nombre}\\")
        nuevo = nuevo.replace(f"{ORIGEN_NOMBRE}_", f"{nombre}_")
        # ⚠️ Path separator: BACKSLASH. Measured: 51 of the 83 generated texture paths used a forward
        # slash, while the `.bff` itself names its 173 entries with backslashes and **so do the 113
        # paths of the three references**. On Windows it usually doesn't matter; inside a pak the
        # lookup is by exact string, and there it does. It's normalised, which is free.
        nuevo = re.sub(r'(v=")([^"]*?)(")',
                       lambda m: m.group(1) + m.group(2).replace("/", "\\") + m.group(3)
                       if (".dds" in m.group(2).lower() or ".tga" in m.group(2).lower()) else m.group(0),
                       nuevo)
        if nuevo != txt:
            open(ruta, "w", encoding="utf-8").write(nuevo)
            tocados += 1
    return tocados


def verificar_texturas(salida: str, nombre: str):
    """Does every texture the materials say they use really exist?

    An MTX with a path that doesn't resolve raises no error when packing: it shows in game, or it
    doesn't. This asks BEFOREHAND, which is the whole difference.
    """
    import re

    pista = os.path.join(salida, "Tracks", nombre)
    faltan, total = [], 0
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        txt = open(pista + os.sep + f, encoding="utf-8").read()
        for ruta in re.findall(r'value v="([^"]*\.dds)"', txt, re.I):
            total += 1
            rel = ruta.replace("\\", "/")
            if not _existe_sin_mayusculas(salida, rel):
                faltan.append((f, rel))
    return total, faltan


def _existe_sin_mayusculas(base: str, rel: str) -> bool:
    """⚠️ The game is case-insensitive; Linux isn't. `tracks/` isn't `Tracks/`, and a naive check
    reports 83 of 83 textures "missing" with all of them present."""
    actual = base
    for parte in rel.split("/"):
        if not parte:
            continue
        try:
            hijos = os.listdir(actual)
        except OSError:
            return False
        casa = next((h for h in hijos if h.lower() == parte.lower()), None)
        if casa is None:
            return False
        actual = os.path.join(actual, casa)
    return True


def generar_limites_de_pista(salida: str, nombre: str, scn: str | None = None,
                             args_aiw: str | None = None):
    """Writes THIS TRACK's `.gcl`: the surface that counts as track.

    🔴 Why it exists. Without this step the package's `track_cut/<track>.gcl` is the example's with the
    name changed — **byte for byte Meadowdale's** (same md5). So Charlotte's track limits were those of
    a road course that looks nothing like it: with Meadowdale's geometry under an oval, either
    everything is off track or nothing is. And since the file existed and the track loaded, there was
    no error.

    The `.gcl` is a separate mesh, not the collision: it says *where you may drive*, not *where there
    is ground*. OMTT exports it from four objects with fixed names; here two are built from the track's
    own materials:

      SMS_GCL_ROAD  <- asphalt and painted lines (the track)
      SMS_GCL_PIT   <- PITROAD* (the pit lane)

    ⚠️ `_ENTRY` and `_EXIT` aren't generated: in the AMS1 AIW the pit entry and exit are waypoints, not
    surface, and the exporter treats them as absent without failing. Effect: the game doesn't tell the
    entry/exit stretch apart, a penalty nuance, not "no limits".

    ⚠️ And an oval's apron goes inside `ROAD` because it's asphalt. It's deliberate and worth knowing:
    driving on the apron will **not** count as going off.
    """
    from trackcompiler.export.gcl_export import export_gcl

    # 🔴 Which meshes the `.gcl` comes from: ONLY those AMS1 marks as **drivable ground**
    # (`HATTarget=True` in the `.scn`). When importing the whole track, the material-family filter put
    # the garage floor, the concrete steps and even a low wall (`RDCP_*`) into the track limits:
    # 20,471 -> 25,601 triangles and the pit area counting as track. The `.scn` flag is authoritative;
    # the material name is a hint.
    suelo = None
    if scn and os.path.exists(scn):
        import scn_read as S

        mallas = S.parse(scn)
        suelo = {k for k, v in mallas.items() if v["suelo"]}

    grupos = {"SMS_GCL_ROAD": [], "SMS_GCL_PIT": []}
    ac = _fisica_ac()
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or obj.name.startswith(("SMS_", "FIS_")):
            continue
        if ac is not None:
            if obj not in ac or obj.get("solo_colision"):
                continue           # collision so you don't fall through, not a track limit (kn5_to_blender)
        elif suelo is not None and obj.name.lower().split(".")[0] not in suelo:
            continue
        mats = list(obj.data.materials)
        if not mats:
            continue
        por_material = {}
        for poly in obj.data.polygons:
            por_material.setdefault(poly.material_index, []).append(poly)
        for idx, polys in por_material.items():
            mat = mats[idx] if idx < len(mats) else None
            if mat is None:
                continue
            destino = gcl_ac(obj.name) if ac is not None else _grupo_gcl(mat.name, obj.name)
            if destino is None:
                continue
            verts, remap, faces = [], {}, []
            for poly in polys:
                cara = []
                for vi in poly.vertices:
                    if vi not in remap:
                        remap[vi] = len(verts)
                        verts.append(obj.data.vertices[vi].co.copy())
                    cara.append(remap[vi])
                faces.append(cara)
            # NOT converted to engine axes HERE: `gcl_export` does the conversion itself
            # (`_convert_coordinate`). Converted twice, the limits come out lying on their side, as
            # happened with the collision — and it wouldn't raise an error either.
            mundo = [obj.matrix_world @ v for v in verts]
            grupos[destino].append(([(p.x, p.y, p.z) for p in mundo], faces))

    creados = {}
    for gname, piezas in grupos.items():
        if not piezas:
            continue
        verts, faces = [], []
        for vs, fs in piezas:
            base = len(verts)
            verts.extend(vs)
            faces.extend([[i + base for i in f] for f in fs])
        malla = bpy.data.meshes.new(gname)
        malla.from_pydata(verts, [], faces)
        malla.update()
        obj = bpy.data.objects.new(gname, malla)
        bpy.context.scene.collection.objects.link(obj)
        creados[gname] = len(faces)

    if not creados:
        return {"ok": False, "error": "no material ended up on the track or the pit lane"}

    # In AC mode it is NOT trimmed: `surfaces.ini` already says what valid track is, and the trim
    # (designed for the infield that AMS1's material family put in as track) ALSO measures the pit lane
    # against the main racing line. Measured on Mountain Peak: the collision has 807 `PITS` triangles
    # and 52 reached the GCL. What's declared rules.
    # ⏳ Suspicion for AMS1, not touched yet: Charlotte also went from 676 to 69 in the pits.
    # Except when the physics lives INSIDE the geometry (Charlotte): there the main file also carries
    # the ROVAL's roads, marked as valid track, and without the trim cutting through the infield
    # wouldn't be going off. ONLY the track is trimmed, never the pit lane (which is exactly what the
    # trim used to eat).
    if _fisica_ac() is None:
        recortes = _acotar_al_trazado(creados, args_aiw)
    elif bpy.context.scene.get("ac_fisica_en_geometria"):
        recortes = _acotar_al_trazado(creados, args_aiw, solo=("SMS_GCL_ROAD",))
    else:
        recortes = {}
    antes = dict(creados)
    creados = {g: _simplificar(g) for g in creados}

    ruta = os.path.join(salida, "Tracks", nombre, "track_cut", f"{nombre}.gcl")
    try:
        r = export_gcl(filepath=ruta, context=bpy.context)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    for gname in creados:
        obj = bpy.data.objects.get(gname)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    return {"ok": True, "grupos": creados, "antes": antes, "recortes": recortes,
            "bytes": os.path.getsize(ruta), "detalle": r}



def _acotar_al_trazado(grupos, ruta_aiw, solo=None):
    """Removes from the `.gcl` what is far from the layout: the infield is not track.

    🔴 Measured: of the 130,322 m² marked as racing surface, **72,918 (56 %) were more than 30 m from
    the line** — the oval's whole interior, in one connected piece with the track. Effect: **cutting
    across the oval doesn't count as going off**, and on an oval the inside is exactly where you cut.

    The limit comes from the AIW itself (`wp_width`, the width declared waypoint by waypoint), not
    from a constant: a wide track keeps its width and a narrow one its own.
    """
    import math

    if not ruta_aiw or not os.path.exists(ruta_aiw):
        return {}

    import aiw_read as A

    aiw = A.parse(ruta_aiw)
    pts = [w.pos for w in aiw.main_path]
    if not pts:
        return {}
    anchos = [max(w.width[0], w.width[1]) for w in aiw.main_path
              if getattr(w, "width", None) and len(w.width) >= 2]
    margen = (sorted(anchos)[int(len(anchos) * 0.9)] if anchos else 12.0) + 8.0
    if bpy.context.scene.get("gr_margen_gcl"):
        # the scene's one includes the APRON (see kn5_to_blender): the AI width no longer
        margen = float(bpy.context.scene["gr_margen_gcl"])

    lado = 16.0
    rejilla = {}
    for p in pts:
        rejilla.setdefault((int(p[0] // lado), int(p[2] // lado)), []).append(p)

    def cerca(x, z):
        cx, cz = int(x // lado), int(z // lado)
        r = int(margen // lado) + 1
        for dx in range(-r, r + 1):
            for dz in range(-r, r + 1):
                for q in rejilla.get((cx + dx, cz + dz), ()):
                    if math.hypot(q[0] - x, q[2] - z) <= margen:
                        return True
        return False

    quitados = {}
    for gname in list(grupos):
        if solo and gname not in solo:
            continue
        obj = bpy.data.objects.get(gname)
        if obj is None:
            continue
        fuera = []
        for poly in obj.data.polygons:
            c = poly.center
            # the GCL mesh is in Blender coordinates: (x, y) is the plane
            if not cerca(c.x, c.y):
                fuera.append(poly.index)
        if not fuera:
            continue
        import bmesh

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in fuera], context="FACES")
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        quitados[gname] = len(fuera)
        grupos[gname] = len(obj.data.polygons)
    return {"quitados": quitados, "margen": margen}


def _simplificar(nombre_obj: str, angulo_grados: float = 8.0) -> int:
    """Merges the object's near-coplanar faces and re-triangulates it.

    🔴 Why. The tutorial says the `.gcl` meshes are made by **dissolving the interior geometry** of
    the physical surface: it's an outline, not the whole track at full resolution. Without this the
    complete mesh goes in.

    What came out, compared with the reference tracks:

    | track | triangles | size |
    |---|---|---|
    | Mid-Ohio (5.1 km) | 4,373 | 1.78 MB |
    | GJ Kartway | 11,110 | 1.43 MB |
    | **Charlotte unsimplified (2.4 km)** | **22,726** | **7.13 MB** |

    Five times denser than a track twice as long. The `.gcl` also carries a 1 m cell grid the engine
    walks when loading — 167,700 at Charlotte —, and it's the heaviest piece the tool generates.

    Near-coplanar faces are merged instead of decimating: on a banked oval the long stretches are
    flat, so a lot of mesh goes **without moving the edge**, which is exactly what defines the track
    limit.
    """
    import bmesh
    import math

    obj = bpy.data.objects.get(nombre_obj)
    if obj is None:
        return 0
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(angulo_grados),
                             verts=bm.verts, edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(obj.data.polygons)


def _grupo_gcl(material: str, objeto: str = ""):
    """Which `.gcl` object this goes to. `None` = it doesn't count as track surface."""
    n = (material or "").upper()
    # The garage is pit area, not track: crossing from there to the track mustn't count as going off,
    # but it can't count as racing asphalt either.
    if n.startswith("PITROAD") or "GARAGE" in (objeto or "").upper() or "GARAGE" in n:
        return "SMS_GCL_PIT"
    fam, _sh, _fis, _don = F.familia_de(material)
    return "SMS_GCL_ROAD" if fam in ("asfalto", "líneas") else None


# ── ASSETTO CORSA MODE ─────────────────────────────────────────────────────────────────
#
# A `kn5_to_blender.py` scene carries the collision SEPARATELY, in the `FISICA_AC` collection, with
# the surface in each mesh name (`01ROAD`, `02WALL`…). Nothing to guess: no `.scn` to know what
# collides, no material family to know what it is.
#
# And the classification comes from `surfaces.ini`, not the name: on Mountain Peak `INFIELD` has
# friction 0.97 — it's ASPHALT (the roval's infield), not grass — and so does `EXTEND`. Mapping by
# name would have cooked asphalt as grass.
SUPERFICIES_AC: dict = {}


def _fisica_ac():
    """The collision objects of an AC scene, or None if the scene is from AMS1."""
    col = bpy.data.collections.get("FISICA_AC")
    return set(col.all_objects) if col is not None else None


def superficie_ac(nombre_obj: str):
    """The rule is `ac_trazado.superficie_de`'s — one single copy, case-insensitive."""
    import ac_trazado as _T

    return _T.superficie_de(nombre_obj, set(SUPERFICIES_AC) | {"WALL"} if SUPERFICIES_AC else None)


def fisica_ac(nombre_obj: str) -> str:
    """AMS2 physical material for an AC collision mesh.

    | surface | friction | physics |
    |---|---|---|
    | WALL | — | CEMENTWALLS |
    | CURB | 0.95 | BUMPYROADS2 (vibrates like a kerb) |
    | not valid and < 0.75 (GRASS 0.60) | | GRASS |
    | everything else (ROAD, APRON, PITS, LINES, EXTEND, INFIELD…) | | ROADS |
    """
    key = superficie_ac(nombre_obj) or ""
    if "WALL" in key:
        return "CEMENTWALLS"
    if key in ("CURB", "KERB"):
        return "BUMPYROADS2"
    sup = SUPERFICIES_AC.get(key)
    if sup and not sup["valida"] and sup["rozamiento"] < 0.75:
        return "GRASS"
    return "ROADS"


def gcl_ac(nombre_obj: str):
    """Track-limits group from `surfaces.ini`: valid -> track; `IS_PITLANE` -> pits."""
    sup = SUPERFICIES_AC.get(superficie_ac(nombre_obj) or "")
    if not sup or not sup["valida"]:
        return None
    return "SMS_GCL_PIT" if sup["boxes"] else "SMS_GCL_ROAD"


ALTURA_REFLEJOS_M = 5.0


def _reflejos_y_centro(aiw) -> dict:
    """`StaticEnvMapLocation`/`StaticConvolveEnvMapLocation` over the finish line, and `TrackCentre`."""
    if not aiw or not aiw.main_path:
        return {}
    mp = aiw.main_path
    x, y, z = mp[0].pos
    cx = sum(w.pos[0] for w in mp) / len(mp)
    cz = sum(w.pos[2] for w in mp) / len(mp)
    punto = f"{x:.3f}; {y + ALTURA_REFLEJOS_M:.3f}; {z:.3f}; 1.0"
    return {"StaticEnvMapLocation": punto, "StaticConvolveEnvMapLocation": punto,
            "TrackCentre": f"{cx:.1f}; 0.0; {cz:.1f}; 1.0"}


def parchear_trd_ac(ruta: str, nombre: str, ui: dict, geo, ruta_aiw: str, titulo=None,
                    limite_boxes=None, fecha=None, max_ia=None, ambiente=None, curvas=None,
                    grupo=None, variante=None, orden=None) -> list:
    """The TRD of an AC track, from its `ui_track.json`.

    ⚠️ Without this the TRD kept the EXAMPLE track's data (Meadowdale), because `parchear_trd` only
    runs with an AMS1 AIW. Coordinates are NOT invented: Mountain Peak's `ui_track.json` has them
    unfilled (literally `"lat"`, `"lon"`), so they come through `--geo` or aren't touched.
    """
    import aiw_read as A

    texto = open(ruta, encoding="utf-8", errors="ignore").read()
    # "2.414 km" (Mountain Peak) or "2343 m" (Charlotte). Only "km" was understood, and with "m"
    # Meadowdale's length stayed: the game's info page said 5.14 km.
    largo = None
    g = re.match(r"\s*([\d.,]+)\s*(km|m)?", str(ui.get("length", "")).lower())
    if g:
        try:
            v = float(g.group(1).replace(",", "."))
            largo = str(int(round(v * 1000 if (g.group(2) or "km") == "km" else v)))
        except ValueError:
            largo = None
    run = str(ui.get("run", "")).lower()
    sentido = "false" if "counter" in run or "anti" in run else ("true" if "clockwise" in run else None)
    aiw = A.parse(ruta_aiw) if os.path.exists(ruta_aiw) else None
    vueltas = {
        **identidad_trd(nombre),
        "TrackName": titulo or ui.get("name") or nombre,
        "Track_Location": ui.get("city") or None,
        "Length": largo,
        # 🔴 `--corners` rules. Symptom: the game said "Corners 2" at Charlotte. The automatic count
        # comes from the centre line's classification, and on an oval without kinks it joins the
        # corners two by two (1-2 and 3-4); with kinks it gave 6. The official ovals say 4 (Fontana,
        # Gateway, Indianapolis, Jacarepaguá) and the tri-ovals 3 (Pocono, Daytona): it's a
        # convention, not something that can be measured.
        "Number Of Turns": (str(int(curvas)) if curvas else (str(_curvas(aiw)) if aiw else None)),
        "Location": ui.get("country") or None,
        "Is Clockwise": sentido,
        # 🔴 AC has no pit limiter in any file, and without this the template's 240 stayed (Mountain
        # Peak: odd behaviour in the pits). The same failure in AMS1 is fixed with `RacePitKPH`. It
        # comes through `--pit-limiter`; if it doesn't, it isn't touched, and the `pit limiter`
        # gate won't let 240 be packed.
        "PitSpeedLimit_HighKPH": f"{float(limite_boxes):.1f}" if limite_boxes else None,
        # `--ambience Daytona`: the time-of-day group and `.wdf` of an OFFICIAL track that exists in
        # the game. The template carries Road America (which doesn't race at night); Charlotte uses Daytona.
        "TimeOfDay Group": ambiente or None,
        "Environment File": f"{ambiente}.wdf" if ambiente else None,
        # the race date (`--date [YYYY-]M-D`): without it Meadowdale's stays, 20 June **1963** — the
        # year showed on screen too. With no year in `--date`, the `ui_track.json` `year` (the model's).
        "Race_Date_Month": str(int(fecha.split("-")[-2])) if fecha else None,
        "Race_Date_Day": str(int(fecha.split("-")[-1])) if fecha else None,
        "Race_Date_Year": (fecha.split("-")[0] if fecha and fecha.count("-") == 2
                           else str(ui.get("year")) if str(ui.get("year") or "").isdigit() else None),
        # 🔴 31, not 32: the game ADDS the player's car. With 32 it said "Number of participants: 33"
        # for 32 grid slots. Texas declares 31.
        # ⚠️ `--max-ai` forces it. On Mountain Peak two tests with 31 hung while loading and one with
        # 32 didn't, but the grass also changed between them: the option exists to isolate which of
        # the two causes it was.
        "Max AI participants": str(int(max_ia)) if max_ia else
        str(min(A.TECHO_PARRILLA, int(ui.get("pitboxes") or 0) or A.TECHO_PARRILLA) - 1),
        "Track_Latitude": f"{geo[0]:.4f}" if geo else None,
        "Track_Longitude": f"{geo[1]:.4f}" if geo else None,
        "Track_Altitude": str(geo[2]) if geo else None,
        "Track_TimeZone": str(geo[3]) if geo else None,
        # 🔴 Meadowdale leftovers (measured: 65 of 96 values in Charlotte's TRD were the template's).
        # The REFLECTIONS point (79; 9; −5) was a random spot in the infield and the track CENTRE
        # (0; 0; 0) the origin: Enna puts the reflections 14 m from its finish line and the centre in
        # the centre. Here: 5 m above the first point of the lap (the finish line: 15 m from the start
        # lights at Charlotte) and the lap's mean. And the model's year instead of Meadowdale's 1963.
        **_reflejos_y_centro(aiw),
        # SEVERAL LAYOUTS, ONE TRACK: together, like the official ones, one venue with several
        # variants. The game groups by `Track Group` (COTA: the three `Circuit_of_the_Americas`) and
        # names each one by `Track_Variation` (GP, National_Circuit, Club_Circuit); `Order Override`
        # decides which comes first.
        "Track Group": grupo or None,
        "Track_Variation": variante or None,
        "Order Override": str(int(orden)) if orden else None,
        "Year": str(ui.get("year")) if str(ui.get("year") or "").isdigit() else None,
    }
    tocados = []
    for clave, valor in vueltas.items():
        if valor is None:
            continue
        pat = re.compile(r'(<prop name="' + re.escape(clave) + r'" data=")[^"]*(")')
        texto, n = pat.subn(lambda m: m.group(1) + valor + m.group(2), texto)
        if n:
            tocados.append(f"{clave}={valor}")
    open(ruta, "w", encoding="utf-8").write(texto)
    return tocados


def cocinar_fisica(salida: str, nombre: str, tmp: str, scn: str | None = None):
    """Generates Charlotte's `.csm`: OBJ split by material -> PhysX -> CSM.

    `PhysicsMeshCooker` assigns the surface **by the object name's prefix** (`ROADS`, `GRASS`,
    `GRAVEL`…), not by the material. But in a gMotor2 track one object (`TRACK01`) carries asphalt,
    lines and grass at once, so it has to be SPLIT by material before exporting, or the whole mesh
    would end up as asphalt.

    It's split by hand walking the polygons instead of with `bpy.ops.mesh.separate`, which needs
    object mode and a window context.
    """
    import subprocess

    import verificar_fisica as V

    # 🔴 Which mesh collides is said by AMS1, not assumed. See `scn_read`: 11 of Charlotte's 51 meshes
    # are marked `CollTarget=False` (inner and outer grass) and cooking them anyway puts invisible
    # ramps on the track.
    mallas_scn = {}
    if scn and os.path.exists(scn):
        import scn_read as S

        mallas_scn = S.parse(scn)

    piezas, descartadas = [], []
    ac = _fisica_ac()
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or obj.name.startswith(("SMS_AIW_", "FIS_")):
            continue
        if ac is not None:
            # AC: the collision is ONLY the `FISICA_AC` collection. What's visible doesn't collide.
            if obj not in ac:
                continue
        elif mallas_scn:
            import scn_read as S

            if not S.choca(mallas_scn, obj.name):
                descartadas.append(obj.name)
                continue
        mats = list(obj.data.materials)
        if not mats:
            continue
        por_material = {}
        for poly in obj.data.polygons:
            por_material.setdefault(poly.material_index, []).append(poly)
        for idx, polys in por_material.items():
            mat = mats[idx] if idx < len(mats) else None
            if mat is None:
                continue
            if ac is not None:
                fisica = fisica_ac(obj.name)
            else:
                _fam, _sh, fisica, _don = F.familia_de(mat.name)
            verts, remap, faces = [], {}, []
            for poly in polys:
                cara = []
                for vi in poly.vertices:
                    if vi not in remap:
                        remap[vi] = len(verts)
                        verts.append(obj.data.vertices[vi].co.copy())
                    cara.append(remap[vi])
                faces.append(cara)
            malla = bpy.data.meshes.new(f"FIS_{fisica}_{mat.name}")
            # 🔴 TO ENGINE COORDINATES, HERE AND NOT IN THE EXPORTER'S OPTIONS.
            # Madness is Y-UP (like gMotor2); Blender is Z-up. If the OBJ comes out with Blender's
            # axes, the collision mesh lies 90° ON ITS SIDE relative to what you see: the car appears
            # where the graphics are, there's nothing underneath and it **sinks into the void**. No
            # error: the track loads.
            # It's done on the vertices so as not to depend on how the OBJ exporter interprets
            # `forward_axis`/`up_axis`.
            mundo = [obj.matrix_world @ v for v in verts]
            # 🔴 (bx, bz, −by): a −90° ROTATION about X, not a mirror. Worked out by measuring the
            # **Example Project**'s physics OBJ against its own AIW: of its 28 grid slots, with the OBJ
            # as is only **8** have asphalt underneath; **with Z inverted, all 28**, and at 0.00 m. So
            # the author exports it with Blender's default axes (Forward −Z / Up Y) = (x, z, −y), while
            # the AIW uses (x, z, y): the two spaces are NOT the same.
            #
            # ⚠️ Simply swapping Y and Z, (x, z, y), **is not a rotation, it's a mirror** (determinant
            # −1), with two effects, both silent:
            # - it flips the winding of EVERY triangle: measured at Charlotte, **22,726 of 22,726
            #   asphalt faces with the normal facing down**. The track shows, the car appears 2 cm above
            #   the asphalt… and goes through it;
            # - it leaves the collision **mirrored relative to the visible track**. Consistent with
            #   itself — that's why `verificar_fisica` passed — and with three symptoms at once: the
            #   grid falls on the grass (the pit straight ends up where the opposite one is), the car
            #   hits the wall before reaching it, and **the banking tilts the wrong way and launches the
            #   car**.
            # The checks that measure WHERE the collision is pass; you also have to measure which way it
            # faces.
            #
            # The tutorial doesn't fall into this because it says to export the OBJ with Blender's
            # exporter and its axes, which does a real **rotation**. Here the conversion is done on the
            # vertices so as not to depend on `forward_axis`/`up_axis` (because of the lying-down
            # collision trap). Since it's a rotation and not a mirror, the face winding **is kept**: no
            # need to flip them. Flipping them hides the mirror's symptom, not its cause.
            malla.from_pydata([(p.x, p.z, -p.y) for p in mundo], [], faces)
            malla.update()
            pieza = bpy.data.objects.new(f"{fisica}_{mat.name}_{len(piezas)}", malla)
            bpy.context.scene.collection.objects.link(pieza)
            piezas.append(pieza)

    for o in bpy.data.objects:
        o.select_set(o in piezas)
    obj_path = os.path.join(tmp, f"{nombre}_physics.obj")
    # identity axes: the conversion is already done on the vertices (see above)
    bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True,
                          export_materials=False, forward_axis="Y", up_axis="Z")

    csm = os.path.join(tmp, f"{nombre}.csm")
    orden, env = _R.orden_cocinero(obj_path, csm)
    r = subprocess.run(orden, cwd=os.path.dirname(COCINERO),
                       capture_output=True, text=True, env=env, timeout=1800)
    salida_cocinero = (r.stdout or "") + (r.stderr or "")
    if not os.path.exists(csm):
        return {"ok": False, "log": salida_cocinero[-600:]}
    destino = os.path.join(salida, "Tracks", nombre, "physics", f"{nombre}.csm")
    shutil.copyfile(csm, destino)
    grupos = salida_cocinero.count("Cooked group")
    return {"ok": True, "piezas": len(piezas), "grupos": grupos,
            "bytes": os.path.getsize(destino), "obj": obj_path,
            "caja": _caja(obj_path), "normales": V.normales_del_suelo(obj_path),
            "descartadas": descartadas}


def _caja(obj_path):
    """(rangeX, rangeY, rangeZ) of the OBJ. In the engine Y is HEIGHT: it must be the smallest."""
    xs, ys, zs = [], [], []
    with open(obj_path, errors="ignore") as fh:
        for l in fh:
            if l.startswith("v "):
                p = l.split()
                xs.append(float(p[1])); ys.append(float(p[2])); zs.append(float(p[3]))
    if not xs:
        return None
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def apagar_coleccion(nombre_parcial: str):
    """Takes out of the view layer whatever must not end up as visible geometry."""
    vl = bpy.context.view_layer
    apagadas = []
    for capa in vl.layer_collection.children:
        if nombre_parcial.lower() in capa.name.lower():
            capa.exclude = True
            apagadas.append(capa.name)
    return apagadas


def main():
    args = _args()
    blend, nombre, salida = args.get("blend"), args.get("nombre", "Charlotte"), args.get("salida")
    if not blend or not salida:
        print("usage: --blend <file> --salida <folder> [--nombre Charlotte]")
        return 2

    bpy.ops.wm.open_mainfile(filepath=blend)
    bpy.ops.preferences.addon_enable(module="trackcompiler")

    borrados = preparar_plantilla(salida, nombre)
    print(f"template ready in {salida} ({borrados} example meb/mtx removed)")

    # AC mode: `surfaces.ini` rules what collides and what is track (see `fisica_ac`).
    if args.get("superficies"):
        import ac_trazado as _T

        SUPERFICIES_AC.update(_T.superficies(args["superficies"]))
        print(f"superficies AC: {len(SUPERFICIES_AC)} — "
              + ", ".join(f"{k}→{fisica_ac('1' + k)}" for k in sorted(SUPERFICIES_AC)))

    apagadas = apagar_coleccion("AIW")
    # AC's collision lives in its own collection and is NOT exported as visible geometry: it's cooked
    # separately. If it were exported, the track would show with the collision mesh on top.
    apagadas += apagar_coleccion("FISICA")
    print(f"collections switched off for the scene export: {apagadas}")

    r = asignar_shaders()
    dds = args.get("dds") or os.path.join(os.path.dirname(args["blend"]), "gmt_plain")
    if os.path.isdir(dds):
        puestas, sin = poner_texturas_propias(dds)
        print(f"the track's OWN textures: {len(puestas)} materials re-pointed"
              + (f" · without texture: {sin}" if sin else ""))
    else:
        print(f"⚠️ can't find the decrypted textures in {dds}: the borrowed ones stay")
    print(f"materials: {r['prestados']} with a recipe borrowed from the example · "
          f"{r['ok']} with a VALID permutation · {len(r['avisos'])} with a warning")
    # ⚠️ `mat_nombre`, NOT `nombre`. With `nombre`, this loop overwrote the track's variable with the
    # name of the last material that warned, and from here on EVERYTHING — the folder, the .sgx, the
    # .trd, the physics, the .gcl — used that name. It only triggered if some material failed the
    # permutation, i.e. **the day something goes wrong**.
    for mat_nombre, fam, shader, aviso in r["avisos"][:10]:
        print(f"  ⚠️ {mat_nombre} ({fam} -> {shader}): {aviso}")

    pista = os.path.join(salida, "Tracks", nombre)
    mallas = [o for o in bpy.context.view_layer.objects if o.type == "MESH"]
    print(f"visible meshes to export: {len(mallas)} | materials: {len(bpy.data.materials)}")

    global CC0_CARPETA, CC0_FAMILIAS
    CC0_CARPETA = args.get("texturas")
    if args.get("familias-cc0"):
        CC0_FAMILIAS = {x.strip().lower() for x in str(args["familias-cc0"]).split(",") if x.strip()}
    factores_uv = apretar_uv(dds_dir=dds)
    if factores_uv:
        detalle = " · ".join(f"{m} {v[1]:.0f}→{v[3]:.1f} m" for m, v
                             in sorted(factores_uv.items())[:4])
        print(f"UV tightened on {len(factores_uv)} materials (metres per repetition): {detalle}")

    if args.get("brillos-nocturnos"):
        MALLAS_POR_MATERIAL.update(mapa_mallas_por_material())
        nb = segundo_uv_para(set(lista_de_brillos(args["brillos-nocturnos"], args.get("config-csp"),
                                                  {mt.name.upper() for mt in bpy.data.materials})))
        print(f"night glows: 2nd UV prepared on {nb} meshes (the recipe uses USE_AO_UVS)")

    if _fisica_ac() is not None:
        qg = quitar_goma_ac()
        if qg:
            print(f"AC RUBBER layers removed from the scene (LiveTrack draws them): {len(qg)} meshes — {', '.join(qg[:6])}")
    su = sin_compresion_uv()
    print(f"UV uncompressed (_no_uv_comp, |uv| > {UV_SIN_COMPRIMIR}): {len(su)} meshes — {', '.join(su[:6])}")
    sgx = os.path.join(pista, f"{nombre}.sgx")
    r = bpy.ops.export_scene.madness(filepath=sgx, export_mtx_files=True)
    print(f"scene export -> {r}")
    if os.path.exists(sgx):
        meb = len([f for f in os.listdir(pista) if f.lower().endswith(".meb")])
        mtx = len([f for f in os.listdir(pista) if f.lower().endswith(".mtx")])
        print(f"  SGX {os.path.getsize(sgx) // 1024} KB · {meb} MEB · {mtx} MTX")

    # --- the SGX: wrapping in LOD, OPTIONAL ---------------------------------------------
    # ⚠️ Both reference tracks wrap each object in a LOD node, which is why this step exists. But
    # **it isn't verified on track**: it went in in the same batch as three other changes, and when
    # the track stopped showing completely there was no way to know which one it was. So by default
    # it is NOT done, and it's turned on by hand with `--lod`, to compare two packages that differ
    # only in this.
    if os.path.exists(sgx) and "--lod" in sys.argv:
        import envolver_lod as L

        rl = L.envolver(sgx)
        print(f"  SGX -> LOD: {rl['envueltos']} objects wrapped · "
              f"{rl['particiones']} partition(s) reordered")
    else:
        print("  SGX -> LOD: NO (use --lod to wrap, like the references)")

    # --- the AIW, from the collection switched off for the scene export ------------------
    for capa in bpy.context.view_layer.layer_collection.children:
        if "aiw" in capa.name.lower():
            capa.exclude = False
    ruta_aiw = os.path.join(salida, "Tracks", "_data", "aiw", f"{nombre}.aiw")
    os.makedirs(os.path.dirname(ruta_aiw), exist_ok=True)
    print(f"AIW -> {bpy.ops.export_scene.aiw(filepath=ruta_aiw)} "
          f"({os.path.getsize(ruta_aiw) // 1024} KB)" if os.path.exists(ruta_aiw) else "AIW FAILED")

    rs = arreglar_sectores(ruta_aiw)
    if rs.get("tocado"):
        print(f"sectors: sector_2_length {rs['s2']:.1f} -> {rs['acumulado']:.1f} "
              f"(the AMS1 original writes it CUMULATIVE from the finish line)")

    # --- el TRD ------------------------------------------------------------------------
    import aiw_read as A
    import gdb_read as G

    aiw = A.parse(args["aiw"]) if args.get("aiw") else None
    gdb = G.parse(args["gdb"]) if args.get("gdb") and os.path.exists(args["gdb"]) else None
    trd = os.path.join(pista, f"{nombre}.trd")
    if aiw and os.path.exists(trd):
        print("TRD:", ", ".join(parchear_trd(trd, nombre, aiw, gdb, args)))
    elif args.get("ui") and os.path.exists(trd):
        import json as _json

        ui = _json.load(open(args["ui"], encoding="utf-8-sig"))
        geo = None
        if args.get("geo"):
            v = [x.strip() for x in str(args["geo"]).split(",")]
            geo = (float(v[0]), float(v[1]), int(float(v[2])), int(float(v[3])))
        print("TRD (AC):", ", ".join(parchear_trd_ac(trd, nombre, ui, geo, ruta_aiw, args.get("titulo"),
                                                         args.get("limite-boxes"), args.get("fecha"),
                                                         args.get("max-ia"), args.get("ambiente"),
                                                         curvas=args.get("curvas"), grupo=args.get("grupo"),
                                                         variante=args.get("variante"), orden=args.get("orden"))))
        if args.get("ovalo"):
            largo = float(re.search(r'name="Length" data="([\d.]+)"', open(trd, encoding="utf-8").read()).group(1))
            print("OVAL TRD:", ", ".join(OV.trd_de_ovalo(trd, largo)))
    elif os.path.exists(trd):
        print("⚠️ TRD NOT PATCHED: neither an AMS1 --aiw nor an AC --ui — the EXAMPLE's data stays")

    # 🔴 `tracks.lod`, `tracks.cul` and an empty `_data/tracklights/<t>.xml` are NOT written. Enna and
    # Texas have them, but **the two tracks made with THIS toolkit by its own author — Mid-Ohio and GJ
    # Kartway — carry none of the three**, and that's the reference that counts: the one made with the
    # same tool. Every invented file is one more assumption the engine can reject silently. The
    # functions are still there, not called, with their reasoning.
    print("invented auxiliary files: none (Mid-Ohio and GJ Kartway have no tracks.lod/cul)")

    # Neither copying another track's nor emptying the file (emptying it crashes AMS2): they're
    # generated from the TOWERS the track already has. See `generar_luces.py`.
    import generar_luces as L

    rl = L.escribir(salida, nombre)
    if rl["luces"]:
        print(f"lights: {rl['luces']} floodlights from the track's towers "
              f"({rl['alturas'][0]:.0f}-{rl['alturas'][1]:.0f} m) — they used to be Meadowdale's")
    else:
        print(f"lights: the inherited file stays — {rl['motivo']}")

    # --- texture formats the engine does NOT accept ------------------------------------
    import generar_mapa as M

    rt = M.convertir_texturas_no_dds(salida, nombre)
    if rt["convertidas"]:
        print(f"textures converted to DDS (the engine accepts nothing else): "
              f"{len(rt['convertidas'])} -> {rt['mtx']} MTX re-pointed "
              f"({', '.join(v for v, _ in rt['convertidas'][:4])})")

    mm = M.poner_mipmaps(salida, nombre)
    if mm:
        print(f"mipmaps added to {len(mm)} track textures that came without them "
              f"({', '.join(f for f, _n in mm[:4])})")

    # --- that the materials point at textures that exist ----------------------------
    print(f"references repaired in {reparar_referencias(salida, nombre)} MTX")
    if args.get("texturas"):
        rt = poner_texturas_por_familia(salida, nombre, args["texturas"])
        if rt["puestas"]:
            print("new textures by family: "
                  + " · ".join(f"{k}: {len(v)} materials" for k, v in sorted(rt["puestas"].items())))

    nd = compensar_detalle(salida, nombre, factores_uv)
    if nd:
        print(f"detail layer recalibrated on {nd} materials (so tightening the UV doesn't turn it into noise)")

    ra = poner_alfatest(salida, nombre)
    if ra["puestos"]:
        print(f"USE_ALPHATEST set on {len(ra['puestos'])} materials with a holed "
              f"texture (they were drawn SOLID): {', '.join(ra['puestos'][:5])}…")
    # 🔴 A material used by VISIBLE geometry with no `.mtx`: the mesh points at something that doesn't
    # exist and the engine paints it however it likes (that's how Charlotte's `oval line` rubber came out).
    pista_dir = os.path.join(salida, "Tracks", nombre)
    hay_mtx = {f[:-4].upper() for f in os.listdir(pista_dir) if f.lower().endswith(".mtx")}
    fis = _fisica_ac() or set()
    sin_mtx = sorted({sl.material.name for o in bpy.context.scene.objects
                      if o.type == "MESH" and o not in fis and not o.hide_render
                      for sl in o.material_slots
                      if sl.material and sl.material.name.upper() not in hay_mtx})
    if sin_mtx:
        print(f"🔴 {len(sin_mtx)} visible materials WITHOUT .mtx: {', '.join(sin_mtx[:6])}")
    if _fisica_ac() is not None:
        rm = poner_mezcla_ac(salida, nombre)
        print(f"AC alpha blending copied to {len(rm['puestos'])} of {rm['declarados']} materials"
              + (f"· HIDDEN (rubber: < 5 % opaque, or horizontal and < 10 %; LiveTrack draws it): {', '.join(rm['sin_recorte'][:5])}"
                 if rm["sin_recorte"] else ""))

    rq = quitar_defines_huerfanos(salida, nombre)
    for define, mats in rq["quitados"].items():
        print(f"orphan define {define} removed from {len(mats)} materials "
              f"(it asked for an unbound texture)")

    rb = afinar_brillo(salida, nombre, fresnel=str(float(args["fresnel-asfalto"])) if args.get("fresnel-asfalto") else "0.2")
    if rb["materiales"]:
        print(f"asphalt gloss on {len(rb['materiales'])} materials: "
              f"specular {rb['antes'].get('globalSpecularFactor','?')}→1.0 · "
              f"power {rb['antes'].get('specularPower','?')}→18.0 (Mid-Ohio and Texas values)")

    if args.get("relieve-asfalto"):
        rr = relieve_de_asfalto(salida, nombre)
        print(f"asphalt relief (CC0 normal) on {len(rr['materiales'])} materials"
              + (f": {rr['textura']}" if rr.get("textura") else f" · 🔴 {rr.get('motivo')}"))
    rd = detalle_de_asfalto(salida, nombre)
    if rd.get("materiales"):
        print(f"asphalt detail with Daytona's alpha ({ALFA_DETALLE_ASFALTO}) on "
              f"{len(rd['materiales'])} materials: {rd['textura']}")
    if args.get("capas-ac"):
        import json as _json
        import capas_ac as _CA
        datos_ca = _json.load(open(args["capas-ac"]))
        rca = _CA.hornear_asfalto(salida, nombre, datos_ca)
        if datos_ca and not rca["materiales"]:
            print(f"🔴 MULTILAYER asphalt: {len(datos_ca)} multilayer materials in AC and NONE matched a "
                  "road material in the package (different names?)")
        print(f"AC MULTILAYER asphalt on {len(rca['materiales'])} materials: tone in {', '.join(rca['texturas'])} · "
              "the author's grain every (repeat X, Y · metres): "
              + ", ".join(f"{k} {v[0]}×{v[1]} · {v[2]} m" for k, v in rca.get("repeticion", {}).items()))
    if args.get("brillo-asfalto"):
        import json as _json
        ruta_ac = args["brillo-asfalto"]
        brillo_ac = _json.load(open(ruta_ac)) if os.path.exists(ruta_ac) else None
        rbr = brillo_de_asfalto(salida, nombre, brillo_ac=brillo_ac)
        if brillo_ac and not rbr["especular"]:
            print(f"🔴 ORIGINAL gloss: {len(brillo_ac)} materials read from AC and NONE matched a "
                  "road material in the package (different names?)")
        if rbr["especular"]:
            mates = sorted(k for k, v in rbr["especular"].items() if v < 0.5)
            print(f"   ORIGINAL gloss on {len(rbr['especular'])} road materials · matte: {', '.join(mates) or 'none'}")
        print(f"asphalt gloss mask (alpha {rbr['alfa']}, Daytona) on {len(rbr['materiales'])} materials"
              f" · {len(rbr['texturas'])} textures copied · kept (they already have a mask): "
              + (", ".join(rbr["respetadas"]) or "ninguna"))

    if args.get("vallas-translucidas"):
        rv = vallas_translucidas(salida, nombre)
        print(f"translucent fences (Daytona's recipe): {len(rv['hechas'])} materials"
              + (f" · left as they were: {', '.join(rv['saltadas'][:6])}" if rv["saltadas"] else ""))
    if args.get("brillos-nocturnos"):
        rb = brillos_nocturnos(salida, nombre, args["brillos-nocturnos"], args.get("config-csp"))
        print(f"night glows on {len(rb['hechos'])} materials: "
              + ", ".join(f"{m} {c}" for m, c in rb["hechos"])
              + (f" · 🔴 not found: {', '.join(rb['faltan'])}" if rb["faltan"] else ""))
    if args.get("publicidad"):
        mats, _, img = str(args["publicidad"]).partition("=")
        rp = publicidad(salida, nombre, mats, img)
        print(f"own ads ({os.path.basename(img)}) on {len(rp['puestos'])} ads: {', '.join(rp['puestos'])}"
              + (f" · 🔴 not found: {', '.join(rp['faltan'])}" if rp["faltan"] else ""))
    if bpy.context.scene.get("gr_semaforos"):
        import json
        import generar_semaforos as GS
        rsem = GS.escribir(salida, nombre, json.loads(bpy.context.scene["gr_semaforos"]))
        print(f"start lights: {rsem['mtx']} own materials · {rsem['texturas']} textures · "
              f"{os.path.relpath(rsem['xml'], salida)}")
    rh = quitar_texturas_huerfanas(salida, nombre)
    if rh["borradas"]:
        print(f"textures no material references: {len(rh['borradas'])} deleted "
              f"({rh['bytes'] / 1e6:.0f} MB) — {', '.join(rh['borradas'][:3])}…")

    total, faltan = verificar_texturas(salida, nombre)
    if faltan:
        print(f"🔴 TEXTURES THAT DON'T EXIST: {len(faltan)} of {total}")
        for f, rel in faltan[:8]:
            print(f"     {f} -> {rel}")
    else:
        print(f"✅ all {total} texture references resolve to a file in the package")

    # --- the physics: without this you drive on the example track -----------------
    # ⚠️ A CLEAN folder every time. Wine **is case-insensitive** (it mimics Windows on a case-sensitive
    # file system): if a `Charlotte.csm` from an earlier run is left and now `charlotte.csm` is
    # requested, the cooker says "Wrote charlotte.csm" and writes INTO THE OTHER ONE. The script looks
    # for its own, doesn't find it, and the physics is left out of the package without any error.
    tmp = os.path.join(os.path.dirname(salida), f"fisica-{nombre}")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    rf = cocinar_fisica(salida, nombre, tmp, args.get("scn"))
    if rf["ok"]:
        print(f"PHYSICS: {rf['piezas']} pieces by material -> {rf['grupos']} groups "
              f"cooked -> {rf['bytes'] // 1024} KB of CSM")
        if rf.get("descartadas"):
            print(f"  meshes LEFT OUT of the collision because the AMS1 .scn says they don't collide: "
                  f"{len(rf['descartadas'])} ({', '.join(rf['descartadas'][:4])}…)")
        elif _fisica_ac() is not None:
            print(f"  AC collision: only the FISICA_AC collection ({len(_fisica_ac())} meshes)")
        elif not args.get("scn"):
            print("  ⚠️ no --scn: EVERYTHING is cooked, including scenery that shouldn't collide")
        cx, cy, cz = rf["caja"]
        print(f"  collision box: X {cx:.1f} · Y {cy:.1f} · Z {cz:.1f} m")
        if cy > min(cx, cz):
            print("  🔴 HEIGHT IS NOT ON Y: the collision is LYING ON ITS SIDE, the car will fall into the void")
        else:
            print("  ✅ height is on Y, as the engine wants it")
        nn = rf.get("normales") or {}
        if nn.get("abajo", 0) > nn.get("arriba", 0):
            print(f"  🔴 THE GROUND FACES POINT DOWN ({nn['abajo']} of {nn['total']}): "
                  f"the car goes THROUGH the asphalt")
        elif nn:
            print(f"  ✅ the ground faces up: {nn['arriba']} of {nn['total']} faces")
    else:
        print(f"PHYSICS FAILED:\n{rf['log']}")

    # --- the TRACK LIMITS, which without this would be Meadowdale's ------------------
    rg = generar_limites_de_pista(salida, nombre, args.get("scn"),
                                  args.get("aiw") or (ruta_aiw if _fisica_ac() is not None else None))
    if rg["ok"]:
        det = " · ".join(
            f"{k.replace('SMS_GCL_', '').lower()}: {rg['antes'][k]}→{v} tri"
            for k, v in rg["grupos"].items())
        print(f"TRACK LIMITS: {det} -> {rg['bytes'] // 1024} KB of GCL")
        q = (rg.get("recortes") or {}).get("quitados") or {}
        if q:
            print(f"  trimmed to the layout (margin {rg['recortes']['margen']:.0f} m): "
                  f"{sum(q.values())} polygons out — the infield is not track")
        total = sum(rg["grupos"].values())
        if total > 15000:
            print(f"  ⚠️ {total} triangles: the references are between 4,000 and 11,000")
    else:
        print(f"🔴 TRACK LIMITS: {rg['error']} — the EXAMPLE's stay")

    print(f"\nPACKAGE READY in {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
