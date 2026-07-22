# Google setup — each user creates their OWN private app (same idea as the Amazon step)

**Model:** every user creates and self-authorizes **their own private Google Cloud project**.
Nobody shares an app. The user owns their project, their credentials, and their data — the
coach holds nothing and carries no data liability. No shared quota, no "you broke my system"
risk, no dependency on the coach after this call.

Unlike Amazon, there's no review to wait on — this is entirely self-serve, live on the call,
~5 minutes.

---

## The flow — ON THE CALL (~5 min, smooth)

1. Go to **console.cloud.google.com** (sign in with the same Google account that owns your FBA
   Ops Sheet + Item Journey sheet). **Create a new project** — any name (e.g. "My FBA Pipeline").
2. **APIs & Services → Library** — enable two APIs: **Google Sheets API** and **Google Drive
   API**. (Search each by name, click it, click Enable.)
3. **Google Auth Platform** (its own top-level section now, not under "APIs & Services"). It
   has its own tabs: Overview / Branding / **Audience** / Clients / Data Access / Verification
   Center / Settings.
   - On **Branding**: fill the required fields (App name, your own email as support + developer
     contact). User type / Audience = **External**. Save.
   - On **Audience**: this is where **Publishing status** lives. Click **"Publish App"** to move
     it from Testing → In production. This is the one setting that matters — an unverified app
     that stays in Testing has every refresh token auto-expire after 7 days; "In production"
     (even without full Google verification) does not have that limit for the low-sensitivity
     scopes this kit uses. Once published, the page shows "In production" with a **"Back to
     testing"** button — that button is the undo, not a status you want; leave it alone.
   - Google will show an "unverified app" warning to anyone who consents — that's expected and
     harmless for a private single-user tool; full verification review is unnecessary overhead
     here.
4. **Clients → Create Credentials → OAuth client ID → Application type: Desktop app.** Name it
   anything, click Create.
5. Click **Download JSON** on the new credential → save it as `credentials.json` in your
   `fba-secrets` folder (the wizard tells you the exact path if you're unsure).
6. Wizard runs `scripts/google_oauth_local.py` — it opens your browser to YOUR OWN app's
   consent screen, you approve (click through the "unverified" warning — it's your own app),
   and it captures the token straight into your `.env`. **Validate:**
   `scripts/validate_google.py` reads your FBA Ops Sheet's title back — ✅ proves the token
   works and the sheet is shared with the right account.

All of it is the **user's own** — project, credentials, token. The coach's Google account
never appears anywhere in this flow.

---

## Facts & gotchas

- **"In production" is not the same as "Google-verified."** Verification is a separate, heavier
  review Google offers for public-facing apps with many users. A private single-user tool never
  needs it — publishing status alone (Testing → In production) is what controls the 7-day
  refresh-token expiry, and that's the only switch this kit needs flipped.
- **Scopes used are narrow on purpose:** `spreadsheets` (read/write your own Sheets),
  `drive.file` (touch only files this app itself creates — the 3 tile feed files, never your
  whole Drive), and `gmail.readonly` (the robot's order/cancellation email readers — read-only,
  never sends or deletes mail). No Calendar or anything else.
- **gmail.readonly needs three one-time clicks in your Cloud project** before re-running the
  auth script: (1) enable the **Gmail API** (APIs & Services → Library), (2) add the
  `gmail.readonly` scope on the consent screen's **Data access** page, (3) on the consent
  prompt, click **Advanced → proceed** past the "unverified app" warning — it's your own app
  reading your own mail. Cloud-Routine note: the Routine's allowed network domains must include
  `gmail.googleapis.com`, or Gmail calls fail with "Tunnel connection failed: 403".
- **Desktop app, not Web application** — the local consent-catcher in `google_oauth_local.py`
  needs a Desktop-app OAuth client; a Web-application client will bounce the redirect.
- **Free tier is plenty** — a Google Cloud project for this kit's call volume costs nothing and
  needs no billing account attached.
- **One project per user** — if you already have a Google Cloud project from something else,
  a fresh one for this kit keeps things simple, but reusing an existing project (with the same
  two APIs enabled) works too.
