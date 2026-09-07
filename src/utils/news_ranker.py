import datetime
from utils.date_parser import parse_to_utc_iso
from config import get_config
from dateutil import parser

def calculate_importance(article, location=None, preferences=None):
    """
    Score article 0-100 based on multiple factors.
    Recency (25), Breaking (20), Source (15), Multi-source (15), User pref (15), Local (10)
    """
    score = 0.0
    config = get_config()
    source_rel = config.get("source_reliability", {})
    
    # 1. Recency (25 max)
    try:
        pub_iso = article.get("published_at") or parse_to_utc_iso(article.get("published"))
        if pub_iso:
            pub_date = datetime.datetime.fromisoformat(pub_iso.replace("Z", "+00:00"))
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            hours_diff = (now_utc - pub_date).total_seconds() / 3600
            
            if hours_diff <= 1:
                score += 25
            elif hours_diff <= 6:
                score += 18
            elif hours_diff <= 24:
                score += 10
            elif hours_diff <= 48:
                score += 4
    except Exception:
        pass
        
    # 2. Breaking score (20 max)
    if article.get("is_breaking") == 1:
        score += 20
        
    # 3. Source reliability (15 max)
    source = article.get("source", "")
    if any(s.lower() in source.lower() for s in source_rel.get("high", [])):
        score += 15
    elif any(s.lower() in source.lower() for s in source_rel.get("medium", [])):
        score += 10
    else:
        score += 5
        
    # 4. Multi-source / baseline
    score += 5
    
    # 5. User preference (15 max)
    if preferences and article.get("category") in preferences:
        score += 15
        
    # 6. Local relevance (10 max)
    if location:
        loc_city = location.get("city", "").lower()
        loc_state = location.get("state", "").lower()
        content = (article.get("title", "") + " " + article.get("description", "")).lower()
        if (loc_city and loc_city in content) or (loc_state and loc_state in content):
            score += 10
            
    # Cap at 100
    return min(100.0, score)

def rank_articles(news_list, location=None, preferences=None):
    """
    Rank a list of articles in-place and return the sorted list.
    """
    if not preferences:
        preferences = get_config().get("preferred_categories", [])
        
    for item in news_list:
        item["importance"] = calculate_importance(item, location, preferences)
        
    # Sort descending by importance
    return sorted(news_list, key=lambda x: x.get("importance", 0.0), reverse=True)
