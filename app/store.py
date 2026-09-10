"""Remembers which postings you've already been told about.

A tiny SQLite file. On Railway this lives on a mounted volume so it survives
redeploys -- otherwise every deploy would re-alert you on every open job.
"""

import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerted (
    key        TEXT PRIMARY KEY,
    company    TEXT NOT NULL,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    alerted_at REAL NOT NULL
);
"""


class Store:
    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "alerted.db")
        self.db = sqlite3.connect(self.path)
        self.db.execute(SCHEMA)
        self.db.commit()

    @staticmethod
    def key(company, job):
        return f"{company}|{job['id']}"

    def is_new(self, company, job):
        cur = self.db.execute(
            "SELECT 1 FROM alerted WHERE key = ?", (self.key(company, job),)
        )
        return cur.fetchone() is None

    def mark(self, company, job):
        self.db.execute(
            "INSERT OR IGNORE INTO alerted (key, company, title, url, alerted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.key(company, job), company, job["title"], job["url"], time.time()),
        )

    def commit(self):
        self.db.commit()

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM alerted").fetchone()[0]
