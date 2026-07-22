#!/usr/bin/env python
"""validate_spapi.py — prove a user's SP-API credentials work, end to end.

Exchanges their refresh token for an access token (LWA), then calls
getMarketplaceParticipations. A 200 with marketplaces listed = the credentials are
live and scoped to a real seller account. Stdlib only (urllib) so it runs from
Cowork's sandboxed bash, a Routine, or locally — no pip installs.

Reads from env (preferred) or --flags:
  LWA_CLIENT_ID, LWA_CLIENT_SECRET, SP_REFRESH_TOKEN
  SP_ENDPOINT (default https://sellingpartnerapi-na.amazon.com  — NA region)
  SP_SELLER_ID (optional; if set, just echoed for the wizard's id-match check)

Usage:
  python -X utf8 validate_spapi.py
  python -X utf8 validate_spapi.py --client-id ... --client-secret ... --refresh-token ...

Exit 0 = ✅ valid. Exit non-zero = ❌ with the reason printed.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
DEFAULT_ENDPOINT = "https://sellingpartnerapi-na.amazon.com"


def _post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url, headers):
    req = urllib.request.Request(url, method="GET", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def get_access_token(client_id, client_secret, refresh_token):
    return _post_form(LWA_TOKEN_URL, {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    })["access_token"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", default=os.environ.get("LWA_CLIENT_ID"))
    ap.add_argument("--client-secret", default=os.environ.get("LWA_CLIENT_SECRET"))
    ap.add_argument("--refresh-token", default=os.environ.get("SP_REFRESH_TOKEN"))
    ap.add_argument("--endpoint", default=os.environ.get("SP_ENDPOINT", DEFAULT_ENDPOINT))
    ap.add_argument("--expected-seller-id", default=os.environ.get("SP_SELLER_ID"))
    a = ap.parse_args()

    missing = [n for n, v in [("LWA_CLIENT_ID", a.client_id),
                              ("LWA_CLIENT_SECRET", a.client_secret),
                              ("SP_REFRESH_TOKEN", a.refresh_token)] if not v]
    if missing:
        print("❌ SP-API: missing " + ", ".join(missing))
        return 2

    try:
        access = get_access_token(a.client_id, a.client_secret, a.refresh_token)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"❌ SP-API: LWA token exchange failed ({e.code}). "
              f"Refresh token or client id/secret is wrong.\n   {body[:300]}")
        return 3
    except Exception as e:
        print(f"❌ SP-API: could not reach LWA token endpoint — {e}")
        return 3

    url = a.endpoint.rstrip("/") + "/sellers/v1/marketplaceParticipations"
    try:
        status, payload = _get(url, {"x-amz-access-token": access,
                                     "Accept": "application/json"})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"❌ SP-API: marketplaceParticipations returned {e.code}. "
              f"Token works but the app may lack the role, or wrong region endpoint.\n   {body[:300]}")
        return 4
    except Exception as e:
        print(f"❌ SP-API: could not reach {a.endpoint} — {e}")
        return 4

    parts = (payload or {}).get("payload", [])
    mkts = []
    for p in parts:
        m = p.get("marketplace", {})
        mkts.append(f"{m.get('name', m.get('id', '?'))} ({m.get('countryCode', '?')})")
    print("✅ SP-API: credentials valid. Access token issued; "
          f"getMarketplaceParticipations 200 with {len(parts)} marketplace(s): {', '.join(mkts) or '—'}")
    if a.expected_seller_id:
        print(f"   (seller id to record in config: {a.expected_seller_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
