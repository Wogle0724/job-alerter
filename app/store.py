"""Remembers which postings you've already been told about.

A plain JSON file that gets committed back to the repo after each run. There's
no server and no disk to persist to on GitHub Actions, so the repo itself is
the database -- which has the nice side effect that the alert history is
readable and diffable right in GitHub.
"""

import json
import os
import time


class Store:
    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "alerted.json")
        self.entries = {}
        if os.path.exists(self.path):
            try:
                with open(self.path) as fh:
                    self.entries = json.load(fh).get("alerted", {})
            except (json.JSONDecodeError, OSError):
                # A corrupt file must not cause a re-alert storm, but it also
                # must not wedge the job -- start clean and rewrite it.
                self.entries = {}
        self._dirty = False

    @staticmethod
    def key(company, job):
        return f"{company}|{job['id']}"

    def is_new(self, company, job):
        return self.key(company, job) not in self.entries

    def mark(self, company, job):
        self.entries[self.key(company, job)] = {
            "company": company,
            "title": job["title"],
            "url": job["url"],
            "alerted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._dirty = True

    def commit(self):
        if not self._dirty:
            return False
        payload = {
            "alerted": dict(sorted(self.entries.items())),  # stable git diffs
            "count": len(self.entries),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, self.path)
        self._dirty = False
        return True

    def count(self):
        return len(self.entries)
