import os
import json
from dotenv import load_dotenv

# Base Directory: root of the project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if not os.path.exists(os.path.join(BASE_DIR, '.env')):
    # Fallback to parent directory
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

load_dotenv(os.path.join(BASE_DIR, '.env'))

# Paths
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_PATH = os.path.join(BASE_DIR, 'logs', 'app.log')
CONFIG_JSON_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')

# API Keys
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Make sure data and logs directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# Default DB Path (SQLite fallback)
DB_PATH = os.path.join(DATA_DIR, 'news.db')


def get_config():
    """Load configuration from config.json."""
    try:
        if os.path.exists(CONFIG_JSON_PATH):
            with open(CONFIG_JSON_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading config.json: {e}")
    
    return {
        "ai_provider": "groq",
        "default_location": {
            "city": "Vijayawada",
            "state": "Andhra Pradesh",
            "country": "India"
        },
        "preferred_categories": ["local", "national", "global", "sports", "technology", "business"],
        "max_articles_per_category": 5,
        "source_reliability": {
            "high": ["Reuters", "BBC", "The Hindu", "NDTV", "Indian Express", "Economic Times"],
            "medium": ["Times of India", "Hindustan Times", "TechCrunch", "News Minute"],
            "low": []
        },
        "first_run_complete": False
    }

def update_config(key, value):
    """Update a specific key in config.json."""
    config = get_config()
    config[key] = value
    try:
        with open(CONFIG_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config.json: {e}")
        return False

def get_db_url():
    """Get PostgreSQL URL if available, else None."""
    return DATABASE_URL

from config.settings_schema import (
    SETTINGS_SCHEMA,
    CANONICAL_SETTINGS,
    CANONICAL_DEFAULTS,
    SETTINGS_VERSION,
    get_canonical_defaults,
    validate_setting,
    validate_settings,
    validate_all_settings,
    validate_settings_payload,
    is_in_quiet_hours
)
