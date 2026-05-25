from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import sys
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR  = os.path.join(BASE_DIR, 'src')
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR  = os.path.join(BASE_DIR, 'logs')
DB_PATH  = os.path.join(DATA_DIR, 'news.db')
LAST_RUN = os.path.join(DATA_DIR, 'last_run.txt')

# Create folders
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR,  exist_ok=True)

# Add src to path
sys.path.insert(0, SRC_DIR)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Nexus News API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Init DB directly here (no dependency on database.py path) ─────────────────
def init_database():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT,
            description TEXT,
            content     TEXT,
            summary     TEXT,
            source      TEXT,
            url         TEXT UNIQUE,
            category    TEXT,
            published   TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            key        TEXT UNIQUE,
            value      TEXT
        )
    """)
    conn.commit()
    conn.close()

# Initialize on startup
init_database()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "Nexus News API running"}

@app.get("/news")
def get_news(category: str = None):
    try:
        conn = get_db()
        if category:
            rows = conn.execute(
                "SELECT * FROM news WHERE category=? ORDER BY id DESC",
                (category,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM news ORDER BY id DESC"
            ).fetchall()
        conn.close()
        return {"articles": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e), "articles": []}

@app.get("/news/categories")
def get_categories():
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT category, COUNT(*) as count FROM news GROUP BY category"
        ).fetchall()
        conn.close()
        return {"categories": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e), "categories": []}

@app.get("/status")
def get_status():
    try:
        last_run = "never"
        if os.path.exists(LAST_RUN):
            with open(LAST_RUN) as f:
                last_run = f.read().strip()
        return {
            "last_run": last_run,
            "today":    datetime.now().strftime("%Y-%m-%d"),
            "is_fresh": last_run == datetime.now().strftime("%Y-%m-%d")
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/fetch")
def trigger_fetch():
    try:
        from fetch.news_api  import fetch_all_news
        from ai.categorizer  import categorize_news_list
        from ai.summarizer   import summarize_news_list

        # Clear old news
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM news")
        conn.commit()
        conn.close()

        # Run pipeline
        news = fetch_all_news()
        news = categorize_news_list(news)
        news = summarize_news_list(news)

        # Save directly to DB
        conn = sqlite3.connect(DB_PATH)
        saved = 0
        for item in news:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO news
                    (title, description, content, summary, source, url, category, published)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("title", ""),
                    item.get("description", ""),
                    item.get("content", ""),
                    item.get("summary", ""),
                    item.get("source", ""),
                    item.get("url", ""),
                    item.get("category", "general"),
                    item.get("published", ""),
                ))
                saved += 1
            except:
                continue
        conn.commit()
        conn.close()

        # Mark as run today
        with open(LAST_RUN, 'w') as f:
            f.write(datetime.now().strftime("%Y-%m-%d"))

        return {
            "status":  "success",
            "fetched": len(news),
            "saved":   saved,
            "time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "trace": traceback.format_exc()}