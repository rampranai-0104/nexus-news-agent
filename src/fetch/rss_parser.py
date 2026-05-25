import feedparser
import os
import sys
import re
import requests
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.logger import get_logger

logger = get_logger("rss_parser")

# Multiple sources per category — mixed so no single source dominates
RSS_FEEDS = {
    "national": [
        ("The Hindu",       "https://www.thehindu.com/news/national/feeder/default.rss"),
        ("NDTV",            "https://feeds.feedburner.com/ndtvnews-india-news"),
        ("Indian Express",  "https://indianexpress.com/section/india/feed/"),
        ("Hindustan Times", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"),
        ("Times of India",  "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms"),
    ],
    "global": [
        ("BBC World",       "http://feeds.bbci.co.uk/news/world/rss.xml"),
        ("The Hindu",       "https://www.thehindu.com/news/international/feeder/default.rss"),
        ("Indian Express",  "https://indianexpress.com/section/world/feed/"),
        ("NDTV World",      "https://feeds.feedburner.com/ndtvnews-world-news"),
        ("Times of India",  "https://timesofindia.indiatimes.com/rssfeeds/296589294.cms"),
    ],
    "sports": [
        ("Indian Express",  "https://indianexpress.com/section/sports/feed/"),
        ("Times of India",  "https://timesofindia.indiatimes.com/rssfeeds/4719148.cms"),
        ("The Hindu",       "https://www.thehindu.com/sport/feeder/default.rss"),
        ("NDTV Sports",     "https://feeds.feedburner.com/ndtvnews-sports"),
        ("BBC Sport",       "http://feeds.bbci.co.uk/sport/rss.xml"),
    ],
    "technology": [
        ("Indian Express",  "https://indianexpress.com/section/technology/feed/"),
        ("NDTV Tech",       "https://feeds.feedburner.com/ndtvnews-tech"),
        ("The Hindu",       "https://www.thehindu.com/sci-tech/technology/feeder/default.rss"),
        ("TechCrunch",      "https://techcrunch.com/feed/"),
        ("Times of India",  "https://timesofindia.indiatimes.com/rssfeeds/66949542.cms"),
    ],
    "business": [
        ("Economic Times",  "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
        ("Indian Express",  "https://indianexpress.com/section/business/feed/"),
        ("The Hindu",       "https://www.thehindu.com/business/feeder/default.rss"),
        ("NDTV Business",   "https://feeds.feedburner.com/ndtvnews-business"),
        ("Times of India",  "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms"),
    ],
    "local": [
        ("The Hindu AP",    "https://www.thehindu.com/news/national/andhra-pradesh/feeder/default.rss"),
        ("The Hindu TS",    "https://www.thehindu.com/news/national/telangana/feeder/default.rss"),
        ("News Minute",     "https://www.thenewsminute.com/feed"),
        ("Indian Express Hyd", "https://indianexpress.com/section/cities/hyderabad/feed/"),
        ("Telangana Today", "https://telanganatoday.com/feed"),
    ],
}

def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = (text
            .replace('&nbsp;', ' ')
            .replace('&amp;', '&')
            .replace('&lt;', '<')
            .replace('&gt;', '>')
            .replace('&quot;', '"')
            .replace('&#39;', "'"))
    return text.strip()

def scrape_full_article(url):
    try:
        if not url:
            return ""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code != 200:
            return ""

        html = response.text
        for tag in ['script', 'style', 'nav', 'header', 'footer',
                    'aside', 'menu', 'noscript', 'form', 'button']:
            html = re.sub(
                rf'<{tag}[^>]*>.*?</{tag}>', '', html,
                flags=re.DOTALL | re.IGNORECASE
            )

        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, flags=re.DOTALL)

        JUNK_PHRASES = [
            "sign in", "log in", "subscribe", "newsletter", "cookie",
            "privacy policy", "terms of use", "all rights reserved",
            "follow us", "click here", "advertisement", "download app",
            "push notification", "breaking news alert", "create account",
            "already a member", "install app", "get app"
        ]

        clean_paras = []
        for p in paragraphs:
            clean = re.sub(r'<[^>]+>', '', p).strip()
            clean = (clean
                     .replace('&nbsp;', ' ')
                     .replace('&amp;', '&')
                     .replace('&lt;', '<')
                     .replace('&gt;', '>')
                     .replace('&quot;', '"')
                     .replace('&#39;', "'"))
            if len(clean) < 50:
                continue
            space_ratio = clean.count(' ') / max(len(clean), 1)
            if space_ratio < 0.05:
                continue
            if any(phrase in clean.lower() for phrase in JUNK_PHRASES):
                continue
            clean_paras.append(clean)

        full_text = " ".join(clean_paras[:15])
        if len(full_text) > 200:
            return full_text
        return ""

    except Exception as e:
        logger.warning(f"Scraping failed for {url}: {e}")
        return ""


def fetch_rss_category(category, articles_per_source=1, target=5):
    """
    Fetch from ALL sources — 1 article per source by default.
    This ensures variety — no single source dominates.
    """
    feeds      = RSS_FEEDS.get(category, [])
    articles   = []
    seen_titles = set()

    for source_name, feed_url in feeds:
        if len(articles) >= target:
            break
        try:
            print(f"    [{source_name}] Fetching...")
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                logger.warning(f"No entries: {feed_url}")
                continue

            count = 0
            for entry in feed.entries:
                if count >= articles_per_source:
                    break

                title = clean_html(entry.get("title", ""))
                if not title or "[Removed]" in title:
                    continue

                # Skip duplicates
                title_key = title.lower()[:60]
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)

                description = clean_html(
                    entry.get("summary", "") or
                    entry.get("description", "")
                )
                url = entry.get("link", "")

                print(f"    Scraping: {title[:50]}...")
                content = scrape_full_article(url)

                articles.append({
                    "title":       title,
                    "description": description,
                    "content":     content if content else description,
                    "source":      source_name,
                    "url":         url,
                    "category":    category,
                    "published":   entry.get("published", ""),
                })
                count += 1

            logger.info(f"[{category}] Got {count} from {source_name}")

        except Exception as e:
            logger.error(f"Feed failed [{source_name}]: {e}")
            continue

    # If we don't have enough, get more from available sources
    if len(articles) < target:
        needed = target - len(articles)
        for source_name, feed_url in feeds:
            if needed <= 0:
                break
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[articles_per_source:]:
                    if needed <= 0:
                        break
                    title = clean_html(entry.get("title", ""))
                    if not title:
                        continue
                    title_key = title.lower()[:60]
                    if title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)

                    description = clean_html(
                        entry.get("summary", "") or
                        entry.get("description", "")
                    )
                    url = entry.get("link", "")
                    content = scrape_full_article(url)

                    articles.append({
                        "title":       title,
                        "description": description,
                        "content":     content if content else description,
                        "source":      source_name,
                        "url":         url,
                        "category":    category,
                        "published":   entry.get("published", ""),
                    })
                    needed -= 1
            except:
                continue

    logger.info(f"[{category}] Final count: {len(articles)}")
    return articles[:target]


def fetch_all_rss():
    all_articles = []
    for category in RSS_FEEDS:
        print(f"\n  Fetching [{category.upper()}]...")
        # 1 article per source × 5 sources = 5 varied articles
        articles = fetch_rss_category(
            category,
            articles_per_source=1,
            target=5
        )
        all_articles.extend(articles)
        print(f"  Got {len(articles)} articles for {category}")

    logger.info(f"Total: {len(all_articles)} articles")
    return all_articles


if __name__ == "__main__":
    print("Testing RSS parser...\n")
    articles = fetch_all_rss()
    print(f"\n--- {len(articles)} total articles ---\n")
    for a in articles:
        print(f"[{a['category'].upper():12}] [{a['source']:20}] {a['title'][:50]}")