import os
import sys
import re
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv
import sqlite3

# Try importing psycopg2 (optional PostgreSQL driver)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

# Import PyMongo
try:
    from pymongo import MongoClient
    from bson import ObjectId
except ImportError:
    MongoClient = None
    ObjectId = None

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.logger import get_logger
from config import DB_PATH, DATABASE_URL

logger = get_logger("database")

# Ensure .env is loaded
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Active Database Configuration
# Default to "mongodb". Setting DB_BACKEND=sqlite in .env provides instant rollback.
DB_BACKEND = os.getenv("DB_BACKEND", "mongodb").lower().strip()

CANONICAL_CATEGORIES = ["local", "national", "global", "technology", "business", "sports"]

# Singleton MongoDB Client & Connection Lock
_mongo_client: Optional[Any] = None
_mongo_lock = threading.Lock()


def mask_secret(text: str) -> str:
    """Mask MongoDB connection string credentials for safe logging."""
    if not text:
        return ""
    return re.sub(r'mongodb(\+srv)?://([^:]+):([^@]+)@', r'mongodb\1://***:***@', str(text))


# ==============================================================================
# MONGODB CONNECTION MANAGEMENT
# ==============================================================================

def get_mongo_client() -> Any:
    """
    Returns the reusable singleton MongoClient instance.
    Never opens a new connection per request.
    Configured with strict timeouts and connection pooling.
    """
    global _mongo_client
    if _mongo_client is not None:
        return _mongo_client

    with _mongo_lock:
        if _mongo_client is not None:
            return _mongo_client

        if MongoClient is None:
            raise RuntimeError("PyMongo is not installed. Please install pymongo to use MongoDB Atlas.")

        mongodb_uri = os.getenv("MONGODB_URI")
        if not mongodb_uri:
            raise RuntimeError("MONGODB_URI environment variable is not configured.")

        try:
            logger.info("Initializing singleton MongoDB Atlas client...")
            client = MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=10000,
                maxPoolSize=50,
                minPoolSize=5
            )
            # Connectivity check (ping)
            client.admin.command("ping")
            _mongo_client = client
            logger.info("Connected to MongoDB Atlas successfully.")
            return _mongo_client
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"MongoDB Atlas connection failure: {masked_err}")
            # Strict safety: Do not silently fall back to SQLite in production when MongoDB fails.
            raise RuntimeError(f"MongoDB Atlas is unreachable: {masked_err}")


def get_mongo_db() -> Any:
    """Returns the MongoDB database instance using DATABASE_NAME from environment."""
    client = get_mongo_client()
    database_name = os.getenv("DATABASE_NAME", "nexus_news")
    return client[database_name]


def get_articles_collection() -> Any:
    """Returns the 'articles' collection from MongoDB Atlas."""
    db = get_mongo_db()
    return db["articles"]


def get_preferences_collection() -> Any:
    """Returns the 'user_preferences' collection from MongoDB Atlas."""
    db = get_mongo_db()
    return db["user_preferences"]


def get_connection() -> Tuple[Any, str]:
    """
    Returns active database connection and backend type:
    - 'mongodb' -> (MongoClient, 'mongodb')
    - 'sqlite'  -> (sqlite3.Connection, 'sqlite')
    - 'postgres' -> (psycopg2.Connection, 'postgres')
    """
    if DB_BACKEND == "mongodb":
        return get_mongo_client(), "mongodb"
    elif DATABASE_URL and psycopg2:
        conn = psycopg2.connect(DATABASE_URL)
        return conn, "postgres"
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"


# ==============================================================================
# DOCUMENT SERIALIZATION / COMPATIBILITY
# ==============================================================================

def _doc_to_article(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a MongoDB document into an API/Frontend compatible dictionary.
    - Stringifies BSON ObjectId _id.
    - Populates integer or string 'id' for existing callers.
    """
    if not doc:
        return {}
    article = dict(doc)
    if "_id" in article:
        article["_id"] = str(article["_id"])

    # ID compatibility: preserve numeric sqlite_id as 'id', or fallback to string _id
    if "sqlite_id" in article and article["sqlite_id"] is not None:
        article["id"] = int(article["sqlite_id"])
    elif "_id" in article:
        article["id"] = article["_id"]

    return article


# ==============================================================================
# DATABASE INITIALIZATION & INDEXES
# ==============================================================================

def init_db():
    """
    Initialize database schema and required indexes.
    - For MongoDB: Ensures required indexes on 'articles' and 'user_preferences'.
    - For SQLite/PostgreSQL: Creates tables and indexes if not existing.
    """
    if DB_BACKEND == "mongodb":
        try:
            articles = get_articles_collection()
            # 1. Unique URL index
            articles.create_index([("url", 1)], unique=True, name="idx_unique_url")
            # 2. Published + importance
            articles.create_index([("published_at", -1), ("importance", -1)], name="idx_published_importance")
            # 3. Category + published
            articles.create_index([("category", 1), ("published_at", -1)], name="idx_category_published")
            # 4. Breaking + published
            articles.create_index([("is_breaking", 1), ("published_at", -1)], name="idx_breaking_published")

            # Preferences index
            prefs = get_preferences_collection()
            prefs.create_index([("key", 1)], unique=True, name="idx_pref_key")

            logger.info("MongoDB Atlas database initialized and indexes verified.")
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"MongoDB Atlas init_db failed: {masked_err}")
            raise
        return

    # Fallback / Rollback SQLite & PostgreSQL Schema Setup
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()

        if db_type == "postgres":
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news (
                    id           SERIAL PRIMARY KEY,
                    title        TEXT NOT NULL,
                    description  TEXT,
                    content      TEXT,
                    summary      TEXT,
                    source       TEXT,
                    url          TEXT UNIQUE,
                    category     TEXT DEFAULT 'general',
                    published    TEXT,
                    published_at TEXT,
                    fetched_at   TEXT,
                    last_seen_at TEXT,
                    image_url    TEXT,
                    is_breaking  INTEGER DEFAULT 0,
                    importance   REAL DEFAULT 0,
                    is_read      INTEGER DEFAULT 0,
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id SERIAL PRIMARY KEY,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    title        TEXT NOT NULL,
                    description  TEXT,
                    content      TEXT,
                    summary      TEXT,
                    source       TEXT,
                    url          TEXT UNIQUE,
                    category     TEXT DEFAULT 'general',
                    published    TEXT,
                    published_at TEXT,
                    fetched_at   TEXT,
                    last_seen_at TEXT,
                    image_url    TEXT,
                    is_breaking  INTEGER DEFAULT 0,
                    importance   REAL DEFAULT 0,
                    is_read      INTEGER DEFAULT 0,
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL
                )
            ''')

        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_published_at ON news (published_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_category ON news (category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_breaking ON news (is_breaking)")
        except Exception as e:
            logger.debug(f"Index creation notice: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Database initialized successfully ({db_type})")
    except Exception as e:
        logger.error(f"DB init failed: {e}")


# ==============================================================================
# NEWS INGESTION & UPSERT
# ==============================================================================

def save_news(news_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Save or update news articles in the active database.
    - If article exists (by URL or exact title): updates last_seen_at, importance, is_breaking, category.
    - If new: inserts full article document.
    Returns: dictionary with counts (fetched, new_articles, duplicates, updated, newest_published_at).
    """
    stats = {
        "fetched": len(news_list),
        "new_articles": 0,
        "duplicates": 0,
        "updated": 0,
        "newest_published_at": None
    }

    if not news_list:
        return stats

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    valid_published_dates = []

    # 1. MONGODB ATLAS IMPLEMENTATION
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()

            for item in news_list:
                url = item.get("url")
                title = (item.get("title") or "").strip()
                published_at = item.get("published_at")
                fetched_at = item.get("fetched_at") or now_iso
                last_seen_at = now_iso

                if published_at:
                    valid_published_dates.append(published_at)

                # Find existing article by URL or title
                existing = None
                if url:
                    existing = col.find_one({"url": url}, {"_id": 1, "published_at": 1})
                if existing is None and title:
                    existing = col.find_one({"title": title}, {"_id": 1, "published_at": 1})

                is_breaking_val = bool(item.get("is_breaking", 0) == 1 or item.get("is_breaking") is True)
                importance_val = float(item.get("importance", 0.0) or 0.0)

                if existing is not None:
                    # Update existing article without overwriting published_at or created_at
                    stats["duplicates"] += 1
                    update_fields = {
                        "last_seen_at": last_seen_at,
                        "importance": importance_val,
                        "is_breaking": is_breaking_val,
                        "category": item.get("category", "general")
                    }
                    if item.get("image_url"):
                        update_fields["image_url"] = item.get("image_url")

                    col.update_one({"_id": existing["_id"]}, {"$set": update_fields})
                    stats["updated"] += 1
                else:
                    # New article insertion
                    doc = {
                        "title": title,
                        "description": (item.get("description") or "").strip(),
                        "content": (item.get("content") or "").strip(),
                        "summary": item.get("summary"),
                        "source": (item.get("source") or "").strip(),
                        "url": url,
                        "category": item.get("category", "general"),
                        "published": item.get("published", published_at or ""),
                        "published_at": published_at,
                        "fetched_at": fetched_at,
                        "last_seen_at": last_seen_at,
                        "image_url": (item.get("image_url") or "").strip(),
                        "is_breaking": is_breaking_val,
                        "importance": importance_val,
                        "is_read": False,
                        "created_at": now_iso
                    }
                    col.insert_one(doc)
                    stats["new_articles"] += 1

            if valid_published_dates:
                stats["newest_published_at"] = max(valid_published_dates)

            logger.info(f"MongoDB Ingestion: {stats['new_articles']} new, {stats['duplicates']} duplicates, {stats['updated']} updated")
            return stats
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to save news to MongoDB Atlas: {masked_err}")
            raise

    # 2. SQLITE / POSTGRESQL ROLLBACK IMPLEMENTATION
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()

        for item in news_list:
            url = item.get("url")
            title = (item.get("title") or "").strip()
            published_at = item.get("published_at")
            fetched_at = item.get("fetched_at") or now_iso
            last_seen_at = now_iso

            if published_at:
                valid_published_dates.append(published_at)

            existing = None
            if url:
                if db_type == "postgres":
                    cursor.execute("SELECT id, published_at FROM news WHERE url = %s", (url,))
                else:
                    cursor.execute("SELECT id, published_at FROM news WHERE url = ?", (url,))
                existing = cursor.fetchone()

            if existing is None and title:
                if db_type == "postgres":
                    cursor.execute("SELECT id, published_at FROM news WHERE title = %s", (title,))
                else:
                    cursor.execute("SELECT id, published_at FROM news WHERE title = ?", (title,))
                existing = cursor.fetchone()

            if existing is not None:
                stats["duplicates"] += 1
                existing_id = existing[0] if type(existing) is tuple or hasattr(existing, '__getitem__') else existing["id"]

                update_params = (
                    last_seen_at,
                    item.get("importance", 0.0),
                    item.get("is_breaking", 0),
                    item.get("category", "general"),
                    existing_id
                )

                if db_type == "postgres":
                    cursor.execute('''
                        UPDATE news 
                        SET last_seen_at = %s, importance = %s, is_breaking = %s, category = %s 
                        WHERE id = %s
                    ''', update_params)
                else:
                    cursor.execute('''
                        UPDATE news 
                        SET last_seen_at = ?, importance = ?, is_breaking = ?, category = ? 
                        WHERE id = ?
                    ''', update_params)
                stats["updated"] += 1
            else:
                params = (
                    title,
                    item.get("description", ""),
                    item.get("content", ""),
                    item.get("summary", ""),
                    item.get("source", ""),
                    url,
                    item.get("category", "general"),
                    item.get("published", published_at or ""),
                    published_at,
                    fetched_at,
                    last_seen_at,
                    item.get("image_url", ""),
                    item.get("is_breaking", 0),
                    item.get("importance", 0.0),
                )

                if db_type == "postgres":
                    cursor.execute('''
                        INSERT INTO news (
                            title, description, content, summary, source, url, category, 
                            published, published_at, fetched_at, last_seen_at, image_url, 
                            is_breaking, importance
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', params)
                else:
                    cursor.execute('''
                        INSERT INTO news (
                            title, description, content, summary, source, url, category, 
                            published, published_at, fetched_at, last_seen_at, image_url, 
                            is_breaking, importance
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', params)
                stats["new_articles"] += 1

        conn.commit()
        conn.close()

        if valid_published_dates:
            stats["newest_published_at"] = max(valid_published_dates)

        logger.info(f"SQLite/Postgres Ingestion: {stats['new_articles']} new, {stats['duplicates']} duplicates, {stats['updated']} updated")
        return stats
    except Exception as e:
        logger.error(f"Failed to save news: {e}")
        return stats


# ==============================================================================
# PAGINATED RETRIEVAL & FILTERING
# ==============================================================================

def get_news_paginated(
    page: int = 1,
    limit: int = 20,
    category: Optional[str] = None,
    search: Optional[str] = None,
    breaking: Optional[bool] = None,
    exclude_categories: Optional[List[str]] = None,
    show_read: bool = True
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Paginated news query with deterministic latest-first sorting:
    published_at DESC, importance DESC, _id DESC
    """
    # 1. MONGODB ATLAS IMPLEMENTATION
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            query_filters: Dict[str, Any] = {}

            # Category filter
            if category:
                query_filters["category"] = category.lower().strip()
            elif exclude_categories:
                clean_excluded = [c.lower().strip() for c in exclude_categories]
                query_filters["category"] = {"$nin": clean_excluded}

            # Search filter (regex across title, description, summary)
            if search:
                escaped_search = re.escape(search.strip())
                search_regex = {"$regex": escaped_search, "$options": "i"}
                query_filters["$or"] = [
                    {"title": search_regex},
                    {"description": search_regex},
                    {"summary": search_regex}
                ]

            # Breaking news filter
            if breaking is not None:
                if breaking:
                    query_filters["is_breaking"] = {"$in": [True, 1]}
                else:
                    query_filters["is_breaking"] = {"$in": [False, 0, None]}

            # Read status filter
            if not show_read:
                query_filters["$or"] = [
                    {"is_read": False},
                    {"is_read": 0},
                    {"is_read": None},
                    {"is_read": {"$exists": False}}
                ]

            # Deterministic sorting: Newest published first, then highest importance, then ID
            sort_criteria = [
                ("published_at", -1),
                ("importance", -1),
                ("_id", -1)
            ]

            total = col.count_documents(query_filters)
            offset = max(0, (page - 1) * limit)

            cursor = col.find(query_filters).sort(sort_criteria).skip(offset).limit(limit)
            articles = [_doc_to_article(doc) for doc in cursor]

            return articles, total
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to get news paginated from MongoDB Atlas: {masked_err}")
            raise

    # 2. SQLITE / POSTGRESQL ROLLBACK IMPLEMENTATION
    try:
        conn, db_type = get_connection()
        if db_type == "postgres":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        query = "SELECT * FROM news WHERE 1=1"
        params = []

        if category:
            query += " AND category = " + ("%s" if db_type == "postgres" else "?")
            params.append(category)
        elif exclude_categories:
            placeholders = ", ".join(["%s" if db_type == "postgres" else "?"] * len(exclude_categories))
            query += f" AND category NOT IN ({placeholders})"
            params.extend(exclude_categories)

        if search:
            query += " AND (title LIKE " + ("%s" if db_type == "postgres" else "?") + " OR description LIKE " + ("%s" if db_type == "postgres" else "?") + " OR summary LIKE " + ("%s" if db_type == "postgres" else "?") + ")"
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])
        if breaking is not None:
            query += " AND is_breaking = " + ("%s" if db_type == "postgres" else "?")
            params.append(1 if breaking else 0)
        if not show_read:
            query += " AND (is_read = 0 OR is_read IS NULL)"

        query += " ORDER BY COALESCE(published_at, fetched_at, created_at) DESC, importance DESC, id DESC LIMIT " + ("%s" if db_type == "postgres" else "?") + " OFFSET " + ("%s" if db_type == "postgres" else "?")
        offset = (page - 1) * limit
        params.extend([limit, offset])

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        count_query = "SELECT COUNT(*) as total FROM news WHERE 1=1"
        count_params = []
        if category:
            count_query += " AND category = " + ("%s" if db_type == "postgres" else "?")
            count_params.append(category)
        elif exclude_categories:
            placeholders = ", ".join(["%s" if db_type == "postgres" else "?"] * len(exclude_categories))
            count_query += f" AND category NOT IN ({placeholders})"
            count_params.extend(exclude_categories)

        if search:
            count_query += " AND (title LIKE " + ("%s" if db_type == "postgres" else "?") + " OR description LIKE " + ("%s" if db_type == "postgres" else "?") + " OR summary LIKE " + ("%s" if db_type == "postgres" else "?") + ")"
            count_params.extend([search_param, search_param, search_param])
        if breaking is not None:
            count_query += " AND is_breaking = " + ("%s" if db_type == "postgres" else "?")
            count_params.append(1 if breaking else 0)
        if not show_read:
            count_query += " AND (is_read = 0 OR is_read IS NULL)"

        cursor.execute(count_query, tuple(count_params))
        total_row = cursor.fetchone()
        total = total_row["total"] if total_row else 0

        conn.close()
        return [dict(row) for row in rows], total
    except Exception as e:
        logger.error(f"Failed to get news paginated: {e}")
        return [], 0


# ==============================================================================
# BREAKING NEWS & CATEGORY OPERATIONS
# ==============================================================================

def get_breaking_news(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get breaking news sorted by newest published first, then importance.
    """
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            query = {"is_breaking": {"$in": [True, 1]}}
            sort_criteria = [
                ("published_at", -1),
                ("importance", -1),
                ("_id", -1)
            ]
            cursor = col.find(query).sort(sort_criteria).limit(limit)
            return [_doc_to_article(doc) for doc in cursor]
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to get breaking news from MongoDB: {masked_err}")
            raise

    try:
        conn, db_type = get_connection()
        if db_type == "postgres":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM news 
            WHERE is_breaking = 1 
            ORDER BY COALESCE(published_at, fetched_at, created_at) DESC, importance DESC 
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get breaking news: {e}")
        return []


def get_category_counts() -> Dict[str, int]:
    """
    Return clean category counts for the 6 canonical categories:
    local, national, global, technology, business, sports.
    Explicitly excludes world, general, all, news.
    """
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            pipeline = [
                {"$match": {"category": {"$in": CANONICAL_CATEGORIES}}},
                {"$group": {"_id": "$category", "count": {"$sum": 1}}}
            ]
            results = col.aggregate(pipeline)
            counts_map = {doc["_id"]: doc["count"] for doc in results}
            # Return strictly the canonical categories
            return {cat: counts_map.get(cat, 0) for cat in CANONICAL_CATEGORIES}
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to get category counts from MongoDB: {masked_err}")
            raise

    try:
        conn, db_type = get_connection()
        if db_type == "postgres":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        cursor.execute("SELECT category, COUNT(*) as count FROM news GROUP BY category")
        rows = cursor.fetchall()
        conn.close()
        counts = {row["category"]: row["count"] for row in rows}
        return {cat: counts.get(cat, 0) for cat in CANONICAL_CATEGORIES}
    except Exception as e:
        logger.error(f"Failed to get category counts: {e}")
        return {}


def mark_as_read(article_id: Any) -> bool:
    """
    Mark an article as read. Supports numeric SQLite ID, MongoDB ObjectId, or string ID.
    """
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            or_conditions = []

            # 1. Check numeric sqlite_id
            if isinstance(article_id, int) or (isinstance(article_id, str) and article_id.isdigit()):
                int_val = int(article_id)
                or_conditions.append({"sqlite_id": int_val})
                or_conditions.append({"id": int_val})

            # 2. Check MongoDB ObjectId
            if ObjectId and isinstance(article_id, str) and ObjectId.is_valid(article_id):
                or_conditions.append({"_id": ObjectId(article_id)})
            elif ObjectId and isinstance(article_id, ObjectId):
                or_conditions.append({"_id": article_id})

            if not or_conditions:
                or_conditions.append({"url": str(article_id)})

            result = col.update_one({"$or": or_conditions}, {"$set": {"is_read": True}})
            return result.matched_count > 0 or result.modified_count > 0
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to mark article {article_id} as read in MongoDB: {masked_err}")
            return False

    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param = ("%s" if db_type == "postgres" else "?")
        cursor.execute(f"UPDATE news SET is_read = 1 WHERE id = {param}", (article_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to mark as read: {e}")
        return False


def get_news_by_category() -> List[Dict[str, Any]]:
    """Helper for scheduler/notifications to retrieve latest news articles."""
    articles, _ = get_news_paginated(limit=50)
    return articles


# ==============================================================================
# SETTINGS & USER PREFERENCES PERSISTENCE
# ==============================================================================

def save_config(key: str, value: Any):
    """Save a user configuration setting to active persistence."""
    if DB_BACKEND == "mongodb":
        try:
            pref_col = get_preferences_collection()
            pref_col.update_one(
                {"key": key},
                {"$set": {"key": key, "value": str(value)}},
                upsert=True
            )
            logger.info(f"Saved preference to MongoDB: {key} = {value}")
            return
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to save preference to MongoDB: {masked_err}")
            raise

    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()

        if db_type == "postgres":
            cursor.execute("INSERT INTO user_preferences (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, str(value)))
        else:
            cursor.execute("INSERT OR REPLACE INTO user_preferences (key, value) VALUES (?, ?)", (key, str(value)))

        conn.commit()
        conn.close()
        logger.info(f"Saved preference: {key} = {value}")
    except Exception as e:
        logger.error(f"Failed to save preference: {e}")

save_setting = save_config
save_user_preference = save_config


def get_preferences_dict() -> Dict[str, str]:
    """Retrieve all user preferences as a key-value dictionary."""
    if DB_BACKEND == "mongodb":
        try:
            pref_col = get_preferences_collection()
            docs = pref_col.find({}, {"key": 1, "value": 1})
            return {doc["key"]: doc["value"] for doc in docs if "key" in doc and "value" in doc}
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to get preferences from MongoDB: {masked_err}")
            return {}

    try:
        conn, db_type = get_connection()
        if db_type == "postgres":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()

        cursor.execute("SELECT key, value FROM user_preferences")
        rows = cursor.fetchall()
        conn.close()
        return {row["key"]: row["value"] for row in rows}
    except Exception as e:
        logger.error(f"Failed to get preferences: {e}")
        return {}


def get_all_settings() -> Dict[str, Any]:
    """Returns a fully merged settings dictionary using canonical schema defaults."""
    from config.settings_schema import get_canonical_defaults, validate_setting, SETTINGS_SCHEMA

    canonical_defaults = get_canonical_defaults()
    prefs = get_preferences_dict()

    settings = dict(canonical_defaults)
    for k, v in prefs.items():
        if k in SETTINGS_SCHEMA:
            valid, parsed_v, _ = validate_setting(k, v)
            if valid:
                settings[k] = parsed_v
        else:
            settings[k] = v

    return settings


def clear_cache_db() -> bool:
    """Clear cached/generated article summaries only, preserving all news articles and user preferences."""
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            col.update_many({}, {"$set": {"summary": None}})
            logger.info("Cleared cached summaries in MongoDB Atlas")
            return True
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to clear cache in MongoDB Atlas: {masked_err}")
            return False

    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE news SET summary = NULL")
        conn.commit()
        conn.close()
        logger.info("Cleared cached summaries from database")
        return True
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        return False


def reset_preferences_db() -> bool:
    """Reset user preferences and cached summaries to canonical defaults."""
    if DB_BACKEND == "mongodb":
        try:
            pref_col = get_preferences_collection()
            pref_col.delete_many({})
            clear_cache_db()
            logger.info("Reset user preferences and cached summaries in MongoDB Atlas")
            return True
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to reset preferences in MongoDB Atlas: {masked_err}")
            return False

    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_preferences")
        cursor.execute("UPDATE news SET summary = NULL")
        conn.commit()
        conn.close()
        logger.info("Reset user preferences and cached summaries to defaults")
        return True
    except Exception as e:
        logger.error(f"Failed to reset preferences: {e}")
        return False


# ==============================================================================
# SUMMARY CACHE & DB STATS
# ==============================================================================

def get_cached_summary(url: str) -> Optional[str]:
    """Retrieve cached summary for an article URL."""
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            doc = col.find_one({"url": url}, {"summary": 1})
            if doc and doc.get("summary"):
                return doc["summary"]
            return None
        except Exception as e:
            logger.error(f"Failed to get cached summary: {e}")
            return None

    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param = ("%s" if db_type == "postgres" else "?")
        cursor.execute(f"SELECT summary FROM news WHERE url = {param}", (url,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0] if type(row) is tuple else row["summary"]
        return None
    except Exception as e:
        return None


def save_cached_summary(url: str, summary: str) -> bool:
    """Save generated summary for an article URL."""
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            col.update_one({"url": url}, {"$set": {"summary": summary}})
            return True
        except Exception as e:
            logger.error(f"Failed to save cached summary to MongoDB: {e}")
            return False

    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param = ("%s" if db_type == "postgres" else "?")
        cursor.execute(f"UPDATE news SET summary = {param} WHERE url = {param}", (summary, url))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save cached summary: {e}")
        return False


def get_db_stats() -> Dict[str, Any]:
    """Returns database summary stats for debugging and refresh status."""
    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            total_articles = col.count_documents({})

            doc_pub = col.find_one(
                {"published_at": {"$ne": None, "$nin": ["", None]}},
                sort=[("published_at", -1)],
                projection={"published_at": 1}
            )
            newest_published = doc_pub.get("published_at") if doc_pub else None

            doc_seen = col.find_one(
                {"last_seen_at": {"$ne": None, "$nin": ["", None]}},
                sort=[("last_seen_at", -1)],
                projection={"last_seen_at": 1}
            )
            last_seen = doc_seen.get("last_seen_at") if doc_seen else None

            return {
                "total_articles": total_articles,
                "newest_published": newest_published,
                "last_seen": last_seen
            }
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to get MongoDB stats: {masked_err}")
            return {"total_articles": 0, "newest_published": None, "last_seen": None}

    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM news")
        total_articles = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(published_at) FROM news WHERE published_at IS NOT NULL")
        newest_published = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(last_seen_at) FROM news WHERE last_seen_at IS NOT NULL")
        last_seen = cursor.fetchone()[0]

        conn.close()
        return {
            "total_articles": total_articles,
            "newest_published": newest_published,
            "last_seen": last_seen
        }
    except Exception as e:
        logger.error(f"Failed to get DB stats: {e}")
        return {"total_articles": 0, "newest_published": None, "last_seen": None}


def mark_ran_today():
    """No-op pipeline run marker."""
    pass


NEWS_RETENTION_DAYS = int(os.getenv("NEWS_RETENTION_DAYS", "7"))


def cleanup_expired_articles(days: Optional[int] = None) -> Dict[str, Any]:
    """
    Automatically delete news articles in MongoDB Atlas whose original publication timestamp
    (published_at) is older than 'days' (default: NEWS_RETENTION_DAYS) relative to current UTC datetime.

    Strict safety rules:
    - Uses 'published_at' exclusively (never created_at, fetched_at, or last_seen_at).
    - Only deletes records with a valid, non-empty published_at string strictly less than cutoff.
    - Articles with null, empty, or missing published_at are preserved.
    - SQLite database remains 100% untouched as rollback/reference database.

    Returns cleanup statistics:
    {
        "deleted": int,
        "cutoff": str,
        "retention_days": int,
        "total_remaining": int
    }
    """
    if days is None:
        days = NEWS_RETENTION_DAYS
    now_utc = datetime.now(timezone.utc)
    cutoff_dt = now_utc - timedelta(days=days)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    if DB_BACKEND == "mongodb":
        try:
            col = get_articles_collection()
            query = {
                "published_at": {
                    "$ne": None,
                    "$nin": ["", None],
                    "$lt": cutoff_iso
                }
            }
            res = col.delete_many(query)
            deleted_count = res.deleted_count
            total_remaining = col.count_documents({})
            logger.info(f"Cleanup expired articles (> {days}d, cutoff={cutoff_iso}): deleted {deleted_count}, remaining {total_remaining}")
            return {
                "deleted": deleted_count,
                "cutoff": cutoff_iso,
                "retention_days": days,
                "total_remaining": total_remaining
            }
        except Exception as e:
            masked_err = mask_secret(str(e))
            logger.error(f"Failed to cleanup expired articles in MongoDB: {masked_err}")
            raise

    # SQLite Rollback Protection: do not delete records in SQLite
    logger.info("SQLite mode: cleanup_expired_articles skipped to preserve rollback database.")
    return {
        "deleted": 0,
        "cutoff": cutoff_iso,
        "retention_days": days,
        "total_remaining": 0,
        "message": "SQLite rollback database preserved"
    }