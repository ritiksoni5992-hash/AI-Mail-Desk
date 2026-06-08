"""
Database models for MailDesk AI
"""
from extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class Account(db.Model, UserMixin):
    """Email account / user record"""
    __tablename__ = "accounts"

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)  # app password hash
    # Raw credentials stored encrypted for IMAP/SMTP (simplified: store as-is for demo)
    imap_host     = db.Column(db.String(255), default="imap.gmail.com")
    imap_port     = db.Column(db.Integer, default=993)
    smtp_host     = db.Column(db.String(255), default="smtp.gmail.com")
    smtp_port     = db.Column(db.Integer, default=587)
    provider      = db.Column(db.String(64), default="gmail")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_sync     = db.Column(db.DateTime, nullable=True)

    # AI Settings
    gemini_api_key  = db.Column(db.String(512), default="")   # stored per-account (optional)
    ai_tone         = db.Column(db.String(32), default="professional")
    reply_language  = db.Column(db.String(32), default="english")
    auto_draft      = db.Column(db.Boolean, default=True)
    require_approval= db.Column(db.Boolean, default=True)
    sync_interval   = db.Column(db.Integer, default=5)  # minutes
    email_limit     = db.Column(db.Integer, default=25)
    auto_archive_days= db.Column(db.Integer, default=30)

    # Notification flags
    notif_new       = db.Column(db.Boolean, default=True)
    notif_negative  = db.Column(db.Boolean, default=True)
    notif_digest    = db.Column(db.Boolean, default=False)
    notif_sla       = db.Column(db.Boolean, default=True)

    emails = db.relationship("Email", backref="account", lazy="dynamic", cascade="all, delete")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def get_raw_password(self) -> str:
        """Retrieve raw IMAP password from Flask session."""
        try:
            from flask import session
            return session.get("raw_password", "")
        except RuntimeError:
            return getattr(self, "_raw_password_cache", "")

    def set_raw_password_cache(self, pw: str):
        """Cache raw password on instance for background jobs."""
        self._raw_password_cache = pw

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "provider": self.provider,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "gemini_api_key": "***" if self.gemini_api_key else "",
            "ai_tone": self.ai_tone,
            "reply_language": self.reply_language,
            "auto_draft": self.auto_draft,
            "require_approval": self.require_approval,
            "sync_interval": self.sync_interval,
            "email_limit": self.email_limit,
            "auto_archive_days": self.auto_archive_days,
            "notif_new": self.notif_new,
            "notif_negative": self.notif_negative,
            "notif_digest": self.notif_digest,
            "notif_sla": self.notif_sla,
        }


@login_manager.user_loader
def load_user(user_id):
    return Account.query.get(int(user_id))


class Email(db.Model):
    """Individual email record"""
    __tablename__ = "emails"

    id          = db.Column(db.Integer, primary_key=True)
    account_id  = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    message_id  = db.Column(db.String(512), unique=True, nullable=False)
    sender_name = db.Column(db.String(255))
    sender_email= db.Column(db.String(255), nullable=False)
    subject     = db.Column(db.String(1000))
    body_text   = db.Column(db.Text)
    body_html   = db.Column(db.Text)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_seen     = db.Column(db.Boolean, default=False)
    is_starred  = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    is_snoozed  = db.Column(db.Boolean, default=False)
    snooze_until= db.Column(db.DateTime, nullable=True)
    category    = db.Column(db.String(32), default="general")  # query/feedback/support/general
    sentiment   = db.Column(db.String(16), default="neutral")  # positive/negative/neutral
    priority    = db.Column(db.String(16), default="normal")   # high/normal/low
    ai_reply    = db.Column(db.Text, nullable=True)
    reply_sent  = db.Column(db.Boolean, default=False)
    reply_sent_at= db.Column(db.DateTime, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "sender_name": self.sender_name,
            "sender_email": self.sender_email,
            "subject": self.subject,
            "body_text": self.body_text,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "is_seen": self.is_seen,
            "is_starred": self.is_starred,
            "is_archived": self.is_archived,
            "is_snoozed": self.is_snoozed,
            "snooze_until": self.snooze_until.isoformat() if self.snooze_until else None,
            "category": self.category,
            "sentiment": self.sentiment,
            "priority": self.priority,
            "ai_reply": self.ai_reply,
            "reply_sent": self.reply_sent,
            "reply_sent_at": self.reply_sent_at.isoformat() if self.reply_sent_at else None,
        }


class ActivityLog(db.Model):
    """Activity log for dashboard feed"""
    __tablename__ = "activity_logs"

    id         = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    action     = db.Column(db.String(64))   # reply_sent / email_received / archived / etc.
    description= db.Column(db.String(512))
    email_id   = db.Column(db.Integer, db.ForeignKey("emails.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }
