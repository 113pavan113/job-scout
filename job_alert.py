"""
Job Alert – Multi-Site CV Matcher with Telegram Alerts
Sources:
  1. unjobs.org – New Delhi
  2. unjobs.org – Bangalore
  3. devnetjobsindia.org – All India development sector
  4. impactpool.org – Global UN/NGO/development (FAO, WFP, IFAD, World Bank, ADB, GIZ, IFC, ITC)
  5. athenainfonomics.com – India policy/development consulting (Delhi/Bangalore)
  6. reliefweb.int – Development/humanitarian jobs in India (public jobs river)
  7. devnetjobs.org – Global development sector jobs (India filter)
  8. jobshobnest.com – CSR/social sector jobs, Delhi/Bangalore/Remote (salary filter)
  9. atree.org – Ashoka Trust for Research in Ecology, Bangalore
 10. selcofoundation.org – SELCO Foundation, Bangalore (livelihoods/agri/rural)
 11. linkedin.com – public guest job search, Bangalore-first keyword sweep + Delhi NCR
 12. Government bodies – vacancy notices from NITI Aayog, NABCONS, SFAC, MoFPI,
     MANAGE, MPEDA and Spices Board (consultant / Young Professional posts)
 13. freejobalert.com – Karnataka government jobs + all-India contract /
     walk-in ("without exam") posts, filtered to policy / agri / programme roles
 14. LinkedIn company follow-list – every current India opening at chosen employers

Scores jobs against the candidate's CV and sends Telegram alerts for NEW matches.
Alert includes: location, matched keywords, posted date, and direct job link.
Run: python job_alert.py

NOTE: ReliefWeb's JSON API is gated behind a staff-approved appname, so this
scrapes their public jobs river instead — no key needed.
"""

import urllib.request
import urllib.error
import urllib.parse
import html
import re
import csv
import os
import json
import sys
import time
from datetime import datetime

# ─── TELEGRAM CONFIG ───────────────────────────────────────────────────────────

# Load .env file if present (local runs) — GitHub Actions uses repo Secrets
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")

# Personal data (CV, profile, prompts, seen-list, logs) lives in a private repo
# checked out at JOB_DATA_DIR; locally it defaults to this folder.
DATA_DIR = os.environ.get("JOB_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
SEEN_JOBS_FILE = os.path.join(DATA_DIR, "seen_jobs.json")


def _load_private_text(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


def _applicant():
    try:
        with open(os.path.join(DATA_DIR, "applicant.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

# ─── CV PROFILE ────────────────────────────────────────────────────────────────

CV_KEYWORDS = {
    # the candidate's actual domain — agriculture, trade, food, fisheries, policy
    "high": [
        "agriculture", "agricultural", "agri", "agrifood", "agri-export",
        "export", "trade", "international trade", "food security",
        "fisheries", "fishery", "value chain", "horticulture",
        "commodity", "commodities", "cooperative", "cooperatives",
        "niti aayog", "apeda", "millet", "rice", "cereals", "organic",
        "blue economy", "SPS", "TBT", "food", "nutrition",
        "food systems", "food policy", "agri policy", "trade policy",
        "agricultural policy", "rural livelihoods",
        # Additional high-relevance keywords
        "agribusiness", "crop", "livestock", "seed", "fertilizer",
        "irrigation", "watershed", "soil", "farm", "farmer",
        "food value chain", "supply chain", "market access",
        "food processing", "post-harvest", "FSSAI", "WTO",
        "tariff", "non-tariff", "import", "sanitary", "phytosanitary",
        "GI tag", "geographical indication", "organic certification",
        "climate-smart agriculture", "agroforestry", "aquaculture",
        "food and nutrition", "agricultural finance", "rural finance",
        "spices", "oilseeds", "pulses", "horticulture development",
        "agtech", "agritech", "agri-tech", "ag-tech", "dairy", "plantation",
        "agronomy", "regenerative", "natural farming", "agroecology",
        "food safety", "rural development", "natural resource management",
        "climate resilience", "sustainable agriculture", "FPC",
        # Agricultural trade & export policy. Deliberately excludes operational logistics
        # (freight, cargo, warehousing, 3PL): those matched shipping and
        # supply-chain jobs at Amazon, UPS and Kuehne+Nagel that have nothing
        # to do with an agricultural economist's profile.
        "exim", "import export", "import-export", "foreign trade",
        "cross-border trade", "trade regulations", "export policy",
        "agricultural export", "agri export", "commodity export",
        "export promotion", "export development", "market linkage",
        "customs clearance", "customs compliance",
        "export documentation", "export compliance", "export control",
        "DGFT", "trade negotiation", "bilateral trade", "multilateral trade",
        "trade agreement", "FTA", "export standards",
        # Government relations & bilateral cooperation — a lead profile family;
        # government-institution experience is
        # exactly what embassies, bilateral agencies and international bodies
        # recruit for, and none of it was searchable before.
        "government relations", "government affairs", "public affairs",
        "development cooperation", "bilateral cooperation", "bilateral",
        "diplomatic", "embassy", "high commission", "mission",
        "programme officer", "program officer", "policy advisor",
        "policy adviser", "sector counsellor", "sector advisor",
        "trade advisor", "trade counsellor", "inter-ministerial",
        "multi-stakeholder", "stakeholder engagement", "briefing note",
        "project management unit", "institutional partnerships",
        "strategic partnerships", "government engagement",
        "public policy", "policy analyst", "policy research",
        # Policy-team titles at Bangalore's consumer-internet and food companies
        # (Zepto, Swiggy, Flipkart, Meesho), which use "Corporate / External /
        # Regulatory Affairs" titles.
        "corporate affairs", "external affairs", "regulatory affairs",
        "government advisor", "government adviser", "government liaison",
        # The eight target role families (Nov 2026): trade-promotion offices,
        # government partnerships, food regulation, sustainability standards
        # and bilateral technical posts.
        "trade promotion", "investment promotion", "trade commissioner",
        "trade officer", "commercial officer", "sector specialist",
        "government partnerships", "public partnerships", "food regulatory",
        "food policy", "sustainability standards", "certification programme",
        "certification program", "traceability", "responsible sourcing",
        "esg agri", "technical expert", "technical advisor",
        "policy & government", "policy and government", "policy & advocacy",
        "public policy manager", "head of policy",
        # State-government and governance work — Karnataka departments, their
        # PMUs (usually staffed via Deloitte / EY / PwC / KPMG / IPE Global) and
        # CM / policy fellowships. Government-institution experience maps
        # directly onto these.
        "state government", "government of karnataka", "karnataka government",
        "govt of karnataka", "government advisory", "public sector",
        "government & public", "government and public", "PMU",
        "programme management unit", "program management unit", "e-governance",
        "policy fellow", "cm fellow", "chief minister",
        "public finance", "state planning", "policy specialist",
        "policy consultant", "policy lead", "policy manager",
    ],
    # Professional context — relevant but not domain-specific enough alone
    "medium": [
        "policy", "public policy",
        "research", "analyst", "analysis", "consultant", "consulting",
        "stakeholder", "policy brief", "data analysis", "strategy", "strategic",
        "compliance", "standards", "quality", "certification", "traceability",
        "rural", "market", "sustainability", "sustainable",
        "UNDP", "FAO", "IFAD", "ILO", "UNESCO", "WFP", "WHO", "CGIAR",
        "ministry", "business development", "market development", "market intelligence",
        # Business development, strategy and partnerships (Nov 2026): at agri / food / trade /
        # development / government-facing employers these roles fit.
        "strategy manager", "strategy and operations", "strategy & operations",
        "chief of staff", "founder's office", "founders office", "partnerships",
        "alliances", "institutional business", "government business", "b2g",
        # Additional medium-relevance
        "GIZ", "USAID", "FCDO", "DFID", "ADB", "IFC", "ICRISAT", "IRRI",
        "IFPRI", "CIMMYT", "IWMI", "World Bank", "Asian Development Bank",
        "livelihoods", "livelihood", "climate change", "environment", "natural resources",
        "gender", "women empowerment", "smallholder", "cooperative development",
        "producer organization", "FPO", "farmer producer",
        "technical assistance", "advisory", "policy analysis",
        "economics", "economist", "trade facilitation",
        # Trade context that is real but not domain-defining on its own.
        # Operational logistics terms were removed entirely — see the note in
        # the "high" list above.
        "customs", "trade compliance", "trade documentation",
        "trade operations", "supply chain", "commodity trading",
        "agricultural marketing", "cooperative marketing",
        "governance", "public governance", "urban governance",
    ],
    # Generic — many NGO/govt jobs have these
    "low": [
        "programme", "program", "project", "development", "manager",
        "monitoring", "evaluation", "M&E", "capacity building", "training",
        "government", "coordination", "partnership",
        "workshop", "conference", "international", "global", "national",
        "finance", "budget", "procurement", "communication",
        "knowledge management", "documentation", "report",
        "officer", "specialist", "coordinator", "associate",
    ],
}

ALL_KEYWORDS = (
    [(k, 3) for k in CV_KEYWORDS["high"]] +
    [(k, 2) for k in CV_KEYWORDS["medium"]] +
    [(k, 1) for k in CV_KEYWORDS["low"]]
)

# A job MUST match at least one of these to qualify as HIGH —
# prevents generic NGO/rural jobs from falsely ranking HIGH
CORE_DOMAIN = {
    "agriculture", "agricultural", "agri", "agrifood", "agri-export",
    "fisheries", "fishery", "food security", "food systems", "food policy",
    "agri policy", "trade policy", "agricultural policy", "rural livelihoods",
    "value chain", "horticulture", "export", "international trade",
    "SPS", "TBT", "apeda", "millet", "rice", "cereals", "organic",
    "blue economy", "commodity", "commodities", "cooperative", "cooperatives",
    "food", "nutrition",
    # Additional core domain terms
    "trade", "agribusiness", "crop", "livestock", "seed", "fertilizer",
    "irrigation", "farm", "farmer", "food processing", "post-harvest",
    "FSSAI", "WTO", "tariff", "aquaculture", "agroforestry",
    "spices", "oilseeds", "pulses", "market access",
    "food value chain", "agricultural finance", "rural finance",
    "food and nutrition", "horticulture development",
    "GI tag", "geographical indication", "organic certification",
    "climate-smart agriculture", "FPO", "farmer producer",
    "producer organization", "smallholder",
    # Agri-adjacent fields that dominate Bangalore's market — agritech,
    # dairy/plantations, livelihoods and natural-resource work
    "agtech", "agritech", "agri-tech", "ag-tech", "dairy", "plantation",
    "agronomy", "regenerative", "natural farming", "agroecology",
    "food safety", "rural development", "livelihood", "livelihoods",
    "watershed", "natural resource management", "climate resilience",
    "sustainable agriculture", "FPC", "market linkage",
    # Agricultural trade & export policy core
    "exim", "import export", "import-export", "foreign trade",
    "cross-border trade", "trade regulations", "export policy",
    "agricultural export", "agri export", "commodity export",
    "export promotion", "export development", "market linkage",
    "customs clearance", "customs compliance",
    "export documentation", "export compliance", "export control",
    "DGFT", "trade negotiation", "bilateral trade", "multilateral trade",
    "trade agreement", "FTA", "export standards", "import",
    # Government relations & bilateral cooperation core
    "government relations", "government affairs", "public affairs",
    "development cooperation", "bilateral cooperation", "bilateral",
    "diplomatic", "embassy", "high commission",
    "programme officer", "program officer", "policy advisor",
    "policy adviser", "sector counsellor", "sector advisor",
    "trade advisor", "trade counsellor", "inter-ministerial",
    "multi-stakeholder", "briefing note", "project management unit",
    "government engagement", "public policy", "policy research",
    "corporate affairs", "external affairs", "regulatory affairs",
    "government advisor", "government adviser", "government liaison",
    "trade promotion", "investment promotion", "trade commissioner",
    "trade officer", "commercial officer", "sector specialist",
    "government partnerships", "public partnerships", "food regulatory",
    "food policy", "sustainability standards", "certification programme",
    "certification program", "traceability", "responsible sourcing",
    "esg agri", "technical expert", "technical advisor",
    "policy & government", "policy and government", "policy & advocacy",
    "public policy manager", "head of policy",
    # State-government and governance work — Karnataka departments, their
    # PMUs (usually staffed via Deloitte / EY / PwC / KPMG / IPE Global) and
    # CM / policy fellowships. Government-institution experience maps
    # directly onto these.
    "state government", "government of karnataka", "karnataka government",
    "govt of karnataka", "government advisory", "public sector",
    "government & public", "government and public", "PMU",
    "programme management unit", "program management unit", "e-governance",
    "policy fellow", "cm fellow", "chief minister",
    "public finance", "state planning", "policy specialist",
    "policy consultant", "policy lead", "policy manager",
}

# Generic commerce vocabulary. These stay high-weight (the profile IS trade),
# but on their own they describe a semiconductor export-compliance desk or a
# bank's trade-finance team just as well as an agricultural export role — so
# they must not be able to unlock the HIGH tier by themselves. Anything
# agri-specific ("agricultural export", "trade policy", SPS/TBT, APEDA) stays
# in CORE_DOMAIN and still does.
GENERIC_TRADE = {
    "export", "trade", "international trade", "import", "exim",
    "import export", "import-export", "foreign trade", "cross-border trade",
    "customs clearance", "customs compliance", "export documentation",
    "export compliance", "export control", "DGFT", "trade regulations",
    "export standards", "tariff", "non-tariff", "FTA", "trade agreement",
    "commodity", "commodities",
}
CORE_DOMAIN = {c for c in CORE_DOMAIN if c.lower() not in {g.lower() for g in GENERIC_TRADE}}

# Development-sector employers. Relevance often lives in WHO is hiring, not in
# the job title: "Head of Impact, Livelihood Programs" at The/Nudge and
# "Senior Research Fellow (Quantitative)" at the Indian Institute of Public
# Health are both squarely in the profile, but neither title carries an
# agriculture word, so keyword scoring alone threw them away. A match here
# counts as a domain signal in its own right.
DEV_SECTOR_ORGS = {
    # UN system
    "fao", "wfp", "undp", "unicef", "unesco", "unido", "unep", "un women",
    "unhcr", "unfpa", "unops", "ifad", "iom", "world food programme",
    "united nations", "unv", "unido",
    # IFIs and development banks
    "world bank", "ifc", "asian development bank", "aiib", "adb",
    # CGIAR and agricultural research
    "cgiar", "icrisat", "irri", "cimmyt", "ifpri", "iwmi", "ilri", "ciat",
    "icarda", "worldfish", "bioversity", "icar", "cip ",
    # Bilateral agencies
    "giz", "usaid", "fcdo", "dfid", "jica", "kfw", "danida", "sida", "afd",
    "swiss agency", "embassy of",
    # Foreign trade-promotion offices and chambers (role family 7)
    "indo-german chamber", "igcc", "consulate general", "netherlands business",
    "nbso", "business france", "enterprise singapore", "kotra", "jetro",
    "trade commission", "uk department for business and trade", "ficci",
    "confederation of indian industry", "assocham",
    # Sustainability-standards and certification bodies (role family 8)
    "control union", "proforest", "bonsucro", "better cotton", "4c services",
    "round table on responsible soy", "rspo", "wwf", "textile exchange",
    "grant thornton bharat",
    # Foundations
    "gates foundation", "rockefeller", "ford foundation", "tata trust",
    "azim premji", "omidyar", "shell foundation", "michael susan dell",
    # Indian policy institutes and think tanks
    "niti aayog", "ceew", "teri", "wri ", "world resources", "ifmr",
    "public health foundation", "institute of public health",
    "institutes of public health", "indian institute of public", "isb ",
    "indian school of business", "takshashila", "orf ", "cpr ",
    "centre for policy research", "icrier", "ncaer",
    # Development NGOs, implementers and impact consultancies
    "pradan", "baif", "digital green", "sattva", "dalberg", "idinsight",
    "j-pal", "jpal", "samagra", "nudge", "atree", "selco", "grameen",
    "precision development", "transform rural", "vrutti", "solidaridad",
    "technoserve", "heifer", "rainforest alliance", "idh ", "landesa",
    "winrock", "acdi", "swasti", "microsave", "intellecap", "samhita",
    "athena infonomics", "catalyst", "sewa", "srijan", "aga khan",
    "care india", "oxfam", "save the children", "plan international",
    "action against hunger", "welthungerhilfe", "helvetas", "snv ",
    "chai", "clinton health", "path ", "brac", "bill  melinda",
    # German development cooperation and Germany-linked institutions — the
    # German academic background is an advantage here
    "deutsche gesellschaft", "daad", "ahk", "indo-german", "indo german",
    "german chamber", "consulate general of germany", "german consulate",
    "german embassy", "fraunhofer", "max planck", "max mueller", "goethe-institut",
    "kfw", "bmz", "giz india", "german agency", "icrisat bangalore",
    # Embassies, high commissions and diplomatic missions
    "embassy", "high commission", "consulate", "royal danish",
    "delegation of the european union", "eu delegation", "european union",
    "british council", "alliance francaise", "goethe",
    # Bilateral development and trade-promotion agencies
    "danida", "norad", "enabel", "expertise france", "agence francaise",
    "netherlands enterprise", "business sweden", "business finland",
    "innovation centre denmark", "invest india", "bmz", "sdc ",
    "austrade", "ukti", "department for business",
    # Indian government bodies and commodity boards
    "niti aayog", "apeda", "ncel", "nabard", "sfac", "nabcons",
    "national institute of agricultural extension", "manage (", "nirdpr", "spices board",
    "mpeda", "tea board", "coffee board", "ministry of", "government of india",
    "national cooperative", "fssai", "ecgc", "dgft",
    # Trade and standards bodies
    "international trade centre", "unctad", "world trade organization",
    "codex", "ippc", "oie ", "wto",
    # Bangalore policy institutes, universities and development NGOs — the
    # city's dev-sector employers rarely put an agriculture word in a title.
    "indian institute for human settlements", "iihs", "cstep",
    "public affairs centre", "janaagraha", "daksh", "isec",
    "institute for social and economic change", "national institute of advanced",
    "iim bangalore", "indian institute of management bangalore",
    "azim premji university", "myrada", "dhan foundation", "wadhwani",
    "akshaya patra", "dasra", "wri india", "ashoka trust", "ashoka university",
    "social alpha",
    "villgro", "foundation for ecological security", "keystone foundation",
    "dhwani rural", "sri sri rural", "outreach association", "fair trade",
    "fairtrade", "nabkisan", "the/nudge", "indian institute of science",
    # Karnataka government departments, missions and state corporations
    "government of karnataka", "govt of karnataka", "karnataka state",
    "kappec", "karnataka state agricultural produce", "ksrlps", "sanjeevini",
    "watershed development department", "karnataka evaluation authority",
    "karnataka agricultural price commission", "kdem",
    "karnataka digital economy", "kitven", "karnataka udyog mitra",
    "invest karnataka", "karnataka innovation", "kspcb", "kssidc", "ksdc",
    "karnataka skill development", "bbmp", "bmrcl", "bwssb", "kiadb",
    "krdcl", "karnataka state planning", "e-governance", "centre for e-governance",
    "ipe global", "nirmaan", "raitha", "university of agricultural sciences",
    "uas bangalore", "uas dharwad", "isec", "iimb",
}

# Agri-food and agritech companies. A commodity / export background
# is directly relevant to their trade, sourcing, policy and
# sustainability desks — and Bangalore is India's agritech hub. Their IT and
# engineering roles are still dropped by NON_FIT_TITLE below.
AGRI_FOOD_ORGS = {
    "cargill", "adm", "archer daniels", "ofi", "olam", "bunge",
    "louis dreyfus", "ed&f man", "ed f man", "wilmar", "viterra",
    "syngenta", "bayer crop", "corteva", "upl", "rallis", "dhanuka",
    "rijk zwaan", "enza zaden", "east-west seed", "known-you seed",
    "mahyco", "nuziveedu", "advanta", "sakata",
    "mahindra agri", "itc agri", "godrej agrovet", "tata consumer",
    "dehaat", "ninjacart", "arya.ag", "arya collateral", "agrostar",
    "cropin", "jai kisan", "samunnati", "waycool", "gramophone", "bighaat",
    "fasal", "agnext", "akshayakalpa", "kisankonnect",
    "agrevolution", "farmart", "gdc agri", "otipy", "ergos",
    "rabobank", "nafed", "amul",
    # Food and grocery companies with policy / regulatory teams (role family 1).
    # Their tech, category and ops roles are still dropped by the title filters.
    "zepto", "blinkit", "bigbasket", "licious", "country delight", "nestle",
    "hindustan unilever", "pepsico", "britannia", "itc limited", "marico",
    "dabur", "mondelez", "nandini", "karnataka milk", "kmf",
}

# Employers whose names collide with dev-sector vocabulary. "Embassy" is a
# Bangalore real-estate group (Embassy REIT, Embassy Office Parks) — not a
# diplomatic mission — and its listings were reaching the alert.
NON_DEV_ORGS = {
    "embassy reit", "embassy group", "embassy office parks",
    "embassy developments", "embassy services", "embassy property",
}


def _org_matches(org, tokens):
    o = " " + (org or "").lower().replace("&", " ") + " "
    for token in tokens:
        t = token.strip().replace("&", " ")
        if len(t) <= 4:                       # short codes: whole word only
            if re.search(r'\b' + re.escape(t) + r'\b', o):
                return True
        elif t in o:
            return True
    return False


def org_is_non_dev(org):
    return _org_matches(org, NON_DEV_ORGS)


def org_is_agri_food(org):
    return not org_is_non_dev(org) and _org_matches(org, AGRI_FOOD_ORGS)


def org_is_dev_sector(org):
    """True when the employer is itself a development-sector signal."""
    return not org_is_non_dev(org) and _org_matches(org, DEV_SECTOR_ORGS)


# Short org codes and abbreviations — must match as whole words to avoid
# substring false-positives (e.g. "UN" inside "volunteers", "foundation")
WHOLE_WORD_KEYWORDS = {"un", "fao", "wfp", "who", "ilo", "sps", "tbt", "adb", "giz", "ifc", "m&e",
                       "exim", "dgft", "import", "fta", "mission", "rural", "fpc",
                       "national", "embassy"}

# ─── HTTP HELPER ───────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_bytes(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def fetch_page(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace")


# ─── SOURCE 1 & 2: UNJOBS.ORG ─────────────────────────────────────────────────

UNJOBS_SOURCES = [
    {"name": "UNjobs Bangalore",  "url": "https://unjobs.org/duty_stations/blr"},
    {"name": "UNjobs New Delhi",  "url": "https://unjobs.org/duty_stations/del"},
]


def parse_unjobs_page(html_content, source_name):
    jobs = []
    job_block_re = re.compile(r'class="job"[^>]*>.*?</div>', re.IGNORECASE | re.DOTALL)
    title_re     = re.compile(r'href="(https://unjobs\.org/vacancies/\d+)"[^>]*>\s*([^<]+?)\s*</a>', re.IGNORECASE)
    org_re       = re.compile(r'</a><br>\s*([^<\n]+?)\s*<br>', re.IGNORECASE)
    time_re      = re.compile(r'datetime="([^"]+)"', re.IGNORECASE)

    for block_match in job_block_re.finditer(html_content):
        block = block_match.group(0)
        tm = title_re.search(block)
        if not tm:
            continue
        url   = tm.group(1)
        title = html.unescape(tm.group(2).strip())
        om    = org_re.search(block)
        org   = html.unescape(om.group(1).strip()) if om else "Unknown"
        tim   = time_re.search(block)
        updated = tim.group(1)[:10] if tim else ""
        jobs.append({"title": title, "url": url, "org": org, "updated": updated, "source": source_name})

    return jobs


def get_unjobs_pages(html_content):
    m = re.search(r'of\s+(\d+)\s+results', html_content)
    if m:
        total = int(m.group(1))
        return (total // 25) + (1 if total % 25 else 0)
    return 1


def scrape_unjobs(source):
    name, base_url = source["name"], source["url"]
    print(f"\n[{name}] Fetching page 1...")
    try:
        first = fetch_page(base_url)
    except Exception as e:
        # unjobs.org sits behind a Cloudflare JS challenge as of 27 Aug 2026,
        # which urllib cannot solve — report and move on.
        print(f"[{name}] Error: {e}")
        return []
    pages  = get_unjobs_pages(first)
    print(f"[{name}] {pages} page(s) found.")
    jobs   = parse_unjobs_page(first, name)

    for page in range(2, pages + 1):
        print(f"[{name}] Fetching page {page}/{pages}...")
        try:
            content = fetch_page(f"{base_url}/{page}")
            jobs.extend(parse_unjobs_page(content, name))
        except Exception as e:
            print(f"[{name}] Error page {page}: {e}")

    return jobs


# ─── SOURCE 3: DEVNETJOBSINDIA.ORG ────────────────────────────────────────────

DEVNET_URL  = "https://www.devnetjobsindia.org/standard_jobs.aspx"
DEVNET_NAME = "DevNetJobs India"

# Only alert for jobs in these cities (case-insensitive)
DEVNET_CITIES = ["delhi", "new delhi", "bangalore", "bengaluru", "gurugram", "gurgaon", "noida", "karnataka", "hyderabad",
                 "chennai", "tamil nadu", "kochi", "kerala", "thiruvananthapuram", "coimbatore", "mysuru", "mysore", "telangana"]

BANGALORE_MARKERS = {"bangalore", "bengaluru", "karnataka"}
SOUTH_MARKERS     = {"hyderabad", "telangana", "chennai", "tamil nadu", "kochi", "kerala",
                     "thiruvananthapuram", "trivandrum", "coimbatore", "mysuru", "mysore",
                     "visakhapatnam", "andhra"}
DELHI_MARKERS     = {"delhi", "new delhi", "ncr", "noida", "gurugram", "gurgaon"}


def parse_devnet_page(html_content):
    """Parse DevNet jobs. Current structure (2025+):
      <a href="https://devnetjobsindia.org/jobdescription.aspx?job_id=ID">
        <p class="fw-bold standardJobTitle ..."><span ...>TITLE</span></p>
        <p class="m-0 standardJobInfo"><span ...>ORG</span></p>
        <p class="m-0 standardJobInfo"><span><span ...>Location: CITY, STATE</span></span></p>
    """
    jobs = []

    url_re   = re.compile(r'href="(https://devnetjobsindia\.org/jobdescription\.aspx\?job_id=(\d+))"', re.IGNORECASE)
    title_re = re.compile(r'lblJobTitle[^"]*"[^>]*>\s*([^<]+?)\s*</span>', re.IGNORECASE)
    org_re   = re.compile(r'lblJobCo[^"]*"[^>]*>\s*([^<]+?)\s*</span>', re.IGNORECASE)
    loc_re   = re.compile(r'lblLocation[^"]*"[^>]*>\s*Location:\s*([^<]+?)\s*</span>', re.IGNORECASE)

    blocks = re.split(r'(?=href="https://devnetjobsindia\.org/jobdescription\.aspx\?job_id=)', html_content)

    for block in blocks:
        um = url_re.search(block)
        if not um:
            continue

        job_url = um.group(1)

        tm = title_re.search(block)
        if not tm:
            continue
        title = html.unescape(tm.group(1).strip())

        om  = org_re.search(block)
        org = html.unescape(om.group(1).strip()) if om else "Unknown"

        lm       = loc_re.search(block)
        location = html.unescape(lm.group(1).strip()) if lm else ""

        # City filter
        combined_lower = (location + " " + title).lower()
        matched_city = next((city for city in DEVNET_CITIES if city in combined_lower), None)
        if not matched_city:
            continue

        if "value member" in title.lower() or "value member" in org.lower():
            continue

        jobs.append({
            "title":    title,
            "url":      job_url,
            "org":      org,
            "updated":  "",
            "source":   DEVNET_NAME,
            "location": location,
        })

    return jobs


def scrape_devnet():
    print(f"\n[{DEVNET_NAME}] Fetching jobs...")
    try:
        content = fetch_page(DEVNET_URL)
        jobs    = parse_devnet_page(content)
        print(f"[{DEVNET_NAME}] {len(jobs)} Delhi/Bangalore jobs found.")
        return jobs
    except Exception as e:
        print(f"[{DEVNET_NAME}] Error: {e}")
        return []


# ─── SOURCE 4: ATHENA INFONOMICS ──────────────────────────────────────────────
# India-based policy/development consulting firm. Server-rendered careers page.
# Filter to Delhi / Bangalore roles only.

ATHENA_NAME = "Athena Infonomics"
ATHENA_URL  = "https://www.athenainfonomics.com/careers"
ATHENA_BASE = "https://www.athenainfonomics.com"


def scrape_athena():
    print(f"\n[{ATHENA_NAME}] Fetching jobs...")
    jobs = []
    try:
        content = fetch_page(ATHENA_URL)

        # Split on each job-cards block (more robust than a single greedy regex)
        title_re    = re.compile(r'class="h4-semibold white">\s*([^<]+?)\s*<', re.IGNORECASE)
        location_re = re.compile(r'class="h6-alternate white">\s*([^<]+?)\s*<', re.IGNORECASE)
        link_re     = re.compile(r'href="(/jobs/[^"]+)"', re.IGNORECASE)

        blocks = re.split(r'(?=<div[^>]*class="job-cards")', content)

        for block in blocks[1:]:
            tm = title_re.search(block)
            if not tm:
                continue
            title = html.unescape(tm.group(1).strip())

            # Location is the 2nd match of h6-alternate (1st is employment type)
            locs = location_re.findall(block)
            location = html.unescape(locs[1].strip()) if len(locs) > 1 else ""

            loc_lower = location.lower()
            if not any(city in loc_lower for city in DELHI_BANGALORE) and "india" not in loc_lower:
                continue

            lm = link_re.search(block)
            url = f"{ATHENA_BASE}{lm.group(1)}" if lm else ATHENA_URL

            jobs.append({
                "title":   title,
                "url":     url,
                "org":     ATHENA_NAME,
                "updated": "",
                "source":  ATHENA_NAME,
            })

        print(f"[{ATHENA_NAME}] {len(jobs)} India jobs found.")
    except Exception as e:
        print(f"[{ATHENA_NAME}] Error: {e}")
    return jobs


# ─── SOURCE 5: IMPACTPOOL.ORG ─────────────────────────────────────────────────
# Searches for CV-relevant terms across FAO, WFP, IFAD, World Bank, CGIAR etc.
# Filters to India-based roles OR globally-relevant roles from key agri orgs.

IMPACTPOOL_NAME = "Impactpool"
IMPACTPOOL_BASE = "https://www.impactpool.org"

# Search queries — Bangalore-first, then Delhi, then broader India
IMPACTPOOL_QUERIES = [
    # Bangalore-specific
    "agriculture policy bangalore",
    "food security consultant bengaluru",
    "rural development karnataka",
    "sustainability bangalore india",
    # Delhi / broader India
    "agriculture food policy india",
    "fisheries rural development india",
    "trade export agricultural india",
    "food security nutrition india",
    "agribusiness value chain india",
    "trade facilitation india",
    "food systems livelihoods india",
    "horticulture crop india",
    "agricultural finance rural india",
    # Org-targeted
    "world bank agriculture india",
    "ADB asian development bank agriculture",
    "GIZ india agriculture rural",
    "IFC india agriculture food",
    "ITC international trade centre india",
    "CGIAR india research",
    "ICRISAT india agriculture",
    "IFAD india rural livelihoods",
    "FAO india food agriculture",
    "USAID india agriculture",
    # German cooperation and Bangalore/Karnataka policy roles
    "GIZ bangalore", "GIZ india policy", "KfW india", "DAAD india",
    "german development cooperation india", "ICRISAT bangalore",
    "public policy bangalore", "policy karnataka government",
    "government advisory bangalore", "policy manager bangalore",
    # UN-agency sweep — replaces the coverage lost when unjobs.org went behind
    # a Cloudflare challenge on 27 Aug 2026. unjobs.org had been supplying ~49
    # Delhi/Bangalore UN roles a run; Impactpool aggregates the same agencies.
    "UNDP india", "UNICEF india", "WFP india", "UN women india",
    "UNESCO india", "UNIDO india", "IOM india", "ILO india",
    "UNEP india", "UNOPS india", "united nations india",
    "united nations new delhi", "united nations bangalore",
    "UN volunteer india", "UNFPA india",
    # Sustainability-standards and trade-promotion bodies (role families 7–8)
    "rainforest alliance india", "solidaridad india", "IDH india",
    "fairtrade india", "WWF india agriculture", "trade promotion india",
]

# Orgs whose jobs are always relevant regardless of location
PRIORITY_ORGS = [
    "fao", "ifad", "wfp", "world food programme", "world bank", "cgiar",
    "icrisat", "irri", "cimmyt", "cip", "icar", "ilri", "iwmi",
    "undp", "unep", "ifpri", "ifc", "adb", "giz", "usaid",
    "asian development bank", "international trade centre", "itc",
]

# Location filter: Bangalore-first, then Delhi NCR
DELHI_BANGALORE = [
    "bangalore", "bengaluru", "karnataka",
    "delhi", "new delhi", "gurugram", "gurgaon", "noida", "ncr",
    "hyderabad",  # ICRISAT/IRRI/ICMR research orgs
    "telangana", "chennai", "tamil nadu", "kochi", "kerala", "thiruvananthapuram",
    "coimbatore", "mysuru", "mysore",
]


def parse_impactpool_page(html_content):
    """Parse job listings from Impactpool search results.

    Actual structure:
      <div class='job'>
        <div class='extra'>...</div>
        <a data-turbo-frame="_top" href="/jobs/ID">
          <div class='ip-typography' type='cardTitle'>TITLE</div>
          <div class='ip-layout' ...>
            <div class='ip-typography' type='bodyEmphasis'>ORG <img/></div>
            <div class='ip-layout' ...>
              <div class='ip-typography' type='bodyEmphasis'>LOCATION</div>
            </div>
          </div>
        </a>
      </div>
    """
    jobs = []

    def strip_tags(s):
        return re.sub(r'<[^>]+>', '', s).strip()

    # Each job block: <div class='job'>...</a></div>
    # We split on the opening tag and grab until </a></div>
    blocks = re.split(r"(?=<div class='job'>)", html_content)

    link_re  = re.compile(r'href="(/jobs/(\d+))"', re.IGNORECASE)
    # Titles moved from <div> to <h3> in the Oct 2026 redesign — accept both.
    title_re = re.compile(r"type='cardTitle'[^>]*>\s*([^<]+?)\s*</(?:div|h3)>", re.IGNORECASE)
    body_re  = re.compile(r"type='bodyEmphasis'[^>]*>(.*?)</div>", re.IGNORECASE | re.DOTALL)

    for block in blocks:
        if not block.startswith("<div class='job'>"):
            continue

        lm = link_re.search(block)
        if not lm:
            continue
        path = lm.group(1)

        tm = title_re.search(block)
        if not tm:
            continue
        title = html.unescape(tm.group(1).strip())
        if len(title) < 5:
            continue

        body_matches = body_re.findall(block)
        org      = html.unescape(strip_tags(body_matches[0])) if len(body_matches) > 0 else "Unknown"
        location = html.unescape(strip_tags(body_matches[1])) if len(body_matches) > 1 else ""

        # Strict India-only filter: location must mention India, Delhi, or Bangalore
        loc_lower = location.lower()
        in_india  = any(city in loc_lower for city in DELHI_BANGALORE) or "india" in loc_lower

        if not in_india:
            continue

        jobs.append({
            "title":    title,
            "url":      f"{IMPACTPOOL_BASE}{path}",
            "org":      org,
            "updated":  "",
            "source":   IMPACTPOOL_NAME,
            "location": location,
        })

    return jobs


def get_impactpool_pages(html_content):
    m = re.search(r'(\d+)\s+jobs?\s+match', html_content, re.IGNORECASE)
    if m:
        total = int(m.group(1))
        return max(1, (total + 39) // 40)
    return 1


def scrape_impactpool():
    print(f"\n[{IMPACTPOOL_NAME}] Fetching jobs...")
    all_jobs = []
    seen_urls = set()

    for query in IMPACTPOOL_QUERIES:
        q_encoded = urllib.parse.quote_plus(query)
        base = f"{IMPACTPOOL_BASE}/search?q={q_encoded}&per_page=40"

        try:
            first   = fetch_page(f"{base}&page=1")
            pages   = min(get_impactpool_pages(first), 3)  # max 3 pages per query
            jobs    = parse_impactpool_page(first)

            for page in range(2, pages + 1):
                try:
                    content = fetch_page(f"{base}&page={page}")
                    jobs.extend(parse_impactpool_page(content))
                except Exception as e:
                    print(f"  [{IMPACTPOOL_NAME}] Error page {page}: {e}")

            # Deduplicate across queries
            for job in jobs:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    all_jobs.append(job)

        except Exception as e:
            print(f"  [{IMPACTPOOL_NAME}] Error query '{query}': {e}")

    print(f"[{IMPACTPOOL_NAME}] {len(all_jobs)} relevant jobs found.")
    return all_jobs


# ─── SOURCE 6: RELIEFWEB.INT ──────────────────────────────────────────────────
# The JSON API is gated: v1 returns 410 Gone (decommissioned) and v2 returns
# 403 "You are not using an approved appname" for any unregistered name, which
# only ReliefWeb staff can grant. The public jobs river is server-rendered and
# needs no key, so we parse that instead.
# advanced-search=(C119) is ReliefWeb's country filter for India.

RELIEFWEB_NAME  = "ReliefWeb"
RELIEFWEB_URL   = "https://reliefweb.int/jobs?advanced-search=%28C119%29"
RELIEFWEB_PAGES = 3

_RW_ARTICLE = re.compile(r'<article[^>]*rw-river-article--job[^>]*>(.*?)</article>', re.DOTALL | re.IGNORECASE)
_RW_TITLE   = re.compile(r'class="rw-river-article__title"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
_RW_ORG     = re.compile(r'tag-value--source.*?<a[^>]*class="rw-entity-meta__tag-link"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
_RW_COUNTRY = re.compile(r'rw-entity-country-slug__link"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
_RW_DATE    = re.compile(r'datetime="(\d{4}-\d{2}-\d{2})', re.IGNORECASE)


def _rw_clean(raw):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', raw or ''))).strip()


def scrape_reliefweb():
    """Fetch India-based development jobs from the ReliefWeb jobs river."""
    print(f"\n[{RELIEFWEB_NAME}] Fetching jobs...")
    jobs, seen = [], set()
    try:
        for page in range(RELIEFWEB_PAGES):
            url = RELIEFWEB_URL if page == 0 else f"{RELIEFWEB_URL}&page={page}"
            content  = fetch_page(url)
            articles = _RW_ARTICLE.findall(content)
            if not articles:
                if page == 0:
                    # Since Oct 2026 the jobs river sits behind an AWS WAF
                    # JavaScript challenge (HTTP 202, empty body, header
                    # x-amzn-waf-action: challenge) that urllib cannot — and
                    # should not — solve. Say so instead of reporting a quiet 0.
                    print(f"[{RELIEFWEB_NAME}] BLOCKED: bot challenge, no listings returned "
                          f"(ReliefWeb roles are mostly cross-posted on Impactpool/LinkedIn).")
                break

            for art in articles:
                tm = _RW_TITLE.search(art)
                if not tm:
                    continue
                job_url = tm.group(1)
                title   = _rw_clean(tm.group(2))
                if not title or job_url in seen:
                    continue
                seen.add(job_url)

                om = _RW_ORG.search(art)
                cm = _RW_COUNTRY.search(art)
                dm = _RW_DATE.search(art)   # first date on a card is "posted"

                jobs.append({
                    "title":    title,
                    "url":      job_url,
                    "org":      _rw_clean(om.group(1)) if om else "Unknown",
                    "updated":  dm.group(1) if dm else "",
                    "source":   RELIEFWEB_NAME,
                    "location": _rw_clean(cm.group(1)) if cm else "India",
                })

            if len(articles) < 20:      # short page = last page
                break

        print(f"[{RELIEFWEB_NAME}] {len(jobs)} India jobs found.")
    except Exception as e:
        print(f"[{RELIEFWEB_NAME}] Error: {e}")
    return jobs


# ─── SOURCE 7: DEVNETJOBS.ORG (GLOBAL) ────────────────────────────────────────
# Global development sector jobs — server-rendered ASP.NET, no JS needed.
# Naukri replaced with this: Naukri is fully client-side JS (Next.js) and
# requires a browser session to access their internal API.
# This source filters for India-based roles only.

DEVNETGLOBAL_NAME = "DevNetJobs Global"
DEVNETGLOBAL_URL  = "https://www.devnetjobs.org/standard_jobs.aspx"


def parse_devnetglobal_page(html_content):
    jobs = []
    # Markup was reskinned: jobSeparator -> standardJobSeparator and the title
    # is no longer a bare .fw-bold span. Anchor on the ASP.NET control ids
    # (lblJobTitle / lblJobCo / lblLocation), which survived the redesign.
    blocks = re.split(r'(?=<div[^>]*class="[^"]*standardJobSeparator[^"]*")', html_content)

    link_re  = re.compile(r'href="(https://devnetjobs\.org/jobdescription\.aspx\?job_id=\d+)"', re.IGNORECASE)
    title_re = re.compile(r'id="[^"]*lblJobTitle"[^>]*>\s*([^<]+?)\s*</span>', re.IGNORECASE)
    org_re   = re.compile(r'id="[^"]*lblJobCo"[^>]*>\s*([^<]+?)\s*</span>', re.IGNORECASE)
    loc_re   = re.compile(r'id="[^"]*lblLocation"[^>]*>\s*Location:\s*([^<]+?)\s*</span>', re.IGNORECASE)

    for block in blocks[1:]:
        lm = link_re.search(block)
        if not lm:
            continue
        job_url = lm.group(1)

        tm = title_re.search(block)
        if not tm:
            continue
        title = html.unescape(tm.group(1).strip())

        om  = org_re.search(block)
        org = html.unescape(om.group(1).strip()) if om else "Unknown"

        locm     = loc_re.search(block)
        location = html.unescape(locm.group(1).strip()) if locm else ""

        if "india" not in location.lower():
            continue

        jobs.append({
            "title":    title,
            "url":      job_url,
            "org":      org,
            "updated":  "",
            "source":   DEVNETGLOBAL_NAME,
            "location": location,
        })

    return jobs


def scrape_devnetglobal():
    print(f"\n[{DEVNETGLOBAL_NAME}] Fetching jobs...")
    try:
        content = fetch_page(DEVNETGLOBAL_URL)
        jobs    = parse_devnetglobal_page(content)
        print(f"[{DEVNETGLOBAL_NAME}] {len(jobs)} India jobs found.")
        return jobs
    except Exception as e:
        print(f"[{DEVNETGLOBAL_NAME}] Error: {e}")
        return []


# ─── SOURCE 8: JOBSHOBNEST ────────────────────────────────────────────────────
# CSR & social sector job platform ("Where Passion Meets Purpose").
# Uses a private but unauthenticated JSON API discovered in their JS bundle.
# Covers UN, NGO, CSR, development roles — Delhi, Bangalore, Remote.
# Salary field included so pay can be judged at a glance.

JOBSHOBNEST_NAME = "JobShobNest"
# Backend moved off the AWS App Runner host (its DNS no longer resolves)
JOBSHOBNEST_API  = "https://api.jobshobnest.com/api/v1/app/jobs?status=active"
JOBSHOBNEST_BASE = "https://jobshobnest.com/job"

# Include these locations; everything else (Mumbai, Bhubaneswar, etc.) is skipped
JOBSHOBNEST_LOCS = [
    "bangalore", "bengaluru", "karnataka",
    "delhi", "new delhi", "ncr", "gurugram", "noida",
    "remote", "pan india", "india",
    "hyderabad", "chennai", "kochi", "kerala", "tamil nadu", "telangana",
    "coimbatore", "mysuru", "mysore", "thiruvananthapuram",
]


def _parse_salary_lpa(salary_str):
    """Return approximate LPA float, or None if unknown/unclear."""
    if not salary_str:
        return None
    s = salary_str.lower().strip()
    # Vague strings — treat as unknown (include the job)
    if any(x in s for x in ["as per", "competitive", "market", "norms", "grade", "p 3", "p3", "g 5", "g5"]):
        return None
    # "18-24 LPA" or "23 LPA"
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:to|-|\s+)?\d*\s*lpa', s)
    if m:
        return float(m.group(1))
    # "12 - 15 lakh"
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:to|-|\s+)?\d*\s*lakh', s)
    if m:
        return float(m.group(1))
    # Numeric amounts: if ≥ 5,00,000 treat as annual; if ≥ 10,000 treat as monthly
    nums = re.findall(r'[\d,]+(?:\.\d+)?', s)
    if nums:
        n = float(nums[0].replace(",", ""))
        if n >= 500000:
            return round(n / 100000, 1)
        if n >= 10000:
            return round((n * 12) / 100000, 1)
    return None


def scrape_jobshobnest():
    print(f"\n[{JOBSHOBNEST_NAME}] Fetching jobs...")
    jobs = []
    try:
        content = fetch_page(JOBSHOBNEST_API)
        data    = json.loads(content)

        for item in (data.get("data") or {}).get("jobs", []):
            title    = (item.get("role") or "").strip()
            org      = (item.get("organization_title") or "").strip()
            location = (item.get("location") or "").strip()
            salary   = (item.get("salary") or "").strip()
            job_url  = (item.get("apply_link") or "").strip()
            posted   = (item.get("posted_on") or "")[:10]
            job_id   = item.get("id", "")

            if not title or not job_url:
                continue

            # Location filter — Delhi, Bangalore, Remote, PAN India only
            loc_lower = location.lower()
            if not any(x in loc_lower for x in JOBSHOBNEST_LOCS):
                continue

            # Salary filter — skip jobs clearly below 8 LPA
            lpa = _parse_salary_lpa(salary)
            if lpa is not None and lpa < 8:
                continue

            # Attach salary to location string so it shows in the alert
            display_loc = location
            if salary:
                display_loc = f"{location} · {salary}"

            jobs.append({
                "title":    title,
                "url":      job_url,
                "org":      org or "Unknown",
                "updated":  posted,
                "source":   JOBSHOBNEST_NAME,
                "location": display_loc,
            })

        print(f"[{JOBSHOBNEST_NAME}] {len(jobs)} Delhi/Bangalore/Remote jobs found.")
    except Exception as e:
        print(f"[{JOBSHOBNEST_NAME}] Error: {e}")
    return jobs


# ─── SOURCE 10: ATREE (BANGALORE) ─────────────────────────────────────────────
# Ashoka Trust for Research in Ecology and the Environment — Bangalore-based
# research org. Ecology, watershed, livelihoods, conservation jobs.
# Server-rendered WordPress + Elementor — no JS needed.

ATREE_NAME = "ATREE Bangalore"
ATREE_URL  = "https://www.atree.org/careers/"


def scrape_atree():
    print(f"\n[{ATREE_NAME}] Fetching jobs...")
    jobs = []
    try:
        content  = fetch_page(ATREE_URL)
        link_re  = re.compile(r'href="(https://www\.atree\.org/career/[^"]+)"', re.IGNORECASE)
        title_re = re.compile(r'class="elementor-heading-title[^"]*"[^>]*>\s*<a[^>]*>\s*([^<]+?)\s*</a>', re.IGNORECASE)

        links  = link_re.findall(content)
        titles = title_re.findall(content)

        for i, job_url in enumerate(links):
            title = html.unescape(titles[i].strip()) if i < len(titles) else ""
            if not title or len(title) < 5:
                continue
            jobs.append({
                "title":    title,
                "url":      job_url,
                "org":      "ATREE",
                "updated":  "",
                "source":   ATREE_NAME,
                "location": "Bangalore",
            })

        print(f"[{ATREE_NAME}] {len(jobs)} jobs found.")
    except Exception as e:
        print(f"[{ATREE_NAME}] Error: {e}")
    return jobs


# ─── SOURCE 11: SELCO FOUNDATION (BANGALORE) ──────────────────────────────────
# SELCO Foundation — Bangalore-based development org focused on sustainable
# energy, livelihoods, agri, and rural development. Very relevant to CV.
# Server-rendered WordPress — no JS needed.

SELCO_NAME = "SELCO Foundation"
SELCO_URL  = "https://selcofoundation.org/careers/"


def scrape_selco():
    print(f"\n[{SELCO_NAME}] Fetching jobs...")
    jobs = []
    try:
        content  = fetch_page(SELCO_URL)
        blocks   = re.split(r'(?=<div[^>]*class="career-div")', content)
        link_re  = re.compile(r'href="(https://selcofoundation\.org/careers/[^"]+)"', re.IGNORECASE)
        title_re = re.compile(r'<h3>\s*<a[^>]*>\s*([^<]+?)\s*</a>\s*</h3>', re.IGNORECASE)
        loc_re   = re.compile(r'</h3>\s*<p>\s*([^<]+?)\s*</p>', re.IGNORECASE)

        seen = set()
        for block in blocks[1:]:
            lm = link_re.search(block)
            if not lm:
                continue
            job_url = lm.group(1)
            if job_url in seen or job_url == SELCO_URL:
                continue
            seen.add(job_url)

            tm = title_re.search(block)
            if not tm:
                continue
            title = html.unescape(tm.group(1).strip())

            locm     = loc_re.search(block)
            location = html.unescape(locm.group(1).strip()) if locm else "Bangalore"

            jobs.append({
                "title":    title,
                "url":      job_url,
                "org":      SELCO_NAME,
                "updated":  "",
                "source":   SELCO_NAME,
                "location": location if location else "India",
            })

        print(f"[{SELCO_NAME}] {len(jobs)} jobs found.")
    except Exception as e:
        print(f"[{SELCO_NAME}] Error: {e}")
    return jobs


# ─── SOURCE: UNDP JOBS ────────────────────────────────────────────────────────
# jobs.undp.org renders every vacancy server-side as a table row whose CSS class
# carries an ISO country code (country_IND), so India roles can be picked out
# without a search call. Each row links to UNDP's Oracle hiring site.

UNDP_NAME = "UNDP Jobs"
UNDP_URL  = "https://jobs.undp.org/cj_view_jobs.cfm"

_UNDP_ROW  = re.compile(
    r'<a href="(https://[^"]*requisitions/job/\d+)"\s+class="vacanciesTableLink[^"]*?country_(\w+)[^"]*"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE)
_UNDP_SPAN = re.compile(r'<span[^>]*>([^<]+)</span>', re.IGNORECASE)


def parse_undp_page(content):
    jobs, seen = [], set()
    for url, country, body in _UNDP_ROW.findall(content):
        spans = [html.unescape(s).strip() for s in _UNDP_SPAN.findall(body) if s.strip()]
        # spans: title, post level, apply-by, agency, location (apply-by may be nested)
        location = spans[-1] if len(spans) >= 4 else ""
        if url in seen or not spans or not (country.upper() == "IND" or "india" in location.lower()):
            continue
        seen.add(url)
        location = location or "India"
        jobs.append({
            "title":    spans[0],
            "url":      url,
            "org":      "UNDP",
            "updated":  "",
            "source":   UNDP_NAME,
            "location": location if "india" in location.lower() else f"{location}, India",
        })
    return jobs


def scrape_undp():
    print(f"\n[{UNDP_NAME}] Fetching jobs...")
    try:
        jobs = parse_undp_page(fetch_page(UNDP_URL))
        print(f"[{UNDP_NAME}] {len(jobs)} India jobs found.")
        return jobs
    except Exception as e:
        print(f"[{UNDP_NAME}] Error: {e}")
        return []


# ─── SOURCE 13: GOVERNMENT BODIES ─────────────────────────────────────────────
# Ministries and boards hire contractual consultants and Young Professionals —
# by posting notices (usually PDFs) on
# their own vacancy pages, never on job boards. Each page is read for links
# whose text looks like a vacancy, from the current year, minus the results,
# corrigenda, tenders and clerical posts that share those pages.
#
# Not covered, because their pages are built with JavaScript: APEDA, ICAR,
# Invest India, NCEL, NABARD and the Karnataka department sites (KAPPEC,
# Sanjeevini, Watershed, Horticulture). Coffee Board's page errors out and
# NIRDPR's portal lists no openings in a parseable form.

GOV_SOURCES = [
    # (name, vacancy page, location)
    ("NITI Aayog",   "https://www.niti.gov.in/work-niti/vacancy-circular",  "New Delhi"),
    ("NABCONS",      "https://www.nabcons.com/career",                      "New Delhi"),
    ("SFAC",         "https://sfacindia.com/VacancyNotice.aspx",            "New Delhi"),
    ("Ministry of Food Processing Industries", "https://www.mofpi.gov.in/en/careers", "New Delhi"),
    ("MANAGE (National Institute of Agricultural Extension Management)",
                     "https://www.manage.gov.in/vacancies/vacancies.asp",   "Hyderabad"),
    ("MPEDA",        "https://mpeda.gov.in/",                               "Kochi"),
    ("Spices Board", "https://www.indianspices.com/opportunities.html",     "Kochi"),
]
GOV_NAME = "Govt"

_GOV_LINK   = re.compile(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_GOV_NOTICE = re.compile(
    r'consultant|young professional|vacanc|recruit|engagement|advertisement|'
    r'notification for|walk[- ]in|post of|position of|positions of|fellow|'
    r'contract(ual)? basis|applications? (are )?invited|hiring', re.IGNORECASE)
_GOV_NOISE  = re.compile(
    r'result|shortlist|short-list|corrigendum|addendum|answer key|rank list|'
    r'admit card|hall ticket|schedule|marks|selected|selection list|merit|'
    r'cancel|extension|extended|postpone|tender|quotation|\brfp\b|\beoi\b|'
    r'archive|recruitment rules|guideline|internship|calendar|venue|syllabus|'
    r'deputation|steno|clerk|\budc\b|\bldc\b|\bmts\b|multi[- ]tasking|'
    r'driver|peon|attendant|technical assistant|laborator|instructor|'
    r'trainees?|lab assistant|system analyst|\(it\)|teaching',
    re.IGNORECASE)


_GOV_DATE = re.compile(r'\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b')


def _gov_expired(text):
    """True when every dd-mm-yyyy date near the notice is already past."""
    dates = []
    for d, mth, y in _GOV_DATE.findall(text):
        try:
            dates.append(datetime(int(y), int(mth), int(d)))
        except ValueError:
            pass
    return bool(dates) and max(dates) < datetime.now()


def _gov_years():
    """Current year, plus last year during January–February."""
    now = datetime.now()
    return {str(now.year)} | ({str(now.year - 1)} if now.month <= 2 else set())


def scrape_government():
    print(f"\n[{GOV_NAME}] Fetching vacancy pages...")
    jobs, seen = [], set()
    years = _gov_years()
    for name, url, location in GOV_SOURCES:
        try:
            content = fetch_page(url)
        except Exception as e:
            print(f"  [{GOV_NAME}] {name}: {e}")
            continue
        found = 0
        for m in _GOV_LINK.finditer(content):
            href, raw = m.groups()
            title = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', raw))).strip()
            if len(title) < 20 or not _GOV_NOTICE.search(title) or _GOV_NOISE.search(title):
                continue
            # Recency: the year must appear in the link, its file name, or the
            # "last date" text that follows it on the page.
            near = title + " " + href + " " + content[m.end():m.end() + 200]
            if not any(y in near for y in years) or _gov_expired(near):
                continue
            job_url = urllib.parse.urljoin(url, href.strip())
            if job_url in seen:
                continue
            seen.add(job_url)
            found += 1
            jobs.append({
                "title":    title[:160],
                "url":      job_url,
                "org":      name,
                "updated":  "",
                "source":   GOV_NAME,
                "location": location,
            })
        print(f"  [{GOV_NAME}] {name}: {found} current notice(s)")
    print(f"[{GOV_NAME}] {len(jobs)} government vacancies found.")
    return jobs


# ─── SOURCE 14: FREEJOBALERT (GOVERNMENT AGGREGATOR) ──────────────────────────
# Aggregates notices from bodies whose own sites cannot be read (Karnataka
# departments and missions, ICAR institutes, agricultural universities, NABARD).
# Mostly exams and clerical posts, so rows are kept only when the post looks
# like a policy / agri / programme role; NON_FIT_TITLE and Gemini filter next.

FJA_NAME    = "FreeJobAlert"
FJA_SOURCES = [
    ("https://www.freejobalert.com/karnataka-government-jobs/",     "Karnataka"),
    # All-India feed — regular (permanent) posts as well as contract ones,
    # e.g. APEDA Director / Secretary, NABARD, NABCONS PMU Lead
    ("https://www.freejobalert.com/latest-notifications/",          "India"),
    ("https://www.freejobalert.com/delhi-government-jobs/",         "New Delhi"),
    ("https://www.freejobalert.com/government-jobs-without-exams/", "India"),
]
# A post must name the profile's domain, in the post or the employer — generic
# "Project Associate" / "Consultant" rows from IITs and DRDO are dropped.
_FJA_RELEVANT = re.compile(
    r'agri|horticult|fisher|aquacult|dairy|livestock|cooperat|co-operat|food|'
    r'rural|livelihood|nrlm|watershed|krishi|\bkvk\b|icar|nabard|nabcons|seed|'
    r'policy|economi|trade|export|dgft|apeda|mpeda|spices|coffee board|tea board|'
    r'niti|planning|\biim|tiss|irma|manage\b|nirdpr|\buas|\bsfac|ncdc|nafed',
    re.IGNORECASE)
# Student fellowships and clerical posts that share these pages
_FJA_NOISE = re.compile(
    r'research fellow|\bjrf\b|\bsrf\b|post[- ]?doc|typist|process server|'
    r'programmer|field investigat|library|tradesman|home guard|cyber|'
    r'soc analyst|security analyst|field operator', re.IGNORECASE)


def scrape_freejobalert():
    print(f"\n[{FJA_NAME}] Fetching government listings...")
    jobs, seen = [], set()
    for url, location in FJA_SOURCES:
        try:
            content = fetch_page(url)
        except Exception as e:
            print(f"  [{FJA_NAME}] {url}: {e}")
            continue
        found = 0
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL):
            lm = re.search(r'href="(https://www\.freejobalert\.com/articles/[^"]+)"', row)
            if not lm or lm.group(1) in seen:
                continue
            cells = [re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', c))).strip()
                     for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)]
            if len(cells) >= 7:      # date | "ORG Vacancy 2026 - ..." | post | count | qual | last date | link
                org = re.split(r'\s+Vacancy\b', cells[1])[0]
                post = re.sub(r'\s*[–-]\s*\d+\s+Posts?$', '', cells[2])
            elif len(cells) >= 4:    # org | "post - N Vacancies" | last date | link
                org, post = cells[0], re.sub(r'\s*-\s*\d+\s+Vacanc\w*$', '', cells[1])
            else:
                continue
            if (not _FJA_RELEVANT.search(post + " " + org) or _FJA_NOISE.search(post)
                    or _GOV_NOISE.search(post) or _gov_expired(" ".join(cells))):
                continue
            seen.add(lm.group(1))
            found += 1
            jobs.append({
                "title":    post[:160],
                "url":      lm.group(1),
                "org":      org[:120],
                "updated":  "",
                "source":   FJA_NAME,
                "location": location,
            })
        print(f"  [{FJA_NAME}] {location}: {found} relevant open post(s)")
    print(f"[{FJA_NAME}] {len(jobs)} government listings kept.")
    return jobs


# ─── SOURCE 15: LINKEDIN COMPANY FOLLOW-LIST ──────────────────────────────────
# LinkedIn shows company posts only to logged-in users, and its company-ID
# filter is ignored for guests — but a keyword search on the company name,
# kept to cards whose employer matches, returns that company's openings.
# Add employers here to "follow" them. Huge employers (Deloitte, Amazon) are
# left out: their names return thousands of unrelated roles.

LINKEDIN_COMPANIES = [
    # 1 Food / grocery policy teams
    "Zepto", "Swiggy", "BigBasket", "Licious", "Country Delight",
    # 2 Agri-commodity and agritech
    "Cargill", "ofi", "Syngenta", "DeHaat", "Ninjacart", "Cropin", "Samunnati", "Arya.ag",
    # 3 Government advisory
    "IPE Global", "Sattva Consulting", "Grant Thornton Bharat", "Dalberg", "IDinsight",
    # 5 Think tanks and institutes
    "CEEW", "WRI India", "Indian Institute for Human Settlements", "Precision Development",
    "Azim Premji Foundation", "The/Nudge",
    # 6 Development and bilateral agencies
    "GIZ", "Gates Foundation", "Tata Trusts", "Digital Green",
    # 7 Trade promotion
    "Invest India", "FICCI", "Confederation of Indian Industry", "Indo-German Chamber of Commerce",
    # 8 Sustainability standards
    "Solidaridad", "Rainforest Alliance", "IDH", "Control Union", "Fairtrade",
]
LINKEDIN_COMPANY_PAGES = 2


def _company_match(company, org):
    c = re.sub(r'[^a-z0-9 ]', ' ', company.lower()).split()
    o = " " + re.sub(r'[^a-z0-9 ]', ' ', (org or "").lower()) + " "
    return all(f" {w} " in o for w in c)


def scrape_linkedin_companies():
    name = f"{LINKEDIN_NAME} follow-list"
    print(f"\n[{name}] Fetching openings at {len(LINKEDIN_COMPANIES)} employers...")
    jobs, seen = [], set()
    for company in LINKEDIN_COMPANIES:
        kept = 0
        for page in range(LINKEDIN_COMPANY_PAGES):
            params = urllib.parse.urlencode({
                "keywords": company, "location": "India",
                "f_TPR": LINKEDIN_TPR, "start": page * 10,
            })
            time.sleep(LINKEDIN_DELAY_SECS)
            content = None
            for attempt in range(2):
                try:
                    content = fetch_page(f"{LINKEDIN_API}?{params}")
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 429 and attempt == 0:
                        time.sleep(LINKEDIN_429_BACKOFF)
                        continue
                    break
                except Exception:
                    break
            if content is None:
                break
            page_jobs = _parse_linkedin_page(content)
            for job in page_jobs:
                if job["url"] in seen or not _company_match(company, job["org"]):
                    continue
                seen.add(job["url"])
                jobs.append(job)
                kept += 1
            if len(page_jobs) < 10:
                break
        if kept:
            print(f"  [{name}] {company}: {kept}")
    print(f"[{name}] {len(jobs)} openings found.")
    return jobs


# ─── SOURCE 12: LINKEDIN (BANGALORE-FIRST) ────────────────────────────────────
# LinkedIn's public "jobs-guest" search endpoint — the same data the logged-out
# job search page shows. Returns server-rendered HTML cards, 10 per page.
# No login/cookies used. LinkedIn rate-limits aggressively, so queries are
# spaced out and capped; a 429 aborts the remaining pages for that query.

LINKEDIN_NAME = "LinkedIn"
LINKEDIN_API  = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Bangalore is the priority — it gets the full keyword sweep.
LINKEDIN_BLR_QUERIES = [
    "agriculture", "agribusiness", "agritech", "food security",
    "food policy", "agriculture policy", "trade policy", "value chain",
    "rural livelihoods", "public policy analyst", "policy consultant",
    "development sector", "farmer producer organization", "climate agriculture",
    # Agricultural trade & export policy.
    # Deliberately not "logistics"/"freight"/"supply chain": those queries
    # returned shipping and warehouse roles, not agri-trade policy.
    # "import export", "EXIM", "commodity trading" and "export trade" were
    # dropped: in Bengaluru they return only corporate trade-compliance and
    # logistics desks, every one of which the filter then rejected — wasted
    # requests that pushed the run into LinkedIn's rate limit.
    "agricultural export", "export policy", "agri commodity",
    "agricultural economist", "trade policy analyst", "export promotion",
    # Bangalore's agri market is agritech, agri-food corporates, dairy and
    # plantations, livelihoods NGOs and policy institutes — search for them.
    "agtech", "agri value chain", "market linkages farmers", "agri sourcing",
    "commodity research analyst", "dairy", "plantation", "natural farming",
    "rural development", "climate resilience", "food systems",
    "policy research associate", "research associate agriculture",
    "think tank", "CSR programme manager", "partnerships manager development",
    "sustainable sourcing", "agri finance", "agriculture consultant",
    # Karnataka state government, PMUs and policy fellowships
    "government of karnataka", "karnataka government consultant",
    "state government consultant", "PMU consultant", "government advisory",
    "public sector consulting", "policy fellow", "e-governance consultant",
    "public policy consultant", "state planning", "KAPPEC",
    # Development-sector role titles — these carry the profile even when
    # the title has no agriculture word in it.
    "livelihoods", "monitoring evaluation", "impact assessment",
    "development consultant", "research fellow policy", "programme manager NGO",
    "social impact consultant", "public policy research",
    # Embassy / bilateral / government-relations roles.
    "programme officer embassy", "government relations", "public affairs",
    "development cooperation", "bilateral cooperation", "policy advisor",
    "programme manager development", "sector advisor", "government affairs",
    # Policy teams at Bangalore tech / quick-commerce / food companies
    "corporate affairs", "external affairs", "regulatory affairs food",
    "policy government affairs",
    # Policy-making roles across government, public and private sector — the
    # private side is public-policy / regulatory / government-affairs teams.
    "public policy manager", "policy manager", "regulatory affairs policy",
    "policy lead", "policy analyst", "policy research", "economic policy",
    "agri policy", "trade and policy", "policy and advocacy",
    # The eight target role families (Nov 2026). Already-covered ones (public
    # policy, PMU, Karnataka government, think tanks) are above.
    # 1 Food / grocery company policy teams
    "food policy manager", "FSSAI regulatory", "government affairs food",
    # 2 Agri-commodity & agritech strategy / partnerships
    "government partnerships", "market access agriculture", "agri partnerships",
    # 3 Government advisory consulting
    "government and public services consultant", "PMU agriculture",
    "public sector advisory agriculture",
    # 6 Development & bilateral agencies
    "programme officer agriculture", "technical expert agriculture",
    "technical advisor agriculture",
    # 7 Trade-promotion offices and chambers
    "trade advisor", "trade commissioner", "trade promotion",
    "investment promotion", "consulate trade", "Indo-German chamber",
    "business development consulate",
    # 8 Sustainability standards & certification
    "sustainability standards", "traceability agriculture",
    "responsible sourcing", "certification programme manager", "ESG agriculture",
    # 9 Business development, strategy and partnerships in the profile's sectors
    "business development agriculture", "business development agritech",
    "business development food", "business development export",
    "government business development", "strategy manager agritech",
    "strategy manager food", "chief of staff impact", "founder's office agritech",
    "partnerships manager agriculture", "business development development sector",
    # 10 Strategy / BD / partnerships at reputable private employers in Bengaluru
    "corporate strategy manager", "strategy and planning manager",
    "business development manager government", "partnerships manager",
    "chief of staff", "government relations manager",
    "public sector consulting manager", "strategy consultant",
    # Germany-linked employers: only "GIZ" is searched here — LinkedIn matches
    # "DAAD" / "Indo-German" / "KfW" loosely and returned IT and sales noise.
    # Those employers are caught by Impactpool queries and by the org lists.
    "GIZ",
]

# Delhi NCR keeps a lighter sweep — the UN/Delhi pipeline is already well fed
# by unjobs.org, Impactpool and ReliefWeb.
LINKEDIN_DEL_QUERIES = [
    "agriculture policy", "food security", "trade policy", "agribusiness",
    "import export", "agricultural export", "export policy",
    # Embassies, ministries and bilateral agencies are concentrated in Delhi,
    # and the CV states "open to New Delhi".
    "programme officer embassy", "government relations", "public affairs",
    "development cooperation", "bilateral cooperation", "policy advisor",
    "programme manager development", "public policy", "trade advisor",
]

# Rest of South India — a lighter sweep of the core profile queries.
LINKEDIN_SOUTH_QUERIES = [
    "agriculture policy", "food security", "agribusiness", "trade policy",
    "rural livelihoods", "policy consultant", "government relations",
    "development sector", "agricultural export", "value chain",
]

# All-India sweep for the role families where the best posts sit outside
# Bangalore (GIZ / embassy trade offices in Delhi, standards bodies, food-
# policy teams in Gurugram). The candidate is open to moving for the right role.
LINKEDIN_INDIA_QUERIES = [
    "agriculture policy", "food policy", "trade policy", "public policy food",
    "government affairs food", "corporate affairs FMCG", "GIZ",
    "programme officer agriculture", "trade advisor embassy",
    "trade commissioner", "PMU agriculture", "sustainability standards agriculture",
    "responsible sourcing agriculture", "agri export policy",
]

LINKEDIN_LOCATIONS = [
    ("Bengaluru, Karnataka, India", LINKEDIN_BLR_QUERIES),
    ("Hyderabad, Telangana, India", LINKEDIN_SOUTH_QUERIES),
    ("Chennai, Tamil Nadu, India",  LINKEDIN_SOUTH_QUERIES),
    ("Delhi, India",                LINKEDIN_DEL_QUERIES),
    ("India",                       LINKEDIN_INDIA_QUERIES),
]

LINKEDIN_TPR         = "r604800"   # posted in the last 7 days
LINKEDIN_MAX_PAGES   = 3           # 3 × 10 results per query
LINKEDIN_DELAY_SECS  = 2.5         # between EVERY request, not just pages
LINKEDIN_429_BACKOFF = 20          # one retry after a rate-limit hit

# Card fragments — the guest endpoint returns a bare <li> list, no wrapper.
_LI_CARD_RE  = re.compile(r'<li>(.*?)</li>', re.DOTALL)
_LI_URL_RE   = re.compile(r'class="base-card__full-link[^"]*"[^>]*href="([^"?]+)', re.IGNORECASE)
_LI_TITLE_RE = re.compile(r'class="base-search-card__title"[^>]*>\s*(.*?)\s*</h3>', re.DOTALL | re.IGNORECASE)
_LI_ORG_RE   = re.compile(r'class="base-search-card__subtitle"[^>]*>\s*(?:<a[^>]*>)?\s*(.*?)\s*(?:</a>)?\s*</h4>', re.DOTALL | re.IGNORECASE)
_LI_LOC_RE   = re.compile(r'class="job-search-card__location"[^>]*>\s*(.*?)\s*</span>', re.DOTALL | re.IGNORECASE)
_LI_DATE_RE  = re.compile(r'datetime="([\d-]+)"', re.IGNORECASE)


def _clean_li_text(raw):
    """Strip nested tags/entities and collapse whitespace from a card fragment."""
    return html.unescape(re.sub(r'<[^>]+>', ' ', raw or "")).strip()


def _parse_linkedin_page(content):
    jobs = []
    for card in _LI_CARD_RE.findall(content):
        um = _LI_URL_RE.search(card)
        tm = _LI_TITLE_RE.search(card)
        if not um or not tm:
            continue
        title = _clean_li_text(tm.group(1))
        title = re.sub(r'\s+', ' ', title)
        if not title:
            continue

        om  = _LI_ORG_RE.search(card)
        lm  = _LI_LOC_RE.search(card)
        dm  = _LI_DATE_RE.search(card)
        org = re.sub(r'\s+', ' ', _clean_li_text(om.group(1))) if om else ""
        loc = re.sub(r'\s+', ' ', _clean_li_text(lm.group(1))) if lm else "India"

        jobs.append({
            "title":    title,
            "url":      um.group(1),
            "org":      org or "Unknown",
            "updated":  dm.group(1) if dm else "",
            "source":   LINKEDIN_NAME,
            "location": loc or "India",
        })
    return jobs


def scrape_linkedin():
    print(f"\n[{LINKEDIN_NAME}] Fetching jobs...")
    jobs, seen = [], set()

    for location, queries in LINKEDIN_LOCATIONS:
        for query in queries:
            for page in range(LINKEDIN_MAX_PAGES):
                params = urllib.parse.urlencode({
                    "keywords": query,
                    "location": location,
                    "f_TPR":    LINKEDIN_TPR,
                    "start":    page * 10,
                })
                time.sleep(LINKEDIN_DELAY_SECS)
                content = None
                for attempt in range(2):
                    try:
                        content = fetch_page(f"{LINKEDIN_API}?{params}")
                        break
                    except urllib.error.HTTPError as e:
                        if e.code == 429 and attempt == 0:
                            time.sleep(LINKEDIN_429_BACKOFF)
                            continue
                        print(f"[{LINKEDIN_NAME}] '{query}' @ {location.split(',')[0]} p{page}: {e}")
                        break
                    except Exception as e:
                        print(f"[{LINKEDIN_NAME}] '{query}' @ {location.split(',')[0]} p{page}: {e}")
                        break
                if content is None:
                    # still blocked — skip the rest of this query, keep the run
                    break

                page_jobs = _parse_linkedin_page(content)
                for job in page_jobs:
                    if job["url"] in seen:
                        continue
                    seen.add(job["url"])
                    jobs.append(job)

                if len(page_jobs) < 10:      # last page for this query
                    break

    blr = sum(1 for j in jobs if any(m in j["location"].lower() for m in BANGALORE_MARKERS))
    print(f"[{LINKEDIN_NAME}] {len(jobs)} jobs found ({blr} Bangalore).")
    return jobs


# ─── SCORING ───────────────────────────────────────────────────────────────────

# Roles a policy / trade / development professional would not apply for,
# whatever the employer. Bangalore's LinkedIn feed is mostly tech, so without
# this an IT developer at Tyson Foods or a billing engineer at an NGO hospital
# scores on the employer's name alone.
NON_FIT_TITLE = re.compile(
    r'\b(developer|software|engineer(ing)?|devops|sap|salesforce|oracle|java|'
    r'python|full[- ]?stack|frontend|backend|data engineer|machine learning|'
    r'it (project|support|manager|specialist)|sales|billing|accountant|'
    r'accounts|cfo|chief financial|chef|culinary|nurse|nursing|doctor|'
    r'physician|pharmac\w*|medical|hospital|teacher|tutor|driver|technician|'
    r'mechanic|electrician|intern|internship|trainee|apprentice|'
    r'receptionist|housekeeping|security guard|executive assistant|'
    r'graphic designer|video editor|hr|human resources|recruiter|'
    r'talent acquisition|payroll|legal counsel|lawyer|financial controller|'
    r'finance manager|rtr|record to report|accounts payable|tax|accounting|'
    r'business finance|costing|real estate|'
    # Too junior for a 7-year policy professional, or plainly not office/policy work
    r'fresher|freshers|entry[- ]level|junior|assistant|farm manager|'
    r'farm supervisor|marketing|architect|data protection|counsel|'
    r'fundraising|data entry|telecaller|field executive|'
    # Lab / bench science and plant-animal technical work — an agricultural
    # economist is not a candidate for these even at ICRISAT or SELCO
    r'laborator\w*|microbiolog\w*|chemist\w*|biotech\w*|geneticist|breeding|'
    r'breeder|agronomist|scientific officer|(?<!social )(?<!policy )(?<!economic )'
    r'(?<!data )scientist|food analyst|nutritionist|poultry|'
    r'(animal|dairy|swine|aqua|feed) (nutrition|health|feed))\b',
    re.IGNORECASE,
)

# Employers in sectors that have nothing to do with the profile, however
# generic the job title. Pharma "Market Access" is drug pricing, not agricultural
# market access; energy majors and big tech hire "policy" and "analyst" roles
# that score on vocabulary alone.
NON_FIT_ORGS = {
    "sanofi", "novartis", "pfizer", "abbott", "gsk", "glaxo", "roche", "merck",
    "astrazeneca", "eli lilly", "novo nordisk", "takeda", "cipla", "sun pharma",
    "dr. reddy", "dr reddy", "lupin", "biocon", "zydus", "alkem", "glenmark",
    "boehringer", "johnson & johnson", "medtronic", "philips", "siemens",
    "chevron", "exxon", "shell", "bp ", "lam research", "intel", "nvidia",
    "google", "microsoft", "meta platforms", "tanla", "alignerr", "als ",
    "amazon", "flipkart", "swiggy", "zomato", "rebel foods", "curefoods",
    "teva", "mankind pharma", "torrent pharma", "aurobindo",
    "cafe coffee day", "dil foods", "yummy bee", "smart food safe",
}

# Corporate functions that share vocabulary with the profile (trade,
# commodity, food, compliance) but are operational desks, not policy or
# development roles. Only applied when the employer is not itself a
# development-sector body, so "Procurement Officer" at UNDP still passes.
CORPORATE_NON_FIT = re.compile(
    r'\b(procurement|supply chain|trade compliance|global trade|'
    r'import (&|and)? ?export operations|export operations|export head|'
    r'commodity manager|strategic commodity|'
    r'compliance specialist|operations compliance|risk compliance|'
    r'food safety|performance|trade marketing|logistics|merchandis\w*|'
    # Food-industry plant floor and quality desks
    r'quality (assurance|executive|system|control|manager|analyst|engineer)|'
    r'qa|qc|qms|production|plant|franchise|cluster manager|outlet|store manager|'
    r'category manager|channel development|marketplaces?|food specialist|'
    r'technical specialist|product manager)\b',
    re.IGNORECASE,
)


# Policy-team titles at big private employers. "Regulatory affairs" is left out
# on purpose: at a pharma or med-tech company it means drug filings, not policy.
POLICY_TEAM_TITLE = re.compile(
    r'policy|public affairs|corporate affairs|external affairs|government', re.IGNORECASE)


# Reputable private employers (Nov 2026: "apply to all good private-sector
# companies"). At these, strategy / BD / partnerships / consulting /
# government-facing roles count as a fit whatever the sector — they are the
# transferable side of policy, trade-promotion and BD experience.
GOOD_PRIVATE_ORGS = {
    # Consulting and advisory
    "deloitte", "ey", "ernst & young", "pwc", "pricewaterhouse", "kpmg",
    "mckinsey", "boston consulting", "bcg", "bain", "accenture", "grant thornton",
    "alvarez", "kearney", "oliver wyman", "roland berger", "redseer", "praxis",
    "technopak", "crisil", "icra", "nielsen",
    # Conglomerates and consumer majors
    "tata", "itc", "mahindra", "aditya birla", "reliance", "adani", "godrej",
    "hindustan unilever", "unilever", "nestle", "pepsico", "coca-cola", "britannia",
    "marico", "dabur", "jsw", "larsen", "l&t", "vedanta", "wipro", "infosys",
    "biocon", "titan", "asian paints",
    # Consumer internet, e-commerce and fintech (Bengaluru-heavy)
    "flipkart", "amazon", "swiggy", "zepto", "zomato", "eternal", "blinkit",
    "meesho", "phonepe", "razorpay", "paytm", "cred", "ola", "uber", "google",
    "microsoft", "walmart", "myntra", "udaan", "bigbasket", "nykaa", "jio",
    # Banks and financial institutions with agri / rural books
    "hdfc", "icici", "axis bank", "kotak", "sbi", "state bank", "yes bank",
    "idfc", "bandhan", "standard chartered", "hsbc", "citi", "rabobank",
}

# Role families that carry over from the profile to any reputable employer
TRANSFERABLE_TITLE = re.compile(
    r'strateg|business development|\bbd\b|partnership|alliance|chief of staff|'
    r"founder'?s office|government|public policy|policy|corporate affairs|"
    r'external affairs|public affairs|regulatory affairs|consult|advisory|'
    r'program(me)? manag|transformation|market access|stakeholder|'
    r'institutional|esg|sustainab', re.IGNORECASE)


def org_is_good_private(org):
    return _org_matches(org, GOOD_PRIVATE_ORGS)


def title_is_non_fit(title, org=""):
    # LinkedIn titles sometimes use underscores for spaces ("Sales_Executive")
    t = (title or "").replace("_", " ")
    if NON_FIT_TITLE.search(t):
        return True
    # Pharma / energy / big-tech employers are excluded — except for policy,
    # public-affairs and government roles, which are exactly the private-sector
    # policy-making jobs wanted.
    if (_org_matches(org, NON_FIT_ORGS) and not org_is_dev_sector(org)
            and not POLICY_TEAM_TITLE.search(t)
            and not (org_is_good_private(org) and TRANSFERABLE_TITLE.search(t))):
        return True
    if CORPORATE_NON_FIT.search(t) and not org_is_dev_sector(org):
        return True
    return False


# Bangalore bonus is a RANKING boost only — it is deliberately kept out of the
# relevance tier so that a broad source like LinkedIn cannot turn every
# Bengaluru listing into a "LOW" match on location alone.
BANGALORE_BONUS = 4


ROLE_ONLY_CORE = {"programme officer", "program officer"}
DIPLOMATIC_ORG = re.compile(r'embassy|high commission|consulate|delegation of the european union', re.IGNORECASE)


def score_job(job):
    org  = "" if org_is_non_dev(job["org"]) else job["org"]
    text = (job["title"] + " " + org + " " + job.get("location", "")).lower()
    title_text = job["title"].lower()
    kw_score, matched, has_core, title_core = 0, [], False, False
    for keyword, weight in ALL_KEYWORDS:
        kw = keyword.lower()
        if kw in WHOLE_WORD_KEYWORDS:
            # Optional trailing 's' so "Imports"/"Exports"/"Shipments" match,
            # while "important" still does not.
            pat = r'\b' + re.escape(kw) + r's?\b'
            hit = bool(re.search(pat, text))
            in_title = bool(re.search(pat, title_text))
        else:
            hit = kw in text
            in_title = kw in title_text
        if hit:
            kw_score += weight
            matched.append(keyword)
            if kw in CORE_DOMAIN:
                has_core = True
                # A bare "Programme Officer" title says nothing about the
                # sector (child protection, digital health…) — it only counts
                # as a profile term at a diplomatic mission.
                if in_title and (kw not in ROLE_ONLY_CORE or DIPLOMATIC_ORG.search(job.get("org", ""))):
                    title_core = True

    # A development-sector employer counts as a domain signal on its own.
    if org_is_dev_sector(job.get("org", "")):
        has_core = True
        kw_score += 3
        matched.append("[dev-sector org]")
    elif org_is_agri_food(job.get("org", "")):
        # +1 only: a corporate analytics or QA role at Cargill should land in
        # MEDIUM, not HIGH, unless the title itself carries a profile word.
        has_core = True
        kw_score += 1
        matched.append("[agri-food org]")
    # Strategy / BD / policy / consulting roles at a reputable private employer
    if (org_is_good_private(job.get("org", "")) and not org_is_non_dev(job.get("org", ""))
            and TRANSFERABLE_TITLE.search(job["title"])):
        has_core = title_core = True
        kw_score += 3
        matched.append("[top private employer]")

    score = kw_score
    loc = (job.get("location", "") + " " + job["source"]).lower()
    if any(m in loc for m in BANGALORE_MARKERS):
        score += BANGALORE_BONUS
    return score, kw_score, has_core, title_core, list(dict.fromkeys(matched))


def classify(kw_score, has_core=False, title_core=False):
    """Tier is decided on CV-keyword merit only — never on location.

    HIGH needs a profile term in the job title itself: an employer being a
    dev-sector body is enough for MEDIUM but not to claim the role fits.
    MEDIUM still needs some domain signal, so generic corporate titles
    ("Manager", "Strategy", "Program") cannot rank above LOW.
    """
    if kw_score >= 5 and title_core: return "HIGH"
    if kw_score >= 4 and has_core: return "MEDIUM"
    if kw_score >= 2: return "LOW"
    return "NO MATCH"


def location_priority(job):
    """0 = Bangalore, 1 = rest of South India, 2 = Delhi NCR, 3 = other."""
    loc = (job.get("location", "") + " " + job["source"]).lower()
    if any(m in loc for m in BANGALORE_MARKERS):
        return 0
    if any(m in loc for m in SOUTH_MARKERS):
        return 1
    if any(m in loc for m in DELHI_MARKERS):
        return 2
    return 3


# Delhi-NCR pay check (no longer used as a gate). Delhi
# listings rarely state pay, so they must clear the bar another way: a stated
# salary, an employer on international / bilateral pay scales, or a senior title.
DELHI_MIN_LPA = 15
HIGH_PAY_ORGS = {
    "united nations", "undp", "unicef", "wfp", "fao", "ifad", "unido", "unep",
    "unesco", "ilo", "un women", "unfpa", "unops", "iom", "unhcr",
    "world bank", "ifc", "asian development bank", "adb", "aiib",
    "cgiar", "icrisat", "irri", "cimmyt", "ifpri", "iwmi", "ilri",
    "embassy", "high commission", "delegation of the european union",
    "giz", "usaid", "fcdo", "jica", "kfw", "daad", "indo-german", "deutsche gesellschaft",
    "consulate general of germany", "gates foundation", "rockefeller",
    "international trade centre", "wto", "unctad", "niti aayog",
    "deloitte", "ey", "pwc", "kpmg", "mckinsey", "bcg", "bain",
}
SENIOR_TITLE = re.compile(
    r'\b(head|director|deputy|senior manager|sr\.? manager|principal|lead|'
    r'chief|advisor|adviser|specialist|representative|country)\b', re.IGNORECASE)


def delhi_pay_ok(job):
    """True when a Delhi-NCR job plausibly pays above the current band."""
    m = re.search(r'·\s*(.+)$', job.get("location", ""))     # JobShobNest salary
    lpa = _parse_salary_lpa(m.group(1)) if m else None
    if lpa is not None:
        return lpa >= DELHI_MIN_LPA
    if _org_matches(job.get("org", ""), HIGH_PAY_ORGS) and not org_is_non_dev(job.get("org", "")):
        return True
    return bool(SENIOR_TITLE.search(job["title"]))




# ─── AI CV-FIT RE-RANKING ──────────────────────────────────────────────────────
# Keyword scoring cannot tell "Head of Digital Agriculture" from "Dairy
# Nutritionist" — both say agriculture. Before alerting, each NEW candidate is
# read against the CV by Gemini, which scores real fit and gives a one-line
# reason. Uses Google's Gemini free tier — needs GEMINI_API_KEY; without one (or if the API fails) the run
# falls back to the keyword tiers, so alerts never stop because of this step.

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
AI_MODEL          = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
AI_BATCH_SIZE     = 8
AI_CALL_GAP_SECS  = 7        # free tier allows ~10 requests/minute
AI_429_BACKOFF    = 30
AI_MAX_JOBS       = 150      # per run; keeps cost and LinkedIn fetches bounded
AI_DESC_CHARS     = 1500
AI_MIN_SCORE      = 4        # below this the job is not alerted...
CV_PROFILE_FILE   = os.path.join(DATA_DIR, "cv_profile.txt")

AI_SYSTEM = _load_private_text("screening_prompt.txt", """You screen job listings for one candidate. Be strict and honest: most listings are NOT a fit.

CANDIDATE PROFILE:
{profile}

Score each listing 0-10 for how well it fits this candidate (10 = exact fit; 7-8 = strong; 5-6 = plausible stretch; below 5 = skip).
Reply with ONLY a JSON array, one object per listing: {{"id": <number>, "score": <0-10>, "reason": "<max 14 words>"}}""")


def _load_cv_profile():
    try:
        with open(CV_PROFILE_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _strip_html(raw):
    raw = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', raw or "")
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', raw))).strip()


def fetch_description(job):
    """Best-effort job description text; '' when unavailable."""
    url = job["url"]
    try:
        if "linkedin.com/jobs/view" in url:
            m = re.search(r'-(\d{6,})(?:\?|$)', url)
            if not m:
                return ""
            page = fetch_page(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}")
            dm = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.DOTALL)
            return _strip_html(dm.group(1) if dm else page)[:AI_DESC_CHARS]
        if re.search(r'drive\.google|docs\.google|\.pdf($|\?)', url):
            return ""
        return _strip_html(fetch_page(url))[:AI_DESC_CHARS]
    except Exception:
        return ""


def _ai_call(system, user):
    """One Gemini generateContent call (free tier); retries on 429/500/503."""
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL}:generateContent"
    for attempt in range(3):
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("x-goog-api-key", GEMINI_API_KEY)
        req.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            # 429 = free-tier rate limit; 500/503 = Google-side demand spike
            if e.code in (429, 500, 503) and attempt < 2:
                time.sleep(AI_429_BACKOFF)
                continue
            raise
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _parse_ai_scores(text):
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return {}
    out = {}
    for item in json.loads(text[start:end + 1]):
        out[int(item["id"])] = (float(item["score"]), str(item.get("reason", "")).strip())
    return out


def ai_rerank(jobs):
    """Score `jobs` against the CV; drop poor fits, re-tier the rest.

    Returns the jobs unchanged when no API key / CV profile is available or the
    API is unreachable.
    """
    profile = _load_cv_profile()
    if not jobs or not GEMINI_API_KEY or not profile:
        print("\nAI re-ranking skipped "
              f"({'no GEMINI_API_KEY' if not GEMINI_API_KEY else 'no cv_profile.txt'}) — using keyword tiers.")
        return jobs

    system = AI_SYSTEM.format(profile=profile)
    todo, rest = jobs[:AI_MAX_JOBS], jobs[AI_MAX_JOBS:]
    print(f"\nAI re-ranking {len(todo)} new jobs with {AI_MODEL}...")
    kept, failed_batches = [], 0

    for i in range(0, len(todo), AI_BATCH_SIZE):
        batch = todo[i:i + AI_BATCH_SIZE]
        lines = []
        for n, j in enumerate(batch):
            desc = fetch_description(j)
            if j["source"] == LINKEDIN_NAME:
                time.sleep(1.0)
            lines.append(f'[{n}] {j["title"]} | {j["org"]} | {j.get("location", "") or "India"}\n'
                         f'    {desc or "(no description available — judge from title and employer)"}')
        if i:
            time.sleep(AI_CALL_GAP_SECS)
        try:
            scores = _parse_ai_scores(_ai_call(system, "\n\n".join(lines)))
        except Exception as e:
            failed_batches += 1
            print(f"  AI batch {i // AI_BATCH_SIZE + 1} failed ({type(e).__name__}: {e}) — keeping keyword tiers for it.")
            kept.extend(batch)
            continue
        for n, j in enumerate(batch):
            if n not in scores:
                kept.append(j)               # model skipped it — do not silently drop
                continue
            score, reason = scores[n]
            j["ai_score"], j["ai_reason"] = score, reason
            if score < AI_MIN_SCORE:
                # ...unless the keywords were strong. Gemini is not consistent
                # across runs: it scored IISc "Program Manager, Strategy & Ops"
                # 8/10 in a test and dropped it in the live run of 30 Oct 2026.
                # A strong keyword match goes out as LOW with Gemini's reason,
                # so the candidate can judge it.
                if j["relevance"] == "HIGH" or org_is_dev_sector(j.get("org", "")):
                    j["relevance"] = "LOW"
                    kept.append(j)
                continue
            j["relevance"] = "HIGH" if score >= 8 else "MEDIUM" if score >= 6 else "LOW"
            kept.append(j)

    print(f"AI kept {len(kept)} of {len(todo)} jobs"
          + (f" ({failed_batches} batch(es) fell back to keywords)." if failed_batches else "."))
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    kept.sort(key=lambda j: (location_priority(j), order.get(j["relevance"], 3), -j.get("ai_score", 0), -j["score"]))
    return kept + rest


# ─── SEEN JOBS TRACKER ─────────────────────────────────────────────────────────

def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen_jobs(seen_urls):
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_urls), f)


# ─── TELEGRAM ──────────────────────────────────────────────────────────────────

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not set — skipping.")
        return
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                print("Telegram alert sent.")
            else:
                print(f"Telegram error: {result}")
    except Exception as e:
        print(f"Telegram send failed: {e}")


def _short_source(src):
    return (src.replace("UNjobs New Delhi", "UNjobs DEL")
               .replace("UNjobs Bangalore", "UNjobs BLR")
               .replace("DevNetJobs India", "DevNet IN")
               .replace("DevNetJobs Global", "DevNet GL")
               .replace("Athena Infonomics", "Athena")
               .replace("JobShobNest", "ShobNest")
               .replace("ATREE Bangalore", "ATREE")
               .replace("SELCO Foundation", "SELCO")
               .replace("ReliefWeb", "ReliefWeb"))


def _job_lines(j, bold=False):
    """Return formatted lines for a single job listing."""
    src  = _short_source(j["source"])
    loc  = j.get("location", "").strip()
    kws  = ", ".join(j["matched"][:4]) if j.get("matched") else ""
    date = j.get("updated", "")

    title_line = f"• <b>{j['title']}</b>" if bold else f"• {j['title']}"
    meta_parts = [j["org"]]
    if loc and loc.lower() not in ("unknown", "india"):
        meta_parts.append(loc)
    meta_parts.append(f"[{src}]")
    if date:
        meta_parts.append(f"Posted: {date}")

    lines = [title_line, f"  {' · '.join(meta_parts)}"]
    if j.get("ai_reason"):
        lines.append(f"  <i>Fit {j['ai_score']:g}/10: {html.escape(j['ai_reason'])}</i>")
    elif kws:
        lines.append(f"  <i>Keywords: {kws}</i>")
    lines.append(f'  <a href="{j["url"]}">View Job →</a>')
    lines.append("")
    return lines


TELEGRAM_MAX_CHARS = 4000  # Telegram limit is 4096; leave headroom


def _split_into_messages(header_lines, sections):
    """Pack header + all job sections into ≤4000-char Telegram messages.

    sections: list of (label_line, [job_line_lists])
    Returns a list of message strings.
    """
    messages  = []
    current   = "\n".join(header_lines) + "\n\n"

    for label, job_chunks in sections:
        section_header = label + "\n"
        # Does the section header alone fit?
        if len(current) + len(section_header) > TELEGRAM_MAX_CHARS:
            messages.append(current.rstrip())
            current = section_header
        else:
            current += section_header

        for chunk in job_chunks:
            block = "\n".join(chunk) + "\n"
            if len(current) + len(block) > TELEGRAM_MAX_CHARS:
                messages.append(current.rstrip())
                current = block
            else:
                current += block

    if current.strip():
        messages.append(current.rstrip())

    return messages


def build_alert_messages(new_jobs, total_jobs):
    """Return a list of Telegram message strings covering ALL new jobs."""
    run_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
    high   = [j for j in new_jobs if j["relevance"] == "HIGH"]
    medium = [j for j in new_jobs if j["relevance"] == "MEDIUM"]
    low    = [j for j in new_jobs if j["relevance"] == "LOW"]

    by_source = {}
    for j in new_jobs:
        by_source.setdefault(j["source"], 0)
        by_source[j["source"]] += 1
    source_summary = " | ".join(f"{s}: {c}" for s, c in by_source.items())

    header = [
        "🔔 <b>Job Alert — New CV Matches</b>",
        f"<i>{run_time}</i>",
        "",
        f"<b>{len(new_jobs)} NEW jobs</b> matched your CV",
        f"HIGH: {len(high)}  ·  MEDIUM: {len(medium)}  ·  LOW: {len(low)}",
        f"Sources: {source_summary}",
        f"Total tracked: {total_jobs}",
    ]

    sections = []
    if high:
        sections.append(("🟢 <b>HIGH MATCH</b>", [_job_lines(j, bold=True)  for j in high]))
    if medium:
        sections.append(("🟡 <b>MEDIUM MATCH</b>", [_job_lines(j, bold=False) for j in medium]))
    if low:
        sections.append((f"⚪ <b>LOW MATCH</b>  ({len(low)} jobs)", [_job_lines(j, bold=False) for j in low]))

    return _split_into_messages(header, sections)


def build_bangalore_spotlight(new_jobs, all_jobs):
    """Return a Telegram message highlighting Bangalore-only new jobs.
    Returns None if there are no Bangalore matches."""
    run_time = datetime.now().strftime("%d %b %Y, %I:%M %p")

    def is_blr(j):
        loc = (j.get("location", "") + " " + j["source"]).lower()
        return any(m in loc for m in BANGALORE_MARKERS)

    blr_new  = [j for j in new_jobs if is_blr(j) and j["relevance"] in ("HIGH", "MEDIUM", "LOW")]
    blr_all  = [j for j in all_jobs if is_blr(j) and j["relevance"] in ("HIGH", "MEDIUM", "LOW")]

    if not blr_new and not blr_all:
        return None

    high   = [j for j in blr_new if j["relevance"] == "HIGH"]
    medium = [j for j in blr_new if j["relevance"] == "MEDIUM"]
    low    = [j for j in blr_new if j["relevance"] == "LOW"]

    header = [
        "🏙️ <b>Bangalore Spotlight</b>",
        f"<i>{run_time}</i>",
        "",
        f"<b>{len(blr_new)} NEW Bangalore jobs</b>  ·  {len(blr_all)} total open",
        f"HIGH: {len(high)}  ·  MEDIUM: {len(medium)}  ·  LOW: {len(low)}",
    ]

    if not blr_new:
        # No new Bangalore jobs — show top open ones as reminder
        top = blr_all[:5]
        lines = ["\n".join(header), "", "No new Bangalore jobs today. Top open roles:"]
        for j in top:
            src = _short_source(j["source"])
            lines.append(f'• <a href="{j["url"]}">{j["title"]}</a>')
            lines.append(f'  {j["org"]} [{src}]  <b>{j["relevance"]}</b>')
        return "\n".join(lines)

    sections = []
    if high:
        sections.append(("🟢 <b>HIGH</b>", [_job_lines(j, bold=True)  for j in high]))
    if medium:
        sections.append(("🟡 <b>MEDIUM</b>", [_job_lines(j, bold=False) for j in medium]))
    if low:
        sections.append((f"⚪ <b>LOW</b>  ({len(low)})", [_job_lines(j, bold=False) for j in low]))

    msgs = _split_into_messages(header, sections)
    return msgs[0] if msgs else None   # spotlight fits in one message


def send_summary_message(all_jobs):
    run_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
    high   = len([j for j in all_jobs if j["relevance"] == "HIGH"])
    medium = len([j for j in all_jobs if j["relevance"] == "MEDIUM"])
    low    = len([j for j in all_jobs if j["relevance"] == "LOW"])

    # Top 3 HIGH jobs as a reminder
    top_high = [j for j in all_jobs if j["relevance"] == "HIGH"][:3]
    top_lines = []
    for j in top_high:
        src = _short_source(j["source"])
        loc = j.get("location", "")
        loc_str = f" · {loc}" if loc and loc.lower() not in ("unknown", "india") else ""
        top_lines.append(f'• <a href="{j["url"]}">{j["title"]}</a>\n  {j["org"]}{loc_str} [{src}]')

    top_section = "\n\n".join(top_lines)

    msg = (
        f"📋 <b>Job Alert — Daily Summary</b>\n"
        f"<i>{run_time}</i>\n\n"
        f"No new jobs since last check.\n"
        f"Tracked: <b>{len(all_jobs)}</b>  ·  HIGH: <b>{high}</b>  ·  MEDIUM: <b>{medium}</b>  ·  LOW: <b>{low}</b>\n"
    )
    if top_section:
        msg += f"\n🏆 <b>Top open roles:</b>\n{top_section}\n"

    send_telegram(msg)


# ─── OUTPUT ────────────────────────────────────────────────────────────────────

def save_csv(jobs, filepath):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "relevance", "score", "title", "org", "updated", "url", "matched_keywords", "ai_score", "ai_reason"])
        writer.writeheader()
        for job in jobs:
            writer.writerow({
                "ai_score":         job.get("ai_score", ""),
                "ai_reason":        job.get("ai_reason", ""),
                "source":           job["source"],
                "relevance":        job["relevance"],
                "score":            job["score"],
                "title":            job["title"],
                "org":              job["org"],
                "updated":          job["updated"],
                "url":              job["url"],
                "matched_keywords": ", ".join(job["matched"]),
            })
    print(f"CSV saved: {filepath}")


def save_html(jobs, filepath):
    run_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
    high   = [j for j in jobs if j["relevance"] == "HIGH"]
    medium = [j for j in jobs if j["relevance"] == "MEDIUM"]
    low    = [j for j in jobs if j["relevance"] == "LOW"]
    none   = [j for j in jobs if j["relevance"] == "NO MATCH"]

    src_counts = {}
    for j in jobs:
        src_counts[j["source"]] = src_counts.get(j["source"], 0) + 1
    src_summary = " &nbsp;|&nbsp; ".join(f"{s}: <b>{c}</b>" for s, c in src_counts.items())

    def color(rel):
        return {"HIGH": "#1a7f4b", "MEDIUM": "#b07d0a", "LOW": "#666", "NO MATCH": "#aaa"}.get(rel, "#aaa")

    def badge(rel):
        bg = {"HIGH": "#d4edda", "MEDIUM": "#fff3cd", "LOW": "#f0f0f0", "NO MATCH": "#f8f8f8"}.get(rel, "#f8f8f8")
        return f'<span style="background:{bg};color:{color(rel)};padding:2px 8px;border-radius:10px;font-size:12px;font-weight:bold">{rel}</span>'

    def src_chip(src):
        colours = {
            "UNjobs New Delhi":   "#1a3c5e",
            "UNjobs Bangalore":   "#2e6b3e",
            "DevNetJobs India":   "#7b3fa0",
            "DevNetJobs Global":  "#5b2f80",
            "Athena Infonomics":  "#0e6b75",
            "Impactpool":         "#b5470b",
            "ReliefWeb":          "#c0392b",
            "JobShobNest":        "#6a1b9a",
            "ATREE Bangalore":    "#1a6e3e",
            "SELCO Foundation":   "#d4820a",
        }
        bg = colours.get(src, "#555")
        short = src.replace("UNjobs ", "").replace("DevNetJobs ", "DevNet ")
        return f'<span style="background:{bg};color:white;padding:1px 6px;border-radius:8px;font-size:11px">{short}</span>'

    def rows(job_list):
        if not job_list:
            return '<tr><td colspan="6" style="color:#aaa;text-align:center">None found</td></tr>'
        out = ""
        for j in job_list:
            kw  = ", ".join(j["matched"]) if j["matched"] else "-"
            new = ' <span style="background:#e74c3c;color:white;font-size:10px;padding:1px 5px;border-radius:8px">NEW</span>' if j.get("is_new") else ""
            out += f"""
            <tr>
              <td>{src_chip(j['source'])}</td>
              <td style="font-weight:bold"><a href="{j['url']}" target="_blank">{j['title']}</a>{new}</td>
              <td>{j['org']}</td>
              <td style="text-align:center">{badge(j['relevance'])}</td>
              <td style="text-align:center">{j['score']}</td>
              <td style="font-size:12px;color:#888">{kw}</td>
            </tr>"""
        return out

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Job Alert – CV Match Report</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 30px; color: #333; background: #f9f9f9; }}
  h1 {{ color: #1a3c5e; }}
  h2 {{ color: #1a3c5e; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 6px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 8px; }}
  .sources {{ font-size: 13px; margin-bottom: 20px; }}
  .summary {{ display: flex; gap: 16px; margin-bottom: 30px; flex-wrap: wrap; }}
  .card {{ background: white; border-radius: 8px; padding: 16px 24px; box-shadow: 0 1px 4px rgba(0,0,0,.1); min-width: 120px; text-align: center; }}
  .card .num {{ font-size: 32px; font-weight: bold; }}
  .card .lbl {{ font-size: 12px; color: #888; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.1); margin-bottom: 30px; }}
  th {{ background: #1a3c5e; color: white; padding: 10px 12px; text-align: left; font-size: 13px; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; vertical-align: top; }}
  tr:hover td {{ background: #f5f8ff; }}
  a {{ color: #1a5276; }} a:hover {{ color: #e74c3c; }}
</style>
</head>
<body>
<h1>Job Alert – CV Match Report</h1>
<p class="meta">Candidate: <strong>{_applicant().get("name", "")}</strong> &nbsp;|&nbsp; Generated: {run_time}</p>
<p class="sources">Sources: {src_summary}</p>
<div class="summary">
  <div class="card"><div class="num" style="color:#1a7f4b">{len(high)}</div><div class="lbl">HIGH Match</div></div>
  <div class="card"><div class="num" style="color:#b07d0a">{len(medium)}</div><div class="lbl">MEDIUM Match</div></div>
  <div class="card"><div class="num" style="color:#666">{len(low)}</div><div class="lbl">LOW Match</div></div>
  <div class="card"><div class="num" style="color:#aaa">{len(none)}</div><div class="lbl">No Match</div></div>
  <div class="card"><div class="num" style="color:#1a3c5e">{len(jobs)}</div><div class="lbl">Total Jobs</div></div>
</div>
<h2>HIGH Relevance ({len(high)} jobs)</h2>
<table><tr><th>Source</th><th>Job Title</th><th>Organization</th><th>Relevance</th><th>Score</th><th>Matched Keywords</th></tr>{rows(high)}</table>
<h2>MEDIUM Relevance ({len(medium)} jobs)</h2>
<table><tr><th>Source</th><th>Job Title</th><th>Organization</th><th>Relevance</th><th>Score</th><th>Matched Keywords</th></tr>{rows(medium)}</table>
<h2>LOW Relevance ({len(low)} jobs)</h2>
<table><tr><th>Source</th><th>Job Title</th><th>Organization</th><th>Relevance</th><th>Score</th><th>Matched Keywords</th></tr>{rows(low)}</table>
</body></html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"HTML report saved: {filepath}")


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Job Alert – CV Matcher")
    print("=" * 60)

    # Every source is isolated. A site going down, rate-limiting us, or putting
    # up a bot challenge must never take the whole run with it — on 27 Aug 2026
    # unjobs.org went behind Cloudflare and its unguarded 403 killed main()
    # before a single alert was sent.
    sources = [(s["name"], (lambda s=s: scrape_unjobs(s))) for s in UNJOBS_SOURCES] + [
        (DEVNET_NAME,        scrape_devnet),
        (ATHENA_NAME,        scrape_athena),
        (IMPACTPOOL_NAME,    scrape_impactpool),
        (RELIEFWEB_NAME,     scrape_reliefweb),
        (DEVNETGLOBAL_NAME,  scrape_devnetglobal),
        (JOBSHOBNEST_NAME,   scrape_jobshobnest),
        (ATREE_NAME,         scrape_atree),
        (SELCO_NAME,         scrape_selco),
        (GOV_NAME,           scrape_government),
        (FJA_NAME,           scrape_freejobalert),
        (LINKEDIN_NAME + " follow-list", scrape_linkedin_companies),
        (UNDP_NAME,          scrape_undp),
        (LINKEDIN_NAME,      scrape_linkedin),
    ]

    all_jobs, failed = [], []
    for name, scrape in sources:
        try:
            all_jobs.extend(scrape())
        except Exception as e:
            failed.append(name)
            print(f"[{name}] FAILED: {type(e).__name__}: {e}")

    if failed:
        print(f"\n!! {len(failed)} of {len(sources)} sources failed: {', '.join(failed)}")

    # Deduplicate by URL AND by title (3+ word titles are unique enough across sources)
    # This catches the same job listed on Impactpool + JobShobNest + UNjobs etc.
    seen_urls_dedup, seen_titles, unique = set(), set(), []
    for job in all_jobs:
        title_key = re.sub(r'\W+', ' ', job["title"].lower()).strip()
        is_specific = len(title_key.split()) >= 3   # short titles like "Manager" can exist at many orgs
        if job["url"] not in seen_urls_dedup and (not is_specific or title_key not in seen_titles):
            seen_urls_dedup.add(job["url"])
            if is_specific:
                seen_titles.add(title_key)
            unique.append(job)
    all_jobs = unique

    print(f"\nTotal unique jobs across all sources: {len(all_jobs)}")

    # Score and classify
    for job in all_jobs:
        job["score"], job["kw_score"], job["has_core"], job["title_core"], job["matched"] = score_job(job)
        job["relevance"] = classify(job["kw_score"], job["has_core"], job["title_core"])
        if title_is_non_fit(job["title"], job.get("org", "")):
            job["relevance"] = "NO MATCH"

    # Sort: Bangalore first → relevance tier → score desc.
    # Location leads the key so the Bangalore roles head every list and message.
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NO MATCH": 3}
    all_jobs.sort(key=lambda j: (location_priority(j), order[j["relevance"]], -j["score"]))

    # Find NEW jobs
    seen_urls = load_seen_jobs()
    # `python job_alert.py --all` re-evaluates every current listing as if new —
    # used after changing the matching rules, so the whole pool gets re-scored.
    rerun_all = "--all" in sys.argv
    if rerun_all:
        print("\n--all: treating every listing as new.")
    new_jobs  = []
    for job in all_jobs:
        if rerun_all or job["url"] not in seen_urls:
            job["is_new"] = True
            new_jobs.append(job)
        else:
            job["is_new"] = False

    # LinkedIn is an uncurated firehose (~280 listings/run) unlike the curated
    # dev-sector sources, so it only earns an alert at MEDIUM or above.
    # Its LOW matches still land in the CSV/HTML for manual browsing.
    def alertable(j):
        if j["relevance"] == "NO MATCH":
            return False
        # No location gate: the candidate is open to moving for a strong role
        # (Nov 2026). Bangalore still sorts first in every message.
        if j["source"] == LINKEDIN_NAME:
            # LinkedIn returns ~450 listings a run against a handful from the
            # curated boards. Require an actual agriculture/food/development
            # signal — a bare trade word is not enough, or every corporate
            # export-compliance desk in Bengaluru lands in the alert.
            if not j["has_core"]:
                return False
            # Policy-team titles go through at LOW too — Gemini reads each one
            # against the CV next, so a weak keyword score is not the last word.
            if j["relevance"] == "LOW" and not (org_is_dev_sector(j.get("org", ""))
                                                or org_is_agri_food(j.get("org", ""))
                                                or POLICY_TEAM_TITLE.search(j["title"])):
                return False
        return True

    candidates  = [j for j in new_jobs if alertable(j)]
    new_matches = ai_rerank(candidates)
    # Only jobs that reached the alert / Gemini stage are marked seen. Jobs the
    # keyword filters dropped stay unseen, so they are re-scored every run for
    # free and surface the moment a filter is loosened — the Delhi pay gate,
    # removed in Nov 2026, had silently and permanently buried IPE Global and
    # PxD roles.
    save_seen_jobs(seen_urls | {j["url"] for j in candidates})

    # Print summary
    high   = [j for j in all_jobs if j["relevance"] == "HIGH"]
    medium = [j for j in all_jobs if j["relevance"] == "MEDIUM"]
    low    = [j for j in all_jobs if j["relevance"] == "LOW"]

    print(f"\n{'='*60}")
    print(f"  TOTAL:   {len(high)} HIGH  |  {len(medium)} MEDIUM  |  {len(low)} LOW")
    print(f"  NEW:     {len(new_matches)} new matching jobs since last run")
    print(f"{'='*60}")

    if high:
        print("\n TOP HIGH-RELEVANCE MATCHES:")
        for j in high[:5]:
            tag = " [NEW]" if j.get("is_new") else ""
            print(f"  [{j['score']}pts]{tag} {j['title']}")
            print(f"         {j['org']}  [{j['source']}]")
            print(f"         {j['url']}\n")

    # Bangalore spotlight first, then full India alert — sent to both Telegram & Discord
    blr_msg = build_bangalore_spotlight(new_matches, all_jobs)
    if blr_msg:
        print("\nSending Bangalore spotlight...")
        send_telegram(blr_msg)

    if new_matches:
        high_new   = [j for j in new_matches if j["relevance"] == "HIGH"]
        medium_new = [j for j in new_matches if j["relevance"] == "MEDIUM"]
        low_new    = [j for j in new_matches if j["relevance"] == "LOW"]

        messages = build_alert_messages(new_matches, len(all_jobs))
        print(f"\nSending alert for {len(new_matches)} new jobs ({len(messages)} message(s))...")
        for msg in messages:
            send_telegram(msg)
    else:
        print("\nNo new matching jobs. Sending daily summary...")
        send_summary_message(all_jobs)

    # Escalate only genuine breakage — a single blocked site is normal noise and
    # would otherwise nag every morning.
    if failed and (len(failed) >= 3 or not new_matches):
        warn = (
            "\u26a0\ufe0f <b>Job Alert — source trouble</b>\n"
            f"{len(failed)} of {len(sources)} sources failed this run:\n"
            + "\n".join(f"\u2022 {f}" for f in failed)
            + f"\n\nStill scraped {len(all_jobs)} jobs from the rest."
        )
        send_telegram(warn)

    # Apply by email to strong Bangalore matches; Telegram kits for the rest
    import auto_apply
    auto_apply.configure(DATA_DIR)
    auto_apply.run(new_matches, ai_call=_ai_call, fetch_page=fetch_page,
                   fetch_bytes=fetch_bytes, notify=send_telegram,
                   is_bangalore=lambda j: location_priority(j) == 0)

    # Save outputs
    out_dir   = os.path.dirname(os.path.abspath(__file__))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    save_csv(all_jobs,  os.path.join(out_dir, f"job_alert_{timestamp}.csv"))
    save_html(all_jobs, os.path.join(out_dir, f"job_alert_{timestamp}.html"))

    print("\nDone.")


if __name__ == "__main__":
    main()
