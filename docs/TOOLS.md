# External tools

Everything this tool uses or relies on, what each piece is for, and whether you need it.

## Required

| tool | what it does here | license | how to get it |
|---|---|---|---|
| [Open Madness Track Tools](https://github.com/ohyeah2389/Open-Madness-Track-Tools) (ohyeah2389) | **TrackCompiler**: the Blender exporter to AMS2's formats (`.meb` meshes, `.mtx` materials, `.sgx` scene, `.gcl` limits…); **TrackPacker**: packs the mod; **Example Project**: the file template and the "donor" materials; **PhysicsMeshCooker**: cooks the `.csm` physics | GPL-3 with output exception (TrackCompiler, TrackPacker); CC BY 4.0 (Example Project); MIT (PhysicsMeshCooker) | submodule `omtt/` + its [releases](https://github.com/ohyeah2389/Open-Madness-Track-Tools/releases) |
| [Blender](https://www.blender.org/) 4.3 | builds the scene and runs TrackCompiler | GPL | blender.org |
| Python 3.11+ with numpy and Pillow | the pipeline outside Blender | PSF / BSD / HPND | `pip install numpy pillow` |
| [ImageMagick](https://imagemagick.org/) 6.9 or 7 | converts and measures `.dds` textures | ImageMagick license (Apache-like) | imagemagick.org |
| [wine](https://www.winehq.org/) | **Linux/macOS only**: runs PhysicsMeshCooker, a Windows `.exe` | LGPL | your package manager |

## Optional

| tool | what for | license | how to get it |
|---|---|---|---|
| [PCarsTools](https://github.com/Nenkai/PCarsTools) (Nenkai) | unpack game `.bff` files and your own packages (`open_bff.py`) | MIT | submodule `tools/PCarsTools` + its releases; on Linux, Windows .NET 6 under wine |
| GonkyRacing mod catalog: [tracks](https://gonkyracing.com/en/mods/tracks), [cars](https://gonkyracing.com/en/mods/cars), [liveries](https://gonkyracing.com/en/liveries) | already converted tracks, and a place to publish yours | free | gonkyracing.com |
| [GonkyRacing Pilot Manager](https://gonkyracing.com/en/pilot-manager) | **one-click install** (and removal) of the mod this tool builds; share it in the [catalog](https://gonkyracing.com/en/mods/tracks) through the [modders studio](https://gonkyracing.com/en/modders) | free | gonkyracing.com |
| [AMS2 Content Manager](https://github.com/OpenSimTools/AMS2CM) (OpenSimTools) | install mods (open-source alternative) | MIT | its releases |

## References (not installed: consulted to understand the formats)

| | what it provides |
|---|---|
| [OMTT Docs](https://github.com/ohyeah2389/Open-Madness-Track-Tools) (`OMTT Docs/` folder in the submodule) | AMS2 formats: MEB, MTX, SGX, TRD, AIW… e.g. that UVs are compressed to float16 unless `_no_uv_comp` |
| [Custom Shaders Patch recreated shaders](https://gitlab.com/ac-custom-shaders-patch/public/acc-shaders) | the code of Assetto Corsa's shaders (`recreated/`): how the `ksMultilayer*` layers combine (in world metres), detail, fresnel… The primary source for everything the tool does with AC materials |
| [CSP track documentation](https://cup.acstuff.club/docs/csp/tracks/miscellaneous-options) | `ext_config.ini`: light series (`LIGHT_SERIES`), materials, effects |
| [assettocorsamods.net](https://assettocorsamods.net/) | AC track-building guides and the list of shaders and texture maps |
| [AC Tools for Blender](https://extensions.blender.org/add-ons/ac-tools/) | add-on for building AC tracks: useful to understand how they're put together (the tool reads `.kn5` with its own reader, `kn5_read.py`) |
| [ambientCG](https://ambientcg.com/) | the CC0 filler textures (see [TEXTURES.md](TEXTURES.md)) |

## Content that is NOT included and must not be

- `oo2core_4_win64.dll` (**Oodle**): RAD Game Tools' (now Epic Games') compression library, which AMS2
  uses for its `.bff` packages. It's closed-source commercial software and can't be redistributed. It
  ships with the game, and PCarsTools uses it from your AMS2 folder.
- Anything extracted from AMS2, Assetto Corsa or other games' packages: it's for learning how they're
  made, **not** for putting in a mod.
