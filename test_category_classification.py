import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from ai.categorizer import categorize_article, classify_text_detailed, VALID_CATEGORIES

def test_twelve_specified_test_cases():
    """
    Test the 12 explicit test cases from the specification:
    TEST 1: "India wins the final cricket match after brilliant batting" -> SPORTS
    TEST 2: "New AI processor promises faster on-device computing" -> TECHNOLOGY
    TEST 3: "Company reports record quarterly revenue" -> BUSINESS
    TEST 4: "Karnataka government announces Bengaluru infrastructure project" -> LOCAL
    TEST 5: "India announces nationwide education reforms" -> NATIONAL
    TEST 6: "US and China announce new international trade agreement" -> GLOBAL
    TEST 7: "Cricket team adopts AI analytics before World Cup" -> SPORTS
    TEST 8: "Technology company launches AI platform for sports teams" -> TECHNOLOGY or BUSINESS
    TEST 9: "Sports streaming app signs deal with cricket league" -> SPORTS
    TEST 10: "Apple reports strong quarterly earnings" -> BUSINESS
    TEST 11: "Apple unveils new iPhone with upgraded processor" -> TECHNOLOGY
    TEST 12: "Football club signs new player" -> SPORTS
    """
    cases = [
        ("India wins the final cricket match after brilliant batting", "sports"),
        ("New AI processor promises faster on-device computing", "technology"),
        ("Company reports record quarterly revenue", "business"),
        ("Karnataka government announces Bengaluru infrastructure project", "local"),
        ("India announces nationwide education reforms", "national"),
        ("US and China announce new international trade agreement", "global"),
        ("Cricket team adopts AI analytics before World Cup", "sports"),
        ("Technology company launches AI platform for sports teams", ["technology", "business"]),
        ("Sports streaming app signs deal with cricket league", "sports"),
        ("Apple reports strong quarterly earnings", "business"),
        ("Apple unveils new iPhone with upgraded processor", "technology"),
        ("Football club signs new player", "sports"),
    ]

    for title, expected in cases:
        article = {"title": title, "description": "", "content": ""}
        result = categorize_article(article)
        if isinstance(expected, list):
            assert result in expected, f"Failed for '{title}': expected one of {expected}, got '{result}'"
        else:
            assert result == expected, f"Failed for '{title}': expected '{expected}', got '{result}'"
        print(f"[PASS] '{title}' -> {result} (confidence: {article.get('category_confidence')})")

def test_sports_leakage_prevented():
    """Sports news mentioning tech or business must NOT leak into Technology or Business."""
    leakage_cases = [
        "Virat Kohli scores a century in the third ODI",
        "India announces squad for the World Cup",
        "India secure thrilling victory in final ODI",
        "Ball cut in half to accommodate both Josh Tongue and Ollie Robinson",
        "Indian cricket team adopts new AI analytics platform ahead of World Cup",
        "IPL 2026: Team signs massive sponsorship deal with technology company",
        "Premier league football match streaming live on mobile app"
    ]
    for title in leakage_cases:
        art = {"title": title, "description": "Details about the sporting match and tournament."}
        cat = categorize_article(art)
        assert cat == "sports", f"Sports leak detected for '{title}': got '{cat}' instead of 'sports'"

def test_technology_purity():
    """Technology articles must be about technology as the primary subject."""
    tech_cases = [
        "Nvidia announces new Blackwell GPU architecture for data centers",
        "OpenAI rolls out GPT-5 with improved reasoning capabilities",
        "Major cybersecurity vulnerability discovered in Linux kernel",
        "Google releases Android 16 update with new developer APIs",
        "Waymo expands autonomous robotaxi operations to new city"
    ]
    for title in tech_cases:
        art = {"title": title, "description": "Tech developments and hardware specifications."}
        cat = categorize_article(art)
        assert cat == "technology", f"Tech classification failed for '{title}': got '{cat}'"

def test_business_discipline():
    """Business stories must be about markets, economy, finance, earnings."""
    biz_cases = [
        "Sensex surges 800 points as foreign investors buy banking stocks",
        "RBI keeps repo rate unchanged at 6.5% amid inflation concerns",
        "Tech startup raises $50 million Series B funding round",
        "Tesla stock plunges after Q3 delivery numbers miss Wall Street estimates",
        "India GDP growth accelerates to 7.8% in first quarter"
    ]
    for title in biz_cases:
        art = {"title": title, "description": "Financial results and macroeconomic indicators."}
        cat = categorize_article(art)
        assert cat == "business", f"Business classification failed for '{title}': got '{cat}'"

def test_local_vs_national():
    """Distinguish local city/state stories from nationwide India stories."""
    local_cases = [
        "Power shock at 11 kV line: 2 Bescom workers injured in Bengaluru",
        "CID issues lookout notice for Karnataka Public Service Commission scam",
        "GHMC initiates road repair works across Hyderabad after heavy rain",
        "UKG student dies after alleged assault by teacher at Visakhapatnam school",
        "Bengaluru woman abducted and assaulted over loan dispute",
        "AP Rajya Sabha MP son booked after car fatally hits woman near Inorbit Mall in Hyderabad"
    ]
    for title in local_cases:
        art = {"title": title, "description": "Local regional reporting."}
        cat = categorize_article(art)
        assert cat == "local", f"Local classification failed for '{title}': got '{cat}'"

def test_global_vs_national():
    """Distinguish international global events from Indian national events."""
    global_cases = [
        "Israel-Gaza conflict escalates as ceasefire talks stall in Cairo",
        "US and China agree on new trade framework during bilateral summit",
        "Vladimir Putin meets North Korean leader Kim Jong Un in Moscow",
        "United Nations Security Council holds emergency meeting on Ukraine",
        "White House announces new economic sanctions on foreign officials"
    ]
    for title in global_cases:
        art = {"title": title, "description": "International affairs."}
        cat = categorize_article(art)
        assert cat == "global", f"Global classification failed for '{title}': got '{cat}'"

    national_cases = [
        "Supreme Court of India issues landmark verdict on electoral bonds",
        "Prime Minister Modi addresses Parliament during budget session",
        "Election Commission of India announces dates for Lok Sabha polls",
        "India launches nationwide power reform scheme for all states",
        "ISRO successfully launches navigation satellite into orbit"
    ]
    for title in national_cases:
        art = {"title": title, "description": "National affairs across India."}
        cat = categorize_article(art)
        assert cat == "national", f"National classification failed for '{title}': got '{cat}'"

if __name__ == "__main__":
    test_twelve_specified_test_cases()
    test_sports_leakage_prevented()
    test_technology_purity()
    test_business_discipline()
    test_local_vs_national()
    test_global_vs_national()
    print("\nAll category classification unit tests passed successfully!")
