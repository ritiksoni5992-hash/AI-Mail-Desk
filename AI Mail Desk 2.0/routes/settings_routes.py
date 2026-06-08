"""
Settings routes
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from extensions import db

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/", methods=["GET"])
@login_required
def get_settings():
    return jsonify(current_user.to_dict())


@settings_bp.route("/", methods=["PATCH"])
@login_required
def update_settings():
    data = request.get_json() or {}
    allowed = [
        "gemini_api_key",
        "ai_tone", "reply_language", "auto_draft", "require_approval",
        "sync_interval", "email_limit", "auto_archive_days",
        "notif_new", "notif_negative", "notif_digest", "notif_sla",
    ]
    for key in allowed:
        if key in data:
            setattr(current_user, key, data[key])
    db.session.commit()
    return jsonify({"ok": True, "settings": current_user.to_dict()})
