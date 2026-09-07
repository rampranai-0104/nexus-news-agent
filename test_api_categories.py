import requests
import json

BASE_URL = "http://127.0.0.1:8000"
CATEGORIES = ["sports", "technology", "business", "local", "national", "global"]

def test_category_api_filtering():
    print("--- Testing API Category Filtering ---")
    for cat in CATEGORIES:
        res = requests.get(f"{BASE_URL}/news", params={"category": cat, "limit": 25})
        assert res.status_code == 200, f"Failed GET /news?category={cat}: {res.status_code}"
        data = res.json()
        articles = data.get("data", [])
        assert len(articles) > 0, f"No articles returned for category '{cat}'"
        
        # Verify 100% of returned articles have category == cat
        non_matching = [a for a in articles if a.get("category") != cat]
        assert len(non_matching) == 0, f"Found {len(non_matching)} non-{cat} articles in /news?category={cat}: {[a.get('category') for a in non_matching]}"
        print(f"[PASS] /news?category={cat}: returned {len(articles)} articles, 100% strictly category='{cat}'")

def test_all_news_endpoint():
    print("\n--- Testing All News Endpoint ---")
    res = requests.get(f"{BASE_URL}/news", params={"limit": 30})
    assert res.status_code == 200
    articles = res.json().get("data", [])
    assert len(articles) > 0
    categories_present = set(a.get("category") for a in articles)
    print(f"[PASS] /news (All News) contains {len(articles)} articles across categories: {categories_present}")
    # Verify no invalid categories appear
    for cat in categories_present:
        assert cat in CATEGORIES, f"Unexpected category '{cat}' in All News"

def test_categories_counts_endpoint():
    print("\n--- Testing /categories Endpoint ---")
    res = requests.get(f"{BASE_URL}/categories")
    assert res.status_code == 200
    data = res.json().get("data", {})
    print(f"Categories distribution: {json.dumps(data, indent=2)}")
    assert "world" not in data or data["world"] == 0
    assert "general" not in data or data["general"] == 0
    for cat in CATEGORIES:
        assert cat in data, f"Missing category '{cat}' in /categories"
        assert data[cat] > 0, f"Category '{cat}' has 0 articles"
    print("[PASS] /categories returns clean counts for all 6 canonical categories.")

def test_breaking_news_categories():
    print("\n--- Testing /breaking News Categories ---")
    res = requests.get(f"{BASE_URL}/breaking")
    assert res.status_code == 200
    articles = res.json().get("data", [])
    print(f"Breaking news count: {len(articles)}")
    for a in articles:
        assert a.get("category") in CATEGORIES, f"Invalid category in breaking: {a.get('category')}"
    print("[PASS] Breaking news retains valid article categories.")

def test_briefing_categories():
    print("\n--- Testing /briefing News Categories ---")
    res = requests.get(f"{BASE_URL}/briefing", params={"limit": 10})
    assert res.status_code == 200
    articles = res.json().get("data", {}).get("articles", [])
    print(f"Briefing articles count: {len(articles)}")
    for a in articles:
        assert a.get("category") in CATEGORIES, f"Invalid category in briefing: {a.get('category')}"
    print("[PASS] Morning Briefing uses valid categories.")

if __name__ == "__main__":
    test_category_api_filtering()
    test_all_news_endpoint()
    test_categories_counts_endpoint()
    test_breaking_news_categories()
    test_briefing_categories()
    print("\nAll category API filtering tests passed successfully!")
