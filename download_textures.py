"""Gonky Track Converter · Downloads the CC0 filler textures from ambientCG and prepares them.

Launcher: the code is in `converter/descargar_texturas.py`.
"""
import os
import runpy
import sys

CONVERTER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "converter")
sys.path.insert(0, CONVERTER)
runpy.run_path(os.path.join(CONVERTER, "descargar_texturas.py"), run_name="__main__")
