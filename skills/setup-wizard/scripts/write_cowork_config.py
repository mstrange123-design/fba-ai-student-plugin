#!/usr/bin/env python
"""write_cowork_config.py — patch _shared/config.json from a user's answers.

Read-modify-write (idempotent): loads the existing config.json, overlays only the
user-specific values from answers.json, re-validates, writes back with the same
formatting. Never blind-overwrites; re-running updates in place. Secrets are NOT written
here — they live in .env / the Routine env. This only writes ids, urls, gids, adapters.

answers.json shape (all keys optional except where noted):
{
  "owner_name": "...", "owner_email": "...", "entity": "...",
  "ops_sheet_id": "...",                         # from their FBA Ops Sheet URL
  "tab_gids": {"Pipeline Runs":"123", "Action Items":"456", "Bought":"789"},
  "adapters": { "prep_center": {...}, "cogs_tool": {...}, "finance": {...} },
  "pre_bought_asins": []
}

Usage:
  python -X utf8 write_cowork_config.py answers.json
  python -X utf8 write_cowork_config.py answers.json --config /path/to/_shared/config.json --dry-run
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.normpath(os.path.join(HERE, "..", "..", "_shared", "config.json"))


def patch(cfg, ans):
    changed = []
    b = cfg.setdefault("business", {})
    for k_ans, k_cfg in [("owner_name", "owner_name"), ("owner_email", "owner_email"), ("entity", "entity")]:
        if ans.get(k_ans):
            if b.get(k_cfg) != ans[k_ans]:
                changed.append(f"business.{k_cfg}")
            b[k_cfg] = ans[k_ans]

    sb = cfg.setdefault("ops_sheet", {})
    if ans.get("ops_sheet_id"):
        if sb.get("sheet_id") != ans["ops_sheet_id"]:
            changed.append("ops_sheet.sheet_id")
        sb["sheet_id"] = ans["ops_sheet_id"]

    # tab gids: match by the tab's gid_name (the dumpGids() keys are tab display names)
    gids = ans.get("tab_gids") or {}
    if gids:
        tabs = sb.get("tabs", {})
        byname = {}
        for key, meta in tabs.items():
            if isinstance(meta, dict) and meta.get("gid_name"):
                byname[meta["gid_name"]] = (key, meta)
        for tabname, gid in gids.items():
            if tabname in byname:
                _, meta = byname[tabname]
                if str(meta.get("gid_numeric")) != str(gid):
                    changed.append(f"tabs[{tabname}].gid_numeric")
                meta["gid_numeric"] = str(gid)

    if ans.get("adapters"):
        cfg.setdefault("adapters", {})
        # preserve the $note; overlay each slot the answers provide
        for slot in ("prep_center", "cogs_tool", "finance"):
            if slot in ans["adapters"]:
                cfg["adapters"][slot] = {**cfg["adapters"].get(slot, {}), **ans["adapters"][slot]}
                changed.append(f"adapters.{slot}")

    if "pre_bought_asins" in ans:
        cfg.setdefault("cogs", {})["pre_bought_asins"] = ans["pre_bought_asins"]
        changed.append("cogs.pre_bought_asins")

    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("answers")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(a.answers, "r", encoding="utf-8") as f:
        ans = json.load(f)
    with open(a.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    changed = patch(cfg, ans)
    # validate the result is still valid JSON-serializable
    out = json.dumps(cfg, indent=2, ensure_ascii=False)
    json.loads(out)  # round-trip guard

    if a.dry_run:
        print(f"[dry-run] would change {len(changed)} key(s): {', '.join(changed) or '(none)'}")
        return 0

    with open(a.config, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(f"✅ wrote {a.config} — {len(changed)} key(s) updated: {', '.join(changed) or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
