"""
Auto-apply — sends applications for strong South-India matches, by email only.

Runs after each alert run on GitHub Actions. For every new match that is in
South India (Bangalore first) or remote, scored 6+/10 by Gemini and not a junior post:

  * If the posting or notice names an application email address, Gemini writes
    a tailored cover email from cv_profile.txt and it is sent from the applicant's
    Gmail with the CV attached and a BCC to the applicant.
  * Otherwise (LinkedIn Easy Apply, company portals, government online forms)
    a ready-to-paste kit — cover letter, standard answers, link — goes to
    Telegram, so applying takes a couple of minutes.

LinkedIn itself is never logged into: automated Easy Apply breaks LinkedIn's
terms and gets accounts restricted.

Sending needs the GMAIL_APP_PASSWORD secret (a Google App Password). Without
it the bot only sends kits. Every application is logged in applied_jobs.json,
and nothing is sent twice to the same organisation for the same role.
"""

import io
import json
import os
import re
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_private_text(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


def configure(data_dir):
    """Point at the private data folder and load the applicant's details."""
    global DATA_DIR, APPLIED_FILE, LOG_FILE, LOG_URL, CV_FILE, CV_PROFILE_FILE, WRITER_SYSTEM
    global APPLICANT_NAME, APPLICANT_EMAIL, APPLICANT_PHONE, APPLICANT_LINKEDIN
    global EXPECTED_CTC, NOTICE_PERIOD, NEVER_APPLY_ORGS
    DATA_DIR        = data_dir
    APPLIED_FILE    = os.path.join(data_dir, "applied_jobs.json")
    LOG_FILE        = os.path.join(data_dir, "APPLICATIONS.md")
    CV_PROFILE_FILE = os.path.join(data_dir, "cv_profile.txt")
    try:
        with open(os.path.join(data_dir, "applicant.json"), encoding="utf-8") as f:
            a = json.load(f)
    except (OSError, ValueError):
        a = {}
    APPLICANT_NAME     = a.get("name", "")
    APPLICANT_EMAIL    = os.environ.get("GMAIL_ADDRESS") or a.get("email", "")
    APPLICANT_PHONE    = a.get("phone", "")
    APPLICANT_LINKEDIN = a.get("linkedin", "")
    EXPECTED_CTC       = a.get("expected_ctc", "negotiable")
    NOTICE_PERIOD      = a.get("notice_period", "")
    LOG_URL            = a.get("log_url", "")
    CV_FILE            = os.path.join(data_dir, a.get("cv_file", "cv/CV.pdf"))
    NEVER_APPLY_ORGS   = re.compile(a.get("never_apply_orgs_regex", r"(?!x)x"), re.IGNORECASE)
    WRITER_SYSTEM      = _load_private_text("writer_prompt.txt", WRITER_SYSTEM_DEFAULT)
    global STANDARD_ANSWERS
    STANDARD_ANSWERS   = a.get("standard_answers", [])


DATA_DIR = HERE
STANDARD_ANSWERS = []
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")

MIN_AI_SCORE      = 6
MAX_SENT_PER_DAY  = 5
MAX_KITS_PER_RUN  = 6
DESC_CHARS        = 6000

# Too junior for a mid-to-senior professional
JUNIOR_TITLE = re.compile(
    r'young professional|\byp[- ]?i\b|project associate|research associate|'
    r'\bassociate[- ]?i\b|intern|trainee|junior|\bjr\.?\b|entry[- ]level|fresher|'
    # "Assistant Director", "Executive Director" and "Senior Fellow" are senior
    r'assistant(?!\s+(director|general manager|vice president|professor))|'
    r'(?<!senior )fellow(ship)?\b|\bexecutive\b(?!\s+director)|'
    r'(?<!state )(?<!senior )coordinator\b',
    re.IGNORECASE)

_EMAIL     = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_BAD_EMAIL = re.compile(
    r'noreply|no-reply|donotreply|freejobalert|linkedin|example\.|privacy|'
    r'abuse|webmaster|support@|grievance|rti|vigilance|tender|sales@|'
    r'\.(png|jpg|jpeg|gif)$', re.IGNORECASE)
_APPLY_CUE = re.compile(
    r'appl|send|e-?mail|cv|resume|résumé|bio-?data|submit|share your|write to',
    re.IGNORECASE)


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def _load_applied():
    try:
        with open(APPLIED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_applied(entries):
    with open(APPLIED_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=1, ensure_ascii=False)


def write_log(entries):
    """Human-readable record of every application, newest first."""
    emailed = [e for e in entries if e.get("method") == "email"]
    kits    = [e for e in entries if e.get("method") == "kit"]
    cell    = lambda v: str(v or "").replace("|", "/").replace("\n", " ")
    lines = [
        "# Applications log",
        "",
        f"_Updated {datetime.now().strftime('%d %b %Y, %H:%M')} (UTC) by the job bot._",
        "",
        f"**{len(emailed)} emailed automatically** · **{len(kits)} sent to you as kits** "
        "(apply via the link — the bot cannot submit portals or LinkedIn).",
        "",
        "| Date | Role | Organisation | How | Fit | Link |",
        "|---|---|---|---|---|---|",
    ]
    ordered = sorted(entries, key=lambda e: e.get("date", ""), reverse=True)
    for e in ordered:
        how = f"✅ Emailed to {e.get('to')}" if e.get("method") == "email" else "📝 Kit — apply yourself"
        lines.append(f"| {e.get('date','')} | {cell(e.get('title'))} | {cell(e.get('org'))} | "
                     f"{how} | {e.get('ai_score') or ''} | [posting]({e.get('url','')}) |")
    lines += ["", "## Cover letters", ""]
    for e in ordered:
        if not e.get("body"):
            continue
        lines += [f"<details><summary>{e.get('date','')} — {cell(e.get('title'))}, {cell(e.get('org'))}</summary>",
                  "", f"**Subject:** {e.get('subject','')}", "", "```", e["body"], "```", "", "</details>", ""]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _key(job):
    norm = lambda s: re.sub(r'[^a-z0-9]+', ' ', (s or "").lower()).strip()
    return f"{norm(job.get('org'))}|{norm(job.get('title'))}"


def _strip_html(raw):
    import html as _html
    raw = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', raw or "")
    raw = re.sub(r'(?i)<br\s*/?>|</p>|</li>', '\n', raw)
    return re.sub(r'[ \t]+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', raw))).strip()


def _pdf_text(data):
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages[:6])
    except Exception:
        return ""


def fetch_full_text(job, fetch_page, fetch_bytes):
    """Full posting text (LinkedIn description, web page or PDF notice)."""
    url = job["url"]
    try:
        m = re.search(r'linkedin\.com/jobs/view/.*?-(\d{6,})(?:\?|$)', url)
        if m:
            page = ""
            for attempt in range(3):          # the guest API rate-limits bursts
                try:
                    page = fetch_page(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}")
                    break
                except Exception:
                    time.sleep(20 * (attempt + 1))
            if not page:
                return ""
            dm = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.DOTALL)
            return _strip_html(dm.group(1) if dm else page)[:DESC_CHARS]
        if re.search(r'\.pdf($|\?)', url, re.IGNORECASE):
            return _pdf_text(fetch_bytes(url))[:DESC_CHARS]
        text = _strip_html(fetch_page(url))
        # Aggregator articles link the official notice PDF — read that too
        pm = re.search(r'href="([^"]+\.pdf)"', fetch_page(url), re.IGNORECASE) if "freejobalert" in url else None
        if pm:
            text += "\n\nOFFICIAL NOTICE:\n" + _pdf_text(fetch_bytes(pm.group(1)))
        return text[:DESC_CHARS]
    except Exception as e:
        print(f"  [auto-apply] could not read {url}: {e}")
        return ""


def find_application_email(text):
    """An email address the posting asks applications to go to, or None.

    Only addresses with an application cue ("send your CV to", "apply at")
    within 150 characters count — a stray contact or webmaster address is never
    used as the application address.
    """
    for m in _EMAIL.finditer(text or ""):
        addr = m.group(0).rstrip(".")
        if _BAD_EMAIL.search(addr):
            continue
        window = text[max(0, m.start() - 150):m.end() + 60]
        if _APPLY_CUE.search(window):
            return addr
    return None


def eligible(job, is_bangalore):
    loc = (job.get("location") or "").lower()
    if not (is_bangalore(job) or "remote" in loc):
        return False
    score = job.get("ai_score")
    if score is None:
        if job.get("relevance") != "HIGH":
            return False
    elif score < MIN_AI_SCORE:
        return False
    if JUNIOR_TITLE.search(job.get("title", "")) or NEVER_APPLY_ORGS.search(job.get("org", "")):
        return False
    return True


# ─── GEMINI: METHOD + COVER LETTER ─────────────────────────────────────────────

WRITER_SYSTEM_DEFAULT = ("""You prepare a truthful job application for one candidate.
CANDIDATE (the ONLY facts you may use): {profile}
Fixed details: name {name}; phone {phone}; email {email}; LinkedIn {linkedin}; notice period {notice}; expected CTC {ctc}.
Reply with ONLY a JSON object with keys method ("email"|"portal"|"unclear"), requires_format (bool), subject, body (170-230 word cover email), why_fit (one line).""")
WRITER_SYSTEM = WRITER_SYSTEM_DEFAULT


def write_application(job, text, ai_call, profile):
    system = WRITER_SYSTEM.format(
        profile=profile, name=APPLICANT_NAME, phone=APPLICANT_PHONE,
        email=APPLICANT_EMAIL, linkedin=APPLICANT_LINKEDIN,
        notice=NOTICE_PERIOD, ctc=EXPECTED_CTC)
    user = (f"JOB: {job['title']}\nEMPLOYER: {job['org']}\nLOCATION: {job.get('location','')}\n"
            f"LINK: {job['url']}\n\nPOSTING:\n{text or '(no description available)'}")
    raw = ai_call(system, user)
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start:end + 1])


# ─── SENDING ───────────────────────────────────────────────────────────────────

def send_email(to_addr, subject, body):
    msg = EmailMessage()
    msg["From"]     = f"{APPLICANT_NAME} <{APPLICANT_EMAIL}>"
    msg["To"]       = to_addr
    msg["Bcc"]      = APPLICANT_EMAIL
    msg["Reply-To"] = APPLICANT_EMAIL
    msg["Subject"]  = subject
    msg.set_content(body)
    with open(CV_FILE, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="pdf",
                           filename=os.path.basename(CV_FILE))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(APPLICANT_EMAIL, GMAIL_APP_PASSWORD)
        s.send_message(msg)


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _kit_message(job, app):
    return "\n".join([
        "📝 <b>Application kit — apply in 2 min</b>",
        f"<b>{_esc(job['title'])}</b>",
        f"{_esc(job['org'])} · {_esc(job.get('location',''))}",
        f"Fit {job.get('ai_score','?')}/10: {_esc(app.get('why_fit',''))}",
        f"<a href=\"{job['url']}\">Open the job →</a>",
        "",
        "<b>Cover letter</b> — tap the block to copy it:",
        f"<pre>{_esc(app.get('body', ''))}</pre>",
        "",
        "<b>Standard answers</b>",
        f"Notice period: {NOTICE_PERIOD} · Expected CTC: {EXPECTED_CTC}",
        *[l for l in STANDARD_ANSWERS],
    ])[:4000]


# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

def run(jobs, ai_call, fetch_page, fetch_bytes, notify, is_bangalore):
    """Apply to / prepare kits for eligible jobs. Never raises."""
    try:
        _run(jobs, ai_call, fetch_page, fetch_bytes, notify, is_bangalore)
    except Exception as e:
        print(f"[auto-apply] stopped: {type(e).__name__}: {e}")


def _run(jobs, ai_call, fetch_page, fetch_bytes, notify, is_bangalore):
    try:
        with open(CV_PROFILE_FILE, encoding="utf-8") as f:
            profile = f.read().strip()
    except OSError:
        print("[auto-apply] no cv_profile.txt — skipped.")
        return

    applied   = _load_applied()
    before    = len(applied)
    done_keys = {e["key"] for e in applied}
    today     = datetime.now().strftime("%Y-%m-%d")
    sent_today = sum(1 for e in applied if e.get("date") == today and e.get("method") == "email")
    can_send  = bool(GMAIL_APP_PASSWORD and APPLICANT_EMAIL) and os.path.exists(CV_FILE)

    todo = [j for j in jobs if eligible(j, is_bangalore) and _key(j) not in done_keys]
    # Why the rest were skipped — shown in the run log
    why = {"not South India/remote": 0, "fit below 6": 0, "junior title": 0, "already applied": 0}
    for j in jobs:
        loc = (j.get("location") or "").lower()
        if not (is_bangalore(j) or "remote" in loc):
            why["not South India/remote"] += 1
        elif (j.get("ai_score") if j.get("ai_score") is not None else (8 if j.get("relevance") == "HIGH" else 0)) < MIN_AI_SCORE:
            why["fit below 6"] += 1
        elif JUNIOR_TITLE.search(j.get("title", "")) or NEVER_APPLY_ORGS.search(j.get("org", "")):
            why["junior title"] += 1
        elif _key(j) in done_keys:
            why["already applied"] += 1
    print(f"[auto-apply] of {len(jobs)} matches, skipped: " + ", ".join(f"{k} {v}" for k, v in why.items() if v))
    print(f"\n[auto-apply] {len(todo)} eligible job(s); "
          f"{'email sending ON' if can_send else 'kits only (no GMAIL_APP_PASSWORD)'}.")
    kits = 0

    for job in todo:
        text  = fetch_full_text(job, fetch_page, fetch_bytes)
        if len(text) < 300:
            print(f"  [auto-apply] no posting text for {job['title']} — retry next run.")
            continue
        email = find_application_email(text)
        try:
            app = write_application(job, text, ai_call, profile)
        except Exception as e:
            print(f"  [auto-apply] Gemini failed for {job['title']}: {e}")
            continue
        time.sleep(7)                     # Gemini free-tier pacing

        by_email = (email and app.get("method") == "email" and not app.get("requires_format")
                    and email.lower() in (text or "").lower())
        entry = {"key": _key(job), "title": job["title"], "org": job["org"],
                 "url": job["url"], "date": today, "ai_score": job.get("ai_score"),
                 "subject": app.get("subject", ""), "body": app.get("body", "")}

        if by_email and can_send and sent_today < MAX_SENT_PER_DAY:
            try:
                send_email(email, app["subject"], app["body"])
            except Exception as e:
                print(f"  [auto-apply] send to {email} failed: {e}")
                continue
            sent_today += 1
            applied.append({**entry, "method": "email", "to": email})
            notify("\n".join([
                "✅ <b>Applied automatically</b>",
                f"<b>{_esc(job['title'])}</b> — {_esc(job['org'])}",
                f"Sent to {_esc(email)} with your CV (copy in your Gmail).",
                f"Fit {job.get('ai_score','?')}/10: {_esc(app.get('why_fit',''))}",
                f"<a href=\"{job['url']}\">Posting →</a>",
            ]))
            print(f"  [auto-apply] SENT: {job['title']} → {email}")
        elif kits < MAX_KITS_PER_RUN:
            if notify(_kit_message(job, app)) is False:
                print(f"  [auto-apply] kit not delivered, will retry: {job['title']}")
                continue
            kits += 1
            applied.append({**entry, "method": "kit"})
            print(f"  [auto-apply] kit: {job['title']}")

    _save_applied(applied)
    write_log(applied)
    new = len(applied) - before
    if new:
        emailed = sum(1 for e in applied if e.get("method") == "email")
        notify(f"📒 <b>Applications log</b>: {new} new this run · {emailed} emailed in total · "
               f"{len(applied) - emailed} kits in total\n<a href=\"{LOG_URL}\">Open the full log →</a>")
