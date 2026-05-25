from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR  = os.path.join(BASE_DIR, 'src')
sys.path.insert(0, SRC_DIR)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Nexus News API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_database():
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id          SERIAL PRIMARY KEY,
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS last_run (
                id       SERIAL PRIMARY KEY,
                run_date TEXT
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully")
    except Exception as e:
        print(f"DB init error: {e}")

# Initialize on startup
init_database()

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "Nexus News API running"}

@app.get("/news")
def get_news(category: str = None):
    try:
        import psycopg2.extras
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if category:
            cur.execute(
                "SELECT * FROM news WHERE category=%s ORDER BY id DESC",
                (category,)
            )
        else:
            cur.execute("SELECT * FROM news ORDER BY id DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return {"articles": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e), "articles": []}

@app.get("/status")
def get_status():
    try:
        import psycopg2.extras
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT run_date FROM last_run ORDER BY id DESC LIMIT 1")
        row      = cur.fetchone()
        last_run = row["run_date"] if row else "never"
        cur.close()
        conn.close()
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "last_run": last_run,
            "today":    today,
            "is_fresh": last_run == today
        }
    except Exception as e:
        return {"error": str(e), "last_run": "never", "is_fresh": False}

@app.post("/fetch")
def trigger_fetch():
    try:
        from fetch.news_api import fetch_all_news
        from ai.categorizer import categorize_news_list
        from ai.summarizer  import summarize_news_list

        # Run pipeline
        news = fetch_all_news()
        news = categorize_news_list(news)
        news = summarize_news_list(news)

        # Save to PostgreSQL
        conn  = get_db()
        cur   = conn.cursor()
        saved = 0

        cur.execute("DELETE FROM news")

        for item in news:
            try:
                cur.execute("""
                    INSERT INTO news
                    (title, description, content, summary, source, url, category, published)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
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
            except Exception as e:
                print(f"Insert error: {e}")
                continue

        # Mark as run today
        today = datetime.now().strftime("%Y-%m-%d")
        cur.execute("DELETE FROM last_run")
        cur.execute("INSERT INTO last_run (run_date) VALUES (%s)", (today,))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "status":  "success",
            "fetched": len(news),
            "saved":   saved,
            "time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        import traceback
        return {
            "status":  "error",
            "message": str(e),
            "trace":   traceback.format_exc()
        }