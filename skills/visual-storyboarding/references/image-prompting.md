# Image prompting (local WebUI Forge or image APIs)
Forge: launch with `--api`; `CF_FORGE_URL` defaults to http://127.0.0.1:7860. On a 4 GB GPU use SD 1.5-class
checkpoints at 576×1024, 20–28 steps, sampler "DPM++ 2M" + scheduler "Karras", CFG 5–7, then the script upscales.
Prompt order: subject → setting → style → lighting → framing. Default framing is appended: "wide shot, full body,
environment visible" (override with CF_SD_FRAMING). Keep a fixed series style string in `style.sd_style` and fixed
seeds per scene for reproducible reruns. Default negative prompt removes text, watermarks, close-up crops, anatomy errors.
Photoreal people or real places → `"realistic": true` in the scene so asset-provenance applies AI labels.
Checkpoint licenses vary: add each checkpoint to `RUN/licenses.json` after reading its model card.
