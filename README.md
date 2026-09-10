# PM Internship Job Alerter

A worker that watches company careers pages around the clock and emails me the
moment a **Summer 2027 product management internship** goes up.

It polls every 20 minutes, matches postings against a keyword ruleset, and
sends one digest email per cycle containing every new hit — with a direct link
to the posting and a link to that company's full careers page. Each posting is
alerted exactly once, ever.

---

## How it works

```
companies.yml ──▶ ATS adapters ──▶ keyword matcher ──▶ dedupe (SQLite) ──▶ email
   (you edit)      (job feeds)       (rules.yml)        (Railway volume)   (Resend)
```

Companies don't get scraped. Nearly every careers page is powered by an
applicant-tracking system — Greenhouse, Lever, Ashby, Workday, SmartRecruiters,
Workable — and each exposes a public JSON feed that the careers page itself
reads from. The alerter reads that same feed, so it sees exactly what the
website shows, without fighting JavaScript rendering. The links it sends you
are the real public posting URLs (usually on the company's own domain).

| File | What it's for |
|---|---|
| `companies.yml` | **The list you edit.** Add or remove companies, push, done. |
| `rules.yml` | What counts as a match — job-title keywords and the target year. |
| `app/sources.py` | One adapter per ATS platform. |
| `app/matcher.py` | Applies `rules.yml` to each posting. |
| `app/store.py` | SQLite record of what's already been alerted. |
| `app/notify.py` | Builds and sends the digest email via Resend. |
| `app/main.py` | The polling loop. |

## Adding a company

Open the company's careers page and read the URL:

| Careers URL looks like | Add this |
|---|---|
| `job-boards.greenhouse.io/COMPANY` | `ats: greenhouse` + `token: COMPANY` |
| `jobs.lever.co/COMPANY` | `ats: lever` + `token: COMPANY` |
| `jobs.ashbyhq.com/COMPANY` | `ats: ashby` + `token: COMPANY` |
| `jobs.smartrecruiters.com/COMPANY` | `ats: smartrecruiters` + `token: COMPANY` |
| `apply.workable.com/COMPANY` | `ats: workable` + `token: COMPANY` |
| `TENANT.wd5.myworkdayjobs.com/SITE` | `ats: workday` + `token: TENANT`, `host: wd5`, `site: SITE` |

```yaml
  - name: Some Company
    ats: greenhouse
    token: somecompany
```

Commit and push — Railway redeploys and picks it up. If the company already has
a matching posting live, you get an email on the next cycle.

Tip: if a careers page is embedded on the company's own domain, view the page
source or the network tab and look for one of the hostnames above.

## Tuning what matches

Everything lives in `rules.yml`: `product_terms`, `intern_terms`,
`exclude_terms`, and `target_year`. A posting matches when its **title** hits a
product term *and* an intern term, hits no exclude term, and doesn't name a
year other than the target. Getting noise? Add a word to `exclude_terms`.
Missing something? Add to `product_terms`.

## Running it locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # then fill in RESEND_API_KEY

# See what would alert, without sending mail or recording anything:
.venv/bin/python -m app.main --dry-run

# One real cycle:
.venv/bin/python -m app.main --once

# Forever:
.venv/bin/python -m app.main
```

## Deploying on Railway

1. Create a project from this GitHub repo.
2. Attach a **volume** mounted at `/data` — this is what keeps the alerter from
   re-emailing you about every open job after each redeploy.
3. Set these variables:

| Variable | Value |
|---|---|
| `RESEND_API_KEY` | from resend.com/api-keys |
| `ALERT_EMAIL_TO` | your email |
| `ALERT_EMAIL_FROM` | `Job Alerter <onboarding@resend.dev>` |
| `DATA_DIR` | `/data` |
| `POLL_INTERVAL_MINUTES` | `20` |

Resend's shared `onboarding@resend.dev` sender only delivers to the address you
signed up with, which is all this needs. To send anywhere else, verify a domain
in Resend and change `ALERT_EMAIL_FROM`.
