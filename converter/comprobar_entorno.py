"""Is everything ready to convert? Checks each requirement and says what is missing and how to fix it.

    python3 check_setup.py

✅ fine · ⚠️ optional or could be better · 🔴 essential and broken (exits with code 1).
It checks the paths resolved by `rutas.py` (settings.ini / AMS2TC_* / default values).
"""
import importlib
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rutas as R  # noqa: E402
from version import VERSION  # noqa: E402

TEXTURAS = ["asfalto_diffuse", "asfalto_normal", "hierba_diffuse", "hierba_normal", "hierba_detalle",
            "hormigon_diffuse", "hormigon_normal", "hormigon_detalle", "grava_diffuse", "grava_normal",
            "grava_detalle", "muros_normal"]
DISCO_MIN_GB = 3.0
rojos = []


def linea(estado, que, detalle="", arreglo=""):
    icono = {"ok": "✅", "aviso": "⚠️ ", "mal": "🔴"}[estado]
    print(f"{icono} {que}" + (f": {detalle}" if detalle else ""))
    if arreglo and estado != "ok":
        print(f"      → {arreglo}")
    if estado == "mal":
        rojos.append(que)


def correr(cmd, timeout=120, env=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def main():
    print(f"Gonky Track Converter v{VERSION} — setup check ({sys.platform})\n")

    # Python
    v = sys.version_info
    linea("ok" if v >= (3, 11) else "mal", "Python", f"{v.major}.{v.minor}.{v.micro}",
          "install Python 3.11 or later")
    for mod, pip in (("numpy", "numpy"), ("PIL", "pillow")):
        try:
            importlib.import_module(mod)
            linea("ok", f"module {pip}")
        except ImportError:
            linea("mal", f"module {pip}", "not installed", f"pip install {pip}")

    # ImageMagick
    rc, out = correr([*R.IM_CONVERT, "-version"])
    ver = out.splitlines()[0] if out else ""
    if rc == 0 and "ImageMagick" in ver:
        rc2, fmt = correr([*R.IM_MAGICK, "-list", "format"])
        linea("ok" if " DDS" in fmt else "mal", "ImageMagick", ver.replace("Version: ", "")[:60],
              "your ImageMagick can't write DDS: install the full version from imagemagick.org")
    else:
        linea("mal", "ImageMagick", "not found",
              "install ImageMagick (imagemagick.org) or set its path in settings.ini (im_magick)")

    # Blender + TrackCompiler
    rc, out = correr([R.BLENDER, "-b", "--factory-startup", "--python-expr",
                      "import bpy, sys; bpy.ops.preferences.addon_enable(module='trackcompiler'); "
                      "import trackcompiler; print('TC_OK', bpy.app.version_string)"], timeout=240)
    if rc == -1:
        linea("mal", "Blender", "not found", "install Blender 4.3 or set its path in settings.ini (blender)")
    elif "TC_OK" in out:
        ver = out.split("TC_OK", 1)[1].split()[0]
        linea("ok" if ver.startswith("4.3") else "aviso", "Blender + TrackCompiler", f"Blender {ver}",
              "the tool was tested with Blender 4.3; another version may fail")
    else:
        linea("mal", "TrackCompiler in Blender", "Blender starts but doesn't load the add-on",
              "install trackcompiler-*.zip from the OMTT releases in Blender (Preferences → Add-ons)")

    # OMTT
    linea("ok" if os.path.isdir(R.OMTT) else "mal", "Open Madness Track Tools", R.OMTT,
          "git submodule update --init  (or set «omtt» in settings.ini)")
    linea("ok" if os.path.isfile(R.PACKER) else "mal", "TrackPacker", R.PACKER,
          "it comes with OMTT: check the OMTT folder")
    ejemplo_ok = os.path.isdir(os.path.join(R.EJEMPLO, "Automobilista 2"))
    linea("ok" if ejemplo_ok else "mal", "Example Project", R.EJEMPLO,
          "unzip ExampleProject.zip (OMTT releases) into omtt/example/")
    if os.path.isfile(R.COCINERO):
        faltan = [d for d in ("PhysX3_x64.dll", "PhysX3Common_x64.dll", "PhysX3Cooking_x64.dll")
                  if not os.path.isfile(os.path.join(os.path.dirname(R.COCINERO), d))]
        linea("aviso" if faltan else "ok", "PhysicsMeshCooker", R.COCINERO + (f" · missing {faltan}" if faltan else ""),
              "put the PhysX DLLs listed in its README next to the .exe")
    else:
        linea("mal", "PhysicsMeshCooker", "not found", "PhysicsMeshCooker.exe (OMTT releases) into omtt/cooker/")
    if not R.WINDOWS:
        linea("ok" if shutil.which("wine") else "mal", "wine", shutil.which("wine") or "not found",
              "install wine: PhysicsMeshCooker is a Windows program")

    # textures
    faltan = [t for t in TEXTURAS if not os.path.isfile(os.path.join(R.TEXTURAS, t + ".dds"))]
    linea("ok" if not faltan else "mal", "CC0 textures", f"{R.TEXTURAS}" + (f" · {len(faltan)} of 12 missing" if faltan else ""),
          "python3 download_textures.py")

    # work folder and disk
    try:
        os.makedirs(R.TRABAJO, exist_ok=True)
        libre = shutil.disk_usage(R.TRABAJO).free / 2**30
        linea("ok" if libre >= DISCO_MIN_GB else "mal", "work folder", f"{R.TRABAJO} · {libre:.1f} GB free",
              f"at least {DISCO_MIN_GB:.0f} GB is needed: each version of a big track takes 1-2 GB")
    except OSError as e:
        linea("mal", "work folder", f"{R.TRABAJO}: {e}", "set «work» in settings.ini")

    # optional
    linea("ok" if os.path.isfile(R.PCARSTOOLS) else "aviso", "PCarsTools (optional, for open_bff.py)",
          R.PCARSTOOLS if os.path.isfile(R.PCARSTOOLS) else "not found", "its releases, and «pcarstools» in settings.ini")
    linea("ok" if os.path.isfile(os.path.join(R.JUEGO, "oo2core_4_win64.dll")) else "aviso",
          "AMS2 folder (optional, for open_bff.py)", R.JUEGO, "set «game» in settings.ini")

    print()
    if rojos:
        print(f"🔴 {len(rojos)} essential thing(s) missing: {', '.join(rojos)}")
        return 1
    print("✅ Everything ready to convert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
