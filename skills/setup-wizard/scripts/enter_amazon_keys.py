#!/usr/bin/env python3
"""enter_amazon_keys.py — the easy, safe way to get the 3 Amazon secrets into the user's .env.

THE PROBLEM this solves: after the user clicks "Authorize" in Seller Central, Amazon shows 3
values on screen (Client ID, Client Secret, Refresh Token). Getting those into the hidden `.env`
file by hand is awkward (especially on a Mac). AND they must never be pasted into the chat — chat
text goes to the model. So Claude can't just read them either.

THE FIX (model-safe by design): this script shuttles the values file-to-file so the MODEL NEVER
SEES THEM. Two steps, both run by Claude:

  1)  python -X utf8 enter_amazon_keys.py --open   [--paste-file PATH]
        Creates + opens a plain text file with 3 clearly-labelled blank lines. The user copies
        each value off their Amazon screen into the matching line, saves, and says "done".

  2)  python -X utf8 enter_amazon_keys.py --commit  [--paste-file PATH] [--env PATH]
        Reads that file, writes the 3 values into `.env` (LWA_CLIENT_ID / LWA_CLIENT_SECRET /
        SP_REFRESH_TOKEN), DELETES the paste file, and prints ONLY masked last-4 confirmation.
        The raw values are read by THIS SCRIPT and written straight to disk — never printed, never
        returned to Claude.

Claude drives it: run --open, tell the user to paste+save+say "done", then run --commit. Claude
never sees a raw key; it only sees the masked table check_env.py-style output.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# label in the paste file  ->  the .env key it maps to
FIELDS = [
    ("CLIENT ID", "LWA_CLIENT_ID"),
    ("CLIENT SECRET", "LWA_CLIENT_SECRET"),
    ("REFRESH TOKEN", "SP_REFRESH_TOKEN"),
]
DEFAULT_PASTE_NAME = "AMAZON-KEYS-PASTE-HERE.txt"
PLACEHOLDER = "<paste the value here, then save this file>"

PASTE_TEMPLATE = f"""HOW TO USE THIS FILE
--------------------
1. Look at your Amazon "Authorize app" screen — it shows 3 values.
2. Copy each one and paste it right after the "=" on the matching line below
   (replace the <paste ...> text). Keep the label; only replace the placeholder.
3. Save this file (Ctrl+S / Cmd+S), then tell Claude "done".
Claude will move these into your keys file for you and then DELETE this file.
Do NOT paste these values into the chat.

CLIENT ID = {PLACEHOLDER}
CLIENT SECRET = {PLACEHOLDER}
REFRESH TOKEN = {PLACEHOLDER}
"""


def _default_env_path():
    """Best-effort .env location (mirrors check_env.py's usual spots). Checkpoint 4 creates it."""
    if os.environ.get("FBA_ENV_PATH"):
        return Path(os.environ["FBA_ENV_PATH"])
    if os.environ.get("FBA_SECRETS_DIR"):
        return Path(os.environ["FBA_SECRETS_DIR"]) / ".env"
    home = Path.home()
    for c in (home / ".fba-secrets" / ".env",
              home / "fba-secrets" / ".env",
              home / "AppData" / "Local" / "fba-secrets" / ".env",
              home / ".env"):
        if c.exists():
            return c
    return home / ".fba-secrets" / ".env"


def _open_in_editor(path):
    """Open the file in the OS default text editor (best-effort, non-fatal)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606 — intended: open in default editor
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass  # opening is a convenience; the path is printed regardless


def _mask(v):
    v = v.strip()
    if len(v) <= 4:
        return "…" + v
    return "…" + v[-4:]


def do_open(paste_file):
    paste_file.write_text(PASTE_TEMPLATE, encoding="utf-8")
    _open_in_editor(paste_file)
    print(f"Opened the paste file: {paste_file}")
    print("Tell the user: paste each of the 3 Amazon values after the '=' on its line, SAVE,")
    print('then say "done". Then run this again with --commit.')


def _parse_paste(paste_file):
    """Return {env_key: value} for lines that were actually filled in. Never prints values."""
    text = paste_file.read_text(encoding="utf-8")
    found = {}
    for label, env_key in FIELDS:
        # match "LABEL = <value>" case-insensitively; take everything after the FIRST '='
        # (refresh tokens can themselves contain '=' / '|', so split once only)
        pat = re.compile(rf"^\s*{re.escape(label)}\s*=(.*)$", re.IGNORECASE | re.MULTILINE)
        m = pat.search(text)
        if not m:
            continue
        val = m.group(1).strip().strip('"').strip("'")
        if val and PLACEHOLDER not in val and "<paste" not in val.lower():
            found[env_key] = val
    return found


def _upsert_env(env_path, values):
    """Insert/replace KEY=value lines in .env, preserving everything else. Values never printed."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    keys = set(values)
    out, seen = [], set()
    for line in lines:
        m = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        if m and m.group(1) in keys:
            k = m.group(1)
            out.append(f"{k}={values[k]}")
            seen.add(k)
        else:
            out.append(line)
    for k in values:
        if k not in seen:
            out.append(f"{k}={values[k]}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)  # tighten perms where the OS honors it
    except Exception:
        pass


def do_commit(paste_file, env_path):
    if not paste_file.exists():
        sys.exit(f"No paste file at {paste_file} — run with --open first.")
    values = _parse_paste(paste_file)
    missing = [k for _, k in FIELDS if k not in values]
    if missing:
        # Do NOT write a half-filled set or delete the file — let the user finish.
        print("Not all 3 values are filled in yet. Still blank: "
              + ", ".join(k for k in ("LWA_CLIENT_ID", "LWA_CLIENT_SECRET", "SP_REFRESH_TOKEN")
                          if k in missing))
        print(f"Have the user finish + save {paste_file.name}, then run --commit again.")
        sys.exit(1)
    _upsert_env(env_path, values)
    # shred + delete the temp paste file
    try:
        paste_file.write_text("\n" * 5, encoding="utf-8")
    except Exception:
        pass
    paste_file.unlink(missing_ok=True)
    print(f"Wrote 3 Amazon keys into {env_path} and deleted the paste file. Masked check:")
    for _, k in FIELDS:
        print(f"  {k:<18} ✓ set ({_mask(values[k])})")
    print("Next: run check_env.py to confirm, then validate_spapi.py for a live 200.")


def main():
    ap = argparse.ArgumentParser(description="Paste-and-file the 3 Amazon secrets into .env (model never sees them).")
    ap.add_argument("--open", action="store_true", help="create + open the labelled paste file")
    ap.add_argument("--commit", action="store_true", help="file the pasted values into .env, then delete the temp")
    ap.add_argument("--paste-file", default=DEFAULT_PASTE_NAME, help=f"paste file path (default: ./{DEFAULT_PASTE_NAME})")
    ap.add_argument("--env", default=None, help="path to the .env (default: auto-detect the fba-secrets .env)")
    args = ap.parse_args()

    paste_file = Path(args.paste_file).expanduser().resolve()
    env_path = Path(args.env).expanduser() if args.env else _default_env_path()

    if args.open == args.commit:  # neither or both
        sys.exit("Pick exactly one: --open (create the paste file) or --commit (file the values).")
    if args.open:
        do_open(paste_file)
    else:
        do_commit(paste_file, env_path)


if __name__ == "__main__":
    main()
