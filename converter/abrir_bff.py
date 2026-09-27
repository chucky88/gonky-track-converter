"""Opens (unpacks) an AMS2 `.bff` with Nenkai's PCarsTools.

    python3 open_bff.py <file.bff> [--game <AMS2 folder>]

It leaves the contents in `<bff folder>/<name>_extracted/`. It is useful for two things:

- **comparing with the official tracks**: how Reiza handles a material, the lights, the AIW, the
  TRD… Everything the tool copies "from Daytona" was measured this way;
- **reviewing your own package**: comparing two versions from the inside (`.bff` files change on
  every build even when their content is the same; what counts is what is inside).

The game folder is needed because PCarsTools uses `oo2core_4_win64.dll` (Oodle), which ships with
AMS2 and cannot be redistributed. By default, `game` from `settings.ini` (or `AMS2TC_GAME`).

⚠️ On Linux, under wine, PCarsTools needs the **.NET 6 runtime for Windows** installed in the wine
prefix, and it dies with "Could not load ICU data" unless it is given
`DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` (it always is).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rutas as R  # noqa: E402


def abrir(bff: str, juego: str) -> tuple:
    """(ok, output folder, PCarsTools output)."""
    if not os.path.isfile(os.path.join(juego, "oo2core_4_win64.dll")):
        return False, None, f"oo2core_4_win64.dll missing in {juego} (it must be the AMS2 folder)"
    orden = [R.PCARSTOOLS, "pak", "-i", os.path.abspath(bff), "-g", os.path.abspath(juego)]
    entorno = dict(os.environ, DOTNET_SYSTEM_GLOBALIZATION_INVARIANT="1")
    if not R.WINDOWS:
        orden = ["wine", *orden]
        entorno.update(WINEDEBUG="-all")
        # ⚠️ NOT the cooker's prefix: PCarsTools needs the .NET 6 runtime installed in ITS prefix
        # (by default, wine's default one). A different one: `wine_prefix_pcarstools` in settings.ini.
        if R.WINE_PREFIX_PCT:
            entorno["WINEPREFIX"] = R.WINE_PREFIX_PCT
    r = subprocess.run(orden, capture_output=True, text=True, env=entorno,
                       cwd=os.path.dirname(R.PCARSTOOLS) or None, timeout=3600)
    salida = os.path.splitext(os.path.abspath(bff))[0] + "_extracted"
    ok = r.returncode == 0 and os.path.isdir(salida)
    return ok, salida, (r.stdout or "") + (r.stderr or "")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    argv = ["--juego" if a == "--game" else a for a in argv]   # the Spanish name still works
    juego = argv[argv.index("--juego") + 1] if "--juego" in argv else R.JUEGO
    ok, salida, log = abrir(argv[1], juego)
    if ok:
        n = sum(len(f) for _, _, f in os.walk(salida))
        print(f"✅ {n} files in {salida}")
        return 0
    print(f"🔴 couldn't open {argv[1]}:\n{log.strip()[-800:]}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
