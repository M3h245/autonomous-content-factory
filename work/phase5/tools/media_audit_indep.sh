#!/bin/bash
# Independent audit of a publishing package (ffprobe tags, strings scan, full decode, AI labels) — not the factory's code
D=$1; F=$D/final.mp4
echo "== $D"
ffprobe -v error -show_entries format_tags:stream_tags -of compact "$F" | sed 's/^/tags: /'
for f in $F $D/thumbnail.jpg $D/cover.jpg; do
  hits=$(strings -n 6 "$f" | grep -Eic "/tmp|/home|scratchpad|claude|kokoro|doodle|factory|provenance|seed|run_id|\.py\b|users\\\\" )
  echo "strings hits in $(basename $f): $hits"
done
strings -n 6 "$F" | grep -Ei "/tmp|/home|scratchpad|claude|kokoro|provenance|run_id" | head -5
err=$(ffmpeg -v error -i "$F" -f null - 2>&1 | head -3); echo "decode errors: ${err:-none}"
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate,sample_rate -of compact "$F"
python3 -c "
import json,sys
m=json.load(open(sys.argv[1]+'/metadata.json'))
print('AI labels: youtube.altered_or_synthetic=', m['youtube'].get('altered_or_synthetic'), '| tiktok.ai_generated_label=', m['tiktok'].get('ai_generated_label'), '| instagram.ai_info=', m['instagram'].get('ai_info'))
print('title:', m['youtube'].get('title'))
d=m['youtube'].get('description','')
print('disclosure line in description:', [l for l in d.splitlines() if 'AI' in l or 'synthetic' in l.lower()][:2])
" "$D"
