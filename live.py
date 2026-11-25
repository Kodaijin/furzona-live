#!/usr/bin/env python3
"""
Furzona live-DJ feed for the VRChat world (no changes to the AzuraCast server).

Reads AzuraCast's public now-playing API, and when a DJ goes live / changes / goes off air, writes a tiny site:
  site/live.json      {"v":1,"live":true,"dj":"Name","song":"Artist - Title","slot":3,"art":true,"since":"...","updated":"..."}
                      ("song" = the track the live DJ is sending as metadata; empty when AutoDJ is playing)
  site/art-<slot>.png the DJ's streamer art, 512x512, transparency kept (+ a .jpg copy for older world versions) (slot rotates 0..7 so the world never sees a stale cached image)
The workflow publishes that folder to GitHub Pages (*.github.io is on VRChat's trusted list for string + image loading).

Usage:  python live.py --once            (one check)
        python live.py --loop 280 --every 20   (poll for 280 s)
Env:    NOWPLAYING_URL  (default https://furzona.radio/api/nowplaying/clubradio)
        PAGES_URL       (the published site, e.g. https://yourname.github.io/furzona-live/) - used to read the last state
Exit code 10 = something changed (the workflow then deploys); 0 = no change.
"""
import io, json, os, sys, time, urllib.request, datetime, argparse

NOWPLAYING_URL = os.environ.get("NOWPLAYING_URL", "https://furzona.radio/api/nowplaying/clubradio")
PAGES_URL = os.environ.get("PAGES_URL", "").rstrip("/") + "/"
SITE = "site"
SLOTS = 8
UA = {"User-Agent": "furzona-live-feed/1.0 (+github actions)"}

def get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

def read_previous():
    # 1) what this run already wrote, 2) what's live on Pages, 3) nothing
    for src in (os.path.join(SITE, "live.json"), PAGES_URL + "live.json" if PAGES_URL != "/" else None):
        if not src: continue
        try:
            raw = open(src, "rb").read() if not src.startswith("http") else get(src + "?t=" + str(int(time.time())))
            return json.loads(raw)
        except Exception:
            pass
    return {"live": False, "dj": "", "slot": -1, "key": ""}

def fetch_state():
    np = json.loads(get(NOWPLAYING_URL))
    if isinstance(np, list): np = np[0]
    live = (np.get("live") or {})
    is_live = bool(live.get("is_live"))
    dj = (live.get("streamer_name") or "").strip() if is_live else ""
    art = (live.get("art") or "").strip() if is_live else ""
    song = ""
    if is_live:
        s = ((np.get("now_playing") or {}).get("song") or {})
        artist, title = (s.get("artist") or "").strip(), (s.get("title") or "").strip()
        song = (artist + " - " + title) if artist and title else (title or (s.get("text") or "").strip())
    return is_live, dj, art, (live.get("broadcast_start") if is_live else None), song[:120]

BOARD_BG = (9, 10, 15)   # the board's panel colour: what transparent art sits on in the .jpg copy

def make_art(url, base):
    """Writes <base>.png (keeps transparency) and <base>.jpg (flattened on the board colour, for older world versions).
    Transparent art (logos) is fitted inside the square with see-through padding; solid art is centre-cropped to fill it."""
    from PIL import Image
    im = Image.open(io.BytesIO(get(url)))
    has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA")
    if has_alpha and im.getextrema()[3][0] < 255:
        im.thumbnail((512, 512), Image.LANCZOS)                   # fit, keep the whole logo
        sq = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        sq.paste(im, ((512 - im.width) // 2, (512 - im.height) // 2), im)
        im = sq
    else:
        w, h = im.size; s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((512, 512), Image.LANCZOS)
    im.save(base + ".png", "PNG", optimize=True)
    flat = Image.new("RGB", im.size, BOARD_BG); flat.paste(im, (0, 0), im)
    flat.save(base + ".jpg", "JPEG", quality=88)

def step(prev):
    is_live, dj, art, since, song = fetch_state()
    art_key = f"png2|{is_live}|{dj}|{art}"   # png2: art is now also written as .png with transparency (bumping this re-makes it)
    key = art_key + "|" + song           # a new track only updates the text; the art is only re-made when the DJ / art changes
    if key == prev.get("key"):
        return prev, False
    os.makedirs(SITE, exist_ok=True)
    slot = prev.get("slot", -1)
    has_art = False
    if art_key == prev.get("art_key") and prev.get("art"):
        has_art = True                   # same DJ + art: keep the slot that's already published (the workflow copies it back in)
    elif is_live and art:
        slot = (slot + 1) % SLOTS if slot >= 0 else 0
        try:
            make_art(art, os.path.join(SITE, f"art-{slot}")); has_art = True
        except Exception as e:
            print("art download failed:", e, file=sys.stderr)
    state = {"v": 1, "live": is_live, "dj": dj, "song": song, "slot": slot, "art": has_art,
             "since": str(since or ""), "updated": now_iso(), "key": key, "art_key": art_key}
    with open(os.path.join(SITE, "live.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset=utf-8><title>Furzona live feed</title><pre>" + json.dumps(state, indent=1, ensure_ascii=False) + "</pre>")
    print(("LIVE: " + dj + ((" | " + song) if song else "")) if is_live else "off air (AutoDJ)", "slot", slot, "art", has_art)
    return state, True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true"); ap.add_argument("--loop", type=int, default=0); ap.add_argument("--every", type=int, default=20)
    a = ap.parse_args()
    prev = read_previous(); changed = False
    end = time.time() + (a.loop if a.loop > 0 else 0)
    while True:
        try:
            prev, c = step(prev); changed = changed or c
        except Exception as e:
            print("now-playing check failed:", e, file=sys.stderr)
        if a.once or time.time() + a.every > end: break
        if changed: break          # deploy as soon as something changes; the next run carries on watching
        time.sleep(a.every)
    sys.exit(10 if changed else 0)

if __name__ == "__main__":
    main()
