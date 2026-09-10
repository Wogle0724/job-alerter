"""Fetch job postings from applicant-tracking systems.

Almost every company runs their careers page on a handful of ATS platforms,
and each one exposes a public JSON feed. Reading those feeds is far more
reliable than scraping a JavaScript-rendered careers page, so each adapter
below speaks one platform's API and returns the same simple shape:

    {"id", "title", "location", "url", "description"}
"""

import html
import logging
import re
from urllib.parse import urljoin

import requests

log = logging.getLogger(__name__)

TIMEOUT = 25
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


class SourceError(Exception):
    """A company's job feed could not be read."""


def _get(url, **kwargs):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r


def _strip_html(raw):
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


# --------------------------------------------------------------------------
# Adapters
# --------------------------------------------------------------------------


def greenhouse(c):
    token = c["token"]
    data = _get(
        f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
        params={"content": "true"},
    ).json()
    out = []
    for j in data.get("jobs", []):
        out.append(
            {
                "id": str(j.get("id")),
                "title": j.get("title", ""),
                "location": (j.get("location") or {}).get("name", ""),
                "url": j.get("absolute_url", ""),
                "description": _strip_html(j.get("content", "")),
            }
        )
    return out


def lever(c):
    token = c["token"]
    data = _get(
        f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"}
    ).json()
    out = []
    for j in data:
        cats = j.get("categories") or {}
        out.append(
            {
                "id": str(j.get("id")),
                "title": j.get("text", ""),
                "location": cats.get("location", ""),
                "url": j.get("hostedUrl", ""),
                "description": j.get("descriptionPlain", ""),
            }
        )
    return out


def ashby(c):
    token = c["token"]
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}").json()
    out = []
    for j in data.get("jobs", []):
        out.append(
            {
                "id": str(j.get("id")),
                "title": j.get("title", ""),
                "location": j.get("location", "") or "",
                "url": j.get("jobUrl", ""),
                "description": _strip_html(j.get("descriptionHtml", "")),
            }
        )
    return out


def smartrecruiters(c):
    token = c["token"]
    out = []
    offset = 0
    while offset < 400:
        data = _get(
            f"https://api.smartrecruiters.com/v1/companies/{token}/postings",
            params={"limit": 100, "offset": offset},
        ).json()
        batch = data.get("content", [])
        for j in batch:
            loc = j.get("location") or {}
            city = ", ".join(x for x in [loc.get("city"), loc.get("country")] if x)
            out.append(
                {
                    "id": str(j.get("id")),
                    "title": j.get("name", ""),
                    "location": city,
                    "url": f"https://jobs.smartrecruiters.com/{token}/{j.get('id')}",
                    "description": "",
                }
            )
        if len(batch) < 100:
            break
        offset += 100
    return out


def workable(c):
    token = c["token"]
    data = _get(
        f"https://apply.workable.com/api/v1/widget/accounts/{token}",
        params={"details": "true"},
    ).json()
    out = []
    for j in data.get("jobs", []):
        out.append(
            {
                "id": str(j.get("shortcode")),
                "title": j.get("title", ""),
                "location": ", ".join(
                    x for x in [j.get("city"), j.get("country")] if x
                ),
                "url": j.get("url") or j.get("application_url", ""),
                "description": _strip_html(j.get("description", "")),
            }
        )
    return out


def workday(c):
    """Workday tenants hold thousands of jobs, so search instead of listing.

    `host` is the shard in the careers URL (wd1, wd5, wd12, ...) and `site`
    is the board name, both visible in the company's careers URL:
        https://<token>.<host>.myworkdayjobs.com/<site>
    """
    token, host, site = c["token"], c.get("host", "wd1"), c["site"]
    searches = c.get("searches") or ["intern", "co-op", "product"]
    base = f"https://{token}.{host}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{token}/{site}/jobs"
    seen, out = set(), []
    for term in searches:
        for page in range(5):
            body = {
                "appliedFacets": {},
                "limit": 20,
                "offset": page * 20,
                "searchText": term,
            }
            r = requests.post(
                api,
                json=body,
                timeout=TIMEOUT,
                headers={**HEADERS, "Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
            postings = data.get("jobPostings", [])
            for j in postings:
                path = j.get("externalPath", "")
                if path in seen:
                    continue
                seen.add(path)
                out.append(
                    {
                        "id": path,
                        "title": j.get("title", ""),
                        "location": j.get("locationsText", ""),
                        "url": f"{base}/en-US/{site}{path}",
                        "description": " ".join(j.get("bulletFields") or []),
                    }
                )
            if len(postings) < 20:
                break
    return out


def amazon(c):
    """amazon.jobs exposes a public search endpoint."""
    out, seen = [], set()
    for term in c.get("searches") or ["product manager intern", "product management"]:
        data = _get(
            "https://www.amazon.jobs/en/search.json",
            params={
                "base_query": term,
                "result_limit": 100,
                "sort": "recent",
                "country": "USA",
            },
        ).json()
        for j in data.get("jobs", []):
            jid = str(j.get("id_icims") or j.get("id"))
            if jid in seen:
                continue
            seen.add(jid)
            out.append(
                {
                    "id": jid,
                    "title": j.get("title", ""),
                    "location": j.get("normalized_location", "") or j.get("location", ""),
                    "url": urljoin("https://www.amazon.jobs", j.get("job_path", "")),
                    "description": j.get("description_short", "") or "",
                }
            )
    return out


LINK_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def generic(c):
    """Last resort: pull every link off a careers page and treat text as titles.

    Only works on server-rendered pages. If a company's board is JavaScript-only
    this returns nothing -- use a real ATS adapter instead.
    """
    url = c["url"]
    resp = requests.get(
        url, headers={**HEADERS, "Accept": "text/html,*/*"}, timeout=TIMEOUT
    )
    resp.raise_for_status()
    out, seen = [], set()
    for href, inner in LINK_RE.findall(resp.text):
        title = _strip_html(inner)
        if not title or len(title) > 160 or len(title) < 6:
            continue
        link = urljoin(url, href)
        if link in seen:
            continue
        seen.add(link)
        out.append(
            {"id": link, "title": title, "location": "", "url": link, "description": ""}
        )
    return out


GOOGLE_LINK_RE = re.compile(r'href="(jobs/results/(\d+)-([a-z0-9-]+))[^"]*"')
H3_RE = re.compile(r"<h3[^>]*>([^<]{5,120})</h3>")


def google(c):
    """Google's careers results page is server-rendered, so it can be read.

    Titles sit in an <h3> just before each job link. Google rotates its CSS
    class names, so rather than matching a class we take the nearest heading
    *before* each link and fall back to the URL slug if that ever stops
    working.
    """
    base = "https://www.google.com/about/careers/applications/jobs/results/"
    searches = c.get("searches") or ["product"]
    out, seen = [], set()
    for term in searches:
        for page in range(1, 4):
            params = {"q": term, "employment_type": "INTERN", "page": page}
            resp = requests.get(
                base, params=params, headers={**HEADERS, "Accept": "text/html,*/*"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.text
            headings = [(m.start(), m.group(1)) for m in H3_RE.finditer(body)]
            links = list(GOOGLE_LINK_RE.finditer(body))
            for m in links:
                path, jid, slug = m.group(1), m.group(2), m.group(3)
                if jid in seen:
                    continue
                seen.add(jid)
                prior = [t for pos, t in headings if pos < m.start()]
                title = (
                    prior[-1].strip()
                    if prior
                    else slug.replace("-", " ").title()
                )
                out.append(
                    {
                        "id": jid,
                        "title": html.unescape(title),
                        "location": "",
                        "url": urljoin(base, path),
                        "description": "",
                    }
                )
            if not links:
                break
    return out


LI_CARD_RE = re.compile(
    r'data-entity-urn="urn:li:jobPosting:(\d+)".*?'
    r'base-card__full-link[^>]*href="([^"]+)".*?'
    r'base-search-card__title">\s*([^<]+?)\s*</h3>',
    re.S,
)


def linkedin(c):
    """Best-effort net for companies with no open job feed of their own.

    Microsoft, Meta, Intuit, LinkedIn and Uber don't publish a public job
    API, but they do syndicate to LinkedIn, whose guest search needs no
    login. Results are filtered by the company slug in each job URL
    (".../product-manager-at-microsoft-123"), which turned out to be more
    reliable than LinkedIn's numeric company ids.

    Caveat worth knowing: this is keyword-driven and returns ~10 results per
    query, so it is a good net rather than a complete listing the way a real
    ATS feed is. LinkedIn also rate-limits aggressively -- a refusal surfaces
    as a SourceError so the rest of the run carries on.
    """
    api = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    slug = c["company_slug"]
    label = c.get("search_name", c["name"])
    terms = c.get("searches") or [
        f"product manager intern {label}",
        f"product management intern {label}",
        f"product design intern {label}",
    ]
    out, seen = [], set()
    for term in terms:
        params = {"keywords": term, "start": 0}
        if c.get("company_id"):
            params["f_C"] = c["company_id"]
        r = requests.get(
            api, params=params, headers={**HEADERS, "Accept": "text/html,*/*"},
            timeout=TIMEOUT,
        )
        if r.status_code in (403, 429, 999):
            raise SourceError(
                f"LinkedIn refused the request (HTTP {r.status_code}) -- "
                "it rate-limits automated traffic"
            )
        r.raise_for_status()
        for jid, url, title in LI_CARD_RE.findall(r.text):
            if jid in seen or f"-at-{slug}-" not in url:
                continue
            seen.add(jid)
            out.append(
                {
                    "id": jid,
                    "title": html.unescape(title.strip()),
                    "location": "",
                    "url": url.split("?")[0],
                    "description": "",
                }
            )
    return out


ADAPTERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "smartrecruiters": smartrecruiters,
    "workable": workable,
    "workday": workday,
    "amazon": amazon,
    "google": google,
    "linkedin": linkedin,
    "generic": generic,
}


def fetch(company):
    """Fetch all postings for one company entry from companies.yml."""
    ats = (company.get("ats") or "").lower()
    adapter = ADAPTERS.get(ats)
    if adapter is None:
        raise SourceError(
            f"unknown ats {ats!r} -- pick one of {', '.join(sorted(ADAPTERS))}"
        )
    try:
        jobs = adapter(company)
    except requests.HTTPError as e:
        raise SourceError(f"HTTP {e.response.status_code} from {ats}") from e
    except requests.RequestException as e:
        raise SourceError(f"network error: {e}") from e
    except (ValueError, KeyError) as e:
        raise SourceError(f"unexpected response shape: {e}") from e
    return [j for j in jobs if j.get("title") and j.get("url")]


def board_url(company):
    """The company's public careers page -- the human-facing board.

    Used as the "browse all openings" link in alerts. A company can override
    it with `careers_url:` in companies.yml (e.g. to point at their own
    branded page instead of the ATS-hosted one).
    """
    if company.get("careers_url"):
        return company["careers_url"]
    ats, token = company.get("ats"), company.get("token", "")
    if ats == "greenhouse":
        return f"https://job-boards.greenhouse.io/{token}"
    if ats == "lever":
        return f"https://jobs.lever.co/{token}"
    if ats == "ashby":
        return f"https://jobs.ashbyhq.com/{token}"
    if ats == "smartrecruiters":
        return f"https://jobs.smartrecruiters.com/{token}"
    if ats == "workable":
        return f"https://apply.workable.com/{token}"
    if ats == "workday":
        host, site = company.get("host", "wd1"), company.get("site", "")
        return f"https://{token}.{host}.myworkdayjobs.com/en-US/{site}"
    if ats == "amazon":
        return "https://www.amazon.jobs/en/search?base_query=product+manager+intern"
    if ats == "google":
        return (
            "https://www.google.com/about/careers/applications/jobs/results/"
            "?employment_type=INTERN&q=product"
        )
    if ats == "linkedin":
        return f"https://www.linkedin.com/company/{company['company_slug']}/jobs/"
    return company.get("url", "")
