"""Which loose files a package keeps: only what is NOT already inside its paks (plus `.mtx`/`.trd`)."""
import io
import os as _os
import struct
import sys as _sys
import tempfile
import unittest
import zipfile
import zlib

_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, "converter"))
import bff_read as B  # noqa: E402
import empaquetar as E  # noqa: E402


def _bff(ficheros):
    """A minimal pak with the layout `bff_read` reads: {name with backslashes: bytes}."""
    n = len(ficheros)
    toc_size = n * 0x2A
    base = 0x130 + toc_size
    tabla = base + 0x308
    nombres_pos = tabla + n * 0x10
    nombres = b""
    offs = []
    for nombre in ficheros:
        offs.append(nombres_pos + len(nombres))
        b = nombre.encode("ascii")
        nombres += bytes([len(b)]) + b
    datos_pos = nombres_pos + len(nombres)
    toc, datos = b"", b""
    for i, contenido in enumerate(ficheros.values()):
        c = zlib.compress(contenido)
        entrada = struct.pack("<QQII", i, datos_pos + len(datos), len(c), len(contenido))
        entrada += b"\0" * (32 - len(entrada)) + bytes([1])             # byte 32: 1 = zlib
        entrada += b"\0" * (0x2A - len(entrada))
        toc += entrada
        datos += c
    cab = bytearray(0x130)
    struct.pack_into("<I", cab, 8, n)
    struct.pack_into("<I", cab, 0x118, toc_size)
    ext = b"\0" * 0x308 + b"".join(struct.pack("<QQ", o, 0) for o in offs)
    return bytes(cab) + toc + ext + nombres + datos


class TestBff(unittest.TestCase):
    def test_lee_nombres_y_contenido(self):
        pak = _bff({"tracks\\t\\a.dds": b"AAA", "tracks\\t\\b.xml": b"<b/>"})
        dentro = B.contenido(io.BytesIO(pak))
        self.assertEqual(set(dentro), {"tracks/t/a.dds", "tracks/t/b.xml"})
        import hashlib
        self.assertEqual(dentro["tracks/t/a.dds"], hashlib.md5(b"AAA").hexdigest())   # decompressed

    def test_un_pak_que_no_entiende_lista_vacio(self):
        self.assertEqual(B.contenido(io.BytesIO(b"\0" * 64)), {})


class TestSueltos(unittest.TestCase):
    def _zip(self, d, pak, sueltos):
        z = _os.path.join(d, "t.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("Automobilista 2/Pakfiles/Tracks/t.bff", _bff(pak))
            for rel, contenido in sueltos.items():
                f.writestr(f"Automobilista 2/{rel}", contenido)
        return z

    def test_quita_solo_lo_que_esta_dentro_y_es_igual(self):
        pak = {"tracks\\textures\\t\\a.dds": b"A", "tracks\\t\\physics\\t.csm": b"CSM",
               "tracks\\t\\m.mtx": b"MTX", "tracks\\textures\\t\\c.dds": b"OTHER"}
        sueltos = {"Tracks/textures/t/a.dds": b"A", "Tracks/t/physics/t.csm": b"CSM",
                   "Tracks/t/m.mtx": b"MTX", "Tracks/t/t.trd": b"TRD",
                   "Tracks/textures/t/c.dds": b"CHANGED",          # same name, different content
                   "Tracks/_data/tracklights/t.xml": b"<l/>"}       # TrackPacker leaves it out
        with tempfile.TemporaryDirectory() as d:
            z = self._zip(d, pak, sueltos)
            fuera, huerfanos = E.limpiar_sueltos(z, "t")
            quedan = {n for n in zipfile.ZipFile(z).namelist()}
        self.assertEqual(sorted(x.split("/")[-1] for x in fuera), ["a.dds", "t.csm"])
        self.assertEqual([x.split("/")[-1] for x in huerfanos], ["c.dds"])   # never dropped on the name
        for rel in ("Tracks/t/m.mtx", "Tracks/t/t.trd", "Tracks/_data/tracklights/t.xml",
                    "Tracks/textures/t/c.dds"):
            self.assertIn(f"Automobilista 2/{rel}", quedan)

    def test_la_puerta_pide_la_fisica_DENTRO_del_pak(self):
        with tempfile.TemporaryDirectory() as d:
            z = self._zip(d, {"tracks\\t\\t.sgx": b"x"},
                          {f"{r}": b"x" for r in E.fisica("t")})     # physics only loose
            E.limpiar_sueltos(z, "t")
            ok, detalle = E.comprobar(z, "t")
        self.assertFalse(ok)
        self.assertIn("not inside any pak", detalle)

    def test_la_puerta_en_verde_como_la_referencia(self):
        pak = {r.replace("/", "\\").lower(): b"x" for r in E.fisica("t")}
        with tempfile.TemporaryDirectory() as d:
            z = self._zip(d, pak, {"Tracks/t/t.trd": b"TRD", "Tracks/t/m.mtx": b"MTX"})
            ok, detalle = E.comprobar(z, "t")
        self.assertTrue(ok, detalle)


    def test_solo_bmt_quita_el_mtx_suelto_si_el_pak_trae_su_bmt(self):
        pak = {"tracks\\t\\a.bmt": b"BMT"}
        with tempfile.TemporaryDirectory() as d:
            z = self._zip(d, pak, {"Tracks/t/a.mtx": b"MTX", "Tracks/t/b.mtx": b"MTX", "Tracks/t/t.trd": b"T"})
            fuera, _ = E.limpiar_sueltos(z, "t", solo_bmt=True)
            quedan = set(zipfile.ZipFile(z).namelist())
        self.assertEqual([x.split("/")[-1] for x in fuera], ["a.mtx"])
        self.assertIn("Automobilista 2/Tracks/t/b.mtx", quedan)       # no .bmt for it: it stays

    def test_solo_bmt_la_puerta_rechaza_cualquier_mtx(self):
        pak = {r.replace("/", "\\").lower(): b"x" for r in E.fisica("t")}
        for extra in ({"tracks\\t\\a.mtx": b"M"}, {"tracks\\t\\a.mtx.aparte": b"M"}):
            with tempfile.TemporaryDirectory() as d:
                z = self._zip(d, {**pak, **extra}, {"Tracks/t/t.trd": b"T"})
                self.assertFalse(E.comprobar(z, "t", solo_bmt=True)[0], extra)
        with tempfile.TemporaryDirectory() as d:
            z = self._zip(d, {**pak, "tracks\\t\\a.bmt": b"B"}, {"Tracks/t/t.trd": b"T"})
            self.assertTrue(E.comprobar(z, "t", solo_bmt=True)[0])


if __name__ == "__main__":
    unittest.main()
