"""
Job-alert emails — jobs from Naukri, iimjobs and LinkedIn, read from the applicant's Gmail.

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
import time
import urllib.request
from email.header import decode_header, make_header

LOOKBACK_DAYS = 4
MAX_MESSAGES  = 150

SENDER_QUERY = ("from:(naukri.com OR iimjobs.com OR jobalerts-noreply@linkedin.com OR "
                "jobs-noreply@linkedin.com OR jobs-listings@linkedin.com) -from:minis.naukri.com")
MAX_LINKEDIN_JOBS = 40       # LinkedIn job pages fetched per run (one guest request each)
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
# iimjobs wraps every link in a cm.iimjobs.com tracking redirect carrying the job id
_IIM_JOBID = re.compile(r'jobId(?:%3D|=)(\d+)', re.IGNORECASE)
# LinkedIn alert mails link every job as linkedin.com/comm/jobs/view/<id>
_LI_JOBID = re.compile(r'linkedin\.com/(?:comm/)?jobs/view/(\d{6,})', re.IGNORECASE)
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
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


def parse_iimjobs_mail(subject, raw_html):
    """iimjobs recommendation mails: one job card per job id (single-job mails also carry the JD)."""
    raw = raw_html or ""
    jobs, seen = [], set()
    for m in _IIM_JOBID.finditer(raw):
        jid = m.group(1)
        if jid in seen:
            continue
        seen.add(jid)
        # Card text after the first link to this job: title, organisation, location, experience
        start = raw.find(">", m.end()) + 1          # end of the opening <a ...> tag
        card = _text(raw[start:start + 3000])
        parts = [p.strip() for p in card.split("|") if p.strip() and p.strip().lower() != "apply now"]
        title = parts[0] if parts else ""
        org = parts[1] if len(parts) > 1 else ""
        loc = re.search(r'Location:\s*\|?\s*([^|]+)', card)
        exp = re.search(r'Experience:\s*\|?\s*([^|]+)', card)
        if len(title) < 4 or len(title) > 160:
            continue
        jd = ""
        if len(seen) == 1 and "<!-- Job Description -->" in raw:
            block = raw.split("<!-- Job Description -->", 1)[1].split("<!--", 1)[0]
            jd = _text(block).replace("| ", "\n")
        note, top = _salary_note(card)
        jobs.append({
            "title":       title,
            "org":         org[:120] or "iimjobs",
            "location":    (loc.group(1).strip() if loc else "India") + (f" · {note}" if note else ""),
            "url":         f"https://www.iimjobs.com/one-click-apply?jobId={jid}",
            "updated":     "",
            "source":      "iimjobs",
            "description": (f"Experience: {exp.group(1).strip()}.\n" if exp else "") + jd[:5500],
            "max_lpa":     top,
        })
    return jobs


def _li_field(page, cls):
    m = re.search(r'class="[^"]*\b' + cls + r'\b[^"]*"[^>]*>(.*?)</(?:h1|h2|h3|a|span|div)>', page, re.DOTALL)
    return _text(m.group(1)).strip("| ") if m else ""


def parse_linkedin_mail(raw_html, budget):
    """LinkedIn job-alert mails: job ids from the links, details from LinkedIn's public job page."""
    jobs, seen = [], set()
    for m in _LI_JOBID.finditer(raw_html or ""):
        jid = m.group(1)
        if jid in seen or len(jobs) >= budget:
            continue
        seen.add(jid)
        try:
            req = urllib.request.Request(
                f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}", headers=_UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                page = r.read().decode("utf-8", "replace")
        except Exception:
            continue                                  # removed or rate-limited; skip this one
        time.sleep(1.0)
        title = _li_field(page, "top-card-layout__title") or _li_field(page, "topcard__title")
        if not title:
            continue
        desc = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.DOTALL)
        jd = _text(desc.group(1)).replace("| ", "\n") if desc else ""
        note, top = _salary_note(page)
        jobs.append({
            "title":       title[:160],
            "org":         (_li_field(page, "topcard__org-name-link") or "LinkedIn")[:120],
            "location":    (_li_field(page, "topcard__flavor--bullet") or "India") + (f" · {note}" if note else ""),
            "url":         f"https://www.linkedin.com/jobs/view/{jid}/",
            "updated":     "",
            "source":      "LinkedIn alert email",
            "description": jd[:6000],
            "max_lpa":     top,
        })
    return jobs


def fetch_email_jobs(address, app_password, min_lpa=12):
    """Jobs from recent Naukri / iimjobs / LinkedIn alert emails. Never raises."""
    if not address or not app_password:
        print("\n[Email alerts] skipped — no Gmail address or app password.")
        return []
    print(f"\n[Email alerts] Reading Naukri / iimjobs / LinkedIn mails from the last {LOOKBACK_DAYS} days...")
    jobs, seen, li_count = [], set(), 0
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
            source = ("iimjobs" if "iimjobs" in sender else
                      "LinkedIn alert email" if "linkedin" in sender else "Naukri")
            found = []
            if source == "LinkedIn alert email":
                found = parse_linkedin_mail(raw, MAX_LINKEDIN_JOBS - li_count)
                li_count += len(found)
                if not found:
                    continue                      # never fall back to the Naukri link parser
            elif source == "iimjobs":
                found = parse_iimjobs_mail(subject, raw)
            elif "Job |" in subject or "applyBroadcastMail" in raw:
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
                job["from_email"] = True          # chosen by the job site for this profile
                jobs.append(job)
        box.logout()
    except Exception as e:
        print(f"[Email alerts] Error: {type(e).__name__}: {e}")
    print(f"[Email alerts] {len(jobs)} jobs from email.")
    return jobs
