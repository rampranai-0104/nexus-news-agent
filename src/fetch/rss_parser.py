import requests
import feedparser
import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from core.logger import get_logger
from fetch.scraper import scrape_article
from fetch.source_tracker import source_tracker
from utils.date_parser import normalize_article_dates
from utils.text_utils import clean_text, is_boilerplate_text, clean_boilerplate_from_content

logger = get_logger("rss_parser")

RSS_FEEDS = {
    "local": [
        "https://www.thehindu.com/news/cities/Hyderabad/feeder/default.rss",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128833038.cms"
    ],
    "national": [
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://www.thehindu.com/news/national/feeder/default.rss"
    ],
    "global": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml"
    ],
    "technology": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml"
    ],
    "business": [
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
        "https://www.thehindubusinessline.com/news/feeder/default.rss"
    ],
    "sports": [
        "https://www.espn.com/espn/rss/news",
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.thehindu.com/sport/feeder/default.rss"
    ]
}

def fetch_all_rss():
    """
    Fetch news from configured RSS feeds with timeout protection and source health tracking.
    Gracefully handles individual feed failures.
    Returns list of normalized article dicts.
    """
    articles_result = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*"
    }
    
    for category, feeds in RSS_FEEDS.items():
        for feed_url in feeds:
            domain = urlparse(feed_url).netloc
            if source_tracker.should_skip(feed_url):
                logger.info(f"Skipping recently failed feed: {feed_url}")
                continue
                
            try:
                # Fetch feed with strict 8-second timeout
                res = requests.get(feed_url, headers=headers, timeout=8)
                res.raise_for_status()
                
                feed = feedparser.parse(res.content)
                
                if getattr(feed, 'bozo', 0) == 1 and not feed.entries:
                    reason = getattr(feed, 'bozo_exception', 'Malformed XML')
                    source_tracker.record_failure(feed_url, f"Parse error: {reason}")
                    logger.warning(f"Failed to parse RSS feed {feed_url}: {reason}")
                    continue
                    
                source_tracker.record_success(feed_url)
                source_title = feed.feed.get("title", domain)
                
                # Take top 25 from each feed to ensure broad fresh coverage
                for entry in feed.entries[:25]:
                    title = entry.get("title")
                    if not title:
                        continue
                        
                    title = clean_text(title)
                    description = entry.get("summary", entry.get("description", ""))
                    
                    # Clean HTML from description if present
                    if "<" in description and ">" in description:
                        description = BeautifulSoup(description, "html.parser").get_text()
                    description = clean_text(description)
                    if is_boilerplate_text(description):
                        description = ""
                    
                    url = entry.get("link", "")
                    
                    # Optional scrape if description is very brief
                    content = ""
                    if len(description) < 80 and url:
                        scraped = scrape_article(url)
                        if scraped:
                            content = clean_boilerplate_from_content(scraped)
                        
                    # Extract images
                    image_url = ""
                    if "media_content" in entry and entry.media_content:
                        image_url = entry.media_content[0].get("url", "")
                    elif "enclosures" in entry and entry.enclosures:
                        for enc in entry.enclosures:
                            if "image" in enc.get("type", ""):
                                image_url = enc.get("href", "")
                                break
                    elif "media_thumbnail" in entry and entry.media_thumbnail:
                        image_url = entry.media_thumbnail[0].get("url", "")
                        
                    raw_published = entry.get("published")
                    raw_updated = entry.get("updated")
                    
                    article = {
                        "title": title,
                        "description": description,
                        "content": content,
                        "url": url,
                        "source": source_title,
                        "image_url": image_url,
                        "category": category,
                        "feed_category": category
                    }
                    
                    # Apply Safe Date Hierarchy
                    normalize_article_dates(article, raw_published=raw_published, raw_updated=raw_updated)
                    articles_result.append(article)
                    
            except requests.exceptions.Timeout:
                source_tracker.record_failure(feed_url, "Timeout (8s)")
                logger.warning(f"Timeout (8s) fetching RSS feed {feed_url}")
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else "Unknown"
                source_tracker.record_failure(feed_url, f"HTTP {status}")
                logger.warning(f"HTTP {status} fetching RSS feed {feed_url}")
            except Exception as e:
                source_tracker.record_failure(feed_url, f"{type(e).__name__}: {e}")
                logger.warning(f"Error fetching RSS feed {feed_url}: {type(e).__name__} - {e}")
                
    return articles_result