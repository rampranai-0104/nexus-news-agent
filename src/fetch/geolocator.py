import requests
from config import IPINFO_TOKEN, get_config
from core.logger import get_logger

logger = get_logger("geolocator")

# Cache to avoid calling the API multiple times per session
_location_cache = None

def get_current_location():
    """
    Get current location following strict location priority:
    IF location_auto == false:
        use saved manual location (city, state, country).
    IF location_auto == true:
        use automatic / IP-based location detection.
    """
    global _location_cache
    
    from db.database import get_all_settings
    settings = get_all_settings()
    location_auto = settings.get("location_auto", True)
    
    if not location_auto:
        # Manual location requested
        city = (settings.get("location_city") or "").strip()
        state = (settings.get("location_state") or "").strip()
        country = (settings.get("location_country") or "").strip() or "India"
        
        if not city:
            logger.warning("Manual location selected but city is missing")
            return {
                "city": "",
                "state": state,
                "country": country,
                "is_manual": True,
                "valid": False,
                "error": "City is required for manual location"
            }
            
        return {
            "city": city,
            "state": state,
            "country": country,
            "is_manual": True,
            "valid": True
        }
        
    # Automatic location requested
    if _location_cache:
        return _location_cache
        
    config = get_config()
    default_loc = config.get("default_location", {
        "city": "Vijayawada",
        "state": "Andhra Pradesh",
        "country": "India"
    })
    
    if not IPINFO_TOKEN:
        logger.info("No IPINFO_TOKEN found. Using default location.")
        _location_cache = {**default_loc, "is_manual": False, "valid": True}
        return _location_cache
        
    try:
        response = requests.get(f"https://ipinfo.io/json?token={IPINFO_TOKEN}", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        city = data.get("city", default_loc["city"])
        region = data.get("region", default_loc["state"])
        country = data.get("country", default_loc["country"])
        
        _location_cache = {
            "city": city,
            "state": region,
            "country": country,
            "is_manual": False,
            "valid": True
        }
        return _location_cache
    except Exception as e:
        logger.warning(f"Failed to detect location: {e}. Using default.")
        _location_cache = {**default_loc, "is_manual": False, "valid": True}
        return _location_cache

def clear_location_cache():
    global _location_cache
    _location_cache = None

get_user_location = get_current_location
invalidate_location_cache = clear_location_cache
