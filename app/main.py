"""Poll every company's job board on a loop and email new PM-internship hits.

Run modes:
    python -m app.main              # run forever (this is what Railway runs)
    python -m app.main --once       # one cycle, then exit
    python -m app.main --dry-run    # find hits, print them, send nothing,
                                    # and don't mark anything as alerted
"""

import argparse
import logging
import sys
import time

from . import notify, sources
from .config import ConfigError, Settings, load_companies, load_rules
from .matcher import Matcher
from .store import Store

log = logging.getLogger("job-alerter")


def scan(companies, matcher, store, dry_run=False):
    """Check every company once. Returns (new hits, per-company failures)."""
    hits, failures = [], []
    for c in companies:
        name = c["name"]
        try:
            jobs = sources.fetch(c)
        except sources.SourceError as e:
            log.warning("%s: %s", name, e)
            failures.append((name, str(e)))
            continue
        except Exception as e:  # a bad board must never kill the loop
            log.warning("%s: unexpected error: %s", name, e)
            failures.append((name, f"unexpected error: {e}"))
            continue

        matched = 0
        for job in jobs:
            verdict = matcher.evaluate(job)
            if not verdict["matched"]:
                continue
            matched += 1
            if not dry_run and not store.is_new(name, job):
                continue
            hits.append(
                {
                    "company": name,
                    "job": job,
                    "verdict": verdict,
                    "careers_url": sources.board_url(c),
                }
            )
        log.info("%-24s %4d postings, %d match", name, len(jobs), matched)
    return hits, failures


def cycle(settings, companies, matcher, store, dry_run=False):
    started = time.time()
    hits, failures = scan(companies, matcher, store, dry_run)
    took = time.time() - started

    if not hits:
        log.info(
            "no new matches (%d companies in %.0fs, %d already alerted)",
            len(companies),
            took,
            store.count(),
        )
        return 0

    log.info("%d NEW match(es) in %.0fs", len(hits), took)
    for h in hits:
        log.info(
            "  [%s] %s — %s  %s",
            h["verdict"]["label"],
            h["company"],
            h["job"]["title"],
            h["job"]["url"],
        )

    if dry_run:
        log.info("dry run: no email sent, nothing marked as alerted")
        return len(hits)

    try:
        msg_id = notify.send_digest(settings, hits, failures, matcher.target_year)
    except notify.NotifyError as e:
        # Leave them unmarked so the next cycle retries instead of losing them.
        log.error("email failed (%s) -- will retry these next cycle", e)
        return 0

    for h in hits:
        store.mark(h["company"], h["job"])
    store.commit()
    log.info("emailed %s (resend id %s)", settings.email_to, msg_id)
    return len(hits)


def main(argv=None):
    ap = argparse.ArgumentParser(description="PM internship job alerter")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would alert without emailing or recording it",
    )
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    try:
        settings = Settings()
        companies = load_companies()
        matcher = Matcher(load_rules())
    except ConfigError as e:
        log.error("config problem: %s", e)
        return 2

    store = Store(settings.data_dir)
    log.info(
        "watching %d companies, target %s, every %g min, db=%s",
        len(companies),
        matcher.target_year,
        settings.interval_minutes,
        store.path,
    )
    if not settings.resend_key and not args.dry_run:
        log.warning("RESEND_API_KEY is not set -- matches will be logged, not emailed")

    if args.once or args.dry_run:
        cycle(settings, companies, matcher, store, args.dry_run)
        return 0

    while True:
        try:
            cycle(settings, companies, matcher, store)
        except Exception:
            log.exception("cycle failed -- continuing")
        time.sleep(settings.interval_minutes * 60)


if __name__ == "__main__":
    sys.exit(main())
