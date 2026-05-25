from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import json
from datetime import datetime

app = FastAPI(title="Nexus News API")
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from db.database import init_db
init_db()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.environ.get("DB_PATH", "data/news.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/")
def root():
    return {"status": "Nexus News API running"}

@app.get("/news")
def get_news(category: str = None):
    """Get all news or filter by category."""
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
    """Get article counts per category."""
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
    """Check when news was last fetched."""
    try:
        last_run_path = os.environ.get("LAST_RUN_PATH", "data/last_run.txt")
        if os.path.exists(last_run_path):
            with open(last_run_path) as f:
                last_run = f.read().strip()
        else:
            last_run = "never"
        return {
            "last_run": last_run,
            "today":    datetime.now().strftime("%Y-%m-%d"),
            "is_fresh": last_run == datetime.now().strftime("%Y-%m-%d")
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/fetch")
def trigger_fetch():
    """Manually trigger news fetch — called by cron job."""
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

        from fetch.news_api   import fetch_all_news
        from ai.categorizer   import categorize_news_list
        from ai.summarizer    import summarize_news_list
        from db.database      import init_db, save_news, mark_ran_today
        import sqlite3 as sq

        # Clear old news
        conn = sq.connect(DB_PATH)
        conn.execute("DELETE FROM news")
        conn.commit()
        conn.close()

        # Run pipeline
        init_db()
        news = fetch_all_news()
        news = categorize_news_list(news)
        news = summarize_news_list(news)
        save_news(news)
        mark_ran_today()

        return {
            "status":  "success",
            "fetched": len(news),
            "time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}