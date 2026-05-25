import sqlite3
import os
import sys
from datetime import datetime
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.logger import get_logger

logger = get_logger("database")

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'news.db')
LAST_RUN_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'last_run.txt')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                summary TEXT,
                source TEXT,
                url TEXT,
                category TEXT,
                fetched_at TEXT
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

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"DB init failed: {e}")

def save_news(news_list):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        count = 0
        for item in news_list:
            # Avoid duplicates by checking title
            cursor.execute("SELECT id FROM news WHERE title = ?", (item.get("title"),))
            if cursor.fetchone() is None:
                cursor.execute('''
                    INSERT INTO news (title, description, summary, source, url, category, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    item.get("title", ""),
                    item.get("description", ""),
                    item.get("summary", ""),
                    item.get("source", ""),
                    item.get("url", ""),
                    item.get("category", "general"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                count += 1
        conn.commit()
        conn.close()
        logger.info(f"Saved {count} new articles to database")
        return count
    except Exception as e:
        logger.error(f"Failed to save news: {e}")
        return 0

def get_news_by_category(category=None):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if category:
            cursor.execute("SELECT * FROM news WHERE category = ? ORDER BY fetched_at DESC", (category,))
        else:
            cursor.execute("SELECT * FROM news ORDER BY fetched_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get news: {e}")
        return []

def save_preference(key, value):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO user_preferences (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
        logger.info(f"Saved preference: {key} = {value}")
    except Exception as e:
        logger.error(f"Failed to save preference: {e}")

def get_preference(key, default=None):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM user_preferences WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception as e:
        logger.error(f"Failed to get preference: {e}")
        return default

def check_already_ran_today():
    try:
        if not os.path.exists(LAST_RUN_PATH):
            return False
        with open(LAST_RUN_PATH, 'r') as f:
            last_run = f.read().strip()
        today = datetime.now().strftime("%Y-%m-%d")
        return last_run == today
    except:
        return False

def mark_ran_today():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        with open(LAST_RUN_PATH, 'w') as f:
            f.write(today)
        logger.info(f"Marked as run today: {today}")
    except Exception as e:
        logger.error(f"Failed to mark run date: {e}")


# Test
if __name__ == "__main__":
    print("Initializing database...")
    init_db()

    test_news = [
        {
            "title": "India wins cricket match",
            "description": "India defeated Australia by 5 wickets.",
            "summary": "India beat Australia in a thrilling match.",
            "source": "ESPN",
            "url": "https://espn.com/test",
            "category": "sports"
        },
        {
            "title": "Google releases new AI model",
            "description": "Gemini Ultra 2 outperforms all models.",
            "summary": "Google launches powerful new AI.",
            "source": "TechCrunch",
            "url": "https://techcrunch.com/test",
            "category": "technology"
        }
    ]

    print("Saving test articles...")
    saved = save_news(test_news)
    print(f"Saved {saved} articles")

    print("\nFetching sports news from DB:")
    sports = get_news_by_category("sports")
    for item in sports:
        print(f"  [{item['category'].upper()}] {item['title']}")

    print("\nChecking daily run flag...")
    print(f"  Already ran today: {check_already_ran_today()}")
    mark_ran_today()
    print(f"  After marking: {check_already_ran_today()}")

    print("\nSaving a preference...")
    save_preference("preferred_categories", "sports,technology,national")
    pref = get_preference("preferred_categories")
    print(f"  Loaded preference: {pref}")

    print("\nDatabase test complete!")