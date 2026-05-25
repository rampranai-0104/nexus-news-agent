import os
import sys
sys.path.append(os.path.dirname(__file__))

from core.logger import get_logger
from fetch.news_api import fetch_all_news
from ai.summarizer import summarize_news_list
from ai.categorizer import categorize_news_list
from db.database import init_db, save_news, get_news_by_category, mark_ran_today
import sqlite3

logger = get_logger("main")

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'news.db')

def clear_old_news():
    """Wipe articles from previous days so feed stays fresh."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM news")
        conn.commit()
        conn.close()
        logger.info("Cleared old news from database")
    except Exception as e:
        logger.error(f"Failed to clear news: {e}")

def run_pipeline(force=False):
    logger.info("=== Morning News Agent Starting ===")

    init_db()

    # Always clear old articles before fetching fresh ones
    clear_old_news()

    # Step 1 - Fetch
    print("\n[1/4] Fetching latest news (last 24 hours)...")
    news = fetch_all_news()
    print(f"  Fetched {len(news)} articles")

    if not news:
        print("  No articles fetched — check API key or internet.")
        return get_news_by_category()

    # Step 2 - Categorize
    print("\n[2/4] Categorizing...")
    news = categorize_news_list(news)

    # Step 3 - Summarize
    print("\n[3/4] Summarizing with AI...")
    news = summarize_news_list(news)

    # Step 4 - Save
    print("\n[4/4] Saving to database...")
    save_news(news)
    mark_ran_today()

    logger.info("Pipeline complete")
    print(f"\nPipeline complete! {len(news)} articles ready.")
    return news

if __name__ == "__main__":
    articles = run_pipeline(force=True)
    print(f"\n=== {len(articles)} Articles ===\n")
    for item in articles:
        print(f"[{item.get('category','?').upper()}] {item.get('title','')[:70]}")
        print(f"  Published: {item.get('published','')[:10]}  Source: {item.get('source','')}")
        print()