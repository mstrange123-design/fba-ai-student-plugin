#!/usr/bin/env python
"""create_feed_files.py — create the user's live-dashboard feed files on THEIR Drive.

The two live tiles (Lifecycle Stages, Cash Flow Equilibrium) each read a small JSON feed file
from Google Drive. The daily robot only UPDATES an existing file — it never creates one. This
script is the missing first domino: run it ONCE during setup (after the Google token exists) and it:

  1. creates the two feed files on the user's Drive (idempotent — if a feed file
     with the same name already exists in this app's Drive namespace, it is reused),
  2. writes each file's id into the plugin config (`_shared/config.json` →
     live_artifact_feeds.feeds.<key>.drive_file_id),
  3. writes the robot's copies (`item_journey_config.json` → lifecycle_feed /
     cash-flow_feed .drive_file_id) if --robot-config is given.

Stdlib only. Uses GOOGLE_TOKEN_JSON (base64, same token google_oauth_local.py captured)
or --token-file. File ids are not secrets — they print in full so you can eyeball them.

Usage:
  python -X utf8 create_feed_files.py --config <path to _shared/config.json>
  python -X utf8 create_feed_files.py --config ... --robot-config <path to item_journey_config.json>
  python -X utf8 create_feed_files.py --config ... --dry-run     # show what would happen
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

# feed key (plugin config) -> Drive file name, robot config block key
FEEDS = [
    ("lifecycle-stages", "lifecycle-feed.json", "lifecycle_feed"),
    ("fba-cash-flow-equilibrium", "cash-flow-feed.json", "cash-flow_feed"),
]

SEED = {"status": "awaiting first robot run", "$created_by": "setup-wizard create_feed_files.py"}


def default_secrets_dir():
    # same convention as google_oauth_local.py, which writes token.json there in Step 6
    home = os.path.expanduser("~")
    if os.name == "nt":
        return os.path.join(home, "AppData", "Local", "fba-secrets")
    return os.path.join(home, "fba-secrets")


def load_token(token_file):
    if token_file:
        with open(token_file, "r", encoding="utf-8") as f:
            return json.load(f)
    raw = os.environ.get("GOOGLE_TOKEN_JSON")
    if raw:
        try:
            return json.loads(base64.b64decode(raw).decode("utf-8"))
        except Exception:
            try:
                return json.loads(raw)
            except Exception:
                return None
    # last resort: the token.json google_oauth_local.py just wrote (Step 6)
    fallback = os.path.join(os.environ.get("FBA_SECRETS_DIR") or default_secrets_dir(), "token.json")
    if os.path.isfile(fallback):
        with open(fallback, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def refresh_access_token(tok):
    fields = {
        "grant_type": "refresh_token",
        "refresh_token": tok["refresh_token"],
        "client_id": tok["client_id"],
        "client_secret": tok["client_secret"],
    }
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))["access_token"]


def api(method, url, access, body=None, content_type="application/json"):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + access,
        **({"Content-Type": content_type} if data else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def find_existing(access, name):
    """drive.file scope only sees files THIS app created — a clean namespace to search."""
    q = urllib.parse.quote(f"name = '{name}' and trashed = false")
    res = api("GET", f"{DRIVE_FILES}?q={q}&fields=files(id,name)&pageSize=5", access)
    files = res.get("files", [])
    return files[0]["id"] if files else None


def create_file(access, name):
    """files.create with multipart upload: metadata + a small seed JSON body."""
    boundary = "feedboundary" + uuid.uuid4().hex[:12]
    meta = json.dumps({"name": name, "mimeType": "application/json"})
    seed = json.dumps(SEED)
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            f"--{boundary}\r\nContent-Type: application/json\r\n\r\n{seed}\r\n"
            f"--{boundary}--").encode("utf-8")
    res = api("POST", f"{DRIVE_UPLOAD}?uploadType=multipart&fields=id,name", access, body,
              content_type=f"multipart/related; boundary={boundary}")
    return res["id"]


def patch_json_file(path, mutate):
    """Read-modify-write a JSON config in place (never blind-overwrite)."""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    mutate(cfg)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="path to the plugin _shared/config.json")
    ap.add_argument("--robot-config", default=None, help="path to the robot item_journey_config.json")
    ap.add_argument("--token-file", default=None, help="raw token JSON path (else GOOGLE_TOKEN_JSON env)")
    ap.add_argument("--dry-run", action="store_true", help="look up / plan only, write nothing")
    a = ap.parse_args()

    if not os.path.isfile(a.config):
        print(f"❌ Feeds: no config at {a.config}")
        return 2
    tok = load_token(a.token_file)
    if not tok:
        print("❌ Feeds: no Google token — run google_oauth_local.py first (writes token.json to the "
              "secrets dir + GOOGLE_TOKEN_JSON to .env), or pass --token-file <secrets-dir>/token.json.")
        return 2
    for k in ("refresh_token", "client_id", "client_secret"):
        if k not in tok:
            print(f"❌ Feeds: token JSON missing '{k}' — re-run google_oauth_local.py")
            return 2

    try:
        access = refresh_access_token(tok)
    except urllib.error.HTTPError as e:
        print(f"❌ Feeds: token refresh failed ({e.code}) — token revoked or client changed. "
              f"Re-run google_oauth_local.py.\n   {e.read().decode('utf-8', 'replace')[:300]}")
        return 3
    except Exception as e:
        print(f"❌ Feeds: could not reach Google — {e}")
        return 3

    ids = {}
    for key, name, _robot_key in FEEDS:
        try:
            fid = find_existing(access, name)
            if fid:
                print(f"✅ {key:<28} exists    → {fid}   ({name})")
            elif a.dry_run:
                print(f"·  {key:<28} would create ({name})")
                continue
            else:
                fid = create_file(access, name)
                print(f"✅ {key:<28} created   → {fid}   ({name})")
            ids[key] = fid
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            print(f"❌ Feeds: Drive call failed for {name} ({e.code}).\n   {body[:300]}")
            return 4

    if a.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    def mutate_plugin(cfg):
        laf = cfg.setdefault("live_artifact_feeds", {})
        feeds = laf.setdefault("feeds", {})
        for key, name, _rk in FEEDS:
            if key not in ids:
                continue
            entry = feeds.setdefault(key, {"drive_feed_name": name})
            entry["drive_file_id"] = ids[key]
    try:
        patch_json_file(a.config, mutate_plugin)
        print(f"\n✅ Wrote feed ids into {a.config}")
    except Exception as e:
        print(f"❌ Feeds: created on Drive but couldn't write {a.config} — {e}")
        return 5

    if a.robot_config:
        if not os.path.isfile(a.robot_config):
            print(f"⚠️  Robot config not found at {a.robot_config} — paste these by hand: "
                  f"lifecycle_feed={ids.get('lifecycle-stages')}, "
                  f"cash-flow_feed={ids.get('fba-cash-flow-equilibrium')}")
        else:
            def mutate_robot(cfg):
                for key, _name, robot_key in FEEDS:
                    if robot_key and key in ids:
                        cfg.setdefault(robot_key, {})["drive_file_id"] = ids[key]
            try:
                patch_json_file(a.robot_config, mutate_robot)
                print(f"✅ Wrote feed ids into {a.robot_config}")
            except Exception as e:
                print(f"❌ Feeds: couldn't write {a.robot_config} — {e}")
                return 5
    else:
        print("ℹ️  No --robot-config given — remember the robot repo's item_journey_config.json "
              "needs lifecycle_feed / cash-flow_feed .drive_file_id too.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
