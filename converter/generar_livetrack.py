"""The LiveTrack `.mrdf` of an AC circuit: the grid on which AMS2 paints the rubber.

    python3 generar_livetrack.py <AC folder> <layout> <output.mrdf> [--fisica phy.kn5]

🔴 Why: without this step the packages carried the `.mrdf` of the SAMPLE circuit
(Meadowdale): rubber and puddles were computed over a rectangle that does not even
match the track. OMTT ships an exporter (`tc020/export/livetrack_mrdf_export.py`),
but it needs a hand-built Geometry Nodes tree; this one writes the SAME format without
Blender.

The recipe is NOT invented: it was measured on the `.mrdf` of Mid-Ohio (Reiza) and of COTA.
- cell ~1 m (Mid-Ohio 0.90; COTA 1.05), Blender axes: X = AIW x, Y = AIW z;
- flag 2 = asphalt; 3 = asphalt + RUBBER STRIP: in Mid-Ohio the cells with bit 0 all fall
  < 5 m from the racing line (188/588/969/990/359/43 cells at 0-1…5-6 m, then 0);
- «friction» = distance to the racing line: median 7 at 0-1 m, 18, 30, 44… 196 at 15-16 m
  (12.7 per metre, capped at 255), a smooth field (correlation with the neighbour 1.0);
- height (puddles) and grip: median 0 in both references. 0 here.
"""
import math
import os
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ac_trazado as T  # noqa: E402

CELDA = 1.0
FRANJA_GOMA_M = 4.5
POR_METRO = 12.75
ASFALTO = {"ROAD", "APRON", "PIT", "PITS"}


def _escribir(ruta, x0, y0, x1, y1, ancho, alto, celda, celdas):
    """Same format as `livetrack_mrdf_export.write_mrdf_file` (copied field by field)."""
    from io import BytesIO
    celdas = sorted(celdas, key=lambda c: (c[1], c[0]))
    filas = [len(celdas)] * (alto + 1)
    filas[0] = 0
    actual = 0
    for i, c in enumerate(celdas):
        while actual < c[1] and actual < alto:
            actual += 1
            filas[actual] = i
    filas[alto] = len(celdas)
    b = BytesIO()
    b.write(b"\x00" * 8)
    b.write(struct.pack("<4f", x0, y0, x1, y1))
    b.write(struct.pack("<2I", ancho, alto))
    b.write(struct.pack("<If", 0, celda))
    b.write(struct.pack("<I", len(celdas)))
    b.write(struct.pack("<f", celda))
    b.write(b"\x00" * 40)
    tam = len(celdas) * 6
    pad = (4 - tam % 4) % 4
    b.write(struct.pack("<Q", 0x70))
    b.write(b"\x00" * 8)
    b.write(struct.pack("<Q", 0x70 + tam + pad))
    for gx, _gy, fr, al, ag, fl in celdas:
        b.write(struct.pack("<H", gx))
        b.write(bytes([fr, al, ag, fl]))
    b.write(b"\x00" * pad)
    for o in filas:
        b.write(struct.pack("<I", o))
    primaria = b.getvalue()
    punteros = b"".join(struct.pack("<II", o, 0) for o in (0x58, 0x68))
    # (type, value) pairs and the TOTAL at the end — like the exporter and like Mid-Ohio
    raster = (struct.pack("<If", 3, 0.01608) + struct.pack("<If", 3, 0.0)
              + struct.pack("<If", 3, 0.0) + struct.pack("<I", 3))
    with open(ruta, "wb") as f:
        f.write(b"Q")
        f.write(bytes([0x02, 0x01, 3, 8]))
        f.write(struct.pack("<H", 256))
        f.write(bytes([0x04]))
        # OMTT's exporter writes 8 RANDOM bytes: here they are derived from the content, so
        # that two identical builds give the same file and zip-to-zip comparisons do not lie
        import hashlib
        f.write(hashlib.sha256(primaria).digest()[:8])
        f.write(struct.pack("<I", len(primaria)) + b"\x01\x0c\x00\x00")
        f.write(struct.pack("<I", len(punteros)) + b"\x10\x00\x00\x00")
        f.write(struct.pack("<I", len(raster)) + b"\x50\x04\x00\x00")
        f.write(b"\x00" * 8)
        f.write(primaria)
        f.write(b"\x00" * 12)
        f.write(punteros)
        f.write(raster)
        f.write(b"\x00" * 4)


def generar(carpeta, trazado, salida, fisica=None):
    t = T.construir(carpeta, trazado, fisica)
    sup_ini = os.path.join(carpeta, trazado, "data", "surfaces.ini")
    claves = T.superficies(sup_ini) if os.path.exists(sup_ini) else dict(T.SISTEMA_AC)
    col = T.Colision([os.path.join(carpeta, t["fisica"])] if t["fisica"] else t["piezas"], claves)
    # the racing line, densified to ~0.5 m, in a grid for fast lookup
    tr = t["trazada"]
    dens = []
    for i in range(len(tr)):
        a, b = tr[i], tr[(i + 1) % len(tr)]
        n = max(1, int(math.dist(a, b) / 0.5))
        dens += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n,
                  a[2] + (b[2] - a[2]) * k / n) for k in range(n)]
    rej = defaultdict(list)
    for p in dens:
        rej[(int(p[0] // 8), int(p[2] // 8))].append(p)

    def cerca(x, z):
        mejor, y = 1e9, None
        for dx in (-2, -1, 0, 1, 2):
            for dz in (-2, -1, 0, 1, 2):
                for p in rej.get((int(x // 8) + dx, int(z // 8) + dz), ()):
                    d = math.hypot(p[0] - x, p[2] - z)
                    if d < mejor:
                        mejor, y = d, p[1]
        return mejor, y

    # the bounding box: that of all the asphalt in the collision mesh
    xs, zs = [], []
    for tris in col.suelo.values():
        for sup, a, b, c in tris:
            if sup in ASFALTO:
                xs += [a[0], b[0], c[0]]
                zs += [a[2], b[2], c[2]]
    x0, x1, z0, z1 = min(xs) - 2, max(xs) + 2, min(zs) - 2, max(zs) + 2
    ancho, alto = int((x1 - x0) / CELDA) + 1, int((z1 - z0) / CELDA) + 1
    celdas, cuenta = [], defaultdict(int)
    ultimo_y = tr[0][1]
    for gy in range(alto):
        z = z0 + gy * CELDA
        for gx in range(ancho):
            x = x0 + gx * CELDA
            d, y = cerca(x, z)
            h = col.debajo(x, z, y if y is not None else ultimo_y)
            if not h or h[0] not in ASFALTO:
                continue
            fl = 3 if d < FRANJA_GOMA_M else 2
            fr = min(255, int(round(d * POR_METRO)))
            celdas.append((gx, gy, fr, 0, 0, fl))
            cuenta[fl] += 1
    _escribir(salida, x0, z0, x0 + (ancho - 1) * CELDA, z0 + (alto - 1) * CELDA,
              ancho, alto, CELDA, celdas)
    return {"rejilla": (ancho, alto), "celdas": len(celdas), "goma": cuenta[3],
            "asfalto": cuenta[2], "limites": (round(x0), round(z0), round(x1), round(z1))}


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    fis = sys.argv[sys.argv.index("--fisica") + 1] if "--fisica" in sys.argv else None
    print(generar(sys.argv[1], sys.argv[2], sys.argv[3], fis))
