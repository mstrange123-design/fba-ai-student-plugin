# SP-API setup — each user registers their OWN private app (verified vs Amazon docs, June 2026)

**Model:** every user creates and self-authorizes **their
own private SP-API app** on their own Seller Central. Nobody shares an app. The user owns
their app, their credentials, and their data — the coach holds nothing and carries no data
liability. No 25-seller cap, no Appstore listing, no AWS/SigV4, no OAuth code exchange.

There are **two gates**: a one-time **developer profile** that Amazon REVIEWS, then **app creation
+ self-authorization** which is instant and self-serve.

> **⚠️ If the Seller Central UI doesn't match the steps below, it MOVED — do not stall.** Amazon
> reshuffles this area often. Web-search the current path yourself ("Seller Central register SP-API
> developer profile 2026" / "Solution Provider Portal develop apps") and adapt — you have the tools.
> Two moves already seen: the old **"Apps & Services → Develop Apps"** menu is now **"Partner
> Network → Develop Apps"** (direct URL `sellercentral.amazon.com/apps/manage`), and new-seller
> registration runs through the **Solution Provider Portal** enrollment flow (below).
>
> **Approval speed varies wildly.** Some clean US Professional accounts are approved **instantly /
> same session** (so registration + keys can sometimes be done live on the call). Others take days
> to ~2 weeks. Start it early to be safe, but don't assume a wait — try it and see.

---

## Gate A — Developer profile = PRE-CALL HOMEWORK (the only real wait)

The user starts this a few days to a couple weeks before the token call. **Amazon reviews it —
for a private app requesting only the non-restricted roles below, real-world 2026 approvals
usually land in a few days to ~1 week (sometimes same/next day), occasionally up to ~2 weeks in a
backlog. The "up to ~4 weeks" you'll read about is the restricted-role / buyer-PII path, which we
deliberately avoid.** Out of our control; cannot be rushed, so start early.

1. Sign in to Seller Central (must be a **Professional** account, and the user must be the
   **Primary User**).
2. Open **Partner Network → Develop Apps** (or go straight to `sellercentral.amazon.com/apps/manage`).
   If it's the first time, this drops into the **Solution Provider Portal** enrollment:
   - **Enroll in New Program → "Your Accounts":** click **Select Account** on the user's EXISTING
     business account (do NOT "Create Account" — that spins up a separate one).
   - **Solution Type Setup → "what do you intend to do":** check **"Build applications that use SP
     APIs"** (leave "Offer services" unchecked) → **Apply**.
3. Complete the **Solution Provider Profile** (this IS the developer-profile review):
   - **Contact Information:** org name, **org website = a REAL URL** (a plain `N/A` is rejected —
     the user's Amazon storefront URL works), home country = United States, contact name/email/
     phone.
   - **Data Access dropdown** → **"Private Solution Provider: I build application(s) to integrate my
     organization with Amazon APIs."** Plus a short use-case sentence (e.g. "automate my own seller
     account's inventory tracking and profit/cost bookkeeping").
   - **Roles** → request ONLY non-restricted: **Amazon Fulfillment**, **Inventory and Order
     Tracking**, **Finance and Accounting** (Brand Analytics is fine too). Do NOT check anything
     marked **(Restricted)** or the Buyer-* roles — buyer PII triggers a heavier review and can
     stall approval. (Roles can get over-selected by the form; keep it to these.)
   - **Security Controls questionnaire:** answer honestly for a solo seller. Most are a legitimate
     **Yes** for how this kit works (HTTPS in transit; single-operator access; keys stored in a
     gitignored `.env`, never in a public repo or chat; incident-report commitment). Only say Yes to
     the incident-response-plan / password-policy items if they're actually true (e.g. MFA is on).
   - Check the policy acknowledgment box → submit.
4. Amazon reviews it. Watch for either an **instant approval** ("developer profile has been
   reviewed") or an email — **check the account email + spam**, a clarification request silently
   stalls the review if missed. **Production apps are gated behind identity verification** — until
   that clears, app creation only offers **Sandbox** (useless — fake data). If only Sandbox is
   selectable at Gate B, the profile/identity isn't fully approved yet; finish that first.

**Hard gate:** do not schedule the on-call token step until the user confirms the approval
email arrived.

---

## Gate B — Create app + self-authorize = ON THE CALL (~15 min, smooth)

Once the profile is approved:

1. **Partner Network → Develop Apps → Add new app client** (or `sellercentral.amazon.com/apps/manage`)
   → name it, **API Type = SP-API**, **App Type = Production** (NOT Sandbox — Sandbox returns fake
   data; if Production is greyed out, identity verification from Gate A isn't complete), **Business
   entities = Sellers** → create. The app is in **Draft** (that's permanent + fine for private).
2. **Edit App → LWA credentials → View** → copy **`LWA_CLIENT_ID`** (`amzn1.application-oa2-client.…`)
   and **`LWA_CLIENT_SECRET`** (`amzn1.oa2-cs.v1.…`).
3. Click **Authorize app** (self-authorize own account). **The refresh token appears directly in
   the UI** — copy it as **`SP_REFRESH_TOKEN`**. (No redirect, no code exchange.)
4. Note the seller id (`SP_SELLER_ID`) from Account Info if needed.
5. Wizard validates: `scripts/validate_spapi.py` (refresh → access token →
   getMarketplaceParticipations). ✅ = HTTP 200 + marketplaces listed. Store the trio in `.env`.

All three values are the **user's own**. The coach's credentials never appear.

---

## Facts & gotchas

- **No AWS / SigV4** — removed Oct 2, 2023. A private app needs only LWA client id + secret +
  refresh token. Ignore any pre-Oct-2023 tutorial that walks through AWS/IAM (the #2 source of
  non-expert confusion).
- **Self-authorization cap = 10 per app** — a user authorizing their own account uses 1.
  Re-authorizing to rotate a token doesn't invalidate prior tokens; only burns a slot.
- **Draft is production** for a private app — "there is no reason to publish a private application."
- **Refresh token ~365-day life** — Amazon emails a 30-day warning; re-authorize is one click.
  LWA secret rotation policy ~180 days — worth a reminder.
- **Region:** NA sellers use `https://sellingpartnerapi-na.amazon.com` (validator default);
  EU/FE need the matching regional endpoint.
- **Individual seller plan → ineligible.** Confirm Professional + Primary User before the homework.
- **Report-type trap:** stay on inventory/inbound/finance/settlement + the `..._GENERAL`
  All-Orders report variants. The `_SHIPPING` / `_TAX` / `_INVOICING` variants carry buyer PII →
  restricted roles → don't request them.

Sources: developer-docs.amazon.com — `self-authorization`,
`onboarding-step-3-create-a-developer-profile`, `registering-your-application`,
`viewing-your-application-information-and-credentials`, `application-authorization-limits`,
`roles-in-the-selling-partner-api`, `report-type-values-order`.
