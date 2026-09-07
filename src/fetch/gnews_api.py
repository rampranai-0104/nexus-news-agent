import requests
import datetime
from config import GNEWS_API_KEY
from core.logger import get_logger
from fetch.scraper import scrape_article
from fetch.source_tracker import source_tracker
from utils.date_parser import normalize_article_dates

logger = get_logger("gnews_api")

def fetch_gnews(location=None):
    """
    Fetch news from GNews API with timeout and health tracking.
    Returns list of normalized article dicts.
    """
    if not GNEWS_API_KEY:
        logger.info("No GNEWS_API_KEY provided. Skipping GNews fetch.")
        return []
        
    if source_tracker.should_skip("gnews.io"):
        logger.info("Skipping temporarily failing GNews API")
        return []
        
    articles_result = []
    categories = ["general", "world", "nation", "business", "technology", "sports"]
    country = "in"
    if location and location.get("country") == "US":
        country = "us"
        
    for cat in categories:
        try:
            url = f"https://gnews.io/api/v4/top-headlines?category={cat}&lang=en&country={country}&max=15&apikey={GNEWS_API_KEY}"
            res = requests.get(url, timeout=8)
            res.raise_for_status()
            data = res.json()
            
            source_tracker.record_success("gnews.io")
            for a in data.get("articles", []):
                formatted = format_article(a, category=cat)
                if formatted:
                    articles_result.append(formatted)
                    
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "Unknown"
            source_tracker.record_failure("gnews.io", f"HTTP {status}")
            logger.warning(f"GNews fetch failed for category {cat} (HTTP {status})")
            if status in [401, 403, 429]:
                # Don't try remaining categories if rate-limited or key invalid
                break
        except requests.exceptions.Timeout:
            source_tracker.record_failure("gnews.io", "Timeout (8s)")
            logger.warning(f"GNews timed out for category {cat}")
            break
        except Exception as e:
            source_tracker.record_failure("gnews.io", str(e))
            logger.warning(f"GNews fetch error for category {cat}: {e}")
            
    return articles_result

def format_article(api_article, category="general"):
    title = api_article.get("title")
    if not title:
        return None
        
    title = title.strip()
    description = api_article.get("description", "") or ""
    content = api_article.get("content", "") or ""
    url = api_article.get("url")
    
    cat_map = {
        "nation": "national",
        "world": "global"
    }
    mapped_cat = cat_map.get(category, category)
    
    if len(description) < 80 and url:
        scraped_content = scrape_article(url)
        if scraped_content:
            content = scraped_content
            
    raw_published = api_article.get("publishedAt")
    source_name = api_article.get("source", {}).get("name", "GNews")
    
    article = {
        "title": title,
        "description": description.strip(),
        "content": content,
        "url": url,
        "source": source_name,
        "image_url": api_article.get("image", "") or "",
        "category": mapped_cat,
        "feed_category": mapped_cat
    }
    
    normalize_article_dates(article, raw_published=raw_published)
    return article
