"""Custom banners on the author's banner meshes (`--banners <config.json>`).

It was born with the Charlotte by «13x»: the back fences were **plain white canvases**
(`Atl_Canopy_D`, the texture the author used) and at night the floodlights burned them out.
Three groups, measured in `charlotte_objs.kn5`:

| mesh | author's material | panels | each |
|---|---|---|---|
| `Charlotte_T1FenceBanners_A` (+ `_backside`) | `…_Banners_A` (canvas) | 45 + 2 background stretches | 2.0 × 1.1 m |
| `Charlotte_T1_FenceBanners_B` | `…_Banners_A` (the SAME canvas!) | 9 | 7.6 × 2.3 m |
| `Charlotte_T1_FenceBanners_C` | `…_Banners_B` (logos) | 14 | ~10.7 × 1.3 m — left untouched |

Each panel uses the WHOLE texture (u from n to n+1, with n even and different for each
panel), so:
- A and B share a material → each group is given its own (otherwise the same image would
  look fine on one and distorted on the other: 1.74:1 versus 3.3:1);
- to ALTERNATE two designs, the texture is an atlas of two halves and each panel keeps its
  own (u' = n + half·0.5 + 0.5·(u − n)), in order of n;
- the stretches that use the texture more than once (the 55 m background, u from 6 to 26)
  go to a plain material: a logo repeated 20 times and distorted looks worse than a plain
  background.

Orientation, measured against group C (the author's logos, which look right in the game): A
and B have v going down with height and u growing to the right, like C → the images come
out upright. The back face (`_backside`) has u reversed when seen from behind →
`espejo: true`.

The proportions of the IMAGE do not matter (the UV stretches it over the panel): what counts
is that the design is cropped to the panel's proportions. That is why the textures are
powers of 2.

Image paths in the JSON are relative to the JSON's own folder.
"""

import json
import math
import os
import re
import subprocess
import rutas as _R  # noqa: E402  (ImageMagick: see rutas.py)

LADO = {1: (1024, 512), 2: (2048, 512)}      # by number of alternating designs
FONDO_DDS = "gr_pancarta_fondo.dds"


def leer(ruta):
    """The JSON, with each image as an absolute path: a relative one is relative to the JSON's folder
    (every step runs inside `converter/`, so resolving it anywhere else found nothing)."""
    with open(ruta, encoding="utf-8") as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(ruta))
    for g in cfg["grupos"]:
        g["imagenes"] = [os.path.join(base, os.path.expanduser(i)) for i in g["imagenes"]]
    return cfg


def _dds(orden, destino):
    subprocess.run([*_R.IM_CONVERT, *orden, "-define", "dds:compression=dxt5", "-define", "dds:mipmaps=8",
                    destino], check=True, capture_output=True)


def texturas(cfg, tex_dir):
    """The DDS files in the circuit's texture folder: `poner_texturas_propias` finds them
    by the material's image name and the exporter copies them into the package."""
    hechas = {}
    for g in cfg["grupos"]:
        f = g["textura"] + ".dds"
        if f in hechas:
            continue
        w, h = LADO[len(g["imagenes"])]
        mitad = w // len(g["imagenes"])
        orden = []
        for img in g["imagenes"]:
            orden += ["(", img, "-resize", f"{mitad}x{h}!", ")"]
        _dds(orden + ["+append", "-alpha", "off"], os.path.join(tex_dir, f))
        hechas[f] = (w, h)
    r, gg, b = cfg.get("fondo", (26, 26, 30))
    _dds(["-size", "64x64", f"xc:rgb({r},{gg},{b})", "-alpha", "off"], os.path.join(tex_dir, FONDO_DDS))
    return hechas


def _islas(bm):
    """Groups of connected faces (each panel is an island)."""
    vistas, fuera = set(), []
    for f in bm.faces:
        if f.index in vistas:
            continue
        pila, isla = [f], []
        vistas.add(f.index)
        while pila:
            c = pila.pop()
            isla.append(c)
            for e in c.edges:
                for o in e.link_faces:
                    if o.index not in vistas:
                        vistas.add(o.index)
                        pila.append(o)
        fuera.append(isla)
    return fuera


def casilla(us):
    """The panel's integer n (u goes from n to n+1), tolerating the author overshooting a hair."""
    return math.floor(min(us) + 0.05)


def remapear(u, n, k, n_dis, espejo=False):
    """The new u of a vertex of panel `k` (in order of n) with `n_dis` alternating designs."""
    fr = min(1.0, max(0.0, u - n))
    if espejo:
        fr = 1.0 - fr
    return n + (k % n_dis) / n_dis + fr / n_dis


def aplicar(cfg, material_de):
    """In Blender. `material_de(nombre, dds)` creates the material with an image named `dds`
    (the usual `kn5_to_blender.material`, so that it follows the textures contract)."""
    import bmesh
    import bpy

    fondo = material_de("GR_PANCARTA_FONDO", FONDO_DDS)
    resumen = []
    for g in cfg["grupos"]:
        mat = material_de(g["material"], g["textura"] + ".dds")
        n_dis = len(g["imagenes"])
        for nombre in g["mallas"]:
            obj = bpy.data.objects.get(nombre)
            if obj is None or obj.type != "MESH":
                resumen.append(f"🔴 {nombre}: not in the scene")
                continue
            me = obj.data
            me.materials.clear()
            me.materials.append(mat)
            me.materials.append(fondo)
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.faces.ensure_lookup_table()
            uv = bm.loops.layers.uv.active
            islas = _islas(bm)
            paneles, anchas = [], 0
            for isla in islas:
                us = [lp[uv].uv[0] for f in isla for lp in f.loops]
                if max(us) - min(us) > 1.5:          # uses the texture several times: plain background
                    for f in isla:
                        f.material_index = 1
                    anchas += 1
                    continue
                # ⚠️ +0.05 and not +1e-3: the author leaves minimum u values like −0.002
                # (group B) and the floor gave −1; the whole panel was squashed into a strip of
                # u −0.002…0. See `casilla()`.
                paneles.append((casilla(us), isla))
            paneles.sort(key=lambda p: p[0])
            # Check on the real geometry (the `.meb` cannot be read with faces): a panel that
            # uses less than half of its cell is a `casilla()` bug, not a crop by the author
            # (the most cropped one, the narrow 1.32 m one, uses 82 %). With a +1e-3 rounding,
            # the 9 in group B gave 0.2 %.
            raros = 0
            for n, isla in paneles:
                us = [min(1.0, max(0.0, lp[uv].uv[0] - n)) for f in isla for lp in f.loops]
                raros += (max(us) - min(us)) < 0.5
            for k, (n, isla) in enumerate(paneles):
                for f in isla:
                    f.material_index = 0
                    for lp in f.loops:
                        u, v = lp[uv].uv
                        lp[uv].uv = (remapear(u, n, k, n_dis, g.get("espejo")), v)
            bm.to_mesh(me)
            bm.free()
            me.update()
            resumen.append(f"{nombre}: {len(paneles)} panels ({n_dis} design{'s' if n_dis > 1 else ''}"
                           f"{', mirrored' if g.get('espejo') else ''}) · {anchas} plain background stretches"
                           f" · odd panels {raros}")
    return resumen


def raros_en(texto_blender):
    """The «odd panels» that `aplicar` counted in Blender (None if it was not applied)."""
    m = re.findall(r"odd panels (\d+)", texto_blender or "")
    return sum(int(x) for x in m) if m else None


def comprobar(salida, nombre, cfg, texto_blender=None):
    """In the EXPORTED package: each custom material with its MTX, opaque, pointing at its
    DDS, and the DDS in the package."""
    pista = os.path.join(salida, "Tracks", nombre)
    tex = os.path.join(salida, "Tracks", "textures", nombre)
    mtx = {f[:-4].upper(): f for f in os.listdir(pista) if f.lower().endswith(".mtx")}
    texs = {f.lower() for f in os.listdir(tex)} if os.path.isdir(tex) else set()
    partes = []
    for mat, dds in [(g["material"], g["textura"] + ".dds") for g in cfg["grupos"]] + [("GR_PANCARTA_FONDO", FONDO_DDS)]:
        f = mtx.get(mat.upper())
        if not f:
            return False, f"{mat}: no MTX in the package"
        txt = open(os.path.join(pista, f), encoding="utf-8", errors="ignore").read()
        dif = re.search(r'name="diffuse1?Texture".*?<value v="([^"]*)"', txt, re.S)
        if not dif or os.path.basename(dif.group(1).replace("\\", "/")).lower() != dds.lower():
            return False, f"{mat}: the diffuse is {dif.group(1) if dif else 'none'}, not {dds}"
        if "translucent" in txt.lower():
            return False, f"{mat}: translucent (another step overwrote it)"
        if dds.lower() not in texs:
            return False, f"{dds} is not in the package"
        partes.append(mat)
    raros = raros_en(texto_blender)
    if raros is None:
        return False, "the Blender step didn't say how many panels came out right (was it applied?)"
    if raros:
        return False, f"{raros} panels use less than half of their image (remapping error)"
    return True, "own materials: " + ", ".join(dict.fromkeys(partes)) + " · 0 odd panels"
