from core.command_handler import CommandHandler
from core.logger import get_logger
from db.database import get_news_paginated, get_breaking_news

logger = get_logger("agent_controller")

class AgentController:
    """
    Central Brain: Sense -> Analyze -> Decide -> Act
    """
    
    def __init__(self):
        self.cmd_handler = CommandHandler()
        
    def handle_user_command(self, user_message: str) -> dict:
        """
        Process a chat message from the user and decide how to act.
        """
        # SENSE & ANALYZE (Parse intent)
        parsed = self.cmd_handler.handle(user_message)
        intent = parsed.get("intent")
        params = parsed.get("params", {})
        
        logger.info(f"Agent analyzed intent: {intent} with params: {params}")
        
        # DECIDE & ACT
        if intent == "GREETING":
            return {
                "text": "Hello! I am your Nexus News Agent. How can I help you today? You can ask me to show you breaking news, specific categories like technology, or search for a topic.",
                "articles": [],
                "action": "none"
            }
            
        elif intent == "HELP":
            help_text = (
                "Here are some things you can ask me:\n"
                "• 'Show me tech news'\n"
                "• 'Any breaking news?'\n"
                "• 'Search for elections'\n"
                "• 'Get top stories'\n"
                "• 'Refresh news'"
            )
            return {
                "text": help_text,
                "articles": [],
                "action": "none"
            }
            
        elif intent == "REFRESH":
            return {
                "text": "I'll start fetching the latest news for you right away.",
                "articles": [],
                "action": "refresh"
            }
            
        elif intent == "BREAKING_NEWS":
            articles = get_breaking_news()
            if articles:
                return {
                    "text": f"Here are the latest breaking news stories.",
                    "articles": articles,
                    "action": "show_breaking"
                }
            return {
                "text": "There are no breaking news stories at the moment.",
                "articles": [],
                "action": "none"
            }
            
        elif intent == "FILTER_CATEGORY":
            cat = params.get("category")
            articles, total = get_news_paginated(limit=5, category=cat)
            if articles:
                return {
                    "text": f"Here are the top stories for {cat.capitalize()}.",
                    "articles": articles,
                    "action": "show_category"
                }
            return {
                "text": f"I couldn't find any recent {cat} stories.",
                "articles": [],
                "action": "none"
            }
            
        elif intent == "TOP_STORIES":
            # Just get the highest importance stories
            articles, total = get_news_paginated(limit=5)
            return {
                "text": "Here are the most important stories right now.",
                "articles": articles,
                "action": "show_top"
            }
            
        elif intent == "SEARCH":
            query = params.get("query")
            articles, total = get_news_paginated(limit=5, search=query)
            if articles:
                return {
                    "text": f"Here is what I found for '{query}'.",
                    "articles": articles,
                    "action": "search_results"
                }
            return {
                "text": f"I didn't find any recent news mentioning '{query}'.",
                "articles": [],
                "action": "none"
            }
            
        elif intent == "DAILY_SUMMARY":
            articles, total = get_news_paginated(limit=5)
            return {
                "text": "Here is a quick overview of today's most important news.",
                "articles": articles,
                "action": "show_summary"
            }

        # Fallback
        return {
            "text": "I'm not sure how to handle that. Try asking for 'top stories' or a category like 'technology'.",
            "articles": [],
            "action": "none"
        }

    def generate_for_you(self, page=1, limit=20):
        from db.database import get_all_settings
        settings = get_all_settings()
        prefs = settings.get("preferred_categories", [])
        articles, total = get_news_paginated(page=page, limit=limit)
        
        breaking = [a for a in articles if a.get("is_breaking") == 1]
        
        # Sort out articles by preferences
        cat_counts = {}
        for a in articles:
            c = a.get("category", "general")
            cat_counts[c] = cat_counts.get(c, 0) + 1
            
        greeting = "Good morning 👋\n\nHere's what matters today.\n\n"
        if breaking:
            greeting += f"🔴 Breaking: {len(breaking)} important stories\n"
        for p in prefs:
            if p in cat_counts:
                greeting += f"📌 {p.capitalize()}: {cat_counts[p]} updates\n"
                
        if not settings.get("ai_features", True):
            greeting += "\n(AI Briefing disabled in settings)"
            
        from ai.summarizer import summarize_news_list
        articles = summarize_news_list(articles)
            
        return {
            "greeting": greeting if page == 1 else None,
            "articles": articles,
            "total": total
        }
        
    def generate_briefing(self, page=1, limit=20):
        from db.database import get_all_settings, get_news_paginated
        from fetch.geolocator import get_current_location
        settings = get_all_settings()
        
        # Category preferences: exclude disabled categories from Morning Briefing
        all_cats = ["local", "national", "global", "technology", "business", "sports"]
        exclude_cats = [c for c in all_cats if settings.get(f"cat_{c}") is False]
        
        articles, total = get_news_paginated(page=page, limit=limit, exclude_categories=exclude_cats)
        
        from ai.summarizer import summarize_news_list
        articles = summarize_news_list(articles)
        
        loc = get_current_location()
        city = loc.get("city", "") if isinstance(loc, dict) else ""
        loc_phrase = f" for {city}" if city else ""
        
        ai_enabled = settings.get("ai_features", True) and settings.get("ai_summarization", True)
        
        if not ai_enabled:
            return {
                "greeting": f"Good morning 👋\n\nHere is your daily briefing{loc_phrase} based on your selected categories. (AI synthesis is currently disabled in settings).",
                "articles": articles,
                "total": total
            }
        
        if page == 1 and articles:
            from ai.summarizer import summarize
            titles = [a.get("title") for a in articles[:5]]
            prompt = f"You are a professional news agent. Write a structured, factual morning briefing greeting (2-3 sentences){loc_phrase} summarizing these top stories: " + " | ".join(titles)
            ai_greeting = summarize(prompt)
            greeting = f"Good morning 👋\n\n{ai_greeting}"
        else:
            greeting = None
            
        return {
            "greeting": greeting,
            "articles": articles,
            "total": total
        }
