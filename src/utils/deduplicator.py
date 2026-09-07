import difflib
from core.logger import get_logger

logger = get_logger("deduplicator")

def deduplicate(news_list):
    """
    Remove duplicate articles using multiple strategies.
    1. URL exact match
    2. Exact title match (after normalization)
    3. Fuzzy title match (>= 0.85 similarity)
    
    Keeps the one with longest content or more reliable source.
    """
    unique_articles = []
    seen_urls = set()
    
    # Sort so that we process articles with longest content first
    sorted_news = sorted(news_list, key=lambda x: len(x.get("content", "") + x.get("description", "")), reverse=True)
    
    for article in sorted_news:
        url = article.get("url")
        title = article.get("title", "")
        
        # Strategy 1: URL match
        if url and url in seen_urls:
            continue
            
        # Normalize title for comparison
        norm_title = "".join(c.lower() for c in title if c.isalnum() or c.isspace()).strip()
        
        # Strategy 2 & 3: Exact and fuzzy title match
        is_duplicate = False
        for existing in unique_articles:
            ex_title = existing.get("title", "")
            ex_norm = "".join(c.lower() for c in ex_title if c.isalnum() or c.isspace()).strip()
            
            # Exact
            if norm_title == ex_norm and len(norm_title) > 0:
                is_duplicate = True
                break
                
            # Fuzzy
            if len(norm_title) > 15 and len(ex_norm) > 15:
                ratio = difflib.SequenceMatcher(None, norm_title, ex_norm).ratio()
                if ratio >= 0.85:
                    is_duplicate = True
                    break
                    
        if not is_duplicate:
            unique_articles.append(article)
            if url:
                seen_urls.add(url)
                
    logger.info(f"Deduplicated {len(news_list)} down to {len(unique_articles)} articles")
    return unique_articles
