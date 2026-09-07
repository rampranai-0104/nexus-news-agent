import datetime
from core.logger import get_logger

logger = get_logger("source_tracker")

class SourceTracker:
    """
    Lightweight health tracker for news sources (RSS feeds, APIs, Scrapers).
    Prevents repeated slow requests to continuously failing domains.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SourceTracker, cls).__new__(cls)
            cls._instance.health = {}
        return cls._instance
        
    def record_success(self, source_name: str):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if source_name not in self.health:
            self.health[source_name] = {
                "source_name": source_name,
                "last_success": now_iso,
                "last_failure": None,
                "failure_reason": None,
                "consecutive_failures": 0,
                "total_successes": 1
            }
        else:
            self.health[source_name]["last_success"] = now_iso
            self.health[source_name]["consecutive_failures"] = 0
            self.health[source_name]["total_successes"] = self.health[source_name].get("total_successes", 0) + 1
            
    def record_failure(self, source_name: str, reason: str):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if source_name not in self.health:
            self.health[source_name] = {
                "source_name": source_name,
                "last_success": None,
                "last_failure": now_iso,
                "failure_reason": str(reason),
                "consecutive_failures": 1,
                "total_successes": 0
            }
        else:
            self.health[source_name]["last_failure"] = now_iso
            self.health[source_name]["failure_reason"] = str(reason)
            self.health[source_name]["consecutive_failures"] += 1
            
        logger.warning(f"Source failure recorded | {source_name} | {reason} | consecutive: {self.health[source_name]['consecutive_failures']}")

    def should_skip(self, source_name: str, max_consecutive: int = 4) -> bool:
        """
        Skip if source has failed multiple times consecutively within the last 15 minutes.
        """
        rec = self.health.get(source_name)
        if not rec or rec.get("consecutive_failures", 0) < max_consecutive:
            return False
            
        last_failure = rec.get("last_failure")
        if not last_failure:
            return False
            
        try:
            lf_time = datetime.datetime.fromisoformat(last_failure)
            now = datetime.datetime.now(datetime.timezone.utc)
            if (now - lf_time).total_seconds() < 900: # 15 min cool-off
                logger.info(f"Temporarily skipping failing source '{source_name}' ({rec['consecutive_failures']} recent failures: {rec['failure_reason']})")
                return True
        except Exception:
            pass
            
        return False
        
    def get_summary(self):
        total = len(self.health)
        failing = sum(1 for v in self.health.values() if v.get("consecutive_failures", 0) > 0)
        healthy = total - failing
        return {
            "total_tracked": total,
            "healthy": healthy,
            "failing": failing,
            "details": self.health
        }

source_tracker = SourceTracker()
