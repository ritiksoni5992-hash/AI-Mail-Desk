"""
Email client service — IMAP fetch + SMTP send + categorization
"""
import imaplib
import smtplib
import email as email_lib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# ── Categorization ─────────────────────────────────────────────────────────────

CATEGORY_RULES = {
    "query": [
        r"\b(how|what|when|where|why|can you|could you|do you|is it|are you|"
        r"price|pricing|cost|availability|available|information|info|details|"
        r"question|inquiry|enquiry|clarif|explain)\b"
    ],
    "feedback": [
        r"\b(feedback|review|rating|complaint|complain|disappointed|unhappy|"
        r"happy|pleased|satisfied|dissatisfied|terrible|excellent|amazing|"
        r"great service|poor service|experience|suggest|improvement)\b"
    ],
    "support": [
        r"\b(help|support|issue|problem|error|bug|not working|broken|fail|"
        r"cannot|can't|unable|trouble|stuck|urgent|asap|immediately|"
        r"login|password|access|account|payment|charge|refund|cancel)\b"
    ],
}

SENTIMENT_RULES = {
    "positive": r"\b(great|excellent|amazing|love|happy|pleased|thank|wonderful|fantastic|good)\b",
    "negative": r"\b(terrible|awful|horrible|disappointed|angry|frustrated|unacceptable|worst|bad|poor|complaint)\b",
}

PRIORITY_RULES = {
    "high": r"\b(urgent|asap|immediately|critical|emergency|important|priority|deadline)\b",
}


def categorize_email(subject: str, body: str) -> dict:
    """Return category, sentiment, priority from subject+body text."""
    text = f"{subject} {body}".lower()

    category = "general"
    for cat, patterns in CATEGORY_RULES.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                category = cat
                break
        if category != "general":
            break

    sentiment = "neutral"
    for sent, pattern in SENTIMENT_RULES.items():
        if re.search(pattern, text, re.IGNORECASE):
            sentiment = sent
            break

    priority = "normal"
    if re.search(PRIORITY_RULES["high"], text, re.IGNORECASE):
        priority = "high"

    return {"category": category, "sentiment": sentiment, "priority": priority}


# ── IMAP helpers ───────────────────────────────────────────────────────────────

def _decode_header_value(value: str) -> str:
    """Decode encoded email header."""
    if not value:
        return ""
    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _get_body(msg) -> tuple:
    """Extract plain text and HTML body from email message."""
    body_text, body_html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain" and not body_text:
                body_text = decoded
            elif ctype == "text/html" and not body_html:
                body_html = decoded
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body_text = payload.decode(charset, errors="replace")
    return body_text.strip(), body_html.strip()


def fetch_emails(account, limit: int = 50) -> list:
    """
    Connect to IMAP, fetch recent emails, return list of dicts.
    account: models.Account instance with imap_host/port/email/password_hash
    NOTE: For IMAP we need the raw app password. In production store it
    encrypted (e.g. Fernet). Here we keep it simple.
    """
    results = []
    try:
        mail = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
        # Use the stored raw password (in production: decrypt first)
        mail.login(account.email, account.get_raw_password())
        mail.select("INBOX")

        # Search all emails, newest first
        status, data = mail.search(None, "ALL")
        if status != "OK":
            return results

        msg_ids = data[0].split()
        msg_ids = msg_ids[-limit:]  # take last N
        msg_ids.reverse()           # newest first

        for num in msg_ids:
            status, msg_data = mail.fetch(num, "(RFC822 FLAGS)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            flags = str(msg_data[0][0])
            is_seen = "\\Seen" in flags

            msg = email_lib.message_from_bytes(raw_email)
            subject = _decode_header_value(msg.get("Subject", "(no subject)"))
            from_raw = _decode_header_value(msg.get("From", ""))
            message_id = msg.get("Message-ID", f"fallback-{num.decode()}")
            date_str = msg.get("Date", "")

            # Parse sender name/email
            match = re.match(r"(.+?)\s*<(.+?)>", from_raw)
            if match:
                sender_name = match.group(1).strip().strip('"')
                sender_email = match.group(2).strip()
            else:
                sender_name = from_raw
                sender_email = from_raw

            body_text, body_html = _get_body(msg)
            meta = categorize_email(subject, body_text)

            # Parse date
            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(date_str)
            except Exception:
                received_at = datetime.utcnow()

            results.append({
                "message_id": message_id.strip(),
                "sender_name": sender_name,
                "sender_email": sender_email,
                "subject": subject,
                "body_text": body_text,
                "body_html": body_html,
                "received_at": received_at,
                "is_seen": is_seen,
                **meta,
            })

        mail.logout()
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP error for {account.email}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching emails for {account.email}: {e}")

    return results


def send_email(account, to_email: str, subject: str, body: str) -> bool:
    """Send a reply via SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = account.email
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(account.smtp_host, account.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(account.email, account.get_raw_password())
            server.sendmail(account.email, [to_email], msg.as_string())
        return True
    except Exception as e:
        logger.error(f"SMTP send error: {e}")
        return False


def test_connection(email: str, password: str, imap_host: str, imap_port: int) -> dict:
    """Test IMAP credentials. Returns {ok: bool, error: str}."""
    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(email, password)
        mail.logout()
        return {"ok": True, "error": None}
    except imaplib.IMAP4.error as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def sync_all_accounts(app):
    """Background job: sync emails for all accounts."""
    with app.app_context():
        from models import Account, Email, ActivityLog
        from extensions import db

        accounts = Account.query.all()
        for account in accounts:
            if not account.get_raw_password():
                continue
            fetched = fetch_emails(account, limit=account.email_limit or 50)
            new_count = 0
            for data in fetched:
                exists = Email.query.filter_by(message_id=data["message_id"]).first()
                if not exists:
                    em = Email(account_id=account.id, **data)
                    db.session.add(em)
                    new_count += 1
                    if data.get("sentiment") == "negative":
                        log = ActivityLog(
                            account_id=account.id,
                            action="negative_flagged",
                            description=f"Negative feedback flagged from {data['sender_email']}",
                        )
                        db.session.add(log)

            account.last_sync = datetime.utcnow()
            if new_count:
                log = ActivityLog(
                    account_id=account.id,
                    action="sync",
                    description=f"Synced {new_count} new email(s)",
                )
                db.session.add(log)
            db.session.commit()
            logger.info(f"Synced {new_count} new emails for {account.email}")
