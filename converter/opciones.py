"""The options of `convert_ac.py`: ONE table that produces the help (`--help`), the aliases, the
rejection of unknown options and the table in docs/OPTIONS.md.

🔴 Why unknown options are rejected: the pipeline reads each option with `"--x" in argv`, so a typo
(`--real-ground-plan`) or a retired option used to be IGNORED silently and the mod came out without it.

The code reads the options by their internal (Spanish) name; `normalizar` translates the English
names — and a few English values — into it, so both spellings work.

    python3 opciones.py --markdown     → the table for docs/OPTIONS.md
"""
import sys

# (internal name, English name, takes a value, group, description). ✅ = used in conversions that work.
OPCIONES = [
    # required
    ("--carpeta", "--folder", True, "Required", "the AC track folder (the one with the `.kn5` files and the `models_*.ini`)"),
    ("--trazado", "--layout", True, "Required", "the layout subfolder (`layout_gp`, `oval`…); defaults to `layout_speedway`"),
    ("--nombre", "--name", True, "Required", "the track id in AMS2: lowercase, no spaces or dots"),
    # track details
    ("--titulo", "--title", True, "Track details", "the name shown in game (defaults to the `ui_track.json` one)"),
    ("--geo", "--geo", True, "Track details", "✅ `lat,lon,altitude,timezone`: real sun, stars and local time. E.g. `40.6170,-3.5857,620,1`"),
    ("--fecha", "--date", True, "Track details", "reference date `YYYY-M-D`"),
    ("--curvas", "--corners", True, "Track details", "number of corners (info page)"),
    ("--foto", "--photo", True, "Track details", "16:9 photo for the menu; without it, the mod's own"),
    ("--estilo-reiza", "--reiza-style-map", False, "Track details", "✅ track map in the style of the official ones"),
    ("--grupo", "--group", True, "Track details", "✅ group to join layouts into one mod (`join_layouts.py`)"),
    ("--variante", "--variant", True, "Track details", "✅ the layout's name within the group"),
    ("--orden", "--order", True, "Track details", "✅ the layout's position in the group (1, 2…)"),
    # track, grid and AI
    ("--ovalo", "--oval", False, "Track, grid and AI", "✅ it's an oval (banking, oval grid and AI)"),
    ("--limite-boxes", "--pit-limiter", True, "Track, grid and AI", "✅ pit speed limiter in km/h"),
    ("--max-ia", "--max-ai", True, "Track, grid and AI", "✅ grid size; 32 is the game's maximum"),
    ("--parrilla-en-meta", "--grid-at-finish", False, "Track, grid and AI", "✅ moves the author's grid to the finish straight (in AC it's often far away: AMS2 doesn't count the lap until the line is crossed)"),
    ("--parrilla-de", "--grid-from", True, "Track, grid and AI", "✅ forms the grid along ANOTHER layout's racing line with the same finish line (when there's a chicane before the finish)"),
    ("--central-asfalto", "--ai-centre-asphalt", False, "Track, grid and AI", "✅ AI centre line along the middle of the racing asphalt"),
    ("--ancho-asfalto", "--asphalt-width", False, "Track, grid and AI", "✅ track limits along the real asphalt"),
    ("--distancias-boxes", "--pit-distances", False, "Track, grid and AI", "✅ pit and grid lap distances with the official tracks' rule"),
    # materials
    ("--texturas", "--textures", True, "Materials and textures", "✅ CC0 textures folder (`download_textures.py`); defaults to the `settings.ini` one"),
    ("--familias-cc0", "--cc0-families", True, "Materials and textures", "✅ families that get CC0 detail (usually `grass`)"),
    ("--capas-ac", "--ac-layers", False, "Materials and textures", "✅ AC's multilayer asphalt (`ksMultilayer*`): the author's tone and grain at their real scale"),
    ("--brillo-asfalto", "--asphalt-gloss", False, "Materials and textures", "✅ each asphalt's gloss = the original's `ksSpecular`, plus a gloss mask where the texture has none"),
    ("--relieve-asfalto", "--asphalt-normal", False, "Materials and textures", "✅ relief (CC0 normal map) on the asphalt"),
    ("--fresnel-asfalto", "--asphalt-fresnel", True, "Materials and textures", "asphalt fresnel (default 0.2)"),
    ("--vallas-translucidas", "--translucent-fences", False, "Materials and textures", "✅ fences and meshes with the official tracks' recipe"),
    ("--pancartas", "--banners", True, "Materials and textures", "your own banners on the author's banner meshes (JSON; see `converter/pancartas.py`)"),
    ("--publicidad", "--ads", True, "Materials and textures", "`MATERIAL[,MATERIAL…]=image.png`: your image on those ads of the author (with their permission)"),
    # night
    ("--luces-autor", "--author-lights", False, "Night and lights", "✅ the lights the author declared for Custom Shaders Patch (`LIGHT_SERIES`)"),
    ("--focos-daytona", "--track-floodlights", False, "Night and lights", "✅ track floodlights with the official tracks' recipe (both sides, tilted, cold colour + short ones above)"),
    ("--plano-real", "--real-ground-plane", False, "Night and lights", "✅ **essential at night**: each light's ground plane at its real height (without it a high floodlight doesn't reach the asphalt)"),
    ("--focos-gradas", "--stand-floodlights", False, "Night and lights", "✅ floodlights for the grandstands and the crowd"),
    ("--focos-oscuros", "--dark-spot-lights", False, "Night and lights", "extra floodlights on dark stretches (replaced by `--track-floodlights`)"),
    ("--brillos-nocturnos", "--night-glow", True, "Night and lights", "✅ what glows at night (windows, panels…): `all`"),
    ("--semaforos", "--start-lights", False, "Night and lights", "✅ the game's start lights and pit lights"),
    ("--ambiente", "--ambience", True, "Night and lights", "✅ sky and fog of another track in the game (`Daytona`, `Barcelona`…)"),
    # other
    ("--camaras-tv", "--tv-cameras", False, "Other", "✅ TV cameras from the mod's"),
    ("--sonido-propio", "--ambient-sound", False, "Other", "✅ ambient sound placed along the track's grandstands"),
    ("--sin-creditos", "--no-credits", False, "Other", "don't write `CREDITS.txt` into the zip"),
]
_POR_ALIAS = {en: es for es, en, *_ in OPCIONES}
_A_INGLES = {es: en for es, en, *_ in OPCIONES}
_CONOCIDAS = {es for es, *_ in OPCIONES} | {"--help", "-h"}
_CON_VALOR = {es for es, _en, v, *_ in OPCIONES if v}
# English VALUES accepted for options whose values are internal names
VALORES = {
    "--familias-cc0": {"grass": "hierba", "gravel": "grava", "concrete": "hormigon", "asphalt": "asfalto",
                       "walls": "muros", "fences": "vallas", "lines": "lineas"},
    "--brillos-nocturnos": {"all": "todo"},
}


def normalizar(argv: list) -> list:
    """English option names → the internal name; and the English values of `VALORES`."""
    fuera = [_POR_ALIAS.get(a, a) for a in argv]
    for i in range(len(fuera) - 1):
        tabla = VALORES.get(fuera[i])
        if tabla:
            fuera[i + 1] = ",".join(tabla.get(v.strip().lower(), v.strip()) for v in fuera[i + 1].split(","))
    return fuera


def ingles(opcion: str, valor: str = None):
    """The other way round, for what is shown to the user: internal name → English (and its value)."""
    en = _A_INGLES.get(opcion, opcion)
    if valor is None:
        return en
    tabla = {v: k for k, v in VALORES.get(opcion, {}).items()}
    return en, ",".join(tabla.get(v, v) for v in valor.split(","))


def desconocidas(argv: list) -> list:
    """The options that don't exist (typos or retired options). Values don't count."""
    fuera, saltar = [], False
    for a in argv[1:]:
        if saltar:
            saltar = False
            continue
        if a.startswith("-") and a not in _CONOCIDAS and not a[1:2].isdigit():
            fuera.append(a)
        saltar = a in _CON_VALOR
    return fuera


def ayuda() -> str:
    lineas = ["Gonky Track Converter · convert_ac.py: converts an Assetto Corsa layout to Automobilista 2.",
              "", "  python3 convert_ac.py --folder <AC track> --layout <layout> --name <id> [options]",
              "", "(✅ = used in conversions that work · in brackets, the original Spanish name, also accepted)"]
    grupo = None
    for es, en, valor, g, texto in OPCIONES:
        if g != grupo:
            lineas += ["", g.upper()]
            grupo = g
        nombre = en + (" <value>" if valor else "")
        alias = f"[{es}] " if es != en else ""
        lineas.append(f"  {nombre:26s} {alias}{texto.replace('`', '').replace('**', '')}")
    lineas += ["", "More detail and real examples: docs/OPTIONS.md and examples/."]
    return "\n".join(lineas)


def markdown() -> str:
    fuera, grupo = [], None
    for es, en, valor, g, texto in OPCIONES:
        if g != grupo:
            fuera += ["", f"## {g}", "", "| option | also accepted | what |", "|---|---|---|"]
            grupo = g
        fuera.append(f"| `{en}{' <value>' if valor else ''}` | {'`' + es + '`' if es != en else '—'} | {texto} |")
    return "\n".join(fuera).strip() + "\n"


if __name__ == "__main__":
    print(markdown() if "--markdown" in sys.argv else ayuda())
