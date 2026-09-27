"""`CREDITS.txt` at the root of the mod's zip: who made the track and which tool converted it.

The credit goes to the TOOL ("converted USING Gonky Track Converter", not "by" anyone): the person
converting is the user. Nothing visible in the game: the track is the work of its original author,
who gave permission to convert it, not to put advertising on it.

Why at the ROOT of the zip and not inside `Automobilista 2/`: installers (AMS2 Content Manager and
the ones that follow its logic) take as the game root the folder that contains `tracks/`,
`pakfiles/`…; whatever sits outside it is NOT copied into the game. The file travels with the mod
and does not clutter the installation.

On by default; `--no-credits` (`--sin-creditos`) removes it (the GPL does not allow preventing
that, and it is honest to say so).

No `bpy`.
"""
import json
import os
import re
import zipfile

from version import VERSION

NOMBRE = "CREDITS.txt"
HERRAMIENTA = "Gonky Track Converter"
REPO = "https://github.com/Gonky28/gonky-track-converter"
CATALOGO = "https://gonkyracing.com/en/mods/tracks"
PILOT = "https://gonkyracing.com/en/pilot-manager"


def leer_ui(ui_path: str) -> dict:
    """name/author/version/url from AC's `ui_track.json` (with a BOM, or broken JSON: recovered by pattern matching)."""
    try:
        t = open(ui_path, encoding="utf-8-sig", errors="replace").read()
    except OSError:
        return {}
    try:
        d = json.loads(t)
    except ValueError:
        d = {k: (m.group(1) if (m := re.search(r'"' + k + r'"\s*:\s*"([^"]*)"', t)) else None)
             for k in ("name", "author", "version", "url")}
    return {k: (str(d.get(k)).strip() if d.get(k) else "") for k in ("name", "author", "version", "url")}


def texto(titulo: str, ui: dict) -> str:
    autor = ui.get("author") or "(unknown)"
    version = f" v{ui['version']}" if ui.get("version") else ""
    web = f"\n  {ui['url']}" if ui.get("url") else ""
    return (
        f"{titulo}\n"
        f"{'=' * len(titulo)}\n\n"
        f"Original Assetto Corsa track:\n"
        f"  {autor}{version}{web}\n\n"
        f"Converted to Automobilista 2 using:\n"
        f"  {HERRAMIENTA} v{VERSION} — {REPO}\n\n"
        f"More AMS2 tracks:    {CATALOGO}\n"
        f"One-click install:   {PILOT}\n\n"
        f"The track belongs to its original author. Ask for permission before redistributing it.\n"
    )


def poner(zip_path: str, contenido: str) -> None:
    """Writes (or replaces) `CREDITS.txt` at the root of the zip."""
    with zipfile.ZipFile(zip_path) as z:
        ya = NOMBRE in z.namelist()
    if not ya:
        with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as z:
            z.writestr(NOMBRE, contenido)
        return
    tmp = zip_path + ".tmp"
    with zipfile.ZipFile(zip_path) as z, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as nuevo:
        for item in z.infolist():
            if item.filename != NOMBRE:
                nuevo.writestr(item, z.read(item.filename))
        nuevo.writestr(NOMBRE, contenido)
    os.replace(tmp, zip_path)


def leer(zip_path: str) -> str:
    with zipfile.ZipFile(zip_path) as z:
        return z.read(NOMBRE).decode("utf-8") if NOMBRE in z.namelist() else ""
