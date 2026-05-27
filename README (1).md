# 🤖 Nexus News — AI News Agent

> A fully automated AI news agent that fetches, summarizes, and delivers daily news — as a desktop app and web app.

🌐 **Live Web App:** [https://rampranai-0104.github.io/nexus-news-agent/](https://rampranai-0104.github.io/nexus-news-agent/)

---

## 📌 What It Does

Every morning at **7 AM IST**, the agent automatically:
- Fetches **30 real-time news articles** from RSS feeds across 6 categories
- Summarizes each article using **Groq LLaMA 3 AI** (3–4 sentence paragraphs)
- Saves everything to a **PostgreSQL database** on Render
- Makes news available via a **web app** and a **desktop app**

The desktop app also **auto-launches 5 minutes after you log into Windows** — your morning brief is waiting before you've even had your coffee.

---

## 🚀 Features

- 📰 **30 articles daily** from The Hindu, NDTV, Indian Express, BBC, TechCrunch, Economic Times, and more
- 🧠 **AI summaries** — Groq LLaMA 3 generates clear 3–4 sentence summaries of each full article
- 🗂️ **6 categories** — Sports, Technology, Markets, India, World, Local (Andhra Pradesh / Telangana)
- 🔍 **Real-time search** — filter articles by keyword instantly
- 💬 **Sentiment badges** — Optimistic / Cautious / Neutral per article
- 🔗 **Read More** — opens the full original article in browser
- 📱 **Web app** — works on phone, tablet, laptop — any browser, no install
- 🖥️ **Desktop app** — PyQt5 window with sidebar navigation
- ⏰ **Auto-launch** — opens 5 minutes after Windows login (Task Scheduler)
- 🔔 **Notifications** — breaking news toast alerts via plyer
- 🔄 **Daily automation** — cron-job.org triggers server fetch at 7 AM IST

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Desktop UI | Python + PyQt5 |
| News Sources | RSS Feeds + NewsAPI |
| AI Summarizer | Groq API (LLaMA 3.1 8B Instant) |
| Categorizer | Keyword-based NLP (Python) |
| Local Fallback | Sumy + NLTK (offline) |
| Backend API | FastAPI + Uvicorn |
| Database | PostgreSQL (Render) |
| Hosting | Render.com (free tier) |
| Web App | HTML + CSS + Vanilla JS |
| Web Hosting | GitHub Pages |
| Scheduler | Windows Task Scheduler |
| Notifications | plyer |
| Cron Jobs | cron-job.org |

---

## 📁 Project Structure

```
news-agent/
├── src/
│   ├── main.py                  # Pipeline runner
│   ├── fetch/
│   │   ├── news_api.py          # NewsAPI fetcher
│   │   └── rss_parser.py        # RSS feed parser (multi-source)
│   ├── ai/
│   │   ├── summarizer.py        # Groq + Sumy summarizer
│   │   └── categorizer.py       # Keyword-based categorizer
│   ├── db/
│   │   └── database.py          # SQLite local DB
│   ├── ui/
│   │   └── chat_ui.py           # PyQt5 desktop app
│   └── core/
│       ├── scheduler.py         # Startup automation
│       ├── notifier.py          # Toast notifications
│       └── logger.py            # Logging system
├── server.py                    # FastAPI backend (Render)
├── index.html                   # Web app (GitHub Pages)
├── render.yaml                  # Render deployment config
├── requirements.txt
├── setup/
│   └── install.bat              # Task Scheduler installer
├── data/
│   ├── news.db                  # Local SQLite database
│   └── last_run.txt             # Daily flag
└── logs/
    └── app.log
```

---

## ⚙️ Setup — Local Desktop App

### Prerequisites
- Python 3.10+
- Windows (for auto-launch feature)

### 1. Clone the repo
```bash
git clone https://github.com/rampranai-0104/nexus-news-agent.git
cd nexus-news-agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
pip install sumy nltk numpy
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"
```

### 3. Create `.env` file
```
NEWSAPI_KEY=your_newsapi_key
GROQ_API_KEY=your_groq_key
HUGGINGFACE_TOKEN=your_hf_token
```

### 4. Get free API keys

| Key | Where to get |
|---|---|
| NewsAPI | [newsapi.org](https://newsapi.org) — free, 100 req/day |
| Groq | [console.groq.com](https://console.groq.com) — free, 100k tokens/day |
| HuggingFace | [huggingface.co](https://huggingface.co) — free |

### 5. Run the desktop app
```bash
python src/ui/chat_ui.py
```

### 6. Fetch fresh news
```bash
python src/main.py
```

### 7. Install startup automation (Windows)
Right-click `setup/install.bat` → **Run as administrator**

The app will now auto-open 5 minutes after every Windows login.

---

## 🌐 Web App — No Installation Needed

Just open: **[https://rampranai-0104.github.io/nexus-news-agent/](https://rampranai-0104.github.io/nexus-news-agent/)**

Works on any device, any browser. No Python, no API keys, no setup.

---

## 🖥️ Backend API (Render)

Base URL: `https://nexus-news-api-oncr.onrender.com`

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check |
| `/news` | GET | Get all articles |
| `/news?category=sports` | GET | Filter by category |
| `/status` | GET | Check last fetch time |
| `/fetch` | POST | Trigger news fetch |

### Trigger manual fetch
```bash
python -c "import requests; r = requests.post('https://nexus-news-api-oncr.onrender.com/fetch', timeout=300); print(r.json())"
```

---

## 🗂️ News Categories

| Category | Sources |
|---|---|
| 🏏 Sports | The Hindu, Indian Express, TOI, NDTV Sports, BBC Sport |
| 💻 Technology | The Hindu Tech, Indian Express, NDTV Tech, TechCrunch, TOI |
| 📈 Markets | Economic Times, Indian Express, The Hindu Business, NDTV Business |
| 🇮🇳 India | The Hindu, NDTV, Indian Express, Hindustan Times, TOI |
| 🌍 World | BBC World, The Hindu, Indian Express, NDTV World |
| 📍 Local | The Hindu AP, The Hindu TS, The News Minute, Indian Express Hyd |

---

## 🔄 How Automation Works

```
7:00 AM IST
    │
    ▼
cron-job.org triggers POST /fetch
    │
    ▼
Server fetches RSS articles → categorizes → Groq summarizes → saves to PostgreSQL
    │
    ▼
Anyone opens the web app → articles load instantly

────────────────────────────────────

Windows Login
    │
    ▼  (5 min delay)
scheduler.py runs via Task Scheduler
    │
    ▼
Internet check → daily flag check
    │
    ▼
Fetches from server → Nexus News desktop window opens
```

---

## 📊 Free Tier Limits

| Service | Limit | Usage |
|---|---|---|
| Groq API | 100,000 tokens/day | ~3,000 tokens per 30 articles |
| NewsAPI | 100 requests/day | 6 requests per fetch |
| Render (web) | 750 hours/month | ~30 hours/month |
| Render (DB) | 1 GB storage | < 10 MB |
| GitHub Pages | Unlimited | Static HTML |
| cron-job.org | Unlimited | 2 jobs |

All free. No credit card required for any service.

---

## 🔮 Future Enhancements

- 🔊 Voice assistant — morning audio briefing (text-to-speech)
- 🌍 Telugu language support
- 📊 News analytics dashboard
- 🤖 Personalized recommendations based on reading history
- ☁️ User accounts and cloud sync
- 📱 React Native mobile app

---

## 👤 Author

**Ram Pranai** — [@rampranai-0104](https://github.com/rampranai-0104)

Built with Python, FastAPI, PyQt5, Groq AI, and a lot of debugging 🛠️

---

## 📄 License

MIT License — free to use, modify, and distribute.
