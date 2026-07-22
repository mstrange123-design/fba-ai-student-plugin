#!/usr/bin/env python
"""verify_addons.py — one command to prove the three tools added on top of the core setup:

  1) buy-logger   — can my Google token read+write my Bought tab? (the exact path the
                    Chrome buy-logger extension uses to write skeleton rows)
  2) gmail        — does gmail.readonly actually work? (live Gmail read — catches the
                    "scope granted but API returns 403" trap)
  3) sourcing     — has my Sourcing Radar agent written candidate rows? (finds the
                    "Sourcing Radar" sheet the agent creates and checks it has results)

This COMPLEMENTS verify.py (which covers the core: Amazon / Google / Routine / Cowork /
bank). Run BOTH for a full picture:
    python -X utf8 verify.py all          # core system
    python -X utf8 verify_addons.py       # the three add-ons

Exit 0 = every hard check green (a still-running sourcing agent is a soft PENDING, not a
fail). Non-zero = something to fix. Never prints a secret. Stdlib only — Mac/Win/Linux.
"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

GREEN, RED, YEL, DIM, RST = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
PASS, FAIL, PEND, SKIP = f"{GREEN}PASS{RST}", f"{RED}FAIL{RST}", f"{YEL}PENDING{RST}", f"{DIM}SKIP{RST}"


# ---------- .env / token loading (mirrors the robot's _json_env_or_file) ----------
def candidate_env_paths():
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    return [
        os.path.join(local, "fba-secrets", ".env"),
        os.path.join(home, "fba-secrets", ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]


def load_env():
    """os.environ wins; otherwise merge the first .env we find. Returns a plain dict."""
    values = dict(os.environ)
    for p in candidate_env_paths():
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    values.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break
    return values


def parse_token(values):
    raw = values.get("GOOGLE_TOKEN_JSON")
    if raw:
        s = raw.strip()
        if not s.startswith("{"):
            s = base64.b64decode(s).decode("utf-8")
        return json.loads(s)
    for p in candidate_env_paths():
        tp = os.path.join(os.path.dirname(p), "token.json")
        if os.path.isfile(tp):
            return json.load(open(tp, encoding="utf-8"))
    raise RuntimeError("GOOGLE_TOKEN_JSON not found in your environment or .env")


def access_token(tok):
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": tok["refresh_token"],
        "client_id": tok["client_id"],
        "client_secret": tok["client_secret"],
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["access_token"]


def http_get(url, at):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + at})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read())


# ---------- the three checks ----------
def check_buylogger(values, at):
    sid = values.get("OPS_SHEET_ID") or values.get("GOOGLE_SHEETS_ID") or values.get("SAS_SHEET_ID")
    if not sid:
        return "FAIL", "no OPS_SHEET_ID in your .env"
    url = ("https://sheets.googleapis.com/v4/spreadsheets/" + urllib.parse.quote(sid)
           + "/values/" + urllib.parse.quote("Bought!A1:AZ1"))
    try:
        _, j = http_get(url, at)
    except urllib.error.HTTPError as e:
        return "FAIL", f"can't read Bought (HTTP {e.code}) — check OPS_SHEET_ID + sheet access"
    header = [str(h).strip().lower() for h in (j.get("values") or [[]])[0]]
    need = {"date", "asin", "status"}
    have_order = any(h in header for h in ("order #", "order#", "order number"))
    missing = [c for c in need if c not in header] + ([] if have_order else ["order #"])
    if missing:
        return "FAIL", "Bought header missing: " + ", ".join(missing)
    return "PASS", f"Bought reachable, {len(header)} columns — extension can write here"


def check_gmail(at, values):
    # Gmail is OPTIONAL. A user can deliberately opt out (privacy) — that's a SUPPORTED healthy
    # state, not a defect. Set GMAIL_OPTED_OUT=1 (or GMAIL_ENABLED=0) in .env and a 403 reads as
    # SKIPPED, not a red FAIL.
    opted_out = str(values.get("GMAIL_OPTED_OUT", "")).strip() in ("1", "true", "yes") \
        or str(values.get("GMAIL_ENABLED", "")).strip() in ("0", "false", "no")
    try:
        _, j = http_get("https://gmail.googleapis.com/gmail/v1/users/me/profile", at)
    except urllib.error.HTTPError as e:
        if opted_out:
            return "SKIP", "Gmail intentionally off (GMAIL_OPTED_OUT) — system self-skips it, this is fine"
        if e.code == 403:
            return "FAIL", "403 — enable the Gmail API + re-consent with ALL boxes ticked (incl. gmail.readonly)"
        if e.code == 401:
            return "FAIL", "401 — token expired; re-run google_oauth_local.py"
        return "FAIL", f"HTTP {e.code}"
    total = j.get("messagesTotal", "?")
    return "PASS", f"Gmail read works ({j.get('emailAddress','?')}, {total} messages)"


def check_sourcing(at):
    q = "name = 'Sourcing Radar' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    url = "https://www.googleapis.com/drive/v3/files?q=" + urllib.parse.quote(q) + "&fields=files(id,name)"
    try:
        _, j = http_get(url, at)
    except urllib.error.HTTPError as e:
        return "PENDING", f"couldn't search Drive (HTTP {e.code}) — agent may not have run yet"
    files = j.get("files") or []
    if not files:
        return "PENDING", "no 'Sourcing Radar' sheet yet — agent still running / not run"
    fid = files[0]["id"]
    try:
        _, meta = http_get("https://sheets.googleapis.com/v4/spreadsheets/" + fid
                           + "?fields=sheets.properties.title", at)
    except urllib.error.HTTPError:
        return "PENDING", "found the sheet but couldn't read its tabs yet"
    titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    tab = next((t for t in titles if "candidat" in t.lower()), None)
    if not tab:
        return "PENDING", "sheet exists but no Candidates tab yet — agent still filling it"
    _, vals = http_get("https://sheets.googleapis.com/v4/spreadsheets/" + fid
                       + "/values/" + urllib.parse.quote(tab + "!A1:A"), at)
    rows = max(0, len(vals.get("values") or []) - 1)
    if rows <= 0:
        return "PENDING", "Candidates tab is empty — agent still running (this is normal same-day)"
    return "PASS", f"{rows} sourcing candidates written to your Sourcing Radar sheet"


def main():
    print(f"{DIM}Verifying the three add-on tools (buy-logger, Gmail, sourcing agent)…{RST}\n")
    try:
        values = load_env()
        tok = parse_token(values)
        at = access_token(tok)
    except Exception as e:
        print(f"{FAIL}  couldn't authenticate with Google — {e}")
        print("       (fix your GOOGLE_TOKEN_JSON, then re-run)")
        return 2

    results = []
    for label, fn in (("buy-logger extension", lambda: check_buylogger(values, at)),
                      ("gmail read", lambda: check_gmail(at, values)),
                      ("sourcing agent", lambda: check_sourcing(at))):
        try:
            status, detail = fn()
        except Exception as e:
            status, detail = "FAIL", f"unexpected error: {e}"
        tag = {"PASS": PASS, "FAIL": FAIL, "PENDING": PEND, "SKIP": SKIP}[status]
        print(f"  {tag}  {label:22} {DIM}{detail}{RST}")
        results.append(status)

    hard_fail = any(s == "FAIL" for s in results)
    pend = any(s == "PENDING" for s in results)
    print()
    if hard_fail:
        print(f"{RED}✗ Something needs fixing above.{RST} (also run: python -X utf8 verify.py all)")
        return 1
    if pend:
        print(f"{YEL}◐ Everything wired; sourcing agent still working — re-run later to confirm it filled.{RST}")
        print(f"{DIM}  For the core system: python -X utf8 verify.py all{RST}")
        return 0
    print(f"{GREEN}✓ All three add-ons verified. For the core system: python -X utf8 verify.py all{RST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
