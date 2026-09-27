"""Gonky Track Converter · Converts one Assetto Corsa layout to Automobilista 2. Help: python3 convert_ac.py --help

Launcher: the code is in `converter/convertir_ac.py`.
"""
import os
import runpy
import sys

CONVERTER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "converter")
sys.path.insert(0, CONVERTER)
runpy.run_path(os.path.join(CONVERTER, "convertir_ac.py"), run_name="__main__")
