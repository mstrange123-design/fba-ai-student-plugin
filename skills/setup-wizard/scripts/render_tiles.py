#!/usr/bin/env python
"""
render_tiles.py — deterministically fill the two live-tile templates from the
user's OWN config, so nobody ever hand-copies a token, a file id, or reasons
out the bank-feed coupling table again.

WHY THIS EXISTS (2026-07-13, field call): the plugin's installed copy caches
stale in Cowork, so tile design updates have to be side-loaded as a finished HTML
file. Doing that fill by hand went wrong twice in one call — a bank-feed boolean
pair that doesn't exist in the kit (false/true), and a 1-vs-l typo in a Drive file
id copied off a screenshot. Both are transcription/reasoning errors a script does
not make. Run this in Claude Code (it can read the configs); hand the two output
files to Cowork, whose ONLY job is to replace {{DRIVE_READ_TOOL}} with its own
connector tool name and create_artifact each.

Reads TWO configs (that split is itself the confusion this removes):
  - robot repo config  (item_journey_config.json / config.json): sheet id,
    has_prep_center, feed ids, bank.fill_estimate_when_empty
  - plugin _shared/config.json: the adapter switches (cogs_tool, finance, prep)

Usage:
  python -X utf8 render_tiles.py [--robot-config PATH] [--plugin-config PATH]
                                 [--templates DIR] [--out DIR] [--drive-tool NAME]

Default: {{DRIVE_READ_TOOL}} is LEFT in the output for Cowork to fill (connector
tool names differ per user — managed vs custom). Pass --drive-tool only if you
already know the exact name.

No network. Deterministic. Exits non-zero if anything is missing or invalid.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))  # skills/


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"  ⚠  {msg}")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        die(f"could not read {path}: {e!r}")


def find_first(names, roots):
    """Return the first existing path matching any of `names` under any of `roots` (shallow + one level)."""
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for name in names:
            direct = os.path.join(root, name)
            if os.path.isfile(direct):
                return direct
        # one level down
        try:
            for entry in os.listdir(root):
                sub = os.path.join(root, entry)
                if os.path.isdir(sub):
                    for name in names:
                        cand = os.path.join(sub, name)
                        if os.path.isfile(cand):
                            return cand
        except OSError:
            pass
    return None


def locate_robot_config(explicit):
    if explicit:
        if not os.path.isfile(explicit):
            die(f"--robot-config not found: {explicit}")
        return explicit
    env = os.environ.get("IJ_CONFIG")
    if env and os.path.isfile(env):
        return env
    roots = [os.getcwd(), os.path.dirname(os.getcwd()), os.path.expanduser("~")]
    # Look for a json that actually has an item_journey block (avoids config.example.json placeholders)
    for name in ("item_journey_config.json", "config.json"):
        hit = find_first([name], roots)
        if hit:
            try:
                data = json.load(open(hit, encoding="utf-8"))
                if isinstance(data, dict) and "item_journey" in data:
                    return hit
            except Exception:
                continue
    die("could not auto-locate the robot config (looked for item_journey_config.json / config.json "
        "with an 'item_journey' block). Pass --robot-config PATH.")


def locate_plugin_config(explicit):
    if explicit:
        if not os.path.isfile(explicit):
            die(f"--plugin-config not found: {explicit}")
        return explicit
    cand = os.path.join(PLUGIN_ROOT, "_shared", "config.json")
    if os.path.isfile(cand):
        return cand
    hit = find_first(["config.json"], [os.path.join(PLUGIN_ROOT, "_shared")])
    if hit:
        return hit
    die("could not auto-locate the plugin _shared/config.json. Pass --plugin-config PATH.")


def locate_templates(explicit):
    if explicit:
        if not os.path.isdir(explicit):
            die(f"--templates dir not found: {explicit}")
        return explicit
    cand = os.path.join(PLUGIN_ROOT, "refresh-artifacts", "templates")
    if os.path.isdir(cand):
        return cand
    die("could not auto-locate refresh-artifacts/templates. Pass --templates DIR.")


def dig(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")


def check_id(name, value):
    if value is None or value == "":
        die(f"{name} is empty in the config — did setup finish? (create_feed_files.py fills feed ids)")
    if "YOUR_" in str(value) or "EXAMPLE" in str(value).upper():
        die(f"{name} still holds a placeholder ({value!r}) — this looks like an example config, not the user's.")
    if not DRIVE_ID_RE.match(str(value)):
        warn(f"{name} = {value!r} doesn't look like a Drive/Sheet id (unusual chars/length) — double-check.")


def bank_pair(finance_provider, fill_estimate_when_empty):
    """Return (HAS_BANK_FEED, BANK_FEED_IS_ESTIMATE) as Python bools, per the kit's coupling table.
    Only three valid combos exist: estimate->(T,T), monarch->(T,F), manual->(F,F)."""
    p = (finance_provider or "").strip().lower()
    fe = bool(fill_estimate_when_empty)
    if p == "monarch":
        if fe:
            warn("finance.provider=monarch but bank.fill_estimate_when_empty=true — "
                 "SETUP sets it false for Monarch so a real deposit isn't masked. Using monarch->(true,false).")
        return True, False
    if p == "estimate" or fe:
        if p == "manual":
            warn("finance.provider=manual but bank.fill_estimate_when_empty=true — treating as ESTIMATE "
                 "(the robot is filling estimates). If you truly opted out, set fill_estimate_when_empty=false.")
        return True, True
    if p == "manual":
        return False, False
    warn(f"finance.provider={finance_provider!r} unrecognized and no estimate signal — defaulting to "
         "ESTIMATE (the kit default). Set adapters.finance.provider explicitly to silence this.")
    return True, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robot-config")
    ap.add_argument("--plugin-config")
    ap.add_argument("--templates")
    ap.add_argument("--out", default=os.getcwd())
    ap.add_argument("--drive-tool", help="Exact Drive read tool name; default leaves {{DRIVE_READ_TOOL}} for Cowork.")
    args = ap.parse_args()

    robot_path = locate_robot_config(args.robot_config)
    plugin_path = locate_plugin_config(args.plugin_config)
    tpl_dir = locate_templates(args.templates)

    robot = load_json(robot_path)
    plugin = load_json(plugin_path)

    print("Sources:")
    print(f"  robot config : {robot_path}")
    print(f"  plugin config: {plugin_path}")
    print(f"  templates    : {tpl_dir}")
    print()

    # --- gather values (robot config is authoritative for the shared ones) ---
    item_journey_sheet_id = dig(robot, "item_journey", "sheet_id")
    lifecycle_feed_id = (dig(robot, "lifecycle_feed", "drive_file_id")
                         or dig(plugin, "live_artifact_feeds", "feeds", "lifecycle-stages", "drive_file_id"))
    cash_flow_feed_id = (dig(robot, "cash-flow_feed", "drive_file_id")
                         or dig(plugin, "live_artifact_feeds", "feeds", "fba-cash-flow-equilibrium", "drive_file_id"))
    pnl_feed_id = (dig(robot, "pnl_feed", "drive_file_id")
                   or dig(plugin, "live_artifact_feeds", "feeds", "fba-pnl-control", "drive_file_id"))

    has_prep = dig(robot, "prep_centers", "has_prep_center")
    if has_prep is None:
        has_prep = dig(plugin, "adapters", "prep_center", "provider") == "yes"
    else:
        # cross-check the plugin switch agrees
        plugin_prep = dig(plugin, "adapters", "prep_center", "provider") == "yes"
        if bool(has_prep) != plugin_prep:
            warn(f"has_prep_center disagreement: robot={has_prep} vs plugin adapter={plugin_prep}. "
                 "Using robot value (it drives the actual pipeline).")
    has_prep = bool(has_prep)

    cogs_provider = dig(plugin, "adapters", "cogs_tool", "provider")
    has_sellerboard = (cogs_provider == "yes")

    finance_provider = dig(plugin, "adapters", "finance", "provider")
    fill_est = dig(robot, "bank", "fill_estimate_when_empty")
    has_bank, is_estimate = bank_pair(finance_provider, fill_est)

    # --- validate ids ---
    check_id("ITEM_JOURNEY_SHEET_ID", item_journey_sheet_id)
    check_id("LIFECYCLE_FEED_FILE_ID", lifecycle_feed_id)
    check_id("CASH_FLOW_FEED_FILE_ID", cash_flow_feed_id)
    check_id("PNL_FEED_FILE_ID", pnl_feed_id)

    def jsbool(b):
        return "true" if b else "false"

    drive_tool_val = args.drive_tool if args.drive_tool else "{{DRIVE_READ_TOOL}}"

    tokens = {
        "ITEM_JOURNEY_SHEET_ID": item_journey_sheet_id,
        "LIFECYCLE_FEED_FILE_ID": lifecycle_feed_id,
        "CASH_FLOW_FEED_FILE_ID": cash_flow_feed_id,
        "PNL_FEED_FILE_ID": pnl_feed_id,
        "HAS_PREP_CENTER": jsbool(has_prep),
        "HAS_SELLERBOARD": jsbool(has_sellerboard),
        "HAS_BANK_FEED": jsbool(has_bank),
        "BANK_FEED_IS_ESTIMATE": jsbool(is_estimate),
        "DRIVE_READ_TOOL": drive_tool_val,
    }

    print("Resolved tokens:")
    src = {
        "ITEM_JOURNEY_SHEET_ID": "robot item_journey.sheet_id",
        "LIFECYCLE_FEED_FILE_ID": "robot lifecycle_feed.drive_file_id",
        "CASH_FLOW_FEED_FILE_ID": "robot cash-flow_feed.drive_file_id",
        "PNL_FEED_FILE_ID": "robot pnl_feed.drive_file_id",
        "HAS_PREP_CENTER": "robot prep_centers.has_prep_center",
        "HAS_SELLERBOARD": f"plugin adapters.cogs_tool.provider={cogs_provider!r}",
        "HAS_BANK_FEED": f"coupling(finance={finance_provider!r}, fill_est={fill_est!r})",
        "BANK_FEED_IS_ESTIMATE": f"coupling(finance={finance_provider!r}, fill_est={fill_est!r})",
        "DRIVE_READ_TOOL": "Cowork fills" if not args.drive_tool else "--drive-tool",
    }
    for k, v in tokens.items():
        print(f"  {k:24} = {str(v):45}  <- {src[k]}")
    print()

    # sanity: the (false,true) combo must never ship
    if tokens["HAS_BANK_FEED"] == "false" and tokens["BANK_FEED_IS_ESTIMATE"] == "true":
        die("invalid bank pair (HAS_BANK_FEED=false, BANK_FEED_IS_ESTIMATE=true) — this combo doesn't exist "
            "in the kit. Fix adapters.finance.provider / bank.fill_estimate_when_empty.")

    jobs = [
        ("lifecycle-stages.template.html", "lifecycle-stages.filled.html"),
        ("fba-cash-flow-equilibrium.template.html", "fba-cash-flow-equilibrium.filled.html"),
        ("fba-pnl-control.template.html", "fba-pnl-control.filled.html"),
    ]
    os.makedirs(args.out, exist_ok=True)
    wrote = []
    for tpl_name, out_name in jobs:
        tpl_path = os.path.join(tpl_dir, tpl_name)
        if not os.path.isfile(tpl_path):
            die(f"template missing: {tpl_path}")
        with open(tpl_path, "r", encoding="utf-8") as f:
            html = f.read()
        for k, v in tokens.items():
            html = html.replace("{{" + k + "}}", str(v))
        # every token must be gone except an intentionally-left DRIVE_READ_TOOL
        leftover = set(re.findall(r"\{\{([A-Z_]+)\}\}", html))
        allowed = set() if args.drive_tool else {"DRIVE_READ_TOOL"}
        bad = leftover - allowed
        if bad:
            die(f"{tpl_name}: unsubstituted tokens remain: {sorted(bad)}")
        out_path = os.path.join(args.out, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        wrote.append((out_path, sorted(leftover)))

    print("Wrote:")
    for path, left in wrote:
        note = "  (Cowork still fills {{DRIVE_READ_TOOL}})" if left else "  (fully filled)"
        print(f"  {path}{note}")
    print()
    if not args.drive_tool:
        print("Next: in Cowork, attach these files and say — 'replace {{DRIVE_READ_TOOL}} with your")
        print("Drive read tool name and create_artifact each; do not read the plugin template.'")
    print("Done.")


if __name__ == "__main__":
    main()
