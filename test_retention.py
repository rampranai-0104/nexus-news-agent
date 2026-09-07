import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import sqlite3

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))
load_dotenv(os.path.join(BASE_DIR, ".env"))

from db.database import cleanup_expired_articles, get_articles_collection, DB_BACKEND

BASE_URL = "http://127.0.0.1:8000"


def test_retention():
    print("=== STARTING 7-DAY NEWS RETENTION TESTS ===")

    assert DB_BACKEND == "mongodb", f"Expected active DB_BACKEND to be 'mongodb', got '{DB_BACKEND}'"
    col = get_articles_collection()

    now_utc = datetime.now(timezone.utc)
    ten_days_ago = (now_utc - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    two_days_ago = (now_utc - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Insert controlled test articles
    print("\n--- 1. Testing Published_at Exclusivity (not fetched_at/last_seen_at) ---")
    test_articles = [
        # Article A: Published 10 days ago, but fetched & last_seen NOW -> MUST BE DELETED
        {
            "url": "https://test.nexusnews.local/article-a-old-published",
            "title": "TEST ARTICLE A: Old Published, Recent Fetched",
            "category": "technology",
            "published_at": ten_days_ago,
            "fetched_at": now_iso,
            "last_seen_at": now_iso,
            "is_test_marker": True
        },
        # Article B: Published 2 days ago, but fetched 10 days ago -> MUST BE KEPT
        {
            "url": "https://test.nexusnews.local/article-b-recent-published",
            "title": "TEST ARTICLE B: Recent Published, Old Fetched",
            "category": "technology",
            "published_at": two_days_ago,
            "fetched_at": ten_days_ago,
            "last_seen_at": ten_days_ago,
            "is_test_marker": True
        },
        # Article C: No published_at date, fetched 10 days ago -> MUST BE KEPT
        {
            "url": "https://test.nexusnews.local/article-c-no-date",
            "title": "TEST ARTICLE C: No Published Date",
            "category": "technology",
            "published_at": None,
            "fetched_at": ten_days_ago,
            "last_seen_at": ten_days_ago,
            "is_test_marker": True
        }
    ]

    for doc in test_articles:
        col.delete_one({"url": doc["url"]})
        col.insert_one(doc)

    print(f"Inserted 3 controlled test articles (A: published -10d, B: published -2d, C: published None)")

    # 2. Run cleanup function
    print("\n--- 2. Executing cleanup_expired_articles(days=7) ---")
    stats = cleanup_expired_articles(days=7)
    print("Cleanup stats:", stats)

    assert "deleted" in stats, "Missing 'deleted' key in stats"
    assert "cutoff" in stats, "Missing 'cutoff' key in stats"
    assert stats["retention_days"] == 7, "Expected retention_days=7"
    assert stats["deleted"] >= 1, "Expected at least Article A to be deleted"

    # 3. Verify Article A is deleted
    doc_a = col.find_one({"url": "https://test.nexusnews.local/article-a-old-published"})
    assert doc_a is None, "FAILURE: Article A (published 10 days ago) was NOT deleted!"
    print("[PASS] Article A (published 10 days ago, fetched today) was correctly DELETED.")

    # 4. Verify Article B is preserved
    doc_b = col.find_one({"url": "https://test.nexusnews.local/article-b-recent-published"})
    assert doc_b is not None, "FAILURE: Article B (published 2 days ago) was incorrectly deleted!"
    print("[PASS] Article B (published 2 days ago, fetched 10 days ago) was correctly PRESERVED.")

    # 5. Verify Article C is preserved
    doc_c = col.find_one({"url": "https://test.nexusnews.local/article-c-no-date"})
    assert doc_c is not None, "FAILURE: Article C (no published_at) was incorrectly deleted!"
    print("[PASS] Article C (no published_at date) was correctly PRESERVED.")

    # Clean up test markers
    col.delete_many({"is_test_marker": True})
    print("Cleaned up temporary test marker articles.")

    # 6. Verify HTTP maintenance endpoint POST /data/cleanup-expired
    print("\n--- 3. Testing HTTP API POST /data/cleanup-expired ---")
    res = requests.post(f"{BASE_URL}/data/cleanup-expired?days=7")
    assert res.status_code == 200, f"Endpoint failed: {res.status_code} {res.text}"
    api_data = res.json()
    assert api_data.get("status") == "success"
    assert "data" in api_data
    assert api_data["data"]["retention_days"] == 7
    print(f"[PASS] POST /data/cleanup-expired returned HTTP 200: {api_data['message']}")

    # 7. Verify SQLite rollback reference database is completely untouched
    print("\n--- 4. Verifying SQLite news.db is Untouched ---")
    conn = sqlite3.connect(os.path.join(BASE_DIR, "data", "news.db"))
    c = conn.cursor()
    c.execute("SELECT count(*) FROM news")
    sqlite_count = c.fetchone()[0]
    conn.close()
    assert sqlite_count == 1850, f"SQLite database count modified! Expected 1850, got {sqlite_count}"
    print(f"[PASS] SQLite data/news.db count is {sqlite_count} (completely UNTOUCHED).")

    print("\n=== ALL 7-DAY NEWS RETENTION TESTS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    test_retention()
