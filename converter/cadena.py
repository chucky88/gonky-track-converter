"""What is common to every conversion: launching processes and Blender, and the gates the pipelines share.

A gate is a function `(ctx) -> (ok, detalle)`: if one comes out red, `convertir_ac.py` does not
write the zip. The ones here do not depend on whether the track comes from Assetto Corsa or from
somewhere else; the AC-specific ones are in `convertir_ac.py`.
"""

import math
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import rutas as _R  # noqa: E402

TRABAJO = _R.TRABAJO
EJEMPLO = _R.EJEMPLO


def corre(cmd, timeout=6000):
    # ⏱ Every external tool reports how long it takes, to know what to parallelise before
    # touching anything.
    import time
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=AQUI)
    etiqueta = next((os.path.basename(c) for c in cmd if str(c).endswith(".py")), os.path.basename(str(cmd[0])))
    print(f"   ⏱ {etiqueta}: {time.time() - t0:.0f} s", flush=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def blender(guion, *args, timeout=6000):
    """🔴 Blender exits with **code 0 even when the script crashes** (measured).

    `construir_paquete.py` died with a `NameError` halfway through a function —a call to a
    function that had been renamed— and `blender -b` returned `rc=0`. The pipeline carried on, and
    the gates judged green **the package from the previous conversion**, which was still on disk:
    the CSM was three hours old and the GCL two. Two gates came out red because they were comparing
    files from different conversions, and the explanation was none of the ones they gave.
    It is the usual family of failure: the process says it went fine.

    So here the exit code is worthless: the output is checked for a `Traceback`.
    """
    rc, salida = corre(["blender", "-b", "--factory-startup", "--python",
                        os.path.join(AQUI, guion), "--", *args], timeout=timeout)
    if rc == 0 and "Traceback (most recent call last)" in salida:
        trozo = salida[salida.index("Traceback (most recent call last)"):][:900]
        return 1, salida + f"\n🔴 {guion} crashed but blender returned 0:\n{trozo}"
    return rc, salida


def puerta_parrilla(ctx):
    """🔴 32 is AMS2's ceiling. With 43 the game closes with a BugSplat crash."""
    import aiw_read as A

    n = ctx["puestos"]
    return n <= A.TECHO_PARRILLA, f"{n} slots (game limit: {A.TECHO_PARRILLA})"


def puerta_rumbo(ctx):
    """🔴 The grid facing backwards: the race starts in the opposite direction (exactly 180.0°). And
    a backwards grid loads, starts and raises no error. It has happened twice."""
    import aiw_read as A

    e = A.error_de_rumbo(ctx["aiw_obj"])
    return e < 5.0, f"worst heading deviation {e:.1f}°"


def puerta_suelo(ctx):
    """🔴 The collision faces pointed downwards: you can see the track, the car goes through it.
    22,726 out of 22,726. And every check was green."""
    import verificar_fisica as V

    r = V.normales_del_suelo(ctx["obj"])
    return r["arriba"] > r["abajo"], f"{r['arriba']} faces up / {r['abajo']} down"


def puerta_texturas(ctx):
    """Checked in both directions. Material → file catches the missing ones; file → material
    uncovered 17 orphans and 179 MB of dead weight."""
    import re

    pista = os.path.join(ctx["pack"], "Tracks", ctx["nombre"])
    tex = os.path.join(ctx["pack"], "Tracks", "textures", ctx["nombre"])
    citadas = set()
    for f in os.listdir(pista):
        if f.lower().endswith(".mtx"):
            t = open(os.path.join(pista, f), encoding="utf-8", errors="ignore").read()
            for m in re.finditer(r'v="([^"]*\.(?:dds|tga))"', t, re.I):
                citadas.add(m.group(1).replace("\\", "/").split("/")[-1].lower())
    reales = {f.lower(): f for f in os.listdir(tex)} if os.path.isdir(tex) else {}
    hay = set(reales)
    faltan = citadas - hay
    sobran = hay - citadas

    # 🔴 And a third question: the texture existing is not enough, it has to carry **mipmaps**.
    # Without them, a texture tiled every 10 m SHIMMERS at a distance, and tightening the UVs
    # multiplies the problem. Official track textures carry them (mip 9-11; GJ Kartway 12-14);
    # some hand-generated textures came out with **mip=1**.
    # ⚠️ Not to be confused with the "zero mipmaps" rule: that one is for the INTERFACE IMAGES —the
    # map and the photo, where a DDS with mipmaps leaves the track loading forever—, not for the
    # track textures.
    import struct as _st

    sin_mip = []
    for f in sorted(hay):
        if f not in citadas:
            continue
        # 🔴 The REAL name is opened, not the lowercased one: on Linux `N19_Charlotte_Toyota.dds`
        # cannot be opened as `n19_charlotte_toyota.dds`, the exception was swallowed and the
        # texture was NOT checked. Of 17 without mipmaps in the Charlotte by "13x", the gate saw 1:
        # the only one whose name was already lowercase.
        with open(os.path.join(tex, reales[f]), "rb") as fh:
            cab = fh.read(32)
        alto, ancho = _st.unpack_from("<II", cab, 12)
        mip = _st.unpack_from("<I", cab, 28)[0]
        # only required for large ones: a 128x128 texture gains nothing and some inherited ones
        # are like that. By the LONGER side: a 1024x256 banner shimmers too.
        if mip <= 1 and max(ancho, alto) >= 512:
            sin_mip.append(f)

    ok = not faltan and not sobran and not sin_mip
    detalle = f"{len(citadas)} referenced · {len(faltan)} without a file · {len(sobran)} orphans"
    if sin_mip:
        detalle += (f" · 🔴 {len(sin_mip)} WITHOUT MIPMAPS ({', '.join(sin_mip[:3])}): "
                    f"they will flicker at distance")
    else:
        detalle += " · mipmaps ✅"
    return ok, detalle


def puerta_luces(ctx):
    """🔴 An EMPTY `_lights.sgx` crashes AMS2, even though it looks harmless: no reference track
    ships an empty one (Mid-Ohio 2, GJ Kartway 6, the example 21)."""
    ruta = os.path.join(ctx["pack"], "Tracks", ctx["nombre"], f"{ctx['nombre']}_lights.sgx")
    if not os.path.exists(ruta):
        return False, "there is no _lights.sgx"
    txt = open(ruta, encoding="utf-8", errors="ignore").read()
    n = txt.count("<LIGHT")
    if n == 0:
        return False, "🔴 _lights.sgx EMPTY — AMS2 won't load"
    # And the other half: 21 floodlights at ground level in the infield raise no error either.
    # They are Meadowdale's (the template), and they passed this gate back when it only counted
    # lights. The generated ones come from the track's towers, so they have to be HIGH UP; if not
    # a single one is up high, the borrowed file is still there.
    import re as _re

    alturas = [float(m.split()[1]) for m in _re.findall(r'Position="([^"]+)"', txt)]
    if alturas and max(alturas) < 5.0:
        return False, (f"🔴 all {n} lights are below 5 m "
                       f"(the highest, {max(alturas):.1f} m): it's the INHERITED file")

    # 🔴 And the third way of breaking it, which crashes AMS2 on load: the header declares
    # `NumPartitions="1"` and the body has NO `<PARTITION_ID>` at all. The engine goes looking for
    # the partition it was promised and it is not there. Mid-Ohio closes it with its bounding box
    # and the list of children.
    # It is the same family as the empty file: **a header that promises what the body does not
    # have**. Counting lights does not see it — 12 lights without a partition are still 12 lights.
    declaradas = int((_re.search(r'NumPartitions="(\d+)"', txt) or [0, 0])[1] or 0) \
        if _re.search(r'NumPartitions="(\d+)"', txt) else 0
    presentes = txt.count("<PARTITION_ID")
    if declaradas != presentes:
        return False, (f"🔴 declares NumPartitions={declaradas} and has {presentes} "
                       f"<PARTITION_ID>: AMS2 won't load")
    hijos = _re.search(r'<CHILD_OBJS IDs="([^"]*)"', txt)
    sueltas = n - len((hijos.group(1) or "").split()) if hijos else n
    if sueltas:
        return False, f"🔴 {sueltas} of the {n} lights are not in the partition's CHILD_OBJS"
    return True, f"{n} lights · the highest at {max(alturas):.0f} m · partition ✅"


def puerta_globales(ctx):
    """🔴 The template carries ENGINE files (`dynamic.sys.xml`, `autograss.bmt`…) and shipping them
    again overwrites the game's. The worst one declared TWO dynamic objects where the game has
    dozens: the track would not load from cold."""
    import empaquetar as E

    malos = []
    for base, _d, fs in os.walk(os.path.join(ctx["pack"], "Tracks", "_data")):
        for f in fs:
            if not E.es_del_circuito(f, ctx["nombre"]):
                malos.append(f)
    for c in E.CARPETAS_GLOBALES:
        if os.path.isdir(os.path.join(ctx["pack"], c)):
            malos.append(c + "/")
    return not malos, f"{len(malos)} game files in the package" + (f": {malos[:3]}" if malos else "")


def puerta_heredados(ctx):
    """A file identical to the example's with its name changed looks like finished work and is
    not. They are listed; they do not block, because some are legitimate template files."""
    import hashlib

    def md5(p):
        return hashlib.md5(open(p, "rb").read()).hexdigest()

    ej = {}
    for base, _d, fs in os.walk(os.path.join(EJEMPLO, "Automobilista 2")):
        for f in fs:
            try:
                ej.setdefault(md5(os.path.join(base, f)), os.path.join(base, f))
            except OSError:
                pass
    iguales = []
    for base, _d, fs in os.walk(ctx["pack"]):
        for f in fs:
            p = os.path.join(base, f)
            try:
                if md5(p) in ej:
                    iguales.append(os.path.relpath(p, ctx["pack"]))
            except OSError:
                pass
    ctx["heredados"] = iguales
    return True, f"{len(iguales)} files are still the example's (informative)"


def puerta_suelo_en_el_gcl(ctx):
    """🔴 The meshes AMS1 marks as GROUND have to contribute to the `.gcl`.

    Measured over the 32 tracks of an AMS1 pack: at **Gateway 73 of its 127 ground meshes** and
    at **Iowa 47 of 77** carry no material from the "asfalto" (asphalt) family, so more than half
    of the drivable surface was left **outside the track limits** — and nothing said so. The most
    common cause: the racing asphalt is named `RDH1`, `RDM1`, `RDL1`… with a digit instead of a
    letter (Pocono, Marty, Atlanta, Kentucky, Mansfield, Iowa, Talladega) and did not match
    `RDHI`/`RDMID`/`RDLOW`.

    `puerta_espacios` compares the `.gcl` with the physics, so **a small, consistent `.gcl` passes
    green**. This one looks at something else: how much of the track the circuit declares
    drivable ends up inside.
    """
    import math

    import gcl_read as GCL

    x0, x1, _y0, _y1, z0, z1 = GCL.caja(ctx["gcl"])
    area_gcl = abs(x1 - x0) * abs(z1 - z0)
    aiw = ctx["aiw_obj"]
    pts = [w.pos for w in aiw.main_path]
    ancho = sorted(min(w.width[0], w.width[1]) for w in aiw.main_path
                   if getattr(w, "width", None) and len(w.width) >= 2)
    semi = ancho[len(ancho) // 2] if ancho else 6.0
    vuelta = sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][2] - pts[i - 1][2])
                 for i in range(1, len(pts)))
    minimo = vuelta * semi * 2 * 0.6      # at least 60 % of the track ribbon
    tri = GCL.cabecera(ctx["gcl"])["triangulos"]
    return area_gcl > minimo and tri > 500, \
        f"{tri} triangles · {abs(x1 - x0):.0f}x{abs(z1 - z0):.0f} m box for a {vuelta:.0f} m lap"


def puerta_interfaz(ctx):
    """🔴 An interface image with mipmaps leaves the track LOADING forever. And another measured
    case: Mountain Peak's logo was the template's —"MEADOWDALE 1963", 1000x1000 uncompressed and
    with 10 mipmaps— because the step that generates it was silently skipped if the loading screen
    was not a `.jpg`; loading got stuck for a while.

    The `heredados` gate already listed it ("14 files", versus 11 for Charlotte), but it is
    informational and easy not to look at. This one is NOT: it checks what the game loads first.
    """
    import hashlib
    import struct

    gui = os.path.join(ctx["pack"], "GUI")
    ejemplo = set()
    for base, _d, fs in os.walk(os.path.join(EJEMPLO, "Automobilista 2", "GUI")):
        for f in fs:
            try:
                ejemplo.add(hashlib.md5(open(os.path.join(base, f), "rb").read()).hexdigest())
            except OSError:
                pass
    malas, vistas = [], 0
    for base, _d, fs in os.walk(gui):
        for f in fs:
            if not f.lower().endswith(".dds"):
                continue
            ruta = os.path.join(base, f)
            rel = os.path.relpath(ruta, gui)
            d = open(ruta, "rb").read()
            vistas += 1
            mip = struct.unpack_from("<I", d, 28)[0]
            fourcc = d[84:88]
            if mip > 1:
                malas.append(f"{rel} with {mip} mipmaps")
            if fourcc not in (b"DXT1", b"DXT5"):
                malas.append(f"{rel} uncompressed ({fourcc!r})")
            if hashlib.md5(d).hexdigest() in ejemplo:
                malas.append(f"{rel} is the EXAMPLE's")
    if not vistas:
        return False, "no UI images"
    return not malas, (f"{vistas} images: no mipmaps, compressed and the track's own" if not malas
                       else "🔴 " + " · ".join(malas))


def puerta_altura_salida(ctx):
    """🔴 Every AIW start position has to sit about **3 m** above the collision.

    That is Reiza's figure at Mid-Ohio (grid, TELEPORT and pits: 2.96-3.04 m). At 7.5 cm the
    Charlotte by "13x" got stuck on the loading screen and Mountain Peak only loaded sometimes; at
    2.1 m it loaded first time. See `kn5_to_blender.ALTURA_SALIDA`. ⚠️ An AMS1 track that keeps its
    original AIW (8 cm) comes out red here, and that is correct.
    """
    import re
    import inclinar_aiw as I

    if not os.path.exists(ctx.get("obj", "")) or not os.path.exists(ctx.get("aiw_out", "")):
        return False, "the collision or the AIW is missing"
    suelo = I.Suelo(ctx["obj"])
    texto = open(ctx["aiw_out"], encoding="latin-1").read()
    ps = [tuple(map(float, m)) for m in
          re.findall(r"^Pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)", texto, re.M)]
    alturas, sin = [], 0
    for x, y, z in ps:
        g = suelo.altura(x, z, y)
        if g is None:
            sin += 1
        else:
            alturas.append(y - g)
    if not alturas:
        return False, f"{len(ps)} positions and none with ground underneath"
    malas = [a for a in alturas if not 2.5 <= a <= 3.5]
    # 🔴 and the PIT boxes (`PitPos`), which this gate did not check: they came out at 3 m and the
    # mechanics floated. Daytona: 0.05 m. Only in the AC pipeline, where
    # `kn5_to_blender.ALTURA_BOXES` places them; the AMS1 one carries its original AIW.
    boxes = []
    if ctx.get("trazado_ac"):
        for x, y, z in [tuple(map(float, m)) for m in
                        re.findall(r"^PitPos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)", texto, re.M)]:
            g = suelo.altura(x, z, y)
            if g is not None:
                boxes.append(y - g)
        malas += [b for b in boxes if not -0.02 <= b <= 0.3]
    alturas.sort()
    return not malas and not sin, (f"{len(ps)} positions · above the collision: median "
                                   f"{alturas[len(alturas) // 2]:.2f} m, max {alturas[-1]:.2f}"
                                   + (f" · pits {len(boxes)}: max {max(boxes):.2f} m" if boxes else "")
                                   + (f" · 🔴 {len(malas)} outside 2.5–3.5 m" if malas else "")
                                   + (f" · 🔴 {sin} without ground" if sin else ""))


def puerta_limite_boxes(ctx):
    """🔴 The TRD's pit speed limit has to be a real one, not the template's 240.

    Without this gate, Mountain Peak came out with `PitSpeedLimit_HighKPH = 240`: the AC pipeline
    did not touch it and Meadowdale's value stayed. No stock track goes above 100 (Mid-Ohio 80,
    AMS1's Charlotte 100). Generous cap: 150.
    """
    import re

    n = ctx["nombre"]
    ruta = os.path.join(ctx["pack"], "Tracks", n, f"{n}.trd")
    if not os.path.exists(ruta):
        return False, "there is no TRD"
    m = re.search(r'<prop name="PitSpeedLimit_HighKPH" data="([^"]*)"', open(ruta, encoding="utf-8", errors="ignore").read())
    if not m:
        return False, "the TRD doesn't declare PitSpeedLimit_HighKPH"
    v = float(m.group(1))
    return 30 <= v <= 150, f"{v:.0f} km/h" + ("" if v <= 150 else " — it's the TEMPLATE's (pass --pit-limiter)")


def puerta_identidad(ctx):
    """🔴 The TRD has to say WHICH track it is: otherwise the game loads another scene.

    Mountain Peak came out with `ScenegraphFile = meadowdale.sgx` and
    `ShortTrackName = Meadowdale_Raceway`: it did not load, and the images came out blank because
    the game looks them up by the short name. All the other gates, green.

    The `heredados` gate could not see it: it compares the WHOLE file with the example's, and a
    half-patched TRD is no longer identical… even though it still carries the example's identity.
    And this gate does NOT import `construir_paquete.identidad_trd`, on purpose: a check that uses
    the same list as the code it checks always comes out green.
    """
    import re

    n = ctx["nombre"]
    ruta = os.path.join(ctx["pack"], "Tracks", n, f"{n}.trd")
    if not os.path.exists(ruta):
        return False, "there is no TRD"
    texto = open(ruta, encoding="utf-8", errors="ignore").read()
    props = dict(re.findall(r'<prop name="([^"]+)" data="([^"]*)"', texto))
    # Several layouts of one track (`--group`/`--variant`): the group and the variant are the
    # REQUESTED ones, not the name; the rest of the identity is still the name.
    esperado = {"Name": n, "ShortTrackName": n, "Track Group": ctx.get("grupo") or n,
                "Track_Variation": ctx.get("variante") or n, "ScenegraphFile": f"{n}.sgx"}
    mal = [f"{k}={props.get(k)!r}" for k, v in esperado.items() if props.get(k, "").lower() != v.lower()]
    if "meadowdale" in texto.lower():
        mal.append("the TRD still mentions Meadowdale")
    if not os.path.exists(os.path.join(ctx["pack"], "Tracks", n, props.get("ScenegraphFile", "-"))):
        mal.append(f"the scenery it asks for ({props.get('ScenegraphFile')}) is not in the package")
    return not mal, (f"the TRD is for «{n}» and its scenery exists" if not mal
                     else "🔴 " + " · ".join(mal))


def inclinar_perp(ctx):
    """Puts the banking back into the exported AIW (OMTT flattens it). See `inclinar_aiw.py`."""
    import inclinar_aiw as I
    texto = open(ctx["aiw_out"], encoding="latin-1").read()
    nuevo, ang, sin = I.inclinar(texto, I.Suelo(ctx["obj"]))
    open(ctx["aiw_out"], "w", encoding="latin-1").write(nuevo)
    return len(ang), sin


def _peralte(aiw, estados_de=None):
    """(median in turns, median on straights) of the tilt of `wp_perp`, in degrees."""
    import aiw_read as A
    mp = aiw.main_path
    _t, est, _u = A.curvas_adaptativo(mp)
    c, r = [], []
    for w, e in zip(mp, est):
        n = math.sqrt(sum(x * x for x in w.perp)) or 1
        g = math.degrees(math.asin(max(-1, min(1, w.perp[1] / n))))
        (c if e != A.STATE_STRAIGHT else r).append(g)
    c.sort(); r.sort()
    return (c[len(c) // 2] if c else 0.0), (r[len(r) // 2] if r else 0.0)


def puerta_moduladores(ctx):
    """🔴 In the ground shader, the MIDDLE layer and the DETAIL layer are GREY modulators.

    Reiza's recipe (example project): `GrassDynamic_Albedo_BWHC` in both, saturation 0.00 and
    luminance 0.51; the colour goes only in the wide layer. With COLOURED grass in the middle and
    detail layers, Mountain Peak's grass came out BLACK: green × green.
    """
    import re
    import subprocess
    import colorsys
    from PIL import Image

    pista = os.path.join(ctx["pack"], "Tracks", ctx["nombre"])
    tex = os.path.join(ctx["pack"], "Tracks", "textures", ctx["nombre"])
    cache, malos, vistos = {}, [], 0
    for f in sorted(os.listdir(pista)):
        if not f.lower().endswith(".mtx"):
            continue
        t = open(os.path.join(pista, f), encoding="utf-8", errors="ignore").read()
        if "new_ground" not in t:
            continue
        for capa in ("middleDiffuseTexture", "detailDiffuseTexture"):
            m = re.search(r'name="' + capa + r'".*?<value v="([^"]*)"', t, re.S)
            if not m or not m.group(1):
                continue
            n = os.path.basename(m.group(1).replace("\\", "/"))
            if n not in cache:
                ruta = os.path.join(tex, n)
                if not os.path.exists(ruta):
                    cache[n] = None
                else:
                    tmp = "/tmp/_modulador.png"
                    subprocess.run([*_R.IM_CONVERT, ruta, "-resize", "128x128", tmp], capture_output=True)
                    px = list(Image.open(tmp).convert("RGB").getdata())
                    sat = sum(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[1] for r, g, b in px) / len(px)
                    lum = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in px) / len(px) / 255
                    cache[n] = (sat, lum)
            vistos += 1
            v = cache[n]
            if v and (v[0] > 0.08 or not 0.35 < v[1] < 0.65):
                malos.append(f"{f[:-4]}.{capa[:6]}={n} (sat {v[0]:.2f}, lum {v[1]:.2f})")
    return not malos, (f"{vistos} modulator layers, all grey and centred on 0.5" if not malos
                       else "🔴 " + " · ".join(malos[:4]) + (f" · and {len(malos) - 4} more" if len(malos) > 4 else ""))
