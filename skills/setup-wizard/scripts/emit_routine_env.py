#!/usr/bin/env python
"""emit_routine_env.py — build the cloud-Routine handoff the user pastes into their account.

Reads the user's local .env (their own secrets) + answers.json (which adapters are on) and
writes TWO files into output/, deliberately split by sensitivity so the user never has to open
a secrets file on a shared screen (a live call once leaked a whole key ring this way):

  1. routine-form-pack-<date>.txt  — NO secrets. Safe to keep open on screen, even on a live
     stream. Everything the user needs to READ while filling the Routine form: the clone
     command, the Routine name, the Instructions command list (parsed live from user-setup.md
     so it's always in sync + carries every --write/--auto flag), the schedule, the network
     allowlist (one host per line), and a MANIFEST of env-key NAMES (names aren't secret) with any
     MISSING warnings.
  2. routine-SECRETS-<date>.txt    — the secret KEY=value lines and nothing else. Opened once,
     blind (Ctrl+A / Ctrl+C / close), pasted into the Routine's Environment box, then deleted.
     Never printed to the console.

Usage:
  python -X utf8 emit_routine_env.py answers.json --env C:\\path\\fba-secrets\\.env --repo https://github.com/<user>/fba-ai-student-robot
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Always-needed (universal core: Amazon + Google + sheet target). GOOGLE_CREDENTIALS_JSON is the
# raw client-secrets file (base64) — the cloud Routine has no local fba-secrets folder to read it
# from, and the robot's token-refresh call needs it alongside GOOGLE_TOKEN_JSON (see fill_d.py
# g_token()). Without it, the robot fails to refresh on its very first cloud run.
CORE_KEYS = ["LWA_CLIENT_ID", "LWA_CLIENT_SECRET", "SP_REFRESH_TOKEN", "SP_SELLER_ID",
             "GOOGLE_TOKEN_JSON", "GOOGLE_CREDENTIALS_JSON", "OPS_SHEET_ID"]
# Optional keys included only when present in the user's .env. SellerBoard cookies imply the
# Routine runs the COGS sync (APPLY=1 sb_cogs_sync.py is a standard Instructions line), so they
# MUST bring app.sellerboard.com onto the allowlist — the sandbox proxy 403s the CONNECT
# otherwise and only that final step fails while everything else stays green (field, 2026-07-17).
OPTIONAL_KEYS = ["KEEPA_API_KEY", "SELLERBOARD_SID", "SELLERBOARD_DID", "SELLERBOARD_QID"]

# Base allowlist hosts (universal core). gmail.googleapis.com is included unconditionally: the
# allowlist grants permission, it doesn't force a call — Gmail-opted-out robots simply never dial
# it, and leaving it off breaks the Gmail readers for everyone who did consent.
CORE_HOSTS = ["api.amazon.com", "sellingpartnerapi-na.amazon.com", "*.amazonaws.com",
              "www.googleapis.com", "sheets.googleapis.com", "oauth2.googleapis.com",
              "gmail.googleapis.com"]


def load_env(path):
    env = {}
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# The canonical daily command list is single-sourced in references/user-setup.md so a doc edit
# and the form pack can never drift (the drift is exactly what stranded a user: the Instructions
# lived only in a chat block he couldn't get back to). We parse the fenced block under the canonical
# heading and FAIL LOUDLY if the heading or fence moves — better a hard error at setup time than a
# form pack silently missing its Instructions.
CANONICAL_HEADING = "### Canonical daily Routine command list"


def load_canonical_commands():
    ref = os.path.normpath(os.path.join(HERE, "..", "references", "user-setup.md"))
    if not os.path.exists(ref):
        sys.exit(f"ABORT: canonical command source not found at {ref} — cannot build the form pack "
                 f"Instructions block. (Expected the setup-wizard references folder alongside scripts.)")
    text = open(ref, encoding="utf-8").read()
    lines = text.splitlines()
    # find the heading, then the first fenced ``` block after it
    hi = next((i for i, ln in enumerate(lines) if ln.startswith(CANONICAL_HEADING)), None)
    if hi is None:
        sys.exit(f"ABORT: heading '{CANONICAL_HEADING}' not found in {ref}. The canonical command "
                 f"list moved or was renamed — fix user-setup.md or this parser before shipping.")
    open_i = next((i for i in range(hi, len(lines)) if lines[i].strip().startswith("```")), None)
    if open_i is None:
        sys.exit(f"ABORT: no ``` code fence found after '{CANONICAL_HEADING}' in {ref}.")
    close_i = next((i for i in range(open_i + 1, len(lines)) if lines[i].strip().startswith("```")), None)
    if close_i is None:
        sys.exit(f"ABORT: unterminated code fence under '{CANONICAL_HEADING}' in {ref}.")
    cmds = [ln for ln in lines[open_i + 1:close_i] if ln.strip()]
    if not cmds:
        sys.exit(f"ABORT: canonical command block under '{CANONICAL_HEADING}' is empty in {ref}.")
    return cmds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("answers")
    ap.add_argument("--env", default=os.environ.get("FBA_ENV_PATH"))
    ap.add_argument("--repo", dest="repo",
                    default="https://github.com/<your-username>/fba-ai-student-robot")
    ap.add_argument("--out-dir", default=os.path.join(HERE, "..", "output"))
    a = ap.parse_args()

    ans = json.load(open(a.answers, encoding="utf-8"))
    env = load_env(a.env)
    adapters = ans.get("adapters", {})

    keys = list(CORE_KEYS)
    hosts = list(CORE_HOSTS)
    for k in OPTIONAL_KEYS:
        if env.get(k):
            keys.append(k)

    # SellerBoard cookies present = the Routine runs the COGS sync = the proxy must allow it.
    if env.get("SELLERBOARD_SID"):
        hosts += ["app.sellerboard.com", "*.sellerboard.com"]

    fin = (adapters.get("finance") or {}).get("provider", "manual")
    if fin == "monarch":
        keys += ["MONARCH_TOKEN"]
        hosts += ["monarchmoney.com", "api.monarch.com"]

    prep = adapters.get("prep_center") or {}
    if "PREPB" in [str(x).upper() for x in (prep.get("providers_active") or [])]:
        keys += ["PW_REFRESH_TOKEN", "PW_FIREBASE_KEY"]
        hosts += ["firestore.googleapis.com", "identitytoolkit.googleapis.com"]

    # cashback portals (optional, only if the user set those up)
    if env.get("TCB_COOKIE"):
        keys.append("TCB_COOKIE")
        hosts.append("www.topcashback.com")

    commands = load_canonical_commands()

    missing = [k for k in keys if not env.get(k)]

    date = datetime.date.today().isoformat()
    out_dir = os.path.normpath(a.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    repo_dir = a.repo.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")

    # ---- File 1: the FORM PACK (no secrets — safe to keep open on screen) ----
    pack_path = os.path.join(out_dir, f"routine-form-pack-{date}.txt")
    p = []
    p.append(f"# Routine FORM PACK — generated {date} by setup-wizard")
    p.append("# SAFE TO KEEP OPEN ON SCREEN — even on a live stream. No secrets in this file.")
    p.append("# The values for the env keys below live in routine-SECRETS-<date>.txt (open that one blind).")
    p.append("")
    p.append("## FIRST (do this before filling the form): install the Claude GitHub App on your repo")
    p.append("#  github.com/apps/claude → Install → pick your robot repo. The Routine form WIPES if you")
    p.append("#  navigate away or refresh, so do this in a SEPARATE tab, then fill the form top-to-bottom.")
    p.append("")
    p.append("## 1) Repo + clone command:")
    p.append(f"git clone {a.repo} && cd {repo_dir}")
    p.append("")
    p.append("## 2) Routine Name:")
    p.append("daily-fba")
    p.append("")
    p.append("## 3) Instructions (paste this whole block into the Routine's Instructions box):")
    p.extend(commands)
    p.append("")
    p.append("## 4) Schedule:")
    p.append("daily 6:00 AM — SET YOUR OWN TIMEZONE (the form defaults to Pacific)")
    p.append("")
    p.append("## 5) Network access = CUSTOM (the default 'Trusted' OMITS Amazon — #1 silent-failure trap).")
    p.append("##    Add these hosts, ONE PER LINE:")
    for h in hosts:
        p.append(h)
    p.append("")
    p.append("## 6) Environment — you'll paste these KEYS' values (names only shown here; values are")
    p.append("##    in routine-SECRETS-<date>.txt):")
    for k in keys:
        p.append(f"   {k}" + ("   <-- MISSING, collect this before the Routine will work" if k in missing else ""))
    p.append("")
    if missing:
        p.append("## ⚠️ MISSING values (validate/collect before the Routine will work): " + ", ".join(missing))
    p.append("## When ready for the Environment step: open routine-SECRETS-<date>.txt, select all,")
    p.append("## copy, close it, paste into the Routine's Environment box, then DELETE that file.")

    with open(pack_path, "w", encoding="utf-8") as f:
        f.write("\n".join(p) + "\n")

    # ---- File 2: the SECRETS (bare KEY=value only — open blind, paste, delete) ----
    secrets_path = os.path.join(out_dir, f"routine-SECRETS-{date}.txt")
    s = []
    s.append("# DO NOT open this file while screen-sharing or recording — it holds your live secrets.")
    s.append("# Use: open -> Ctrl+A -> Ctrl+C -> close -> paste into the Routine's Environment box -> DELETE this file.")
    for k in keys:
        s.append(f"{k}={env.get(k, '')}")

    with open(secrets_path, "w", encoding="utf-8") as f:
        f.write("\n".join(s) + "\n")

    print(f"✅ wrote {pack_path}  (safe to open on screen)")
    print(f"✅ wrote {secrets_path}  (contents NOT shown — never print or cat this file)")
    print(f"   Instructions: {len(commands)} commands | env keys: {len(keys)} | allowlist hosts: {len(hosts)}"
          + (f" | ⚠️ MISSING: {', '.join(missing)}" if missing else " | all values present"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
