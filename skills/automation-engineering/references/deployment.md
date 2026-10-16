# Deployment
## Windows (PC with WebUI Forge)
1. `winget install Gyan.FFmpeg` · Python 3.10+ · Node 18+ · `npm install -g @anthropic-ai/claude-code` · sign in or set ANTHROPIC_API_KEY.
2. Unzip the skills bundle, then `python automation-engineering\scripts\install_skills.py --project D:\shorts-ai\factory`.
3. `python D:\shorts-ai\factory\.claude\skills\content-factory\scripts\setup_env.py --out capabilities.json` — fix anything reported.
4. Forge: add `--api` to COMMANDLINE_ARGS in webui-user.bat; doctor then reports `visual.sd_forge`.
5. Copy templates `run_factory.ps1` and `env.example` (→ `.env`) into the project; test once by hand; then schedule with
   `schtasks /Create /SC DAILY /ST 09:00 /TN ContentFactory /TR "powershell -NoProfile -ExecutionPolicy Bypass -File D:\shorts-ai\factory\run_factory.ps1 -Topic \"…\" -Count 2"`.
## Linux/macOS: same steps with `run_factory.sh` and cron. ## GitHub Actions: `content-factory.yml`, secret ANTHROPIC_API_KEY.
## Operations
Logs: `logs/run-*.json` (result text, `total_cost_usd`, session id). Alert on non-zero exit. Keep 30 days of logs.
## Troubleshooting
| Symptom | Fix |
|---|---|
| doctor: ffmpeg filters missing | install a full ffmpeg build (libass, HarfBuzz, FriBidi) |
| Kokoro download fails | allow github.com and release-assets.githubusercontent.com or copy the two model files into the cache |
| headless run stops on permissions | add the tool to --allowedTools; keep --permission-prompts none for unattended runs |
| skills not used headless | don't pass --bare; call `/content-factory` explicitly in the prompt |
| 429 / quota errors | exponential backoff, smaller batches, spread schedule |
