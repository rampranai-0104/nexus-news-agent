import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QFrame, QSizePolicy,
    QProgressBar
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QCursor

from db.database import get_news_by_category, init_db
from core.logger import get_logger

logger = get_logger("chat_ui")


# ── Pipeline thread ───────────────────────────────────────────────────────────
class PipelineThread(QThread):
    finished = pyqtSignal(list)
    progress = pyqtSignal(str, int)

    def run(self):
        try:
            import sys, os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
            from fetch.news_api import fetch_all_news
            from ai.categorizer import categorize_news_list
            from ai.summarizer  import summarize_news_list
            from db.database    import init_db, save_news, mark_ran_today
            import sqlite3

            DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'news.db')

            self.progress.emit("Clearing old news…", 5)
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM news")
                conn.commit()
                conn.close()
            except:
                pass

            self.progress.emit("Fetching latest headlines from RSS feeds…", 15)
            news = fetch_all_news()

            self.progress.emit(f"Fetched {len(news)} articles. Categorizing…", 35)
            news = categorize_news_list(news)

            self.progress.emit("AI is summarizing articles…", 50)
            news = summarize_news_list(news)

            self.progress.emit("Saving to database…", 90)
            save_news(news)
            mark_ran_today()

            self.progress.emit("Done!", 100)
            self.finished.emit(news)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            self.finished.emit([])


# ── Read More button ──────────────────────────────────────────────────────────
class ReadMoreButton(QLabel):
    def __init__(self, url, parent=None):
        super().__init__("Read More →", parent)
        self._url = url
        self.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.setStyleSheet("color:#004ac6; background:transparent; border:none;")
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mousePressEvent(self, event):
        try:
            import webbrowser
            webbrowser.open(self._url)
        except Exception:
            pass
        event.accept()


# ── Sidebar nav item ──────────────────────────────────────────────────────────
class NavItem(QLabel):
    clicked_signal = pyqtSignal(str)

    def __init__(self, icon, label, cat=None, active=False):
        super().__init__()
        self.cat     = cat or ""
        self._active = active
        self.setText(f"  {icon}   {label}")
        self.setFixedHeight(40)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._style()

    def _style(self):
        if self._active:
            self.setStyleSheet("""
                QLabel { background:#e8eeff; color:#004ac6; border-radius:8px;
                         padding:0 12px; font-size:13px; font-weight:700; }
            """)
        else:
            self.setStyleSheet("""
                QLabel { background:transparent; color:#555770; border-radius:8px;
                         padding:0 12px; font-size:13px; font-weight:500; }
                QLabel:hover { background:#f0f0f5; color:#1a1c1c; }
            """)

    def set_active(self, v):
        self._active = v
        self._style()

    def mousePressEvent(self, event):
        self.clicked_signal.emit(self.cat)
        event.accept()


# ── Article card ──────────────────────────────────────────────────────────────
class ArticleCard(QFrame):
    CAT_COLORS = {
        "sports":     "#15803d",
        "technology": "#004ac6",
        "business":   "#b45309",
        "national":   "#7c3aed",
        "global":     "#0369a1",
        "local":      "#dc2626",
        "general":    "#475569",
    }
    CAT_LABELS = {
        "sports":     "SPORTS",
        "technology": "TECHNOLOGY",
        "business":   "MARKETS",
        "national":   "INDIA",
        "global":     "WORLD",
        "local":      "LOCAL",
        "general":    "GENERAL",
    }

    def __init__(self, article, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setStyleSheet("""
            QFrame {
                background:#ffffff;
                border:1px solid #e0e0e8;
                border-radius:10px;
                margin-bottom:10px;
            }
        """)

        cat   = article.get("category", "general")
        color = self.CAT_COLORS.get(cat, "#475569")
        label = self.CAT_LABELS.get(cat, cat.upper())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Meta row
        meta = QHBoxLayout()
        meta.setSpacing(8)
        cat_lbl = QLabel(label)
        cat_lbl.setStyleSheet(f"""
            color:{color}; font-size:11px; font-weight:700;
            letter-spacing:1px; background:transparent; border:none;
        """)
        sep = QLabel("•")
        sep.setStyleSheet("color:#c0c0cc; font-size:11px; background:transparent; border:none;")
        src_lbl = QLabel(article.get("source", "Unknown"))
        src_lbl.setStyleSheet("color:#737686; font-size:11px; background:transparent; border:none;")
        meta.addWidget(cat_lbl)
        meta.addWidget(sep)
        meta.addWidget(src_lbl)
        meta.addStretch()
        layout.addLayout(meta)

        # Title
        title = QLabel(article.get("title", ""))
        title.setWordWrap(True)
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title.setStyleSheet("color:#1a1c1c; background:transparent; border:none;")
        layout.addWidget(title)

        # AI Summary box
        summary_text = article.get("summary") or article.get("description", "")
        if summary_text:
            sf = QFrame()
            sf.setStyleSheet("""
                QFrame {
                    background:#f5f6ff;
                    border-left:3px solid #004ac6;
                    border-top:none; border-right:none; border-bottom:none;
                    border-radius:0 6px 6px 0;
                }
            """)
            sf_lay = QVBoxLayout(sf)
            sf_lay.setContentsMargins(12, 8, 12, 8)
            sf_lay.setSpacing(3)

            ai_tag = QLabel("NEXUS AI SYNTHESIS")
            ai_tag.setStyleSheet("""
                color:#004ac6; font-size:10px; font-weight:700;
                letter-spacing:1px; background:transparent; border:none;
            """)
            sf_lay.addWidget(ai_tag)

            summ_lbl = QLabel(summary_text)
            summ_lbl.setWordWrap(True)
            summ_lbl.setFont(QFont("Segoe UI", 10))
            summ_lbl.setStyleSheet("color:#2a2c3c; font-style:italic; background:transparent; border:none;")
            sf_lay.addWidget(summ_lbl)
            layout.addWidget(sf)

        # Footer
        footer = QHBoxLayout()
        sent   = self._sentiment(article.get("title", "") + " " + summary_text)
        sent_lbl = QLabel(sent["label"])
        sent_lbl.setStyleSheet(f"""
            background:{sent['bg']}; color:{sent['fg']};
            font-size:11px; font-weight:700;
            border-radius:10px; padding:3px 10px; border:none;
        """)
        footer.addWidget(sent_lbl)
        footer.addStretch()

        url = article.get("url", "")
        if url:
            rm = ReadMoreButton(url)
            footer.addWidget(rm)

        layout.addLayout(footer)

    def _sentiment(self, text):
        t = text.lower()
        pos = ["wins","growth","surge","record","breakthrough",
               "rally","gain","launch","rise","success","awarded"]
        neg = ["crash","fail","drop","war","conflict","crisis",
               "loss","decline","struggle","strike","ban","kill"]
        if any(w in t for w in pos):
            return {"label": "↑ Optimistic", "bg": "#f0fdf4", "fg": "#15803d"}
        if any(w in t for w in neg):
            return {"label": "↓ Cautious",   "bg": "#fef2f2", "fg": "#b91c1c"}
        return     {"label": "— Neutral",    "bg": "#f0f0f5", "fg": "#555770"}


# ── Main window ───────────────────────────────────────────────────────────────
class NewsAgentUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nexus News — Intelligence Briefing")
        self.setMinimumSize(900, 700)
        self.resize(1100, 800)
        self._all_articles = []
        self._active_cat   = None
        self._nav_items    = []
        self._build_ui()
        QTimer.singleShot(400, self._load_news)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet("background:#f5f5f8;")
        main_row = QHBoxLayout(root)
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("background:#ffffff; border-right:1px solid #e0e0e8;")
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(12, 24, 12, 20)
        sb.setSpacing(2)

        brand = QLabel("Nexus News")
        brand.setFont(QFont("Segoe UI", 15, QFont.Bold))
        brand.setStyleSheet("color:#004ac6; padding:0 8px; background:transparent;")
        tagline = QLabel("YOUR PERSONAL ANALYST")
        tagline.setFont(QFont("Segoe UI", 8, QFont.Bold))
        tagline.setStyleSheet(
            "color:#737686; padding:0 8px 18px 8px; "
            "letter-spacing:1px; background:transparent;"
        )
        sb.addWidget(brand)
        sb.addWidget(tagline)

        nav_cfg = [
            ("📰", "All News",    "",           True),
            ("🏏", "Sports",      "sports",     False),
            ("💻", "Technology",  "technology", False),
            ("📈", "Markets",     "business",   False),
            ("🇮🇳", "India",      "national",   False),
            ("🌍", "World",       "global",     False),
            ("📍", "Local",       "local",      False),
        ]
        for icon, lbl, cat, active in nav_cfg:
            item = NavItem(icon, lbl, cat, active)
            item.clicked_signal.connect(self._on_nav)
            sb.addWidget(item)
            self._nav_items.append(item)

        sb.addStretch()

        self.refresh_btn = QPushButton("⟳   Refresh News")
        self.refresh_btn.setFixedHeight(42)
        self.refresh_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.refresh_btn.setStyleSheet("""
            QPushButton { background:#004ac6; color:white; border-radius:21px; border:none; }
            QPushButton:hover    { background:#1d63d4; }
            QPushButton:disabled { background:#c0c0d0; color:#888; }
        """)
        self.refresh_btn.clicked.connect(self._run_pipeline)
        sb.addWidget(self.refresh_btn)
        main_row.addWidget(sidebar)

        # ── Main content ──
        content = QWidget()
        content.setStyleSheet("background:#f5f5f8;")
        feed_col = QVBoxLayout(content)
        feed_col.setContentsMargins(32, 24, 32, 16)
        feed_col.setSpacing(0)

        # Header
        hdr_row   = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        self.feed_title = QLabel("Intelligence Briefing")
        self.feed_title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.feed_title.setStyleSheet("color:#1a1c1c; background:transparent;")

        self.feed_sub = QLabel("Loading…")
        self.feed_sub.setFont(QFont("Segoe UI", 11))
        self.feed_sub.setStyleSheet("color:#737686; background:transparent;")

        title_col.addWidget(self.feed_title)
        title_col.addWidget(self.feed_sub)
        hdr_row.addLayout(title_col)
        hdr_row.addStretch()
        feed_col.addLayout(hdr_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background:#e0e0e8; border-radius:2px; border:none; }
            QProgressBar::chunk { background:#004ac6; border-radius:2px; }
        """)
        self.progress_bar.hide()
        feed_col.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setFont(QFont("Segoe UI", 10))
        self.progress_label.setStyleSheet(
            "color:#004ac6; background:transparent; padding:4px 0;"
        )
        self.progress_label.hide()
        feed_col.addWidget(self.progress_label)

        # Search bar
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍   Search headlines…")
        self.search_box.setFixedHeight(44)
        self.search_box.setFont(QFont("Segoe UI", 12))
        self.search_box.setStyleSheet("""
            QLineEdit {
                background:#ffffff; border:1px solid #d0d0dc;
                border-radius:22px; padding:0 20px;
                color:#1a1c1c; margin:12px 0 14px 0;
                font-size:13px;
            }
            QLineEdit:focus { border-color:#004ac6; }
        """)
        self.search_box.textChanged.connect(self._on_search)
        feed_col.addWidget(self.search_box)

        # Feed scroll area
        self.feed_scroll = QScrollArea()
        self.feed_scroll.setWidgetResizable(True)
        self.feed_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.feed_scroll.setStyleSheet("""
            QScrollArea { border:none; background:transparent; }
            QScrollBar:vertical { width:5px; background:transparent; }
            QScrollBar::handle:vertical { background:#c8c8d8; border-radius:3px; }
        """)
        self.feed_container = QWidget()
        self.feed_container.setStyleSheet("background:transparent;")
        self.feed_layout = QVBoxLayout(self.feed_container)
        self.feed_layout.setContentsMargins(0, 0, 8, 0)
        self.feed_layout.setSpacing(0)
        self.feed_layout.setAlignment(Qt.AlignTop)
        self.feed_scroll.setWidget(self.feed_container)
        feed_col.addWidget(self.feed_scroll)

        main_row.addWidget(content)

    # ── Load from cache ───────────────────────────────────────────────────────
    def _load_news(self):
        init_db()
        arts = get_news_by_category()
        if arts:
            self._all_articles = arts
            self._render_feed()
        else:
            self.feed_sub.setText("No articles yet — click Refresh News in the sidebar")

    # ── Run full pipeline ─────────────────────────────────────────────────────
    def _run_pipeline(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Fetching…")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.show()
        self.thread = PipelineThread()
        self.thread.progress.connect(self._on_progress)
        self.thread.finished.connect(self._on_done)
        self.thread.start()

    def _on_progress(self, msg, pct):
        self.progress_bar.setValue(pct)
        self.progress_label.setText(f"⏳  {msg}")

    def _on_done(self, articles):
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("⟳   Refresh News")
        self.progress_bar.hide()
        self.progress_label.hide()
        if articles:
            self._all_articles = articles
            self._active_cat   = None
            for item in self._nav_items:
                item.set_active(item.cat == "")
            self._render_feed()
        else:
            self.feed_sub.setText("Fetch failed — check internet and API keys")

    # ── Render feed ───────────────────────────────────────────────────────────
    def _render_feed(self):
        # Clear existing
        while self.feed_layout.count():
            w = self.feed_layout.takeAt(0)
            if w.widget():
                w.widget().deleteLater()

        arts = self._all_articles
        cat  = self._active_cat
        q    = self.search_box.text().strip().lower()

        if cat:
            arts = [a for a in arts if a.get("category", "") == cat]
        if q:
            arts = [a for a in arts if q in (
                a.get("title", "") + " " +
                a.get("summary", "") + " " +
                a.get("description", "")
            ).lower()]

        from datetime import datetime
        date_str = datetime.now().strftime("%A, %d %B %Y")
        self.feed_sub.setText(f"{len(arts)} articles · {date_str}")

        # Update header title based on active category
        CAT_TITLES = {
            "":           "Intelligence Briefing",
            "sports":     "🏏  Sports",
            "technology": "💻  Technology",
            "business":   "📈  Markets",
            "national":   "🇮🇳  India",
            "global":     "🌍  World",
            "local":      "📍  Local",
        }
        self.feed_title.setText(CAT_TITLES.get(cat or "", "Intelligence Briefing"))

        if not arts:
            empty = QLabel("No articles found for this filter.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setFont(QFont("Segoe UI", 12))
            empty.setStyleSheet("color:#9090a0; padding:60px; background:transparent;")
            self.feed_layout.addWidget(empty)
            return

        CAT_ORDER = ["local","national","global","sports","technology","business","general"]
        CAT_LABELS = {
            "sports":     "🏏  SPORTS",
            "technology": "💻  TECHNOLOGY",
            "business":   "📈  MARKETS",
            "national":   "🇮🇳  INDIA",
            "global":     "🌍  WORLD",
            "local":      "📍  LOCAL",
            "general":    "📰  GENERAL",
        }
        CAT_COLORS = {
            "sports":     "#15803d",
            "technology": "#004ac6",
            "business":   "#b45309",
            "national":   "#7c3aed",
            "global":     "#0369a1",
            "local":      "#dc2626",
            "general":    "#475569",
        }

        from collections import defaultdict
        groups = defaultdict(list)
        for a in arts:
            groups[a.get("category", "general")].append(a)

        sorted_cats = sorted(
            groups,
            key=lambda c: CAT_ORDER.index(c) if c in CAT_ORDER else 99
        )

        for cat_key in sorted_cats:
            # Only show section headers when viewing all news
            if not cat:
                color = CAT_COLORS.get(cat_key, "#475569")
                lbl   = QLabel(CAT_LABELS.get(cat_key, cat_key.upper()))
                lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
                lbl.setFixedHeight(28)
                lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                lbl.setStyleSheet(f"""
                    color:{color}; background:{color}18;
                    border-radius:10px; padding:0 12px;
                    letter-spacing:1px; margin-bottom:6px; margin-top:10px;
                """)
                self.feed_layout.addWidget(lbl)

            for article in groups[cat_key][:5]:
                self.feed_layout.addWidget(ArticleCard(article))

        self.feed_layout.addStretch()

    # ── Nav click ─────────────────────────────────────────────────────────────
    def _on_nav(self, cat):
        self._active_cat = cat if cat else None
        for item in self._nav_items:
            item.set_active(item.cat == cat)
        self._render_feed()

    # ── Search ────────────────────────────────────────────────────────────────
    def _on_search(self, _):
        self._render_feed()


# ── Launch ────────────────────────────────────────────────────────────────────
def launch():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    win = NewsAgentUI()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    launch()