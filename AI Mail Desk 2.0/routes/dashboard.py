"""
Dashboard summary routes
"""
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from models import Email, ActivityLog
from datetime import datetime, timedelta
from collections import Counter
import re

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/summary", methods=["GET"])
@login_required
def summary():
    aid = current_user.id
    base = Email.query.filter_by(account_id=aid, is_archived=False)

    total    = base.count()
    unread   = base.filter_by(is_seen=False).count()
    replied  = base.filter_by(reply_sent=True).count()
    pending  = total - replied

    # Category breakdown
    cats = {}
    for cat in ["query", "feedback", "support", "general"]:
        cats[cat] = Email.query.filter_by(account_id=aid, category=cat, is_archived=False).count()

    # Sentiment
    sentiments = {
        "positive": Email.query.filter_by(account_id=aid, sentiment="positive").count(),
        "negative": Email.query.filter_by(account_id=aid, sentiment="negative").count(),
        "neutral":  Email.query.filter_by(account_id=aid, sentiment="neutral").count(),
    }

    # Response rate
    response_rate = round((replied / total * 100) if total else 0, 1)

    # Avg response time (from received_at to reply_sent_at)
    replied_emails = Email.query.filter(
        Email.account_id == aid,
        Email.reply_sent == True,
        Email.reply_sent_at != None,
    ).all()
    if replied_emails:
        deltas = [
            (e.reply_sent_at - e.received_at).total_seconds() / 3600
            for e in replied_emails
            if e.reply_sent_at and e.received_at
        ]
        avg_response_hrs = round(sum(deltas) / len(deltas), 1) if deltas else 0
    else:
        avg_response_hrs = 0

    # Daily counts for last 7 days
    daily = []
    for i in range(6, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end   = start + timedelta(days=1)
        count = Email.query.filter(
            Email.account_id == aid,
            Email.received_at >= start,
            Email.received_at < end,
        ).count()
        daily.append({"date": start.strftime("%a"), "count": count})

    # Top keywords (simple word frequency from subjects)
    subjects = [e.subject or "" for e in Email.query.filter_by(account_id=aid).all()]
    all_words = re.findall(r"\b[a-z]{4,}\b", " ".join(subjects).lower())
    stopwords = {"this", "that", "with", "from", "have", "your", "will", "been", "they", "what", "just", "also", "more"}
    filtered  = [w for w in all_words if w not in stopwords]
    top_keywords = [{"word": w, "count": c} for w, c in Counter(filtered).most_common(10)]

    # Recent activity
    activity = ActivityLog.query.filter_by(account_id=aid).order_by(
        ActivityLog.created_at.desc()
    ).limit(10).all()

    # Smart suggestions
    suggestions = []
    if unread > 5:
        suggestions.append(f"You have {unread} unread emails — consider processing them soon.")
    neg = Email.query.filter_by(account_id=aid, sentiment="negative", reply_sent=False).count()
    if neg:
        suggestions.append(f"{neg} negative email(s) need urgent attention.")
    if response_rate < 70:
        suggestions.append(f"Response rate is {response_rate}% — use AI replies to improve.")
    if avg_response_hrs > 4:
        suggestions.append(f"Average response time is {avg_response_hrs}h — aim for under 2h.")

    return jsonify({
        "total":            total,
        "unread":           unread,
        "replied":          replied,
        "pending":          pending,
        "response_rate":    response_rate,
        "avg_response_hrs": avg_response_hrs,
        "categories":       cats,
        "sentiments":       sentiments,
        "daily_counts":     daily,
        "top_keywords":     top_keywords,
        "activity":         [a.to_dict() for a in activity],
        "suggestions":      suggestions,
        "last_sync":        current_user.last_sync.isoformat() if current_user.last_sync else None,
    })
