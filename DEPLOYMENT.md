# Nexus News Agent — Production Deployment Guide

This guide details the complete production deployment procedure for Nexus News Agent using **FastAPI on Render** and **MongoDB Atlas** as the active persistent store.

---

## 1. Architecture Overview

```
[Decoupled Frontend Option]                  [Unified Deployment Option]
Vercel / Netlify (Static HTML/CSS/JS)        Render Web Service (FastAPI)
         │                                            │
         │ HTTPS                                      │ Serves index.html at '/'
         ▼                                            ▼
   Render Web Service (FastAPI Server on 0.0.0.0:$PORT)
         │
         │ TLS 1.3 / PyMongo Singleton Connection Pool
         ▼
   MongoDB Atlas Cloud (Cluster: nexus_news)
   Collections: articles (rolling 7-day retention), user_preferences
```

---

## 2. MongoDB Atlas Setup & Security Configuration

### A. Network Access (IP Whitelisting)
Render uses dynamic outbound IP addresses by default for its web services, unless a paid static outbound IP add-on is used.

1. **Option 1 (Recommended if using Render Static Outbound IP)**:
   - In MongoDB Atlas → **Network Access** → **Add IP Address**.
   - Add only the specific fixed egress IP addresses provided by your Render service.
   - Restricting Atlas access to fixed outbound IPs provides maximum perimeter security.

2. **Option 2 (Standard Render Dynamic IPs — 0.0.0.0/0 with Strict Hardening)**:
   - In MongoDB Atlas → **Network Access** → **Add IP Address** → Enter `0.0.0.0/0` (Allow access from anywhere).
   - **Mandatory Security Controls when using 0.0.0.0/0**:
     - **Least-Privilege Database User**: Create a dedicated database user scoped strictly to `readWrite` on the `nexus_news` database only. Never grant `atlasAdmin`, `readWriteAnyDatabase`, or cluster management privileges.
     - **High-Entropy Password**: Generate a random, high-entropy password (minimum 24+ alphanumeric characters and symbols).
     - **SCRAM-SHA-256 / TLS**: Ensure TLS/SSL encryption is enforced (default on Atlas SRV URIs).

### B. Database & Collections
- **Database**: `nexus_news`
- **Collections**:
  - `articles`: Primary news storage. Automatically indexed on:
    - `idx_unique_url`: `{"url": 1}` (`unique=True`)
    - `idx_published_importance`: `[("published_at", -1), ("importance", -1)]`
    - `idx_category_published`: `[("category", 1), ("published_at", -1)]`
    - `idx_breaking_published`: `[("is_breaking", 1), ("published_at", -1)]`
  - `user_preferences`: User appearance, category preferences, and location overrides.

---

## 3. Required Environment Variables

Configure these environment variables in your Render Web Service dashboard (or `.env` for local staging):

| Variable Name | Required | Default / Value | Description |
|---|---|---|---|
| `MONGODB_URI` | **YES** | `mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority` | Secret MongoDB Atlas connection string. Never commit or expose. |
| `DATABASE_NAME` | **YES** | `nexus_news` | Target database name in MongoDB Atlas. |
| `DB_BACKEND` | **YES** | `mongodb` | Active database backend. Set to `mongodb` for production. |
| `NEWS_RETENTION_DAYS` | NO | `7` | Automatic news retention window. Articles older than this (by `published_at`) are purged. |
| `NEWS_REFRESH_MINUTES` | NO | `15` | Freshness TTL for news ingestion cache. |
| `FRONTEND_ORIGIN` | NO | `https://your-frontend.vercel.app` | Allowed CORS origins for decoupled frontends (comma-separated for multiple origins). |
| `GROQ_API_KEY` | NO | `gsk_...` | API key for Groq AI news summarization and morning briefing. |
| `OPENAI_API_KEY` | NO | `sk-...` | Fallback AI provider API key. |
| `NEWSAPI_KEY` | NO | `...` | API key for NewsAPI ingestion. |
| `GNEWS_API_KEY` | NO | `...` | API key for GNews integration. |
| `IPINFO_TOKEN` | NO | `...` | Token for client geolocation detection. |
| `PORT` | Auto | Provided by Render (`10000`) | Port to bind to. FastAPI dynamically binds to `$PORT`. |
| `HOST` | Auto | `0.0.0.0` | Host binding for production. |

---

## 4. Render Web Service Deployment

### Method 1: Infrastructure as Code (render.yaml Blueprint)
1. In the Render Dashboard, select **New** → **Blueprint**.
2. Connect your GitHub repository (`nexus-news-agent`).
3. Render will read `render.yaml` automatically:
   - **Service Name**: `nexus-news-api`
   - **Environment**: `python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. Populate the secret environment variables (`MONGODB_URI`, API keys) prompted by the Render dashboard.
5. Click **Apply**.

### Method 2: Manual Web Service
1. Select **New** → **Web Service** → Connect your repository.
2. Configure settings:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
3. Under **Environment Variables**, add the variables listed in Section 3.
4. Click **Create Web Service**.

---

## 5. Frontend Deployment Options

### Option A: Unified Hosting (Render Serves Frontend Directly)
- FastAPI automatically serves `index.html` at the root path (`GET /`).
- **No extra setup needed**: The frontend uses relative URLs (e.g. `/news`), requiring zero CORS configuration.

### Option B: Decoupled Hosting (Vercel or Netlify)
If you prefer deploying the static frontend independently:
1. Deploy `index.html` to Vercel or Netlify.
2. In your Render Web Service dashboard, set:
   ```text
   FRONTEND_ORIGIN=https://your-site.vercel.app
   ```
3. In `index.html` (or via browser console / localStorage), configure the API base URL:
   ```javascript
   // Set either on window before scripts run, or in localStorage:
   localStorage.setItem('NEXUS_API_BASE', 'https://nexus-news-api.onrender.com');
   ```
   Or edit `index.html` line:
   ```javascript
   window.NEXUS_API_BASE = "https://nexus-news-api.onrender.com";
   ```

---

## 6. Health Checks & Verification

After deployment, verify that the service is operational:

1. **Lightweight Health Check**:
   ```bash
   curl -s https://nexus-news-api.onrender.com/health
   # Expected: {"status": "ok", "timestamp": "..."}
   ```
2. **Refresh & Database Status**:
   ```bash
   curl -s https://nexus-news-api.onrender.com/refresh-status
   # Expected: {"status": "idle", "is_fresh": true, ...}
   ```
3. **News Feed**:
   ```bash
   curl -s "https://nexus-news-api.onrender.com/news?limit=5"
   # Expected: {"status": "ok", "data": [...]}
   ```
4. **Categories Distribution**:
   ```bash
   curl -s https://nexus-news-api.onrender.com/categories
   # Expected: 6 canonical categories with counts
   ```

---

## 7. Disaster Recovery & Rollback

If MongoDB Atlas becomes unavailable and you need to perform an immediate rollback during maintenance:

1. **Rollback to Local SQLite**:
   - Set environment variable: `DB_BACKEND=sqlite`.
   - The application will automatically switch all database operations to `data/news.db`.
   - SQLite `data/news.db` remains 100% intact as the reference copy.
2. **Return to MongoDB Atlas**:
   - Set environment variable: `DB_BACKEND=mongodb`.
   - The application resumes normal cloud operations against Atlas.
