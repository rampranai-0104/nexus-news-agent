import requests
import datetime
from config import NEWSAPI_KEY
from core.logger import get_logger
from fetch.scraper import scrape_article
from fetch.source_tracker import source_tracker
from utils.date_parser import normalize_article_dates
from utils.text_utils import clean_text, is_boilerplate_text, clean_boilerplate_from_content

logger = get_logger("news_api")

def fetch_newsapi(location=None):
    """
    Fetch news from NewsAPI with error handling and health tracking.
    Uses location for local news if provided.
    Returns list of normalized article dicts.
    """
    if not NEWSAPI_KEY:
        logger.info("No NEWSAPI_KEY provided. Skipping NewsAPI fetch.")
        return []
        
    if source_tracker.should_skip("newsapi.org"):
        logger.info("Skipping temporarily failing NewsAPI")
        return []
        
    articles_result = []
    
    # 1. Fetch Top Headlines (India / User Country)
    country = "in"
    if location and location.get("country") == "US":
        country = "us"
        
    try:
        url_top = f"https://newsapi.org/v2/top-headlines?country={country}&apiKey={NEWSAPI_KEY}"
        res = requests.get(url_top, timeout=8)
        res.raise_for_status()
        data = res.json()
        if data.get("status") == "ok":
            source_tracker.record_success("newsapi.org")
            for a in data.get("articles", []):
                formatted = format_article(a, category="national")
                if formatted:
                    articles_result.append(formatted)
        else:
            source_tracker.record_failure("newsapi.org", data.get("message", "API status not ok"))
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "Unknown"
        source_tracker.record_failure("newsapi.org", f"HTTP {status}")
        logger.warning(f"NewsAPI Top Headlines failed (HTTP {status})")
    except requests.exceptions.Timeout:
        source_tracker.record_failure("newsapi.org", "Timeout (8s)")
        logger.warning("NewsAPI Top Headlines timed out")
    except Exception as e:
        source_tracker.record_failure("newsapi.org", str(e))
        logger.warning(f"NewsAPI Top Headlines failed: {e}")
        
    # 2. Fetch Local News (Based on location)
    if location and not source_tracker.should_skip("newsapi.org"):
        city = location.get("city", "")
        state = location.get("state", "")
        if city or state:
            query = f'"{city}" OR "{state}"' if city and state else f'"{city or state}"'
            try:
                url_local = f"https://newsapi.org/v2/everything?q={query}&sortBy=publishedAt&language=en&apiKey={NEWSAPI_KEY}"
                res = requests.get(url_local, timeout=8)
                res.raise_for_status()
                data = res.json()
                if data.get("status") == "ok":
                    for a in data.get("articles", [])[:15]:
                        formatted = format_article(a, category="local")
                        if formatted:
                            articles_result.append(formatted)
            except Exception as e:
                logger.warning(f"NewsAPI Local News failed: {e}")
            
    return articles_result

def format_article(api_article, category="general"):
    title = api_article.get("title")
    if not title or title == "[Removed]":
        return None
        
    title = clean_text(title)
    description = clean_text(api_article.get("description", "") or "")
    if is_boilerplate_text(description):
        description = ""
        
    url = api_article.get("url")
    content = clean_boilerplate_from_content(api_article.get("content", "") or "")
    
    if len(description) < 80 and url:
        scraped_content = scrape_article(url)
        if scraped_content:
            cleaned_scraped = clean_boilerplate_from_content(scraped_content)
            if cleaned_scraped:
                content = cleaned_scraped
            
    source_name = api_article.get("source", {}).get("name", "NewsAPI")
    raw_published = api_article.get("publishedAt")
    
    article = {
        "title": title,
        "description": description,
        "content": content,
        "url": url,
        "source": source_name,
        "image_url": api_article.get("urlToImage", "") or "",
        "category": category,
        "feed_category": category
    }
    
    normalize_article_dates(article, raw_published=raw_published)
    return article