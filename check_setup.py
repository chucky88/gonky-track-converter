"""Gonky Track Converter · Checks that everything needed is installed, and says how to fix what is missing.

Launcher: the code is in `converter/comprobar_entorno.py`.
"""
import os
import runpy
import sys

CONVERTER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "converter")
sys.path.insert(0, CONVERTER)
runpy.run_path(os.path.join(CONVERTER, "comprobar_entorno.py"), run_name="__main__")
