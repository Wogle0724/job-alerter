"""Sends the alert email through Resend.

One digest per polling cycle rather than one email per posting, so adding a
big batch of companies at once doesn't flood your inbox.
"""

import html
import logging

import requests

log = logging.getLogger(__name__)

API = "https://api.resend.com/emails"
TIMEOUT = 20

BADGE = {"High": "#0a7d33", "Medium": "#8a6100", "Low": "#666666"}


class NotifyError(Exception):
    pass


def _subject(hits):
    if len(hits) == 1:
        h = hits[0]
        return f"PM intern posting: {h['company']} — {h['job']['title']}"
    companies = sorted({h["company"] for h in hits})
    shown = ", ".join(companies[:3])
    more = f" +{len(companies) - 3} more" if len(companies) > 3 else ""
    return f"{len(hits)} new PM intern postings — {shown}{more}"


def _render_html(hits, failures):
    rows = []
    for h in hits:
        job, v = h["job"], h["verdict"]
        color = BADGE.get(v["label"], "#666")
        loc = html.escape(job.get("location") or "Location not listed")
        rows.append(
            f"""
    <tr><td style="padding:18px 0;border-bottom:1px solid #e6e6e6;">
      <div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#666;">
        {html.escape(h['company'])}
      </div>
      <div style="margin:4px 0 6px;font-size:17px;font-weight:600;line-height:1.3;">
        <a href="{html.escape(job['url'])}" style="color:#111;text-decoration:none;">
          {html.escape(job['title'])}</a>
      </div>
      <div style="font-size:13px;color:#555;">{loc}</div>
      <div style="margin-top:10px;font-size:12px;color:#555;">
        <span style="display:inline-block;padding:2px 8px;border-radius:10px;
              background:{color}1a;color:{color};font-weight:600;">
          {v['label']} confidence</span>
        &nbsp;{html.escape(' · '.join(v['reasons']))}
      </div>
      <div style="margin-top:12px;">
        <a href="{html.escape(job['url'])}"
           style="display:inline-block;padding:8px 14px;background:#111;color:#fff;
                  border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;">
          View posting</a>
        <a href="{html.escape(h.get('careers_url') or job['url'])}"
           style="display:inline-block;margin-left:8px;padding:8px 14px;border:1px solid #ccc;
                  color:#333;border-radius:6px;text-decoration:none;font-size:13px;">
          All {html.escape(h['company'])} openings</a>
      </div>
    </td></tr>"""
        )

    warn = ""
    if failures:
        items = "".join(
            f"<li>{html.escape(name)} — {html.escape(err)}</li>" for name, err in failures
        )
        warn = (
            '<div style="margin-top:24px;padding:12px 14px;background:#fff8e1;'
            'border-radius:6px;font-size:12px;color:#6b5200;">'
            f"<strong>Couldn't check {len(failures)} board(s) this round:</strong>"
            f'<ul style="margin:6px 0 0 16px;padding:0;">{items}</ul></div>'
        )

    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
     Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#111;">
  <div style="font-size:20px;font-weight:700;">
    {len(hits)} new posting{'s' if len(hits) != 1 else ''} matched
  </div>
  <div style="font-size:13px;color:#666;margin-top:4px;">
    Summer 2027 product management — found by your job alerter.
  </div>
  <table style="width:100%;border-collapse:collapse;margin-top:8px;">{''.join(rows)}</table>
  {warn}
  <div style="margin-top:24px;font-size:11px;color:#999;">
    You get one alert per posting. Tune the keyword rules in rules.yml,
    add companies in companies.yml.
  </div>
</div>"""


def _render_text(hits):
    lines = []
    for h in hits:
        job, v = h["job"], h["verdict"]
        lines.append(
            f"{h['company']} — {job['title']}\n"
            f"  {job.get('location') or 'Location not listed'}\n"
            f"  {v['label']} confidence: {'; '.join(v['reasons'])}\n"
            f"  Posting:      {job['url']}\n"
            f"  Careers page: {h.get('careers_url') or job['url']}\n"
        )
    return "\n".join(lines)


def send_digest(settings, hits, failures=()):
    """Send one email covering every new hit. Raises NotifyError on failure."""
    if not settings.resend_key:
        raise NotifyError("RESEND_API_KEY is not set")
    if not settings.email_to:
        raise NotifyError("ALERT_EMAIL_TO is not set")

    payload = {
        "from": settings.email_from,
        "to": [settings.email_to],
        "subject": _subject(hits),
        "html": _render_html(hits, list(failures)),
        "text": _render_text(hits),
    }
    r = requests.post(
        API,
        json=payload,
        headers={"Authorization": f"Bearer {settings.resend_key}"},
        timeout=TIMEOUT,
    )
    if r.status_code >= 300:
        raise NotifyError(f"Resend returned {r.status_code}: {r.text[:300]}")
    return r.json().get("id", "")
