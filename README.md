# Your Amazon FBA assistant

This is a clean, ready-to-install copy of the system you run your own Amazon FBA business with:
a **daily routine** that reconciles your buys all the way to the bank, an **item-journey board**
that shows every unit from *bought → prep → Amazon → sold → paid*, and a **cash-flow cycle** view —
all as live dashboards.

You install this plugin, run one **setup-wizard**, and it becomes *yours* — wired to your own Amazon account
and your own Google Sheet. Nothing here is your data; every personal value is a blank you fill.

## The 3 homes (where it all lives)

- **Home 1 — Claude (Cowork):** you install this plugin; it runs your daily routine + shows your live tiles.
- **Home 2 — Google Drive:** two Google Sheets (you copy your coach's templates) — your "filing cabinet."
- **Home 3 — a daily cloud Routine:** a small robot (the `fba-ai-student-robot` repo) that runs at ~6am with
  your laptop off and pulls your Amazon numbers into your sheets.

## The adapters (turn things on as you grow)

The core (Amazon + Google Sheets) works for everyone. Three optional slots plug in when you have them:

| Slot | If you have it | If you don't |
|------|----------------|--------------|
| **Prep center** | the wizard wires it; prep stages light up | board shows the short lane (Bought → Amazon → Sold → Paid) |
| **SellerBoard** | COGS checks run | skipped cleanly |
| **Bank (Monarch)** | bank tie-out + cash cycle run | skipped cleanly |

A slot you skip is left as a **dormant skeleton** — flip one setting later and it lights up. A brand-new
setup with nothing wired still runs end-to-end and reaches the 🏁 "complete" banner.

## Getting started (your coach walks you through this on the call)

1. Copy the two template Google Sheets into your Drive (your coach sends the two "Make a copy" links).
2. Install this plugin — in the **Claude desktop app**: Settings → **Plugins** → **Add** ▸
   **Add marketplace** → pick `fba-ai-student-plugin` from your GitHub list → **Sync** → click
   **`+`** on the plugin card. (You need the repo invite from your coach accepted first.
   Terminal users only: `/plugin marketplace add <coach-github-user>/fba-ai-student-plugin`
   then `/plugin install fba-ai@fba-ai` does the same thing.)
3. Run the wizard: tell Claude **"run the setup wizard"** and answer its questions.
4. (Pre-call homework) Register your own Amazon SP-API developer profile — Amazon's review is usually
   fast, often within minutes to a day. Once approved, the wizard grabs your token in ~15 minutes and your board fills in.

That's it — every skill reads `skills/_shared/config.json`, and the wizard fills that one file for you.
