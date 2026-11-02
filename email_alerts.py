"""
Job-alert emails — jobs from Naukri and iimjobs, read from the applicant's Gmail.

Naukri and iimjobs block scripts on their sites, but both email jobs to their
users: recruiter "Job | <title> in <company>" mails, saved-search alerts and
digests. This reads those emails over IMAP with the Gmail app password, in
read-only mode (BODY.PEEK — nothing is marked read, moved or deleted), and
turns each job into the same dict the scrapers produce. Recruiter mails carry
the full job description, which is passed on so Gemini can score it without
visiting Naukri.
"""

import email
import html
import imaplib
import re
from email.header import decode_header, make_header

LOOKBACK_DAYS = 4
MAX_MESSAGES  = 150

SENDER_QUERY = "from:(naukri.com OR iimjobs.com) -from:minis.naukri.com"
# Account / marketing mails from these senders that carry no job
NOT_JOB_SUBJECT = re.compile(
    r'noticing your profile|you applied|profile (view|update)|verify|password|'
    r'otp|lpa works out|gratuity|resume|newsletter|webinar|course|premium|'
    r'subscription|payment|invoice', re.IGNORECASE)

# Job links in alert / digest emails
_JOB_LINK = re.compile(
    r'href="?(https?://(?:www\.)?(?:naukri\.com/job-listings-[^"\s>]+|'
    r'iimjobs\.com/j/[^"\s>]+|hirist\.(?:com|tech)/j/[^"\s>]+))"?[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL)
_APPLY_LINK = re.compile(
    r'href="?(https?://my\.naukri\.com/[^"\s>]*applyBroadcastMail[^"\s>]*)', re.IGNORECASE)
_SALARY = re.compile(r'₹\s*([\d.]+)\s*-\s*([\d.]+)\s*LPA', re.IGNORECASE)


def _text(raw_html):
    t = re.sub(r'(?s)<(style|script|title|head).*?</\1>', ' ', raw_html or "")
    t = re.sub(r'<[^>]+>', ' | ', t)
    t = re.sub(r'\s+', ' ', html.unescape(t))
    return re.sub(r'(\|\s*)+', '| ', t).strip()


def _html_part(msg):
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", "replace")
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            return html.escape(payload.decode(part.get_content_charset() or "utf-8", "replace"))
    return ""


def _salary_note(text):
    m = _SALARY.search(text or "")
    return (f"₹{m.group(1)}–{m.group(2)} LPA", float(m.group(2))) if m else ("", None)


def parse_recruiter_mail(subject, raw_html):
    """Naukri 'Job | <title> in <company/location>' mail sent by a recruiter."""
    text = _text(raw_html)
    m = re.search(r"invited to apply to this job \| (.+?) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|", text)
    am = _APPLY_LINK.search(raw_html or "")
    if not m or not am:
        return None
    company, title, location, exp, salary = (s.strip() for s in m.groups())
    jd = text[text.find("Job description"):] if "Job description" in text else text
    note, top = _salary_note(salary)
    return {
        "title":       title[:160],
        "org":         company[:120],
        "location":    location + (f" · {note}" if note else ""),
        "url":         html.unescape(am.group(1)),
        "updated":     "",
        "source":      "Naukri",
        "description": f"Experience: {exp}. Salary: {salary}.\n{jd}"[:6000],
        "max_lpa":     top,
    }


def parse_alert_mail(raw_html, source):
    """Saved-search alerts and digests: one entry per job link."""
    jobs = []
    for m in _JOB_LINK.finditer(raw_html or ""):
        url, anchor = m.group(1), _text(m.group(2)).strip("| ")
        if len(anchor) < 6 or anchor.lower() in {"apply", "apply now", "view job", "view details"}:
            continue
        around = _text(raw_html[m.end():m.end() + 1500])[:400]
        note, top = _salary_note(around)
        loc = next((p.strip() for p in around.split("|")
                    if re.search(r'bengaluru|bangalore|hyderabad|chennai|kochi|mumbai|delhi|'
                                 r'gurgaon|gurugram|noida|pune|remote|india|kolkata', p, re.I)), "")
        jobs.append({
            "title":       anchor[:160],
            "org":         (around.split("|")[0].strip() or source)[:120],
            "location":    (loc or "India") + (f" · {note}" if note else ""),
            "url":         url.split("?")[0],
            "updated":     "",
            "source":      source,
            "description": around,
            "max_lpa":     top,
        })
    return jobs


def fetch_email_jobs(address, app_password, min_lpa=12):
    """Jobs from recent Naukri / iimjobs emails. Never raises."""
    if not address or not app_password:
        print("\n[Email alerts] skipped — no Gmail address or app password.")
        return []
    print(f"\n[Email alerts] Reading Naukri / iimjobs mails from the last {LOOKBACK_DAYS} days...")
    jobs, seen = [], set()
    try:
        box = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        box.login(address, app_password.replace(" ", ""))
        box.select('"[Gmail]/All Mail"', readonly=True)
        query = f'{SENDER_QUERY} newer_than:{LOOKBACK_DAYS}d'
        typ, data = box.search(None, "X-GM-RAW", f'"{query}"')
        ids = (data[0] or b"").split()[-MAX_MESSAGES:]
        for mid in ids:
            typ, parts = box.fetch(mid, "(BODY.PEEK[])")
            if typ != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            msg = email.message_from_bytes(parts[0][1])
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            sender  = msg.get("From", "").lower()
            if NOT_JOB_SUBJECT.search(subject):
                continue
            raw = _html_part(msg)
            source = "iimjobs" if "iimjobs" in sender else "Naukri"
            found = []
            if "Job |" in subject or "applyBroadcastMail" in raw:
                job = parse_recruiter_mail(subject, raw)
                found = [job] if job else []
            if not found:
                found = parse_alert_mail(raw, source)
            for job in found:
                if job["url"] in seen:
                    continue
                if job.get("max_lpa") is not None and job["max_lpa"] < min_lpa:
                    continue                      # stated pay tops out below the goal
                seen.add(job["url"])
                jobs.append(job)
        box.logout()
    except Exception as e:
        print(f"[Email alerts] Error: {type(e).__name__}: {e}")
    print(f"[Email alerts] {len(jobs)} jobs from email.")
    return jobs
