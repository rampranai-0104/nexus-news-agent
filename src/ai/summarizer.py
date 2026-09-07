import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from groq import Groq
from openai import OpenAI
from config import GROQ_API_KEY, OPENAI_API_KEY, get_config
from core.logger import get_logger
from db.database import get_cached_summary, save_cached_summary
from utils.text_utils import (
    clean_text,
    is_boilerplate_text,
    clean_boilerplate_from_content,
    is_summary_relevant,
    truncate_clean,
    extract_keywords,
    STOP_WORDS
)

logger = get_logger("summarizer")

provider_status = {
    "groq": True,
    "openai": True
}
ai_stats = {
    "generated": 0,
    "failures": 0
}

_ai_lock = threading.Lock()

def groq_summarize(text, system_prompt):
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is missing")
    client = Groq(api_key=GROQ_API_KEY)
    model = os.environ.get("AI_MODEL", "groq/compound-mini")
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        model=model,
        temperature=0.3,
        max_tokens=250
    )
    return chat_completion.choices[0].message.content.strip()

def openai_summarize(text, system_prompt):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is missing")
    client = OpenAI(api_key=OPENAI_API_KEY)
    model = os.environ.get("AI_MODEL", "gpt-3.5-turbo")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.3,
        max_tokens=250
    )
    return response.choices[0].message.content.strip()

def summarize(text, article_url=None):
    """
    Summarize text with swappable AI providers and caching.
    Respects user AI feature toggle, ai_summarization toggle, and summary length settings.
    """
    if not text or len(text) < 30:
        return ""
        
    from db.database import get_all_settings
    settings = get_all_settings()
    
    ai_features = settings.get("ai_features", True)
    ai_summarization = settings.get("ai_summarization", True)
    if not ai_features or not ai_summarization:
        # AI Features or AI Summarization is OFF: non-AI fallback
        return truncate_clean(text, 500)
        
    # Check cache
    if article_url:
        cached = get_cached_summary(article_url)
        if cached and not is_boilerplate_text(cached):
            return cached
            
    config = get_config()
    provider = config.get("ai_provider", "groq")
    
    summary_length = settings.get("summary_length", "medium")
    if summary_length == "short":
        system_prompt = (
            "You are a professional news editor for Nexus News Agent. "
            "Summarize the key facts of the following news story into a single concise, factual sentence of 150-250 characters (never exceed 500 characters). "
            "Do NOT repeat the headline word-for-word. Do NOT add commentary. Output only the direct factual summary."
        )
    elif summary_length == "detailed":
        system_prompt = (
            "You are a professional news editor for Nexus News Agent. "
            "Summarize the key facts of the following news story into a detailed, comprehensive paragraph of approximately 400-480 characters (never exceed 500 characters). "
            "Cover: WHAT happened, WHO/WHERE involved, and WHY it matters. "
            "Do NOT repeat the headline word-for-word. Do NOT add commentary. Output only the direct factual summary."
        )
    else:
        system_prompt = (
            "You are a professional news editor for Nexus News Agent. "
            "Summarize the key facts of the following news story into a concise, factual paragraph of approximately 350-450 characters (never exceed 500 characters). "
            "Cover: WHAT happened, WHO/WHERE involved, and WHY it matters. "
            "Do NOT repeat the headline word-for-word. Do NOT add opinions, speculation, or commentary. "
            "Do NOT include introductory text like 'Title:', 'Summary:', or 'Here is a summary:'. "
            "Output only the direct factual summary."
        )
    
    summary = ""
    
    # Provider 1
    if provider == "groq":
        primary, fallback = ("groq", groq_summarize), ("openai", openai_summarize)
    else:
        primary, fallback = ("openai", openai_summarize), ("groq", groq_summarize)

    try:
        with _ai_lock:
            p_status = provider_status[primary[0]]
        if p_status:
            try:
                summary = primary[1](text, system_prompt)
            except Exception as e:
                logger.warning(f"{primary[0].capitalize()} configuration/execution failed: {e}. Disabling provider for this run.")
                with _ai_lock:
                    provider_status[primary[0]] = False
                
        with _ai_lock:
            fb_status = provider_status[fallback[0]]
        if not summary and fb_status:
            try:
                summary = fallback[1](text, system_prompt)
            except Exception as e:
                logger.warning(f"{fallback[0].capitalize()} configuration/execution failed: {e}. Disabling provider for this run.")
                with _ai_lock:
                    provider_status[fallback[0]] = False

        if not summary:
            raise Exception("No active providers available.")
            
        with _ai_lock:
            ai_stats["generated"] += 1
            
    except Exception as e:
        with _ai_lock:
            if ai_stats["failures"] == 0:
                logger.error("AI summarization completely failed or providers exhausted. Skipping AI for remaining pipeline.")
            ai_stats["failures"] += 1
        summary = ""
        
    return summary

def get_ai_stats():
    return ai_stats


def extractive_summarize(title: str, description: str, content: str, max_chars: int = 500) -> str:
    """
    Deterministic extractive summarizer — used as the final fallback when AI is
    unavailable or produces invalid output.  Works entirely from real article data.

    Algorithm:
      1. Build a candidate pool from description + content sentences.
      2. Remove boilerplate sentences individually (not the entire field).
      3. Score each sentence by:
         a. Keyword overlap with the article title.
         b. Position bonus (earlier = more important).
         c. Named-entity bonus (capitalized multi-word phrases).
      4. Pick the top-scoring sentences until max_chars is reached.
      5. Return combined text truncated cleanly.

    Never fabricates content — every word comes from the article.
    """
    title_kws = extract_keywords(title) if title else set()

    # Build candidate sentences from description then content
    raw_pool = []
    for source in [description, content]:
        if not source:
            continue
        cleaned = clean_boilerplate_from_content(source)
        if not cleaned:
            continue
        # Split on sentence boundaries and line breaks
        parts = re.split(r'[\r\n]+|(?<=[.!?])\s+', cleaned)
        raw_pool.extend(parts)

    # Also include the title itself as a seed if pool is empty
    if title and not raw_pool:
        raw_pool = [title]

    seen = set()
    candidates = []
    for s in raw_pool:
        s = s.strip()
        norm = s.lower()
        if not s or len(s) < 20 or norm in seen:
            continue
        if is_boilerplate_text(s):
            continue
        seen.add(norm)
        candidates.append(s)

    if not candidates:
        # Last resort: just use the title itself
        return truncate_clean(title, max_chars) if title else ""

    def score_sentence(idx: int, s: str) -> float:
        s_kws = extract_keywords(s)
        if title_kws:
            kw_overlap = len(title_kws & s_kws) / len(title_kws)
        else:
            kw_overlap = 0.0
        # Position bonus: first 3 sentences of description are most important
        position_bonus = max(0.0, 0.3 - idx * 0.05)
        # Named-entity bonus: count capitalized words
        cap_words = len(re.findall(r'\b[A-Z][a-z]+\b', s))
        entity_bonus = min(0.3, cap_words * 0.05)
        return kw_overlap + position_bonus + entity_bonus

    scored = sorted(
        enumerate(candidates),
        key=lambda t: score_sentence(t[0], t[1]),
        reverse=True
    )

    # Greedy fill up to max_chars
    selected = []
    total_len = 0
    for _, s in scored:
        if total_len + len(s) + 1 > max_chars:
            break
        selected.append(s)
        total_len += len(s) + 1
        if len(selected) >= 4:
            break

    # Restore original ordering for readability
    order = {s: i for i, (_, s) in enumerate(scored)}
    selected.sort(key=lambda s: candidates.index(s) if s in candidates else 0)

    result = " ".join(selected).strip()
    return truncate_clean(result, max_chars) if result else truncate_clean(title, max_chars)

def _summarize_single_article(article):
    """
    Summarize a single article following the strict fallback hierarchy:
    1. Return existing valid AI summary if cached/present.
    2. AI summary (Groq -> OpenAI fallback) with multi-signal relevance validation.
    3. If AI fails/invalid: extractive summary from real article sentences (is_ai_summary=False).
    4. Only fall back to "Summary unavailable" if the article has NO usable text at all.
    """
    title = clean_text(article.get("title", ""))
    raw_desc = clean_text(article.get("description", "") or "")
    raw_content = article.get("content", "") or ""
    url = article.get("url", "")

    # Sentence-level boilerplate cleaning (not whole-field rejection)
    desc = clean_boilerplate_from_content(raw_desc) if raw_desc else ""
    content = clean_boilerplate_from_content(raw_content) if raw_content else ""

    # Step 1: Reuse existing valid summary
    existing_summary = article.get("summary", "") or ""
    if (existing_summary
            and existing_summary != "Summary unavailable for this article."
            and not is_boilerplate_text(existing_summary)):
        body_ref = content or desc
        valid, score, reason = is_summary_relevant(title, body_ref, existing_summary)
        if valid:
            article["summary"] = truncate_clean(existing_summary, 500)
            article["is_ai_summary"] = article.get("is_ai_summary", True)
            return article
        # Existing summary failed validation — fall through to re-summarize

    # Candidate body for AI summarization
    body = content if (content and len(content) > len(desc)) else desc

    from db.database import get_all_settings
    settings = get_all_settings()
    ai_features = settings.get("ai_features", True)
    ai_summarization = settings.get("ai_summarization", True)
    ai_enabled = ai_features and ai_summarization

    ai_summary = ""
    if ai_enabled and (body or title):
        input_parts = []
        if title:
            input_parts.append(f"Title: {title}")
        if body:
            input_parts.append(f"Content: {body[:2500]}")
        content_to_summarize = "\n\n".join(input_parts).strip()
        try:
            ai_summary = summarize(content_to_summarize, url)
        except Exception as e:
            logger.warning(f"AI summarization call error for '{title}': {e}")
            ai_summary = ""

    # Step 2: Validate AI summary
    if ai_summary and not is_boilerplate_text(ai_summary):
        is_valid, score, reason = is_summary_relevant(title, body, ai_summary)
        if is_valid:
            final_summary = truncate_clean(ai_summary, 500)
            article["summary"] = final_summary
            article["is_ai_summary"] = True
            logger.info(f"Summary source: AI | Title: {title} | Relevance score: {score:.2f}")
            if url:
                save_cached_summary(url, final_summary)
            return article
        else:
            logger.warning(f"AI summary validation failed — Title: {title} | score={score:.2f} | {reason}")

    # Step 3: Extractive fallback — always produces something if ANY text exists
    extractive = extractive_summarize(title, desc, content, max_chars=500)
    if extractive and extractive != title:  # worth showing
        article["summary"] = extractive
        article["is_ai_summary"] = False
        logger.info(f"Summary source: extractive | Title: {title}")
        if url:
            save_cached_summary(url, extractive)
        return article

    # Step 4: Title-only synthesis — only if genuinely nothing else exists
    if title:
        article["summary"] = truncate_clean(title, 500)
        article["is_ai_summary"] = False
        logger.info(f"Summary source: title-only | Title: {title}")
        return article

    # Step 5: Truly empty article
    article["summary"] = "Summary unavailable for this article."
    article["is_ai_summary"] = False
    logger.info(f"Summary source: unavailable | Title: {title} | No usable content found")
    return article


def summarize_news_list(news_list):
    """
    Summarize a list of articles using controlled concurrent batching.
    Used for JIT summarization at the API level.
    """
    if not news_list:
        return []
        
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_summarize_single_article, article): article for article in news_list}
        
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error summarizing article: {e}")
                
    return news_list

summarize_article = _summarize_single_article