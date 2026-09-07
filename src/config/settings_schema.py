import re
from datetime import datetime, time
from typing import Any, Dict, Optional, Tuple

SETTINGS_VERSION = 1

SETTINGS_SCHEMA: Dict[str, Dict[str, Any]] = {
    "settings_version": {
        "type": int,
        "default": SETTINGS_VERSION,
        "min": 1,
        "max": 100
    },
    # Personalization
    "location_city": {
        "type": str,
        "default": "",
        "max_length": 100
    },
    "location_state": {
        "type": str,
        "default": "",
        "max_length": 100
    },
    "location_country": {
        "type": str,
        "default": "India",
        "max_length": 100
    },
    "location_auto": {
        "type": bool,
        "default": True
    },
    "personalized_feed": {
        "type": bool,
        "default": True
    },
    # News
    "cat_local": {
        "type": bool,
        "default": True
    },
    "cat_national": {
        "type": bool,
        "default": True
    },
    "cat_global": {
        "type": bool,
        "default": True
    },
    "cat_technology": {
        "type": bool,
        "default": True
    },
    "cat_business": {
        "type": bool,
        "default": True
    },
    "cat_sports": {
        "type": bool,
        "default": True
    },
    "article_limit": {
        "type": int,
        "default": 20,
        "min": 5,
        "max": 50
    },
    "show_images": {
        "type": bool,
        "default": True
    },
    "show_read_articles": {
        "type": bool,
        "default": True
    },
    # AI
    "ai_features": {
        "type": bool,
        "default": True
    },
    "ai_summarization": {
        "type": bool,
        "default": True
    },
    "summary_length": {
        "type": str,
        "default": "medium",
        "allowed": ["short", "medium", "detailed"]
    },
    # Notifications
    "notifications_enabled": {
        "type": bool,
        "default": False
    },
    "notify_breaking": {
        "type": bool,
        "default": True
    },
    "notify_daily": {
        "type": bool,
        "default": True
    },
    "quiet_hours_enabled": {
        "type": bool,
        "default": False
    },
    "quiet_hours_start": {
        "type": str,
        "default": "22:00",
        "regex": r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    },
    "quiet_hours_end": {
        "type": str,
        "default": "08:00",
        "regex": r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    },
    # Appearance
    "theme": {
        "type": str,
        "default": "dark",
        "allowed": ["dark", "light", "system"]
    },
    "font_size": {
        "type": str,
        "default": "medium",
        "allowed": ["small", "medium", "large", "xl"]
    },
    "ui_density": {
        "type": str,
        "default": "comfortable",
        "allowed": ["compact", "comfortable"]
    },
    "animations": {
        "type": bool,
        "default": True
    }
}

CANONICAL_SETTINGS = SETTINGS_SCHEMA

def get_canonical_defaults() -> Dict[str, Any]:
    """Return dictionary of canonical default settings."""
    return {k: meta["default"] for k, meta in SETTINGS_SCHEMA.items()}

CANONICAL_DEFAULTS = get_canonical_defaults()

def validate_setting(key: str, value: Any) -> Tuple[bool, Any, Optional[str]]:
    """
    Validate a single setting against the schema.
    Returns: (is_valid, parsed_value, error_message)
    """
    if key not in SETTINGS_SCHEMA:
        return False, None, f"Unknown setting key: '{key}'"

    meta = SETTINGS_SCHEMA[key]
    target_type = meta["type"]

    # Handle boolean conversion
    if target_type == bool:
        if isinstance(value, bool):
            parsed = value
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                parsed = True
            elif lowered in ("false", "0", "no", "off"):
                parsed = False
            else:
                return False, None, f"Setting '{key}' must be boolean (true/false), got '{value}'"
        elif isinstance(value, (int, float)):
            parsed = bool(value)
        else:
            return False, None, f"Setting '{key}' must be boolean, got type {type(value).__name__}"
        return True, parsed, None

    # Handle integer conversion
    if target_type == int:
        try:
            parsed = int(value)
        except (ValueError, TypeError):
            return False, None, f"Setting '{key}' must be an integer, got '{value}'"

        if "min" in meta and parsed < meta["min"]:
            return False, None, f"Setting '{key}' cannot be less than {meta['min']}, got {parsed}"
        if "max" in meta and parsed > meta["max"]:
            return False, None, f"Setting '{key}' cannot be greater than {meta['max']}, got {parsed}"
        return True, parsed, None

    # Handle string validation
    if target_type == str:
        if value is None:
            parsed = ""
        else:
            parsed = str(value).strip()

        if "max_length" in meta and len(parsed) > meta["max_length"]:
            return False, None, f"Setting '{key}' exceeds maximum length of {meta['max_length']} characters"

        if "allowed" in meta:
            allowed = meta["allowed"]
            if parsed.lower() not in [a.lower() for a in allowed]:
                return False, None, f"Setting '{key}' must be one of: {', '.join(allowed)}, got '{parsed}'"
            # Normalize to canonical casing
            for a in allowed:
                if a.lower() == parsed.lower():
                    parsed = a
                    break

        if "regex" in meta:
            pattern = meta["regex"]
            if not re.match(pattern, parsed):
                return False, None, f"Setting '{key}' does not match required format (e.g. HH:MM), got '{parsed}'"

        return True, parsed, None

    return False, None, f"Unsupported schema type for key '{key}'"

def validate_settings_payload(payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Dict[str, str]]:
    """
    Validate an entire dictionary of incoming settings.
    Returns: (all_valid: bool, cleaned_data: dict, errors: dict)
    """
    cleaned: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    if not isinstance(payload, dict):
        return False, {}, {"_general": "Request body must be a JSON object"}

    for key, val in payload.items():
        # Allow internal or legacy keys to pass through safely if needed, or validate known keys
        if key in SETTINGS_SCHEMA:
            valid, parsed_val, err = validate_setting(key, val)
            if valid:
                cleaned[key] = parsed_val
            else:
                errors[key] = err or "Validation failed"
        else:
            errors[key] = f"Unrecognized setting: '{key}'"

    # Cross-field validation: Manual location requires city
    if cleaned.get("location_auto") is False:
        city = cleaned.get("location_city", "")
        if not city or not str(city).strip():
            errors["location_city"] = "City is required when automatic location is disabled"

    all_valid = len(errors) == 0
    return all_valid, cleaned, errors

validate_settings = validate_settings_payload
validate_all_settings = validate_settings_payload

def is_in_quiet_hours(settings_or_start: Any, end_or_current: Any = None, current_time: Optional[time] = None) -> bool:
    """
    Check if the given time falls within quiet hours.
    Supports either:
      is_in_quiet_hours(settings_dict, current_time=None)
    or:
      is_in_quiet_hours(start_str, end_str, current_time=None)
    Correctly supports quiet hours crossing midnight (e.g., 22:00 -> 07:00).
    """
    if isinstance(settings_or_start, dict):
        settings = settings_or_start
        if not settings.get("quiet_hours_enabled", False):
            return False
        start_str = settings.get("quiet_hours_start", "22:00")
        end_str = settings.get("quiet_hours_end", "08:00")
        check_time = end_or_current if isinstance(end_or_current, time) else (current_time or datetime.now().time())
    elif isinstance(settings_or_start, str):
        start_str = settings_or_start
        end_str = end_or_current or "08:00"
        check_time = current_time or (end_or_current if isinstance(end_or_current, time) else datetime.now().time())
    else:
        return False

    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)
    except Exception:
        return False

    if start_t <= end_t:
        # Range does not cross midnight (e.g. 01:00 to 07:00)
        return start_t <= check_time < end_t
    else:
        # Range crosses midnight (e.g. 22:00 to 07:00)
        return check_time >= start_t or check_time < end_t
