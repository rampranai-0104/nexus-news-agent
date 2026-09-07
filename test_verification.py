import sys
import os
import datetime
import requests
import json

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from utils.date_parser import parse_to_utc_iso, normalize_article_dates
from db.database import init_db, save_news, get_news_paginated, get_breaking_news, get_db_stats

def test_date_parser():
    print("--- 1. Testing Date Parser Hierarchy & Timezone Safety ---")
    # Test RFC 2822 with various timezones
    d1 = parse_to_utc_iso("Tue, 01 Sep 2026 08:30:00 GMT")
    assert d1 == "2026-09-01T08:30:00Z", f"Expected 2026-09-01T08:30:00Z, got {d1}"
    
    d2 = parse_to_utc_iso("Tue, 01 Sep 2026 14:00:00 +0530")
    assert d2 == "2026-09-01T08:30:00Z", f"Expected 2026-09-01T08:30:00Z, got {d2}"
    
    d3 = parse_to_utc_iso("Tue, 01 Sep 2026 04:30:00 EDT")
    assert d3 == "2026-09-01T08:30:00Z", f"Expected 2026-09-01T08:30:00Z, got {d3}"
    
    # Test invalid / missing date -> must return None (NEVER fabricate current time)
    d_invalid = parse_to_utc_iso("invalid date string")
    assert d_invalid is None, f"Expected None for invalid date, got {d_invalid}"
    
    d_none = parse_to_utc_iso(None)
    assert d_none is None, f"Expected None for None input, got {d_none}"
    
    # Test normalization hierarchy
    art = {"title": "Test Article"}
    normalize_article_dates(art, raw_published="invalid", raw_updated="Tue, 01 Sep 2026 08:30:00 GMT")
    assert art["published_at"] == "2026-09-01T08:30:00Z"
    assert art["fetched_at"] is not None
    
    art2 = {"title": "No Date Article"}
    normalize_article_dates(art2, raw_published=None, raw_updated=None)
    assert art2["published_at"] is None, "published_at must be None when no date exists"
    assert art2["fetched_at"] is not None, "fetched_at must be populated"
    print("[PASS] Date Parser passed all assertions.")

def test_db_upsert_and_sorting():
    print("\n--- 2. Testing DB Migration, Upsert & Newest-First Sorting ---")
    init_db()
    
    test_articles = [
        {
            "title": "Older Breaking Story",
            "url": "https://example.com/old-story",
            "category": "technology",
            "published_at": "2026-09-01T01:00:00Z",
            "fetched_at": "2026-09-01T08:00:00Z",
            "importance": 90.0,
            "is_breaking": 1
        },
        {
            "title": "Brand New Normal Story",
            "url": "https://example.com/new-story",
            "category": "technology",
            "published_at": "2026-09-01T08:00:00Z",
            "fetched_at": "2026-09-01T08:00:00Z",
            "importance": 50.0,
            "is_breaking": 0
        }
    ]
    
    stats = save_news(test_articles)
    print(f"Save Stats: {stats}")
    assert stats["new_articles"] >= 1 or stats["duplicates"] >= 1
    
    # Re-inserting the same articles should update last_seen_at and count duplicates
    stats2 = save_news(test_articles)
    print(f"Second Save Stats (Duplicates): {stats2}")
    assert stats2["duplicates"] == 2, f"Expected 2 duplicates, got {stats2['duplicates']}"
    assert stats2["new_articles"] == 0, f"Expected 0 new articles, got {stats2['new_articles']}"
    
    # Verify sorting: 'Brand New Normal Story' (published at 08:00) must appear before 'Older Breaking Story' (01:00) in paginated news
    articles, total = get_news_paginated(category="technology", search="Story", limit=10)
    titles = [a["title"] for a in articles if a["url"] in ["https://example.com/old-story", "https://example.com/new-story"]]
    print(f"Retrieved ordering: {titles}")
    assert titles == ["Brand New Normal Story", "Older Breaking Story"], f"Sorting failed: expected newest first, got {titles}"
    
    print("[PASS] DB upsert & latest-first sorting passed all assertions.")

if __name__ == "__main__":
    test_date_parser()
    test_db_upsert_and_sorting()
    print("\nAll verification tests completed successfully!")
