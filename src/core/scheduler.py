import os
import sys
import time
import datetime

# Fix import path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC_DIR  = os.path.join(BASE_DIR, 'src')
sys.path.insert(0, SRC_DIR)

from core.logger import get_logger
logger = get_logger("scheduler")

LAST_RUN_FILE = os.path.join(BASE_DIR, 'data', 'last_run.txt')

def already_ran_today():
    try:
        if not os.path.exists(LAST_RUN_FILE):
            return False
        with open(LAST_RUN_FILE, 'r') as f:
            last_run = f.read().strip()
        today = datetime.date.today().strftime("%Y-%m-%d")
        return last_run == today
    except Exception as e:
        logger.error(f"Error checking last run: {e}")
        return False

def check_internet():
    try:
        import requests
        requests.get("https://www.google.com", timeout=5)
        return True
    except:
        return False

def wait_for_internet(max_wait=120):
    logger.info("Checking internet connection...")
    for i in range(max_wait // 5):
        if check_internet():
            logger.info("Internet connection confirmed")
            return True
        logger.info(f"No internet yet, waiting... ({(i+1)*5}s)")
        time.sleep(5)
    logger.error("Internet not available after waiting")
    return False

def startup_delay(minutes=4):
    seconds = minutes * 60
    logger.info(f"Waiting {minutes} minutes for system to load...")
    time.sleep(seconds)
    logger.info("Startup delay complete")

def launch_ui_only():
    try:
        python  = sys.executable
        ui_path = os.path.join(SRC_DIR, 'ui', 'chat_ui.py')
        os.system(f'start "" "{python}" "{ui_path}"')
        logger.info("UI launched with cached news")
    except Exception as e:
        logger.error(f"Failed to launch UI: {e}")

def launch_full():
    try:
        python    = sys.executable
        main_path = os.path.join(SRC_DIR, 'main.py')
        ui_path   = os.path.join(SRC_DIR, 'ui', 'chat_ui.py')

        # Run pipeline
        logger.info("Running pipeline...")
        os.system(f'"{python}" "{main_path}"')

        # Send notifications
        logger.info("Sending notifications...")
        try:
            from core.notifier import check_and_notify
            from db.database   import get_news_by_category
            articles = get_news_by_category()
            check_and_notify(articles)
        except Exception as e:
            logger.error(f"Notification error: {e}")

        # Launch UI
        logger.info("Launching UI...")
        os.system(f'start "" "{python}" "{ui_path}"')

    except Exception as e:
        logger.error(f"Failed to launch: {e}")

def run_startup():
    logger.info("=== News Agent Startup ===")

    startup_delay(minutes=1)  # change to 4 for real use

    if already_ran_today():
        logger.info("Already ran today — opening UI with cached news")
        launch_ui_only()
        return

    if not wait_for_internet(max_wait=120):
        logger.error("No internet — cannot fetch news")
        return

    logger.info("Running full news pipeline...")
    launch_full()


if __name__ == "__main__":
    run_startup()