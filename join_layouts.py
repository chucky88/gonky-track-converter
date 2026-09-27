"""Gonky Track Converter · Joins several converted layouts into one mod (group, variant and order).

Launcher: the code is in `converter/unir_trazados.py`.
"""
import os
import runpy
import sys

CONVERTER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "converter")
sys.path.insert(0, CONVERTER)
runpy.run_path(os.path.join(CONVERTER, "unir_trazados.py"), run_name="__main__")
