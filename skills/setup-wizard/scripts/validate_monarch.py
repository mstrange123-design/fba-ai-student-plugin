#!/usr/bin/env python
"""validate_monarch.py — prove the user's Monarch token authenticates.

Lesson 5 (bank / cash-cycle) is OPTIONAL. If the user tracks their bank in Monarch,
this confirms MONARCH_TOKEN is accepted by sending one tiny authenticated request. We
only check that auth succeeds — not any account data — so nothing sensitive is read or
printed, and the token never appears in output.

Stdlib only (urllib). Reads MONARCH_TOKEN from env or --token.

Usage:
  python -X utf8 validate_monarch.py

Exit 0 = ✅ token authenticates. Non-zero = ❌ (wrong/expired token, or couldn't reach Monarch).
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

GRAPHQL_URL = "https://api.monarchmoney.com/graphql"
# Minimal query: we only care that we get PAST the auth layer. If `me` ever changes,
# a 200 with a field error still proves the token authenticated.
QUERY = {"query": "query { me { id } }", "variables": {}}
AUTH_MARKERS = ("unauthenticated", "not authenticated", "unauthorized", "not authorized",
                "login", "signature", "invalid token", "authentication")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("MONARCH_TOKEN"))
    a = ap.parse_args()

    if not a.token:
        print("❌ Monarch: no MONARCH_TOKEN set. (This lesson is optional — skip it if you just "
              "use your bank's own site.)")
        return 2

    data = json.dumps(QUERY).encode("utf-8")
    headers = {
        "Authorization": "Token " + a.token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://app.monarchmoney.com",
        "Client-Platform": "web",
    }
    req = urllib.request.Request(GRAPHQL_URL, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code in (401, 403):
            print("❌ Monarch: token rejected (got "
                  f"{e.code}). It's wrong or expired — grab a fresh token and update your .env.")
            return 3
        print(f"❌ Monarch: request failed ({e.code}).\n   {body[:200]}")
        return 3
    except Exception as e:
        print(f"❌ Monarch: could not reach Monarch — {e}")
        return 3

    low = body.lower()
    if status == 200 and any(m in low for m in AUTH_MARKERS):
        print("❌ Monarch: the token didn't authenticate (the server asked for login). "
              "Grab a fresh token and update your .env.")
        return 3

    if status == 200:
        print("✅ Monarch: token authenticates — your bank/cash-cycle feed is wired.")
        return 0
    print(f"❌ Monarch: unexpected response ({status}).\n   {body[:200]}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
