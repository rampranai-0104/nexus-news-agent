import sys
import os

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from config.settings_schema import (
    CANONICAL_SETTINGS,
    CANONICAL_DEFAULTS,
    validate_settings,
    is_in_quiet_hours,
    SETTINGS_VERSION
)
from db.database import (
    init_db,
    get_all_settings,
    save_setting,
    clear_cache_db,
    reset_preferences_db,
    get_news_paginated,
    get_connection
)
from fetch.geolocator import get_user_location, invalidate_location_cache
from ai.summarizer import summarize_article
from core.agent_controller import AgentController
import requests
from datetime import time

def run_tests():
    print("=== STARTING COMPREHENSIVE SETTINGS E2E TESTS ===")
    
    # 1. Canonical schema tests
    print("\n--- 1. Testing Canonical Schema ---")
    assert "theme" in CANONICAL_SETTINGS
    assert "ai_features" in CANONICAL_SETTINGS
    assert "location_city" in CANONICAL_SETTINGS
    assert "quiet_hours_start" in CANONICAL_SETTINGS
    assert "settings_version" in CANONICAL_SETTINGS
    assert CANONICAL_DEFAULTS["settings_version"] == SETTINGS_VERSION
    assert CANONICAL_DEFAULTS["theme"] == "dark"
    print("[PASS] Canonical schema keys and defaults verified.")

    # 2. Quiet hours midnight-crossing tests
    print("\n--- 2. Testing Quiet Hours Midnight-Crossing ---")
    # Quiet hours: 22:00 to 07:00
    assert is_in_quiet_hours("22:00", "07:00", time(22, 0)) == True
    assert is_in_quiet_hours("22:00", "07:00", time(23, 30)) == True
    assert is_in_quiet_hours("22:00", "07:00", time(0, 0)) == True
    assert is_in_quiet_hours("22:00", "07:00", time(6, 59)) == True
    assert is_in_quiet_hours("22:00", "07:00", time(7, 0)) == False
    assert is_in_quiet_hours("22:00", "07:00", time(12, 0)) == False
    assert is_in_quiet_hours("22:00", "07:00", time(21, 59)) == False
    # Non-midnight quiet hours: 13:00 to 15:00
    assert is_in_quiet_hours("13:00", "15:00", time(14, 0)) == True
    assert is_in_quiet_hours("13:00", "15:00", time(16, 0)) == False
    print("[PASS] Quiet hours midnight-crossing logic passed.")

    # 3. Schema validation tests
    print("\n--- 3. Testing Schema Validation ---")
    # Invalid theme
    is_valid, _, errors = validate_settings({"theme": "neon"})
    assert not is_valid
    assert "theme" in errors
    
    # Invalid article_limit
    is_valid, _, errors = validate_settings({"article_limit": 100})
    assert not is_valid
    assert "article_limit" in errors

    # Invalid manual location (auto=False, city missing)
    is_valid, _, errors = validate_settings({"location_auto": False, "location_city": "   "})
    assert not is_valid
    assert "location_city" in errors
    print("[PASS] Schema validation correctly rejects invalid values.")

    # 4. HTTP API validation via local server
    print("\n--- 4. Testing HTTP API /settings (GET & POST) ---")
    base_url = "http://127.0.0.1:8000"
    
    # GET /settings
    res = requests.get(f"{base_url}/settings")
    assert res.status_code == 200, f"GET /settings failed: {res.text}"
    get_data = res.json()
    assert get_data["status"] == "success"
    assert "theme" in get_data["data"]
    print("[PASS] GET /settings returns 200 with canonical settings structure.")

    # POST /settings invalid (should return 400)
    bad_payload = {"theme": "invalid_cyber", "article_limit": 3}
    res = requests.post(f"{base_url}/settings", json=bad_payload)
    assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
    err_json = res.json()
    assert err_json["status"] == "error"
    assert "theme" in err_json["errors"]
    assert "article_limit" in err_json["errors"]
    print("[PASS] POST /settings with invalid values returns structured 400 response.")

    # POST /settings valid update
    valid_payload = {
        "location_city": "Visakhapatnam",
        "location_state": "Andhra Pradesh",
        "location_country": "India",
        "location_auto": False,
        "personalized_feed": True,
        "cat_local": True,
        "cat_national": True,
        "cat_global": True,
        "cat_technology": True,
        "cat_business": True,
        "cat_sports": False, # Sports disabled in personalized feed
        "article_limit": 25,
        "show_images": True,
        "show_read_articles": True,
        "ai_features": False, # AI disabled
        "ai_summarization": False,
        "summary_length": "short",
        "notifications_enabled": False,
        "notify_breaking": True,
        "notify_daily": False,
        "quiet_hours_enabled": True,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
        "theme": "light",
        "font_size": "large",
        "ui_density": "compact",
        "animations": False,
        "settings_version": 1
    }
    res = requests.post(f"{base_url}/settings", json=valid_payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    saved_res = res.json()
    assert saved_res["status"] == "success"
    assert saved_res["data"]["theme"] == "light"
    assert saved_res["data"]["location_city"] == "Visakhapatnam"
    assert saved_res["data"]["cat_sports"] == False
    print("[PASS] POST /settings successfully saves settings.")

    # 5. Location priority tests
    print("\n--- 5. Testing Strict Location Priority ---")
    invalidate_location_cache()
    loc = get_user_location()
    assert loc["is_manual"] == True
    assert loc["city"] == "Visakhapatnam"
    assert loc["state"] == "Andhra Pradesh"
    assert loc["country"] == "India"
    print(f"[PASS] Manual location prioritized strictly: {loc}")

    # 6. AI hierarchy tests
    print("\n--- 6. Testing AI Hierarchy (ai_features=False) ---")
    mock_article = {
        "title": "Quantum Computing Breakthrough Announced",
        "description": "Researchers achieve room-temperature quantum coherence.",
        "content": "Researchers at TechLab have published findings on room-temperature quantum computing.",
        "category": "technology"
    }
    res_art = summarize_article(mock_article)
    summary = res_art.get("summary")
    is_ai = res_art.get("is_ai_summary")
    assert is_ai == False, "AI was called even though ai_features is False!"
    assert "room-temperature" in summary.lower() or "quantum" in summary.lower()
    print("[PASS] AI features disabled: fallback description returned without AI call.")

    # 7. Category preferences vs Navigation test
    print("\n--- 7. Testing Category Preferences vs Navigation ---")
    # In settings, cat_sports is False.
    # But /news?category=sports MUST return live sports news!
    res = requests.get(f"{base_url}/news?category=sports&limit=5")
    assert res.status_code == 200
    sports_data = res.json()
    assert sports_data["status"] == "ok"
    assert len(sports_data["data"]) > 0
    print(f"[PASS] Category navigation works: fetched {len(sports_data['data'])} sports articles despite cat_sports=False.")

    # Morning briefing should exclude sports because cat_sports is False
    controller = AgentController()
    briefing = controller.generate_briefing()
    for art in briefing.get("articles", []):
        cat = (art.get("category") or "").lower()
        assert cat != "sports", f"Sports article found in briefing despite cat_sports=False: {art['title']}"
    print("[PASS] Morning briefing respects disabled categories (no sports included).")

    # 8. Clear cache test (POST /data/clear_cache)
    print("\n--- 8. Testing Clear Cache ---")
    def get_article_counts_and_summaries():
        conn, db_type = get_connection()
        if db_type == "mongodb":
            database_name = os.getenv("DATABASE_NAME", "nexus_news")
            db = conn[database_name]
            total = db.articles.count_documents({})
            summaries = db.articles.count_documents({"summary": {"$ne": None, "$nin": ["", None]}})
            return total, summaries
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM news")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM news WHERE summary IS NOT NULL AND summary != ''")
            summaries = cursor.fetchone()[0]
            conn.close()
            return total, summaries

    # Verify article count before
    total_before, summaries_before = get_article_counts_and_summaries()

    res = requests.post(f"{base_url}/data/clear_cache")
    assert res.status_code == 200
    clear_json = res.json()
    assert clear_json["status"] == "success"
    assert "Cache cleared successfully" in clear_json["message"]

    # Verify article count after clear cache is unchanged
    total_after, summaries_after = get_article_counts_and_summaries()
    
    assert total_before == total_after, f"Articles deleted during cache clear! {total_before} vs {total_after}"
    assert summaries_after == 0, f"Summaries were not cleared! Found {summaries_after}"
    # Verify preferences still preserved
    settings_after_cache = get_all_settings()
    assert settings_after_cache["theme"] == "light"
    assert settings_after_cache["location_city"] == "Visakhapatnam"
    print(f"[PASS] Cache cleared: {total_after} articles preserved, summaries cleared to 0, settings preserved.")

    # 9. Reset application data test (POST /data/reset)
    print("\n--- 9. Testing Reset Application Data ---")
    res = requests.post(f"{base_url}/data/reset")
    assert res.status_code == 200
    reset_json = res.json()
    assert reset_json["status"] == "success"
    assert reset_json["data"]["theme"] == "dark" # Default restored
    assert reset_json["data"]["location_city"] == "" # Default restored
    assert reset_json["data"]["ai_features"] == True # Default restored

    # Verify articles still preserved
    total_after_reset, _ = get_article_counts_and_summaries()
    assert total_after_reset == total_before, f"Articles deleted during reset! {total_before} vs {total_after_reset}"
    print(f"[PASS] Application reset: all settings restored to defaults, {total_after_reset} articles preserved.")

    print("\n=== ALL COMPREHENSIVE SETTINGS TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_tests()
