"""Surface families: from a gMotor2 material name to its Madness shader.

A single table for the two things that depend on it —the shader it is rendered with and the prefix
`PhysicsMeshCooker` uses to assign its physical surface—, because the cooker classifies **by
object name** and it would be the same decision written twice.

No `bpy`: it is tested without Blender.
"""

# ⚠️ ORDER MATTERS: from the most specific to the most general. `ROADLINES` starts with
# `ROAD`, so with "asfalto" first the lines would be rendered as asphalt — and it would not raise
# any error. You see it by reading the table, not by seeing that the script finishes fine.
FAMILIAS = [
    # 🔴 WALLS BEFORE CONCRETE. `CONCWALL*` starts with `CONC`, so with concrete first the
    # concrete walls of **Nazareth** (9 meshes) and **Texas** came out again as a DRIVABLE
    # surface: cars went through the walls on track. Measured over the 32 tracks of an AMS1
    # pack.
    ("líneas", ("ROADLINES", "ROADLINE", "LINE"), "rz_basic", "ROADS", "PAINTLINE_WHITE.mtx"),
    ("muros", ("WALL", "CMWL", "INWL", "TOPWALL", "CONCWALL"), "rz_basic", "CEMENTWALLS",
     "PITWALL_BAKED.mtx"),
    # ⚠️ `FENCESHADOW*`/`FENCESHAD` are fence SHADOWS (Hampshire, Indy, Phoenix): with plain
    # `FENCE` they were cooked as guardrails. They go first, and out of the physics.
    ("decorado", ("FENCESHAD", "CONCESSION", "BANNER", "SHADOW"), "rz_basic", "BUMPYROADS2",
     "PLACEHOLDER_CONCRETE.mtx"),
    ("vallas", ("FENCE",), "rz_basic", "GUARDRAILS", "PLACEHOLDER_CONCRETE.mtx"),
    ("hormigón", ("RDCP", "CONC"), "rz_basic", "BUMPYROADS2", "PLACEHOLDER_CONCRETE.mtx"),
    # 🔴 `RDH1`, `RDM1`, `RDL1`… with a DIGIT instead of a letter: this is the racing asphalt of
    # **Pocono** (RDH1..3, RDM1..3, RDL1..3), **Marty**, **Atlanta**, **Kentucky**,
    # **Mansfield**, **Iowa** and **Talladega**. **None** of them matched the patterns
    # `RDHI`/`RDMID`/`RDLOW`: the main track fell into "sin clasificar" (unclassified) and, above
    # all, was left **out of the `.gcl`** — no track limits, and nothing said so.
    #
    # ⚠️ And the opposite: `ROADOUT`/`ROAD_OUT`/`ROADIN` are access roads OUTSIDE the oval
    # (7 tracks), `ROADDIRT01..05` is dirt (Chicago), `ROADVICTORY*` and `*FLOOR` the victory
    # lane floor, and `ROAD_TUNNEL` a tunnel. All of them came in as racing asphalt and were
    # added to the `.gcl`. They are excluded up front.
    ("fuera de pista", ("ROADOUT", "ROAD_OUT", "ROADIN", "ROAD_IN", "ROADDIRT",
                        "ROADVICTORY", "ROADV", "ROAD_R", "ROAD_Y", "ROAD_G",
                        "ROAD_TUNNEL", "ROADLIGHT"), "rz_basic", "BUMPYROADS2",
     "PLACEHOLDER_CONCRETE.mtx"),
    ("asfalto", ("RDHI", "RDMID", "RDLOW", "RDH", "RDM", "RDL", "ROAD", "APRON", "PITROAD"),
     "rz_road_main_3diffuse", "ROADS", "ROAD.mtx"),
    # 🔴 `GRAS_X01`/`GRAS_X02` —with ONE "s", at Jarama— and the gravel `SAND_01` fell into
    # "sin clasificar" → `rz_basic` with just the base map, no detail: the largest grass area of
    # the track was a stretched colour map, blurry up close.
    ("hierba/terreno", ("GRASS", "GRAS", "OUTFIELD", "OUTFLD", "TERR"), "new_ground", "GRASS",
     "MIDGRASS.mtx"),
    ("grava", ("GRVL", "GRAVEL", "SAND"), "new_ground", "GRAVEL", "NEARGRASS.mtx"),
]

SIN_CLASIFICAR = ("sin clasificar", "rz_basic", "ROADS", "PLACEHOLDER_CONCRETE.mtx")


def familia_de(nombre: str):
    """(familia, shader, prefijo_de_fisica, mtx_donante). Anything unrecognised falls into `rz_basic`.

    The **donor** is an MTX from OMTT's Example Project: a shader permutation the game already
    loads, with its parameters tuned. Copying it and changing its texture is safer than composing
    one by hand, where an uncompiled permutation leaves the mesh **invisible without any error**.
    """
    n = (nombre or "").upper()
    for fam, patrones, shader, fisica, donante in FAMILIAS:
        if any(n.startswith(p) for p in patrones):
            return fam, shader, fisica, donante
    return SIN_CLASIFICAR


def familia_por_nombre(familia: str):
    """(familia, shader, prefijo_de_fisica, mtx_donante) of a family in the table."""
    for fam, _patrones, shader, fisica, donante in FAMILIAS:
        if fam == familia:
            return fam, shader, fisica, donante
    raise KeyError(familia)


def ruta_shader(shader: str) -> str:
    """The short name -> the path the MTX expects."""
    return f"Render\\Shaders\\{shader}.fx"
