"""Draws the selection-screen images from the `.aiw`, instead of inheriting them.

    python3 generar_mapa.py <track.aiw> <pack>/GUI [--nombre Charlotte] [--render photo.png]

🔴 Why it exists: the Sample Project template carries the map, the photo and the logo of
**Meadowdale**, and `preparar_plantilla` only changes their FILE names. So a 1.5-mile oval
was advertised with the drawing of a wooded layout in Illinois — and there is no error at
all, because an image always shows.

The map comes from the same waypoints used for everything else: the two track EDGES are
drawn (`wp_pos` ± `wp_perp` × `wp_width`), which is what gives the silhouette the game
shows — a white line on transparent.

Requires ImageMagick (`convert`) to write the DDS: PIL reads DDS but does not write it.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aiw_read as A  # noqa: E402
import rutas as _R  # noqa: E402  (ImageMagick: see rutas.py)

# Format COPIED from a mod that works (Enna Pergusa), not chosen:
#    trackmaps3d 512x512 DXT5 · trackmaps 512x512 DXT5 · trackphotos 1280x720 DXT1
#    and **ZERO MIPMAPS** in all of them.
# ⚠️ ImageMagick generates 10 mipmaps on its own (`caps 0x401008`). Enna's carries 0.
#    It was the ONLY thing that changed between a version that could be driven and the
#    next one, which got stuck loading, so the format is copied as is instead of assuming
#    it does not matter.
# 1000x1000: that is what Mid-Ohio, GJ Kartway and the sample use, **all three**. At 512 with
# a 2-3 px stroke and no mipmap chain, the map lines break up when the UI scales them down.
# It costs 1.3 MB per circuit and it is the same drawing.
LADO_3D = 1000
LADO_HUD = 512
# 1920x1080: that is what Mid-Ohio, GJ Kartway and the sample use, all three. 1280x720 is
# half the pixels.
FOTO = (1920, 1080)
COLOR_HUD = (173, 178, 181, 255)   # sampled from Enna's, not invented
MARGEN = 0.06


def _proyectar(puntos, lado):
    """World (x, z) -> pixels, centred and scaled, keeping the aspect ratio.

    Height is ignored: the map is a top-down view. And the image's vertical axis grows
    downwards, so Z is flipped or the circuit comes out mirrored.
    """
    xs = [p[0] for p in puntos]
    zs = [p[2] for p in puntos]
    ancho, alto = max(xs) - min(xs), max(zs) - min(zs)
    escala = (lado * (1 - 2 * MARGEN)) / max(ancho, alto, 1e-6)
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    return [
        (lado / 2 + (p[0] - cx) * escala, lado / 2 - (p[2] - cz) * escala) for p in puntos
    ]


def _acotado(main, lado):
    """Width cap = the MEDIAN (not double), so that the pit entry does not draw spikes."""
    i = 0 if lado == "left" else 1
    anchos = sorted(w.width[i] for w in main)
    return anchos[len(anchos) // 2]  # the median: the left width ranges from 8.4 to 30 m (apron + pits)


def _vuelve_atras(puntos, umbral: float = 0.3) -> bool:
    """Does the route go back along its dominant axis by more than `umbral` of its extent?

    A straight pit lane always advances in the same direction; a U-shaped one (the AC one,
    which wraps around half the oval) goes out and comes back. Only the former admits the
    spine from `_espina`.
    """
    if len(puntos) < 4:
        return False
    xs = [p[0] for p in puntos]
    zs = [p[2] for p in puntos]
    eje = 0 if (max(xs) - min(xs)) > (max(zs) - min(zs)) else 2
    v = [p[eje] for p in puntos]
    ext = max(v) - min(v) or 1.0
    signo = 1 if v[-1] - v[0] >= 0 else -1
    peor, pico = 0.0, v[0]
    for x in v:
        pico = max(pico, x) if signo > 0 else min(pico, x)
        peor = max(peor, (pico - x) * signo)
    return peor / ext > umbral


def _espina(puntos, trozos: int = 40):
    """Reduces a cloud of pit points to ONE line: its axis.

    ⚠️ The `wp_bitfields=1` points are not the pit lane: they are the pit BOXES, and they
    alternate between the lane and the garage. Drawn in order they come out like a comb and
    the map looks broken. They are projected onto their dominant axis, split into stretches,
    and the lateral median of each stretch is taken — what remains is the spine, which is
    what a map should show.
    """
    if len(puntos) < 4:
        return [w.pos for w in puntos]
    xs = [w.pos[0] for w in puntos]
    zs = [w.pos[2] for w in puntos]
    # dominant axis: the one that stretches the most
    horizontal = (max(xs) - min(xs)) > (max(zs) - min(zs))
    largo = (lambda p: p[0]) if horizontal else (lambda p: p[2])
    corto = (lambda p: p[2]) if horizontal else (lambda p: p[0])

    ps = sorted((w.pos for w in puntos), key=largo)
    lo, hi = largo(ps[0]), largo(ps[-1])
    paso = (hi - lo) / trozos if hi > lo else 1.0
    salida = []
    for k in range(trozos):
        tramo = [p for p in ps if lo + k * paso <= largo(p) < lo + (k + 1) * paso]
        if not tramo:
            continue
        lat = sorted(corto(p) for p in tramo)[len(tramo) // 2]
        alt = sorted(p[1] for p in tramo)[len(tramo) // 2]
        eje = lo + (k + 0.5) * paso
        salida.append((eje, alt, lat) if horizontal else (lat, alt, eje))

    # moving average of 3: the stretches that mix lane and garage leave a jitter that on a
    # map reads as noise. Smoothing ONE drawing falsifies nothing; it is not used for driving.
    if len(salida) >= 3:
        suave = [salida[0]]
        for i in range(1, len(salida) - 1):
            tres = salida[i - 1 : i + 2]
            suave.append(tuple(sum(c[j] for c in tres) / 3 for j in range(3)))
        suave.append(salida[-1])
        salida = suave
    return salida


def dibujar_hud(aiw: A.Aiw, lado: int = LADO_HUD):
    """The IN-RACE map: a thick line along the centreline, plus the pit lane.

    It is a different drawing from the selection-screen one: there the two thin edges go,
    here a single ribbon. And the game wants it under TWO names — `<track>.dds` and
    `map_<track>.dds` in `GUI/trackmaps/` — which in Enna are **the same file** (same md5).
    Without the `map_…` one there is no map in the HUD.
    """
    from PIL import Image, ImageDraw

    main = aiw.main_path
    if not main:
        return None
    # 🔴 The spine is only valid for a STRAIGHT lane. `_espina` projects onto one axis and
    # takes the median per stretch, and the Assetto Corsa pit lane is U-shaped (main
    # straight, turns 1-2, back straight): in each stretch it mixed both sides of the oval
    # and drew a line CROSSING THE INFIELD on the HUD map. If the ordered route comes back
    # along its axis, it is a path and not a comb: it is drawn as is. With AMS1 (straight)
    # nothing changes.
    ordenada = [w.pos for w in aiw.pit_path_ordered()]
    pit = ordenada if _vuelve_atras(ordenada) else _espina(aiw.pit_waypoints)
    # a common projection for track and pits, or the branch would come out misplaced
    todos = _proyectar([w.pos for w in main] + pit, lado)
    pista_px, pit_px = todos[: len(main)], todos[len(main) :]

    im = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _cinta(d, pista_px + [pista_px[0]], COLOR_HUD, max(3, lado // 55))
    if len(pit_px) > 2:
        _cinta(d, pit_px, COLOR_HUD, max(2, lado // 150))
    return im


def dibujar(aiw: A.Aiw, lado: int, grosor: int):
    from PIL import Image, ImageDraw

    main = aiw.main_path
    if not main:
        return None
    # ⚠️ `wp_width` shoots up where the pit lane joins, and drawn as is it produces spikes
    # that look like noise instead of a pit lane. It is capped at the median (`_acotado`):
    # the map is a silhouette, not a plan.
    izq = [w.edge("left", ancho=_acotado(main, "left")) for w in main]
    der = [w.edge("right", ancho=_acotado(main, "right")) for w in main]
    # a single projection for both edges, or each one would come out at its own scale
    todos = _proyectar(izq + der, lado)
    izq_px, der_px = todos[: len(izq)], todos[len(izq) :]

    # 🔴 ONE THICK RIBBON, not two thin edges. Drawn at 1000 px with a 5 px line, the game
    # shows it at about 60 px: 5/16 = 0.3 px on screen, which comes out DOTTED. Reiza's
    # position marker (the one in the S1/S2/S3 mix in the list) is a white ribbon about
    # 3-4 % of the width. A thin dark border so that it reads on top of the photo.
    ancho = max(grosor, round(lado * 0.045))
    borde = max(2, ancho // 6)
    centro = _proyectar([w.pos for w in main], lado)
    im = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _cinta(d, centro + [centro[0]], (20, 20, 24, 230), ancho + 2 * borde)
    _cinta(d, centro + [centro[0]], (255, 255, 255, 255), ancho)
    del izq_px, der_px
    return im


FUENTE_ROTULOS = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def dibujar_reiza(aiw: A.Aiw, lado: int = LADO_3D):
    """The menu map in REIZA STYLE (like the «TrackMaps3D Reiza style» pack).
    Measured in `GUITRACKMAPS.bff/gui/trackmaps3d/daytona.dds`:
    a white ribbon with a dark border, a cut at each sector change and at the finish line,
    «S1/S2/S3» labels OUTSIDE the track, the pit lane in thin RED and a grey arrow next to the
    finish line showing the direction of travel. Sectors and pits come from the AIW itself."""
    import math
    from PIL import Image, ImageDraw, ImageFont

    main = aiw.main_path
    if not main:
        return None
    pit = aiw.pit_path_ordered() if aiw.pit_waypoints else []
    todos = _proyectar([w.pos for w in main] + [w.pos for w in pit], lado)
    centro, calle = todos[: len(main)], todos[len(main):]
    ancho = round(lado * 0.035)
    borde = max(2, ancho // 6)
    im = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    anillo = centro + [centro[0]]
    _cinta(d, anillo, (20, 20, 24, 235), ancho + 2 * borde)
    # the pit lane, BENEATH the white ribbon: where it separates from the track it shows red,
    # and where it runs alongside it does not muddy the track (like Daytona's)
    if len(calle) > 1:
        _cinta(d, calle, (20, 20, 24, 235), max(3, ancho // 3) + 2 * borde)
        _cinta(d, calle, (205, 30, 30, 255), max(3, ancho // 3))
    _cinta(d, anillo, (245, 245, 245, 255), ancho)

    n = len(main)
    mx = sum(p[0] for p in centro) / n
    my = sum(p[1] for p in centro) / n

    def normal(i):
        a, b = centro[(i - 1) % n], centro[(i + 1) % n]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L
        # towards the OUTSIDE of the circuit
        if (centro[i][0] - mx) * nx + (centro[i][1] - my) * ny < 0:
            nx, ny = -nx, -ny
        return nx, ny, tx / L, ty / L

    # cuts: finish line (index 0) and each sector change
    cortes = [0] + [i for i in range(1, n) if main[i].sector != main[i - 1].sector]
    for i in cortes:
        nx, ny, _tx, _ty = normal(i)
        x, y = centro[i]
        L = ancho / 2 + borde + 1
        d.line([(x - nx * L, y - ny * L), (x + nx * L, y + ny * L)], fill=(20, 20, 24, 255),
               width=max(3, ancho // 4))

    # S1/S2/S3 labels halfway through each sector, on the outside
    fuente = ImageFont.truetype(FUENTE_ROTULOS, round(lado * 0.045))
    limites = cortes + [n]
    for k, (a, b) in enumerate(zip(limites, limites[1:]), start=1):
        if b - a < 3:
            continue
        i = (a + b) // 2
        nx, ny, _tx, _ty = normal(i)
        x, y = centro[i][0] + nx * lado * 0.075, centro[i][1] + ny * lado * 0.075
        d.text((x, y), f"S{k}", font=fuente, fill=(245, 245, 245, 255), anchor="mm",
               stroke_width=max(2, borde), stroke_fill=(20, 20, 24, 235))

    # arrow for the direction of travel, on the outside, a little after the finish line
    i = min(n - 1, max(2, n // 40))
    nx, ny, tx, ty = normal(i)
    x, y = centro[i][0] + nx * lado * 0.05, centro[i][1] + ny * lado * 0.05
    t = lado * 0.022
    d.polygon([(x + tx * t * 1.4, y + ty * t * 1.4), (x - tx * t + nx * t, y - ty * t + ny * t),
               (x - tx * t - nx * t, y - ty * t - ny * t)], fill=(150, 150, 150, 255))
    return im


def _cinta(d, puntos, color, ancho):
    """Thick line WITHOUT notches.

    ⚠️ `ImageDraw.line` with a large `width` over very close points (1,476 in the Charlotte by
    «13x», <1 px from each other) leaves wedge-shaped GAPS at the joints: the map ribbon came
    out with black teeth all along the edge. A circle of the same thickness at each vertex
    fills in the joints.
    """
    d.line(puntos, fill=color, width=ancho)
    r = ancho / 2
    for x, y in puntos:
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _logo_de_texto(titulo: str, destino: str) -> str:
    """256x128 DXT1 logo without mipmaps with the circuit's name, on two lines."""
    from PIL import Image, ImageDraw, ImageFont

    im = Image.new("RGB", (256, 128), (22, 24, 28))
    d = ImageDraw.Draw(im)
    palabras = titulo.upper().split()
    lineas = [" ".join(palabras[: (len(palabras) + 1) // 2]),
              " ".join(palabras[(len(palabras) + 1) // 2:])] if len(palabras) > 1 else [titulo.upper()]
    fuente = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    tam = 30
    while tam > 10:
        f = ImageFont.truetype(fuente, tam)
        if all(d.textlength(l, font=f) <= 236 for l in lineas if l):
            break
        tam -= 2
    alto = tam + 6
    y = (128 - alto * len([l for l in lineas if l])) // 2
    for l in lineas:
        if not l:
            continue
        w = d.textlength(l, font=f)
        d.text(((256 - w) / 2, y), l, font=f, fill=(235, 235, 235))
        y += alto
    tmp = destino.replace(".dds", "_tmp.png")
    im.save(tmp)
    ok, err = a_dds(tmp, destino, compresion="dxt1")
    os.remove(tmp)
    return f"tracklogos 256x128 with text {'✓' if ok else '✗ ' + err}"


def a_dds(png: str, dds: str, compresion: str = "dxt5", tamano=None, mipmaps=False):
    """Writes the DDS with the SAME format as the mods that work.

    `dds:mipmaps=0` is what matters IN THE UI IMAGES: without it ImageMagick adds a chain of
    10 and the game gets stuck loading. `convert` is what knows how to write DDS; PIL only
    reads.
    🔴 And the opposite for the CIRCUIT TEXTURES (`mipmaps=True`): without a chain they
    shimmer at a distance. Converted with the UI rule, 16 PNGs of the Charlotte by «13x» came
    out without mipmaps and the gate did not catch it.
    """
    cmd = [*_R.IM_CONVERT, png]
    if tamano:
        cmd += ["-resize", f"{tamano[0]}x{tamano[1]}!"]
    cmd += ["-define", f"dds:compression={compresion}"]
    if not mipmaps:
        cmd += ["-define", "dds:mipmaps=0"]
    cmd += [dds]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and not mipmaps:
        _sin_mipmaps(dds)
    return r.returncode == 0, (r.stderr or "").strip()


def poner_mipmaps(salida: str, nombre: str, minimo: int = 512) -> list:
    """Adds the mipmap chain to the circuit textures that do not carry it.

    They may come without it from the mod itself (`driver_face.dds`, from the pit crew of the
    Charlotte by «13x»). It is rewritten with the SAME compression type: DXT1 stays DXT1 (no
    alpha) and DXT3/DXT5 become DXT5, which keeps the alpha.
    Returns [(file, new mipmaps)]. Only those whose longer side is >= `minimo`.
    """
    import struct

    tex = os.path.join(salida, "Tracks", "textures", nombre)
    hechas = []
    if not os.path.isdir(tex):
        return hechas
    for f in sorted(os.listdir(tex)):
        if not f.lower().endswith(".dds"):
            continue
        ruta = os.path.join(tex, f)
        with open(ruta, "rb") as fh:
            cab = fh.read(128)
        if cab[:4] != b"DDS ":
            continue
        alto, ancho = struct.unpack_from("<II", cab, 12)
        mip = struct.unpack_from("<I", cab, 28)[0]
        cc = cab[84:88]
        if mip > 1 or max(ancho, alto) < minimo or cc not in (b"DXT1", b"DXT3", b"DXT5"):
            continue
        tmp = ruta + ".tmp.dds"
        ok, _err = a_dds(ruta, tmp, "dxt1" if cc == b"DXT1" else "dxt5", mipmaps=True)
        if ok:
            with open(tmp, "rb") as fh:
                nuevo = struct.unpack_from("<I", fh.read(32), 28)[0]
            os.replace(tmp, ruta)
            hechas.append((f, nuevo))
        elif os.path.exists(tmp):
            os.remove(tmp)
    return hechas


def _formato(dds: str) -> str:
    """The fourCC that actually got written, read from the file. Not the one requested."""
    import struct

    try:
        with open(dds, "rb") as fh:
            d = fh.read(92)
        return d[84:88].decode("ascii", "replace").strip() + " "
    except Exception:  # noqa: BLE001
        return ""


def _sin_mipmaps(dds: str):
    """Leaves the header EXACTLY like that of a mod that works.

    With `dds:mipmaps=0` ImageMagick no longer writes the chain —the file weighs the same as
    Enna's, to the byte— but it leaves `mipMapCount = 1` and the mipmap flags set. Enna
    carries `0` and `caps = 0x1000`. In a format bug no difference is left unexplained: it is
    copied.
    """
    import struct

    with open(dds, "r+b") as fh:
        d = bytearray(fh.read(128))
        flags = struct.unpack_from("<I", d, 8)[0]
        struct.pack_into("<I", d, 8, flags & ~0x20000)   # drop DDSD_MIPMAPCOUNT
        struct.pack_into("<I", d, 28, 0)                 # mipMapCount = 0
        struct.pack_into("<I", d, 108, 0x1000)           # caps = plain TEXTURE
        fh.seek(0)
        fh.write(d)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    aiw_path, gui = argv[1], argv[2]
    nombre = argv[argv.index("--nombre") + 1] if "--nombre" in argv else "Charlotte"
    render = argv[argv.index("--render") + 1] if "--render" in argv else None
    args_foto = argv[argv.index("--foto") + 1] if "--foto" in argv else None
    titulo = argv[argv.index("--titulo") + 1] if "--titulo" in argv else None

    aiw = A.parse(aiw_path)
    hechos = []

    # the selection-screen one: two-edge silhouette
    # `--estilo-reiza`: sectors, arrow and pits in red, like the official ones
    im = dibujar_reiza(aiw) if "--estilo-reiza" in argv else dibujar(aiw, LADO_3D, 5)
    destino = os.path.join(gui, "trackmaps3d", f"{nombre}.dds")
    if im is not None and os.path.isdir(os.path.dirname(destino)):
        tmp = destino.replace(".dds", "_tmp.png")
        im.save(tmp)
        ok, err = a_dds(tmp, destino)
        os.remove(tmp)
        hechos.append(f"trackmaps3d {LADO_3D}px {'✓' if ok else '✗ ' + err}")

    # the HUD one: ribbon + pits, and with BOTH NAMES
    hud = dibujar_hud(aiw)
    carpeta = os.path.join(gui, "trackmaps")
    if hud is not None and os.path.isdir(carpeta):
        tmp = os.path.join(carpeta, "_hud_tmp.png")
        hud.save(tmp)
        for fichero in (f"{nombre}.dds", f"map_{nombre}.dds"):
            ok, err = a_dds(tmp, os.path.join(carpeta, fichero))
            hechos.append(f"{fichero} {'✓' if ok else '✗ ' + err}")
        os.remove(tmp)

    # THE LOGO, cropped from the loading screen that the AMS1 pack itself carries.
    # AMS1 circuits carry a 1920x1080 `<track>_Loading.jpg` with the layout, the name and
    # the OFFICIAL LOGO at the top right. It is better material than any generated drawing,
    # and it comes with the circuit.
    if render and os.path.exists(render) and render.lower().endswith((".jpg", ".jpeg")):
        destino = os.path.join(gui, "tracklogos", f"{nombre}.dds")
        if os.path.isdir(os.path.dirname(destino)):
            try:
                from PIL import Image

                im = Image.open(render).convert("RGB")
                w, h = im.size
                # top-right corner, where the logo goes in the AMS1 template
                logo = im.crop((int(w * 0.76), int(h * 0.02), int(w * 0.99), int(h * 0.14)))
                tmp = destino.replace(".dds", "_tmp.png")
                logo.resize((256, 128), Image.LANCZOS).save(tmp)
                ok, err = a_dds(tmp, destino)
                os.remove(tmp)
                hechos.append(f"tracklogos 256x128 {'✓' if ok else '✗ ' + err}")
            except Exception as e:
                hechos.append(f"tracklogos ✗ {e}")

    # 🔴 THE FALLBACK LOGO. The crop above only runs if the loading screen is a `.jpg` (the
    # AMS1 `_Loading.jpg`). With Assetto Corsa it is not, the step was SKIPPED WITHOUT A WORD,
    # and the template's logo stayed: literally «MEADOWDALE 1963», 1000x1000 uncompressed and
    # with **10 mipmaps** — a UI DDS with mipmaps leaves loading stuck. Symptom: the circuit
    # hung for a while on load. The rule: if there is nothing to crop it from, one is
    # generated with the circuit's name; the sample's one NEVER stays.
    if not any(h.startswith("tracklogos") and "✓" in h for h in hechos):
        destino = os.path.join(gui, "tracklogos", f"{nombre}.dds")
        if os.path.isdir(os.path.dirname(destino)):
            try:
                hechos.append(_logo_de_texto(titulo or nombre, destino))
            except Exception as e:
                hechos.append(f"tracklogos ✗ {e}")

    # The circuit's PHOTO. In order: `--foto` (a real image of the venue), and if there is
    # none, the AMS1 loading screen.
    #
    # 🔴 Why `--foto` exists. Without it the photo is the AMS1 `_Loading.jpg` rescaled: it
    # carries the caption **«AUTOMOBILISTA · MOTORSPORTS SIMULATOR» at the bottom left** —the
    # previous game's brand, full screen every time it loads— and it draws a layout with the
    # oval PLUS an infield road course that this package does not have. And it is 1280x720
    # DXT1 when the three references use **1920x1080**.
    foto = args_foto or render
    if foto and os.path.exists(foto):
        destino = os.path.join(gui, "trackphotos", f"{nombre}.dds")
        if os.path.isdir(os.path.dirname(destino)):
            # 🔴 FORCED DXT1. When asked for DXT5, ImageMagick drops to DXT1 only if the image
            # has no alpha; Assetto Corsa's `preview.png` DOES have it and came out DXT5, outside
            # the recipe's format. A photo does not use alpha.
            ok, err = a_dds(foto, destino, compresion="dxt1", tamano=FOTO)
            # The format in the message is not assumed: it is read from the file that was written.
            hechos.append(f"trackphotos {FOTO[0]}x{FOTO[1]} {_formato(destino) if ok else ''}"
                          f"{'✓' if ok else '✗ ' + err}")

    print("images generated from the AIW: " + " · ".join(hechos))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


def convertir_texturas_no_dds(salida: str, nombre: str) -> dict:
    """Converts to DDS the textures that are not DDS and repoints the MTX files that name them.

    🔴 Why. When importing the WHOLE circuit, 3 `.TGA` textures turned up (`SCORETOWERBKG`,
    `RDGLOW`, `GRNGLOW`) referenced by 4 materials. The OMTT tutorial lists the formats the
    engine accepts and **TGA is not among them**: only DDS (DXT1/3/5, BC7, BC5U and
    uncompressed A8R8G8B8). A reference to a TGA gives no error: the mesh is left without a
    texture, or is simply not drawn.

    They are converted to DXT5 WITH mipmaps (they are circuit textures, not UI ones), and the
    path in the MTX files is rewritten. Returns what was converted and how many materials were
    repointed.
    """
    import re

    tex = os.path.join(salida, "Tracks", "textures", nombre)
    pista = os.path.join(salida, "Tracks", nombre)
    if not os.path.isdir(tex):
        return {"convertidas": [], "mtx": 0}

    convertidas = []
    for f in sorted(os.listdir(tex)):
        if f.lower().endswith(".dds"):
            continue
        origen = os.path.join(tex, f)
        if not os.path.isfile(origen):
            continue
        destino = os.path.splitext(origen)[0] + ".dds"
        ok, err = a_dds(origen, destino, mipmaps=True)
        if ok:
            os.remove(origen)
            convertidas.append((f, os.path.basename(destino)))

    tocados = 0
    if convertidas and os.path.isdir(pista):
        cambios = {v.lower(): d for v, d in convertidas}
        for f in os.listdir(pista):
            if not f.lower().endswith(".mtx"):
                continue
            ruta = os.path.join(pista, f)
            texto = original = open(ruta, encoding="utf-8", errors="ignore").read()
            for viejo, nuevo in cambios.items():
                texto = re.sub(re.escape(viejo), nuevo, texto, flags=re.I)
            if texto != original:
                open(ruta, "w", encoding="utf-8").write(texto)
                tocados += 1
    return {"convertidas": convertidas, "mtx": tocados}
