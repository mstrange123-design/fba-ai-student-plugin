# Adapters — the 3 yes/no switches (v1: tile display only)

In this kit, the 3 adapters are **display switches for your two live tiles** — nothing more yet.
"Yes" just means your tile shows the fuller journey (prep lanes, SellerBoard label, real cash
numbers); "no" means it shows an honest, clean version instead. **Nobody logs into your prep
center or SellerBoard for you yet — that automation is a later lesson, not this kit.**

Everything lives in `_shared/config.json → adapters`. There's nothing else to configure.

```jsonc
"adapters": {
  "prep_center": { "provider": "manual" },   // "yes" or "manual"
  "cogs_tool":   { "provider": "none" },     // "yes" or "none"
  "finance":     { "provider": "manual" }    // "monarch" or "manual"
}
```

---

## `prep_center` — "Do you use a prep center?"

- **`manual`** (default): the lifecycle tile shows a clean from-home journey (Bought → Amazon →
  Sold → Paid).
- **`yes`**: the lifecycle tile shows the fuller journey with prep lanes (Bought → at prep center
  → shipped to Amazon → Sold → Paid).
- Either way, nothing logs into a prep-center portal on your behalf. If you'd like that
  automated (Cowork pulling your prep-center data automatically), that's a follow-on lesson —
  ask your coach.

## `cogs_tool` — "Do you use SellerBoard?"

- **`none`** (default): the tile reads "cost basis: your Costs tab."
- **`yes`**: the tile shows the "SellerBoard planner" label.
- Either way, nothing writes your cost-of-goods into SellerBoard automatically yet — that's a
  follow-on lesson.

## `finance` — "How do you see your bank — Monarch, or just your bank's site?"

- **`manual`** (default): the cash-flow tile shows an honest "connect a bank feed to unlock your
  cash cycle" prompt instead of numbers.
- **`monarch`**: the cash-flow tile shows your real cash-cycle numbers.

---

Set these once in the wizard (Step 4) — you can always change your mind later by editing
`_shared/config.json → adapters` directly and re-opening the tile.
