#!/usr/bin/env python
"""google_oauth_local.py — run the Google consent flow on the user's machine and capture the token.

The wizard's Step 6. Opens the user's browser to Google's consent screen for THEIR OWN Google
Cloud OAuth app (created minutes earlier this same call — see
references/google-cloud-authorize.md, the same self-authorize pattern as the Amazon SP-API step),
catches the redirect on a local port, exchanges the code for a refresh token, then:

  1. writes token.json into the local secrets folder,
  2. base64-encodes it and writes GOOGLE_TOKEN_JSON=... straight into the .env
     (never printed to screen — only a masked tail, safe on a screen share).

Stdlib only (no pip). The client id/secret are the USER'S OWN — a "Desktop app" OAuth client
they created in their own Google Cloud project and downloaded as credentials.json — place it next
to the .env or pass --credentials. Nobody else's app, nobody else's quota, nobody else's data.

Usage:
  python -X utf8 google_oauth_local.py                          # auto-find credentials.json
  python -X utf8 google_oauth_local.py --credentials PATH       # point at the client-secrets file
  python -X utf8 google_oauth_local.py --out-dir DIR --env PATH # custom secrets locations

"Google hasn't verified this app" is EXPECTED — it's your own small private app, and Google's
full verification review is unnecessary for a single-user tool. Click "Continue" /
"Advanced > Go to ...". As long as YOUR project's OAuth consent screen is set to **Published /
In production** (not Testing — see references/google-cloud-authorize.md step 3), your refresh
token does NOT expire after 7 days the way an unverified Testing-mode app's would.

Exit 0 = token captured + written. Non-zero = a step to fix (message says which).
"""
import argparse
import base64
import json
import os
import platform
import secrets as pysecrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# What the kit uses: Sheets (their FBA Ops + Item Journey sheets), Drive (the 3 live-tile feed
# files, scoped drive.file so it only ever touches files THIS app created), and Gmail read-only
# (the robot's order/cancellation email readers — reader_d, detect_cancellations, gmail_probe).
# gmail.readonly is a RESTRICTED scope: the consent screen shows a scarier "unverified app"
# warning; the user owns the app, so Advanced → proceed is safe. Their Cloud project must have
# the Gmail API enabled and the scope added on the consent screen's Data access page first.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.readonly",
]

LANDING_OK = ("<html><body style='font-family:sans-serif;text-align:center;padding-top:80px'>"
              "<h1>&#9989; Google connected</h1><p>You can close this tab and go back to the call.</p>"
              "</body></html>")
LANDING_ERR = ("<html><body style='font-family:sans-serif;text-align:center;padding-top:80px'>"
               "<h1>&#10060; Consent didn't finish</h1><p>Close this tab — the terminal says what to fix.</p>"
               "</body></html>")


def default_secrets_dir():
    home = os.path.expanduser("~")
    if platform.system() == "Windows":
        return os.path.join(home, "AppData", "Local", "fba-secrets")
    return os.path.join(home, "fba-secrets")


def find_client_secrets(explicit):
    """Locate the user's OWN client-secrets JSON (the Desktop-app OAuth client they created
    in their own Google Cloud project — see references/google-cloud-authorize.md). Returns
    (client_id, client_secret) or (None, reason)."""
    cands = []
    if explicit:
        cands.append(explicit)
    sdir = default_secrets_dir()
    for d in (os.getcwd(), sdir):
        cands.append(os.path.join(d, "credentials.json"))
        try:
            for fn in os.listdir(d):
                if fn.startswith("client_secret") and fn.endswith(".json"):
                    cands.append(os.path.join(d, fn))
        except OSError:
            pass
    for path in cands:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        blob = data.get("installed") or data.get("web")
        if blob and blob.get("client_id") and blob.get("client_secret"):
            if "web" in data and "installed" not in data:
                print("⚠️  This is a 'Web application' OAuth client — a 'Desktop app' client is the "
                      "reliable kind for this local flow. Go back to your Google Cloud project's "
                      "Credentials page and create a 'Desktop app' client instead (see "
                      "references/google-cloud-authorize.md step 4).")
            return (blob["client_id"], blob["client_secret"], path)
    return (None, None, None)


class _Catcher(BaseHTTPRequestHandler):
    """One-shot handler: stores the redirect query params on the server object."""
    def do_GET(self):
        q = urllib.parse.urlparse(self.path).query
        params = {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}
        if "code" in params or "error" in params:
            self.server.oauth_params = params
            body = LANDING_OK if "code" in params else LANDING_ERR
        else:
            body = ""  # favicon etc — ignore, keep waiting
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *a):  # silence request logging
        pass


def wait_for_redirect(httpd, deadline):
    httpd.timeout = 5
    httpd.oauth_params = None
    while time.time() < deadline:
        httpd.handle_request()
        if getattr(httpd, "oauth_params", None):
            return httpd.oauth_params
    return None


def exchange_code(code, client_id, client_secret, redirect_uri):
    fields = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def upsert_env_key(env_path, key, value):
    """Replace or append KEY=value in the .env, preserving every other line."""
    lines = []
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "="):
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    with open(env_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return replaced


def mask(v):
    return ("…" + v[-4:]) if len(v) > 4 else "•" * len(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--credentials", help="path to YOUR OWN client-secrets JSON (credentials.json)")
    ap.add_argument("--out-dir", default=None, help="where token.json + .env live (default: local fba-secrets)")
    ap.add_argument("--env", default=None, help="explicit .env path (default: <out-dir>/.env)")
    ap.add_argument("--timeout", type=int, default=300, help="seconds to wait for consent (default 300)")
    a = ap.parse_args()

    client_id, client_secret, cred_path = find_client_secrets(a.credentials)
    if not client_id:
        print("❌ Google: no client-secrets file found. Create your OWN Google Cloud project + "
              "Desktop-app OAuth client (see references/google-cloud-authorize.md — ~5 min, same "
              "idea as the Amazon self-authorize step), download its credentials.json, put it in " +
              default_secrets_dir() + " (or pass --credentials PATH), and run me again.")
        return 2
    print(f"✅ Client secrets: {cred_path}  (client id …{client_id[-12:]})")

    # The daily cloud Routine has no local fba-secrets folder to read credentials.json from —
    # it can only see what's in its env block. The robot's g_token() refresh call needs the raw
    # client-secrets file (not just the token), so base64 it into GOOGLE_CREDENTIALS_JSON here,
    # same convention as GOOGLE_TOKEN_JSON below. emit_routine_env.py bundles both into the
    # Routine handoff. Without this, the robot's very first cloud run fails to refresh at all.
    with open(cred_path, "r", encoding="utf-8") as f:
        raw_credentials = f.read()

    out_dir = a.out_dir or default_secrets_dir()
    env_path = a.env or os.path.join(out_dir, ".env")

    httpd = HTTPServer(("127.0.0.1", 0), _Catcher)
    port = httpd.server_port
    redirect_uri = f"http://127.0.0.1:{port}/"
    state = pysecrets.token_urlsafe(16)
    auth_url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",          # guarantees a refresh_token even on re-consent
        "state": state,
    })

    print("\n🌐 Opening Google's consent screen in your browser…")
    print("   • Pick the Google account you run your FBA sheets under.")
    print("   • 'Google hasn't verified this app' is EXPECTED — click Continue.")
    print("   • If the browser didn't open, paste this URL into it yourself:\n")
    print("   " + auth_url + "\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    params = wait_for_redirect(httpd, time.time() + a.timeout)
    httpd.server_close()

    if not params:
        print(f"❌ Google: no consent within {a.timeout}s. Re-run me and finish the browser flow "
              "(keep this terminal open while you click).")
        return 3
    if params.get("error"):
        err = params["error"]
        hint = ("you clicked Cancel, or your project's OAuth consent screen still needs the "
                "Sheets + Drive scopes added (Google Cloud Console → OAuth consent screen → Data "
                "access) — fix that, then re-run"
                if err == "access_denied" else "re-run and complete the consent screen")
        print(f"❌ Google: consent returned '{err}' — {hint}.")
        return 3
    if params.get("state") != state:
        print("❌ Google: state mismatch on the redirect (stale tab?). Close old consent tabs and re-run.")
        return 3

    try:
        tok = exchange_code(params["code"], client_id, client_secret, redirect_uri)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"❌ Google: code exchange failed ({e.code}) — usually a client id/secret mismatch.\n   {body[:300]}")
        return 4
    except Exception as e:
        print(f"❌ Google: could not reach the token endpoint — {e}")
        return 4

    if "refresh_token" not in tok:
        print("❌ Google: consent finished but no refresh token came back. Go to "
              "https://myaccount.google.com/permissions, remove this app's access, and re-run me.")
        return 4

    expiry = datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 3600)))
    token_json = {
        "token": tok.get("access_token", ""),
        "refresh_token": tok["refresh_token"],
        "token_uri": GOOGLE_TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES,
        "universe_domain": "googleapis.com",
        "account": "",
        "expiry": expiry.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
    }

    os.makedirs(out_dir, exist_ok=True)
    token_path = os.path.join(out_dir, "token.json")
    try:
        with open(token_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(token_json, f, indent=2)
        b64 = base64.b64encode(json.dumps(token_json).encode("utf-8")).decode("ascii")
        replaced = upsert_env_key(env_path, "GOOGLE_TOKEN_JSON", b64)
        creds_b64 = base64.b64encode(raw_credentials.encode("utf-8")).decode("ascii")
        creds_replaced = upsert_env_key(env_path, "GOOGLE_CREDENTIALS_JSON", creds_b64)
    except OSError as e:
        print(f"❌ Google: token captured but couldn't write it — {e}")
        return 5

    print(f"\n✅ Google: token captured.")
    print(f"   • token.json              → {token_path}")
    print(f"   • GOOGLE_TOKEN_JSON       → {env_path}  ({'updated' if replaced else 'added'}; "
          f"…{mask(b64)}, len {len(b64)})")
    print(f"   • GOOGLE_CREDENTIALS_JSON → {env_path}  ({'updated' if creds_replaced else 'added'}; "
          f"the daily Routine's robot needs this to refresh — it has no local file to fall back on)")
    print("\nNext: prove it can see YOUR sheet:")
    print("   python -X utf8 validate_google.py --sheet-id <your FBA Ops Sheet id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
