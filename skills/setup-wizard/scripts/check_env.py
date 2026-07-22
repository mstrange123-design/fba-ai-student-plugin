#!/usr/bin/env python
"""check_env.py — find a user's .env and confirm their keys actually landed.

The "where is my .env / did I fill it in right?" helper. Unlike validate_spapi.py
(which makes a live Amazon call), this does ZERO network — it just LOCATES the file
and checks each key is present, non-empty, well-formed, and free of the stray-space /
placeholder / quote mistakes that silently break login. Safe to run on a screen share:
it NEVER prints a secret — only ✅/❌, the key length, and a masked last-4 tail.

This is the self-serve answer to "I can't find the user's .env on their computer."
Works identically on Mac, Windows, and Linux; stdlib only (no pip).

Usage:
  python -X utf8 check_env.py                 # auto-find the .env in the usual spots
  python -X utf8 check_env.py --env PATH       # point it straight at a file
  python -X utf8 check_env.py --search FOLDER  # hunt a folder tree for any .env
  python -X utf8 check_env.py --full           # also require the Google + Sheet keys

Exit 0 = ✅ all required keys present and well-formed. Non-zero = ❌ something to fix.
"""
import argparse
import os
import sys

# Required for the Amazon (SP-API) leg — the four the validator needs.
SPAPI_KEYS = ["LWA_CLIENT_ID", "LWA_CLIENT_SECRET", "SP_REFRESH_TOKEN", "SP_SELLER_ID"]
# Added once the Google leg is done (Step 6/7). Only required with --full.
GOOGLE_KEYS = ["GOOGLE_TOKEN_JSON", "OPS_SHEET_ID"]

# Known value prefixes — a mismatch usually means a swapped or wrong-pasted value.
PREFIX = {
    "LWA_CLIENT_ID": "amzn1.application-oa2-client.",
    "LWA_CLIENT_SECRET": "amzn1.oa2-cs.v1.",
    "SP_REFRESH_TOKEN": "Atzr|",
}
PLACEHOLDER_BITS = ["…", "...", "<", "your-", "paste", "xxxx", "example", "amzn1.application-oa2-client.…"]
NOISY_DIRS = {"node_modules", ".git", "venv", ".venv", "env", "__pycache__",
              "Library", "AppData", "Applications", "site-packages"}


def candidate_paths(explicit):
    """The usual spots, in priority order — first existing one wins."""
    cands = []
    if explicit:
        cands.append(explicit)
    if os.environ.get("FBA_ENV_PATH"):
        cands.append(os.environ["FBA_ENV_PATH"])
    d = os.getcwd()                       # current dir, then walk up a few levels
    for _ in range(6):
        cands.append(os.path.join(d, ".env"))
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    home = os.path.expanduser("~")
    cands += [
        os.path.join(home, "fba-secrets", ".env"),
        os.path.join(home, "AppData", "Local", "fba-secrets", ".env"),
        os.path.join(home, "fba-ai-student-robot", ".env"),
        os.path.join(home, ".env"),
    ]
    seen, ordered = set(), []
    for c in cands:
        c = os.path.abspath(c)
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def scan_tree(root, max_depth=4, limit=50):
    """Hunt a folder tree for any .env file (bounded, skips noisy dirs)."""
    root = os.path.abspath(root)
    base = root.rstrip(os.sep).count(os.sep)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count(os.sep) - base > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in NOISY_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn == ".env" or fn.endswith(".env"):
                found.append(os.path.join(dirpath, fn))
                if len(found) >= limit:
                    return found
    return found


def load_detailed(path):
    """Return {key: {value, had_ws, had_quotes, had_export, dup}} plus key order.

    Keeps the mistakes a naive loader would silently swallow (stray spaces, quotes,
    `export ` prefix, duplicates) so we can warn on them."""
    entries, order = {}, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\r\n").strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key_part, raw = s.split("=", 1)
            key = key_part.strip()
            had_export = key.startswith("export ")
            if had_export:
                key = key[len("export "):].strip()
            stripped = raw.strip()
            had_ws = raw != stripped
            had_quotes = len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'"
            val = stripped[1:-1] if had_quotes else stripped
            dup = key in entries
            entries[key] = {"value": val, "had_ws": had_ws, "had_quotes": had_quotes,
                            "had_export": had_export, "dup": dup}
            if not dup:
                order.append(key)
    return entries, order


def mask(v):
    if not v:
        return "(empty)"
    return ("…" + v[-4:]) if len(v) > 4 else "•" * len(v)


def is_placeholder(v):
    lv = v.lower()
    return any(bit.lower() in lv for bit in PLACEHOLDER_BITS)


def evaluate(key, entries):
    """Return (symbol, ok, line) for one key."""
    e = entries.get(key)
    if not e or not e["value"]:
        return "❌", False, f"  ❌ {key:<20} MISSING — not in the file"

    v = e["value"]
    notes = []
    ok = True
    if is_placeholder(v):
        ok = False
        notes.append("looks like a placeholder, not your real value")
    elif key in PREFIX and not v.startswith(PREFIX[key]):
        ok = False
        notes.append(f"doesn't start with \"{PREFIX[key]}\" — wrong value, or ID/secret swapped?")
    if e["had_ws"]:
        ok = False
        notes.append("extra spaces around the value (retype it — stray spaces silently break login)")
    if e["had_quotes"]:
        notes.append("wrapped in quotes (usually fine in .env, but drop them to be safe)")
    if e["had_export"]:
        notes.append("has an 'export ' prefix — remove it")
    if e["dup"]:
        notes.append("appears more than once — keep only the last")

    sym = "✅" if ok else "⚠️"
    tail = f"  {mask(v)}  (len {len(v)})"
    note = ("   — " + "; ".join(notes)) if notes else ""
    return sym, ok, f"  {sym} {key:<20}{tail}{note}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", help="explicit path to the .env to check")
    ap.add_argument("--search", help="hunt this folder tree for any .env files")
    ap.add_argument("--full", action="store_true",
                    help="also require the Google + Sheet keys (post-Google-leg)")
    a = ap.parse_args()

    print("\U0001f50e Checking your .env\n")

    if a.search:
        hits = scan_tree(a.search)
        if not hits:
            print(f"❌ No .env found anywhere under {os.path.abspath(a.search)}")
            return 2
        print(f"Found {len(hits)} .env file(s) under {os.path.abspath(a.search)}:")
        for h in hits:
            print(f"   • {h}")
        path = hits[0]
        print(f"\nChecking the first one: {path}\n")
    elif a.env:
        path = os.path.abspath(a.env)
        if not os.path.isfile(path):
            print(f"❌ No file at {path}")
            return 2
        print(f"✅ Checking:  {path}\n")
    else:
        ordered = candidate_paths(None)
        existing = [c for c in ordered if os.path.isfile(c)]
        if not existing:
            print("❌ Couldn't find a .env in the usual spots. I looked in:")
            for c in ordered[:8]:
                print(f"   • {c}")
            print("\nFix: point me at it with  --env <path>  or hunt a folder with  --search <folder>")
            return 2
        path = existing[0]
        print(f"✅ Found it:  {path}")
        if len(existing) > 1:
            print("   (note: more than one .env exists — others: "
                  + ", ".join(existing[1:]) + ")")
        print()

    entries, _ = load_detailed(path)

    required = list(SPAPI_KEYS) + (GOOGLE_KEYS if a.full else [])
    print("Amazon SP-API keys (required):")
    bad = []
    for k in SPAPI_KEYS:
        sym, ok, line = evaluate(k, entries)
        print(line)
        if not ok:
            bad.append(k)

    if a.full:
        print("\nGoogle + Sheet keys (required with --full):")
        for k in GOOGLE_KEYS:
            sym, ok, line = evaluate(k, entries)
            print(line)
            if not ok:
                bad.append(k)
    else:
        extra = [k for k in entries if k not in SPAPI_KEYS]
        if extra:
            print("\nOther keys in this file (not needed for the Amazon check): "
                  + ", ".join(sorted(extra)))

    print()
    if not bad:
        n = len(required)
        print(f"✅ All {n} required key(s) present and well-formed. You're good — "
              "next: run validate_spapi.py to prove they actually reach Amazon.")
        return 0
    print(f"❌ {len(bad)} key(s) to fix: {', '.join(bad)}. "
          "Fix those in the .env, then run me again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
