"""Loads companies.yml, rules.yml, and environment settings."""

import os
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    pass


def _load_yaml(name):
    path = ROOT / name
    if not path.exists():
        raise ConfigError(f"{name} is missing from the repo root")
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


REQUIRED_FIELDS = {
    "greenhouse": ["token"],
    "lever": ["token"],
    "ashby": ["token"],
    "smartrecruiters": ["token"],
    "workable": ["token"],
    "workday": ["token", "site"],
    "amazon": [],
    "generic": ["url"],
}


def load_companies():
    data = _load_yaml("companies.yml")
    companies = data.get("companies") or []
    if not companies:
        raise ConfigError("companies.yml has no companies listed")

    cleaned = []
    for i, c in enumerate(companies, 1):
        if not isinstance(c, dict) or not c.get("name"):
            raise ConfigError(f"company #{i} in companies.yml is missing a name")
        ats = (c.get("ats") or "").lower()
        if ats not in REQUIRED_FIELDS:
            raise ConfigError(
                f"{c['name']}: ats {ats!r} is not supported "
                f"(use one of {', '.join(sorted(REQUIRED_FIELDS))})"
            )
        missing = [f for f in REQUIRED_FIELDS[ats] if not c.get(f)]
        if missing:
            raise ConfigError(
                f"{c['name']}: ats '{ats}' needs {', '.join(missing)} in companies.yml"
            )
        c["ats"] = ats
        cleaned.append(c)
    return cleaned


def load_rules():
    return _load_yaml("rules.yml")


class Settings:
    def __init__(self):
        self.resend_key = os.environ.get("RESEND_API_KEY", "").strip()
        self.email_to = os.environ.get("ALERT_EMAIL_TO", "").strip()
        self.email_from = os.environ.get(
            "ALERT_EMAIL_FROM", "Job Alerter <onboarding@resend.dev>"
        ).strip()
        self.interval_minutes = float(os.environ.get("POLL_INTERVAL_MINUTES", "20"))
        self.data_dir = os.environ.get("DATA_DIR", str(ROOT / "data"))
