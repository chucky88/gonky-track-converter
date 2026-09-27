# Filler textures (CC0)

The tool uses a few **CC0** (public domain) textures from [ambientCG](https://ambientcg.com/) for the
surfaces whose mod texture doesn't work in AMS2 (grass and gravel detail, asphalt and wall relief).

**They are generated for you**: `python3 download_textures.py` downloads them from ambientCG and
converts them (`--source <folder>` if you already have the materials; `--small` to keep everything at
4K).

| file | source |
|---|---|
| `asfalto_diffuse.dds`, `asfalto_normal.dds` | [Asphalt031](https://ambientcg.com/view?id=Asphalt031) |
| `hierba_diffuse.dds`, `hierba_normal.dds`, `hierba_detalle.dds` | [Grass001](https://ambientcg.com/view?id=Grass001) |
| `hormigon_diffuse.dds`, `hormigon_normal.dds`, `hormigon_detalle.dds` | [Concrete034](https://ambientcg.com/view?id=Concrete034) |
| `grava_diffuse.dds`, `grava_normal.dds`, `grava_detalle.dds` | [Gravel022](https://ambientcg.com/view?id=Gravel022) |
| `muros_normal.dds` | Concrete034 (relief only) |

- Format (measured on the textures the conversions were tested with): DXT1 with the full mipmap chain;
  asphalt and grass diffuse at 8192, the rest at 4096 and the `_detalle` ones at 2048.
- The `*_detalle` textures are the same texture in **greyscale, shifted to a mean luminance of 0.5 by
  ADDING** (which keeps the contrast): AMS2's ground shader multiplies colour × detail × 2, so a detail
  that isn't centred on 0.5 darkens or burns the whole ground.

🔴 **Don't use textures from official AMS2 tracks** or other games: it's paid content, and putting it in
a mod is redistributing it.
