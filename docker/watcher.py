#!/usr/bin/env python3
"""
Furzona live watcher (optional, runs on your own server).

Checks AzuraCast's public now-playing info every few seconds. When the live DJ, their art or the track changes,
it asks GitHub to run the "Furzona live DJ feed" workflow right away (quick mode), so the VRChat board updates in
about a minute instead of waiting for GitHub's 5-minute schedule. It only makes outgoing requests - no ports,
no tunnel needed - and it never touches the radio server's settings.

Settings (environment variables, see .env.example):
  GITHUB_TOKEN    fine-grained token: this repo only, permission "Actions: Read and write"   (required)
  GITHUB_REPO     owner/repo                    (default Kodaijin/furzona-live)
  NOWPLAYING_URL  AzuraCast now-playing API     (default https://furzona.radio/api/nowplaying/clubradio)
  POLL_SECONDS    how often to check            (default 10)
  MIN_GAP_SECONDS shortest time between two GitHub runs (default 30)
"""
import json, os, sys, time, urllib.request, urllib.error

TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPO", "Kodaijin/furzona-live").strip()
NOWPLAYING_URL = os.environ.get("NOWPLAYING_URL", "https://furzona.radio/api/nowplaying/clubradio").strip()
POLL = max(3, int(os.environ.get("POLL_SECONDS", "10")))
MIN_GAP = max(10, int(os.environ.get("MIN_GAP_SECONDS", "30")))
UA = "furzona-live-watcher/1.0"

def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)

def now_playing_key():
    req = urllib.request.Request(NOWPLAYING_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        np = json.loads(r.read())
    if isinstance(np, list): np = np[0]
    live = np.get("live") or {}
    if not live.get("is_live"):
        return "off", "off air (AutoDJ)"
    song = ((np.get("now_playing") or {}).get("song") or {})
    track = ((song.get("artist") or "") + " - " + (song.get("title") or "")).strip(" -") or (song.get("text") or "")
    dj = (live.get("streamer_name") or "").strip()
    return f"live|{dj}|{(live.get('art') or '').strip()}|{track}", f"LIVE {dj} | {track}"

def trigger():
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/live.yml/dispatches"
    body = json.dumps({"ref": "main", "inputs": {"quick": "true"}}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status

def main():
    if not TOKEN:
        log("GITHUB_TOKEN is not set - see .env.example"); sys.exit(1)
    log(f"watching {NOWPLAYING_URL} every {POLL}s -> {REPO}")
    last_key, pending, last_run = None, False, 0.0
    while True:
        try:
            key, desc = now_playing_key()
            if key != last_key:
                log("change:", desc); last_key = key; pending = True
        except Exception as e:
            log("now-playing check failed:", e)
        if pending and time.time() - last_run >= MIN_GAP:
            try:
                st = trigger(); last_run = time.time(); pending = False
                log("asked GitHub to publish (HTTP", st, ")")
            except urllib.error.HTTPError as e:
                log("GitHub said", e.code, e.read()[:200]); last_run = time.time()   # retry after MIN_GAP
            except Exception as e:
                log("GitHub request failed:", e); last_run = time.time()
        time.sleep(POLL)

if __name__ == "__main__":
    main()
