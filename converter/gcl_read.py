"""Minimal reader for the `.gcl` (track limits): header and triangles.

🔴 Why it exists: the `.gcl` and the `.csm` of the same package are in **different spaces on
purpose**: the GCL in `(x, z, y)` —because `gcl_export` does the conversion by itself— and the
physics in `(x, z, −y)`. They have to be checked together: "fixing" the GCL to be consistent with
the physics would break the track limits **without anything saying so**.

Format (from `OMTT Docs/Formats/GCL.md` and from `gcl_export.py` itself):
    u32 version · u32 triangle count · f32 cell(100) · 3×f32 origin · 2×u32 grid
    then, per triangle: 3 × (3×f32) + u32 flag  = 40 bytes

No dependencies: it is tested without Blender and without the game.
"""

import struct

CABECERA = 32
TRIANGULO = 40


def cabecera(path: str) -> dict:
    with open(path, "rb") as fh:
        d = fh.read(CABECERA)
    ver, tri, celda, ox, oy, oz, gx, gz = struct.unpack_from("<IIffffII", d, 0)
    return {"version": ver, "triangulos": tri, "celda": celda,
            "origen": (ox, oy, oz), "rejilla": (gx, gz)}


def triangulos(path: str, limite: int | None = None):
    """(a, b, c, flag) per triangle, in engine coordinates."""
    cab = cabecera(path)
    n = cab["triangulos"] if limite is None else min(limite, cab["triangulos"])
    with open(path, "rb") as fh:
        fh.seek(CABECERA)
        crudo = fh.read(n * TRIANGULO)
    for i in range(n):
        v = struct.unpack_from("<9fI", crudo, i * TRIANGULO)
        yield (v[0:3], v[3:6], v[6:9], v[9])


def caja(path: str):
    """(minX, maxX, minY, maxY, minZ, maxZ) of the limits mesh."""
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3
    for a, b, c, _f in triangulos(path):
        for p in (a, b, c):
            for k in range(3):
                mn[k] = min(mn[k], p[k])
                mx[k] = max(mx[k], p[k])
    return (mn[0], mx[0], mn[1], mx[1], mn[2], mx[2])


def banderas(path: str):
    """How many triangles of each class: 0x1 track, 0x2 pits, 0x4 pit exit, 0xA pit entry."""
    import collections

    return dict(collections.Counter(f for _a, _b, _c, f in triangulos(path)))
