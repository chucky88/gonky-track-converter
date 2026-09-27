"""`python3 test_familias.py`"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "converter"))
import os, sys, unittest
import familias as F

class T(unittest.TestCase):
    def test_asfalto(self):
        self.assertEqual(F.familia_de("RDHI")[1], "rz_road_main_3diffuse")

    def test_las_lineas_NO_son_asfalto(self):
        """ROADLINES starts with ROAD: if the order breaks, this catches it."""
        self.assertEqual(F.familia_de("ROADLINES05")[0], "líneas")
        # what matters is that it does NOT share a recipe with the asphalt
        self.assertNotEqual(F.familia_de("ROADLINES05")[3], F.familia_de("RDHI")[3])
        self.assertEqual(F.familia_de("ROADLINES05")[3], "PAINTLINE_WHITE.mtx")

    def test_muro(self):
        self.assertEqual(F.familia_de("WALL_TURN_1_Y")[1], "rz_basic")

    def test_hierba_y_su_fisica(self):
        self.assertEqual(F.familia_de("GRASSA")[2], "GRASS")

    def test_grava_tiene_fisica_propia(self):
        self.assertEqual(F.familia_de("GRVL03")[2], "GRAVEL")

    def test_desconocido_cae_en_basic_y_no_revienta(self):
        self.assertEqual(F.familia_de("CHORIZO")[1], "rz_basic")
        self.assertEqual(F.familia_de(None)[1], "rz_basic")

    def test_no_distingue_mayusculas(self):
        self.assertEqual(F.familia_de("grassa")[0], F.familia_de("GRASSA")[0])

    def test_cada_familia_tiene_donante(self):
        for fam, _pat, _sh, _fis, donante in F.FAMILIAS:
            self.assertTrue(donante.endswith(".mtx"), fam)

    def test_el_donante_del_asfalto_existe_en_el_ejemplo(self):
        import os
        import rutas as _R
        base = _os.path.join(_R.EJEMPLO, "Automobilista 2", "Tracks", "Meadowdale")
        if not os.path.isdir(base):
            self.skipTest("needs the Example Project")
        self.assertTrue(os.path.exists(os.path.join(base, F.familia_de("RDHI")[3])))

    def test_ruta_del_shader(self):
        self.assertEqual(F.ruta_shader("rz_basic"), "Render\\Shaders\\rz_basic.fx")

if __name__ == "__main__":
    unittest.main(verbosity=1)
