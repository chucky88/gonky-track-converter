"""The `REPORT.md` of each conversion: what the tool found in the track and which gates passed.

So the tool can learn from tracks nobody has tested: the person converting attaches this report to
an *issue* ("New case", "Working conversion", "Failure") and within seconds you can see what is
different about their track — a shader never seen before, an untranslated surface, lights declared
in another way, a red gate.

🔑 It carries NOTHING of the mod's content (no meshes, no textures, no files): only shader, surface
and material names, counts and the gate results. No paths from the converting user's computer
either (only the name of the track folder).
"""
import collections
import datetime
import os
import re

from version import VERSION

# AC shaders the pipeline handles on purpose (the rest go through the general path)
SHADERS_CONOCIDOS = {
    "ksPerPixel", "ksPerPixelNM", "ksPerPixelAT", "ksPerPixelAT_NM", "ksPerPixelAlpha",
    "ksPerPixelMultiMap", "ksPerPixelMultiMap_AT", "ksPerPixelMultiMap_AT_NMDetail",
    "ksPerPixelMultiMap_NMDetail", "ksPerPixelMultiMap_emissive", "ksMultilayer",
    "ksMultilayer_fresnel_nm", "ksMultilayer_fresnel_nm4", "ksMultilayer_objsp", "ksTree",
    "ksGrass", "ksFlags", "ksSkinnedMesh", "ksPerPixelReflection", "ksWindscreen",
}


def _ext_config(carpeta: str) -> collections.Counter:
    """Sections of CSP's `extension/ext_config.ini`, by type (LIGHT_SERIES, MATERIAL_ADJUSTMENT…)."""
    ruta = os.path.join(carpeta, "extension", "ext_config.ini")
    if not os.path.exists(ruta):
        return collections.Counter()
    texto = open(ruta, encoding="utf-8", errors="replace").read()
    return collections.Counter(re.sub(r"_[.\d]*$|_\.\.\.$", "", m).rstrip("_.")
                               for m in re.findall(r"^\[([A-Z_][A-Z0-9_.]*)", texto, re.M))


def escribir(ruta: str, ctx: dict, argv: list, puertas: list, carpeta: str, trazado: str,
             ui: dict, zip_ok: bool) -> str:
    import kn5_read as K
    t = ctx.get("trazado_ac") or {}
    shaders, sin_textura = collections.Counter(), 0
    for pieza in ctx.get("kn5") or []:
        try:
            for m in K.leer(pieza)["materiales"]:
                shaders[m.shader] += 1
                sin_textura += not m.texturas
        except Exception:  # noqa: BLE001  (a report must not bring down the conversion)
            pass
    avisos = []
    for salida in ctx.get("salidas_blender", []):
        for ln in salida.splitlines():
            if ("⚠️" in ln or "🔴" in ln) and ln.strip() not in avisos:
                avisos.append(ln.strip()[:220])
    import opciones as OP
    opciones, i = [], 1
    while i < len(argv):
        a = argv[i]
        if a in OP._CON_VALOR and i + 1 < len(argv):
            v = argv[i + 1]
            # no paths from the converting user's computer: only the last component
            ultimo = re.split(r"[\\/]", v.rstrip("\\/"))[-1]     # Linux or Windows path
            en, v = OP.ingles(a, v)
            opciones.append(f"{en} {ultimo if ('/' in v or '\\' in v) else v}")
            i += 2
        else:
            opciones.append(OP.ingles(a))
            i += 1
    L = [f"# Conversion report · {ui.get('name') or ctx.get('nombre')}", "",
         f"Gonky Track Converter v{VERSION} · {datetime.date.today().isoformat()} · "
         f"{'✅ zip written' if zip_ok else '🔴 zip NOT written'}", "",
         "> No mod content: only what the tool found. Attach it to an *issue* to help improve the",
         "> tool (see CONTRIBUTING.md).", "",
         "## Track", "",
         f"- AC mod: {ui.get('name') or '?'} · author {ui.get('author') or '?'} · version {ui.get('version') or '?'}",
         f"- layout: `{trazado}` · AMS2 id: `{ctx.get('nombre')}` · `.kn5` pieces: {len(ctx.get('kn5') or [])}",
         f"- physics: {'`' + str(t.get('fisica')) + '` (separate)' if t.get('fisica') else 'inside the visible meshes'}",
         f"- AI racing line: {len(t.get('trazada') or [])} points · pit lane: {len(t.get('boxes_linea') or [])} points",
         f"- editor markers: grid {len((t.get('marcas') or {}).get('parrilla') or [])} · "
         f"pits {len((t.get('marcas') or {}).get('boxes') or [])} · timing {len((t.get('marcas') or {}).get('tiempos') or {})}",
         "", "## Physical surfaces (triangles)", ""]
    for s, n in sorted((t.get("superficies_colision") or {}).items(), key=lambda x: -x[1]):
        L.append(f"- `{s}`: {n}")
    L += ["", "## Assetto Corsa shaders (materials)", ""]
    for s, n in shaders.most_common():
        L.append(f"- `{s}`: {n}" + ("" if s in SHADERS_CONOCIDOS else "  ← **never seen before**"))
    if sin_textura:
        L.append(f"- materials without any texture: {sin_textura}")
    ext = _ext_config(carpeta)
    L += ["", "## Custom Shaders Patch (`ext_config.ini`)", ""]
    L += [f"- `[{k}]`: {n}" for k, n in ext.most_common()] or ["- no `ext_config.ini`"]
    L += ["", "## Gates", ""]
    L += [f"- {'✅' if ok else '🔴'} {nombre}: {detalle}" for nombre, ok, detalle in puertas]
    if avisos:
        L += ["", "## Warnings during the conversion", ""] + [f"- {a}" for a in avisos[:60]]
    L += ["", "## Options used", "", "```", " ".join(opciones), "```", ""]
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return ruta
