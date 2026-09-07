import sqlite3
import os
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.logger import get_logger
from config import DB_PATH, DATABASE_URL

logger = get_logger("database")

def get_connection():
    """Auto-detect: use PostgreSQL if DATABASE_URL is set, else SQLite."""
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
        return conn, "postgres"
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

def init_db():
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

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS read_status (
                    id SERIAL PRIMARY KEY,
                    news_id INTEGER,
                    read_at TEXT,
                    FOREIGN KEY (news_id) REFERENCES news(id)
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

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS read_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_id INTEGER,
                    read_at TEXT,
                    FOREIGN KEY (news_id) REFERENCES news(id)
                )
            ''')

        # Non-destructive migrations for existing databases
        migration_columns = [
            ("published_at", "TEXT"),
            ("fetched_at", "TEXT"),
            ("last_seen_at", "TEXT")
        ]
        for col, col_type in migration_columns:
            try:
                if db_type == "postgres":
                    cursor.execute(f"ALTER TABLE news ADD COLUMN IF NOT EXISTS {col} {col_type}")
                else:
                    cursor.execute(f"ALTER TABLE news ADD COLUMN {col} {col_type}")
            except Exception:
                # Column already exists in SQLite
                pass

        # Create indexes for fast sorting and category lookups
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

def save_news(news_list):
    """
    Save or update news articles in the database.
    - If article exists (by url or normalized title): updates last_seen_at and importance (preserves published_at).
    - If new: inserts full article with published_at, fetched_at, last_seen_at.
    Returns dictionary with counts: fetched, new_articles, duplicates, updated, newest_published_at.
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

    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        valid_published_dates = []

        for item in news_list:
            url = item.get("url")
            title = (item.get("title") or "").strip()
            published_at = item.get("published_at")
            fetched_at = item.get("fetched_at") or now_iso
            last_seen_at = now_iso
            
            if published_at:
                valid_published_dates.append(published_at)

            # Check for existing article by URL or exact title
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
                # Existing article - update last_seen_at and importance, do NOT overwrite published_at
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
                # New article - insert
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
            
        logger.info(f"DB Ingestion: {stats['new_articles']} new, {stats['duplicates']} duplicates, {stats['updated']} updated")
        return stats
    except Exception as e:
        logger.error(f"Failed to save news: {e}")
        return stats

def get_news_paginated(page=1, limit=20, category=None, search=None, breaking=None, exclude_categories=None, show_read=True):
    """
    Paginated news query with strict latest-first sorting:
    COALESCE(published_at, fetched_at, created_at) DESC, importance DESC
    """
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
            
        # Strict sorting: Newest published articles first, then highest importance, then ID
        query += " ORDER BY COALESCE(published_at, fetched_at, created_at) DESC, importance DESC, id DESC LIMIT " + ("%s" if db_type == "postgres" else "?") + " OFFSET " + ("%s" if db_type == "postgres" else "?")
        offset = (page - 1) * limit
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        # Get total count
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

def get_breaking_news(limit=10):
    """
    Get breaking news sorted by newest published first, then importance.
    """
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
            LIMIT 10
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get breaking news: {e}")
        return []

def get_category_counts():
    try:
        conn, db_type = get_connection()
        if db_type == "postgres":
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            cursor = conn.cursor()
            
        cursor.execute("SELECT category, COUNT(*) as count FROM news GROUP BY category")
        rows = cursor.fetchall()
        conn.close()
        return {row["category"]: row["count"] for row in rows}
    except Exception as e:
        logger.error(f"Failed to get category counts: {e}")
        return {}

def mark_as_read(article_id):
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

def save_config(key, value):
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        
        if db_type == "postgres":
            cursor.execute("INSERT INTO user_preferences (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
        else:
            cursor.execute("INSERT OR REPLACE INTO user_preferences (key, value) VALUES (?, ?)", (key, value))
            
        conn.commit()
        conn.close()
        logger.info(f"Saved preference: {key} = {value}")
    except Exception as e:
        logger.error(f"Failed to save preference: {e}")

save_setting = save_config
save_user_preference = save_config

def get_preferences_dict():
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

def get_all_settings():
    """Returns a fully merged settings dictionary using the canonical schema defaults."""
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

def clear_cache_db():
    """Clear cached/generated article summaries only, preserving all news articles and user preferences."""
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

def reset_preferences_db():
    """Reset user preferences and cached summaries to canonical defaults."""
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

def get_cached_summary(url):
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

def save_cached_summary(url, summary):
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

def get_db_stats():
    """Returns database summary stats for debugging and refresh status."""
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
    pass