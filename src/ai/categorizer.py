import os
import re
import math
from typing import Dict, Tuple, Any, List
from groq import Groq
from openai import OpenAI
from config import GROQ_API_KEY, OPENAI_API_KEY, get_config
from core.logger import get_logger

logger = get_logger("categorizer")

# Canonical supported categories
VALID_CATEGORIES = ["local", "national", "global", "technology", "business", "sports"]

# Legacy / alias category mapping
CATEGORY_ALIASES = {
    "world": "global",
    "nation": "national",
    "international": "global",
    "tech": "technology",
    "sport": "sports",
    "biz": "business",
    "finance": "business",
    "economy": "business",
    "general": "national",
    "all": "national",
    "news": "national"
}

# ---------------------------------------------------------------------------
# Topic and Geographic Patterns (Weighted)
# ---------------------------------------------------------------------------

# SPORTS patterns
SPORTS_PATTERNS = [
    # Weight 3.5: Definitive multi-word events & leagues
    (3.5, [
        r"\bworld cup\b", r"\bcricket world cup\b", r"\bicc world cup\b", r"\bfifa world cup\b",
        r"\bipl 202\d\b", r"\bindian premier league\b", r"\bpremier league\b", r"\bchampions league\b",
        r"\bla liga\b", r"\bserie a\b", r"\bbundesliga\b", r"\btest match\b", r"\bone day international\b",
        r"\bodi series\b", r"\bt20 series\b", r"\bt20 world cup\b", r"\bgrand slam\b", r"\bwimbledon\b",
        r"\baustralian open\b", r"\bfrench open\b", r"\bus open tennis\b", r"\bformula 1\b", r"\bformula one\b",
        r"\bf1 grand prix\b", r"\bolympic games\b", r"\bolympics\b", r"\bpro kabaddi\b", r"\buefa\b"
    ]),
    # Weight 2.5: Core sports, entities, figures
    (2.5, [
        r"\bcricket\b", r"\bcricketer\b", r"\bcricketers\b", r"\bbcci\b", r"\bicc\b", r"\bipl\b",
        r"\bbatsman\b", r"\bbatsmen\b", r"\bbatting\b", r"\bbowler\b", r"\bbowlers\b", r"\bbowling\b",
        r"\bwickets?\b", r"\binnings\b", r"\bodi\b", r"\bt20\b", r"\bfifa\b", r"\bbadminton\b",
        r"\bfootball\b", r"\bfootballer\b", r"\bsoccer\b", r"\bhockey\b", r"\bathletics\b", r"\bathlete\b",
        r"\bwimbledon\b", r"\btennis\b", r"\bmarathon\b", r"\bboxer\b", r"\bboxers\b", r"\bboxings?\b",
        r"\bwrestler\b", r"\bwrestlers\b", r"\bwrestlings?\b", r"\bgolf\b", r"\bgolfer\b", r"\bbasketball\b",
        r"\bnba\b", r"\bnfl\b", r"\btouchdown\b", r"\bquarterback\b", r"\bvirat kohli\b", r"\brohit sharma\b",
        r"\bms dhoni\b", r"\bsachin tendulkar\b", r"\bjasprit bumrah\b", r"\bhardik pandya\b", r"\bkl rahul\b",
        r"\bshubman gill\b", r"\brishabh pant\b", r"\bjosh tongue\b", r"\bollie robinson\b", r"\bben stokes\b",
        r"\bpat cummins\b", r"\btravis head\b", r"\blionel messi\b", r"\bcristiano ronaldo\b", r"\bmbappe\b",
        r"\bhaaland\b", r"\bdjokovic\b", r"\balcaraz\b", r"\bnadal\b", r"\bsinner\b", r"\bfederer\b",
        r"\bpv sindhu\b", r"\bneeraj chopra\b", r"\bbabar azam\b", r"\bravindra jadeja\b"
    ]),
    # Weight 1.8: Tournament, match and competition terms
    (1.8, [
        r"\bmatch(?:es)?\b", r"\btournaments?\b", r"\bchampionships?\b", r"\bleagues?\b",
        r"\bstadium\b", r"\bderby\b", r"\bplaying xi\b", r"\bsquad\b", r"\broster\b",
        r"\bhead coach\b", r"\bteam captain\b", r"\bquarterfinal\b", r"\bsemifinal\b",
        r"\bplayoffs?\b", r"\bhalf-century\b", r"\bcentury\b", r"\bhat-trick\b",
        r"\bclean sheet\b", r"\bpenalty shootout\b", r"\bball cut in half\b", r"\bdrop(?:ped)? the ball\b"
    ]),
    # Weight 1.2: Match outcome verbs in sports context
    (1.2, [
        r"\bscored?\b", r"\bclinch(?:es|ed)? title\b", r"\blost to\b", r"\bwon by\b",
        r"\bthrashing\b", r"\bbeat by\b", r"\bdefeat(?:ed|s)?\b", r"\bvictory\b"
    ])
]

# TECHNOLOGY patterns
TECH_PATTERNS = [
    # Weight 3.5: Definitive tech domain terms & modern AI
    (3.5, [
        r"\bartificial intelligence\b", r"\bgenerative ai\b", r"\blarge language models?\b",
        r"\bdeep learning\b", r"\bmachine learning\b", r"\bneural networks?\b", r"\bfoundation models?\b",
        r"\bcloud computing\b", r"\bquantum computing\b", r"\boperating systems?\b",
        r"\bdata centers?\b", r"\bcybersecurity\b", r"\bcyber security\b", r"\bmalware attack\b",
        r"\bransomware\b", r"\bzero-day(?: vulnerability)?\b", r"\bautonomous driving\b",
        r"\bautonomous vehicles?\b", r"\bhumanoid robots?\b", r"\bsemiconductor(?:s)?\b",
        r"\bmicrochips?\b", r"\bapple vision pro\b", r"\bmeta quest\b", r"\bfoldable smartphones?\b",
        r"\bon-device computing\b", r"\bcyberattacks?\b", r"\bdata breach(?:es)?\b"
    ]),
    # Weight 2.5: Tech products, hardware, chips, platforms
    (2.5, [
        r"\bai models?\b", r"\bai chatbot\b", r"\bchatgpt\b", r"\bopenai\b", r"\banthropic\b",
        r"\bdeepmind\b", r"\bclaude(?: 3)?\b", r"\bgpt-4\b", r"\bgemini pro\b", r"\bcopilot\b",
        r"\bllms?\b", r"\bchipmakers?\b", r"\bnvidia\b", r"\btsmc\b", r"\bintel\b", r"\bamd\b",
        r"\bqualcomm\b", r"\bsnapdragon\b", r"\bgpus?\b", r"\bcpus?\b", r"\bprocessors?\b",
        r"\bsoftwares?\b", r"\bcodebases?\b", r"\bapis?\b", r"\bsdks?\b", r"\bfirmwares?\b",
        r"\bkernels?\b", r"\balgorithms?\b", r"\bsupercomputers?\b", r"\brobotics?\b",
        r"\brobotaxis?\b", r"\bwaymo\b", r"\bsmartphones?\b", r"\biphones?\b", r"\bpixels?\b",
        r"\bgalaxy s2\d\b", r"\bgadgets?\b", r"\bsmartwatch(?:es)?\b", r"\bwearables?\b",
        r"\bhackers?\b", r"\bpatch updates?\b", r"\bsoftwares? updates?\b", r"\bios 1\d\b",
        r"\bandroid 1\d\b", r"\bwindows 11\b", r"\blinux\b", r"\bmacos\b", r"\bgit(?:hub)?\b",
        r"\bopen-source\b"
    ]),
    # Weight 1.8: Tech product events & announcements
    (1.8, [
        r"\btech launch(?:es)?\b", r"\bunveils? new phone\b", r"\bunveils? new chip\b",
        r"\bunveils? new processor\b", r"\bunveils? new iphone\b", r"\bnew feature update\b",
        r"\bmobile apps?\b", r"\bsoftware platform\b", r"\btech specs\b"
    ]),
    # Weight 0.3: Weak tech words (never sufficient alone)
    (0.3, [
        r"\bapps?\b", r"\bdigital\b", r"\bonline\b", r"\bwebsites?\b", r"\bplatforms?\b"
    ])
]

# BUSINESS patterns
BIZ_PATTERNS = [
    # Weight 3.5: Definitive corporate finance, earnings, macro markets
    (3.5, [
        r"\bquarterly results\b", r"\bquarterly earnings\b", r"\bquarterly profit\b", r"\bquarterly revenue\b",
        r"\bnet profit\b", r"\boperating profit\b", r"\bebitda\b", r"\brevenue grew\b", r"\brevenue surged\b",
        r"\brevenue rose\b", r"\brevenue fell\b", r"\bprofit surged\b", r"\bprofit fell\b", r"\bloss widened\b",
        r"\bstock markets?\b", r"\bshares fell\b", r"\bshares surged\b", r"\bshares rose\b", r"\bshares plunged\b",
        r"\binitial public offering\b", r"\blisting on bse\b", r"\blisting on nse\b", r"\bwall street\b",
        r"\bdow jones\b", r"\bs&p 500\b", r"\breserve bank of india\b", r"\bfederal reserve\b",
        r"\bmonetary policy committee\b", r"\binterest rate cut\b", r"\binterest rate hike\b", r"\bbasis points\b",
        r"\brepo rate\b", r"\binflation rate\b", r"\bconsumer price index\b", r"\bwholesale price index\b",
        r"\bgdp growth\b", r"\bfiscal deficit\b", r"\btrade deficit\b", r"\bventure capital\b",
        r"\bprivate equity\b", r"\bfunding round\b", r"\bseries [a-e] funding\b", r"\bseed funding\b",
        r"\bmergers? and acquisitions?\b", r"\bantitrust investigation\b", r"\bmarket capitalization\b"
    ]),
    # Weight 2.5: Financial metrics, markets, corporate actions
    (2.5, [
        r"\bearnings?\b", r"\brevenues?\b", r"\bnet income\b", r"\bsensex\b", r"\bnifty\b", r"\bnasdaq\b",
        r"\bipos?\b", r"\bshareholders?\b", r"\bdividends?\b", r"\bstocks?\b", r"\bequities\b",
        r"\binflation\b", r"\brecession\b", r"\bgdp\b", r"\brbi\b", r"\bbse\b", r"\bnse\b", r"\bsebi\b",
        r"\btariffs?\b", r"\btreasury\b", r"\bbonds?\b", r"\byields?\b", r"\bforex\b", r"\bcryptocurrency\b",
        r"\bbitcoin\b", r"\bethereum\b", r"\brupee depreciat\b", r"\bdollar index\b", r"\binvestors?\b",
        r"\bvaluations?\b", r"\bacquisitions?\b", r"\bmergers?\b", r"\bbankruptcy\b", r"\binsolvency\b",
        r"\bdebt restructuring\b", r"\blending rate\b", r"\bcorporate tax\b", r"\bfiscal year\b"
    ]),
    # Weight 1.8: General commerce & trade
    (1.8, [
        r"\bcommercial\b", r"\bexports?\b", r"\bimports?\b", r"\bcommerce\b", r"\bretail sales\b",
        r"\bconglomerates?\b", r"\bconsortium\b", r"\bsubsidiary\b", r"\bquarterly\b"
    ])
]

# LOCAL patterns (Cities, Indian States, civic authorities, local events)
LOCAL_PATTERNS = [
    # Weight 3.5: Civic bodies, regional police/agencies, local utility infrastructure
    (3.5, [
        r"\bbbmp\b", r"\bbescom\b", r"\bbda\b", r"\bbmtc\b", r"\bbwssb\b", r"\bghmc\b", r"\bhmda\b",
        r"\btsche\b", r"\bapsrtc\b", r"\btsrtc\b", r"\btsspdcl\b", r"\btssouthernpower\b", r"\bbmc\b",
        r"\bmcd\b", r"\blokayukta\b", r"\bhigh court of karnataka\b", r"\bkarnataka high court\b",
        r"\btelangana high court\b", r"\bandhra pradesh high court\b", r"\bbombay high court\b",
        r"\bmadras high court\b", r"\bdelhi high court\b", r"\bkpsc\b", r"\bappsc\b", r"\btspsc\b",
        r"\bvidhana soudha\b", r"\b11 kv line\b", r"\bbescom workers?\b", r"\bpower shock\b",
        r"\bmunicipal corporation\b", r"\bcorporator\b", r"\bward councillor\b", r"\btraffic police\b",
        r"\bpolice station limits\b"
    ]),
    # Weight 2.8: Specific Indian cities / districts
    (2.8, [
        r"\bbengaluru\b", r"\bbangalore\b", r"\bhyderabad\b", r"\bvisakhapatnam\b", r"\bvizag\b",
        r"\bvijayawada\b", r"\bamaravati\b", r"\bguntur\b", r"\btirupati\b", r"\bkurnool\b",
        r"\bwarangal\b", r"\bsecunderabad\b", r"\bchennai\b", r"\bmumbai\b", r"\bpune\b",
        r"\bkolkata\b", r"\bahmedabad\b", r"\bmysuru\b", r"\bmysore\b", r"\bhubballi\b",
        r"\bdharwad\b", r"\bmangaluru\b", r"\bmangalore\b", r"\bbelagavi\b", r"\bkochi\b",
        r"\bthiruvananthapuram\b", r"\bcoimbatore\b", r"\bmadurai\b", r"\bnoida\b", r"\bgurugram\b",
        r"\bgurgaon\b", r"\bthane\b", r"\bnavi mumbai\b", r"\bchandigarh\b", r"\blucknow\b",
        r"\bkanpur\b", r"\bjaipur\b", r"\bpatna\b", r"\bbhopal\b", r"\bindore\b", r"\bnagpur\b",
        r"\bvadodara\b", r"\bsurat\b"
    ]),
    # Weight 2.0: Indian states and regional context
    (2.0, [
        r"\bkarnataka\b", r"\btelangana\b", r"\bandhra pradesh\b", r"\bandhra\b", r"\btamil nadu\b",
        r"\bkerala\b", r"\bmaharashtra\b", r"\buttar pradesh\b", r"\bmadhya pradesh\b", r"\brajasthan\b",
        r"\bpunjab\b", r"\bharyana\b", r"\bbihar\b", r"\bwest bengal\b", r"\bodisha\b", r"\bassam\b"
    ]),
    # Weight 1.5: Local community and civic events
    (1.5, [
        r"\bpotholes?\b", r"\bwater supply\b", r"\bpower outage\b", r"\bcity traffic\b",
        r"\bflyover construction\b", r"\bmetro phase\b", r"\bcivic body\b", r"\blocal police\b"
    ])
]

# NATIONAL patterns (India-wide governance, policies, central institutions)
NATIONAL_PATTERNS = [
    # Weight 3.5: Central government institutions, national leaders, national policies
    (3.5, [
        r"\bprime minister modi\b", r"\bpm modi\b", r"\bnarendra modi\b", r"\bcentral government\b",
        r"\bunion government\b", r"\bunion cabinet\b", r"\bunion minister\b", r"\blok sabha\b",
        r"\brajya sabha\b", r"\bparliament of india\b", r"\bsupreme court of india\b",
        r"\bchief justice of india\b", r"\bcji\b", r"\bpresident murmu\b", r"\bdroupadi murmu\b",
        r"\belection commission of india\b", r"\belection commission\b", r"\bgeneral elections?\b",
        r"\bisro\b", r"\bdrdo\b", r"\bindian army\b", r"\bindian air force\b", r"\bindian navy\b",
        r"\benforcement directorate\b", r"\bcentral bureau of investigation\b", r"\bcbi\b",
        r"\bnational investigation agency\b", r"\bnia\b", r"\bnational education policy\b",
        r"\bunion budget\b", r"\bnationwide reforms?\b", r"\bnationwide education reforms?\b",
        r"\bnationwide\b", r"\bacross india\b", r"\bacross the country\b"
    ]),
    # Weight 2.5: National political entities & central ministries
    (2.5, [
        r"\bindia\b", r"\bindian\b", r"\bbharat\b", r"\bparliament\b", r"\bsupreme court\b",
        r"\bbjp\b", r"\bcongress party\b", r"\baam aadmi party\b", r"\bnda\b", r"\bindia bloc\b",
        r"\bhome ministry\b", r"\bdefence ministry\b", r"\bministry of external affairs\b",
        r"\bmea\b", r"\bs jaishankar\b", r"\bnirmala sitharaman\b", r"\bpan-india\b",
        r"\bconstitution of india\b"
    ]),
    # Weight 1.5: National affairs context
    (1.5, [
        r"\bnational security\b", r"\blaw commission\b", r"\bcentral scheme\b", r"\binterstate\b"
    ])
]

# GLOBAL patterns (International affairs, foreign nations, geopolitics)
GLOBAL_PATTERNS = [
    # Weight 3.5: Major foreign superpowers, world leaders, international bodies
    (3.5, [
        r"\bunited states\b", r"\bwhite house\b", r"\bjoe biden\b", r"\bdonald trump\b",
        r"\bkamala harris\b", r"\bpentagon\b", r"\bcapitol hill\b", r"\bunited kingdom\b",
        r"\bdowning street\b", r"\bkeir starmer\b", r"\brishi sunak\b", r"\bvladimir putin\b",
        r"\bkremlin\b", r"\bvolodymyr zelenskyy\b", r"\bzelenskyy\b", r"\bkyiv\b",
        r"\bbeijing\b", r"\bxi jinping\b", r"\btaiwan strait\b", r"\bbenjamin netanyahu\b",
        r"\bnetanyahu\b", r"\btel aviv\b", r"\bgaza strip\b", r"\bhamas\b", r"\bhezbollah\b",
        r"\bisrael-gaza(?: conflict)?\b", r"\bunited nations\b", r"\bun security council\b",
        r"\bunsc\b", r"\bnato\b", r"\beuropean union\b", r"\bg7 summit\b", r"\bg20 summit\b",
        r"\binternational trade agreement\b", r"\binternational court of justice\b", r"\bicj\b",
        r"\bworld health organization\b", r"\binternational monetary fund\b", r"\bworld trade organization\b"
    ]),
    # Weight 2.5: Foreign nations and regional conflicts
    (2.5, [
        r"\bu\.?s\.?\b", r"\busa\b", r"\buk\b", r"\brussia\b", r"\bukraine\b", r"\bchina\b",
        r"\btaiwan\b", r"\bjapan\b", r"\bsouth korea\b", r"\bnorth korea\b", r"\bkim jong un\b",
        r"\biran\b", r"\btehran\b", r"\blebanon\b", r"\bbeirut\b", r"\bsyria\b", r"\byemen\b",
        r"\bhouthi\b", r"\bsaudi arabia\b", r"\buae\b", r"\bqatar\b", r"\bpakistan\b",
        r"\bislamabad\b", r"\bbangladesh\b", r"\bdhaka\b", r"\bcanada\b", r"\bjustin trudeau\b",
        r"\baustralia\b", r"\bgermany\b", r"\bfrance\b", r"\bmacron\b", r"\beu\b"
    ]),
    # Weight 1.8: Global diplomacy and conflict terms
    (1.8, [
        r"\bbilateral agreement\b", r"\bforeign policy\b", r"\bgeopolitics\b", r"\benvoy\b",
        r"\bambassadors?\b", r"\bsanctions on\b", r"\bmissile tests?\b", r"\bairstrikes?\b",
        r"\bceasefire(?: talks)?\b", r"\bpeace summit\b", r"\btreaty\b", r"\binternational community\b",
        r"\bglobal economy\b"
    ])
]

# Compile pattern tables
CATEGORY_RULES = {
    "sports": [(w, [re.compile(p, re.IGNORECASE) for p in patterns]) for w, patterns in SPORTS_PATTERNS],
    "technology": [(w, [re.compile(p, re.IGNORECASE) for p in patterns]) for w, patterns in TECH_PATTERNS],
    "business": [(w, [re.compile(p, re.IGNORECASE) for p in patterns]) for w, patterns in BIZ_PATTERNS],
    "local": [(w, [re.compile(p, re.IGNORECASE) for p in patterns]) for w, patterns in LOCAL_PATTERNS],
    "national": [(w, [re.compile(p, re.IGNORECASE) for p in patterns]) for w, patterns in NATIONAL_PATTERNS],
    "global": [(w, [re.compile(p, re.IGNORECASE) for p in patterns]) for w, patterns in GLOBAL_PATTERNS]
}

# Backward compatibility KEYWORDS dictionary
KEYWORDS = {
    "sports": ["cricket", "football", "tennis", "ipl", "match", "wicket", "tournament", "championship"],
    "technology": ["ai", "software", "chip", "semiconductor", "cybersecurity", "smartphone", "robotics"],
    "business": ["earnings", "revenue", "profit", "stocks", "market", "sensex", "nifty", "inflation", "gdp"],
    "local": ["bengaluru", "hyderabad", "visakhapatnam", "vijayawada", "bescom", "bbmp", "ghmc"],
    "national": ["india", "modi", "parliament", "supreme court", "lok sabha", "isro", "bjp", "congress"],
    "global": ["us", "uk", "china", "russia", "ukraine", "gaza", "israel", "biden", "un", "nato"]
}

_cat_cache = {}


def score_text_for_category(text: str, category: str) -> float:
    """Calculate weighted match score for a given category on a text block."""
    if not text:
        return 0.0
        
    rules = CATEGORY_RULES.get(category, [])
    total_score = 0.0
    matched_patterns = 0
    
    for weight, compiled_list in rules:
        for pattern in compiled_list:
            matches = len(pattern.findall(text))
            if matches > 0:
                # Diminishing returns for repeated matches within the same field
                match_mult = 1.0 + (math.log(matches) * 0.4)
                total_score += weight * match_mult
                matched_patterns += 1
                
    return total_score


def classify_text_detailed(
    title: str = "",
    description: str = "",
    content: str = "",
    source_category: str = "",
    source_name: str = ""
) -> Tuple[str, float, Dict[str, float], str]:
    """
    Two-stage hierarchical, multi-signal classification.
    
    Weights:
      Title: 50%
      Description: 30%
      Content (first 1500 chars): 20%
      Source / Feed Category: weak prior bonus (+0.08 max)
    
    Returns:
      (category, confidence, scores_dict, reason)
    """
    title = (title or "").strip()
    description = (description or "").strip()
    content_snippet = (content or "")[:1500].strip()
    
    raw_scores: Dict[str, float] = {c: 0.0 for c in VALID_CATEGORIES}
    
    # 1. Multi-field scoring with strict weighting: 50% title, 30% desc, 20% content
    for cat in VALID_CATEGORIES:
        s_title = score_text_for_category(title, cat)
        s_desc = score_text_for_category(description, cat)
        s_content = score_text_for_category(content_snippet, cat)
        
        composite = (0.50 * s_title) + (0.30 * s_desc) + (0.20 * s_content)
        raw_scores[cat] = composite

    # 2. Source / Feed prior as weak supporting signal (max 0.08, NEVER overrides clear article content)
    norm_source_cat = CATEGORY_ALIASES.get(source_category.lower().strip(), source_category.lower().strip())
    if norm_source_cat in raw_scores:
        # Prior is kept small so a single title keyword easily overrides it
        raw_scores[norm_source_cat] += 0.08

    # 3. Apply Cross-Category Negative Signals / Damping
    # 3a. Sports leakage prevention: If sports has strong signal, heavily damp technology and business
    sports_score = raw_scores["sports"]
    if sports_score > 0.4:
        raw_scores["technology"] = max(0.0, raw_scores["technology"] - (0.85 * sports_score))
        raw_scores["business"] = max(0.0, raw_scores["business"] - (0.50 * sports_score))
        
    # 3b. Technology purity: If technology is clearly primary, damp sports
    tech_score = raw_scores["technology"]
    if tech_score > 0.6 and tech_score > sports_score:
        raw_scores["sports"] = max(0.0, raw_scores["sports"] - (0.60 * tech_score))
        
    # 3c. Business vs Technology nuance:
    # If both score high, examine headline verbs/nouns:
    # Financial results / earnings / stocks -> Business.
    # Product launches / models / processors / hardware -> Technology.
    biz_score = raw_scores["business"]
    if tech_score > 0.4 and biz_score > 0.4:
        t_lower = title.lower()
        has_biz_title = any(w in t_lower for w in ["earnings", "revenue", "profit", "stocks", "shares", "valuation", "quarterly", "ipo"])
        has_tech_title = any(w in t_lower for w in ["unveil", "launch", "processor", "chip", "model", "phone", "update", "feature"])
        if has_biz_title and not has_tech_title:
            raw_scores["technology"] *= 0.4
        elif has_tech_title and not has_biz_title:
            raw_scores["business"] *= 0.4

    # 3d. Local vs National nuance:
    # If a specific city or local authority is in title or has strong civic presence, Local takes priority over National
    local_score = raw_scores["local"]
    national_score = raw_scores["national"]
    if local_score > 0.5:
        # If city/civic body in headline, prevent broad "India" mention from turning it into National
        raw_scores["national"] = max(0.0, national_score - (0.50 * local_score))
        
    # 3e. Global vs National nuance:
    # International treaties or foreign conflicts (US, China, Russia, Ukraine, Gaza) should not become National
    global_score = raw_scores["global"]
    if global_score > 0.6 and global_score > national_score:
        raw_scores["national"] = max(0.0, national_score - (0.40 * global_score))

    # ---------------------------------------------------------------------------
    # 4. Two-Stage Hierarchical Classification
    # ---------------------------------------------------------------------------
    # STAGE 1 — Specialized topics (Sports, Technology, Business)
    # If an article is about sports, technology, or business, it should be categorized as such
    # regardless of geography (e.g. India cricket -> Sports, India tech -> Tech, India budget -> Business)
    specialized_scores = {
        "sports": raw_scores["sports"],
        "technology": raw_scores["technology"],
        "business": raw_scores["business"]
    }
    top_specialized = max(specialized_scores, key=specialized_scores.get)
    top_spec_val = specialized_scores[top_specialized]
    
    # STAGE 2 — Geographic categories (Local, National, Global)
    geo_scores = {
        "local": raw_scores["local"],
        "national": raw_scores["national"],
        "global": raw_scores["global"]
    }
    top_geo = max(geo_scores, key=geo_scores.get)
    top_geo_val = geo_scores[top_geo]

    # Decision logic:
    # Specialized category wins if it has a confident primary signal (>= 0.35)
    # AND is either greater than or competitive with the geographic signal
    if top_spec_val >= 0.35 and (top_spec_val >= (top_geo_val * 0.75)):
        best_category = top_specialized
        chosen_score = top_spec_val
        reason = f"Specialized topic '{top_specialized}' dominates with score {top_spec_val:.2f}"
    elif top_geo_val >= 0.25:
        best_category = top_geo
        chosen_score = top_geo_val
        reason = f"Geographic category '{top_geo}' dominates with score {top_geo_val:.2f}"
    elif top_spec_val > 0.0 or top_geo_val > 0.0:
        # Lower confidence match
        if top_spec_val >= top_geo_val:
            best_category = top_specialized
            chosen_score = top_spec_val
            reason = f"Specialized topic '{top_specialized}' chosen on marginal score {top_spec_val:.2f}"
        else:
            best_category = top_geo
            chosen_score = top_geo_val
            reason = f"Geographic category '{top_geo}' chosen on marginal score {top_geo_val:.2f}"
    else:
        # True zero score on all categories -> safe broader fallback
        # Check for India or foreign hints in raw text
        full_text = f"{title} {description}".lower()
        if any(w in full_text for w in ["india", "delhi", "centre", "govt", "state", "minister"]):
            best_category = "national"
            chosen_score = 0.1
            reason = "Zero keyword score; defaulted to national on India context"
        elif any(w in full_text for w in ["us", "world", "international", "global", "foreign", "un"]):
            best_category = "global"
            chosen_score = 0.1
            reason = "Zero keyword score; defaulted to global on international context"
        else:
            best_category = "national"
            chosen_score = 0.1
            reason = "Ambiguous zero score; defaulted to broader national"

    # Compute normalized confidence (0.0 to 1.0)
    total_all = sum(raw_scores.values())
    if total_all > 0:
        confidence = min(1.0, max(0.20, chosen_score / total_all))
    else:
        confidence = 0.20
        
    return best_category, confidence, raw_scores, reason


def keyword_match(text: str) -> str:
    """Legacy keyword match wrapper for backward compatibility."""
    cat, _, _, _ = classify_text_detailed(title=text)
    return cat


def llm_categorize(text: str) -> str:
    """Fallback to LLM if rule confidence is genuinely low and AI is enabled."""
    if text in _cat_cache:
        return _cat_cache[text]
        
    config = get_config()
    provider = config.get("ai_provider", "groq")
    
    prompt = (
        "Categorize the following news headline into exactly ONE of these categories: "
        "technology, sports, business, national, global, local. Reply with ONLY the category word.\n\n"
        f"Headline: {text}"
    )
    
    cat = "national"
    try:
        if provider == "groq" and GROQ_API_KEY:
            client = Groq(api_key=GROQ_API_KEY)
            models_to_try = [
                os.environ.get("AI_MODEL", "llama-3.3-70b-versatile"),
                "llama3-8b-8192",
                "llama-3.1-8b-instant"
            ]
            for model_name in models_to_try:
                try:
                    res = client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model=model_name,
                        temperature=0.1,
                        max_tokens=10
                    )
                    cat = res.choices[0].message.content.strip().lower()
                    break
                except Exception:
                    continue
                    
        elif OPENAI_API_KEY:
            client = OpenAI(api_key=OPENAI_API_KEY)
            res = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=10
            )
            cat = res.choices[0].message.content.strip().lower()
    except Exception as e:
        logger.warning(f"LLM categorizer fallback error: {e}")
        cat = "national"
        
    if cat not in VALID_CATEGORIES:
        for vc in VALID_CATEGORIES:
            if vc in cat:
                cat = vc
                break
        else:
            cat = "national"
            
    _cat_cache[text] = cat
    return cat


def categorize_article(article: dict) -> str:
    """
    Authoritative article categorizer.
    Analyzes title (50%), description (30%), content (20%), and source hints.
    Assigns one of the 6 canonical categories: local, national, global, technology, business, sports.
    """
    title = article.get("title", "") or ""
    description = article.get("description", "") or ""
    content = article.get("content", "") or ""
    source_cat = article.get("category", "") or article.get("feed_category", "") or ""
    source_name = article.get("source", "") or ""
    
    cat, confidence, scores, reason = classify_text_detailed(
        title=title,
        description=description,
        content=content,
        source_category=source_cat,
        source_name=source_name
    )
    
    config = get_config()
    # Optional LLM fallback only if rule confidence is critically low (< 0.25)
    if confidence < 0.25 and config.get("ai_categorization", True):
        llm_cat = llm_categorize(title)
        if llm_cat in VALID_CATEGORIES:
            cat = llm_cat
            confidence = 0.50
            reason = "LLM fallback chosen for low-confidence article"
            
    article["category"] = cat
    article["category_confidence"] = round(confidence, 3)
    
    # Log suspicious or interesting transitions when source category diverges
    if source_cat and source_cat.lower() in VALID_CATEGORIES and source_cat.lower() != cat:
        logger.info(
            f"CATEGORY CORRECTION | Title: '{title[:60]}' | "
            f"Old Feed Category: {source_cat} -> New Category: {cat} (conf={confidence:.2f}) | {reason}"
        )
        
    return cat


def categorize_news_list(news_list: List[dict]) -> List[dict]:
    """Categorize a list of articles in place and return the list."""
    stats = {cat: 0 for cat in VALID_CATEGORIES}
    
    for a in news_list:
        cat = categorize_article(a)
        stats[cat] = stats.get(cat, 0) + 1
        
    logger.info(
        f"Categorized {len(news_list)} articles: "
        f"local={stats['local']}, national={stats['national']}, global={stats['global']}, "
        f"tech={stats['technology']}, biz={stats['business']}, sports={stats['sports']}"
    )
    return news_list