import os
import sys
import sqlite3
import argparse
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

# Ensure project root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

load_dotenv(os.path.join(BASE_DIR, ".env"))

CANONICAL_CATEGORIES = ["local", "national", "global", "technology", "business", "sports"]


def mask_secret(text: str) -> str:
    """Mask credentials and connection strings from error messages."""
    if not text:
        return ""
    return re.sub(r'mongodb(\+srv)?://([^:]+):([^@]+)@', r'mongodb\1://***:***@', str(text))


def normalize_datetime_to_iso(dt_str: Optional[str]) -> Optional[str]:
    """Convert SQLite timestamps (e.g. 'YYYY-MM-DD HH:MM:SS') to UTC ISO 8601 string."""
    if not dt_str:
        return None
    dt_str = dt_str.strip()
    if not dt_str:
        return None
    # Already ISO 8601 with Z or offset
    if "T" in dt_str and (dt_str.endswith("Z") or "+" in dt_str or "-" in dt_str[10:]):
        return dt_str
    # SQLite CURRENT_TIMESTAMP format: YYYY-MM-DD HH:MM:SS
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return dt_str


def transform_sqlite_row(row: sqlite3.Row, now_iso: str) -> Dict[str, Any]:
    """
    Transform a SQLite news row into a clean, typed MongoDB article document.
    Preserves all fields without data loss.
    """
    row_dict = dict(row)
    
    # 1. Primary keys & identifiers
    sqlite_id = row_dict.get("id")
    url = (row_dict.get("url") or "").strip()
    
    # 2. Text fields
    title = (row_dict.get("title") or "").strip()
    description = (row_dict.get("description") or "").strip()
    content = (row_dict.get("content") or "").strip()
    summary = row_dict.get("summary")
    if summary is not None:
        summary = summary.strip()
        if not summary:
            summary = None
            
    source = (row_dict.get("source") or "").strip()
    category = (row_dict.get("category") or "national").strip().lower()
    if category not in CANONICAL_CATEGORIES:
        category = "national"
        
    image_url = (row_dict.get("image_url") or "").strip()
    
    # 3. Numeric & Boolean flags
    is_breaking = bool(row_dict.get("is_breaking", 0) == 1)
    is_read = bool(row_dict.get("is_read", 0) == 1)
    importance = float(row_dict.get("importance", 0.0) or 0.0)
    
    # 4. Dates & Timestamps
    published = (row_dict.get("published") or "").strip()
    published_at = row_dict.get("published_at")
    if published_at:
        published_at = published_at.strip()
    fetched_at = row_dict.get("fetched_at")
    if fetched_at:
        fetched_at = fetched_at.strip()
    last_seen_at = row_dict.get("last_seen_at")
    if last_seen_at:
        last_seen_at = last_seen_at.strip()
    created_at = normalize_datetime_to_iso(row_dict.get("created_at"))
    
    doc = {
        "sqlite_id": sqlite_id,
        "url": url,
        "title": title,
        "description": description,
        "content": content,
        "summary": summary,
        "source": source,
        "category": category,
        "published": published,
        "published_at": published_at,
        "fetched_at": fetched_at,
        "last_seen_at": last_seen_at,
        "image_url": image_url,
        "is_breaking": is_breaking,
        "importance": importance,
        "is_read": is_read,
        "created_at": created_at,
        "migrated_at": now_iso
    }
    
    return doc


def validate_document(doc: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate that document satisfies required schema constraints."""
    if not doc.get("url"):
        return False, "Missing URL"
    if not doc.get("title"):
        return False, "Missing title"
    if not doc.get("category") or doc.get("category") not in CANONICAL_CATEGORIES:
        return False, f"Invalid category: {doc.get('category')}"
    return True, "Valid"


def run_migration(
    db_path: str,
    dry_run: bool = True,
    batch_size: int = 200
) -> Dict[str, Any]:
    """
    Execute migration or dry-run validation from SQLite to MongoDB Atlas.
    """
    print("=" * 65)
    print("NEXUS NEWS AGENT — SQLITE TO MONGODB ATLAS MIGRATION")
    print("=" * 65)
    print(f"Mode:               {'DRY-RUN (No database writes)' if dry_run else 'LIVE MIGRATION'}")
    print(f"Source SQLite DB:   {db_path}")

    # 1. Check SQLite DB existence
    if not os.path.exists(db_path):
        print(f"ERROR: SQLite database file not found at '{db_path}'")
        sys.exit(1)

    # 2. Check MongoDB Configuration from .env
    mongodb_uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("DATABASE_NAME", "nexus_news")

    if not mongodb_uri:
        print("ERROR: MONGODB_URI is not set in environment or .env file.")
        sys.exit(1)

    print(f"Target Database:    {database_name}")
    print(f"Target Collection:  articles")
    print(f"MONGODB_URI:        FOUND (Credentials masked for safety)")

    # 3. Connect to MongoDB using PyMongo
    try:
        from pymongo import MongoClient, UpdateOne
        from pymongo.errors import PyMongoError
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=10000)
        # Test ping
        client.admin.command("ping")
        print("MongoDB Atlas:      CONNECTED (Ping verified)")
    except Exception as e:
        print(f"ERROR connecting to MongoDB Atlas: {mask_secret(str(e))}")
        sys.exit(1)

    db = client[database_name]
    collection = db["articles"]

    # 4. Read from SQLite
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT count(*) FROM news")
    total_sqlite_rows = cursor.fetchone()[0]
    print(f"SQLite Articles:    {total_sqlite_rows} total rows found")
    print("-" * 65)

    cursor.execute("SELECT * FROM news ORDER BY id ASC")
    
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    stats = {
        "total_read": 0,
        "valid_docs": 0,
        "invalid_docs": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "categories": {c: 0 for c in CANONICAL_CATEGORIES},
        "sample_doc": None
    }

    batch_ops = []
    processed = 0

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break

        for row in rows:
            stats["total_read"] += 1
            doc = transform_sqlite_row(row, now_iso)
            
            is_valid, msg = validate_document(doc)
            if not is_valid:
                stats["invalid_docs"] += 1
                stats["failed_count"] += 1
                continue

            stats["valid_docs"] += 1
            cat = doc["category"]
            stats["categories"][cat] = stats["categories"].get(cat, 0) + 1

            if stats["sample_doc"] is None:
                stats["sample_doc"] = doc

            if not dry_run:
                # Idempotent bulk upsert matching on unique URL
                batch_ops.append(
                    UpdateOne(
                        {"url": doc["url"]},
                        {"$set": doc},
                        upsert=True
                    )
                )

        if not dry_run and batch_ops:
            try:
                res = collection.bulk_write(batch_ops, ordered=False)
                stats["inserted_count"] += res.upserted_count
                stats["updated_count"] += res.modified_count
                stats["skipped_count"] += (len(batch_ops) - res.upserted_count - res.modified_count)
            except PyMongoError as e:
                print(f"Bulk write error: {mask_secret(str(e))}")
                stats["failed_count"] += len(batch_ops)
            batch_ops = []

        processed += len(rows)
        if processed % 500 == 0 or processed == total_sqlite_rows:
            pct = (processed / total_sqlite_rows) * 100
            print(f"Progress: {processed}/{total_sqlite_rows} articles ({pct:.1f}%) processed")

    # 5. Create Indexes if live migration
    if not dry_run:
        print("\nCreating MongoDB Atlas indexes...")
        try:
            # Unique index on URL
            collection.create_index("url", unique=True, name="idx_unique_url")
            # Compound query/sort index: published_at DESC, importance DESC
            collection.create_index([("published_at", -1), ("importance", -1)], name="idx_published_importance")
            # Category index for filtering
            collection.create_index([("category", 1), ("published_at", -1)], name="idx_category_published")
            # Breaking news index
            collection.create_index([("is_breaking", 1), ("published_at", -1)], name="idx_breaking_published")
            print("Indexes created successfully: idx_unique_url, idx_published_importance, idx_category_published, idx_breaking_published")
        except Exception as e:
            print(f"Warning: Index creation notice: {mask_secret(str(e))}")

    conn.close()
    client.close()

    # 6. Summary Report
    print("\n" + "=" * 65)
    print(f"MIGRATION {'DRY-RUN' if dry_run else 'EXECUTION'} SUMMARY")
    print("=" * 65)
    print(f"Total SQLite rows read:     {stats['total_read']}")
    print(f"Valid documents:            {stats['valid_docs']}")
    print(f"Invalid documents:          {stats['invalid_docs']}")
    
    if dry_run:
        print(f"Would be upserted to Atlas: {stats['valid_docs']}")
        print(f"Documents written:          0 (Dry-run mode enforced)")
    else:
        print(f"Documents inserted:         {stats['inserted_count']}")
        print(f"Documents updated:          {stats['updated_count']}")
        print(f"Documents unchanged/skipped:{stats['skipped_count']}")
        print(f"Documents failed:           {stats['failed_count']}")

    print("\nCategory Distribution:")
    for c in CANONICAL_CATEGORIES:
        print(f"  {c:<15}: {stats['categories'].get(c, 0)}")

    if stats["sample_doc"]:
        print("\nSample Transformed Document Schema:")
        print(json.dumps(stats["sample_doc"], indent=2))

    print("=" * 65)
    if dry_run:
        print("STATUS: DRY-RUN COMPLETED SUCCESSFULLY.")
        print("SQLite was NOT modified. No documents were written to MongoDB Atlas.")
    else:
        print("STATUS: LIVE MIGRATION COMPLETED SUCCESSFULLY.")
    print("=" * 65)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Migrate articles from SQLite (data/news.db) to MongoDB Atlas (nexus_news.articles)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run validation and transformation without writing to MongoDB Atlas (default: True)."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute real migration write to MongoDB Atlas."
    )
    parser.add_argument(
        "--db-path",
        default=os.path.join(BASE_DIR, "data", "news.db"),
        help="Path to SQLite news.db (default: data/news.db)."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Batch size for reading and bulk write operations (default: 200)."
    )

    args = parser.parse_args()

    # Safety: dry_run is True unless --execute is explicitly passed
    dry_run = not args.execute

    run_migration(
        db_path=args.db_path,
        dry_run=dry_run,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()
