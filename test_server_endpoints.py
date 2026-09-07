import sys
import os
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_endpoints():
    print("--- 1. Testing GET /refresh-status ---")
    res = requests.get(f"{BASE_URL}/refresh-status", headers={"Cache-Control": "no-cache"})
    print("Status code:", res.status_code)
    data = res.json()
    print("Refresh status response:", json.dumps(data, indent=2))
    assert res.status_code == 200
    assert "status" in data
    assert "is_fresh" in data
    print("[PASS] GET /refresh-status verified.")

    print("\n--- 2. Testing POST /refresh-news (TTL check) ---")
    # First call with force=False when fresh should return status 'fresh'
    res_ttl = requests.post(f"{BASE_URL}/refresh-news?force=false")
    print("TTL check response:", res_ttl.json())
    assert res_ttl.status_code == 200
    assert res_ttl.json().get("status") in ["fresh", "success"]
    print("[PASS] TTL Freshness Check verified.")

    print("\n--- 3. Testing GET /news (Newest-first sorting) ---")
    res_news = requests.get(f"{BASE_URL}/news?limit=10")
    assert res_news.status_code == 200
    news_data = res_news.json()
    articles = news_data.get("data", [])
    print(f"Retrieved {len(articles)} articles.")
    
    # Verify ordering of published_at
    timestamps = [a.get("published_at") or a.get("published") for a in articles if (a.get("published_at") or a.get("published"))]
    print(f"Top 5 article timestamps: {timestamps[:5]}")
    for i in range(len(timestamps) - 1):
        if timestamps[i] and timestamps[i+1]:
            assert timestamps[i] >= timestamps[i+1], f"Timestamp ordering violation: {timestamps[i]} is before {timestamps[i+1]}"
    print("[PASS] Newest-first sorting verified across /news.")

    print("\n--- 4. Testing Category Feeds ---")
    categories = ["national", "global", "technology", "business", "sports", "local"]
    for cat in categories:
        res_cat = requests.get(f"{BASE_URL}/news?category={cat}&limit=5")
        assert res_cat.status_code == 200
        cat_data = res_cat.json()
        print(f"Category '{cat}': {len(cat_data.get('data', []))} articles returned.")
    print("[PASS] Category feeds verified.")

    print("\n--- 5. Testing For You, Morning Briefing, and Breaking News ---")
    res_foryou = requests.get(f"{BASE_URL}/for-you")
    assert res_foryou.status_code == 200
    print("For You total articles:", len(res_foryou.json().get("data", {}).get("articles", [])))

    res_briefing = requests.get(f"{BASE_URL}/briefing")
    assert res_briefing.status_code == 200
    print("Briefing total articles:", len(res_briefing.json().get("data", {}).get("articles", [])))

    res_breaking = requests.get(f"{BASE_URL}/breaking")
    assert res_breaking.status_code == 200
    print("Breaking news count:", len(res_breaking.json().get("data", [])))

    print("\nAll endpoint tests passed successfully! 🎉")

if __name__ == "__main__":
    test_endpoints()
