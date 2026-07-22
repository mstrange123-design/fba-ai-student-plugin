# User first-run setup checklist

> **The one rule:** every value that is specific to *you* lives in **`_shared/config.json`**. Edit it **once** there. Never paste your IDs/paths into the individual skills — they all read config at runtime.

`config.json` is short on purpose (~40 lines — only what this kit's two skills actually read) —
the setup wizard writes almost all of it for you (Steps 1, 2, 4, 7). This checklist is only
useful if you're hand-editing instead of running the wizard, or want to see what each key does.

After you finish, open both live tiles and confirm they're no longer showing "awaiting first
robot run" once the daily Routine has run once.

---

## 1. Who you are — `business`
| Key | What it is |
|-----|-----------|
| `business.entity` | Your business / LLC name. |
| `business.owner_name` | Your first name. |
| `business.owner_email` | The Google account you're running everything under. |

## 2. Your tracker sheet — `ops_sheet`
| Key | What it is / how to find it |
|-----|-----------|
| `ops_sheet.sheet_id` | The long ID in your Google Sheet URL (`.../spreadsheets/d/`**`THIS`**`/edit`). |
| `ops_sheet.tabs.*.gid_numeric` | Each tab's numeric `gid` (in the URL when that tab is open: `...#gid=`**`THIS`**). Only 3 tabs matter in this kit: Pipeline Runs, Action Items, Bought. |

## 3. Your 3 tile switches — `adapters`
| Key | What it is |
|-----|-----------|
| `adapters.prep_center.provider` | `yes` / `manual` — do you use a prep center? Controls the lifecycle tile's lanes only (see `references/adapters.md`). |
| `adapters.cogs_tool.provider` | `yes` / `none` — do you use SellerBoard? Controls a tile label only. |
| `adapters.finance.provider` | `monarch` / `manual` — do you use Monarch? Controls whether the cash-flow tile shows real numbers or an honest "connect a bank feed" prompt. |

## 4. COGS — `cogs`
| Key | What it is |
|-----|-----------|
| `cogs.pre_bought_asins` | ASINs that already had cost history in SellerBoard **before** you started using this kit. If you have none, leave this `[]`. |

## 5. Your two live tiles — `live_artifact_feeds`
| Key | What it is |
|-----|-----------|
| `live_artifact_feeds.feeds.*.drive_file_id` | The Google Drive file ID for each of your 2 live-tile feeds (lifecycle-stages, fba-cash-flow-equilibrium). The wizard's `create_feed_files.py` (Step 7b) creates these on your own Drive and fills them in — you shouldn't need to touch this by hand. |

---

## Routine — schedule the daily cloud robot

The Cowork plugin is only half the system. The other half is the **cloud Routine** (`daily-amazon-finance`):
a Claude Code Routine that runs your robot scripts every morning, laptop off, and writes the Amazon /
prep / bank data into your sheet tabs. The Cowork pipeline then *reads* those tabs. Set it up once:

1. **Get the env block.** Run `setup-wizard` Step 8 (`scripts/emit_routine_env.py`) — it writes
   `output/routine-env-<date>.txt` containing every key the Routine needs (SP-API trio, Google token,
   plus whichever of `MONARCH_TOKEN` / `TCB_COOKIE` / `PW_REFRESH_TOKEN` / `PW_FIREBASE_KEY` /
   `PrepPortalA_EMAIL`+`PrepPortalA_PASSWORD` you wired). Never paste a secret into chat — load each from
   that file.
2. **Create the Routine** in the **Claude desktop app → Routines** (left sidebar) → New. (Older notes
   said "claude.ai → Routines"; the UI moved into the app. If it's elsewhere again, find it — don't
   stall.) Point it at **your own copy** of the robot repo (the scripts sit at the repo root), with the
   clone command the wizard printed. Schedule it **daily, ~6:00am your time**.
3. **Paste the env block** into the Routine's environment settings.
4. **Set Network access = Custom** and add the allowlist (the wizard prints it): at minimum
   `api.amazon.com`, `sellingpartnerapi-na.amazon.com`, `*.amazonaws.com` (the rotating S3 report host —
   the wildcard matters), `www.googleapis.com`, plus your prep/portal hosts
   (`app.prepportalb.io`, `unity.prepportala.com`) and `*.monarchmoney.com` if used. The default "Trusted"
   preset omits Amazon's hosts and the pull silently fails — this step is the #1 thing people miss.
5. **Smoke-test:** run the Routine once by hand. Confirm it wrote the **AMZ Inventory / AMZ Inbound /
   AMZ Settlements** tabs (and the Item Journey columns) with today's timestamp. If a 403 appears, it's
   almost always the allowlist in step 4.

### Canonical daily Routine command list (paste this as the Routine's Instructions)

⚠️ **Every write step MUST carry its write flag** (`--write`, or `--auto` for the roster seeder).
Without it, the script **dry-runs and persists NOTHING** — the pulls still succeed, so the run
looks healthy, but zero rows land and the dashboard shows zeros. This silently zeroed a real
user's board once; don't ship a command list without the flags. (`--write` on an adapter that
isn't connected is harmless — it just prints `status=NOT-CONNECTED` and skips.)

```
python -X utf8 pull_amazon_truth.py --write
python -X utf8 pull_amazon_truth.py --finance --write
python -X utf8 pull_monarch_deposits.py --write
python -X utf8 reconcile_cashback.py --write
python -X utf8 track_card_rewards.py --write
python -X utf8 pull_topcashback.py --write
python -X utf8 pull_prepportalb.py --write
python -X utf8 sync_bought_to_journey.py --auto
python -X utf8 fill_order_number.py --write
python -X utf8 detect_cancellations.py --write
python -X utf8 cancel_item_journey.py --write
python -X utf8 fill_gh.py --write
python -X utf8 fill_e.py --write
python -X utf8 fill_f.py --write
python -X utf8 fill_item_journey.py --write
python -X utf8 fill_k.py --write
python -X utf8 push_lifecycle_feed.py
python -X utf8 push_cash_flow_feed.py --write
```

`sync_bought_to_journey.py --auto` seeds one per-unit Item Journey row from each Bought box (the
board needs that roster before the funnel can fill). The two `push_*` steps differ:
`push_lifecycle_feed.py` takes **no flag** (and **refuses to publish an empty funnel over a feed
that already has real units** — it exits non-zero and leaves the good feed intact, a backstop
against the missing-`--write` mistake above). `push_cash_flow_feed.py` **DOES need `--write`** —
without it, it dry-runs and the **cash-flow tile silently never updates** (this exact omission left
a real user's cash tile frozen at zero). Keep the flag.

The adapter pulls (`pull_monarch_deposits`, `track_card_rewards`, `pull_topcashback`,
`pull_prepportalb`) self-skip with a `status=NOT-CONNECTED` line when their credential isn't in
your env yet — a fresh setup runs the whole chain clean and those steps light up as you connect
each tool later. No need to trim the chain.

Once this runs clean for a morning, "run the pipeline" in Cowork will find fresh tabs to reconcile.

---

## Don't change these (they're not personal)
Base URLs (`amazon`/`sellerboard`/`monarch`/prep portals), tolerances, claim windows, the COGS auto-write safety gate, the bulk-flip threshold, status enums. These are business logic, the same for everyone.

## Verify
1. `dry run the pipeline` → confirm it lists every step with your IDs (no "unresolved"/"missing config" notes).
2. Run one real pass and watch the end-of-run banner: a clean run prints `🏁 …complete`; if anything was missed it prints `⚠️ Pipeline INCOMPLETE` naming the exact step(s). That banner is produced by a script reading the run log — it will not lie to you.
