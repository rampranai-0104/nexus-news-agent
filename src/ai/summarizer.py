import os
import sys
import re
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.logger import get_logger

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
logger = get_logger("summarizer")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def groq_summarize(text):
    """Summarize using Groq's free LLaMA 3 — fast and high quality."""
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        # Clean up the text first
        text = re.sub(r'\s+', ' ', text).strip()
        text = text[:3000]  # Groq handles long text well

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a news summarizer. "
                        "Write a clear, factual 3-4 sentence paragraph summary "
                        "of the article the user gives you. "
                        "Do NOT copy sentences directly — rephrase in your own words. "
                        "Do NOT include opinions or analysis. "
                        "Just the key facts, who, what, where, why."
                    )
                },
                {
                    "role": "user",
                    "content": f"Summarize this news article:\n\n{text}"
                }
            ],
            temperature=0.3,
            max_tokens=200
        )

        summary = response.choices[0].message.content.strip()
        logger.info("Groq summary generated successfully")
        return summary

    except Exception as e:
        logger.error(f"Groq summarization failed: {e}")
        return None


def local_summarize(text, sentence_count=4):
    """Fallback: local sumy summarizer — no API needed."""
    try:
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers    import Tokenizer
        from sumy.summarizers.lsa   import LsaSummarizer
        from sumy.nlp.stemmers      import Stemmer
        from sumy.utils             import get_stop_words

        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) < 100:
            return text

        parser     = PlaintextParser.from_string(text, Tokenizer("english"))
        stemmer    = Stemmer("english")
        summarizer = LsaSummarizer(stemmer)
        summarizer.stop_words = get_stop_words("english")

        sentences = summarizer(parser.document, sentence_count)
        summary   = " ".join(str(s) for s in sentences)

        if summary and len(summary) > 50:
            logger.info("Local summary generated successfully")
            return summary

        return text[:200].strip() + "..."

    except Exception as e:
        logger.error(f"Local summarization failed: {e}")
        return text[:200].strip() + "..." if text else ""


def summarize(text):
    if not text or len(text.strip()) < 50:
        return text.strip() if text else ""

    # Step 1 — Try Groq first (best quality, free)
    result = groq_summarize(text)
    if result:
        return result

    # Step 2 — Fall back to local sumy
    logger.info("Groq unavailable — using local summarizer")
    return local_summarize(text, sentence_count=4)


def summarize_news_list(news_list):
    summarized = []
    total = len(news_list)
    for i, item in enumerate(news_list):
        text = item.get("content") or item.get("description") or item.get("title", "")
        print(f"  [{i+1}/{total}] Summarizing: {item['title'][:45]}...")
        item["summary"] = summarize(text)
        summarized.append(item)
    return summarized


# ── Test ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_text = """
    The Indian Premier League 2026 season has been one of the most exciting in recent memory.
    Mumbai Indians have been knocked out of playoff contention after a series of poor performances.
    Kolkata Knight Riders are facing a must-win situation in their remaining matches.
    The team has struggled with batting consistency despite having world-class players.
    Captain Shreyas Iyer has been in poor form, managing only 180 runs in 10 matches.
    However, their bowling attack led by Varun Chakravarthy has been exceptional this season.
    KKR need to win their next three matches and hope other results go in their favour.
    The match against Chennai Super Kings on Friday will be crucial for their playoff hopes.
    """

    print("Testing Groq summarizer...\n")
    result = summarize(test_text)
    print(f"Summary:\n{result}")