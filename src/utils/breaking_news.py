import re
import os
from core.logger import get_logger

logger = get_logger("breaking_news")

def detect_breaking(news_list):
    """
    Score articles for breaking news status.
    If score >= threshold, mark is_breaking = 1
    """
    urgency_keywords = [
        "breaking", "just in", "urgent", "alert", "developing", "exclusive",
        "flash", "live updates", "earthquake", "attack", "resigns", "crisis"
    ]
    
    threshold_str = os.environ.get("BREAKING_SCORE_THRESHOLD", "65")
    try:
        threshold = int(threshold_str)
    except:
        threshold = 65
        
    highest_score = 0
    candidates = 0
    detected = 0
    
    # We will score articles in place
    for article in news_list:
        score = 0
        title = article.get("title", "").lower()
        desc = article.get("description", "").lower()
        content = title + " " + desc
        
        # 1. Urgency Keywords (+25)
        if any(keyword in content for keyword in urgency_keywords):
            score += 25
            
        # 2. Category (+20)
        cat = article.get("category", "")
        if cat in ["national", "global"]:
            score += 20
            
        # 3. Already marked as breaking by ranker/fetcher (+50)
        if article.get("is_breaking") == 1:
            score += 50
            
        if score > 0:
            candidates += 1
            
        if score > highest_score:
            highest_score = score
            
        if score >= threshold:
            article["is_breaking"] = 1
            detected += 1
        else:
            article["is_breaking"] = 0
            
    logger.info(f"""
    Breaking News Analysis:
    Total checked: {len(news_list)}
    Highest score: {highest_score}
    Threshold: {threshold}
    Candidates: {candidates}
    Detected: {detected}
    """)
    
    return news_list
