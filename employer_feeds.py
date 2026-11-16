"""
Employer career pages — think tanks, foundations and consultancies that post
many roles only on their own job systems, not on LinkedIn.

Each employer runs a standard applicant-tracking system with a public job
feed: Workday (JSON "cxs" endpoint), Workable (widget API) or Zoho Recruit
(the career page embeds its job list). Only openings in India or remote are
kept. Never raises.
"""

import html
import json
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Accept": "application/json", "Content-Type": "application/json"}
SOURCE = "Employer careers"
INDIA = re.compile(r'india|delhi|bengaluru|bangalore|mumbai|hyderabad|chennai|pune|gurugram|gurgaon|'
                   r'noida|kolkata|ahmedabad|jaipur|lucknow|patna|bhubaneswar|remote', re.I)

# (employer, host, tenant, site, search text)
WORKDAY = [
    ("WRI India",             "wri.wd501.myworkdayjobs.com",             "wri",             "WRI_India",                      ""),
    ("Gates Foundation",      "gatesfoundation.wd1.myworkdayjobs.com",   "gatesfoundation", "Gates",                          "India"),
    ("PATH",                  "path.wd1.myworkdayjobs.com",              "path",            "External",                       "India"),
    ("FHI 360",               "fhi.wd1.myworkdayjobs.com",               "fhi",             "FHI_360_External_Career_Portal", "India"),
    ("ERM",                   "erm.wd3.myworkdayjobs.com",               "erm",             "ERM_Careers",                    "India"),
    ("PwC India",             "pwc.wd3.myworkdayjobs.com",               "pwc",             "Global_Experienced_Careers",     "India government"),
]
# (employer, Workable account)
WORKABLE = [
    ("Evidence Action",                 "evidence-action"),
    ("Nutrition International",         "nutritionintl"),
    ("International Water Management Institute", "international-water-management-institute"),
]
# (employer, Zoho Recruit career host)
ZOHO = [
    ("CEEW",            "ceew.zohorecruit.in"),
    ("Swaniti Initiative", "swaniti.zohorecruit.in"),
    ("Indus Action",    "indusaction.zohorecruit.com"),
    ("Wadhwani AI",     "wadhwaniai.zohorecruit.in"),
    ("NSDC",            "nsdcindia.zohorecruit.in"),
]


def _get(url, data=None, timeout=25):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _job(title, org, location, url, description=""):
    return {"title": title.strip()[:160], "org": org, "location": (location or "India").strip()[:80],
            "url": url, "updated": "", "source": SOURCE, "description": description[:3000]}


def _workday(name, host, tenant, site, q):
    jobs, offset = [], 0
    while offset < 100:
        d = json.loads(_get(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                            {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": q}))
        posts = d.get("jobPostings", [])
        for p in posts:
            loc = p.get("locationsText", "")
            if INDIA.search(loc) or (not q and "india" in site.lower()):
                jobs.append(_job(p["title"], name, loc, f"https://{host}/en-US/{site}{p['externalPath']}"))
        offset += 20
        if offset >= d.get("total", 0) or not posts:
            break
    return jobs


def _workable(name, account):
    d = json.loads(_get(f"https://apply.workable.com/api/v1/widget/accounts/{account}"))
    return [_job(j["title"], name, ", ".join(x for x in (j.get("city"), j.get("country")) if x) or
                 ("Remote" if j.get("telecommuting") else ""), j.get("url") or j.get("shortlink", ""))
            for j in d.get("jobs", [])
            if INDIA.search(f"{j.get('country','')} {j.get('city','')}") or j.get("telecommuting")]


def _zoho(name, host):
    page = _get(f"https://{host}/jobs/Careers", timeout=40)
    for m in re.finditer(r'<input type="hidden" value="(\[\{[^"]*?Posting_Title[^"]*)"', page):
        rows = json.loads(html.unescape(m.group(1)))
        return [_job(r.get("Posting_Title") or r.get("Job_Opening_Name", ""), name,
                     ", ".join(x for x in (r.get("City"), r.get("Country")) if x and x != "NA")
                     or ("Remote" if r.get("Remote_Job") else "India"),
                     f"https://{host}/jobs/Careers/{r['id']}")
                for r in rows if r.get("Publish", True) and (INDIA.search(str(r.get("Country", "")) + str(r.get("City", "")))
                                                         or r.get("Remote_Job"))]
    return []


def fetch_employer_jobs():
    print(f"\n[{SOURCE}] Checking {len(WORKDAY) + len(WORKABLE) + len(ZOHO)} employer career sites...")
    jobs = []
    for fn, rows in ((_workday, WORKDAY), (_workable, WORKABLE), (_zoho, ZOHO)):
        for row in rows:
            try:
                found = fn(*row)
                print(f"  [{SOURCE}] {row[0]}: {len(found)}")
                jobs.extend(found)
            except Exception as e:
                print(f"  [{SOURCE}] {row[0]}: {type(e).__name__}: {str(e)[:80]}")
    print(f"[{SOURCE}] {len(jobs)} India / remote openings.")
    return jobs
