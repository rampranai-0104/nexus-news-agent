import re

def clean_headline(title: str) -> str:
    """
    Clean noisy headlines using heuristics.
    """
    if not title:
        return ""
        
    cleaned = title
    
    # Common prefixes to remove
    prefixes = [
        r"(?i)^NDTV:\s*",
        r"(?i)^BBC News\s*-\s*",
        r"(?i)^Breaking News:\s*",
        r"(?i)^Watch:\s*",
        r"(?i)^Live Updates:\s*"
    ]
    for p in prefixes:
        cleaned = re.sub(p, "", cleaned)
        
    # Common suffixes to remove
    suffixes = [
        r"\s*\|\s*The Hindu$",
        r"\s*-\s*Times of India$",
        r"\s*-\s*NDTV$",
        r"\s*\|\s*BBC News$",
        r"\s*-\s*TechCrunch$",
        r"\s*-\s*CNN$"
    ]
    for s in suffixes:
        cleaned = re.sub(s, "", cleaned)
        
    # Fix broken encodings
    replacements = {
        "â€™": "'",
        "&amp;": "&",
        "&quot;": '"',
        "&#39;": "'",
        "&lt;": "<",
        "&gt;": ">"
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
        
    # Normalize excessive spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned

def clean_all_headlines(news_list):
    """
    Clean headlines for a list of articles in place.
    """
    for item in news_list:
        if "title" in item:
            item["title"] = clean_headline(item["title"])
    return news_list
