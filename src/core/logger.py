import logging
import os

LOG_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'app.log')

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # File handler - saves logs to file
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Console handler - shows logs in terminal
    console_handler = logging.StreamHandler()
    console_handler.stream.reconfigure(encoding='utf-8', errors='replace')
    console_handler.setLevel(logging.INFO)

    # Format
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger