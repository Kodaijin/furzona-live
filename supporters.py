#!/usr/bin/env python3
"""
Furzona supporter wall feed (VRChat world: the supporter wall in the tunnel).

Reads the campaign's members from the Patreon API (creator token in the PATREON_TOKEN secret), keeps only
active, paying patrons, groups them by their highest tier, adds the hand-written special thanks, and writes
  site/supporters.json
    {"v":1,"updated":"...","count":12,
     "tiers":[{"name":"Tier name","amount":1000,"names":["A","B"]}, ...],   # highest tier first, names A-Z
     "special":[{"name":"Lain","note":"truss logo edit"}, ...]}

Hand-edited files in this repo (edit them on GitHub; saving them republishes):
  special-thanks.txt   one per line:  Name | optional note        (# = comment)
  hidden.txt           supporter names to leave off the wall, one per line (exact name, any case)

Usage:  python supporters.py                 rebuild if the published list is older than --max-age (default 6 h)
        python supporters.py --force         rebuild now
Env:    PATREON_TOKEN (required to rebuild), PAGES_URL (to read the published list)
Exit 10 = site/supporters.json was rebuilt (deploy needed); 0 = nothing to do (the published one is kept).
"""
import argparse, datetime, json, os, sys, time, urllib.parse, urllib.request, urllib.error

API = os.environ.get("PATREON_API", "https://www.patreon.com/api/oauth2/v2")   # override only for local tests
TOKEN = os.environ.get("PATREON_TOKEN", "").strip()
PAGES_URL = os.environ.get("PAGES_URL", "").rstrip("/") + "/"
SITE = "site"
UA = "furzona-supporter-wall/1.0 (+github actions)"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def api(url):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", "replace")
        if e.code == 401:
            sys.exit("Patreon said 401 (token expired or wrong). Make a new Creator's Access Token and update the "
                     "PATREON_TOKEN secret. The wall keeps showing the last published list meanwhile.")
        sys.exit(f"Patreon API error {e.code}: {body}")


def read_lines(path):
    if not os.path.exists(path):
        return []
    out = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln)
    return out


def published_age():
    """Seconds since the published supporters.json was made (None = not published yet)."""
    if PAGES_URL == "/":
        return None
    try:
        req = urllib.request.Request(PAGES_URL + "supporters.json?t=" + str(int(time.time())), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        t = datetime.datetime.fromisoformat(d["updated"])
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    except Exception:
        return None


def fetch_members():
    camps = api(API + "/campaigns?fields%5Bcampaign%5D=creation_name,vanity")
    if not camps.get("data"):
        sys.exit("No Patreon campaign found for this token.")
    cid = camps["data"][0]["id"]
    q = {
        "include": "currently_entitled_tiers",
        "fields[member]": "full_name,patron_status,currently_entitled_amount_cents",
        "fields[tier]": "title,amount_cents",
        "page[count]": "500",
    }
    url = f"{API}/campaigns/{cid}/members?" + urllib.parse.urlencode(q)
    members, tiers = [], {}
    while url:
        page = api(url)
        for inc in page.get("included", []):
            if inc.get("type") == "tier":
                a = inc.get("attributes") or {}
                tiers[inc["id"]] = {"name": (a.get("title") or "").strip(), "amount": int(a.get("amount_cents") or 0)}
        members += page.get("data", [])
        url = ((page.get("links") or {}).get("next")) or None
    return members, tiers


def build():
    members, tiers = fetch_members()
    hidden = {h.lower() for h in read_lines("hidden.txt")}
    groups = {}   # tier key -> {"name","amount","names"}
    count = 0
    for m in members:
        a = m.get("attributes") or {}
        if a.get("patron_status") != "active_patron" or int(a.get("currently_entitled_amount_cents") or 0) <= 0:
            continue   # only people paying right now
        name = " ".join((a.get("full_name") or "").split())
        if not name or name.lower() in hidden:
            continue
        rel = ((m.get("relationships") or {}).get("currently_entitled_tiers") or {}).get("data") or []
        best = None
        for t in rel:
            ti = tiers.get(t.get("id"))
            if ti and (best is None or ti["amount"] > best["amount"]):
                best = ti
        if best is None:   # paying without a tier (custom pledge)
            amt = int(a.get("currently_entitled_amount_cents") or 0)
            best = {"name": "Supporters", "amount": amt}
        key = best["name"] or "Supporters"
        g = groups.setdefault(key, {"name": key, "amount": best["amount"], "names": []})
        g["amount"] = max(g["amount"], best["amount"])
        g["names"].append(name)
        count += 1
    out_tiers = sorted(groups.values(), key=lambda g: -g["amount"])
    for g in out_tiers:
        g["names"] = sorted(set(g["names"]), key=str.lower)
    special = []
    for ln in read_lines("special-thanks.txt"):
        name, _, note = ln.partition("|")
        if name.strip():
            special.append({"name": name.strip(), "note": note.strip()})
    return {"v": 1, "updated": now_iso(), "count": count, "tiers": out_tiers, "special": special}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-age", type=int, default=6 * 3600)
    a = ap.parse_args()
    if not a.force:
        age = published_age()
        if age is not None and age < a.max_age:
            print(f"supporters.json is {int(age / 60)} min old - keeping it")
            sys.exit(0)
    if not TOKEN:
        sys.exit("PATREON_TOKEN is not set (repo Settings > Secrets and variables > Actions).")
    state = build()
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "supporters.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    print(f"supporters: {state['count']} in {len(state['tiers'])} tiers, {len(state['special'])} special thanks")
    sys.exit(10)


if __name__ == "__main__":
    main()
