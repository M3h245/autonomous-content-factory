#!/bin/bash
# Phase 5 final regression (same commands as CLOUD_HANDOFF.md "Tests" + test_phase5); one log line per suite
R=$(cd "$(dirname "$0")/../../.." && pwd); L=$1; O=$2; : > $L
cd $R/skills
run() { local name=$1; shift; local t0=$(date +%s); "$@" > $O/$name.log 2>&1; local rc=$?; echo "$name rc=$rc $(( $(date +%s) - t0 ))s $(grep -E '^(Ran|OK|FAILED)' $O/$name.log | tr '\n' ' ')" >> $L; }
mkdir -p $O
for t in test_cf_common_identity test_stage_order test_phase0_regressions test_tts_cache test_visual_audit \
         test_reviewer test_futile_retry test_phase2_script test_phase3 test_phase35 test_factory_review; do
  run $t python3 -m unittest content-factory.tests.$t; done
run test_phase2_hooks python3 -m unittest content-factory.tests.test_phase2_hooks
run test_phase4 python3 -m unittest content-factory.tests.test_phase4
run test_phase5 python3 -m unittest content-factory.tests.test_phase5
run test_final_media_metadata python3 -m unittest content-factory.tests.test_final_media_metadata
run test_idea_engine python3 -m unittest content-factory.tests.test_idea_engine
run smoke_v2 python3 content-factory/tests/smoke_v2.py
for k in A B C D; do run bad_$k python3 -m unittest content-factory/tests/test_bad_videos.py -k $k; done
cd $R/fixtures/v1_regression && V=$O/v1 && rm -rf $V && mkdir -p $V && sed "s#{FIXTURE}#$PWD#g" video/storyboard.timed.template.json > $V/timed.json
run v1_render python3 ../../skills/video-production/scripts/render_video.py --storyboard $V/timed.json --voice audio/voice.wav \
    --timing audio/timing.json --out-dir $V/video --result $V/video/result.json --engine kenburns
run v1_subs python3 ../../skills/subtitle-production/scripts/subtitles.py run --timing audio/timing.json \
    --video $V/video/video_nosubs.mp4 --out-dir $V/subs --result $V/subs/result.json --style karaoke
python3 -c "import json,sys; print('v1 results', [json.load(open(f))['status'] for f in sys.argv[1:]])" $V/video/result.json $V/subs/result.json >> $L
echo DONE >> $L
