# PM Internship Job Alerter

Watches company careers pages around the clock and emails me the moment a
**Summer 2027 product management internship** goes up.

A GitHub Actions workflow runs on a schedule, checks ~60 company job boards,
matches postings against a keyword ruleset, and sends one digest email
containing every new hit — with a direct link to the posting and a link to that
company's careers page. Each posting is alerted exactly once, ever.

No server, no database, no hosting bill. GitHub runs it on a schedule and the
repo itself stores the record of what's already been sent.

---

## How it works

```
GitHub Actions cron
        │
        ▼
companies.yml ──▶ ATS adapters ──▶ keyword matcher ──▶ dedupe ─────────▶ email
   (you edit)      (job feeds)       (rules.yml)     state/alerted.json  (Resend)
                                                     (committed to repo)
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
| `app/store.py` | Reads/writes `state/alerted.json`. |
| `state/alerted.json` | Every posting already emailed. Committed by the workflow. |
| `.github/workflows/check-jobs.yml` | The schedule and the run steps. |
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
| Google careers | `ats: google` |
| Amazon jobs | `ats: amazon` |
| *no public feed* | `ats: linkedin` + `company_slug: some-co` |

```yaml
  - name: Some Company
    ats: greenhouse
    token: somecompany
```

Commit and push — Railway redeploys and picks it up. If the company already has
a matching posting live, you get an email on the next cycle.

Tip: if a careers page is embedded on the company's own domain, view the page
source or the network tab and look for one of the hostnames above.

### Coverage caveats

Not every company publishes an open job feed. Two tiers here:

**Direct feeds (complete and reliable)** — every posting on the board is read.
That's every company above except the five below.

**LinkedIn guest search (best-effort net)** — Microsoft, Meta, LinkedIn, Uber
and Intuit publish no public feed, so their postings are read from LinkedIn's
public search, filtered to that company. This is keyword-driven and returns
roughly 10 results per query, so it can miss a posting that a real ATS feed
would always catch. It also varies run to run. Treat these five as a useful
net, not a guarantee.

**Apple is not covered.** Their careers search page ignores the search query
server-side (it returns the same retail jobs no matter what you ask for), and
their internal API is tied to browser session state and returns empty results
intermittently. There's no stable way to read it, so it was left out rather
than shipped as something that looks like it works but doesn't. Check
[jobs.apple.com](https://jobs.apple.com/en-us/search) by hand, or set up an
email alert on their site.

**"Gemini"** in `companies.yml` is the crypto exchange (Greenhouse board
`gemini`). Google's Gemini roles are posted under Google, which is covered by
the `google` adapter.

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

## The schedule

`.github/workflows/check-jobs.yml` runs `python -m app.main --once` and commits
`state/alerted.json` if anything new was sent.

**Real-world cadence: every 2-5 hours, not every 20 minutes.** The cron is set
to `*/20`, but GitHub heavily deprioritizes frequent scheduled jobs on free
public repos and silently drops most slots. Measured gaps over one day were
123, 158, 211, 235 and 319 minutes. This is accepted on purpose: internship
postings stay open for weeks, so a few hours' delay costs nothing, and the
alternatives (an external service holding a GitHub token, or parking a runner
24/7) add risk for no real benefit. If you ever do need true 20-minute polling,
the fix is an external scheduler calling the `workflow_dispatch` API. Two settings
live in the repo's GitHub settings rather than in code:

| Where | Name | Value |
|---|---|---|
| Secrets | `RESEND_API_KEY` | from resend.com/api-keys |
| Variables | `ALERT_EMAIL_TO` | your email |
| Variables | `ALERT_EMAIL_FROM` | `Job Alerter <onboarding@resend.dev>` |

The key is a secret (encrypted, never printed in logs); the two email addresses
are plain variables.

### Maintaining it

- **Run it now:** Actions tab → *Check for PM internships* → *Run workflow*.
  Tick `dry_run` to see what it would send without sending anything.
- **Did it run?** The Actions tab lists every run. Green check = ran fine.
- **Long gaps are normal, not a fault.** See the cadence note above: 2-5 hours
  between runs is expected behaviour, not something broken.
- **GitHub pauses schedules on public repos after 60 days of no commits.**
  Pushing anything — even a new company — resets the clock. If alerts go quiet
  for weeks, check this first.
- **A board that breaks doesn't break the run.** Failures are logged and listed
  at the bottom of the next alert email, and the other companies still get
  checked.
- **Resetting:** delete an entry from `state/alerted.json` to be re-alerted
  about that posting. Delete the whole file to be re-alerted about everything.

Resend's shared `onboarding@resend.dev` sender only delivers to the address you
signed up with, which is all this needs. To send anywhere else, verify a domain
in Resend and change `ALERT_EMAIL_FROM`.
