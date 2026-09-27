"""Packs the circuit with TrackPacker, and FIRST sets aside whatever does not belong to it.

    python3 empaquetar.py <pack folder> [--nombre charlotte]

🔴 Why it exists. The package is built from OMTT's SAMPLE project (Meadowdale), and that
sample carries —so that it can work on its own— its own copy of several **GLOBAL engine**
files, not circuit files. Copying the whole template re-ships them, and on install **they
overwrite the game's own**.

The worst one, by far:

    Tracks/_data/dynamic/physics/dynamic.sys.xml

which is **the global declaration of the dynamic objects** of AMS2 (cones, tyre stacks,
barriers…). The sample's copy declares **two**: the two cones the sample uses. Shipping it
replaces the game's entire list with a two-entry stub.

The symptom it produces: Charlotte does not load cold; you load COTA, go back to Charlotte
and then it does load. Cold, the stub wins and the loader keeps waiting for something that
is no longer declared; if another circuit was loaded before, the engine has already
resolved the real globals and Charlotte gets in.

**Mid-Ohio —the circuit by the toolkit's own author— ships NOT ONE of those files.**
That is the reference: under `Tracks/_data/` only files **named after the circuit** go in.

⚠️ The same symptom can be read the other way round: adding `render/` and `effects/`
believing that global resources are missing. They were not missing, **they were surplus**.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rutas as _R  # noqa: E402
PACKER = _R.PACKER
EJEMPLO_DINAMICOS = os.path.join(_R.EJEMPLO, "Automobilista 2", "Tracks", "_data", "dynamic", "physics")

# Sample folders that belong to the ENGINE, not to the circuit. Removed entirely.
CARPETAS_GLOBALES = ("render", "effects")

# Under these, only what is named after the circuit survives.
ZONAS_COMPARTIDAS = (
    os.path.join("Tracks", "_data"),
    os.path.join("Tracks", "textures", "_data"),
)


def apartar_globales(pack_dir, nombre):
    """Takes out of the pack whatever belongs to the game. Returns the paths set aside.

    Nothing is deleted: it is moved to `globales-retirados/` alongside, which is reversible
    and lets you see what the template carried.
    """
    destino_raiz = os.path.join(os.path.dirname(pack_dir), "globales-retirados")
    apartados = []

    def apartar(origen):
        rel = os.path.relpath(origen, pack_dir)
        destino = os.path.join(destino_raiz, rel)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.move(origen, destino)
        apartados.append(rel.replace(os.sep, "/"))

    for carpeta in CARPETAS_GLOBALES:
        raiz = os.path.join(pack_dir, carpeta)
        if not os.path.isdir(raiz):
            continue
        for base, _dirs, ficheros in os.walk(raiz):
            for f in sorted(ficheros):
                apartar(os.path.join(base, f))

    for zona in ZONAS_COMPARTIDAS:
        raiz = os.path.join(pack_dir, zona)
        if not os.path.isdir(raiz):
            continue
        for base, _dirs, ficheros in os.walk(raiz):
            for f in sorted(ficheros):
                if es_del_circuito(f, nombre):
                    continue
                apartar(os.path.join(base, f))

    # 🔴 The SAMPLE's `env.xml`. Symptom: the Charlotte by «13x» got stuck loading, and
    # Mountain Peak only loaded if another circuit had been loaded first. The THREE packages
    # tested carried a `<track>.env.xml` byte-for-byte identical to Meadowdale's, which places
    # 6 `cone_loda` at Meadowdale's coordinates. That object is only declared by the
    # sample's `dynamic.sys.xml`, which is already set aside above: on load the circuit asked
    # for an object that does not exist. Mid-Ohio uses `dyn_cone_e1_clean_loda` (from the
    # game) and GJ Kartway carries no `env.xml`: we do it like GJ.
    import hashlib

    ejemplo_env = os.path.join(EJEMPLO_DINAMICOS, "Meadowdale.env.xml")
    env = os.path.join(pack_dir, "Tracks", "_data", "dynamic", "physics", f"{nombre}.env.xml")
    if os.path.exists(env) and os.path.exists(ejemplo_env):
        md5 = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()   # noqa: E731
        if md5(env) == md5(ejemplo_env):
            apartar(env)

    return apartados


def es_del_circuito(fichero, nombre):
    """`charlotte.aiw` yes; `dynamic.sys.xml` or `CONE.mtx`, no."""
    return os.path.splitext(fichero)[0].lower().split(".")[0] == nombre.lower()


def empaquetar(pack_dir, nombre):
    r = subprocess.run(
        [sys.executable, PACKER, pack_dir, "--track-name", nombre, "--quiet"],
        capture_output=True, text=True, cwd=os.path.dirname(PACKER), timeout=3600,
    )
    zip_path = os.path.join(os.path.dirname(pack_dir.rstrip("/")), f"{nombre.lower()}.zip")
    if not os.path.exists(zip_path):
        return None, (r.stdout + r.stderr)[-800:]
    return zip_path, None


# 🔴 What goes LOOSE and what goes only INSIDE the pak. Measured in game, one change per build:
#
#   1. everything loose that was already inside the paks (textures, physics, AIW, LiveTrack)
#      REMOVED, `.mtx` removed too → the cars sit on the grid (the physics inside `_Physics.bff`
#      works) but **the track is not drawn**: cars floating in black;
#   2. the same with the loose `.mtx` put back → the track is drawn, identical to before.
#
# So the only loose files that matter are the `.mtx`. TrackPacker writes each material TWICE into
# the pak, `.mtx` and `.bmt`, and OMTT's docs say «MTX files are used with LOOSE content and do NOT
# work with packed content; with BMT files it is the other way round». A working reference that
# packs everything (a PC2-style track made with the same toolkit) carries only `.bmt` in its pak
# and nothing loose but the `.trd` and `GUI/`.
#
# ⚠️ Nobody puts loose `.bmt` files there: `TrackPacker` generates them IN THE source FOLDER when
# converting MTX→BMT, so the second packing of that same folder takes them along as sources.
#
# 🪤 An earlier build that «fell through the ground» was blamed on the missing loose physics, and
# for weeks every package shipped it twice. It was something else: build 1 above drives fine.
#
# TrackPacker leaves two files OUT of the pak; those have to go loose. All these files carry the
# circuit's name, so they do not overwrite anybody's files.
def no_empaquetados(nombre):
    """What TrackPacker does NOT put into the pak (reference tracks carry it inside)."""
    return [
        f"Tracks/_data/tracklights/{nombre}.xml",
        f"Tracks/_data/dynamic/physics/{nombre}.env.xml",
    ]


def fisica(nombre):
    """What the car needs to have ground under it, AI and timing: it must be INSIDE a pak."""
    return [
        f"Tracks/{nombre}/physics/{nombre}.csm",
        f"Tracks/{nombre}/physics/dynamic_collisions.xml",
        f"Tracks/{nombre}/physics/object_properties.xml",
        f"Tracks/{nombre}/physics/triggers.xml",
        f"Tracks/{nombre}/track_cut/{nombre}.gcl",
        f"Tracks/_data/aiw/{nombre}.aiw",
        f"Tracks/_data/livetrack/{nombre}.mrdf",
    ]


def añadir_no_empaquetados(zip_path, pack_dir, nombre):
    """The files TrackPacker left out, loose. Both are optional (GJ Kartway has no `env.xml`)."""
    dentro = set(zipfile.ZipFile(zip_path).namelist())
    añadidos = []
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as z:
        for rel in no_empaquetados(nombre):
            origen = os.path.join(pack_dir, *rel.split("/"))
            destino = f"Automobilista 2/{rel}"
            if os.path.exists(origen) and destino not in dentro:
                z.write(origen, destino)
                añadidos.append(rel)
    return añadidos


SUELTOS_PERMITIDOS = (".mtx", ".trd")


def _en_los_paks(z):
    """{relative path in lowercase: md5} of everything inside the zip's `.bff` files."""
    import io
    import bff_read as B
    dentro = {}
    for n in z.namelist():
        if n.lower().endswith(".bff"):
            dentro.update(B.contenido(io.BytesIO(z.read(n))))
    return dentro


def _rel(n):
    return n[len("Automobilista 2/"):].lower() if n.startswith("Automobilista 2/") else None


def limpiar_sueltos(zip_path, nombre):
    """Drops every loose file under `Tracks/` that is ALREADY inside a pak with the same content,
    except the `.mtx`/`.trd` and what TrackPacker leaves out. Returns (removed, loose not in any pak):
    a loose copy is only dropped once the pak is proven to hold it, never on the name alone."""
    import hashlib
    guardar = {f"Automobilista 2/{r}" for r in no_empaquetados(nombre)}
    z = zipfile.ZipFile(zip_path)
    dentro = _en_los_paks(z)
    fuera, huerfanos = [], []
    for n in z.namelist():
        if (not n.startswith("Automobilista 2/Tracks/") or n.endswith("/") or n in guardar
                or n.lower().endswith(SUELTOS_PERMITIDOS)):
            continue
        if dentro.get(_rel(n)) == hashlib.md5(z.read(n)).hexdigest():
            fuera.append(n)
        else:
            huerfanos.append(n)
    if not fuera:
        z.close()
        return [], huerfanos
    tmp = tempfile.mktemp(suffix=".zip")
    quitar = set(fuera)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as nuevo:
        for item in z.infolist():
            if item.filename not in quitar:
                nuevo.writestr(item, z.read(item.filename))
    z.close()
    shutil.move(tmp, zip_path)
    return fuera, huerfanos


def comprobar(zip_path, nombre):
    """The zip must look like a working reference: paks with the physics INSIDE, few loose files
    and NOTHING global."""
    z = zipfile.ZipFile(zip_path)
    nombres = [n for n in z.namelist() if not n.endswith("/")]
    paks = [n for n in nombres if "/Pakfiles/Tracks/" in n and n.endswith(".bff")]
    sueltos = [n for n in nombres if n.startswith("Automobilista 2/Tracks/")]
    guardar = {f"Automobilista 2/{r}" for r in no_empaquetados(nombre)}
    malos = [n for n in sueltos if n not in guardar and not n.lower().endswith(SUELTOS_PERMITIDOS)]
    dentro = _en_los_paks(z)
    falta_fisica = [r for r in fisica(nombre) if r.lower() not in dentro]
    globales = [
        n for n in nombres
        if any(f"/{c}/" in n for c in CARPETAS_GLOBALES)
        or ("/Tracks/_data/" in n and not es_del_circuito(os.path.basename(n), nombre))
    ]
    if not paks:
        return False, "🔴 there is no .bff at all: the track has no content"
    if malos:
        return False, (f"🔴 {len(malos)} loose files are not inside any pak "
                       f"(e.g. {', '.join(x.split('/')[-1] for x in malos[:3])})")
    if falta_fisica:
        return False, ("🔴 physics missing from the paks: " + ", ".join(os.path.basename(x) for x in falta_fisica)
                       + " — the car will fall into the void")
    if globales:
        return False, (f"🔴 the package overwrites {len(globales)} GAME files: "
                       f"{', '.join(globales[:4])}")
    return True, (f"✅ {len(paks)} paks with the physics inside · {len(sueltos)} loose "
                  f"(.mtx/.trd + {len([n for n in sueltos if n in guardar])} not packed by TrackPacker) "
                  f"· 0 global engine files")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    pack_dir = argv[1].rstrip("/")
    nombre = argv[argv.index("--nombre") + 1] if "--nombre" in argv else "charlotte"

    apartados = apartar_globales(pack_dir, nombre)
    print(f"GAME files set aside from the pack: {len(apartados)}"
          + (f"\n   " + "\n   ".join(apartados) if apartados else " — it was already clean"))

    zip_path, err = empaquetar(pack_dir, nombre)
    if not zip_path:
        print(f"🔴 TrackPacker failed:\n{err}")
        return 1
    print(f"packed: {zip_path} ({os.path.getsize(zip_path) // 1024 // 1024} MB)")

    puestos = añadir_no_empaquetados(zip_path, pack_dir, nombre)
    print(f"loose, because TrackPacker leaves them out of the pak: {len(puestos)}")

    sobran, huerfanos = limpiar_sueltos(zip_path, nombre)
    print(f"loose copies removed (they are inside the pak, same content): {len(sobran)}"
          + (f" — {', '.join(sorted({os.path.splitext(x)[1] for x in sobran}))}" if sobran else "")
          + (f" · ⚠️ {len(huerfanos)} loose files are NOT in any pak and stay" if huerfanos else ""))

    ok, detalle = comprobar(zip_path, nombre)
    print(detalle)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
