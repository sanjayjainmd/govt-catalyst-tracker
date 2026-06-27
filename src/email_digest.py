"""Build and send the daily digest email via Gmail SMTP.

Credentials come from environment variables (GitHub Secrets in CI):
  MAIL_USERNAME      your gmail address
  MAIL_APP_PASSWORD  a Google app password (NOT your normal password)
  MAIL_TO            where to send (defaults to MAIL_USERNAME)

If creds are missing (e.g. local dry run), it prints the digest instead of sending.
"""
import os
import smtplib
from email.mime.text import MIMEText

_TIER_LABEL = {1: "T1 offtake/floor", 2: "T2 production credit",
               3: "T3 loan", 4: "T4 grant", 5: "T5 R&D"}


def _row_html(r):
    tier = _TIER_LABEL.get(r.get("quality_tier"), "T?")
    mat = r.get("materiality_ratio")
    mat_s = f"{mat * 100:.0f}% of cap" if mat else "n/a"
    amt = r.get("amount")
    amt_s = f"${amt / 1e6:,.0f}M" if amt else "—"
    color = "#a32d2d" if r["decision"] == "immediate" else "#854f0b"
    return f"""
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:8px;font-weight:600;">{r.get('ticker') or '—'}</td>
      <td style="padding:8px;">
        <a href="{r.get('url')}" style="color:#185fa5;text-decoration:none;">{r.get('title') or ''}</a><br>
        <span style="color:#666;font-size:12px;">{tier} &middot; stage {r.get('stage')} &middot; {mat_s} &middot; {amt_s}</span>
      </td>
      <td style="padding:8px;text-align:right;font-weight:600;color:{color};">{r.get('score')}</td>
      <td style="padding:8px;font-size:12px;color:#666;">{r['decision']}</td>
    </tr>"""


def build_html(rows, dash_url=None):
    rows_sorted = sorted(rows, key=lambda r: r.get("score", 0), reverse=True)
    body = "".join(_row_html(r) for r in rows_sorted)
    link = f'<p><a href="{dash_url}">Open dashboard</a></p>' if dash_url else ""
    return f"""<html><body style="font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;">
    <h2 style="font-weight:500;">Government catalyst digest</h2>
    <p style="color:#666;">{len(rows_sorted)} new/updated catalyst(s) above threshold.</p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <thead><tr style="text-align:left;border-bottom:2px solid #ddd;">
        <th style="padding:8px;">Ticker</th><th style="padding:8px;">Event</th>
        <th style="padding:8px;text-align:right;">Score</th><th style="padding:8px;">Route</th>
      </tr></thead><tbody>{body}</tbody></table>
    {link}
    <p style="color:#999;font-size:12px;margin-top:24px;">
      Descriptive triage, not a predictive signal or trade recommendation.</p>
    </body></html>"""


def send(rows, subject_prefix="[Catalyst]", dash_url=None):
    if not rows:
        print("email: no qualifying catalysts, nothing to send.")
        return False

    user = os.environ.get("MAIL_USERNAME")
    pw = os.environ.get("MAIL_APP_PASSWORD")
    to = os.environ.get("MAIL_TO") or user
    html = build_html(rows, dash_url)

    if not (user and pw and to):
        print("email: MAIL_* env vars not set — printing digest instead:\n")
        print(html)
        return False

    immediate = sum(1 for r in rows if r["decision"] == "immediate")
    subject = f"{subject_prefix} {len(rows)} catalysts" + (f", {immediate} urgent" if immediate else "")
    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, pw)
        server.sendmail(user, [to], msg.as_string())
    print(f"email: sent '{subject}' to {to}")
    return True
