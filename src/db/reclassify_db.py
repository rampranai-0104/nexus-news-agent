import os
import sys
import shutil
from datetime import datetime, timezone
from collections import defaultdict

# Add project root and src to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from db.database import get_connection
from ai.categorizer import classify_text_detailed, VALID_CATEGORIES
from core.logger import get_logger

logger = get_logger("reclassify_db")


def backup_sqlite_db(db_path: str) -> str:
    """Create a safe timestamped copy of the SQLite database before reclassification."""
    if not os.path.exists(db_path):
        return ""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.bak_{timestamp}"
    shutil.copy2(db_path, backup_path)
    logger.info(f"Database backed up to: {backup_path}")
    return backup_path


def run_reclassification(dry_run: bool = False) -> dict:
    """
    Safely reclassify all stored news articles in the database.
    - Preserves all fields (url, title, published_at, source, summary, importance, timestamps)
    - Updates only category when the new classification is confident
    - Automatically backs up SQLite database before executing updates
    - Returns report dictionary with transition statistics
    """
    conn, db_type = get_connection()
    cursor = conn.cursor()
    
    # 1. Automatic Backup
    backup_file = ""
    if db_type == "sqlite":
        from config import DB_PATH
        backup_file = backup_sqlite_db(DB_PATH)
        
    # 2. Get distribution before
    cursor.execute("SELECT category, count(*) as cnt FROM news GROUP BY category")
    before_counts = {row[0] if type(row) is tuple or hasattr(row, '__getitem__') else row["category"]: 
                     row[1] if type(row) is tuple or hasattr(row, '__getitem__') else row["cnt"] 
                     for row in cursor.fetchall()}
    
    # 3. Fetch all articles
    cursor.execute("SELECT id, title, description, content, category, source FROM news")
    articles = cursor.fetchall()
    
    total_articles = len(articles)
    logger.info(f"Starting reclassification for {total_articles} articles (dry_run={dry_run})...")
    
    updates = []
    transitions = defaultdict(int)
    suspicious_samples = []
    
    for row in articles:
        if type(row) is tuple or hasattr(row, '__getitem__'):
            art_id, title, desc, content, old_cat, source = row[0], row[1], row[2], row[3], row[4], row[5]
        else:
            art_id = row["id"]
            title = row["title"]
            desc = row["description"]
            content = row["content"]
            old_cat = row["category"]
            source = row["source"]
            
        old_cat_norm = (old_cat or "").strip().lower()
        
        # Classify article using multi-signal hierarchical engine
        new_cat, confidence, scores, reason = classify_text_detailed(
            title=title,
            description=desc,
            content=content,
            source_category=old_cat_norm,
            source_name=source
        )
        
        # Decide if category should be updated:
        # - Always update invalid categories ('world', 'general', 'all', empty, etc.)
        # - For valid categories, update if new_cat != old_cat_norm AND confidence >= 0.25
        should_update = False
        if old_cat_norm not in VALID_CATEGORIES:
            should_update = True
        elif new_cat != old_cat_norm:
            # Significant change (e.g. technology -> sports, national -> local, etc.)
            should_update = True
            
        if should_update and new_cat != old_cat_norm:
            updates.append((new_cat, art_id))
            transition_key = f"{old_cat_norm} -> {new_cat}"
            transitions[transition_key] += 1
            
            # Record interesting or significant transitions for logging
            if len(suspicious_samples) < 20 or "technology -> sports" in transition_key or "national -> local" in transition_key:
                suspicious_samples.append({
                    "id": art_id,
                    "title": (title or "")[:80],
                    "old_category": old_cat_norm,
                    "new_category": new_cat,
                    "confidence": confidence,
                    "reason": reason
                })
                
    # 4. Perform database updates
    if not dry_run and updates:
        logger.info(f"Applying {len(updates)} category updates to database...")
        update_query = "UPDATE news SET category = %s WHERE id = %s" if db_type == "postgres" else "UPDATE news SET category = ? WHERE id = ?"
        cursor.executemany(update_query, updates)
        conn.commit()
        logger.info(f"Successfully applied {len(updates)} updates.")
        
    # 5. Get distribution after
    cursor.execute("SELECT category, count(*) as cnt FROM news GROUP BY category")
    after_counts = {row[0] if type(row) is tuple or hasattr(row, '__getitem__') else row["category"]: 
                    row[1] if type(row) is tuple or hasattr(row, '__getitem__') else row["cnt"] 
                    for row in cursor.fetchall()}
    
    conn.close()
    
    report = {
        "backup_file": backup_file,
        "total_articles": total_articles,
        "updated_count": len(updates),
        "dry_run": dry_run,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "transitions": dict(transitions),
        "sample_transitions": suspicious_samples[:15]
    }
    
    # 6. Formatted Logging
    summary_lines = [
        "==================================================",
        "NEXUS NEWS DATABASE RECLASSIFICATION REPORT",
        "==================================================",
        f"Database Type:      {db_type}",
        f"Backup File:        {backup_file or 'N/A'}",
        f"Total Records:      {total_articles}",
        f"Records Reclassified: {len(updates)}",
        "",
        "CATEGORY DISTRIBUTION:",
        f"{'Category':<15} {'Before':<10} {'After':<10}",
        "-" * 35
    ]
    all_cat_names = sorted(set(list(before_counts.keys()) + list(after_counts.keys()) + VALID_CATEGORIES))
    for c in all_cat_names:
        summary_lines.append(f"{c:<15} {before_counts.get(c, 0):<10} {after_counts.get(c, 0):<10}")
        
    summary_lines.append("")
    summary_lines.append("TOP TRANSITIONS (Old -> New):")
    summary_lines.append("-" * 35)
    for trans, count in sorted(transitions.items(), key=lambda x: x[1], reverse=True):
        summary_lines.append(f"  {trans:<30}: {count}")
        
    summary_lines.append("==================================================")
    logger.info("\n".join(summary_lines))
    print("\n".join(summary_lines))
    
    return report


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    run_reclassification(dry_run=is_dry)
