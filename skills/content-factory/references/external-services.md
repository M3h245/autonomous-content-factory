# External services (optional adapters; none is required for the free local pipeline)

Run anything that needs a key on your own machine (or CI) with the key in an environment variable — never in chat,
files or logs. In claude.ai the sandbox blocks these hosts; `doctor.py` reports reachability and key presence.

| Service | Endpoint / access | Auth | Inputs | Outputs | Role | Env | Status |
|---|---|---|---|---|---|---|---|
| ElevenLabs TTS | `POST /v1/text-to-speech/{voice_id}/with-timestamps?output_format=pcm_24000` | header `xi-api-key` | text, model_id | base64 PCM + character alignment | AUDIO backend (premium voices, Persian/Arabic) | ELEVENLABS_API_KEY | adapter in tts.py, not live-tested |
| Stable Diffusion WebUI Forge (local) | `POST {CF_FORGE_URL}/sdapi/v1/txt2img`, `GET /sdapi/v1/options` | none (start Forge with `--api`) | prompt, negative, seed, steps, cfg, size, sampler, scheduler | base64 PNG, checkpoint name | VISUAL_PLAN image backend | CF_FORGE_URL | adapter in storyboard_tool.py, not live-tested |
| Pexels | `GET https://api.pexels.com/v1/search?query=…&orientation=portrait` | header `Authorization: KEY` | query | photo URLs, photographer, page URL | VISUAL_PLAN stock backend (credit recorded) | PEXELS_API_KEY | adapter, not live-tested |
| YouTube Data API v3 | `search.list`, `videos.list` (API key); `videos.insert` (OAuth, upload scope) | API key / OAuth 2.0 | query, publishedAfter, videoDuration=short | ids, titles, view counts | trend-intelligence signals; uploads stay manual | YOUTUBE_API_KEY | not implemented as script; documented |
| YouTube Analytics API | `reports.query` | OAuth 2.0 (read-only analytics scope) | channel, metrics, dims | per-video retention/views | content-analytics alternative to CSV | YOUTUBE_OAUTH_CLIENT_SECRETS | documented |
| vidIQ (claude.ai connector) | connector tools e.g. trending videos, outliers, keyword research | OAuth via connector | niche/keywords | trending/outlier videos, keyword stats | trend-intelligence | — | in directory, not connected |
| Supermetrics (claude.ai connector) | connector data_query tools | OAuth via connector | accounts, fields, dates | platform metrics | content-analytics | — | in directory, not connected |
| Google Trends | manual CSV export from trends.google.com | none | terms, region, period | interest series | trend-intelligence `--gt-csv` | — | parser implemented |
| Anthropic API | used by Claude Code headless | ANTHROPIC_API_KEY or Claude login | prompt `/content-factory …` | run log JSON (`total_cost_usd`) | automation-engineering | ANTHROPIC_API_KEY | documented |
| TikTok Content Posting API · Instagram Graph API | platform publishing APIs | OAuth + app review | video, caption | post id | publishing — intentionally not automated | — | out of scope |

Rate limits and quotas change; adapters should back off exponentially on 429/5xx and record the provider and model
in provenance. Paid generative video is deliberately not wired in: per-clip costs and realism labels apply.
