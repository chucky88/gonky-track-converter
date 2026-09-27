"""The SGX must come out with the SAME shape as the reference tracks."""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "converter"))
import os
import unittest
import xml.etree.ElementTree as ET

import envolver_lod as L

import rutas as _R  # noqa: E402
REF = _os.path.join(_R.OMTT, "referencias", "MidOhio.sgx")   # an official track's sgx: only if you have it

CRUDO = """<?xml version='1.0' encoding='utf-8'?>
<SCENE FileVersion="0.1.0.0" NumObjects="1" NumPartitions="1">
    <OBJ_ID no="1">
        <NODE type="OBJECT" Name="TRACK01" MatrixNumber="-1" instances="1" userflags="1048693">
            <RESOURCE Filename="tracks/charlotte/TRACK01.meb" />
            <SPHERE Centre="1.0 2.0 3.0 1.000000" Radius="9.5" />
            <MATRIX Offset="0.0 0.0 0.0" Orientation="0.0 0.0 0.0 -1.0" Scale="1.000000" />
        </NODE>
    </OBJ_ID>
    <PARTITION_ID no="0">
        <AABBOX min="-1 -1 -1" max="1 1 1" />
        <CHILD_PARTITIONS IDs="NONE" />
        <CHILD_OBJS IDs="1 " />
    </PARTITION_ID>
</SCENE>
"""


class TestEnvolver(unittest.TestCase):
    def setUp(self):
        self.ruta = "/tmp/_test_envolver.sgx"
        open(self.ruta, "w", encoding="utf-8").write(CRUDO)

    def tearDown(self):
        os.path.exists(self.ruta) and os.remove(self.ruta)

    def _raiz(self):
        return ET.parse(self.ruta).getroot()

    def test_el_objeto_queda_dentro_de_un_lod_de_un_nivel(self):
        L.envolver(self.ruta)
        nodo = self._raiz().find("OBJ_ID/NODE")
        self.assertEqual(nodo.get("type"), "LOD")
        self.assertEqual(nodo.get("subobjects"), "1")
        self.assertEqual(nodo.get("MatrixNumber"), "-1")
        hijos = nodo.findall("NODE")
        self.assertEqual(len(hijos), 1)
        self.assertEqual(hijos[0].get("type"), "OBJECT")
        # the child inherits the parent's matrix: MatrixNumber 0 and NO <MATRIX> of its own
        self.assertEqual(hijos[0].get("MatrixNumber"), "0")
        self.assertIsNone(hijos[0].find("MATRIX"))

    def test_la_esfera_va_en_los_dos_y_la_matriz_solo_en_el_lod(self):
        L.envolver(self.ruta)
        nodo = self._raiz().find("OBJ_ID/NODE")
        self.assertIsNotNone(nodo.find("SPHERE"))
        self.assertIsNotNone(nodo.find("MATRIX"))
        self.assertIsNotNone(nodo.find("NODE/SPHERE"))
        self.assertEqual(nodo.find("SPHERE").get("Radius"), "9.5")

    def test_no_se_pierde_el_recurso_ni_los_userflags(self):
        L.envolver(self.ruta)
        hijo = self._raiz().find("OBJ_ID/NODE/NODE")
        self.assertEqual(hijo.find("RESOURCE").get("Filename"), "tracks/charlotte/TRACK01.meb")
        self.assertEqual(hijo.get("userflags"), "1048693")

    def test_child_objs_antes_que_child_partitions(self):
        L.envolver(self.ruta)
        part = list(self._raiz().find("PARTITION_ID"))
        self.assertLess([e.tag for e in part].index("CHILD_OBJS"),
                        [e.tag for e in part].index("CHILD_PARTITIONS"))

    def test_es_idempotente(self):
        L.envolver(self.ruta)
        r = L.envolver(self.ruta)
        self.assertEqual(r["envueltos"], 0)
        self.assertEqual(r["ya_estaban"], 1)

    @unittest.skipUnless(os.path.exists(REF), "needs the reference SGX")
    def test_la_forma_es_la_de_mid_ohio(self):
        """The test that matters: the same skeleton as a track that DOES work."""
        L.envolver(self.ruta)
        mio = self._raiz().find("OBJ_ID/NODE")
        suyo = ET.parse(REF).getroot().find("OBJ_ID/NODE")
        self.assertEqual([e.tag for e in mio], [e.tag for e in suyo])
        self.assertEqual(sorted(mio.attrib), sorted(suyo.attrib))
        self.assertEqual(mio.find("CONTROL").get("Distances"), suyo.find("CONTROL").get("Distances"))
        self.assertEqual(sorted(mio.find("NODE").attrib), sorted(suyo.find("NODE").attrib))


if __name__ == "__main__":
    unittest.main()
