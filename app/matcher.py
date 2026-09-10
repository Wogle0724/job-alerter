"""Decide whether a posting is a Summer 2027 PM internship.

Pure keyword rules driven by rules.yml -- no model calls, nothing hidden.
Every decision comes back with the reasons behind it so the email can show
its work and you can tune the word lists when something slips through.
"""

import re

# Titles that carry the strongest signal. A hit on one of these is what
# separates "high confidence" from "worth a look".
CORE_TERMS = {
    "product manager",
    "product management",
    "product management intern",
    "product intern",
    "associate product manager",
    "apm",
    "pm intern",
    "product owner",
    "product mgmt",
}

YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _term_re(term):
    """Whole-word regex for a term, tolerant of extra spacing."""
    parts = [re.escape(p) for p in term.strip().split()]
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.I)


class Matcher:
    def __init__(self, rules):
        self.target_year = str(rules.get("target_year", 2027))
        self.product = [(t, _term_re(t)) for t in rules.get("product_terms", [])]
        self.intern = [(t, _term_re(t)) for t in rules.get("intern_terms", [])]
        self.exclude = [(t, _term_re(t)) for t in rules.get("exclude_terms", [])]
        seasons = rules.get("season_words", [])
        self.season_year_re = (
            re.compile(
                r"\b(?:" + "|".join(re.escape(s) for s in seasons) + r")\s+(20\d{2})\b",
                re.I,
            )
            if seasons
            else None
        )

    @staticmethod
    def _first_hit(pairs, text):
        for term, rx in pairs:
            if rx.search(text):
                return term
        return None

    def evaluate(self, job):
        """Return a verdict dict for one posting."""
        title = job.get("title", "")
        desc = (job.get("description") or "")[:4000]

        blocked = self._first_hit(self.exclude, title)
        if blocked:
            return {"matched": False, "why": f"excluded term {blocked!r} in title"}

        product = self._first_hit(self.product, title)
        if not product:
            return {"matched": False, "why": "no product-management term in title"}

        intern = self._first_hit(self.intern, title)
        if not intern:
            return {"matched": False, "why": "no internship term in title"}

        # Year check. An explicit wrong year in the title is disqualifying.
        title_years = set(YEAR_RE.findall(title))
        if title_years and self.target_year not in title_years:
            return {
                "matched": False,
                "why": f"title names {', '.join(sorted(title_years))}, not {self.target_year}",
            }

        # A season-anchored year ("Summer 2026") anywhere is also disqualifying.
        season_years = set()
        if self.season_year_re:
            season_years = set(self.season_year_re.findall(title)) | set(
                self.season_year_re.findall(desc)
            )
        if season_years and self.target_year not in season_years:
            return {
                "matched": False,
                "why": f"posting is for {', '.join(sorted(season_years))}",
            }

        # Confidence.
        reasons = [f"title matches {product!r} + {intern!r}"]
        score = 0.60
        if product in CORE_TERMS:
            score += 0.20
            reasons.append("core product-management title")
        else:
            reasons.append("adjacent product role")
        if self.target_year in title_years or self.target_year in season_years:
            score += 0.20
            reasons.append(f"explicitly {self.target_year}")
        elif not title_years and not season_years:
            score += 0.05
            reasons.append("no year stated (most postings omit it)")

        score = min(score, 1.0)
        label = "High" if score >= 0.80 else "Medium" if score >= 0.65 else "Low"
        return {
            "matched": True,
            "confidence": round(score, 2),
            "label": label,
            "reasons": reasons,
        }
