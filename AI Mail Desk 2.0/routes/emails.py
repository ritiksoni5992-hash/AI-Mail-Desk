"""
Email routes: list, detail, mark read/unread, star, archive, snooze, delete, send
"""
from flask import Blueprint, request, jsonify, session
from flask_login import login_required, current_user
from extensions import db
from models import Email, ActivityLog
from services.email_client import fetch_emails, send_email, categorize_email
from datetime import datetime, timedelta

emails_bp = Blueprint("emails", __name__)



# ── List & filter ─────────────────────────────────────────────────────────────

@emails_bp.route("/", methods=["GET"])
@login_required
def list_emails():
    q = Email.query.filter_by(account_id=current_user.id, is_archived=False)

    # Filters
    status   = request.args.get("status")       # unread | read | starred | snoozed
    category = request.args.get("category")     # query | feedback | support | general
    date_range = request.args.get("date")       # today | week | month
    search   = request.args.get("q", "").strip()
    sort     = request.args.get("sort", "newest")
    limit    = int(request.args.get("limit", current_user.email_limit or 25))
    offset   = int(request.args.get("offset", 0))

    if status == "unread":
        q = q.filter_by(is_seen=False)
    elif status == "read":
        q = q.filter_by(is_seen=True)
    elif status == "starred":
        q = q.filter_by(is_starred=True)
    elif status == "snoozed":
        q = q.filter_by(is_snoozed=True)

    if category:
        q = q.filter_by(category=category)

    if date_range == "today":
        since = datetime.utcnow().replace(hour=0, minute=0, second=0)
        q = q.filter(Email.received_at >= since)
    elif date_range == "week":
        q = q.filter(Email.received_at >= datetime.utcnow() - timedelta(days=7))
    elif date_range == "month":
        q = q.filter(Email.received_at >= datetime.utcnow() - timedelta(days=30))

    if search:
        like = f"%{search}%"
        q = q.filter(
            (Email.sender_name.ilike(like)) |
            (Email.sender_email.ilike(like)) |
            (Email.subject.ilike(like)) |
            (Email.body_text.ilike(like))
        )

    if sort == "oldest":
        q = q.order_by(Email.received_at.asc())
    elif sort == "unread":
        q = q.order_by(Email.is_seen.asc(), Email.received_at.desc())
    elif sort == "cat":
        q = q.order_by(Email.category.asc(), Email.received_at.desc())
    else:  # newest
        q = q.order_by(Email.received_at.desc())

    total = q.count()
    emails = q.offset(offset).limit(limit).all()

    return jsonify({
        "total": total,
        "limit": limit,
        "offset": offset,
        "emails": [e.to_dict() for e in emails],
    })


# ── Detail ────────────────────────────────────────────────────────────────────

@emails_bp.route("/<int:email_id>", methods=["GET"])
@login_required
def get_email(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    # Auto-mark seen
    if not em.is_seen:
        em.is_seen = True
        db.session.commit()
    return jsonify(em.to_dict())


# ── Sync (manual trigger) ─────────────────────────────────────────────────────

@emails_bp.route("/sync", methods=["POST"])
@login_required
def sync():
    fetched = fetch_emails(current_user, limit=current_user.email_limit or 50)
    new_count = 0
    for data in fetched:
        if not Email.query.filter_by(message_id=data["message_id"]).first():
            em = Email(account_id=current_user.id, **data)
            db.session.add(em)
            new_count += 1
    current_user.last_sync = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "new": new_count})


# ── Mark seen / unseen ────────────────────────────────────────────────────────

@emails_bp.route("/<int:email_id>/seen", methods=["PATCH"])
@login_required
def mark_seen(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    data = request.get_json() or {}
    em.is_seen = data.get("seen", True)
    db.session.commit()
    return jsonify({"ok": True, "is_seen": em.is_seen})


@emails_bp.route("/mark-all-read", methods=["PATCH"])
@login_required
def mark_all_read():
    Email.query.filter_by(account_id=current_user.id, is_seen=False).update({"is_seen": True})
    db.session.commit()
    return jsonify({"ok": True})


# ── Star ──────────────────────────────────────────────────────────────────────

@emails_bp.route("/<int:email_id>/star", methods=["PATCH"])
@login_required
def star(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    em.is_starred = not em.is_starred
    db.session.commit()
    return jsonify({"ok": True, "is_starred": em.is_starred})


# ── Archive ───────────────────────────────────────────────────────────────────

@emails_bp.route("/<int:email_id>/archive", methods=["PATCH"])
@login_required
def archive(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    em.is_archived = True
    log = ActivityLog(account_id=current_user.id, action="archived",
                      description=f"Archived email: {em.subject[:60]}", email_id=em.id)
    db.session.add(log)
    db.session.commit()
    return jsonify({"ok": True})


# ── Snooze ────────────────────────────────────────────────────────────────────

@emails_bp.route("/<int:email_id>/snooze", methods=["PATCH"])
@login_required
def snooze(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    data = request.get_json() or {}
    hours = int(data.get("hours", 1))
    em.is_snoozed  = True
    em.snooze_until = datetime.utcnow() + timedelta(hours=hours)
    db.session.commit()
    return jsonify({"ok": True, "snooze_until": em.snooze_until.isoformat()})


# ── Category override ─────────────────────────────────────────────────────────

@emails_bp.route("/<int:email_id>/category", methods=["PATCH"])
@login_required
def update_category(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    data = request.get_json() or {}
    allowed = {"query", "feedback", "support", "general"}
    cat = data.get("category")
    if cat not in allowed:
        return jsonify({"ok": False, "error": "Invalid category"}), 400
    em.category = cat
    db.session.commit()
    return jsonify({"ok": True, "category": em.category})


# ── Delete ────────────────────────────────────────────────────────────────────

@emails_bp.route("/<int:email_id>", methods=["DELETE"])
@login_required
def delete_email(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    db.session.delete(em)
    db.session.commit()
    return jsonify({"ok": True})


# ── Send reply ────────────────────────────────────────────────────────────────

@emails_bp.route("/<int:email_id>/send-reply", methods=["POST"])
@login_required
def send_reply(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    data = request.get_json() or {}
    reply_body = data.get("body", em.ai_reply or "")

    if not reply_body:
        return jsonify({"ok": False, "error": "Reply body is empty"}), 400

    subject = f"Re: {em.subject}"
    ok = send_email(current_user, em.sender_email, subject, reply_body)
    if ok:
        em.reply_sent    = True
        em.reply_sent_at = datetime.utcnow()
        em.ai_reply      = reply_body
        log = ActivityLog(
            account_id=current_user.id, action="reply_sent",
            description=f"Reply sent to {em.sender_email} — {em.subject[:50]}",
            email_id=em.id,
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({"ok": True})
    else:
        return jsonify({"ok": False, "error": "SMTP send failed. Check credentials."}), 500


# ── Stats helper ──────────────────────────────────────────────────────────────

@emails_bp.route("/stats/counts", methods=["GET"])
@login_required
def counts():
    base = Email.query.filter_by(account_id=current_user.id, is_archived=False)
    return jsonify({
        "total":    base.count(),
        "unread":   base.filter_by(is_seen=False).count(),
        "query":    base.filter_by(category="query").count(),
        "feedback": base.filter_by(category="feedback").count(),
        "support":  base.filter_by(category="support").count(),
        "general":  base.filter_by(category="general").count(),
        "starred":  base.filter_by(is_starred=True).count(),
        "replied":  base.filter_by(reply_sent=True).count(),
    })
