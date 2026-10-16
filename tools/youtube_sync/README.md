# youtube_sync — read-only YouTube analytics pull (Brain Academy)

Separate tool. It does not touch the frozen V3.0.1 engine. It needs only the Python standard library (no pip install).

It runs on Windows itself, not inside Claude's sandbox: the sandbox cannot reach googleapis.com.

## One-time setup (about 10 minutes, free)

1. Open https://console.cloud.google.com and create a project, for example `brain-academy-analytics`.
2. Go to APIs & Services → Library and enable **YouTube Data API v3** and **YouTube Analytics API**.
3. Set up the OAuth consent screen (Google Auth Platform):
   - user type **External**, any app name, your email as the support contact;
   - under **Audience / Test users**, add the Google account that owns the channel.
4. Go to Clients (Credentials) → Create client → **Desktop app**.
   - Download the JSON.
   - Save it as `%USERPROFILE%\.brain-academy\client_secret.json`. Create the folder if it does not exist.
5. In PowerShell, from the project folder, run:
   `python tools\youtube_sync\yt_sync.py auth`
   - In the browser, pick the account and the **Brain Academy** channel.
   - "Google hasn't verified this app" is expected for your own test app: choose Continue, then Allow.

## Use

    python tools\youtube_sync\yt_sync.py pull

This writes `data/analytics/<timestamp>/snapshot.json`, `videos.csv` and `data/analytics/latest.json` under the repository root, whichever folder you run it from (since experiment layer 1.1; 1.0 wrote relative to the current folder).

Secrets stay in `%USERPROFILE%\.brain-academy\`, outside the repository. The tool never prints tokens. The scopes are read-only.
