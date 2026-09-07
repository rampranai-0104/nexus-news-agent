import datetime
import re
import warnings
from dateutil import parser
from core.logger import get_logger

logger = get_logger("date_parser")

# Timezone mapping for common abbreviations to avoid UnknownTimezoneWarning
TZ_INFOS = {
    "UTC": datetime.timezone.utc,
    "GMT": datetime.timezone.utc,
    "Z": datetime.timezone.utc,
    "IST": datetime.timezone(datetime.timedelta(hours=5, minutes=30)),
    "EST": datetime.timezone(datetime.timedelta(hours=-5)),
    "EDT": datetime.timezone(datetime.timedelta(hours=-4)),
    "CST": datetime.timezone(datetime.timedelta(hours=-6)),
    "CDT": datetime.timezone(datetime.timedelta(hours=-5)),
    "MST": datetime.timezone(datetime.timedelta(hours=-7)),
    "MDT": datetime.timezone(datetime.timedelta(hours=-6)),
    "PST": datetime.timezone(datetime.timedelta(hours=-8)),
    "PDT": datetime.timezone(datetime.timedelta(hours=-7)),
    "BST": datetime.timezone(datetime.timedelta(hours=1)),
    "CET": datetime.timezone(datetime.timedelta(hours=1)),
    "CEST": datetime.timezone(datetime.timedelta(hours=2)),
}

def parse_to_utc_iso(date_input):
    """
    Safely parse a date string or datetime object into a normalized UTC ISO 8601 string.
    Format: YYYY-MM-DDTHH:MM:SSZ
    Returns None if date cannot be reliably parsed (DO NOT fabricate using current time).
    """
    if not date_input:
        return None
        
    if isinstance(date_input, datetime.datetime):
        if date_input.tzinfo is None:
            date_input = date_input.replace(tzinfo=datetime.timezone.utc)
        return date_input.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
    if not isinstance(date_input, str):
        return None
        
    cleaned = date_input.strip()
    if not cleaned:
        return None
        
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            parsed = parser.parse(cleaned, tzinfos=TZ_INFOS)
            
        if parsed.tzinfo is None:
            # Assume UTC if no timezone is specified
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            
        utc_dt = parsed.astimezone(datetime.timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        logger.debug(f"Could not parse date '{cleaned}': {e}")
        return None

def normalize_article_dates(article, raw_published=None, raw_updated=None):
    """
    Implements the Safe Date Hierarchy:
    1. published_at <- raw_published
    2. published_at <- raw_updated (if published is missing/unparseable)
    3. published_at <- None (if no reliable date exists)
    
    fetched_at <- current UTC time
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    pub_iso = parse_to_utc_iso(raw_published)
    if not pub_iso and raw_updated:
        pub_iso = parse_to_utc_iso(raw_updated)
        
    article["published_at"] = pub_iso
    article["published"] = pub_iso or "" # backwards compatibility
    article["fetched_at"] = now_utc
    return article
