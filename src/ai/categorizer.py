import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.logger import get_logger

logger = get_logger("categorizer")

# RULE: any keyword under 4 chars must have spaces around it e.g. " f1 "
# to prevent partial matches inside other words
CATEGORY_KEYWORDS = {
    "sports": [
        "cricket", "ipl 2026", " ipl ", "football match", "wicket",
        " fifa ", "olympic", "athlete", "champion", "trophy",
        "tennis", "badminton", "hockey match", "batting", "bowling",
        "innings", " odi ", "t20 match", "test match", "stadium",
        "ind vs", "vs afg", "vs aus", "vs eng", "vs pak", "vs nz",
        "big bash", " bbl ", "rohit sharma", "virat kohli", "bumrah",
        "dhoni", " rcb ", " csk ", " kkr ", " srh ", " pbks ",
        "premier league", "la liga", " nba ", " nfl ", " f1 ",
        "boxing match", "wrestling", "swimming race", "athletics",
        "squad live", "sports news", "sportsman", "cricket season",
        "uefa", "premier league", "football ban", "coach",
        "selection meet", "ipl match", "cricket team"
    ],
    "technology": [
        "artificial intelligence", "software", "hardware",
        "cybersecurity", "cloud computing", "machine learning",
        "coding", "programming", "gadget", "smartphone", "microchip",
        "openai", "chatgpt", "nvidia", "samsung galaxy",
        "electric vehicle", "5g network", "satellite launch",
        "nasa", "isro", "tech company", "silicon valley",
        "google i/o", "alphabet", "gemini", "wwdc", "iphone", "openai",
        "apple", "chatgpt", "musk", "altman",
        "data breach", "app launch", "technology company",
        "generative ai", "large language model"
    ],
    "business": [
        "stock market", "share market", "trade deal", "gdp growth",
        "inflation rate", "rupee falls", "dollar rises",
        "quarterly profit", "annual revenue", "reserve bank",
        "rbi rate", "tax policy", "union budget",
        "export import", "manufacturing sector",
        "sensex", "nifty", "sebi", "ipo launch", "mutual fund",
        "insurance policy", "bank loan", "edible oil",
        "crude oil price", "gold price", "market rally",
        "market crash", "quarterly results", "earnings report",
        "duty-free", "industry body", "fiscal year",
        "trade setup", "pre-market", "volatile market",
        "disciplined invest", "commodity market", "equity market",
        "imports rise", "exports fall", "trade surplus", "trade deficit"
    ],
    "global": [
        "united states", "white house", "pentagon", "china says",
        "russia ukraine", "nato summit", "united nations",
        "european union", "middle east", "international community",
        "world leaders", "foreign minister", "trade war",
        "senate", "iran", "israel", "lebanon", "west asia", "hostilities",
        "cassidy", "war live",
        "sanctions against", "trump", "biden", "g20 summit",
        "g7 meeting", "israel", "iran nuclear", "north korea",
        "taiwan strait", "sri lanka", "global economy",
        "world news", "foreign policy"
    ],
    "local": [
        "andhra pradesh", "telangana", "hyderabad", "vijayawada",
        "amaravati", "visakhapatnam", "tirupati", "warangal",
        "guntur", "kurnool", "ap government", "ts government",
        "ap cm", "ts cm", "municipal corporation",
        "nellore", "kurnool", "kavali", "chandrababu", "ap cm",
        "andhra pradesh cm", "chief minister advises",
        "zilla parishad", "panchayat", "andhra floods",
        "telangana rains", "vizag"
    ],
    "national": [
        "prime minister modi", "pm modi", "parliament session",
        "supreme court", "high court", "central government",
        "bjp", "congress party", "lok sabha", "rajya sabha",
        "election commission", "ministry of", "indian army",
        "heatwave", "chemists", "strike", "bandh", "kerala", "bengal",
        "k-rail", "ldf", "udf", "heat alert", "orange alert", "power demand",
        "navy", "aditi", "defence", "drdo",
        "indian navy", "indian air force", "home minister",
        "finance minister", "gst council", "national policy",
        "modi government", "india government", "new delhi policy",
        "scheme for india", "india scheme", "farmers scheme"
    ]
}

PRIORITY_ORDER = ["sports", "local", "national", "global", "technology", "business"]

def categorize(title, description="", debug=False):
    try:
        # Add spaces around text so " odi " matches at word boundaries
        text = " " + (title + " " + description).lower() + " "

        for category in PRIORITY_ORDER:
            for keyword in CATEGORY_KEYWORDS[category]:
                if keyword in text:
                    if debug:
                        print(f"    MATCHED: '{keyword}' → {category}")
                    logger.info(f"Categorized as: {category} | Title: {title[:40]}")
                    return category

        return "general"

    except Exception as e:
        logger.error(f"Categorization failed: {e}")
        return "general"

def categorize_news_list(news_list):
    for item in news_list:
        item["category"] = categorize(
            item.get("title", ""),
            item.get("description", "")
        )
    return news_list


if __name__ == "__main__":
    test_articles = [
        {"title": "IND vs AFG Squad Live: Bumrah workload, Rohit fitness headline the selection meet", "description": "cricket team"},
        {"title": "India wins cricket match against Australia",                                        "description": ""},
        {"title": "Google releases new AI model Gemini Ultra",                                        "description": "artificial intelligence"},
        {"title": "Modi launches new scheme for farmers in Delhi",                                    "description": "prime minister modi india government policy farmers scheme"},
        {"title": "Andhra Pradesh CM reviews flood situation in Vijayawada",                          "description": ""},
        {"title": "Stock market hits record high as inflation drops",                                 "description": "sensex nifty market rally quarterly results"},
        {"title": "India's edible oil imports rise 3% in FY26 on Nepal duty-free surge",              "description": "edible oil commodity duty-free industry body fiscal year"},
        {"title": "Big Bash 2026/27 season set to begin in Chennai, India",                           "description": "cricket season bbl"},
        {"title": "Supreme Court to decide validity of State control over Hindu temples",             "description": "supreme court india"},
        {"title": "Stay disciplined think five years out Deepak Shenoy on volatile markets",          "description": "stock market investment earnings report volatile market"},
        {"title": "Bill Gates Foundation fully exits Microsoft sells final stake",                    "description": "technology company"},
        {"title": "Pre-market action: Here's the trade setup for today's session",                   "description": "sensex nifty pre-market trade setup"},
    ]

    print("Categorizing articles...\n")
    results = categorize_news_list(test_articles)
    print()
    for item in results:
        print(f"  [{item['category'].upper():12}] {item['title'][:70]}")