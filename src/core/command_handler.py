import re
from core.logger import get_logger

logger = get_logger("command_handler")

class CommandHandler:
    """
    Natural Language intent router for user commands.
    Translates raw text into structured intents without LLM latency.
    """
    
    def __init__(self):
        self.intents = {
            r"(?i)\b(hi|hello|hey|greetings|morning|evening)\b": "GREETING",
            r"(?i)\b(help|commands|what can you do)\b": "HELP",
            r"(?i)\b(refresh|latest|update|fetch)\b": "REFRESH",
            r"(?i)\b(breaking|urgent|flash)\b": "BREAKING_NEWS",
            r"(?i)\b(summarize|summary|overview)\b": "DAILY_SUMMARY",
            r"(?i)\b(important|top stories|top news)\b": "TOP_STORIES",
            r"(?i)\b(search|find)\s+(.+)\b": "SEARCH",
            r"(?i)\b(show|get|read)?\s*me\s*(some)?\s*(sports|technology|tech|business|national|india|global|world|local)\s*(news)?\b": "FILTER_CATEGORY"
        }
        
        # Category aliases
        self.cat_map = {
            "tech": "technology",
            "india": "national",
            "world": "global"
        }

    def handle(self, user_input: str) -> dict:
        """
        Parse user message -> structured intent
        Returns: {"intent": str, "params": dict}
        """
        user_input = user_input.strip()
        
        for pattern, intent in self.intents.items():
            match = re.search(pattern, user_input)
            if match:
                params = {}
                
                if intent == "SEARCH":
                    # The search query is the 2nd group
                    params["query"] = match.group(2).strip()
                    
                elif intent == "FILTER_CATEGORY":
                    # The category is usually the 3rd group
                    cat = match.group(3).lower()
                    params["category"] = self.cat_map.get(cat, cat)
                    
                return {"intent": intent, "params": params}
                
        # Fallback if no specific intent is found
        return {"intent": "SEARCH", "params": {"query": user_input}}
