"""Source Credibility Scoring.

Maintains a tiered source registry and provides credibility scores
for domains encountered during evidence retrieval.
"""

from __future__ import annotations

from urllib.parse import urlparse

import structlog

from ..db.postgres import ClaimDB

logger = structlog.get_logger()

# ── In-memory cache of known sources (loaded on first use) ──────────

_SOURCE_CACHE: dict[str, dict] = {}

# Fallback hardcoded tier scores when DB is unavailable
TIER_SCORES = {
    "TIER_1": (0.90, 1.00),
    "TIER_2": (0.75, 0.89),
    "TIER_3": (0.50, 0.74),
    "UNKNOWN": (0.40, 0.40),
    "BLACKLISTED": (0.00, 0.00),
}

# ── Built-in known sources ──────────────────────────────────────────
# These ensure common domains get reasonable scores even without a DB.
KNOWN_SOURCES: dict[str, dict] = {
    # TIER 1 — Official / primary / global institutions
    "who.int":            {"tier": "TIER_1", "credibility": 0.95},
    "un.org":             {"tier": "TIER_1", "credibility": 0.93},
    "reuters.com":        {"tier": "TIER_1", "credibility": 0.94},
    "apnews.com":         {"tier": "TIER_1", "credibility": 0.94},
    "bbc.com":            {"tier": "TIER_2", "credibility": 0.89},
    "bbc.co.uk":          {"tier": "TIER_2", "credibility": 0.89},
    "india.gov.in":       {"tier": "TIER_1", "credibility": 0.90},
    "mea.gov.in":         {"tier": "TIER_1", "credibility": 0.90},
    "mha.gov.in":         {"tier": "TIER_1", "credibility": 0.88},
    "rbi.org.in":         {"tier": "TIER_1", "credibility": 0.92},
    "sebi.gov.in":        {"tier": "TIER_1", "credibility": 0.90},
    "mospi.gov.in":       {"tier": "TIER_1", "credibility": 0.90},
    "imd.gov.in":         {"tier": "TIER_1", "credibility": 0.90},
    "unicef.org":         {"tier": "TIER_1", "credibility": 0.94},
    "worldbank.org":      {"tier": "TIER_1", "credibility": 0.93},
    "imf.org":            {"tier": "TIER_1", "credibility": 0.93},
    "ec.europa.eu":       {"tier": "TIER_1", "credibility": 0.93},
    "europa.eu":          {"tier": "TIER_1", "credibility": 0.92},
    "gov.uk":             {"tier": "TIER_1", "credibility": 0.92},
    "noaa.gov":           {"tier": "TIER_1", "credibility": 0.92},
    "nih.gov":            {"tier": "TIER_1", "credibility": 0.92},
    "fda.gov":            {"tier": "TIER_1", "credibility": 0.91},
    "icrc.org":           {"tier": "TIER_1", "credibility": 0.91},

    # TIER 2 — Major international outlets / strong regional outlets / official Indian news feeds
    "cbc.ca":             {"tier": "TIER_2", "credibility": 0.82},
    "abc.net.au":         {"tier": "TIER_2", "credibility": 0.82},
    "dw.com":             {"tier": "TIER_2", "credibility": 0.80},
    "france24.com":       {"tier": "TIER_2", "credibility": 0.78},
    "aljazeera.com":      {"tier": "TIER_2", "credibility": 0.78},
    "scmp.com":           {"tier": "TIER_2", "credibility": 0.80},
    "nikkeiasia.com":     {"tier": "TIER_2", "credibility": 0.82},
    "straitstimes.com":   {"tier": "TIER_2", "credibility": 0.80},
    "aa.com.tr":          {"tier": "TIER_2", "credibility": 0.78},
    "english.elpais.com": {"tier": "TIER_2", "credibility": 0.78},
    "news24.com":         {"tier": "TIER_2", "credibility": 0.76},

    "ptinews.com":        {"tier": "TIER_2", "credibility": 0.86},
    "ddnews.gov.in":      {"tier": "TIER_2", "credibility": 0.85},
    "newsonair.gov.in":   {"tier": "TIER_2", "credibility": 0.84},

    "moneycontrol.com":   {"tier": "TIER_2", "credibility": 0.76},
    "newindianexpress.com":{"tier": "TIER_2", "credibility": 0.78},
    "deccanherald.com":   {"tier": "TIER_2", "credibility": 0.78},
    "telegraphindia.com": {"tier": "TIER_2", "credibility": 0.76},
    "tribuneindia.com":   {"tier": "TIER_2", "credibility": 0.76},
    "theprint.in":        {"tier": "TIER_2", "credibility": 0.74},
    "firstpost.com":      {"tier": "TIER_2", "credibility": 0.72},
    "thewire.in":         {"tier": "TIER_2", "credibility": 0.70},
    "aninews.in":         {"tier": "TIER_2", "credibility": 0.74},

    # TIER 3 — Niche / aggregators / social / lower-trust / experimental
    "news18.com":         {"tier": "TIER_3", "credibility": 0.68},
    "outlookindia.com":   {"tier": "TIER_3", "credibility": 0.66},
    "scroll.in":          {"tier": "TIER_3", "credibility": 0.70},
    "thequint.com":       {"tier": "TIER_3", "credibility": 0.62},
    "indiatoday.in":      {"tier": "TIER_3", "credibility": 0.68},
    "dailyhunt.in":       {"tier": "TIER_3", "credibility": 0.45},
    "inshorts.com":       {"tier": "TIER_3", "credibility": 0.40},
    "yahoo.com":          {"tier": "TIER_3", "credibility": 0.55},

    "linkedin.com":       {"tier": "TIER_3", "credibility": 0.50},
    "medium.com":         {"tier": "TIER_3", "credibility": 0.45},
    "quora.com":          {"tier": "TIER_3", "credibility": 0.35},
    "reddit.com":         {"tier": "TIER_3", "credibility": 0.35},
    "facebook.com":       {"tier": "TIER_3", "credibility": 0.30},
    "twitter.com":        {"tier": "TIER_3", "credibility": 0.35},
    "x.com":              {"tier": "TIER_3", "credibility": 0.35},

    "xinhuanet.com":      {"tier": "TIER_3", "credibility": 0.50},
    "globaltimes.cn":     {"tier": "TIER_3", "credibility": 0.40},
    "rt.com":             {"tier": "TIER_3", "credibility": 0.35},
    "sputniknews.com":    {"tier": "TIER_3", "credibility": 0.30},

    # BLACKLISTED — Troll / Satire / Parody / Known Fake News Outlets
    # India Satire & Troll
    "thefauxy.com":               {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Fauxy", "category": "satire"},
    "fauxy.com":                  {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Fauxy", "category": "satire"},
    "fakingnews.com":             {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Faking News", "category": "satire"},
    "fakingnews.firstpost.com":   {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Faking News", "category": "satire"},
    "theunrealtimes.com":         {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The UnReal Times", "category": "satire"},
    "unrealtimes.com":            {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The UnReal Times", "category": "satire"},
    "rhinoreview.com":            {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Rhino Review", "category": "satire"},
    "thefrustratedindian.com":    {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Frustrated Indian", "category": "troll"},
    "postcard.news":              {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Postcard News", "category": "fake_news"},
    "hindutva.info":              {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Hindutva Info", "category": "fake_news"},
    "dainik-bharat.com":          {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Dainik Bharat", "category": "fake_news"},
    "indiasamvad.co.in":          {"tier": "BLACKLISTED", "credibility": 0.0, "name": "India Samvad", "category": "fake_news"},

    # Global Satire & Parody Outlets
    "theonion.com":               {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Onion", "category": "satire"},
    "onion.com":                  {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Onion", "category": "satire"},
    "babylonbee.com":             {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Babylon Bee", "category": "satire"},
    "thebabylonbee.com":          {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Babylon Bee", "category": "satire"},
    "clickhole.com":              {"tier": "BLACKLISTED", "credibility": 0.0, "name": "ClickHole", "category": "satire"},
    "thehardtimes.net":           {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Hard Times", "category": "satire"},
    "hard-drive.net":             {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Hard Drive", "category": "satire"},
    "reductress.com":             {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Reductress", "category": "satire"},
    "thebeaverton.com":           {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Beaverton", "category": "satire"},
    "thechaser.com.au":           {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Chaser", "category": "satire"},
    "betootaadvocate.com":        {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Betoota Advocate", "category": "satire"},
    "theshovel.com.au":           {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Shovel", "category": "satire"},
    "waterfordwhispersnews.com":  {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Waterford Whispers News", "category": "satire"},
    "thedailymash.co.uk":         {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Daily Mash", "category": "satire"},
    "dailymash.co.uk":            {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Daily Mash", "category": "satire"},
    "thepoke.co.uk":              {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Poke", "category": "satire"},
    "newsbiscuit.com":            {"tier": "BLACKLISTED", "credibility": 0.0, "name": "NewsBiscuit", "category": "satire"},
    "newsthump.com":              {"tier": "BLACKLISTED", "credibility": 0.0, "name": "NewsThump", "category": "satire"},
    "thespoof.com":               {"tier": "BLACKLISTED", "credibility": 0.0, "name": "The Spoof", "category": "satire"},
    "der-postillon.com":          {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Der Postillon", "category": "satire"},
    "le-gorafi.fr":               {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Le Gorafi", "category": "satire"},
    "elmundotoday.com":           {"tier": "BLACKLISTED", "credibility": 0.0, "name": "El Mundo Today", "category": "satire"},
    "duffelblog.com":             {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Duffel Blog", "category": "satire"},
    "burrardstreetjournal.com":   {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Burrard Street Journal", "category": "satire"},

    # Notorious Global Fabricated / Disinformation / Hoax Sites
    "worldnewsdailyreport.com":   {"tier": "BLACKLISTED", "credibility": 0.0, "name": "World News Daily Report", "category": "hoax"},
    "huzlers.com":                {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Huzlers", "category": "troll"},
    "empirenews.net":             {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Empire News", "category": "hoax"},
    "nationalreport.net":         {"tier": "BLACKLISTED", "credibility": 0.0, "name": "National Report", "category": "fake_news"},
    "naturalnews.com":            {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Natural News", "category": "fake_news"},
    "infowars.com":               {"tier": "BLACKLISTED", "credibility": 0.0, "name": "InfoWars", "category": "conspiracy"},
    "beforeitsnews.com":          {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Before It's News", "category": "conspiracy"},
    "newspunch.com":              {"tier": "BLACKLISTED", "credibility": 0.0, "name": "NewsPunch", "category": "fake_news"},
    "yournewswire.com":           {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Your News Wire", "category": "fake_news"},
    "dailybuzzlive.com":          {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Daily Buzz Live", "category": "fake_news"},
    "prntly.com":                 {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Prntly", "category": "fake_news"},
    "witscience.org":             {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Wit Science", "category": "satire"},
    "breakyourownnews.com":       {"tier": "BLACKLISTED", "credibility": 0.0, "name": "Break Your Own News", "category": "generator"},
}

# Domain keyword substrings that strongly signal satire / parody / troll sites
SATIRE_KEYWORDS = (
    "fauxy",
    "theonion",
    "babylonbee",
    "clickhole",
    "fakingnews",
    "unrealtimes",
    "betoota",
    "dailymash",
    "waterfordwhispers",
    "worldnewsdailyreport",
    "huzlers",
)


def extract_domain(url: str) -> str:
    """Extract the base domain from a URL or raw domain string."""
    try:
        if not url:
            return ""
        url_to_parse = url.strip()
        if "://" not in url_to_parse:
            url_to_parse = "http://" + url_to_parse
        parsed = urlparse(url_to_parse)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if ":" in domain:
            domain = domain.split(":")[0]
        return domain
    except Exception:
        return ""


def is_blacklisted(url_or_domain: str) -> bool:
    """Check if a URL or domain is blacklisted / troll / satire (credibility 0.0)."""
    domain = extract_domain(url_or_domain)
    if not domain:
        return False

    # Exact domain match in KNOWN_SOURCES
    if domain in KNOWN_SOURCES and KNOWN_SOURCES[domain].get("tier") == "BLACKLISTED":
        return True

    # Check parent domain (e.g. "news.theonion.com" -> "theonion.com")
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in KNOWN_SOURCES and KNOWN_SOURCES[parent].get("tier") == "BLACKLISTED":
            return True

    # Keyword heuristic matching across domain segments
    if any(kw in domain for kw in SATIRE_KEYWORDS):
        return True

    # Check if explicitly marked as satire/parody in domain (e.g. "satirenews.com")
    domain_labels = domain.replace("-", ".").split(".")
    if "satire" in domain_labels or "parody" in domain_labels:
        return True

    return False


def is_satire_or_troll(url_or_domain: str) -> bool:
    """Check if a URL or domain is a known satire, parody, or troll news site."""
    return is_blacklisted(url_or_domain)


async def get_credibility(url: str) -> dict:
    """
    Get the credibility score and tier for a URL's domain.

    Returns dict with: domain, name, tier, credibility, category
    """
    domain = extract_domain(url)
    if not domain:
        return {
            "domain": "",
            "name": "Unknown",
            "tier": "UNKNOWN",
            "credibility": 0.40,
            "category": "unknown",
        }

    # Check in-memory cache first
    if domain in _SOURCE_CACHE:
        return _SOURCE_CACHE[domain]

    # Fast-path check: Is it a blacklisted / satire / troll source?
    if is_blacklisted(domain):
        known_meta = KNOWN_SOURCES.get(domain, {})
        result = {
            "domain": domain,
            "name": known_meta.get("name", domain),
            "tier": "BLACKLISTED",
            "credibility": 0.00,
            "category": known_meta.get("category", "satire"),
        }
        _SOURCE_CACHE[domain] = result
        return result

    # Check database
    try:
        source = await ClaimDB.get_source_credibility(domain)
        if source:
            # If DB marked it as BLACKLISTED, ensure credibility is 0.0
            if source.get("tier") == "BLACKLISTED":
                source["credibility"] = 0.00
            _SOURCE_CACHE[domain] = source
            return source
    except Exception as e:
        logger.debug("credibility.db_error", domain=domain, error=str(e))

    # Check built-in known sources
    if domain in KNOWN_SOURCES:
        known = KNOWN_SOURCES[domain]
        result = {
            "domain": domain,
            "name": known.get("name", domain),
            "tier": known["tier"],
            "credibility": known["credibility"],
            "category": known.get("category", "news"),
        }
        _SOURCE_CACHE[domain] = result
        return result

    # Check if a parent domain matches (e.g., "news.bbc.co.uk" → "bbc.co.uk")
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in KNOWN_SOURCES:
            known = KNOWN_SOURCES[parent]
            result = {
                "domain": domain,
                "name": known.get("name", domain),
                "tier": known["tier"],
                "credibility": known["credibility"],
                "category": known.get("category", "news"),
            }
            _SOURCE_CACHE[domain] = result
            return result

    # Default: unknown source — give a baseline of 0.40
    result = {
        "domain": domain,
        "name": domain,
        "tier": "UNKNOWN",
        "credibility": 0.40,
        "category": "unknown",
    }
    _SOURCE_CACHE[domain] = result
    return result


def is_primary_source(url: str, claim_entities: list[str]) -> bool:
    """
    Heuristic: determine if a URL is likely a primary source.

    Primary sources include:
    - Government domains (.gov)
    - Organization domains matching claim entities
    - Press release pages
    - Academic/journal sources

    Blacklisted / satire / troll sources are NEVER considered primary sources.
    """
    domain = extract_domain(url)
    if not domain or is_blacklisted(domain):
        return False

    url_lower = url.lower()

    # Government sites (.gov, .gov.uk, .gov.in)
    if domain.endswith(".gov") or domain.endswith(".gov.uk") or domain.endswith(".gov.in"):
        return True

    # International organizations and official national institutions
    primary_domains = {
        "who.int", "un.org", "europa.eu", "imf.org", "worldbank.org",
        "rbi.org.in", "unicef.org", "icrc.org"
    }
    if domain in primary_domains:
        return True

    # Press releases
    if any(term in url_lower for term in ["press-release", "pressrelease", "media-release", "news-release"]):
        return True

    # Academic journals
    academic_domains = {"nature.com", "science.org", "thelancet.com", "nejm.org", "arxiv.org"}
    if domain in academic_domains:
        return True

    # Check if domain matches any claim entity
    for entity in claim_entities:
        entity_lower = entity.lower().replace(" ", "")
        domain_clean = domain.replace(".", "").replace("-", "")
        if entity_lower and (entity_lower in domain_clean or domain_clean in entity_lower):
            return True

    return False
