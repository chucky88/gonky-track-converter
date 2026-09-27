# Gonky Track Converter

Converts **Assetto Corsa** tracks (`.kn5`) to **Automobilista 2** with a single command — and
**refuses to deliver the package if something is wrong**: 30+ checks ("gates") born from real
failures that raised no error and left the track broken in game.

Looking for tracks that are already converted? See the
[GonkyRacing mod catalog](https://gonkyracing.com/en/mods/tracks).

> **Status: beta.** Tested end to end with two tracks — Charlotte Motor Speedway (oval + Roval) and
> Circuito del Jarama (3 layouts) — **on Linux only**. It should work on Windows (see
> [Installation](#installation)), but has not been tried there yet.

## ⚠️ Before converting anything: the author's permission

A conversion is a derivative of someone else's work. **Ask the original author before publishing** the
result, and credit them. Many AC mods also contain content from Kunos or other games (trees, marshals,
rFactor/GTR2 textures…) that **cannot be redistributed**: read the mod's readme and remove or replace
that content before sharing your conversion.

This tool ships no track and no game content.

## What it does

1. **Reads the AC track**: the pieces listed in `models_<layout>.ini`, the physics (inside the visible
   meshes or in `phy*.kn5`), the surfaces (`surfaces.ini` plus AC's built-in ones), the AI racing and
   pit lines, the editor markers (`AC_START_n`, `AC_PIT_n`, `AC_TIME_n`), the cameras and the Custom
   Shaders Patch lights (`extension/ext_config.ini`).
2. **Builds the scene in Blender** with the
   [Open Madness Track Tools](https://github.com/ohyeah2389/Open-Madness-Track-Tools) exporter and maps
   AC materials to AMS2 shaders (asphalt, grass, gravel, walls, glass…), including AC's **multilayer
   asphalt** (`ksMultilayer*`) with its tone and grain at their real scale.
3. **Generates what AMS2 needs and AC lacks**: the AIW (racing line, limits, grid, pit lane), timing
   triggers, cooked physics, LiveTrack (rubber and puddles), night lights, start lights, TV cameras,
   the track map and the menu images.
4. **Runs the gates. If one is red, no zip is written**, and it tells you which gate and why.
5. **Packs the mod**, ready to install. Several layouts are joined into one mod with `join_layouts.py`.

Every conversion also writes a `REPORT.md` with what the tool found in the track (see
[Help improve it](#help-improve-it)).

## What's in the repository

| | |
|---|---|
| `convert_ac.py` | **the main command**: converts one layout |
| `join_layouts.py` | joins several converted layouts into one mod |
| `check_setup.py` | checks that everything is installed |
| `download_textures.py` | downloads and prepares the CC0 filler textures |
| `open_bff.py` | unpacks a game `.bff` (optional) |
| `converter/` | the code: AC and AMS2 format readers, generators (AIW, lights, cameras, triggers…) and the gates |
| `examples/` | the exact commands of real conversions that work |
| `docs/` | options, lessons learned, external tools, textures, compatibility list |
| `tests/` | automated tests (no Blender needed) |
| `omtt/`, `tools/PCarsTools/` | submodules: Open Madness Track Tools and PCarsTools |

## Installation

| | tested | for |
|---|---|---|
| [Blender](https://www.blender.org/) | 4.3 | builds and exports the scene |
| [Open Madness Track Tools](https://github.com/ohyeah2389/Open-Madness-Track-Tools) | pinned (submodule) | the exporter (TrackCompiler, as a Blender add-on), TrackPacker, the Example Project, PhysicsMeshCooker |
| Python | 3.11+ | the pipeline |
| numpy, Pillow | | `pip install numpy pillow` |
| [ImageMagick](https://imagemagick.org/) | 6.9 or 7 | `.dds` textures |
| [wine](https://www.winehq.org/) | | **Linux/macOS only**: runs PhysicsMeshCooker (a Windows `.exe`) |

1. Clone this repository **with its submodules** (Open Madness Track Tools lives in `omtt/`, pinned to
   the version everything was tested with):
   ```bash
   git clone --recursive https://github.com/Gonky28/gonky-track-converter.git
   ```
   (Already cloned without `--recursive`? Run `git submodule update --init`.)
2. From the [OMTT releases](https://github.com/ohyeah2389/Open-Madness-Track-Tools/releases), get:
   - `trackcompiler-*.zip` → install it in Blender as an add-on (*Edit → Preferences → Add-ons →
     Install from Disk*);
   - `ExampleProject.zip` → unzip it into `omtt/example/` (you must end up with
     `omtt/example/Example Project/`);
   - `PhysicsMeshCooker.exe` → into `omtt/cooker/`, with the PhysX DLLs listed in its README.
3. `pip install numpy pillow`, and install ImageMagick (and wine if you are not on Windows).
4. Download and prepare the CC0 filler textures (~170 MB): `python3 download_textures.py`.
5. Check everything is in place: `python3 check_setup.py` — it tells you what is missing and how to
   fix it.
6. *(Optional)* By default everything lives inside the repo (`omtt/`, `textures/`, `work/`). To change
   something — e.g. a work folder on a disk with space — copy `settings.example.ini` to `settings.ini`,
   or use `AMS2TC_<KEY>` environment variables.

## Usage

```bash
python3 convert_ac.py --folder "<AC track folder>" --layout <layout> --name <id_no_spaces> \
    --title "Track name" --geo <lat>,<lon>,<altitude>,<timezone> \
    --cc0-families grass --pit-limiter 60 --max-ai 32
```

The result is `<work folder>/<id>/<id>.zip`, next to a `REPORT.md`. All options:
`python3 convert_ac.py --help` or [docs/OPTIONS.md](docs/OPTIONS.md). A misspelt option stops the
command instead of being silently ignored.

**Easiest start: copy a [real example](examples/)** — Charlotte (oval + Roval, at night) or Jarama
(three layouts, by day) — and change the track details.

Several layouts in one mod:

```bash
python3 join_layouts.py my_track.zip --group My_Track_Group \
    layout1.zip:id1:Variant1:1 layout2.zip:id2:Variant2:2
```

## What you must check in game

The gates catch what can be measured from outside; they cannot see the game. For every version:

- **load cold** (without having loaded another track first);
- **start from the grid**: every car on track and in its column;
- **drive a full lap**: no sinking, no floating, no holes;
- **the asphalt**, near and far, by day and **at night** (reflections, grain);
- **the lights** at night: track, pit lane and grandstands;
- **the AI**: no braking where it shouldn't.

Change **one thing per version**: if a version fails, you know what caused it.
[docs/LESSONS.md](docs/LESSONS.md) collects the failures that already cost us versions — none of them
raised an error — and how the tool now catches them.

## Opening `.bff` files (optional)

To look inside an official track (how Reiza solves a material, the lights, the AIW…) or compare two
builds of your own package, `open_bff.py` uses [PCarsTools](https://github.com/Nenkai/PCarsTools) by
Nenkai (submodule in `tools/PCarsTools`):

```bash
python3 open_bff.py "<AMS2>/Pakfiles/DAYTONA.bff" --game "<AMS2 folder>"
```

Get the executable from its releases (or build it with .NET 6) and set `pcarstools` in `settings.ini`.
The AMS2 folder is needed because PCarsTools uses its `oo2core_4_win64.dll`, which cannot be
redistributed. On Linux it runs under wine with the Windows .NET 6 runtime in the prefix.
What you extract from the game is Reiza's content: use it to **learn**, never ship it in a mod.

## Installing and sharing the mod

- **GonkyRacing mod catalog**: [tracks](https://gonkyracing.com/en/mods/tracks),
  [cars](https://gonkyracing.com/en/mods/cars) and [liveries](https://gonkyracing.com/en/liveries) for
  AMS2, with details, screenshots and authors. Tracks converted with this tool are published there.
- **[GonkyRacing Pilot Manager](https://gonkyracing.com/en/pilot-manager)**: GonkyRacing's free app for
  AMS2. One-click install (and removal) of anything in the catalog, plus lobbies, results, telemetry
  and FFB settings.
- **Converted a track and want to share it?** Upload it through GonkyRacing's
  [modders studio](https://gonkyracing.com/en/modders) so it reaches drivers through the Pilot Manager.
- Open-source alternative: [AMS2 Content Manager](https://github.com/OpenSimTools/AMS2CM).

External tools, what each one is for, its license and where to get it: [docs/TOOLS.md](docs/TOOLS.md).

## Help improve it

The tool comes from converting a handful of tracks, and every new track has brought something it did
not handle yet. **Every conversion leaves a `REPORT.md`** describing what the tool found — no mod
content, no paths from your computer: AC shaders (and the ones it has never seen), surfaces, physics,
CSP sections, gate results. **Share it in an issue** — *Working conversion*, *New case* or *Lesson
learned* — and the next version will know. See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[compatibility list](docs/COMPATIBILITY.md).

## Versions and bug reports

See [CHANGELOG.md](CHANGELOG.md). The version is also written into each mod's `CREDITS.txt`, so you
know which one converted it. Something went wrong? Open an issue with the *Conversion problem*
template: it asks for the command, its output and `check_setup.py`, which is what we need to help.

## Credits and license

- [Open Madness Track Tools](https://github.com/ohyeah2389/Open-Madness-Track-Tools) by **ohyeah2389**:
  the AMS2 exporter everything relies on. GPL-3 with an output exception.
- [PCarsTools](https://github.com/Nenkai/PCarsTools) by **Nenkai** (MIT).
- Filler textures from [ambientCG](https://ambientcg.com/) (CC0).
- Made by [GonkyRacing](https://gonkyracing.com). Not affiliated with Reiza, Kunos or Epic: see
  [NOTICE.md](NOTICE.md).

License: **GPL-3.0** (see [LICENSE](LICENSE)) — the same as TrackCompiler, which this tool uses. You
may use, modify and share it freely; if you distribute a modified version, it must stay GPL-3 and keep
the credits.

The tracks you convert belong to you and their original authors, not to this tool. Each mod carries a
`CREDITS.txt` at the root of its zip (outside the game folder: it is not installed) with the original
author and a "converted using Gonky Track Converter" note; `--no-credits` removes it.
