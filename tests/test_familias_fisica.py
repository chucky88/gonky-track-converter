"""The physics prefixes must exist in the game's master table.

🔴 It exists because the walls went to `BUMPYROADS2` — index 3, "CONC", DRIVABLE concrete — and
**you drove through them**. The name was picked by resemblance and never checked against the table,
which is documented in `OMTT Docs/Formats/CSM.md`.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "converter"))
import re
import unittest

import familias as F

import rutas as _R  # noqa: E402
DOC = _os.path.join(_R.OMTT, "OMTT Docs", "Formats", "CSM.md")


def tabla_del_juego():
    """The valid names, read from the format documentation, not copied by hand."""
    nombres = set()
    for linea in open(DOC, encoding="utf-8"):
        m = re.match(r"\s*(?:\d+\.|-)\s+([A-Z][A-Z0-9_ ]+)\s*$", linea)
        if m:
            nombres.add(m.group(1).strip())
    return nombres


@unittest.skipUnless(_os.path.exists(DOC), "needs the OMTT docs (git submodule update --init)")
class TestPrefijosDeFisica(unittest.TestCase):
    def test_todos_los_prefijos_existen_en_la_tabla(self):
        validos = tabla_del_juego()
        self.assertIn("ROADS", validos, "could not read the table in the document")
        for fam, _patrones, _shader, fisica, _don in F.FAMILIAS:
            self.assertIn(fisica, validos, f"«{fisica}» ({fam}) is not in the game's table")
        self.assertIn(F.SIN_CLASIFICAR[2], validos)

    def test_los_muros_no_son_superficie_conducible(self):
        """The test of the real failure: a wall cannot end up as a road-surface material."""
        CONDUCIBLES = {"ROADS", "ROAD", "BUMPYROADS1", "BUMPYROADS2", "BUMPYROADS3",
                       "LOWGRIPROADS", "RUNOFFROAD", "PAVEMENT", "DIRT_ROAD", "SAND_ROAD"}
        for nombre in ("WALL_TURN_1_Y", "CMWL01_Y", "INWL01", "TOPWALL_Y", "FENCENEW", "FENCETOP"):
            fisica = F.familia_de(nombre)[2]
            self.assertNotIn(fisica, CONDUCIBLES,
                             f"{nombre} -> {fisica}: the car would drive through it")

    def test_el_asfalto_sigue_siendo_asfalto(self):
        for nombre in ("ROAD01", "RDHI", "APRONA", "PITROADA", "ROADLINES01"):
            self.assertEqual(F.familia_de(nombre)[2], "ROADS", nombre)


if __name__ == "__main__":
    unittest.main()
