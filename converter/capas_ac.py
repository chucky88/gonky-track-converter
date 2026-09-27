"""Bakes Assetto Corsa's MULTILAYER asphalt (`ksMultilayer*`) into the base texture of the AMS2 one.

🔴 Why. Symptom measured in the Jarama: the asphalt looked right on a piece of the main straight
and odd on the rest of the circuit. In AC the Jarama's main asphalt (`ROAD_01`, `ROAD_02`,
`ROAD_03`, `ROAD_LINE`) is `ksMultilayer_fresnel_nm`: the base `road.dds` is a LIGHT, SMOOTH grey
(contrast 20) and the look comes from two grain layers MULTIPLIED on top, weighted by a mask
(`asph-mask5.dds`, magenta = layers R and B across the whole track): `001tarmac-detail2`
(contrast 37) repeated ×1 and `001tarmac-noise` (contrast 55) ×0.8 of the base's coordinate.
The AMS2 road shader has no such layers: only the smooth base was left. The finish-line area
that looked right is `ROAD15_META`, a `ksPerPixel` with its complete texture (contrast 76).

The formula comes from the shader's CODE (CSP, `recreated/ksMultilayer_ps.fx`):
`color = base(uv) × Σ mask_c(uv) × detail_c(posW.xz × mult_c) × magicMult`.
🔴 The detail does NOT follow the UV: it follows the WORLD position, in metres — it repeats every
`1/mult` m. Baked onto the UV (`uv × mult`), the Jarama's grain came out 14 times larger (every
14 m instead of every 1 m). A grain in world coordinates CANNOT be baked into a UV texture.
See docs/LESSONS.md.

Recipe (`hornear_asfalto`):
  1. TONE: `base × Σ mask_c × mean(detail_c)` → the base texture (the colour AC gives, without grain).
  2. GRAIN: the author's main layer (the one with the most weight in the mask) goes to the
     `detailTexture` of the AMS2 road shader with Daytona's alpha (0.113: its `tarmac_7_detail`
     is almost the same, grey 63 versus 69) and with the repetition in METRES:
     `detailTiling = metres per UV unit × mult`, per axis and per material (the Jarama's UV is
     not isotropic: `ROAD_LINE` 10 m × 0.72 m).

No `bpy`: it can be tested on its own.
"""
import json
import os
import re

CANALES = ("R", "G", "B", "A")


def metros_por_uv(modelos) -> dict:
    """{material: (metres per unit of u, of v)}: per-triangle median of the world/UV Jacobian."""
    import numpy as np
    import kn5_read as K
    por = {}
    for f in modelos:
        r = K.leer(f, con_geometria=True)
        for m in r["mallas"]:
            if not m.uv or not m.dibuja:
                continue
            nom = r["materiales"][m.material].nombre
            for a, b, c in m.caras[::2]:
                dP = np.array([np.subtract(m.pos[b], m.pos[a]), np.subtract(m.pos[c], m.pos[a])]).T
                dU = np.array([np.subtract(m.uv[b], m.uv[a]), np.subtract(m.uv[c], m.uv[a])]).T
                if abs(np.linalg.det(dU)) < 1e-9:
                    continue
                J = dP @ np.linalg.inv(dU)
                por.setdefault(nom, []).append((np.linalg.norm(J[:, 0]), np.linalg.norm(J[:, 1])))
    return {k: (float(np.median([x[0] for x in v])), float(np.median([x[1] for x in v]))) for k, v in por.items()}


def leer_multicapa(modelos, carpeta_tex):
    """{material: {base, mascara, capas: [(canal, textura, mult)], m_uv: (u, v)}} from the `.kn5` files."""
    import kn5_read as K
    fuera = {}
    escala = metros_por_uv(modelos)
    for f in modelos:
        for m in K.leer(f)["materiales"]:
            if not m.shader.lower().startswith("ksmultilayer") or m.nombre in fuera:
                continue
            t = m.texturas
            capas = []
            for c in CANALES:
                tex = t.get(f"txDetail{c}")
                if tex:
                    capas.append((c, os.path.join(carpeta_tex, tex), float(m.props.get(f"mult{c}", 1.0))))
            if t.get("txDiffuse") and t.get("txMask") and capas:
                fuera[m.nombre] = {"base": os.path.join(carpeta_tex, t["txDiffuse"]),
                                   "mascara": os.path.join(carpeta_tex, t["txMask"]), "capas": capas,
                                   "m_uv": escala.get(m.nombre), "shader": m.shader,
                                   "magic": float(m.props.get("magicMult", 1.0) or 1.0)}
    return fuera


def _imagen(ruta):
    import numpy as np
    from PIL import Image
    im = Image.open(ruta)
    im.load()
    return np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0


def hornear(base, mascara, capas):
    """🔴 DO NOT USE for `ksMultilayer`/`ksMultilayer_fresnel_nm`: it samples the detail over the UV
    (`uv × mult`) and in AC it goes over the WORLD (in the Jarama: grain 14× larger). Only valid
    for `ksMultilayer_objsp`, the only variant that uses the UV. Kept for that case.

    The base texture with the AC layers multiplied in, as an RGB 0..1 array (height × width × 3)."""
    import numpy as np
    from PIL import Image
    b = _imagen(base)
    h, w = b.shape[:2]
    m = np.asarray(Image.open(mascara).convert("RGBA").resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = (xs + 0.5) / w, (ys + 0.5) / h
    suma = np.zeros((h, w, 3), dtype=np.float32)
    for canal, ruta, mult in capas:
        peso = m[:, :, CANALES.index(canal)]
        if float(peso.max()) < 0.01 or not os.path.exists(ruta):
            continue
        d = _imagen(ruta)
        hd, wd = d.shape[:2]
        iy = (np.floor(v * mult * hd).astype(np.int64)) % hd
        ix = (np.floor(u * mult * wd).astype(np.int64)) % wd
        suma += peso[:, :, None] * d[iy, ix, :3]
    return np.clip(b[:, :, :3] * suma, 0.0, 1.0)


def tono(base, mascara, capas, magic=1.0):
    """`base × Σ mask_c × mean(detail_c) × magicMult`: the AC colour without grain (RGB 0..1).

    🔴 `magicMult` is NOT always 1: in the Jarama it is (which is why it was not being
    read), in the Charlotte it is 1.7 for the track and the apron and 1.2 for the Roval tarmac.
    Without it the tone came out at grey 43 instead of 73: 40 % darker than the original. It is
    applied only to the COLOUR; the alpha (gloss mask, a hypothesis in AMS2) is left as the base
    brings it."""
    import numpy as np
    from PIL import Image
    b = _imagen(base)
    h, w = b.shape[:2]
    m = np.asarray(Image.open(mascara).convert("RGBA").resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0
    suma = np.zeros((h, w, 3), dtype=np.float32)
    for canal, ruta, _mult in capas:
        peso = m[:, :, CANALES.index(canal)]
        if float(peso.max()) < 0.01 or not os.path.exists(ruta):
            continue
        suma += peso[:, :, None] * _imagen(ruta)[:, :, :3].reshape(-1, 3).mean(axis=0)
    return np.clip(b[:, :, :3] * suma * magic, 0.0, 1.0)


def capa_principal(mascara, capas):
    """(canal, textura, mult) of the layer with the most weight in the mask."""
    import numpy as np
    m = _imagen(mascara)
    vivas = [c for c in capas if os.path.exists(c[1]) and c[2] > 0]
    return max(vivas, key=lambda c: float(np.mean(m[:, :, CANALES.index(c[0])])), default=None)


ALFA_GRANO = 0.113      # Daytona, `rz_shared/tarmac_7_detail.dds` (measured): the strength of the detail in AMS2


def hornear_asfalto(salida: str, nombre: str, datos_ac: dict) -> dict:
    """For each AMS2 road material that was multilayer in AC: TONE in the base, the author's GRAIN
    in the detail and the repetition in metres (see the module docstring). New textures:
    `<base>_gr_ac.dds` and `<detalle>_gr_grano.dds` (the originals are left untouched)."""
    import numpy as np
    from PIL import Image
    import generar_mapa as GM
    pista = os.path.join(salida, "Tracks", nombre)
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    hechas, materiales, repeticion = {}, [], {}
    # ⚠️ Same bug as in `brillo_asfalto`: .mtx in UPPERCASE, `.kn5` with the author's name
    # → 0 materials and no warning (measured in the Charlotte). The lookup is case-insensitive.
    datos_ac = {k.upper(): v for k, v in datos_ac.items()}

    def poner(txt, param, valor):
        return re.sub(r'(<shaderparam name="' + param + r'"[^>]*>.*?<value v=")[^"]*(")',
                      lambda mm: mm.group(1) + valor + mm.group(2), txt, count=1, flags=re.S)

    for f in sorted(os.listdir(pista)):
        mat = f[:-4]
        if not f.lower().endswith(".mtx") or mat.upper() not in datos_ac:
            continue
        ruta = os.path.join(pista, f)
        txt = open(ruta, encoding="utf-8", errors="ignore").read()
        if "rz_road_main" not in txt:
            continue
        d = datos_ac[mat.upper()]
        # 1) tone
        clave = (d["base"], d["mascara"], tuple(tuple(c) for c in d["capas"]), d.get("magic", 1.0))
        if clave not in hechas:
            nuevo = os.path.splitext(os.path.basename(d["base"]))[0] + "_gr_ac"
            if any(v == nuevo for v in hechas.values()):
                nuevo += f"_{len(hechas)}"
            png = os.path.join(tex, nuevo + "_tmp.png")
            rgb = tono(d["base"], d["mascara"], d["capas"], d.get("magic", 1.0))
            # 🔴 The base's ALPHA is the author's GLOSS MASK (3 of the 4 asphalt textures of
            # the Charlotte carry it). In DXT1 it was lost, and `brillo_asfalto` then put
            # Daytona's fixed 0.38 on top of the author's. It is preserved.
            alfa = _imagen(d["base"])[:, :, 3]
            if float(alfa.min()) < 0.98:
                Image.fromarray((np.dstack([rgb, alfa]) * 255.0 + 0.5).astype(np.uint8), "RGBA").save(png)
                formato = "dxt5"
            else:
                Image.fromarray((rgb * 255.0 + 0.5).astype(np.uint8), "RGB").save(png)
                formato = "dxt1"
            ok, _err = GM.a_dds(png, os.path.join(tex, nuevo + ".dds"), formato, mipmaps=True)
            os.remove(png)
            if not ok:
                continue
            hechas[clave] = nuevo
        txt = poner(txt, "diffuse1Texture", f"tracks\\textures\\{nombre}\\{hechas[clave]}.dds")
        # 2) grain with its repetition in metres
        cap = capa_principal(d["mascara"], d["capas"])
        if cap and d.get("m_uv"):
            _c, ruta_det, mult = cap
            grano = os.path.splitext(os.path.basename(ruta_det))[0] + "_gr_grano"
            destino = os.path.join(tex, grano + ".dds")
            if not os.path.exists(destino):
                png = destino[:-4] + "_tmp.png"
                rgb = _imagen(ruta_det)[:, :, :3]
                rgba = np.dstack([rgb, np.full(rgb.shape[:2], ALFA_GRANO, dtype=np.float32)])
                Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA").save(png)
                GM.a_dds(png, destino, "dxt5", mipmaps=True)
                os.remove(png)
            tx, ty = d["m_uv"][0] * mult, d["m_uv"][1] * mult
            txt = poner(txt, "detailTexture", f"tracks\\textures\\{nombre}\\{grano}.dds")
            txt = poner(txt, "detailTilingX", f"{tx:.3f}")
            txt = poner(txt, "detailTilingY", f"{ty:.3f}")
            repeticion[mat] = (round(tx, 1), round(ty, 1), round(1 / mult, 2))
        open(ruta, "w", encoding="utf-8").write(txt)
        materiales.append(mat)
    return {"materiales": materiales, "texturas": sorted(set(hechas.values())), "repeticion": repeticion}


def guardar(modelos, carpeta_tex, ruta_json):
    json.dump(leer_multicapa(modelos, carpeta_tex), open(ruta_json, "w"), indent=1)
    return ruta_json
