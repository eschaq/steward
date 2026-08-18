#!/usr/bin/env bash
# Render every card to out/. Two formats, on purpose:
#
#   full-frame cards -> H.264 MP4, which DaVinci takes without ceremony
#   lower-thirds     -> ProRes 4444 .mov, because they overlay live footage and
#                       need a real alpha channel. H.264 has none; a "transparent"
#                       MP4 would arrive as a black box over the recording.
set -euo pipefail
mkdir -p out

for c in opening problem positioning stack closing; do
  echo "  $c -> mp4"
  npx remotion render "$c" "out/$c.mp4" --codec=h264 --image-format=png --log=error
done

for c in lt1-two-people lt2-asks-answers lt3-nobody-else lt4-learned lt5-honest lt6-full-circle; do
  echo "  $c -> prores 4444 (alpha)"
  npx remotion render "$c" "out/$c.mov" \
    --codec=prores --prores-profile=4444 \
    --image-format=png --pixel-format=yuva444p10le --log=error
done
echo "done"
