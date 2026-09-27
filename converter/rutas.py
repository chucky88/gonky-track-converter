"""Where everything lives: ONE single place for paths and external programs.

Why it exists: so the tool works on any machine, no path is hard-coded in the modules. And
ImageMagick cannot be called as plain `convert`: on Windows that is the system tool that converts
DISKS. Everything is resolved here once; the other modules import from here.

Order of precedence for each value:
  1. environment variable `AMS2TC_<KEY>` (e.g. `AMS2TC_OMTT=D:/omtt`);
  2. `settings.ini` at the repo root (section `[paths]`; see `settings.example.ini`);
  3. the default value: GonkyRacing's installation if it exists; otherwise, the folders
     of this repo (submodule `omtt/`, `tools/`).

No `bpy`: it is imported both from Blender and from outside.
"""
import configparser
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
WINDOWS = sys.platform.startswith("win")
# the repo root: this file lives in `<repo>/converter/` (it may be imported through a symlink)
_REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

_ini = configparser.ConfigParser()
_ini.read([os.path.join(_REPO, "settings.ini"), os.path.join(_REPO, "ajustes.ini")], encoding="utf-8")


def _valor(clave: str, defecto: str, *antiguas: str) -> str:
    """Environment variable `AMS2TC_<KEY>`, then `settings.ini` ([paths]), then the default.
    `antiguas`: older (Spanish) key names, still accepted."""
    for k in (clave, *antiguas):
        v = os.environ.get(f"AMS2TC_{k.upper()}")
        if v:
            return v
    for seccion in ("paths", "rutas"):
        for k in (clave, *antiguas):
            if _ini.has_option(seccion, k):
                return _ini.get(seccion, k)
    return defecto


# By default EVERYTHING stays inside the repo; each installation can change it in `settings.ini`.
# Open Madness Track Tools (https://github.com/ohyeah2389/Open-Madness-Track-Tools): the submodule
# `omtt/`, pinned to the tested version (TrackCompiler, TrackPacker, Example Project, cooker).
OMTT = _valor("omtt", os.path.join(_REPO, "omtt"))
EJEMPLO = _valor("example", os.path.join(OMTT, "example", "Example Project"), "ejemplo")
PACKER = _valor("packer", os.path.join(OMTT, "TrackPacker", "pack_track.py"))
COCINERO = _valor("cooker", os.path.join(OMTT, "cooker", "PhysicsMeshCooker.exe"), "cocinero")
# work folder: one subfolder per track (scene, package, logs, report, zip)
TRABAJO = _valor("work", os.path.join(_REPO, "work"), "trabajo")
# CC0 filler textures (`download_textures.py`)
TEXTURAS = _valor("textures", os.path.join(_REPO, "textures"), "texturas")
# wine prefix for the cooker (only outside Windows)
WINE_PREFIX = _valor("wine_prefix", os.path.expanduser("~/.wine-omtt"))
# PCarsTools (https://github.com/Nenkai/PCarsTools, MIT), for `open_bff.py`: the source code is a
# submodule in `tools/PCarsTools`; the executable, from its releases, goes here:
PCARSTOOLS = _valor("pcarstools", os.path.join(_REPO, "tools", "PCarsTools-bin", "PCarsTools.exe"))
WINE_PREFIX_PCT = _valor("wine_prefix_pcarstools", "")   # empty = the default wine prefix
# the AMS2 folder (the one containing `oo2core_4_win64.dll`): only for `open_bff.py`
JUEGO = _valor("game", "", "juego")
# only for custom pipelines that reuse these modules (e.g. GonkyRacing's AMS1 one)
PACK_AMS1 = _valor("pack_ams1", os.path.join(OMTT, "ams1-pack"))


def _imagemagick(herramienta: str) -> list:
    """ImageMagick's `convert`/`identify`. On Windows ALWAYS `magick <herramienta>`: Windows'
    `convert.exe` converts FAT file systems to NTFS."""
    fijado = _valor(f"im_{herramienta}", "")
    if fijado:
        return fijado.split()
    if not WINDOWS and shutil.which(herramienta):
        return [herramienta]
    return ["magick", herramienta]


IM_CONVERT = _imagemagick("convert")
IM_IDENTIFY = _imagemagick("identify")
IM_MAGICK = _valor("im_magick", "magick").split()
BLENDER = _valor("blender", "blender")


def orden_cocinero(*args) -> tuple:
    """(command, environment) to launch the PhysicsMeshCooker (a Windows .exe): directly on Windows and
    through wine on Linux/macOS."""
    if WINDOWS:
        return [COCINERO, *args], dict(os.environ)
    return (["wine", COCINERO, *args],
            dict(os.environ, WINEDEBUG="-all", WINEPREFIX=WINE_PREFIX))
