"""Reader for AMS1's `.scn`: which mesh collides, which one is driven on and which is just scenery.

🔴 Why it exists: cooking **all** visible meshes as collision is a mistake. The `.scn` —which
ships with the track— says the opposite, mesh by mesh:

    MeshFile=OUTFIELD.gmt CollTarget=False HATTarget=False

Measured on Charlotte over the **207 meshes declared in the `.scn`**: **151 with
`CollTarget=False`** (73 % of the scene: grandstands, cones, crowd, signs, ambulances, the infield
grass and the whole outer area), **27 ground meshes** (`HATTarget=True`) and 29 walls. The filter
discards three out of every four meshes. They are decorative meshes, large and coarse, that
**intersect the track** — and cooking them as collision means placing invisible ramps on top of
the asphalt: the car reaches a point where it takes off and flies, and the race starts on the grass.

The two flags are not the same thing:

- `CollTarget` — **it collides**. A wall collides.
- `HATTarget` — *Height Above Terrain*: **it is ground you drive on**. A wall is not.

On Charlotte: **27 ground meshes** (`TRACK01..24`, `TRACK_GARAGE`, `garage_floor`…),
29 walls and **151 scenery meshes**.

⚠️ And there is a third class worth keeping an eye on: `xfinish`, `xsector1/2`, `xpitin`,
`xpitout` are `CollTarget=True, HATTarget=False` — **invisible timing planes** that cross the
track. If a track imports them and they get cooked, the car goes flying when it crosses the
finish line.

No `bpy`: it is tested without Blender.
"""

from __future__ import annotations

import re

_MALLA = re.compile(r"MeshFile\s*=\s*(\S+?)\.gmt([^\n]*)", re.I)


def parse(path: str) -> dict:
    with open(path, "r", encoding="latin-1") as fh:
        return parse_text(fh.read())


def parse_text(texto: str) -> dict:
    """{lowercase name: {"choca": bool, "suelo": bool}}"""
    fuera = {}
    for m in _MALLA.finditer(texto):
        fuera[m.group(1).lower()] = {
            "choca": _bandera(m.group(2), "CollTarget"),
            "suelo": _bandera(m.group(2), "HATTarget"),
        }
    return fuera


def _bandera(resto: str, nombre: str) -> bool:
    """Missing = True: in gMotor2 colliding is the norm; what gets declared is the exception."""
    m = re.search(rf"{nombre}\s*=\s*(\w+)", resto, re.I)
    return True if m is None else m.group(1).lower() == "true"


def choca(mallas: dict, nombre_objeto: str) -> bool:
    """Should this Blender mesh go into the collision mesh?

    The object name in Blender comes from the `.gmt`, and Blender appends `.001` when duplicating.
    Whatever does not appear in the `.scn` **is** cooked: removing something unidentified from the
    physics is worse than leaving it in.
    """
    base = nombre_objeto.lower().split(".")[0]
    entrada = mallas.get(base)
    return True if entrada is None else entrada["choca"]
