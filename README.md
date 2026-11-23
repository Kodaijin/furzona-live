# Furzona live-DJ feed

Feeds the **Live DJ board** in the VRChat world *Aftermath REDUX*: who's live on Furzona Radio, their streamer art,
and the track they're sending. Nothing on the AzuraCast server is changed — it only reads the station's public
now-playing API.

The feed is published to **GitHub Pages** (`https://kodaijin.github.io/furzona-live/`) because `*.github.io` is on
VRChat's trusted list: every player sees the board without turning on "Allow Untrusted URLs".

```
live.json        {"v":1,"live":true,"dj":"DJ Name","song":"Artist - Title","slot":3,"art":true,...}
art-<slot>.jpg   the DJ's art, 512x512 (slot rotates 0-7 so VRChat never shows a stale cached picture)
```

## How it updates

| Path | Speed | Needs |
|---|---|---|
| GitHub schedule (`.github/workflows/live.yml`) | new DJ / track within ~5 min (GitHub's cron can run late) | nothing |
| Docker watcher (`docker/`), optional | ~1 min | a small container on your server + a GitHub token |

Both can run together; the schedule is the fallback if the container is down.

## One-time setup

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Actions → Furzona live DJ feed → Run workflow.** After it finishes, open
   `https://kodaijin.github.io/furzona-live/live.json`.
3. In Unity: `Assets/Live DJ/live-base-url.txt` = `https://kodaijin.github.io/furzona-live/`, then
   **Tools → Aftermath → Live DJ → Build Live DJ Board**.

Scheduled workflows pause after 60 days without a commit to the repo. If the board stops updating, open the
Actions tab and re-enable the workflow (or push any small commit).

## Optional: the Docker watcher (instant updates)

It only makes outgoing requests (to your radio and to GitHub) — no open ports, no Cloudflare tunnel needed.

1. Make a token: GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate new token.
   - Repository access: **Only select repositories → furzona-live**
   - Permissions: **Actions → Read and write** (nothing else)
2. On your server, in the `docker/` folder:
   ```sh
   cp .env.example .env      # paste the token into .env (never commit .env)
   docker compose up -d --build
   docker compose logs -f    # "change: LIVE DJ ..." then "asked GitHub to publish (HTTP 204)"
   ```

## Settings

- Station URL: repo **Settings → Secrets and variables → Actions → Variables → `NOWPLAYING_URL`**
  (default `https://furzona.radio/api/nowplaying/clubradio`). The watcher uses `NOWPLAYING_URL` in `.env`.
- Local test: `python live.py --once` (writes `site/`).
