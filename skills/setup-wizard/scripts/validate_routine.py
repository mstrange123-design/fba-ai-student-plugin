#!/usr/bin/env python
"""validate_routine.py — prove the user's daily cloud Routine actually ran.

The Routine's whole job is to write fresh data into the user's Google Sheet every
morning. So "did the engine run?" = "was the FBA Ops Sheet updated recently?". This
refreshes the Google token and asks Drive when the sheet was last modified. Fresh
(within --max-age-hours, default 36) = ✅ the Routine is alive. Stale = ❌ run it once.

Uses the same GOOGLE_TOKEN_JSON the Google lesson already produced — no new credential.
Stdlib only (urllib); never prints a secret.

Reads:
  GOOGLE_TOKEN_JSON (base64 authorized-user token) or --token-file
  OPS_SHEET_ID (the sheet the Routine writes) or --sheet-id

Usage:
  python -X utf8 validate_routine.py --sheet-id <id>
  python -X utf8 validate_routine.py --sheet-id <id> --max-age-hours 48

Exit 0 = ✅ ran recently. Non-zero = ❌ (stale, or couldn't check).
"""
import argparse
import base64
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def load_token(args):
    if args.token_file:
        with open(args.token_file, "r", encoding="utf-8") as f:
            return json.load(f)
    raw = os.environ.get("GOOGLE_TOKEN_JSON")
    if not raw:
        return None
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:
        try:
            return json.loads(raw)
        except Exception:
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


def parse_rfc3339(s):
    """Parse Drive's modifiedTime (e.g. 2026-06-19T11:23:45.123Z) to aware UTC datetime."""
    s = s.strip().replace("Z", "")
    base = s.split(".")[0]
    dt = datetime.datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    return dt.replace(tzinfo=datetime.timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", default=os.environ.get("OPS_SHEET_ID"))
    ap.add_argument("--feed-id", default=os.environ.get("LIFECYCLE_FEED_FILE_ID"),
                    help="lifecycle feed file id (preferred) — the Routine rewrites it every run, "
                         "and because THIS app created it the narrow drive.file scope can stat it; "
                         "a hand-copied sheet cannot (Drive returns 404).")
    ap.add_argument("--token-file", default=None)
    ap.add_argument("--max-age-hours", type=float, default=36.0)
    a = ap.parse_args()

    # Prefer the feed file. It's app-created (drive.file scope CAN read its modifiedTime), the
    # Routine rewrites it on every run, and a user's sheet is hand-copied (Drive 404s on it).
    target_id = a.feed_id or a.sheet_id
    is_feed = bool(a.feed_id)
    if not target_id:
        print("❌ Routine: no feed id or OPS_SHEET_ID — they come with the Google/dashboards lesson")
        return 2

    tok = load_token(a)
    if not tok:
        print("❌ Routine: no Google token — set GOOGLE_TOKEN_JSON (base64) or pass --token-file")
        return 2
    for k in ("refresh_token", "client_id", "client_secret"):
        if k not in tok:
            print(f"❌ Routine: token JSON missing '{k}' — re-run the Google consent flow")
            return 2

    try:
        access = refresh_access_token(tok)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"❌ Routine: Google token refresh failed ({e.code}) — fix the Google lesson first.\n"
              f"   {body[:200]}")
        return 3
    except Exception as e:
        print(f"❌ Routine: could not reach Google token endpoint — {e}")
        return 3

    url = (f"https://www.googleapis.com/drive/v3/files/{target_id}"
           f"?fields=modifiedTime,name&supportsAllDrives=true")
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + access})
        with urllib.request.urlopen(req, timeout=30) as r:
            meta = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 403:
            hint = ("the Google token doesn't have Drive access — re-run the Google consent "
                    "flow and approve Drive, then try again")
        elif e.code == 404:
            hint = ("the feed file id is wrong or the dashboards weren't created yet — "
                    "run create_feed_files.py" if is_feed
                    else "the sheet id is wrong, or the sheet isn't shared with this Google account")
        else:
            hint = "check the Drive API is enabled on the OAuth app"
        print(f"❌ Routine: couldn't read the sheet's last-update time ({e.code}) — {hint}.\n"
              f"   {body[:200]}")
        return 4
    except Exception as e:
        print(f"❌ Routine: could not reach the Drive API — {e}")
        return 4

    name = meta.get("name", "(your sheet)")
    mod = meta.get("modifiedTime")
    if not mod:
        print("❌ Routine: Drive didn't return a modified time — can't tell if the Routine ran.")
        return 4
    try:
        modified = parse_rfc3339(mod)
        now = datetime.datetime.now(datetime.timezone.utc)
        hours = (now - modified).total_seconds() / 3600.0
    except Exception as e:
        print(f"❌ Routine: couldn't read the timestamp Drive returned ({mod}) — {e}")
        return 4

    what = "your dashboards" if is_feed else f"\"{name}\""
    if hours <= a.max_age_hours:
        ago = f"{hours:.0f}h ago" if hours >= 1 else "under an hour ago"
        print(f"✅ Routine: your engine looks alive — {what} refreshed {ago} "
              f"(within {a.max_age_hours:.0f}h). The daily Routine is writing data.")
        return 0
    days = hours / 24.0
    when = f"{days:.1f} days ago" if days >= 1 else f"{hours:.0f}h ago"
    print(f"❌ Routine: {what} haven't refreshed since {when} (older than {a.max_age_hours:.0f}h).\n"
          "   Run your Routine once now (check it's scheduled + Network access = Custom with the "
          "Amazon hosts), then run this again. The default 'Trusted' network setting silently "
          "blocks Amazon — that's the #1 reason a Routine looks set up but pulls nothing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
