"""
Auth routes: /setup  /login  /logout
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import Account
from services.email_client import test_connection

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("auth.inbox"))
    return redirect(url_for("auth.setup"))


@auth_bp.route("/setup")
def setup():
    if current_user.is_authenticated:
        return redirect(url_for("auth.inbox"))
    return render_template("setup.html")


@auth_bp.route("/inbox")
@login_required
def inbox():
    return render_template("app.html", account=current_user)


@auth_bp.route("/api/auth/connect", methods=["POST"])
def connect():
    """Test credentials and create/login account."""
    data = request.get_json()
    email     = data.get("email", "").strip().lower()
    password  = data.get("password", "").strip()
    imap_host = data.get("imap_host", "imap.gmail.com")
    imap_port = int(data.get("imap_port", 993))
    smtp_host = data.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(data.get("smtp_port", 587))
    provider  = data.get("provider", "gmail")

    if not email or not password:
        return jsonify({"ok": False, "error": "Email and password are required."}), 400

    # Test IMAP connection
    result = test_connection(email, password, imap_host, imap_port)
    if not result["ok"]:
        return jsonify({"ok": False, "error": f"IMAP connection failed: {result['error']}"}), 400

    # Find or create account
    account = Account.query.filter_by(email=email).first()
    if not account:
        account = Account(
            email=email,
            imap_host=imap_host, imap_port=imap_port,
            smtp_host=smtp_host, smtp_port=smtp_port,
            provider=provider,
        )
        db.session.add(account)

    account.set_password(password)
    account.imap_host = imap_host
    account.imap_port = imap_port
    account.smtp_host = smtp_host
    account.smtp_port = smtp_port
    account.provider  = provider
    db.session.commit()

    # Store raw password in session for IMAP (in production: encrypt)
    session["raw_password"] = password
    account.set_raw_password_cache(password)

    login_user(account, remember=True)
    return jsonify({"ok": True, "redirect": url_for("auth.inbox")})


@auth_bp.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    session.pop("raw_password", None)
    logout_user()
    return jsonify({"ok": True, "redirect": url_for("auth.setup")})


@auth_bp.route("/api/auth/me")
@login_required
def me():
    return jsonify(current_user.to_dict())
