import re
from typing import Tuple, Dict, Set

# Comprehensive English stop words list
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "also", "just", "said", "will", "new", "one", "two"
}

BOILERPLATE_PHRASES = [
    "account subscription benefits",
    "unlock these with subscription",
    "premium stories",
    "subscribe now",
    "subscription benefits",
    "already a subscriber",
    "sign in to continue",
    "login to continue",
    "click here to read",
    "read full article",
    "read full story",
    "continue reading",
    "terms of service",
    "terms of use",
    "privacy policy",
    "cookie policy",
    "all rights reserved",
    "advertisement",
    "sponsored content",
    "newsletter sign up",
    "sign up for newsletter",
    "subscribe to our newsletter",
    "we have migrated to a new commenting platform",
    "comments have to be in english",
    "please abide by our community guidelines",
    "community guidelines",
    "share your thoughts in the comments",
    "share your thoughts",
    "in the comments",
    "be respectful",
    "toi community guidelines",
    "post a comment",
    "leave a comment",
    "join the discussion",
    "join the conversation",
    "follow us on twitter",
    "follow us on facebook",
    "download the app",
    "download our app",
    "share this story",
    "read more on",
    "read more at",
    "read the full article",
    "read the full story"
]

def clean_text(text: str) -> str:
    """Normalize whitespace and remove unwanted characters."""
    if not text:
        return ""
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned

def is_boilerplate_text(text: str) -> bool:
    """Return True if text contains boilerplate, paywall, or subscription notices."""
    if not text:
        return True
    lowered = text.lower()
    for phrase in BOILERPLATE_PHRASES:
        if phrase in lowered:
            return True
    return False

def clean_boilerplate_from_content(text: str) -> str:
    """
    Remove boilerplate sentences or paragraphs from article text.
    Preserves valid journalistic content.
    """
    if not text:
        return ""
    
    # Split text by sentence or line breaks
    sentences = re.split(r'[\r\n]+|(?<=[.!?])\s+', text)
    clean_sentences = []
    
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        if is_boilerplate_text(s_clean):
            continue
        clean_sentences.append(s_clean)
        
    res = " ".join(clean_sentences)
    res = re.sub(r'^[|\s\-—]+', '', res).strip()
    return res

def extract_keywords(text: str) -> Set[str]:
    """Extract lowercased alphanumeric words with stop words removed."""
    if not text:
        return set()
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    return {w for w in words if len(w) >= 3 and w not in STOP_WORDS}

def extract_entities(text: str) -> Set[str]:
    """
    Heuristic extraction of named entities (capitalized phrases/names).
    Matches patterns like 'Santosh Lad', 'Hanagal', 'NASA', 'White House'.
    """
    if not text:
        return set()
    # Match capitalized words, including multi-word entities
    matches = re.findall(r'\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*\b', text)
    entities = set()
    for m in matches:
        m_str = m.strip()
        if len(m_str) >= 3 and m_str.lower() not in STOP_WORDS:
            entities.add(m_str.lower())
    return entities

def compute_similarity(text1: str, text2: str) -> float:
    """
    Compute TF-IDF cosine similarity between two texts.
    Falls back to Jaccard similarity if sklearn is unavailable.
    """
    if not text1 or not text2:
        return 0.0
        
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        vec = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vec.fit_transform([text1, text2])
        sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return float(sim)
    except Exception:
        # Fallback to token Jaccard similarity
        s1 = extract_keywords(text1)
        s2 = extract_keywords(text2)
        if not s1 or not s2:
            return 0.0
        return len(s1.intersection(s2)) / len(s1.union(s2))

def compute_relevance_score(title: str, content: str, summary: str) -> Tuple[float, Dict[str, float]]:
    """
    Compute a multi-signal relevance score (0.0 to 1.0) for a summary against article title & content.
    Signals:
      1. Important title keywords match
      2. Named entities match
      3. Meaningful word overlap (Jaccard)
      4. TF-IDF semantic similarity
    Penalties:
      - Boilerplate text detected -> score = 0.0
      - Unusually short summary (< 40 chars)
    """
    details = {
        "title_overlap": 0.0,
        "entity_overlap": 0.0,
        "word_overlap": 0.0,
        "tfidf_sim": 0.0,
        "boilerplate": 0.0,
        "final_score": 0.0
    }
    
    if not summary or not title:
        return 0.0, details
        
    if is_boilerplate_text(summary):
        details["boilerplate"] = 1.0
        return 0.0, details
        
    title_keywords = extract_keywords(title)
    summary_keywords = extract_keywords(summary)
    
    if not summary_keywords:
        return 0.0, details
        
    # 1. Title keyword overlap
    if title_keywords:
        title_overlap = len(title_keywords.intersection(summary_keywords)) / len(title_keywords)
    else:
        title_overlap = 0.0
    details["title_overlap"] = title_overlap
    
    # 2. Named entities match
    title_entities = extract_entities(title)
    summary_entities = extract_entities(summary)
    if title_entities:
        entity_overlap = len(title_entities.intersection(summary_entities)) / len(title_entities)
    else:
        # If title had no entities, check overlap with content entities
        content_entities = extract_entities(content[:1000]) if content else set()
        if content_entities:
            entity_overlap = len(content_entities.intersection(summary_entities)) / min(len(content_entities), 5)
        else:
            entity_overlap = title_overlap
    details["entity_overlap"] = entity_overlap
    
    # 3. Meaningful word overlap (Jaccard) between (title + content) and summary
    article_keywords = title_keywords.union(extract_keywords(content[:1500]))
    if article_keywords:
        word_overlap = len(summary_keywords.intersection(article_keywords)) / len(summary_keywords)
    else:
        word_overlap = title_overlap
    details["word_overlap"] = word_overlap
    
    # 4. TF-IDF Cosine Similarity
    ref_text = f"{title} {content[:1500]}"
    tfidf_sim = compute_similarity(ref_text, summary)
    details["tfidf_sim"] = tfidf_sim
    
    # Weighted composite score
    # For short articles TF-IDF is unreliable; keyword overlap and entities carry more signal.
    score = (
        0.40 * title_overlap +
        0.25 * entity_overlap +
        0.20 * word_overlap +
        0.15 * tfidf_sim
    )
    
    # Length sanity check
    if len(summary.strip()) < 40:
        score *= 0.5
        
    final_score = max(0.0, min(1.0, score))
    details["final_score"] = final_score
    return final_score, details

def is_summary_relevant(title: str, content: str, summary: str, threshold: float = 0.15) -> Tuple[bool, float, str]:
    """
    Determine if a summary genuinely describes the article using multi-signal evaluation.
    Returns: (is_valid: bool, score: float, reason: str)

    Design notes:
    - The hard 'zero title overlap → reject' gate was removed. AI summaries frequently
      rephrase headlines using synonyms or pronouns; a zero-keyword-overlap summary can
      still be semantically valid and should be evaluated on composite score alone.
    - Threshold lowered to 0.20 to account for short titles and synonym-heavy AI output.
    - Only hard-rejects on boilerplate or when the composite score is below threshold
      AND there is genuinely no semantic overlap (tfidf_sim < 0.05 AND word_overlap < 0.15).
    """
    if not summary or not summary.strip():
        return False, 0.0, "Empty summary"

    if is_boilerplate_text(summary):
        return False, 0.0, "Summary contains boilerplate/paywall phrases"

    score, details = compute_relevance_score(title, content, summary)

    tfidf_sim  = details.get("tfidf_sim", 0.0)
    word_overlap = details.get("word_overlap", 0.0)
    title_overlap = details.get("title_overlap", 0.0)
    entity_overlap = details.get("entity_overlap", 0.0)

    # Hard-reject only when there is truly zero semantic signal from ALL signals
    # (This prevents completely hallucinated or off-topic text from passing)
    if tfidf_sim < 0.05 and word_overlap < 0.15 and title_overlap == 0.0 and entity_overlap == 0.0:
        return False, score, f"No semantic overlap on any signal (tfidf={tfidf_sim:.2f}, word={word_overlap:.2f})"

    if score < threshold:
        return False, score, f"Relevance score {score:.2f} below threshold {threshold:.2f}"

    return True, score, "Passed multi-signal relevance validation"


def truncate_clean(text: str, max_chars: int = 500, min_chars: int = 300) -> str:
    """
    Intelligently truncate text to <= max_chars without cutting words in the middle.
    Prefers breaking at sentence boundaries when length allows.
    """
    if not text:
        return ""
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
        
    # Look for sentence boundary before max_chars
    truncated_candidate = text[:max_chars]
    sentence_end = max(
        truncated_candidate.rfind(". "),
        truncated_candidate.rfind("! "),
        truncated_candidate.rfind("? ")
    )
    
    if sentence_end >= min_chars:
        return truncated_candidate[:sentence_end + 1].strip()
        
    # If no sentence boundary in reasonable range, break at last word boundary
    last_space = truncated_candidate.rfind(" ")
    if last_space > 0:
        return truncated_candidate[:last_space].strip() + "..."
        
    return truncated_candidate[:max_chars - 3] + "..."
