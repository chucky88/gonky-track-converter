# Lessons: the failures that already cost us versions

They all have one thing in common: **none of them raised an error**. The game loaded, the package was
built, and the track was broken in a way you only saw by driving it. Each one now has a gate or a rule
in the code that catches it. Ordered by how much it costs if it slips through.

## Loading and scene

- **AC's editor markers (`AC_START_n`, `AC_PIT_n`, `AC_TIME_n`) must be in the scene**, even if
  invisible. Without them loading hangs (measured over 5 builds in a row).
- **Respect the `.kn5` flags**: some meshes are collision only (53 in Charlotte). And compose the
  parents' transforms.
- **Material names without spaces or dots**, or its `.mtx` is not written and the mesh comes out wrong.
- **AMS2's grid limit is 32.** With more, the server warns on the console and loads another track.

## Physics

- **AC's built-in surfaces are not listed in `surfaces.ini`.** If one is missing (it happened with
  `LINE`, the painted line), that area is left out of the physics: the car **sinks** and flips. The
  "ground under the racing line" gate walks the racing line against the cooked physics, not against the
  surface table (which had the same flaw as what it measured).
- **`pit_lane.ai` is a full lap**: it has to be cut by surface (track → apron → pits → apron → track).
- **Grid and TELEPORT 3 m above the collision, pit boxes (`PitPos`) at 0.05 m** (at 3 m the mechanics
  float), with the ray cast against the collision only.
- **Collision: `(x, z, −y)`, not `(x, z, y)`.** The second one is a MIRROR, not a rotation: it leaves the
  normals facing down (the car goes through the asphalt) and the collision mirrored from the visible
  track (grid on the grass, banking reversed).
- **AC has the opposite handedness to AMS2: Z must be negated.** A mirrored world passes every gate that
  compares the package with itself; only comparing with the direction declared in `ui_track.json`
  catches it.
- **The physics goes INSIDE the pak, not loose; the `.mtx` do go loose.** Measured one change at a
  time: with every loose copy of what was already in the paks removed, the cars sat on the grid (the
  physics in `_Physics.bff` works) but the track was not drawn at all; putting only the loose `.mtx`
  back drew it again. TrackPacker writes each material into the pak as both `.mtx` and `.bmt`, and
  packed `.mtx` don't work. (An older note here said the loose `.csm` was needed: that failure had
  another cause.) `empaquetar.py` now drops a loose copy only after proving the pak holds it.
- **AC surfaces are case-insensitive** (`1apron_…`): otherwise, areas without physics and the car falls
  into the void. In the main `.kn5` the grass (`3GRASS`) is collision only, and `3DPANO` is not physics.
- **wine is case-insensitive**: the physics cooker needs a clean folder on every run.

## Grid

- **In AC the grid is often far from the finish line** (AC has no rolling start). AMS2 does not count the
  lap until the line is crossed: the order is scrambled for the whole first lap. `--grid-at-finish`.
- **When moving it, the asphalt centre is the median over ±40 m**, not one point: where the asphalt
  widens (the pit entry/exit junction) a grid slot moved 11 m inwards, off the track.
- **If there is a chicane before the finish line**, the grid is formed along the racing line of another
  layout that shares the finish line (`--grid-from`). The formation gate checks that each column is
  **straight**, independently of the racing line.

## AI and racing line (AIW)

- **OMTT writes `wp_width` with 2 numbers and AMS1 with 4**: requiring 4 left the track with zero width.
- **OMTT flattens `wp_perp` (the banking)**: the AI braked from 250 to 140 km/h on the oval. Fixed by
  tilting it with the real banking (`inclinar_aiw`).
- **OMTT leaves `wp_score` at 0 on the pit lane and grid**: to the game they are at the finish line and
  it counts extra laps. They are scored along the lap (`aiw_puntuar`).
- **The AI centre line and width without the apron**: with it you get kinks (the AI brakes mid-corner)
  and the AI looks for lines on the apron. But the limits (`.gcl`) do include it: check the apron stays
  inside.
- **Resample the AC racing line to ~5 m**: with 1.6 m between points a 4-corner oval produced 186
  corners. And the corner threshold must be adaptive (Talladega would get 0); the apex is a plateau.
- **Pit triggers away from the ends of the pit lane**: if they touch the racing line, the AI pits and
  laps don't count.

## Timing

- **Triggers are 100 m tall boxes with no direction.** If another stretch of the lap passes through the
  same box (a Roval running twice over the same asphalt), the lap time is cut there. Thresholds measured
  on official tracks: finish line and sectors, 100 % of the asphalt covered and ≥16.5 m from other
  passes; pits, ≥85 %.

## TRD and Example Project files

- **The TRD must not keep the Example Project's identity** (Meadowdale: `ScenegraphFile`,
  `ShortTrackName`): the track doesn't load and the images come out blank. The template's pit limiter is
  240 km/h.
- **`Track Type=Oval` without `Oval Type`** hangs loading forever.
- **`Max AI participants` = 31** with a 32-car grid: the game adds the player. `sector_2_length` is
  cumulative.
- **The engine's global files must not go in the package** (`dynamic.sys.xml`, an `env.xml` with the
  example's cones…): they override the game's and the track doesn't load cold. Neither must the
  example's `.mrdf`, `.lsd` or renamed textures.
- **Blender exits with code 0 even if the script crashes**: look for `Traceback` in its output, or the
  gates judge the package from the previous conversion.

## Asphalt and materials

- **A material's family is decided by its physical SURFACE, not by its name.**
- **AC's multilayer asphalt (`ksMultilayer*`) works in WORLD metres**, not in UV space: the grain repeats
  every `1/mult` m. Baking it onto the UV made it 14 times bigger (`--ac-layers` does it right).
- **Every AC shader parameter is read from the `.kn5`, never assumed**: `magicMult` was 1 on one track and
  1.7 on the next, and without it the asphalt came out 40 % darker.
- **Names in the `.kn5` and the `.mtx` files may differ in case**: compare case-insensitively, and warn
  if there is data and nothing matches (two builds came out without the change and without a warning).
- **AMS2 compresses mesh UVs to float16** unless the `.meb` name ends in `_no_uv_comp`: heavily tiled
  textures appear and disappear.
- **AC rubber/skid-mark layers are removed**: AMS2 draws rubber with LiveTrack, and AC's flicker.
- **AC's alpha blending, always with alpha test** (without it, black rectangles); **never** alpha test
  on the road shader.
- **Track textures WITH mipmaps; UI textures WITHOUT.** And open every texture by its real name (case):
  on Linux, otherwise, the mipmap check misses it.
- **The order of a material's defines is part of its permutation**: an order the game hasn't compiled
  leaves the mesh invisible, without an error. Orphan defines (`USE_DIFFUSE2`, `USE_TERRAIN_BLEND`) do
  the same. `USE_ALPHATEST` on textures with holes (otherwise 31 materials came out solid).
- **Texture paths with backslashes**, and **no TGA** (the game doesn't read them).
- **Grass (`new_ground`)**: only the wide layer carries colour; the middle and detail layers are GREY
  modulators centred on 0.5 (with coloured grass, the lawn comes out black).
- **A DXT1 with no alpha means maximum gloss** on the road shader; each material's gloss is read from
  the original's `ksSpecular`. At night a high `fresnelFactor` turned the asphalt white; and
  `USE_COLOURISATION`/`TINT_USE_SIMPLE` tinted the whole track green or red.
- **A normal map baked for another track makes it worse.** Tighten the UV only with a tileable texture,
  compensating every `*Scale/Tiling*`.
- **In `.kn5` materials, every scalar is followed by a vec2, a vec3 and a vec4**: skipping them left
  `detailNMMult` and `multA` at 0.
- **`ac_crew.kn5` out**: its static figures show on top of AMS2's animated crew.

## Start lights and cameras

- **Start-light mesh vertices in local coordinates**: otherwise a red sheet appears in the sky. Each
  light's ID goes in the 2nd UV and only reaches the `.meb` with `uv1`/`uv2`; those meshes, referenced
  by name, don't get `_no_uv_comp`.
- **TV cameras**: split the lap into more zones, don't enlarge them (it breaks loading); at most 5 zones
  per camera; `areaIndex` is an attribute, not a property; `FOVMin` = `FOVMax` is a camera without zoom;
  `Dimensions` are half-sizes.

## Night and lights

- **`GroundPlaneDistance` = the light's height above the ground.** With a fixed value of 5, a floodlight
  25 m up doesn't reach the asphalt: the track stays **black** even though the numbers say there's
  plenty of light. The cars' headlights (<1 m above the ground) do light it, which is misleading.
  `--real-ground-plane`.
- **A repeated `DIRECTION` in a CSP `LIGHT_SERIES`**: the last one wins and the lights point at the sky.
  The first one is used, with a warning.
- **1–8 px emissive strips vanish with mipmaps**: minimum thickness, and use the author's
  `[CustomEmissive]` rectangles when there are any.
- **An empty lights file crashes AMS2**, and so does one whose header promises a partition the body
  doesn't have.
- **Cone 120/150** on the big floodlights (the template's −1/180 lights nothing).
- **Copy the GEOMETRY of the official floodlights**, not a "total light" number: on both sides, tilted
  24° towards the track, cold colour, plus short lights above (`--track-floodlights`).

## Workflow

- **One change per version.** If a version changes five things and fails, there's no way to know which.
- **Compare zip to zip with the previous version before publishing**: what comes in, what goes out,
  what changes. Two of the failures above were caught that way, not in the log.
- **Disk**: each version of a big track takes 1–2 GB. Out of space, Blender says "No such file or
  directory" when saving, not "disk full".
