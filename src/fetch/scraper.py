import requests
from bs4 import BeautifulSoup
import re

# Helper to detect boilerplate, subscription, paywall, ads, cookie notices, navigation, newsletter prompts
def is_boilerplate(text: str) -> bool:
    """Return True if the given text looks like boilerplate or unrelated content."""
    if not text:
        return True
    lowered = text.lower()
    boilerplate_terms = [
        "subscribe", "subscription", "premium", "paywall", "login",
        "read more", "continue reading", "advertisement", "ad", "cookie",
        "newsletter", "sign up", "terms of use", "privacy policy",
        "navigation", "menu", "footer", "header"
    ]
    if any(term in lowered for term in boilerplate_terms):
        return True
    words = text.split()
    if len(words) < 6:
        return True
    return False
from urllib.parse import urlparse
from core.logger import get_logger
from fetch.source_tracker import source_tracker

logger = get_logger("scraper")

blocked_domains = set()

def scrape_article(url, timeout=4):
    """
    Scrape the main content of an article given its URL.
    Returns cleaned text or empty string on failure.
    Uses strict 4-second timeout to avoid blocking ingestion.
    """
    if not url:
        return ""
        
    domain = urlparse(url).netloc
    if domain in blocked_domains or source_tracker.should_skip(domain):
        return ""
        
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Remove unwanted tags
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'button', 'iframe', 'noscript']):
            tag.decompose()
            
        # Find paragraphs
        paragraphs = soup.find_all('p')
        text_blocks = []
        
        for p in paragraphs:
            text = p.get_text().strip()
            # Filter out short or junk paragraphs (cookie notices, etc)
            if not is_boilerplate(text):
                text_blocks.append(text)
                
        content = " ".join(text_blocks)
        content = re.sub(r'\s+', ' ', content).strip()
        
        if content:
            source_tracker.record_success(domain)
        return content
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "Unknown"
        source_tracker.record_failure(domain, f"HTTP {status}")
        if status in [401, 403, 404, 429]:
            blocked_domains.add(domain)
        return ""
    except requests.exceptions.Timeout:
        source_tracker.record_failure(domain, "Timeout (4s)")
        return ""
    except Exception as e:
        source_tracker.record_failure(domain, type(e).__name__)
        return ""
