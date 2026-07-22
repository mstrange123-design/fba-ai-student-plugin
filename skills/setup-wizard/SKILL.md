---
name: setup-wizard
description: Cowork finale for a NEW user who has already run SETUP.md in Claude Code (keys captured, config pushed, feed files created). This skill does ONLY the three things Cowork can do that a terminal cannot -- it takes the user's handoff block, proves the Google Drive connector can read their feed files, instantiates their two live dashboard tiles (Lifecycle Stages + Cash Flow Equilibrium) from templates, and walks them through creating the daily cloud Routine. It does NOT collect secrets or run Amazon/Google validators -- Cowork's sandbox can't reach api.amazon.com, so all credential work happens earlier in Claude Code (SETUP.md). Trigger on "run the setup wizard", "finish my setup", "build my dashboards", "set up my tiles", "onboard me", "user setup", "set up my FBA system", or any first-run user onboarding finale.
---

# Setup Wizard — the Cowork finale (tiles + Routine)

> **Setup happens in two places.** The heavy lifting — installing tools, cloning the repo,
> capturing Amazon + Google keys, writing config, creating the feed files, pushing to GitHub —
> is done **on the user's own computer in Claude Code**, driven by **SETUP.md** in their robot
> repo. Cowork can't reach `api.amazon.com` (sandboxed network), so credentials can never be
> validated here. This skill picks up **after** that, and does only what Cowork is uniquely good
> at: reading Drive files through the connector, publishing live artifact tiles, and setting up
> the Routine.

## Operating principles
- **Never paste a raw secret into chat.** You won't need one here — this phase handles only ids
  and display switches, no keys.
- **Auto-detect from the pushed config FIRST — don't make the user find a text block.** Every id
  and switch this skill needs already lives in the user's own `item_journey_config.json` (which
  their SETUP.md run pushed to their repo) and in their Drive feed files. So your DEFAULT is to
  recover them yourself (see "Recover the handoff automatically" below), not to ask for a pasted
  block. A live call proved the paste-the-block step dies the moment a session goes non-linear —
  the block scrolls out of reach and the user is stuck hunting for it. Auto-detect never has
  that failure. **If the user happens to still have the `=== READY FOR COWORK ===` block handy,
  great — it's a shortcut, not a requirement.** Either way you end up with the same ids.

---

## Step A — Prove the Drive read tool (gate — do NOT build tiles before this passes)
1. In YOUR OWN tool list, find the Google Drive file-read tool: a name ending in
   `read_file_content`. On a managed connector it's typically
   `mcp__claude_ai_Google_Drive__read_file_content`; a custom connector looks like
   `mcp__<connector-id>__read_file_content`. Never guess — use the exact name you can see.
2. **Test it:** call that tool with `fileId` = the **lifecycle feed id** from the handoff block.
   Expect the seed JSON back (contains `"awaiting first robot run"`).
3. If the call fails or the tool doesn't exist: the user's Google Drive connector isn't
   connected in Cowork, or is connected under a DIFFERENT Google account than the one the feeds
   were created under (must match the email used in SETUP.md Checkpoint 7). Fix that and re-test.
   Do not proceed.

## Step B — Instantiate the two live tiles (the headline deliverable)

> **Shortcut (preferred, and REQUIRED when the installed plugin is cache-stale):** don't fill the
> tokens by hand. In **Claude Code**, run `scripts/render_tiles.py` — it reads the user's robot
> config + plugin `_shared/config.json` and writes `lifecycle-stages.filled.html` +
> `fba-cash-flow-equilibrium.filled.html` with every token filled deterministically (including the
> bank-feed coupling table and the exact feed ids — no hand-copied ids, no wrong boolean pairs). It
> leaves only `{{DRIVE_READ_TOOL}}` for you. Then Cowork's whole job is: attach those two files,
> replace `{{DRIVE_READ_TOOL}}` with your connector tool name, and `create_artifact` each — do NOT
> re-read the plugin template (it may be the stale cached copy). This exists because hand-filling
> went wrong twice on one call (2026-07-13): an invalid bank pair and a 1-vs-l feed-id typo.

If you are filling by hand anyway (fresh install, plugin not stale), read
`../refresh-artifacts/templates/lifecycle-stages.template.html` and
`fba-cash-flow-equilibrium.template.html`, replace the tokens, then `create_artifact` each:
- `{{LIFECYCLE_FEED_FILE_ID}}` / `{{CASH_FLOW_FEED_FILE_ID}}` → the two feed ids from the handoff block.
- `{{DRIVE_READ_TOOL}}` → the exact tool name that PASSED Step A. Nothing else.
- `{{ITEM_JOURNEY_SHEET_ID}}` → their Item Journey sheet id (handoff block).
- `{{HAS_PREP_CENTER}}` (lifecycle tile only) → bare JS boolean from the handoff block. When
  `false` the lifecycle board drops the three prep lanes (D/E/F) and shows a clean from-home
  journey (Bought → Arrived at Amazon → Prime → Sold → Paid Out → In the Bank). Must be
  `true`/`false`, never quoted — an unsubstituted or quoted value breaks the tile's script.
- `{{HAS_SELLERBOARD}}` (lifecycle tile only) → bare JS boolean. When `false` the panel header
  drops the "SellerBoard planner" label and reads "cost basis: your Costs tab". Must be
  `true`/`false`, never quoted.
- `{{HAS_BANK_FEED}}` and `{{BANK_FEED_IS_ESTIMATE}}` (BOTH tiles — bake the same pair into
  lifecycle AND cash-flow) → two bare JS booleans, derived from `adapters.finance.provider` in the
  handoff block. Set them by the coupling table (must match the robot's `bank.fill_estimate_when_empty`):

  | `finance.provider` | `HAS_BANK_FEED` | `BANK_FEED_IS_ESTIMATE` | what the user sees |
  |---|---|---|---|
  | **`estimate`** (default) | `true` | `true` | cash-flow shows real numbers, labeled 🟠 estimated (in-bank date = Amazon transfer + 1 business day); lifecycle stage-K reads "estimated" |
  | `monarch` | `true` | `false` | real bank-confirmed numbers, no estimate label |
  | `manual` (rare opt-out) | `false` | `false` | cash-flow shows the "connect a bank feed" em-dash state; lifecycle stage-J reads "Amazon-confirmed · no bank tie-in" |

  Both must be `true`/`false`, never quoted — an unsubstituted or quoted value breaks the tile's script.

Open each tile once: it should render the "awaiting first robot run" seed (proof the tile can reach
the feed). Their own numbers appear after the first Routine run (Step C).

## Step C — Create the daily Routine + smoke test
**You hand the user every value; they only click and paste.** Never point them at a file to "go
find" something — you read it and print it inline. Only ONE thing stays file-borne: the secret env
values (blind-paste, never in chat).

1. **Location:** the **Claude desktop app → Routines** (left sidebar) → New. (Older notes said
   "claude.ai → Routines"; the UI moved into the app — if it's elsewhere again, find it, don't stall.)
   Before opening the form, make sure the **Claude GitHub App is installed on their repo**
   (github.com/apps/claude), or the repo won't appear in the picker — and the form **wipes if they
   navigate away**, so do that in a separate tab.
2. **Print the non-secret blocks inline, in chat**, straight from their `routine-form-pack-<date>.txt`
   (or reconstruct them — you can read the canonical command list from this plugin's
   `references/user-setup.md`): ① the clone command, ② the Routine **Name**, ③ the **Instructions**
   command list in one code box (keep every `--write`/`--auto` flag), ④ the **schedule** — ask their
   timezone, ⑤ the **Network allowlist**, one host per line. The user pastes each into the form.
3. **Environment (secrets — the one blind step):** say *"When you're ready — pause screen-sharing if
   you're sharing — open `routine-SECRETS-<date>.txt`, select all, copy, close it, paste into the
   Routine's Environment box, tell me, and delete the file. I will never print those values here."*
4. **Network access = Custom** (not the default "Trusted" — it omits Amazon's hosts and the pull
   silently fails, the #1 miss). The hosts are in block ⑤ above.
5. **Run it once by hand.** Confirm it wrote the **AMZ Inventory / AMZ Inbound / AMZ Settlements**
   tabs (and the Item Journey columns), ending with the **🏁** banner. Un-wired adapters read
   `SKIPPED — TRUE_BLOCK:ADAPTER_NONE`, never a red FAIL.
6. **Refresh both tiles** — they now show the user's real numbers. That's the finish line.
7. **If the handoff shows Migration PENDING** (`answers.json: past_records` ≠ `none`): tell them their
   next stop is **Claude Code with MIGRATE.md** — their Claude runs the import; they only answer a few
   business questions and approve the preview. (You're the announcer here; the doer is Claude Code.)

---

## Recover the handoff automatically (the DEFAULT path — no pasted block needed)
Everything this skill needs is recoverable without secrets, straight from what SETUP.md already
pushed. Do this by default; only fall back to a pasted `=== READY FOR COWORK ===` block if the
user volunteers one:
- **Feed ids:** Drive-search the user's Drive for `lifecycle-feed.json` and `cash-flow-feed.json`
  by name, or read them from `live_artifact_feeds.feeds.*.drive_file_id` in their pushed
  `item_journey_config.json`.
- **Sheet ids + switches:** read them from that same `item_journey_config.json`
  (`ops_sheet_id`, `item_journey.sheet_id`, `prep_centers.has_prep_center`, adapter blocks).
- **Routine handoff:** re-emit both files in Claude Code with `emit_routine_env.py` (needs their
  `.env`) — it writes the non-secret `routine-form-pack-<date>.txt` (print this inline) plus the
  `routine-SECRETS-<date>.txt` (blind-paste only). Cowork can't emit them — it never sees their secrets.

## Verifying the whole system (user-facing capstone)
The one line a user runs at the end of each lesson is `verify.py <leg>` — but **run it in Claude
Code, not here**. Cowork can't reach `api.amazon.com`, so `verify.py amazon` can never pass in the
Cowork sandbox; that's expected, not a bug. The legs map to the course lessons:
`amazon` (SP-API live), `google` (reads the Ops Sheet), `routine` (the daily Routine ran — Ops Sheet
fresh within 36h), `bank` (Monarch, optional), `keys` (`.env` well-formed, no network), and `all`
(everything + the Cowork eyeball reminder that the two tiles load). The `cowork` leg is a manual
checklist — plugin installed, Drive connected, both tiles render — the one thing a script can't prove.

## Scripts (all live here; SETUP.md in the robot repo drives most of them in Claude Code)
- `scripts/verify.py` — end-of-lesson capstone: `verify.py amazon|google|routine|cowork|bank|keys|all`.
- `scripts/check_env.py` — locate + sanity-check the `.env` (no network, never prints a secret).
- `scripts/validate_spapi.py` / `validate_google.py` / `validate_routine.py` / `validate_monarch.py`
  — the live credential tests each `verify.py` leg wraps.
- `scripts/google_oauth_local.py` — Google consent against the user's OWN Cloud app (Claude Code).
- `scripts/write_cowork_config.py` — patch `_shared/config.json` from `answers.json`.
- `scripts/create_feed_files.py` — create the feed files on the user's Drive + write the ids into
  both configs (run once, in Claude Code).
- `scripts/emit_routine_env.py` — build the Routine env + allowlist handoff file.
- `references/spapi-authorize.md` — the exact Amazon developer-profile + authorize flow + gotchas.
- `references/google-cloud-authorize.md` — the exact Google self-authorize flow + gotchas.
- `references/user-setup.md` — what each config key means + the Routine setup detail.
