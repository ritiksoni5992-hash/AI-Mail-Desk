"""
AI routes — Gemini Flash Vision powered endpoints
/api/ai/generate-reply/<id>     POST  — generate reply (+ optional image)
/api/ai/summarize/<id>          POST  — summarize email
/api/ai/reclassify/<id>         POST  — AI reclassify email
/api/ai/analyze-attachment/<id> POST  — vision analyze image attachment
/api/ai/templates/<id>          POST  — suggest 3 reply openers
/api/ai/test-key                POST  — validate Gemini API key
"""
import base64
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Email
from services.ai_service import (
    generate_reply,
    summarize_email,
    classify_email_ai,
    analyze_image_attachment,
    suggest_reply_templates,
    _gemini_generate,
    _get_api_key,
)

ai_bp = Blueprint("ai", __name__)


def _api_key_from_request() -> str:
    """Pull Gemini API key from JSON body or fall back to app config."""
    data = request.get_json(silent=True) or {}
    return data.get("api_key", "") or data.get("gemini_key", "")


# ── Generate reply ─────────────────────────────────────────────────────────────
@ai_bp.route("/generate-reply/<int:email_id>", methods=["POST"])
@login_required
def gen_reply(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}

    result = generate_reply(
        sender_name=em.sender_name or em.sender_email,
        sender_email=em.sender_email,
        subject=em.subject or "",
        body=em.body_text or "",
        category=em.category,
        sentiment=em.sentiment,
        tone=data.get("tone", current_user.ai_tone or "professional"),
        language=data.get("language", current_user.reply_language or "english"),
        company_name=data.get("company_name", "our company"),
        api_key=data.get("api_key", ""),
    )

    if result["success"]:
        em.ai_reply = result["reply"]
        db.session.commit()
        return jsonify({"ok": True, "reply": result["reply"]})
    return jsonify({"ok": False, "error": result["error"]}), 500


# ── Generate reply with image vision ──────────────────────────────────────────
@ai_bp.route("/generate-reply-vision/<int:email_id>", methods=["POST"])
@login_required
def gen_reply_vision(email_id):
    """
    Accepts multipart/form-data with optional 'image' file field.
    Uses Gemini Vision to analyze the image and incorporate it in the reply.
    """
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()

    tone     = request.form.get("tone", current_user.ai_tone or "professional")
    language = request.form.get("language", current_user.reply_language or "english")
    api_key  = request.form.get("api_key", "")

    image_b64  = None
    image_mime = "image/jpeg"

    image_file = request.files.get("image")
    if image_file:
        image_mime = image_file.mimetype or "image/jpeg"
        image_b64  = base64.b64encode(image_file.read()).decode("utf-8")

    result = generate_reply(
        sender_name=em.sender_name or em.sender_email,
        sender_email=em.sender_email,
        subject=em.subject or "",
        body=em.body_text or "",
        category=em.category,
        sentiment=em.sentiment,
        tone=tone,
        language=language,
        company_name=request.form.get("company_name", "our company"),
        api_key=api_key,
        attachment_b64=image_b64,
        attachment_mime=image_mime,
    )

    if result["success"]:
        em.ai_reply = result["reply"]
        db.session.commit()
        return jsonify({"ok": True, "reply": result["reply"]})
    return jsonify({"ok": False, "error": result["error"]}), 500


# ── Summarize ──────────────────────────────────────────────────────────────────
@ai_bp.route("/summarize/<int:email_id>", methods=["POST"])
@login_required
def summarize(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    result = summarize_email(
        body=em.body_text or "",
        subject=em.subject or "",
        api_key=data.get("api_key", ""),
    )
    if result["success"]:
        return jsonify({"ok": True, "summary": result["summary"]})
    return jsonify({"ok": False, "error": result.get("error")}), 500


# ── Reclassify ─────────────────────────────────────────────────────────────────
@ai_bp.route("/reclassify/<int:email_id>", methods=["POST"])
@login_required
def reclassify(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    result = classify_email_ai(
        subject=em.subject or "",
        body=em.body_text or "",
        api_key=data.get("api_key", ""),
    )
    em.category  = result.get("category",  em.category)
    em.sentiment = result.get("sentiment", em.sentiment)
    em.priority  = result.get("priority",  em.priority)
    db.session.commit()
    return jsonify({
        "ok": True,
        "category":  em.category,
        "sentiment": em.sentiment,
        "priority":  em.priority,
    })


# ── Analyze image attachment (vision) ─────────────────────────────────────────
@ai_bp.route("/analyze-attachment/<int:email_id>", methods=["POST"])
@login_required
def analyze_attachment(email_id):
    """
    Accepts multipart/form-data with 'image' file field.
    Uses Gemini Vision to describe the image content.
    """
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()

    image_file = request.files.get("image")
    if not image_file:
        return jsonify({"ok": False, "error": "No image file provided."}), 400

    image_mime = image_file.mimetype or "image/jpeg"
    image_b64  = base64.b64encode(image_file.read()).decode("utf-8")
    api_key    = request.form.get("api_key", "")

    result = analyze_image_attachment(
        image_b64=image_b64,
        image_mime=image_mime,
        email_context=f"{em.subject}: {(em.body_text or '')[:200]}",
        api_key=api_key,
    )

    if result["success"]:
        return jsonify({"ok": True, "analysis": result["analysis"]})
    return jsonify({"ok": False, "error": result["error"]}), 500


# ── Reply template suggestions ─────────────────────────────────────────────────
@ai_bp.route("/templates/<int:email_id>", methods=["POST"])
@login_required
def templates(email_id):
    em = Email.query.filter_by(id=email_id, account_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    result = suggest_reply_templates(
        category=em.category,
        sentiment=em.sentiment,
        api_key=data.get("api_key", ""),
    )
    if result["success"]:
        return jsonify({"ok": True, "templates": result["templates"]})
    return jsonify({"ok": False, "error": result.get("error")}), 500


# ── Test Gemini API key ────────────────────────────────────────────────────────
@ai_bp.route("/test-key", methods=["POST"])
@login_required
def test_key():
    data = request.get_json(silent=True) or {}
    key = data.get("api_key", "")
    if not key:
        return jsonify({"ok": False, "error": "API key is required."}), 400

    result = _gemini_generate(
        prompt="Reply with exactly: OK",
        api_key=key,
        max_tokens=5,
    )
    if result["success"]:
        return jsonify({"ok": True, "message": "Gemini API key is valid ✓"})
    return jsonify({"ok": False, "error": result["error"]}), 400
