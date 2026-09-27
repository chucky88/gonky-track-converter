"""Zip credits, options table, paths and report: what can be tested without Blender or the game."""
import os as _os
import sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, "converter"))
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import zipfile  # noqa: E402

import creditos as CR  # noqa: E402
import informe as INF  # noqa: E402
import opciones as OP  # noqa: E402
from version import VERSION  # noqa: E402


def _zip(ruta, nombre):
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr(f"Automobilista 2/Tracks/{nombre}/{nombre}.trd",
                   '<prop name="Track Group" data="x" />\n<prop name="Track_Variation" data="x" />\n'
                   '<prop name="Order Override" data="0" />\n')


class TestCreditos(unittest.TestCase):
    def test_texto(self):
        t = CR.texto("Mi Circuito", {"author": "Fulano", "version": "1.2", "url": "https://x"})
        for trozo in ("Mi Circuito", "Fulano v1.2", "https://x", f"Gonky Track Converter v{VERSION}",
                      "using", "its original author"):
            self.assertIn(trozo, t)
        self.assertNotIn("by GonkyRacing", t)      # the credit is the TOOL's, not the converter's

    def test_va_en_la_raiz_del_zip_y_se_sustituye(self):
        with tempfile.TemporaryDirectory() as d:
            z = _os.path.join(d, "m.zip")
            _zip(z, "m")
            CR.poner(z, "uno")
            CR.poner(z, "dos")
            nombres = zipfile.ZipFile(z).namelist()
            self.assertEqual(nombres.count(CR.NOMBRE), 1)
            self.assertIn(CR.NOMBRE, nombres)                     # root: outside "Automobilista 2/"
            self.assertEqual(CR.leer(z), "dos")

    def test_unir_trazados_junta_los_creditos(self):
        with tempfile.TemporaryDirectory() as d:
            a, b, out = (_os.path.join(d, x) for x in ("a.zip", "b.zip", "out.zip"))
            _zip(a, "a")
            _zip(b, "b")
            CR.poner(a, "credits A")
            CR.poner(b, "credits B")
            r = subprocess.run([_sys.executable, _os.path.join(_RAIZ, "join_layouts.py"), out, "--group", "G",
                                f"{a}:a:A:1", f"{b}:b:B:2"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            c = CR.leer(out)
            self.assertIn("credits A", c)
            self.assertIn("credits B", c)
            self.assertEqual(zipfile.ZipFile(out).namelist().count(CR.NOMBRE), 1)

    def test_leer_ui_con_bom_y_json_roto(self):
        with tempfile.TemporaryDirectory() as d:
            p = _os.path.join(d, "ui.json")
            open(p, "w", encoding="utf-8-sig").write('{"name": "N", "author": "A", "version": "1",}')
            self.assertEqual(CR.leer_ui(p)["author"], "A")


class TestOpciones(unittest.TestCase):
    def test_errata_y_retirada_se_detectan(self):
        argv = ["x", "--carpeta", "/a", "--plano-rea", "--publicidad-gonky", "M"]
        self.assertEqual(OP.desconocidas(OP.normalizar(argv)), ["--plano-rea", "--publicidad-gonky"])

    def test_los_valores_no_cuentan_como_opciones(self):
        self.assertEqual(OP.desconocidas(["x", "--geo", "-3.5,40.1,620,1", "--titulo", "-X-"]), [])

    def test_alias_en_ingles(self):
        self.assertEqual(OP.normalizar(["x", "--folder", "a", "--oval", "--no-credits"]),
                         ["x", "--carpeta", "a", "--ovalo", "--sin-creditos"])

    def test_la_ayuda_lista_todas(self):
        ayuda = OP.ayuda()
        for es, en, *_ in OP.OPCIONES:
            self.assertIn(es, ayuda)
            self.assertIn(en, ayuda)

    def test_alias_unicos(self):
        todos = [es for es, *_ in OP.OPCIONES] + [en for _es, en, *_ in OP.OPCIONES if en != _es]
        self.assertEqual(len(todos), len(set(todos)))


class TestRutas(unittest.TestCase):
    def test_la_variable_de_entorno_manda(self):
        r = subprocess.run([_sys.executable, "-c", "import rutas; print(rutas.TRABAJO)"],
                           cwd=_os.path.join(_RAIZ, "converter"), capture_output=True, text=True,
                           env=dict(_os.environ, AMS2TC_TRABAJO="/ruta/de/prueba"))
        self.assertEqual(r.stdout.strip(), "/ruta/de/prueba")

    def test_en_windows_nunca_el_convert_del_sistema(self):
        import rutas
        if rutas.WINDOWS:
            self.assertEqual(rutas.IM_CONVERT[0].lower().rstrip(".exe"), "magick")


class TestInforme(unittest.TestCase):
    def test_sin_rutas_del_equipo(self):
        with tempfile.TemporaryDirectory() as d:
            argv = ["convertir_ac.py", "--carpeta", "/home/fulano/secreto/mi_circuito", "--foto",
                    "C:\\Users\\fulano\\foto.jpg", "--ovalo", "--familias-cc0", "hierba"]
            r = INF.escribir(_os.path.join(d, "REPORT.md"), {"nombre": "x"}, argv,
                             [("a gate", True, "fine")], d, "t", {"name": "N"}, True)
            texto = open(r, encoding="utf-8").read()
            self.assertNotIn("fulano", texto)
            self.assertIn("--folder mi_circuito", texto)          # English names, as typed
            self.assertIn("--photo foto.jpg", texto)
            self.assertIn("--cc0-families grass", texto)
            self.assertIn("✅ a gate", texto)



class TestPancartas(unittest.TestCase):
    def test_imagenes_relativas_al_json(self):
        """Every step runs inside `converter/`: a relative image must start at the JSON's folder."""
        import json
        import pancartas as PC
        with tempfile.TemporaryDirectory() as d:
            _os.makedirs(_os.path.join(d, "img"))
            open(_os.path.join(d, "img", "a.png"), "wb").close()
            j = _os.path.join(d, "banners.json")
            with open(j, "w", encoding="utf-8") as f:
                json.dump({"grupos": [{"imagenes": ["img/a.png"]}]}, f)
            self.assertEqual(PC.leer(j)["grupos"][0]["imagenes"], [_os.path.join(d, "img", "a.png")])


if __name__ == "__main__":
    unittest.main()
