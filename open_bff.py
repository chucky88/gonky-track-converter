"""Gonky Track Converter · Unpacks an AMS2 .bff with PCarsTools.

Launcher: the code is in `converter/abrir_bff.py`.
"""
import os
import runpy
import sys

CONVERTER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "converter")
sys.path.insert(0, CONVERTER)
runpy.run_path(os.path.join(CONVERTER, "abrir_bff.py"), run_name="__main__")
