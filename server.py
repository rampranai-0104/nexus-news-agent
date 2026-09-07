import os
import sys
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Setup paths to import from src
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, 'src'))

from db.database import (
    init_db, get_news_paginated, get_breaking_news, 
    get_category_counts, mark_as_read, get_db_stats,
    get_all_settings, clear_cache_db, reset_preferences_db, save_setting
)
from core.logger import get_logger
from main import run_pipeline

logger = get_logger("server")

# Initialize database
init_db()

app = FastAPI(title="Nexus News API")

# Setup CORS if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prevent stale caching on API responses
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith(("/news", "/refresh", "/for-you", "/briefing", "/breaking", "/status", "/categories")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# --- Models ---
class ChatMessage(BaseModel):
    message: str

class PreferencesUpdate(BaseModel):
    preferred_categories: list[str]
    ai_provider: str

# --- Refresh State & Concurrency Lock ---
NEWS_REFRESH_MINUTES = int(os.getenv("NEWS_REFRESH_MINUTES", "15"))
refresh_lock = asyncio.Lock()

refresh_state = {
    "status": "idle", # "idle" | "refresh_in_progress"
    "last_successful_refresh": None,
    "last_attempt": None,
    "last_error": None,
    "stage": "idle",
    "progress": 0,
    "articles_last_fetched": 0,
    "new_articles_last_refresh": 0,
    "last_meta": {}
}

# Pre-populate last_successful_refresh from DB stats on startup
initial_db_stats = get_db_stats()
if initial_db_stats.get("last_seen"):
    refresh_state["last_successful_refresh"] = initial_db_stats["last_seen"]
elif initial_db_stats.get("newest_published"):
    refresh_state["last_successful_refresh"] = initial_db_stats["newest_published"]

def is_within_ttl(last_refresh_str: str, ttl_minutes: int) -> bool:
    if not last_refresh_str:
        return False
    try:
        dt = datetime.fromisoformat(last_refresh_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() < (ttl_minutes * 60)
    except Exception:
        return False

def update_progress(stage, pct):
    refresh_state["stage"] = stage
    refresh_state["progress"] = pct

# --- Routes ---
@app.get("/")
async def serve_frontend():
    index_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Nexus News API is running (Frontend not found)"}

@app.get("/refresh-status")
async def get_refresh_status():
    is_fresh = is_within_ttl(refresh_state["last_successful_refresh"], NEWS_REFRESH_MINUTES)
    return {
        "status": refresh_state["status"],
        "is_fresh": is_fresh,
        "last_successful_refresh": refresh_state["last_successful_refresh"],
        "last_attempt": refresh_state["last_attempt"],
        "last_error": refresh_state["last_error"],
        "stage": refresh_state["stage"],
        "progress": refresh_state["progress"],
        "articles_last_fetched": refresh_state["articles_last_fetched"],
        "new_articles_last_refresh": refresh_state["new_articles_last_refresh"],
        "ttl_minutes": NEWS_REFRESH_MINUTES,
        "last_meta": refresh_state["last_meta"]
    }

@app.post("/refresh-news")
async def refresh_news(force: bool = False):
    """
    Intelligent refresh endpoint.
    - If already running: returns HTTP 202 refresh_in_progress.
    - If not forced and data is fresh (< TTL): returns status 'fresh'.
    - Otherwise runs non-blocking threaded ingestion with lock and timeout protection.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    refresh_state["last_attempt"] = now_iso

    # 1. Concurrency Check
    if refresh_state["status"] == "refresh_in_progress" or refresh_lock.locked():
        return JSONResponse(
            status_code=202,
            content={
                "status": "refresh_in_progress",
                "message": "News refresh is already running",
                "stage": refresh_state["stage"],
                "progress": refresh_state["progress"]
            }
        )

    # 2. TTL Freshness Check
    if not force and is_within_ttl(refresh_state["last_successful_refresh"], NEWS_REFRESH_MINUTES):
        logger.info(f"Refresh skipped: News is fresh (within {NEWS_REFRESH_MINUTES}m TTL)")
        return {
            "status": "fresh",
            "message": f"News is already fresh (refreshed recently)",
            "meta": refresh_state["last_meta"],
            "last_successful_refresh": refresh_state["last_successful_refresh"]
        }

    # 3. Non-blocking Ingestion Execution
    async with refresh_lock:
        refresh_state["status"] = "refresh_in_progress"
        refresh_state["stage"] = "Starting"
        refresh_state["progress"] = 5
        refresh_state["last_error"] = None
        
        try:
            # Run blocking ingestion in a worker thread with 120s overall timeout
            result = await asyncio.wait_for(
                asyncio.to_thread(run_pipeline, progress_callback=update_progress),
                timeout=120.0
            )
            
            meta = result.get("meta", {})
            refresh_state["status"] = "idle"
            refresh_state["stage"] = "Completed"
            refresh_state["progress"] = 100
            refresh_state["last_successful_refresh"] = meta.get("updated_at", now_iso)
            refresh_state["articles_last_fetched"] = meta.get("fetched", 0)
            refresh_state["new_articles_last_refresh"] = meta.get("new_articles", 0)
            refresh_state["last_meta"] = meta
            
            return {
                "status": "success",
                "message": "News refreshed successfully",
                "meta": meta
            }
        except asyncio.TimeoutError:
            err_msg = "News refresh pipeline timed out (120s limit)"
            logger.error(err_msg)
            refresh_state["last_error"] = err_msg
            refresh_state["status"] = "idle"
            refresh_state["stage"] = "Timeout"
            return JSONResponse(
                status_code=504,
                content={"status": "error", "message": err_msg, "last_meta": refresh_state["last_meta"]}
            )
        except Exception as e:
            err_msg = f"News refresh failed: {str(e)}"
            logger.error(err_msg)
            refresh_state["last_error"] = err_msg
            refresh_state["status"] = "idle"
            refresh_state["stage"] = "Failed"
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": err_msg, "last_meta": refresh_state["last_meta"]}
            )
        finally:
            refresh_state["status"] = "idle"

# Alias for backwards compatibility
@app.post("/fetch")
async def trigger_fetch(force: bool = True):
    return await refresh_news(force=force)

@app.get("/fetch/status")
async def fetch_status():
    return await get_refresh_status()

@app.get("/news")
async def get_news(page: int = 1, limit: int = None, category: str = None, search: str = None, breaking: bool = None):
    try:
        settings = get_all_settings()
        if limit is None or limit <= 0:
            limit = int(settings.get("article_limit", 20))
        show_read = settings.get("show_read_articles", True)
        
        articles, total = get_news_paginated(page, limit, category, search, breaking, show_read=show_read)
        from ai.summarizer import summarize_news_list
        articles = summarize_news_list(articles)
        has_more = (page * limit) < total
        
        return {
            "status": "ok",
            "data": articles,
            "meta": {"page": page, "limit": limit, "total": total, "has_more": has_more}
        }
    except Exception as e:
        import traceback
        err_detail = traceback.format_exc()
        logger.error(f"Error in /news: {err_detail}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e), "traceback": err_detail})

@app.get("/status")
async def get_status():
    is_fresh = is_within_ttl(refresh_state["last_successful_refresh"], NEWS_REFRESH_MINUTES)
    return {
        "status": "ok",
        "is_fresh": is_fresh,
        "last_successful_refresh": refresh_state["last_successful_refresh"]
    }

@app.post("/chat")
async def chat_command(chat: ChatMessage):
    from core.agent_controller import AgentController
    agent = AgentController()
    response = agent.handle_user_command(chat.message)
    return response

@app.get("/settings")
async def get_settings():
    from db.database import get_all_settings
    settings = get_all_settings()
    return {
        "status": "success",
        "data": settings
    }

@app.post("/settings")
async def update_settings(request: Request):
    from db.database import save_config, get_all_settings
    from config.settings_schema import validate_settings_payload
    import json
    
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Malformed JSON payload",
                "errors": {"_general": "Request body must be valid JSON"}
            }
        )
        
    all_valid, cleaned, errors = validate_settings_payload(payload)
    if not all_valid:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Invalid setting value",
                "errors": errors
            }
        )
        
    for key, value in cleaned.items():
        if isinstance(value, bool):
            val_str = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            val_str = json.dumps(value)
        else:
            val_str = str(value)
        save_config(key, val_str)
        
    if any(k.startswith("location") for k in cleaned):
        from fetch.geolocator import clear_location_cache
        clear_location_cache()
        
    updated_settings = get_all_settings()
    return {
        "status": "success",
        "data": updated_settings,
        "message": "Settings saved successfully"
    }

@app.post("/data/clear_cache")
async def clear_cache():
    from db.database import clear_cache_db
    success = clear_cache_db()
    if success:
        return {
            "status": "success",
            "message": "Cache cleared successfully"
        }
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Failed to clear cache"}
    )

@app.post("/data/reset")
async def reset_settings():
    from db.database import reset_preferences_db, get_all_settings
    from fetch.geolocator import clear_location_cache
    success = reset_preferences_db()
    clear_location_cache()
    if success:
        defaults = get_all_settings()
        return {
            "status": "success",
            "data": defaults,
            "message": "Application data reset successfully"
        }
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Failed to reset application data"}
    )

@app.get("/for-you")
async def get_for_you(page: int = 1, limit: int = 20):
    from core.agent_controller import AgentController
    agent = AgentController()
    result = agent.generate_for_you(page, limit)
    total = result.get("total", 0)
    return {
        "status": "ok",
        "data": result,
        "meta": {"page": page, "limit": limit, "total": total, "has_more": (page * limit) < total}
    }

@app.get("/briefing")
async def get_briefing(page: int = 1, limit: int = 20):
    from core.agent_controller import AgentController
    agent = AgentController()
    result = agent.generate_briefing(page, limit)
    total = result.get("total", 0)
    return {
        "status": "ok",
        "data": result,
        "meta": {"page": page, "limit": limit, "total": total, "has_more": (page * limit) < total}
    }

@app.get("/breaking")
async def get_breaking():
    articles = get_breaking_news()
    from ai.summarizer import summarize_news_list
    articles = summarize_news_list(articles)
    return {
        "status": "ok",
        "data": articles,
        "meta": {"count": len(articles)}
    }

@app.get("/categories")
async def get_categories():
    counts = get_category_counts()
    return {"status": "ok", "data": counts}

@app.get("/location")
async def get_location():
    from fetch.geolocator import get_current_location
    return {"status": "ok", "data": get_current_location()}

@app.get("/preferences")
async def get_preferences():
    from config import get_config
    return {"status": "ok", "data": get_config()}

@app.post("/preferences")
async def set_preferences(prefs: PreferencesUpdate):
    from config import update_config
    update_config("preferred_categories", prefs.preferred_categories)
    update_config("ai_provider", prefs.ai_provider)
    return {"status": "ok"}

@app.get("/article/{id}/read")
async def read_article(id: int):
    success = mark_as_read(id)
    if success:
        return {"status": "ok"}
    raise HTTPException(status_code=400, detail="Failed to mark as read")