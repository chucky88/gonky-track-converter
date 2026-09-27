# Options of `convert_ac.py`

> Generated from `converter/opciones.py` (`python3 converter/opciones.py --markdown`): to add or
> change an option, change it there. `python3 convert_ac.py --help` shows the same list.

✅ = used in conversions that work in game. Each option also accepts its original Spanish name. An
option that doesn't exist (a typo, say) **stops** the command instead of being ignored.

For `--cc0-families` the values are `grass`, `gravel`, `concrete`, `asphalt`, `walls`, `fences` and
`lines`, comma-separated; for `--night-glow`, a list of materials or `all`.

## Required

| option | also accepted | what |
|---|---|---|
| `--folder <value>` | `--carpeta` | the AC track folder (the one with the `.kn5` files and the `models_*.ini`) |
| `--layout <value>` | `--trazado` | the layout subfolder (`layout_gp`, `oval`…); defaults to `layout_speedway` |
| `--name <value>` | `--nombre` | the track id in AMS2: lowercase, no spaces or dots |

## Track details

| option | also accepted | what |
|---|---|---|
| `--title <value>` | `--titulo` | the name shown in game (defaults to the `ui_track.json` one) |
| `--geo <value>` | — | ✅ `lat,lon,altitude,timezone`: real sun, stars and local time. E.g. `40.6170,-3.5857,620,1` |
| `--date <value>` | `--fecha` | reference date `YYYY-M-D` |
| `--corners <value>` | `--curvas` | number of corners (info page) |
| `--photo <value>` | `--foto` | 16:9 photo for the menu; without it, the mod's own |
| `--reiza-style-map` | `--estilo-reiza` | ✅ track map in the style of the official ones |
| `--group <value>` | `--grupo` | ✅ group to join layouts into one mod (`join_layouts.py`) |
| `--variant <value>` | `--variante` | ✅ the layout's name within the group |
| `--order <value>` | `--orden` | ✅ the layout's position in the group (1, 2…) |

## Track, grid and AI

| option | also accepted | what |
|---|---|---|
| `--oval` | `--ovalo` | ✅ it's an oval (banking, oval grid and AI) |
| `--pit-limiter <value>` | `--limite-boxes` | ✅ pit speed limiter in km/h |
| `--max-ai <value>` | `--max-ia` | ✅ grid size; 32 is the game's maximum |
| `--grid-at-finish` | `--parrilla-en-meta` | ✅ moves the author's grid to the finish straight (in AC it's often far away: AMS2 doesn't count the lap until the line is crossed) |
| `--grid-from <value>` | `--parrilla-de` | ✅ forms the grid along ANOTHER layout's racing line with the same finish line (when there's a chicane before the finish) |
| `--ai-centre-asphalt` | `--central-asfalto` | ✅ AI centre line along the middle of the racing asphalt |
| `--asphalt-width` | `--ancho-asfalto` | ✅ track limits along the real asphalt |
| `--pit-distances` | `--distancias-boxes` | ✅ pit and grid lap distances with the official tracks' rule |

## Materials and textures

| option | also accepted | what |
|---|---|---|
| `--textures <value>` | `--texturas` | ✅ CC0 textures folder (`download_textures.py`); defaults to the `settings.ini` one |
| `--cc0-families <value>` | `--familias-cc0` | ✅ families that get CC0 detail (usually `grass`) |
| `--ac-layers` | `--capas-ac` | ✅ AC's multilayer asphalt (`ksMultilayer*`): the author's tone and grain at their real scale |
| `--asphalt-gloss` | `--brillo-asfalto` | ✅ each asphalt's gloss = the original's `ksSpecular`, plus a gloss mask where the texture has none |
| `--asphalt-normal` | `--relieve-asfalto` | ✅ relief (CC0 normal map) on the asphalt |
| `--asphalt-fresnel <value>` | `--fresnel-asfalto` | asphalt fresnel (default 0.2) |
| `--translucent-fences` | `--vallas-translucidas` | ✅ fences and meshes with the official tracks' recipe |
| `--banners <value>` | `--pancartas` | your own banners on the author's banner meshes (JSON; see `converter/pancartas.py`) |
| `--ads <value>` | `--publicidad` | `MATERIAL[,MATERIAL…]=image.png`: your image on those ads of the author (with their permission) |

## Night and lights

| option | also accepted | what |
|---|---|---|
| `--author-lights` | `--luces-autor` | ✅ the lights the author declared for Custom Shaders Patch (`LIGHT_SERIES`) |
| `--track-floodlights` | `--focos-daytona` | ✅ track floodlights with the official tracks' recipe (both sides, tilted, cold colour + short ones above) |
| `--real-ground-plane` | `--plano-real` | ✅ **essential at night**: each light's ground plane at its real height (without it a high floodlight doesn't reach the asphalt) |
| `--stand-floodlights` | `--focos-gradas` | ✅ floodlights for the grandstands and the crowd |
| `--dark-spot-lights` | `--focos-oscuros` | extra floodlights on dark stretches (replaced by `--track-floodlights`) |
| `--night-glow <value>` | `--brillos-nocturnos` | ✅ what glows at night (windows, panels…): `all` |
| `--start-lights` | `--semaforos` | ✅ the game's start lights and pit lights |
| `--ambience <value>` | `--ambiente` | ✅ sky and fog of another track in the game (`Daytona`, `Barcelona`…) |

## Other

| option | also accepted | what |
|---|---|---|
| `--tv-cameras` | `--camaras-tv` | ✅ TV cameras from the mod's |
| `--ambient-sound` | `--sonido-propio` | ✅ ambient sound placed along the track's grandstands |
| `--no-credits` | `--sin-creditos` | don't write `CREDITS.txt` into the zip |


## Real examples

The full commands for Charlotte (oval + Roval, at night) and Jarama (three layouts, by day) are in
[../examples/](../examples/). The easiest start is to copy the one closest to your track.
