#!/usr/bin/env python
"""verify.py — the end-of-lesson "is this piece set up right?" check.

ONE consistent command a user runs at the end of each lesson. It finds their .env,
loads it, runs the right check for that lesson, and prints a clear green/red banner.
All green = that piece is wired correctly. Run `all` for the final capstone.

The 5 lessons / legs:
  amazon   — Lesson 1: do my Amazon SP-API credentials actually reach Amazon? (live call)
  google   — Lesson 2 pre-req: can my Google token read my FBA Ops Sheet? (live call)
  routine  — Lesson 3: did my daily cloud Routine actually run? (sheet freshness)
  cowork   — Lesson 4: are my two dashboards showing in Cowork? (manual eyeball)
  bank     — Lesson 5 (optional): does my Monarch token authenticate? (live call)
  keys     — bonus: is my .env filled in right? (no network — locate + presence + format)
  all      — run every automatable check and print one capstone banner

Usage:
  python -X utf8 verify.py            # same as `all`
  python -X utf8 verify.py amazon
  python -X utf8 verify.py routine
  python -X utf8 verify.py --env /path/to/.env all

Exit 0 = ✅ everything checked is green (optional skips are fine). Non-zero = ❌ to fix.
Never prints a secret. Stdlib only — runs on Mac, Windows, Linux with no pip installs.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_env  # reuse the .env finder + loader + key evaluator (single source of truth)

# Legs that run as an automated check (in lesson order). `cowork` is manual; `keys` is a bonus.
SCRIPT_LEGS = ["keys", "amazon", "google", "routine", "bank"]
LEG_LABEL = {
    "keys": "Amazon keys (.env)",
    "amazon": "Amazon live (SP-API)",
    "google": "Google + Sheet",
    "routine": "Routine ran (engine)",
    "bank": "Bank / Monarch (opt.)",
    "cowork": "Cowork dashboards",
}
PAD = 24  # column width for the summary dots


def resolve_env(explicit):
    """Return (path, values dict) for the user's .env, or (None, {})."""
    if explicit:
        path = os.path.abspath(explicit)
        if not os.path.isfile(path):
            return None, {}
    else:
        existing = [c for c in check_env.candidate_paths(None) if os.path.isfile(c)]
        path = existing[0] if existing else None
    if not path:
        return None, {}
    entries, _ = check_env.load_detailed(path)
    return path, {k: e["value"] for k, e in entries.items()}


def lifecycle_feed_id(plugin_config):
    """Read the lifecycle feed file id from the plugin config (create_feed_files wrote it there).
    The Routine check prefers this app-created file: the narrow drive.file scope CAN stat its
    modifiedTime, whereas a hand-copied sheet returns 404."""
    try:
        with open(plugin_config, encoding="utf-8") as f:
            cfg = json.load(f)
        fid = (((cfg.get("live_artifact_feeds") or {}).get("feeds") or {})
               .get("lifecycle-stages") or {}).get("drive_file_id")
        if fid and not str(fid).upper().startswith("YOUR"):
            return fid
    except Exception:
        pass
    return None


def child_env(values):
    env = dict(os.environ)
    for k, v in values.items():
        if v:
            env[k] = v
    return env


def run_validator(script, values, extra_args=None):
    """Run a validator script as a subprocess with the .env loaded in; echo its output."""
    cmd = [sys.executable, "-X", "utf8", os.path.join(HERE, script)] + (extra_args or [])
    proc = subprocess.run(cmd, env=child_env(values), capture_output=True, text=True)
    out = (proc.stdout or "").strip()
    if out:
        for line in out.splitlines():
            print("   " + line)
    err = (proc.stderr or "").strip()
    if err and proc.returncode != 0:
        print("   " + err.splitlines()[-1])
    return proc.returncode == 0


def check_keys(path, values):
    """No-network key presence/format check (mirrors check_env, inline so we share the table)."""
    ok = True
    for k in check_env.SPAPI_KEYS:
        sym, key_ok, line = check_env.evaluate(k, {kk: {"value": vv, "had_ws": False,
                                                        "had_quotes": False, "had_export": False,
                                                        "dup": False} for kk, vv in values.items()})
        print("   " + line)
        ok = ok and key_ok
    return ok


def cowork_note():
    """Lesson 4 can't be checked from a terminal — print the eyeball checklist."""
    print("   I can't check this one from the command line — open Cowork and confirm:")
    print("     1. Your FBA plugin is installed (you can see its skills).")
    print("     2. Your Google Drive is connected in Cowork.")
    print("     3. Both dashboard tiles load: the Item Journey and the Cash Cycle.")
    print("   All three there → Lesson 4 is done. 👀")


def run_leg(leg, path, values):
    """Return True (green), False (red), or None (optional, not set up — counts as fine)."""
    print(f"\n▶ {LEG_LABEL[leg]}")
    if leg == "keys":
        return check_keys(path, values)
    if leg == "amazon":
        return run_validator("validate_spapi.py", values)
    if leg == "google":
        sid = values.get("OPS_SHEET_ID")
        if not sid:
            print("   ❌ Google: OPS_SHEET_ID not in your .env yet (that comes with the Google lesson)")
            return False
        return run_validator("validate_google.py", values, ["--sheet-id", sid])
    if leg == "routine":
        if values.get("LIFECYCLE_FEED_FILE_ID"):
            # validate_routine defaults --feed-id from LIFECYCLE_FEED_FILE_ID in the child env
            return run_validator("validate_routine.py", values)
        sid = values.get("OPS_SHEET_ID")
        if not sid:
            print("   ❌ Routine: no dashboards feed id or OPS_SHEET_ID yet (comes with the dashboards lesson)")
            return False
        return run_validator("validate_routine.py", values, ["--sheet-id", sid])
    if leg == "bank":
        if not values.get("MONARCH_TOKEN"):
            print("   ⏭ Monarch/bank is optional — not set up, skipping (that's fine).")
            return None
        return run_validator("validate_monarch.py", values)
    if leg == "cowork":
        cowork_note()
        return None
    return False


SYM = {True: "✅", False: "❌", None: "⏭"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("leg", nargs="?", default="all", choices=SCRIPT_LEGS + ["cowork", "all"],
                    help="which lesson to verify (default: all)")
    ap.add_argument("--env", help="explicit path to the .env (otherwise auto-found)")
    ap.add_argument("--plugin-config", default=os.path.join(HERE, "..", "..", "_shared", "config.json"),
                    help="plugin _shared/config.json — used to find the lifecycle feed id for the Routine check")
    a = ap.parse_args()

    print("\U0001f50e Setup check\n")

    # cowork is a pure eyeball step — no .env needed.
    if a.leg == "cowork":
        run_leg("cowork", None, {})
        print("\n(Visual step — nothing to measure here. If the tiles load, you're set.)")
        return 0

    path, values = resolve_env(a.env)
    if not path:
        print("❌ Couldn't find your .env. Ask Claude to find it, or pass --env <path>.")
        print("   (Tip: run  check_env.py --search <your project folder>  to hunt for it.)")
        return 2
    print(f"Using .env:  {path}")

    # The Routine check prefers the app-created lifecycle feed file (drive.file scope can stat it;
    # a hand-copied sheet 404s). Surface its id so validate_routine's --feed-id default picks it up.
    if not values.get("LIFECYCLE_FEED_FILE_ID"):
        fid = lifecycle_feed_id(a.plugin_config)
        if fid:
            values["LIFECYCLE_FEED_FILE_ID"] = fid

    legs = SCRIPT_LEGS if a.leg == "all" else [a.leg]
    results = {leg: run_leg(leg, path, values) for leg in legs}

    print("\n" + "═" * 44)
    print("  SETUP CHECK")
    for leg in legs:
        dots = "." * max(2, PAD - len(LEG_LABEL[leg]))
        print(f"  {LEG_LABEL[leg]} {dots} {SYM[results[leg]]}")
    print("═" * 44)

    has_fail = any(v is False for v in results.values())

    if a.leg == "all":
        # Lesson 4 (Cowork dashboards) is the one step a script can't prove — remind, don't block.
        print("\n▶ " + LEG_LABEL["cowork"] + "  (the one I can't check — eyeball it):")
        cowork_note()

    if not has_fail:
        if a.leg == "all":
            print("\n🎉 ALL GREEN — credentials + engine are wired. "
                  "Confirm the Cowork dashboards above and you're fully set up.")
        elif results.get(a.leg) is None:
            print(f"\n⏭ {LEG_LABEL[a.leg]} is optional and not set up — nothing to check here.")
        else:
            print(f"\n✅ GREEN — the {a.leg} piece is wired correctly.")
        return 0

    bad = [LEG_LABEL[l] for l, ok in results.items() if ok is False]
    print(f"\n❌ Not yet: {', '.join(bad)}. Fix the red item above, then run this again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
