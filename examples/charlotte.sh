#!/bin/bash
# Charlotte Motor Speedway (AC mod by "13x and someguys"): OVAL + ROVAL in one mod.
# Exactly the options used for the version published in the GonkyRacing mod catalog.
#   MOD = the AC track folder (the one with the .kn5 files and models_oval.ini / models_roval.ini)
# NIGHT track: it uses --track-floodlights and --real-ground-plane (without the ground plane, the
# track stays black).
set -e
cd "$(dirname "$0")/.."
MOD="${MOD:?set MOD=<AC track folder>}"
COMMON="--cc0-families grass --pit-limiter 100 --max-ai 32 \
  --author-lights --stand-floodlights --track-floodlights --real-ground-plane --night-glow all \
  --start-lights --ambience Daytona --ai-centre-asphalt --pit-distances --asphalt-width \
  --grid-at-finish --reiza-style-map --translucent-fences --asphalt-normal --asphalt-gloss \
  --ac-layers --ambient-sound --tv-cameras --geo 35.352,-80.6839,230,-5 \
  --group Charlotte_Motor_Speedway"
python3 convert_ac.py --folder "$MOD" --layout oval --name charlottecms \
  --title "Charlotte Motor Speedway (Oval)" --date 2020-8-11 --corners 4 --oval \
  --variant Oval --order 1 $COMMON
# the Roval forms its grid on the oval's front stretch: it has a chicane before the finish line
python3 convert_ac.py --folder "$MOD" --layout roval --name charlotteroval --grid-from oval \
  --title "Charlotte Motor Speedway (Roval)" --date 2020-10-11 --corners 17 \
  --variant Roval --order 2 $COMMON
WORK=$(cd converter && python3 -c "import rutas; print(rutas.TRABAJO)")
python3 join_layouts.py charlotte_motor_speedway.zip --group Charlotte_Motor_Speedway \
  "$WORK/charlottecms/charlottecms.zip:charlottecms:Oval:1" \
  "$WORK/charlotteroval/charlotteroval.zip:charlotteroval:Roval:2"
