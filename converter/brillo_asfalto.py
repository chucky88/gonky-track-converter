"""The asphalt GLOSS mask and level (road shader). No `bpy`: it can be tested on its own.

Split out of `construir_paquete.py` so that it can run outside Blender.
"""
import os
import re
import rutas as _R  # noqa: E402  (ImageMagick: see rutas.py)

ALFA_BRILLO_ASFALTO = 0.38       # Daytona, alpha of `roadc.dds` (0.376) and `roada2.dds` (0.358), measured
ALFA_SIN_MASCARA = 0.9           # above this the texture carries no mask (DXT1 reads alpha 1)


def brillo_de_asfalto(salida: str, nombre: str, alfa: float = ALFA_BRILLO_ASFALTO, brillo_ac=None) -> dict:
    """The asphalt GLOSS MASK: the alpha of `diffuse1Texture` in the road shader.

    🔴 Symptom (Jarama): the asphalt reflections were wrong, sometimes fine and sometimes
    not. Reiza's asphalt textures carry alpha (Daytona `roadc` 0.38, `roada2` 0.36), and so
    does the one by the author of the Charlotte (0.55). The Jarama and Roval ones are DXT1:
    NO alpha, which the game reads as 1 → asphalt shining at full gloss across the whole
    track. AC does not use that channel, so the original does not provide the value: the
    Daytona one is used.
    ⚠️ Hypothesis about the shader (the OMTT documentation does not say): alpha = gloss mask.

    HOW MUCH each material shines comes from the ORIGINAL (`brillo_ac`: {material: AC
    ksSpecular}): in the Jarama the dirt and the secondary asphalts are 0.05 (matte) and
    only the main asphalt and the lines are 1.0. With `globalSpecularFactor` 1.0 on ALL of
    them, a dirt run-off area with the road shader reflected like a mirror.

    ⚠️ The texture may also be used by materials that are NOT road (`asphalt_01.dds` on the
    pit wall): the original is left untouched, a COPY with alpha is written and only the
    road materials are pointed at it. Textures that already carry a mask (< 0.9) are kept."""
    import subprocess
    import generar_mapa as GM
    brillo_mayus = {k.upper(): v for k, v in brillo_ac.items()} if brillo_ac else None
    pista = os.path.join(salida, "Tracks", nombre)
    base = os.path.join(salida, "Tracks")
    hechas, materiales, respetadas, especular = {}, [], set(), {}
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8", errors="ignore").read()
        if "rz_road_main" not in txt:
            continue
        m = re.search(r'(name="diffuse1Texture".*?<value v=")([^"]*)(")', txt, flags=re.S)
        if not m or not m.group(2):
            continue
        rel = m.group(2)                                    # tracks\textures\<n>\x.dds
        origen = os.path.join(salida, *rel.replace("\\", "/").split("/"))
        if not os.path.exists(origen):
            origen = os.path.join(base, *rel.replace("\\", "/").split("/")[1:])
        if not os.path.exists(origen):
            continue
        if rel not in hechas:
            media = subprocess.run([*_R.IM_MAGICK, origen, "-format", "%[fx:mean.a]", "info:"],
                                   capture_output=True, text=True).stdout.strip()
            opaca = subprocess.run([*_R.IM_MAGICK, origen, "-format", "%[opaque]", "info:"],
                                   capture_output=True, text=True).stdout.strip().lower() == "true"
            try:
                a = float(media)
            except ValueError:
                a = 1.0
            # ⚠️ Keeping the author's mask must NOT skip the whole material: the gloss from
            # the original below is applied all the same. With a `continue` here, 3 of the 5
            # asphalts of the Charlotte were left at 1.0 instead of their 0.1-0.5.
            if not opaca and a < ALFA_SIN_MASCARA:
                respetadas.add(os.path.basename(origen))
                hechas[rel] = None
            else:
                destino = origen[:-4] + "_gr_brillo.dds"
                tmp = destino[:-4] + "_tmp.png"
                subprocess.run([*_R.IM_MAGICK, origen + "[0]", "-alpha", "set", "-channel", "A",
                                "-evaluate", "set", f"{alfa * 100:.1f}%", "+channel", tmp],
                               check=True, capture_output=True)
                ok, err = GM.a_dds(tmp, destino, "dxt5", mipmaps=True)
                os.remove(tmp)
                hechas[rel] = rel[:-4] + "_gr_brillo.dds" if ok else None
        nuevo = txt
        if hechas[rel]:
            nuevo = txt[:m.start(2)] + hechas[rel] + txt[m.end(2):]
        # ⚠️ The .mtx files come out in UPPERCASE (`LAS_ROAD_D2.mtx`) and the `.kn5` keeps the
        # author's name (`las_road_d2`): with an exact lookup none matched in the Charlotte and
        # the package came out WITHOUT the original's gloss, with no warning. In the Jarama it
        # matched because the author already wrote in uppercase. The lookup is case-insensitive.
        g_ac = brillo_mayus.get(f[:-4].upper()) if brillo_mayus else None
        if g_ac is not None:
            g = max(0.02, min(1.0, float(g_ac)))
            nuevo = re.sub(r'(<shaderparam name="globalSpecularFactor" type="EPT_F32">\s*<value v=")[^"]*(")',
                           lambda mm: mm.group(1) + f"{g:.3f}" + mm.group(2), nuevo, count=1)
            especular[f[:-4]] = g
        if nuevo != txt:
            open(ruta, "w", encoding="utf-8").write(nuevo)
            materiales.append(f[:-4])
    return {"materiales": materiales, "texturas": sorted(os.path.basename(v) for v in hechas.values() if v),
            "respetadas": sorted(respetadas), "alfa": alfa, "especular": especular}
