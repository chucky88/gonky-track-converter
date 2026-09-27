#!/bin/bash
# Circuito del Jarama (AC mod by shin956, from GTR2/rFactor): THREE historic layouts in one mod.
# The options used for the version in the GonkyRacing mod catalog.
#   MOD = the AC track folder
# DAY track. ⚠️ If you want it at night, add --track-floodlights --real-ground-plane.
set -e
cd "$(dirname "$0")/.."
MOD="${MOD:?set MOD=<AC track folder>}"
COMMON="--geo 40.6170,-3.5857,620,1 --ambience Barcelona --cc0-families grass \
  --pit-limiter 60 --max-ai 32 --author-lights --start-lights --ai-centre-asphalt --pit-distances \
  --asphalt-width --grid-at-finish --reiza-style-map --translucent-fences --asphalt-normal \
  --asphalt-gloss --asphalt-fresnel 0.67 --ac-layers --ambient-sound --tv-cameras \
  --group Circuito_del_Jarama"
python3 convert_ac.py --folder "$MOD" --layout 2022 --name jarama2022 \
  --title "Circuito del Jarama (2022)" --date 2022-6-12 --corners 13 --variant 2022 --order 1 $COMMON
python3 convert_ac.py --folder "$MOD" --layout 2009 --name jarama2009 \
  --title "Circuito del Jarama (2009)" --date 2009-6-14 --corners 13 --variant 2009 --order 2 $COMMON
python3 convert_ac.py --folder "$MOD" --layout 1995_bpr --name jarama1995 \
  --title "Circuito del Jarama (1995 BPR)" --date 1995-3-12 --corners 13 --variant 1995_BPR --order 3 $COMMON
WORK=$(cd converter && python3 -c "import rutas; print(rutas.TRABAJO)")
python3 join_layouts.py circuito_del_jarama.zip --group Circuito_del_Jarama \
  "$WORK/jarama2022/jarama2022.zip:jarama2022:2022:1" \
  "$WORK/jarama2009/jarama2009.zip:jarama2009:2009:2" \
  "$WORK/jarama1995/jarama1995.zip:jarama1995:1995_BPR:3"
