"""A `.bmt` writer that matches Reiza's own files, used instead of OMTT's `TrackPacker/mtx2bmt.py`.

    python3 bmt_fix.py <material.mtx> [<out.bmt>]

🔴 Why. Packed on their own, the `.bmt` that OMTT writes draw NOTHING — the track is invisible,
cars floating in black — and only the loose `.mtx` that TrackPacker also ships hide it. Compared
with Reiza's `.bmt` (and those of a working fully packed track) they differ in the layout, not in
the values:
  - each element points at its first CHILD's attributes instead of its own (`attr_start` is taken
    before the children are processed): `<material>` loses its name and its shader;
  - elements are stored pre-order; Reiza stores them post-order (children before their parent);
  - the chains that link elements/attributes with the same path (`next_same`) are left empty;
  - the name index (`COLL`) holds tag names with a count; Reiza's holds PATHS
    (`material/shaderparam`, `material/shaderparam/@name`) with the first index and a 0/1 kind,
    sorted by signed hash;
  - the header's 5th and 7th fields are the string count and the root index, not the byte size and 0;
  - a single number already stored for the same attribute path is reused; booleans are stored in
    32-bit words.
  - the root attribute is `version`; OMTT's `.mtx` say `VERSION` (a different hash).
This writer reproduces 338 of 362 of an official track's `.bmt` byte for byte from their decoded XML,
and the other 24 with the same structure and values (they only share number slots differently).
OMTT itself is not modified: `empaquetar.py --bmt-only` swaps its converter while packing.
"""
import os
import struct
import sys
import xml.etree.ElementTree as ET

BLMY, HEAD, ELMT, ATTR, COLL, NUMB, BOOL, STRS = (0x594D4C42, 0x44414548, 0x544D4C45, 0x52545441,
                                                  0x4C4C4F43, 0x424D554E, 0x4C4F4F42, 0x53525453)
T_FLOAT, T_BOOL, T_STRING = 0, 1, 2


def hash_string(s):
    """Same hash as OMTT's `mtx2bmt.hash_string` (checked against Reiza's files)."""
    sys.path.insert(0, _trackpacker())
    from mtx2bmt import hash_string as h
    return h(s)


def _trackpacker():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "omtt", "TrackPacker")


def _i32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def construir(raiz: ET.Element, h=None) -> bytes:
    h = h or hash_string
    elementos, atributos, numeros, booleanos = [], [], [], []
    cadenas, offs = bytearray(), {}

    def cadena(s):
        if s not in offs:
            offs[s] = len(cadenas)
            b = s.encode("utf-8") + b"\0"
            cadenas.extend(b + b"\0" * ((4 - len(b) % 4) % 4))
        return offs[s]

    vistos = {}                           # (attribute path, float32) → index, for single numbers

    def valor(raw, ruta_attr):
        if raw.lower() in ("true", "false"):
            booleanos.append(raw.lower() == "true")
            return T_BOOL, len(booleanos) - 1, 1
        try:
            fl = [float(x) for x in raw.split()]
        except ValueError:
            return T_STRING, cadena(raw), 1
        if not fl:
            return T_STRING, cadena(raw), 1
        if len(fl) == 1:                  # a single number reuses an equal one OF THE SAME PATH
            clave = (ruta_attr, struct.pack("<f", fl[0]))
            if clave in vistos:
                return T_FLOAT, vistos[clave], 1
            vistos[clave] = len(numeros)
        inicio = len(numeros)
        numeros.extend(fl)
        return T_FLOAT, inicio, len(fl)

    def visitar(el, ruta):
        ruta = f"{ruta}/{el.tag}" if ruta else el.tag
        hijos = [visitar(c, ruta) for c in el]                     # post-order: children first
        for a, b in zip(hijos, hijos[1:]):
            elementos[a]["sig"] = b
        inicio = len(atributos)
        for nombre, raw in el.attrib.items():
            t, v, n = valor(raw, f"{ruta}/@{nombre}")
            atributos.append({"nombre": h(nombre), "tipo": t, "valor": v, "n": n,
                              "ruta": f"{ruta}/@{nombre}", "mismo": -1})
        elementos.append({"nombre": h(el.tag), "ini": inicio, "nat": len(el.attrib), "nhijos": len(hijos),
                          "hijo": hijos[0] if hijos else -1, "sig": -1, "mismo": -1, "ruta": ruta})
        return len(elementos) - 1

    visitar(raiz, "")
    coll = {}
    for tipo, lista in ((0, elementos), (1, atributos)):
        ultimo = {}
        for i, x in enumerate(lista):
            if x["ruta"] in ultimo:
                lista[ultimo[x["ruta"]]]["mismo"] = i
            else:
                coll[x["ruta"]] = (i, tipo)
            ultimo[x["ruta"]] = i
    indice = sorted(((_i32(h(r)), i, t) for r, (i, t) in coll.items()), key=lambda x: x[0])

    head = struct.pack("<7I", len(elementos), len(atributos), len(indice), len(numeros),
                       len(offs), len(booleanos), len(elementos) - 1)
    elmt = b"".join(struct.pack("<7I", *(v & 0xFFFFFFFF for v in (
        e["nombre"], e["ini"], e["nat"], e["nhijos"], e["hijo"], e["sig"], e["mismo"]))) for e in elementos)
    attr = b"".join(struct.pack("<5I", *(v & 0xFFFFFFFF for v in (
        a["nombre"], a["tipo"], a["valor"], a["n"], a["mismo"]))) for a in atributos)
    coll_b = b"".join(struct.pack("<4i", hh, i, t, -1) for hh, i, t in indice)
    numb = b"".join(struct.pack("<f", n) for n in numeros)
    bits = bytearray(((len(booleanos) + 31) // 32) * 4)      # whole 32-bit words, like Reiza's
    for i, b in enumerate(booleanos):
        if b:
            bits[i // 8] |= 1 << (i % 8)
    bloques = [(HEAD, head), (ELMT, elmt), (ATTR, attr), (COLL, coll_b), (NUMB, numb),
               (BOOL, bytes(bits)), (STRS, bytes(cadenas))]
    pos = 16 + 16 * len(bloques)
    tabla = []
    for bid, d in bloques:
        tabla.append((bid, len(d), pos, 0))
        pos += (len(d) + 3) & ~3
    out = bytearray(struct.pack("<4I", BLMY, len(bloques), pos, 0))
    for fila in tabla:
        out.extend(struct.pack("<4I", *fila))
    for i, (_, d) in enumerate(bloques):
        out.extend(d)
        if i < len(bloques) - 1:
            out.extend(b"\0" * ((4 - len(out) % 4) % 4))
    return bytes(out)


def convertir(mtx, bmt=None, name_suffix=""):
    """Same signature as OMTT's `mtx2bmt.convert`, so it can replace it."""
    raiz = ET.parse(mtx).getroot()
    # OMTT's exporter writes `VERSION`; Reiza's files say `version`, and in a `.bmt` the name is a hash
    if "VERSION" in raiz.attrib and "version" not in raiz.attrib:
        orden = [(("version" if k == "VERSION" else k), v) for k, v in raiz.attrib.items()]
        raiz.attrib.clear()
        raiz.attrib.update(orden)
    if name_suffix:
        raiz.set("name", raiz.get("name", os.path.splitext(os.path.basename(str(mtx)))[0]) + name_suffix)
    destino = bmt or os.path.splitext(str(mtx))[0] + ".bmt"
    with open(destino, "wb") as f:
        f.write(construir(raiz))


if __name__ == "__main__":
    convertir(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
