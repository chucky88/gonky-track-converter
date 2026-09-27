"""Lists (and reads) what is INSIDE an AMS2 `.bff` pak, without the game or PCarsTools.

    python3 bff_read.py <file.bff>

Enough of the format to answer «is this file already in the pak, and is it the same?», which is
what `empaquetar.py` needs before dropping a loose copy. Entries are zlib-compressed or stored.
Only tested on the paks TrackPacker writes (and on the ones of working track mods); the tiny
placeholder paks (`AUT_…`, a few KB) have no entries this reader understands, so they list empty.
"""
import hashlib
import struct
import sys
import zlib


def listar(fh):
    """[{name, pos, cs, us, ct}] of every entry. `name` as stored (backslashes, usually lowercase)."""
    fh.seek(0)
    h = fh.read(0x130)
    n = struct.unpack_from("<I", h, 8)[0]
    toc_size = struct.unpack_from("<I", h, 0x118)[0]
    toc = fh.read(toc_size)
    fh.seek(0x130 + toc_size)
    ext = fh.read(0x308 + n * 0x10 + n * 260)
    base = 0x130 + toc_size + 0x308
    ents = []
    for i in range(n):
        o = i * 0x2A
        _uid, pos = struct.unpack_from("<QQ", toc, o)
        cs, us = struct.unpack_from("<II", toc, o + 16)
        no = struct.unpack_from("<Q", ext, 0x308 + i * 0x10)[0] - base
        largo = ext[0x308 + no]
        nombre = ext[0x308 + no + 1:0x308 + no + 1 + largo].decode("ascii", "replace")
        ents.append({"name": nombre, "pos": pos, "cs": cs, "us": us, "ct": toc[o + 32]})
    return ents


def leer(fh, e):
    fh.seek(e["pos"])
    d = fh.read(e["cs"])
    return zlib.decompress(d) if e["ct"] == 1 else d


def contenido(fh):
    """{relative path in lowercase with `/`: md5 of its content}. Empty if the pak can't be read."""
    try:
        return {e["name"].replace("\\", "/").lower(): hashlib.md5(leer(fh, e)).hexdigest()
                for e in listar(fh)}
    except (struct.error, IndexError, ValueError, zlib.error, OverflowError):
        return {}


if __name__ == "__main__":
    with open(sys.argv[1], "rb") as f:
        for ent in listar(f):
            print(f"{ent['us']:>10}  {ent['name']}")
