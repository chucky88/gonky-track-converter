# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions: [SemVer](https://semver.org/).
The version lives in `converter/version.py` and is written into each mod's `CREDITS.txt`.

## [Unreleased]

### Added
- `--light-boost <factor>`: multiplies the intensity of the spotlights over the track and the pits
  (stands, buildings and glows are left as they are). Default 1.
- 🧪 `--bmt-only`: materials only as `.bmt` inside the paks, with no `.mtx` loose or packed, like
  fully packed reference tracks, written by a new `.bmt` writer (`converter/bmt_fix.py`) that follows
  the layout of the game's own files. TrackPacker is wrapped, not modified.

### Found
- OMTT's MTX→BMT converter writes a layout the game can't use: each element points at its first
  child's attributes (the material loses its name and shader), elements are pre-order, the path
  index and the same-path chains differ. Packed alone, those `.bmt` draw nothing. The new writer
  reproduces 338 of 362 of an official track's `.bmt` byte for byte and the rest with the same
  structure and values.

## [0.3.1] — 2026-09-27

### Changed
- **Packages ship far fewer loose files** (Charlotte: 582 → 415 MB). Everything that is already inside
  the paks with the same content — textures, physics, AI line, LiveTrack — is no longer shipped a
  second time loose; the `.mtx`, the `.trd` and the two files TrackPacker leaves out of the pak
  (start lights, `env.xml`) stay loose. Tested in game: the track loads, drives and draws as before.
- A loose copy is only dropped once the pak is proven to hold it (new `converter/bff_read.py`), and
  the packaging gate now checks that the physics is INSIDE a pak.

## [0.3.0] — 2026-09-27

First public release (beta): the pipeline GonkyRacing used to convert Charlotte Motor Speedway (oval +
Roval) and Circuito del Jarama (3 layouts), reviewed and prepared for the community.

### Added
- `convert_ac.py`: converts an Assetto Corsa layout to AMS2 with 30+ gates that refuse to write the zip
  when something is wrong.
- `join_layouts.py`: several layouts in one mod (group, variant, order), with their credits merged.
- `check_setup.py`: checks the requirements and says how to fix what is missing.
- `download_textures.py`: downloads and prepares the 12 CC0 filler textures from ambientCG.
- `open_bff.py`: unpacks `.bff` files with PCarsTools.
- `--help` with every option grouped, generated from one table (`converter/opciones.py`) that also
  produces `docs/OPTIONS.md`. Options in English, with the original Spanish names as aliases.
- **A misspelt or unknown option stops the command** instead of being silently ignored.
- **`REPORT.md` for every conversion**: AC shaders (flagging the ones never seen before), surfaces,
  physics, CSP sections, gates and warnings — no mod content and no local paths. Share it in an issue
  so the tool learns from new tracks.
- `CREDITS.txt` at the zip root of every mod (original author + "converted using Gonky Track
  Converter"); `--no-credits` removes it.
- `--ads MATERIAL[,…]=image.png`: your own image on those ads of the original track (with its author's
  permission).
- Configurable paths and programs (`settings.ini` or `AMS2TC_*`); by default everything stays inside the
  repo. Ready for Windows (ImageMagick's `convert` vs the Windows disk tool; PhysicsMeshCooker without
  wine).
- Submodules: Open Madness Track Tools and PCarsTools, pinned to the tested versions.
- Docs: options, 53 lessons learned, external tools, textures, compatibility list, real examples;
  issue templates (conversion problem, new case, working conversion, lesson learned); CONTRIBUTING.
- Automated tests (no Blender needed), run on every push.
- Everything in English: messages, reports, credits, docs and code comments.

### Verified
- Charlotte (oval + Roval) rebuilt with this version is identical to the published one: inside the
  packages, only rounding noise in 72 meshes (< 4 µm) and the sign of one tangent.

### Fixed
- Relative paths (`--photo my.jpg`, `--folder ../my_track`) used to break outside GonkyRacing's own
  setup, because every step runs inside `converter/`; they are made absolute first.

### Not tested yet
- Windows (only run on Linux so far).
