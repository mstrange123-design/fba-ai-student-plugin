#!/usr/bin/env python
"""validate_google.py — prove the user's Google token works AND can see their sheet.

Refreshes the OAuth access token from GOOGLE_TOKEN_JSON, then calls Sheets
spreadsheets.get on the user's FBA Ops Sheet id. A 200 with the sheet title proves
two things at once: the token is valid AND the sheet is shared with / owned by the
authorized account. Stdlib only.

GOOGLE_TOKEN_JSON is the base64 of an authorized-user token JSON that includes at least
refresh_token, client_id, client_secret (the same shape google-auth writes). Pass it via
env GOOGLE_TOKEN_JSON (base64) or --token-file (a raw JSON path).

Usage:
  GOOGLE_TOKEN_JSON=<base64> python -X utf8 validate_google.py --sheet-id <id>
  python -X utf8 validate_google.py --token-file token.json --sheet-id <id>
"""
import argparse
import base64
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
    # tolerate either base64 or already-plain JSON
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", required=True)
    ap.add_argument("--token-file", default=None)
    a = ap.parse_args()

    tok = load_token(a)
    if not tok:
        print("❌ Google: no token — set GOOGLE_TOKEN_JSON (base64) or pass --token-file")
        return 2
    for k in ("refresh_token", "client_id", "client_secret"):
        if k not in tok:
            print(f"❌ Google: token JSON missing '{k}' — re-run the consent flow")
            return 2

    try:
        access = refresh_access_token(tok)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"❌ Google: token refresh failed ({e.code}) — the token may be revoked or the "
              f"app's client id/secret changed.\n   {body[:300]}")
        return 3
    except Exception as e:
        print(f"❌ Google: could not reach token endpoint — {e}")
        return 3

    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{a.sheet_id}"
           f"?fields=properties.title")
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + access})
        with urllib.request.urlopen(req, timeout=30) as r:
            meta = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        hint = ("the sheet isn't shared with this Google account, or the id is wrong"
                if e.code in (403, 404) else "check the Sheets API is enabled on the OAuth app")
        print(f"❌ Google: spreadsheets.get returned {e.code} — {hint}.\n   {body[:300]}")
        return 4
    except Exception as e:
        print(f"❌ Google: could not reach Sheets API — {e}")
        return 4

    title = (meta.get("properties") or {}).get("title", "(untitled)")
    print(f"✅ Google: token valid AND can read the sheet — \"{title}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
