# MailDesk AI — Flask Email Management App
### Powered by Google Gemini 2.0 Flash Vision API

AI-powered email management: smart categorization, Gemini Vision replies,
summary dashboard, IMAP/SMTP integration.

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set environment variables
```bash
export SECRET_KEY="your-secret-key-here"
export GEMINI_API_KEY="AIzaSy..."       # Google Gemini API key
# Optional PostgreSQL:
# export DATABASE_URL="postgresql://user:pass@localhost/maildesk"
```

### 3. Run
```bash
python app.py
```
Open: http://localhost:5000

---

## 📁 Project Structure

```
maildesk/
├── app.py                    # Flask app factory + scheduler
├── extensions.py             # db, login_manager, scheduler
├── models.py                 # Account, Email, ActivityLog
├── requirements.txt
├── routes/
│   ├── auth.py               # Setup / connect / logout
│   ├── emails.py             # CRUD, sync, filter, send reply
│   ├── ai.py                 # Gemini Flash Vision endpoints
│   ├── dashboard.py          # Summary stats
│   └── settings_routes.py   # Settings CRUD
├── services/
│   ├── email_client.py       # IMAP / SMTP / categorization
│   └── ai_service.py         # Gemini 2.0 Flash Vision (urllib, no SDK)
├── templates/
│   ├── setup.html            # Account connection screen
│   └── app.html              # Main app UI
└── static/
    ├── css/style.css
    └── js/app.js
```

---

## ✨ Features

### 🔗 Setup Dashboard
- Email + app password entry
- Provider presets (Gmail, Outlook, Yahoo, Zoho, Custom)
- IMAP/SMTP auto-fill + live connection test before saving

### 📬 Inbox
- Live IMAP sync with background scheduler (every 5 min)
- Seen / Unseen dot indicators
- Category badges: Query | Feedback | Support | General
- Priority badges: 🔴 Urgent
- 3-dot slide menu: Mark read, Generate AI reply, Move category, Star, Snooze, Archive
- Search across sender/subject/body
- Sidebar filters: Status, Date range, Email limit slider

### 🤖 Gemini 2.0 Flash Vision AI
- **Generate reply** — context-aware reply for any email category/sentiment
- **Vision reply** — attach a customer screenshot; Gemini analyzes it and references it in the reply
- **Summarize** — 1–2 sentence email summary
- **Reclassify** — AI re-categorizes category/sentiment/priority
- **Analyze attachment** — describe any image the customer sent
- **Template suggestions** — 3 quick reply openers to start editing from
- **Test API key** — validate Gemini key in Settings before using

### 📊 Summary Dashboard
- Total / Unread / AI Replied / Pending counts
- Response rate % + avg response time
- Category breakdown bar chart
- Daily email volume chart (last 7 days)
- Activity feed + top keywords + smart suggestions

### ⚙️ Settings
- Gemini API key (stored in DB + tested via button)
- AI tone: Professional / Friendly / Formal / Concise
- Reply language: English / Hindi / Auto-detect
- Auto-draft & approval toggles
- Sync frequency, email limit, auto-archive
- Notification toggles: new email, negative flag, SLA breach, daily digest

---

## 🔐 Gmail App Password Setup
1. Enable 2-Step Verification on Google Account
2. Visit: https://myaccount.google.com/apppasswords
3. Create App Password → "Mail"
4. Use the 16-char password in MailDesk Setup

## 🔑 Get Gemini API Key
1. Visit: https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Paste in MailDesk Settings → Gemini API key → Test

---

## 🔧 Environment Variables

| Variable        | Description              | Default            |
|-----------------|--------------------------|--------------------|
| `SECRET_KEY`    | Flask session secret     | dev-secret         |
| `GEMINI_API_KEY`| Google Gemini API key    | (empty)            |
| `DATABASE_URL`  | SQLAlchemy DB URL        | sqlite:///maildesk.db |

The Gemini API key can also be set directly in the Settings page.
