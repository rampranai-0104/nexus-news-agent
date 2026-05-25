import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.logger import get_logger

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logger = get_logger("news_api")
API_KEY = os.getenv("NEWSAPI_KEY")
BASE_URL = "https://newsapi.org/v2"

TODAY     = datetime.now().strftime("%Y-%m-%d")
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

CATEGORY_QUERIES = {
    "sports":     "IPL 2026 OR cricket India OR sports India",
    "technology": "artificial intelligence OR technology India 2026",
    "business":   "India economy OR stock market OR business India",
    "national":   "India government OR Modi OR India news today",
    "global":     "world news OR international OR global today",
    "local":      "Andhra Pradesh OR Telangana OR Vijayawada OR Hyderabad",
}
def scrape_full_article(url):
    """Scrape full article text from URL, filtering out navigation junk."""
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

        import re
        html = response.text

        # Remove script, style, nav, header, footer blocks
        for tag in ['script', 'style', 'nav', 'header', 'footer',
                    'aside', 'menu', 'noscript', 'form', 'button']:
            html = re.sub(
                rf'<{tag}[^>]*>.*?</{tag}>', '', html,
                flags=re.DOTALL | re.IGNORECASE
            )

        # Extract paragraph text
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, flags=re.DOTALL)

        # Clean and filter paragraphs
        JUNK_PHRASES = [
            "sign in", "log in", "subscribe", "newsletter", "cookie",
            "privacy policy", "terms of use", "all rights reserved",
            "follow us", "click here", "read more", "advertisement",
            "daily discussion", "newquiz", "epaper", "personalise",
            "dark mode", "abc news", "cnn.com", "times of india",
            "please let us know", "abc account", "listen", "iview",
            "download app", "get app", "install app", "push notification",
            "breaking news alert", "follow system settings",
            "log in to your", "already a member", "create account"
        ]

        clean_paras = []
        for p in paragraphs:
            # Remove HTML tags
            clean = re.sub(r'<[^>]+>', '', p).strip()

            # Decode HTML entities
            clean = (clean
                     .replace('&nbsp;', ' ')
                     .replace('&amp;', '&')
                     .replace('&lt;', '<')
                     .replace('&gt;', '>')
                     .replace('&quot;', '"')
                     .replace('&#39;', "'"))

            # Skip short paragraphs
            if len(clean) < 50:
                continue

            # Skip paragraphs with too many words concatenated (navbar dump)
            # Real sentences have spaces — junk has very few spaces relative to length
            space_ratio = clean.count(' ') / max(len(clean), 1)
            if space_ratio < 0.05:
                continue

            # Skip junk phrases
            clean_lower = clean.lower()
            if any(phrase in clean_lower for phrase in JUNK_PHRASES):
                continue

            clean_paras.append(clean)

        full_text = " ".join(clean_paras[:15])

        if len(full_text) > 200:
            logger.info(f"Scraped {len(full_text)} chars from article")
            return full_text

        return ""

    except Exception as e:
        logger.warning(f"Scraping failed for {url}: {e}")
        return ""
def fetch_category(category):
    try:
        url    = f"{BASE_URL}/everything"
        params = {
            "apiKey":   API_KEY,
            "q":        CATEGORY_QUERIES[category],
            "language": "en",
            "sortBy":   "publishedAt",
            "from":     YESTERDAY,
            "to":       TODAY,
            "pageSize": 3,
        }
        response = requests.get(url, params=params, timeout=10)
        data     = response.json()

        if data.get("status") == "ok":
            articles  = data.get("articles", [])
            news_list = []
            for a in articles:
                if "[Removed]" in (a.get("title") or ""):
                    continue

                article_url = a.get("url", "")

                # Try to scrape full article
                print(f"    Scraping: {a.get('title','')[:50]}...")
                full_text = scrape_full_article(article_url)

                # Use full text if scraped, else fall back to description
                content = full_text if full_text else a.get("description", "")

                news_list.append({
                    "title":       a.get("title", "No Title"),
                    "description": a.get("description", ""),
                    "content":     content,   # full article text for summarizer
                    "source":      a.get("source", {}).get("name", "Unknown"),
                    "url":         article_url,
                    "category":    category,
                    "published":   a.get("publishedAt", ""),
                })

            logger.info(f"Fetched {len(news_list)} articles for: {category}")
            return news_list
        else:
            logger.error(f"API error [{category}]: {data.get('message')}")
            return []

    except Exception as e:
        logger.error(f"Failed to fetch [{category}]: {e}")
        return []

def fetch_all_news():
    all_news = []

    # Primary — RSS feeds (real-time, no limits)
    print("\n[RSS] Fetching real-time RSS feeds...")
    try:
        from fetch.rss_parser import fetch_all_rss
        rss_articles = fetch_all_rss()
        all_news.extend(rss_articles)
        logger.info(f"RSS fetched: {len(rss_articles)} articles")
    except Exception as e:
        logger.error(f"RSS fetch failed: {e}")

    # Secondary — NewsAPI (fills gaps if RSS has fewer articles)
    print("\n[NewsAPI] Fetching backup articles...")
    for category in CATEGORY_QUERIES:
        # Skip if RSS already gave us enough for this category
        existing = [a for a in all_news if a.get("category") == category]
        if len(existing) >= 5:
            logger.info(f"Skipping NewsAPI for {category} — RSS has enough")
            continue
        news = fetch_category(category)
        all_news.extend(news)

    logger.info(f"Total fetched: {len(all_news)} articles")
    return all_news


if __name__ == "__main__":
    news = fetch_all_news()
    for item in news:
        print(f"\n[{item['category'].upper()}] {item['title']}")
        print(f"  Content length: {len(item.get('content',''))} chars")
        print(f"  Content preview: {item.get('content','')[:100]}...")