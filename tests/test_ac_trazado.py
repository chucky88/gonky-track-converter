"""Tests for `ac_trazado` that need no track on disk."""

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "converter"))
import os
import sys
import unittest
from collections import defaultdict

import ac_trazado as T  # noqa: E402


def _colision(triangulos):
    col = T.Colision.__new__(T.Colision)
    col.suelo, col.muros, col.cuenta = defaultdict(list), defaultdict(list), defaultdict(int)
    for t in triangulos:
        T._indexar(col.muros, ("WALL",) + t)
    return col


class TestMuroEnEsquinaDeCelda(unittest.TestCase):
    """The case measured at Charlotte: the ray cuts diagonally across the corner of the cell where the
    wall is, at 2.49 m. With samples every 3 m that cell was never looked at."""

    def test_muro_en_la_celda_que_el_rayo_roza(self):
        # ray from (5.0, 5.3) at 45°: it enters cell (0, 1) at s=0.99 m and leaves at
        # s=1.41 m. The old samples (s=0 and s=3) fell in (0, 0) and (1, 1).
        d = (0.70710678, 0.0, 0.70710678)
        o = (5.0, 0.5, 5.3)
        # vertical wall perpendicular to the ray, entirely inside cell (0, 1), at s≈1.2
        a, b = (5.78, -1.0, 6.22), (5.92, -1.0, 6.08)
        a2, b2 = (5.78, 3.0, 6.22), (5.92, 3.0, 6.08)
        col = _colision([(a, b, a2), (b, b2, a2)])
        self.assertEqual(set(col.muros), {(0, 1)})
        dist = col.muro(o, d, maxd=10)
        self.assertIsNotNone(dist)
        self.assertAlmostEqual(dist, 1.2, delta=0.1)

    def test_sin_muro_sigue_siendo_none(self):
        col = _colision([((50, -1, 50), (50, 3, 50), (51, -1, 51))])
        self.assertIsNone(col.muro((0, 0.5, 0), (1, 0, 0), maxd=20))


if __name__ == "__main__":
    unittest.main()
