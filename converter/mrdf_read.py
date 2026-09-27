"""Reader for LiveTrack's `.mrdf` (rubber and puddle grid), the format written by
`omtt/tc020/export/livetrack_mrdf_export.py`.

    python3 mrdf_read.py <file.mrdf> [--celdas]

MRDF header (16 B) + section directory (8 B each) + extended header, and in the PRIMARY_DATA
section: world bounds (x0, y0, x1, y1 in BLENDER axes: the plane is XY), grid width × height, cell
size, number of cells and, per cell, (grid x, friction, height, grip, flags) in 6 bytes, grouped
by rows.
"""
import struct
import sys


def leer(ruta, celdas=False):
    d = open(ruta, "rb").read()
    if d[:1] != b"Q":
        raise ValueError("no es un MRDF")
    nsec, ext = d[3], d[4]
    secs, o = [], 16
    for _ in range(nsec):
        tam, tipo, pad = struct.unpack_from("<IB", d, o) + (d[o + 5],)
        secs.append((tipo, tam, pad))
        o += 8
    o += ext
    p = o                                           # PRIMARY_DATA
    x0, y0, x1, y1 = struct.unpack_from("<4f", d, p + 0x08)
    w, h = struct.unpack_from("<2I", d, p + 0x18)
    celda = struct.unpack_from("<f", d, p + 0x24)[0]
    n = struct.unpack_from("<I", d, p + 0x28)[0]
    r = {"secciones": secs, "limites": (x0, y0, x1, y1), "rejilla": (w, h), "celda": celda,
         "celdas": n, "ocupacion": n / max(1, w * h)}
    if celdas:
        off = struct.unpack_from("<Q", d, p + 0x58)[0]
        tabla = struct.unpack_from("<Q", d, p + 0x68)[0]
        filas = struct.unpack_from(f"<{h + 1}I", d, p + tabla)
        lista = []
        for fy in range(h):
            for k in range(filas[fy], filas[fy + 1]):
                gx, fr, al, ag, fl = struct.unpack_from("<HBBBB", d, p + off + k * 6)
                lista.append((gx, fy, fr, al, ag, fl))
        r["lista"] = lista
    return r


if __name__ == "__main__":
    import collections
    r = leer(sys.argv[1], celdas=True)
    l = r.pop("lista")
    print({k: (tuple(round(v, 1) for v in x) if isinstance(x, tuple) and isinstance(x[0], float) else x)
           for k, x in r.items()})
    for i, nombre in ((2, "rozamiento"), (3, "altura"), (4, "agarre"), (5, "banderas")):
        c = collections.Counter(x[i] for x in l)
        print(f"  {nombre}: {len(c)} values · most common {c.most_common(5)}")
