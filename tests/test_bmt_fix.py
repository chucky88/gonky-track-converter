"""The `.bmt` layout of Reiza's own files (see converter/bmt_fix.py), on a synthetic material."""
import os as _os
import struct
import sys as _sys
import unittest
import xml.etree.ElementTree as ET

_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, "converter"))
import bmt_fix as F  # noqa: E402

MTX = """<material VERSION="v1.0.0.1" name="WALL" shader="Render\\Shaders\\rz_basic.fx" technique="rz_basic" antialias="1">
  <shaderparam name="detailTilingX" type="EPT_F32"><value v="8.0" /></shaderparam>
  <shaderparam name="detailTilingY" type="EPT_F32"><value v="8.0" /></shaderparam>
  <shaderparam name="diffuse1Texture" type="EPT_TEXTURE"><type t="ET_STANDARD" /><value v="tracks\\textures\\t\\wall.dds" /></shaderparam>
  <depthparams><enabled e="true" /><writeenabled w="true" /></depthparams>
  <alphablendparams><enabled e="false" /></alphablendparams>
</material>"""


def _tablas(b):
    _, nb, _, _ = struct.unpack_from("<4I", b, 0)
    bl = {}
    for i in range(nb):
        bid, ln, off, _ = struct.unpack_from("<4I", b, 16 + 16 * i)
        bl[struct.pack("<I", bid).decode()] = b[off:off + ln]
    el = [struct.unpack_from("<7i", bl["ELMT"], 28 * i) for i in range(len(bl["ELMT"]) // 28)]
    at = [struct.unpack_from("<5i", bl["ATTR"], 20 * i) for i in range(len(bl["ATTR"]) // 20)]
    co = [struct.unpack_from("<4i", bl["COLL"], 16 * i) for i in range(len(bl["COLL"]) // 16)]
    return bl, el, at, co


class TestBmt(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.d = tempfile.mkdtemp()
        with open(_os.path.join(self.d, "wall.mtx"), "w") as f:
            f.write(MTX)
        F.convertir(_os.path.join(self.d, "wall.mtx"))
        with open(_os.path.join(self.d, "wall.bmt"), "rb") as f:
            self.bl, self.el, self.at, self.co = _tablas(f.read())

    def _h(self, s):
        return F.hash_string(s) & 0xFFFFFFFF

    def test_la_raiz_es_la_ultima_y_apunta_a_SUS_atributos(self):
        raiz = self.el[-1]
        self.assertEqual(raiz[0] & 0xFFFFFFFF, self._h("material"))
        suyos = [self.at[i][0] & 0xFFFFFFFF for i in range(raiz[1], raiz[1] + raiz[2])]
        self.assertEqual(suyos, [self._h(n) for n in ("version", "name", "shader", "technique", "antialias")])

    def test_post_orden_los_hijos_antes_que_el_padre(self):
        for i, e in enumerate(self.el):
            if e[4] != -1:
                self.assertLess(e[4], i)

    def test_indice_de_rutas_ordenado_y_con_tipo(self):
        claves = {c[0] & 0xFFFFFFFF: c[2] for c in self.co}
        self.assertEqual(claves[self._h("material/shaderparam/@name")], 1)
        self.assertEqual(claves[self._h("material/depthparams/enabled")], 0)
        self.assertEqual([c[0] for c in self.co], sorted(c[0] for c in self.co))

    def test_cadena_de_la_misma_ruta(self):
        sp = [i for i, e in enumerate(self.el) if e[0] & 0xFFFFFFFF == self._h("shaderparam")]
        self.assertEqual([self.el[i][6] for i in sp], sp[1:] + [-1])

    def test_numero_repetido_de_la_misma_ruta_se_comparte(self):
        self.assertEqual(struct.unpack_from("<I", self.bl["HEAD"], 12)[0], 2)   # 8.0 (×2) and 1 (antialias)


if __name__ == "__main__":
    unittest.main()
