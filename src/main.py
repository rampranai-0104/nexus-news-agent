import sys
import os
import time
import datetime

sys.path.append(os.path.dirname(__file__))

from fetch.geolocator import get_current_location
from fetch.rss_parser import fetch_all_rss
from fetch.gnews_api import fetch_gnews
from fetch.news_api import fetch_newsapi
from fetch.source_tracker import source_tracker
from ai.headline_cleaner import clean_all_headlines
from utils.deduplicator import deduplicate
from utils.news_ranker import rank_articles
from ai.categorizer import categorize_news_list
from utils.breaking_news import detect_breaking
from db.database import save_news, mark_ran_today, get_db_stats, cleanup_expired_articles
from core.logger import get_logger
from config import get_config

logger = get_logger("pipeline")

def safe_fetch(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Fetch function {func.__name__} failed: {e}")
        return []

def run_pipeline(progress_callback=None):
    """
    Full agent news ingestion and refinement pipeline.
    Returns: dict with status, articles, and rich metadata.
    """
    start_time = datetime.datetime.now(datetime.timezone.utc)
    
    def report(stage, pct):
        if progress_callback:
            try:
                progress_callback(stage, pct)
            except Exception:
                pass
            
    config = get_config()
    preferences = config.get("preferred_categories", [])
    
    # 1. Detect location
    report("Detecting location", 5)
    location = get_current_location()
    
    # 2. Fetch from ALL sources with isolation
    report("Fetching news", 15)
    rss_news = safe_fetch(fetch_all_rss)
    gnews_news = safe_fetch(fetch_gnews, location)
    api_news = safe_fetch(fetch_newsapi, location)
    
    raw_news = rss_news + gnews_news + api_news
    
    if not raw_news:
        logger.warning("No raw articles fetched from any source.")
        report("No sources available — pipeline finished", 100)
        return {
            "status": "warning",
            "articles": [],
            "meta": {
                "fetched": 0,
                "new_articles": 0,
                "duplicates": 0,
                "updated": 0,
                "updated_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        }
        
    # 3. Clean headlines
    report("Cleaning headlines", 30)
    raw_news = clean_all_headlines(raw_news)
    
    # 4. Deduplicate
    report("Removing duplicates", 40)
    unique = deduplicate(raw_news)
    
    # 5. Categorize
    report("Categorizing articles", 50)
    categorized = categorize_news_list(unique)
    
    # 6. Rank
    report("Ranking articles", 65)
    ranked = rank_articles(categorized, location, preferences)
    
    # 7. Detect breaking news
    report("Detecting breaking news", 80)
    all_articles = detect_breaking(ranked)
    
    # 8. Re-rank after breaking news detection
    report("Finalizing importance", 90)
    final = rank_articles(all_articles, location, preferences)
    
    # 9. Save to database
    report("Saving to database", 95)
    db_stats = save_news(final)
    mark_ran_today()
    
    # 10. 7-Day Automatic Retention Cleanup
    report("Cleaning expired articles (>7 days)", 98)
    cleanup_stats = cleanup_expired_articles(days=7)
    
    end_time = datetime.datetime.now(datetime.timezone.utc)
    total_db_info = get_db_stats()
    health_summary = source_tracker.get_summary()
    
    # 11. Structured summary log (Requirement #16)
    summary_log = f"""
    ==================================================
    Nexus News Ingestion Pipeline Summary
    ==================================================
    Refresh started at:       {start_time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    Refresh completed at:     {end_time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    Duration:                 {(end_time - start_time).total_seconds():.2f}s
    
    Sources Tracked:          {health_summary['total_tracked']}
    Sources Healthy:          {health_summary['healthy']}
    Sources Failing:          {health_summary['failing']}
    
    Articles fetched:         {len(raw_news)}
    Deduplicated pool:        {len(unique)}
    New articles saved:       {db_stats.get('new_articles', 0)}
    Duplicates encountered:   {db_stats.get('duplicates', 0)}
    Updated articles:         {db_stats.get('updated', 0)}
    Articles purged (>7d):    {cleanup_stats.get('deleted', 0)}
    
    Database total articles:  {total_db_info.get('total_articles', 0)}
    Newest article timestamp: {db_stats.get('newest_published_at') or total_db_info.get('newest_published')}
    ==================================================
    """
    logger.info(summary_log)
    
    meta = {
        "fetched": len(raw_news),
        "new_articles": db_stats.get("new_articles", 0),
        "duplicates": db_stats.get("duplicates", 0),
        "updated": db_stats.get("updated", 0),
        "articles_purged": cleanup_stats.get("deleted", 0),
        "database_total": total_db_info.get("total_articles", 0),
        "newest_published_at": db_stats.get("newest_published_at") or total_db_info.get("newest_published"),
        "updated_at": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources_tracked": health_summary["total_tracked"],
        "sources_healthy": health_summary["healthy"],
        "sources_failing": health_summary["failing"]
    }
    
    report("Completed", 100)
    return {
        "status": "success",
        "articles": final,
        "meta": meta
    }

if __name__ == "__main__":
    def print_progress(stage, pct):
        print(f"[{pct}%] {stage}")
        
    result = run_pipeline(progress_callback=print_progress)
    print("Pipeline result meta:", result.get("meta"))