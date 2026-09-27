"""Downloads from ambientCG (CC0) and prepares the filler textures used by the pipeline.

    python3 download_textures.py [--output <folder>] [--source <folder>] [--small]

It leaves in the textures folder (`textures` from `settings.ini`, or `--output`) the 12 `.dds`
files the pipeline looks up by name (`<familia>_diffuse/_normal/_detalle.dds`, see docs/TEXTURES.md).

- `--source`: a folder that already holds the ambientCG materials, unzipped
  (`Asphalt031_8K/…_Color.jpg`) or as their zips; that way nothing is downloaded.
- `--small`: everything at 4K at most (the asphalt and grass diffuse maps are 8K by default: 42 MB each).

The recipe is that of the textures the conversions were tested with (measured from their DDS
headers, not assumed): DXT1 with the full mipmap chain; asphalt and grass diffuse maps at 8K, the
rest at 4K; `_detalle` at 2K. 🔴 The `_detalle` map is the texture in GREYSCALE shifted to a mean of
0.5 by ADDING (this keeps the contrast: standard deviation 0.0645 versus 0.0628 in the original):
AMS2's ground shader multiplies colour × detail × 2, and a detail map in colour or off-centre leaves
the ground black or burnt out. The normal maps are the `NormalDX` ones (DirectX convention).
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rutas as R  # noqa: E402

# family: (ambientCG material, diffuse resolution, does it have a _detalle map?)
MATERIALES = {
    "asfalto": ("Asphalt031", "8K", False),
    "hierba": ("Grass001", "8K", True),
    "hormigon": ("Concrete034", "4K", True),
    "grava": ("Gravel022", "4K", True),
}
LADO = {"8K": 8192, "4K": 4096}
LADO_NORMAL, LADO_DETALLE = 4096, 2048
URL = "https://ambientcg.com/get?file={material}_{res}-JPG.zip"


def _mapa(carpeta: str, material: str, res: str, tipo: str) -> str | None:
    """Path of `<material>_<res>-JPG_<tipo>.jpg` in `carpeta` (unzipped, or inside its zip)."""
    for patron in (f"{material}_{res}*/*_{tipo}.jpg", f"*{material}_{res}*_{tipo}.jpg"):
        hay = glob.glob(os.path.join(carpeta, patron))
        if hay:
            return hay[0]
    zips = glob.glob(os.path.join(carpeta, f"{material}_{res}*.zip"))
    if zips:
        destino = os.path.join(carpeta, f"{material}_{res}")
        with zipfile.ZipFile(zips[0]) as z:
            z.extractall(destino)
        return _mapa(carpeta, material, res, tipo)
    return None


def _descargar(material: str, res: str, carpeta: str) -> None:
    destino = os.path.join(carpeta, f"{material}_{res}-JPG.zip")
    if os.path.exists(destino):
        return
    print(f"   downloading {material} {res} from ambientCG…", flush=True)
    peticion = urllib.request.Request(URL.format(material=material, res=res),
                                      headers={"User-Agent": "GonkyTrackConverter"})
    with urllib.request.urlopen(peticion, timeout=600) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f)


def _dds(entrada: str, salida: str, lado: int, *extra) -> None:
    cmd = [*R.IM_CONVERT, entrada, *extra, "-resize", f"{lado}x{lado}!",
           "-define", "dds:compression=dxt1", "-define", f"dds:mipmaps={lado.bit_length()}", salida]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"🔴 ImageMagick couldn't write {salida}: {r.stderr.strip()[-300:]}")


def _media_gris(ruta: str, lado: int) -> float:
    r = subprocess.run([*R.IM_CONVERT, ruta, "-colorspace", "Gray", "-resize", f"{lado}x{lado}!",
                        "-format", "%[fx:mean]", "info:"], capture_output=True, text=True)
    return float(r.stdout.strip())


def preparar(salida: str, origen: str | None = None, ligero: bool = False) -> list:
    os.makedirs(salida, exist_ok=True)
    cache = origen or os.path.join(tempfile.gettempdir(), "gonky-track-converter-ambientcg")
    os.makedirs(cache, exist_ok=True)
    hechas = []
    for familia, (material, res, con_detalle) in MATERIALES.items():
        res = "4K" if ligero else res
        color, normal = (_mapa(cache, material, res, t) for t in ("Color", "NormalDX"))
        if not (color and normal):
            _descargar(material, res, cache)
            color, normal = (_mapa(cache, material, res, t) for t in ("Color", "NormalDX"))
        if not (color and normal):
            raise SystemExit(f"🔴 can't find {material} {res} (Color and NormalDX) in {cache}")
        _dds(color, os.path.join(salida, f"{familia}_diffuse.dds"), LADO[res])
        _dds(normal, os.path.join(salida, f"{familia}_normal.dds"), LADO_NORMAL)
        hechas += [f"{familia}_diffuse.dds", f"{familia}_normal.dds"]
        if con_detalle:
            m = _media_gris(color, LADO_DETALLE)
            _dds(color, os.path.join(salida, f"{familia}_detalle.dds"), LADO_DETALLE,
                 "-colorspace", "Gray", "-evaluate", "add", f"{(0.5 - m) * 100:.3f}%")
            hechas.append(f"{familia}_detalle.dds")
        if familia == "hormigon":       # the relief of the walls: ONLY the concrete normal map
            _dds(normal, os.path.join(salida, "muros_normal.dds"), LADO_NORMAL)
            hechas.append("muros_normal.dds")
        print(f"   ✅ {familia}: {material} {res}", flush=True)
    with open(os.path.join(salida, "SOURCES.txt"), "w", encoding="utf-8") as f:
        f.write("Textures generated by download_textures.py (Gonky Track Converter) from ambientCG, CC0:\n")
        for familia, (material, res, _d) in MATERIALES.items():
            f.write(f"  {familia}: https://ambientcg.com/view?id={material} ({'4K' if ligero else res})\n")
    return hechas


def main(argv):
    # English names → internal ones (the Spanish ones still work)
    argv = [{"--output": "--salida", "--source": "--origen", "--small": "--ligero"}.get(a, a) for a in argv]
    salida = argv[argv.index("--salida") + 1] if "--salida" in argv else R.TEXTURAS
    origen = argv[argv.index("--origen") + 1] if "--origen" in argv else None
    hechas = preparar(salida, origen, "--ligero" in argv)
    print(f"✅ {len(hechas)} textures in {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
