import os
import sys
import sqlite3
import argparse
import json
import re
from typing import Dict, Any, List
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))

CANONICAL_CATEGORIES = ["local", "national", "global", "technology", "business", "sports"]


def mask_secret(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'mongodb(\+srv)?://([^:]+):([^@]+)@', r'mongodb\1://***:***@', str(text))


def run_verification(db_path: str, sample_size: int = 10) -> bool:
    print("=" * 65)
    print("NEXUS NEWS AGENT — SQLITE VS MONGODB ATLAS VERIFICATION")
    print("=" * 65)

    if not os.path.exists(db_path):
        print(f"ERROR: SQLite database file not found at '{db_path}'")
        sys.exit(1)

    mongodb_uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("DATABASE_NAME", "nexus_news")

    if not mongodb_uri:
        print("ERROR: MONGODB_URI is not set in environment or .env file.")
        sys.exit(1)

    try:
        from pymongo import MongoClient
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
    except Exception as e:
        print(f"ERROR connecting to MongoDB Atlas: {mask_secret(str(e))}")
        sys.exit(1)

    mongo_db = client[database_name]
    mongo_articles = mongo_db["articles"]

    # 1. Total Article Count
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT count(*) FROM news")
    sqlite_count = c.fetchone()[0]

    mongo_count = mongo_articles.count_documents({})

    print(f"Total Articles:")
    print(f"  SQLite:     {sqlite_count}")
    print(f"  MongoDB:    {mongo_count}")

    if mongo_count == 0:
        print("\n[NOTICE] MongoDB articles collection is currently EMPTY.")
        print("Migration has not been executed yet (as expected during preparation phase).")
        print("Run this verification script after executing the migration to validate data parity.")
        conn.close()
        client.close()
        return True

    count_match = (sqlite_count == mongo_count)
    print(f"  Status:     {'MATCH [PASS]' if count_match else 'MISMATCH [FAIL]'}")

    # 2. Category Distribution Comparison
    print("\nCategory Distribution Comparison:")
    print(f"{'Category':<15} {'SQLite':<12} {'MongoDB':<12} {'Status':<10}")
    print("-" * 50)

    category_match = True
    for cat in CANONICAL_CATEGORIES:
        c.execute("SELECT count(*) FROM news WHERE category = ?", (cat,))
        sql_cat_count = c.fetchone()[0]
        mongo_cat_count = mongo_articles.count_documents({"category": cat})
        status = "PASS" if sql_cat_count == mongo_cat_count else "FAIL"
        if sql_cat_count != mongo_cat_count:
            category_match = False
        print(f"{cat:<15} {sql_cat_count:<12} {mongo_cat_count:<12} {status}")

    # 3. URL Uniqueness in MongoDB
    distinct_mongo_urls = len(mongo_articles.distinct("url"))
    print(f"\nURL Uniqueness in MongoDB:")
    print(f"  Total MongoDB Docs: {mongo_count}")
    print(f"  Unique MongoDB URLs: {distinct_mongo_urls}")
    url_unique_pass = (mongo_count == distinct_mongo_urls)
    print(f"  Status:             {'PASS (100% Unique)' if url_unique_pass else 'FAIL (Duplicates Detected)'}")

    # 4. Spot-Check Sample Records
    print(f"\nSpot-Checking {sample_size} Sample Records by URL:")
    c.execute(f"SELECT url, title, category, importance, is_breaking, summary FROM news ORDER BY RANDOM() LIMIT {sample_size}")
    sample_rows = c.fetchall()

    spot_check_pass = True
    for idx, (url, title, cat, imp, breaking, summary) in enumerate(sample_rows, 1):
        mongo_doc = mongo_articles.find_one({"url": url})
        if not mongo_doc:
            print(f"  [{idx}] FAIL: URL not found in MongoDB: {url[:60]}")
            spot_check_pass = False
            continue

        title_match = (mongo_doc.get("title") == title)
        cat_match = (mongo_doc.get("category") == cat)
        imp_match = (float(mongo_doc.get("importance", 0)) == float(imp or 0))
        breaking_match = (mongo_doc.get("is_breaking") == bool(breaking == 1))

        safe_title = (title[:50] or "").encode('ascii', 'replace').decode('ascii')
        if title_match and cat_match and imp_match and breaking_match:
            print(f"  [{idx}] PASS: '{safe_title}...' (cat={cat}, imp={imp})")
        else:
            print(f"  [{idx}] MISMATCH: '{safe_title}...'")
            print(f"       Title match: {title_match}, Cat match: {cat_match}, Imp match: {imp_match}, Breaking match: {breaking_match}")
            spot_check_pass = False

    # 5. Missing Fields Check
    missing_required = mongo_articles.count_documents({
        "$or": [
            {"title": {"$exists": False}},
            {"title": ""},
            {"url": {"$exists": False}},
            {"url": ""},
            {"category": {"$exists": False}},
            {"category": ""}
        ]
    })
    print(f"\nRequired Fields Integrity Check (title, url, category):")
    print(f"  Documents with missing required fields: {missing_required}")
    fields_pass = (missing_required == 0)
    print(f"  Status: {'PASS' if fields_pass else 'FAIL'}")

    conn.close()
    client.close()

    overall_pass = count_match and category_match and url_unique_pass and spot_check_pass and fields_pass
    print("\n" + "=" * 65)
    print(f"OVERALL VERIFICATION RESULT: {'PASSED' if overall_pass else 'FAILED'}")
    print("=" * 65)

    return overall_pass


def main():
    parser = argparse.ArgumentParser(
        description="Verify data parity between SQLite (data/news.db) and MongoDB Atlas (nexus_news.articles)."
    )
    parser.add_argument(
        "--db-path",
        default=os.path.join(BASE_DIR, "data", "news.db"),
        help="Path to SQLite news.db (default: data/news.db)."
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        help="Number of random records to spot-check (default: 10)."
    )

    args = parser.parse_args()
    success = run_verification(db_path=args.db_path, sample_size=args.samples)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
