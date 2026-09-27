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


# 🔴 What goes LOOSE in an OMTT package, measured in **Mid-Ohio**: only `.mtx` and the
# `.trd`, plus the textures. The documentation says so: «MTX files are used with LOOSE
# content and do NOT work with packed content; with BMT files it is the other way round».
# Shipping both forms of the same material is asking the engine to choose.
#
# ⚠️ Nobody puts loose `.bmt` files there: `TrackPacker` generates them IN THE source
# FOLDER when converting MTX→BMT, so the second packing of that same folder takes them
# along as if they were source files.
# 🔴 The PHYSICS also goes LOOSE, in addition to inside the pak.
#
# With Beezer's trick the game reads the `Tracks/` folder **from disk**, not from the pak:
# that is why the loose `.mtx` files are the ones that count. The same happens with the
# collision. Measured in tests: with the loose `.csm` **you could drive**; without it, the
# car starts **spinning in the air** — which is falling with no ground.
#
# ⚠️ Mid-Ohio does not ship it, but that does not mean «nothing loose»: Mid-Ohio shows
# **what NOT to ship of what belongs to the game** (the globals). Global and packed are two
# different questions.
#
# All these files carry the circuit's name, so they do not overwrite anybody's files.
def rutas_fisica(nombre):
    return [
        f"Tracks/{nombre}/physics/{nombre}.csm",
        f"Tracks/{nombre}/physics/dynamic_collisions.xml",
        f"Tracks/{nombre}/physics/object_properties.xml",
        f"Tracks/{nombre}/physics/triggers.xml",
        f"Tracks/{nombre}/track_cut/{nombre}.gcl",
        f"Tracks/_data/aiw/{nombre}.aiw",
        f"Tracks/_data/livetrack/{nombre}.mrdf",
        f"Tracks/_data/dynamic/physics/{nombre}.env.xml",
        # ⚠️ TrackPacker does NOT copy `_data/tracklights` into the pak (nor `crowds`): Enna and
        # Daytona carry it inside; here it goes loose, like the physics, which is already read that way.
        f"Tracks/_data/tracklights/{nombre}.xml",
    ]


def opcional(rel):
    """`env.xml` is OPTIONAL: GJ Kartway (Reiza) does not carry one, and the one that came from
    the template was the sample's, asking for cones that do not exist (see `apartar_globales`).
    If present, it goes loose."""
    return rel.endswith(".env.xml") or "/tracklights/" in rel


def añadir_fisica_suelta(zip_path, pack_dir, nombre):
    dentro = set(zipfile.ZipFile(zip_path).namelist())
    añadidos, faltan = [], []
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as z:
        for rel in rutas_fisica(nombre):
            origen = os.path.join(pack_dir, *rel.split("/"))
            destino = f"Automobilista 2/{rel}"
            if not os.path.exists(origen):
                if not opcional(rel):
                    faltan.append(rel)
                continue
            if destino in dentro:
                continue
            z.write(origen, destino)
            añadidos.append(rel)
    return añadidos, faltan


SUELTOS_PERMITIDOS = (".mtx", ".trd", ".dds", ".txt")


def limpiar_sueltos(zip_path, nombre):
    """Rebuilds the zip leaving loose only what the reference carries + the physics."""
    fisica = {f"Automobilista 2/{r}" for r in rutas_fisica(nombre)}
    z = zipfile.ZipFile(zip_path)
    fuera = [
        n for n in z.namelist()
        if n.startswith("Automobilista 2/Tracks/")
        and not n.endswith("/")
        and n not in fisica
        and not n.lower().endswith(SUELTOS_PERMITIDOS)
    ]
    if not fuera:
        z.close()
        return []
    tmp = tempfile.mktemp(suffix=".zip")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as nuevo:
        for item in z.infolist():
            if item.filename not in fuera:
                nuevo.writestr(item, z.read(item.filename))
    z.close()
    shutil.move(tmp, zip_path)
    return fuera


def comprobar(zip_path, nombre):
    """The zip must look like Mid-Ohio: paks, few loose files and NOTHING global."""
    nombres = [n for n in zipfile.ZipFile(zip_path).namelist() if not n.endswith("/")]
    paks = [n for n in nombres if "/Pakfiles/Tracks/" in n and n.endswith(".bff")]
    sueltos = [n for n in nombres if n.startswith("Automobilista 2/Tracks/")]
    fisica = {f"Automobilista 2/{r}" for r in rutas_fisica(nombre)}
    malos = [n for n in sueltos
             if n not in fisica and not n.lower().endswith(SUELTOS_PERMITIDOS)]
    falta_fisica = sorted(r for r in fisica - set(nombres) if not opcional(r))
    globales = [
        n for n in nombres
        if any(f"/{c}/" in n for c in CARPETAS_GLOBALES)
        or ("/Tracks/_data/" in n and not es_del_circuito(os.path.basename(n), nombre))
    ]
    if not paks:
        return False, "🔴 there is no .bff at all: the track has no content"
    if malos:
        return False, f"🔴 {len(malos)} loose files remain that should only be in the pak"
    if falta_fisica:
        return False, ("🔴 LOOSE physics missing: " + ", ".join(os.path.basename(x) for x in falta_fisica)
                       + " — the car will fall into the void")
    if globales:
        return False, (f"🔴 the package overwrites {len(globales)} GAME files: "
                       f"{', '.join(globales[:4])}")
    return True, (f"✅ {len(paks)} paks · {len(sueltos)} loose (.mtx/.trd/.dds + "
                  f"{len(fisica)} physics) · 0 global engine files")


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
    print(f"empaquetado: {zip_path} ({os.path.getsize(zip_path) // 1024 // 1024} MB)")

    puestos, faltan = añadir_fisica_suelta(zip_path, pack_dir, nombre)
    print(f"LOOSE physics added: {len(puestos)}"
          + (f" · 🔴 THEY WERE NOT IN THE PACK: {', '.join(faltan)}" if faltan else ""))

    sobran = limpiar_sueltos(zip_path, nombre)
    print(f"loose files removed (they go inside the pak): {len(sobran)}"
          + (f" — {', '.join(sorted({os.path.splitext(x)[1] for x in sobran}))}" if sobran else ""))

    ok, detalle = comprobar(zip_path, nombre)
    print(detalle)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
