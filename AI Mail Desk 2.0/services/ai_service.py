"""
AI service — Google Gemini Flash Vision API
Handles: reply generation, email summarization, classification, image/attachment analysis
Uses urllib (no SDK) so no extra pip install needed.
"""
import logging
import json
import re
import urllib.request
import urllib.error
import os

logger = logging.getLogger(__name__)

# ── Tone & context maps ────────────────────────────────────────────────────────
TONE_INSTRUCTIONS = {
    "professional": "professional, polite, and clear",
    "friendly":     "warm, friendly, and approachable",
    "formal":       "formal, structured, and precise",
    "concise":      "concise and to-the-point, no unnecessary words",
}

CATEGORY_CONTEXT = {
    "query":    "The customer is asking a question or making an inquiry. Provide a helpful, complete answer.",
    "feedback": "The customer is sharing feedback (positive or negative). Acknowledge it genuinely and personally.",
    "support":  "The customer has a technical issue or needs urgent help. Be empathetic and solution-focused.",
    "general":  "General email — respond helpfully and route to the right team if needed.",
}


def _get_api_key(override: str = "") -> str:
    """Get Gemini API key from override → Flask app config → env var."""
    if override:
        return override
    try:
        from flask import current_app
        key = current_app.config.get("GEMINI_API_KEY", "")
        if key:
            return key
    except RuntimeError:
        pass
    return os.environ.get("GEMINI_API_KEY", "")


def _gemini_generate(
    prompt: str,
    api_key: str,
    image_b64: str = None,
    image_mime: str = "image/jpeg",
    max_tokens: int = 800,
) -> dict:
    """
    Core Gemini 3.0 Flash Vision API call via urllib (no google-generativeai SDK needed).
    Supports optional inline base64 image for vision tasks.
    Returns: {success: bool, text: str, error: str|None}
    """
    model = "gemini-3-flash-preview"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )

    # Build content parts — image first (if any), then text
    parts = []
    if image_b64:
        parts.append({
            "inline_data": {
                "mime_type": image_mime,
                "data": image_b64,
            }
        })
    parts.append({"text": prompt})

    payload = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.7,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",        "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",  "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",  "threshold": "BLOCK_NONE"},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                return {"success": False, "text": "", "error": "Gemini returned no candidates."}
            text = candidates[0]["content"]["parts"][0]["text"].strip()
            return {"success": True, "text": text, "error": None}

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"Gemini HTTP {e.code}: {body}")
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except Exception:
            msg = body
        return {"success": False, "text": "", "error": f"Gemini API error {e.code}: {msg}"}

    except urllib.error.URLError as e:
        logger.error(f"Gemini URL error: {e}")
        return {"success": False, "text": "", "error": f"Network error: {e.reason}"}

    except Exception as e:
        logger.error(f"Gemini unexpected error: {e}")
        return {"success": False, "text": "", "error": str(e)}


# ── Public AI functions ────────────────────────────────────────────────────────

def generate_reply(
    sender_name: str,
    sender_email: str,
    subject: str,
    body: str,
    category: str = "general",
    sentiment: str = "neutral",
    tone: str = "professional",
    language: str = "english",
    company_name: str = "our company",
    api_key: str = "",
    attachment_b64: str = None,
    attachment_mime: str = "image/jpeg",
) -> dict:
    """
    Generate a customer reply using Gemini Flash Vision.
    Optionally accepts a base64-encoded image attachment for visual context.
    Returns: {success: bool, reply: str, error: str|None}
    """
    key = _get_api_key(api_key)
    if not key:
        return {
            "success": False, "reply": "",
            "error": "No Gemini API key configured. Add it in Settings.",
        }

    tone_desc   = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["professional"])
    cat_context = CATEGORY_CONTEXT.get(category, CATEGORY_CONTEXT["general"])
    lang_note   = (
        f"Write the reply in {language}."
        if language.lower() not in ("english", "auto") else ""
    )
    vision_note = (
        "\nNote: A customer image/screenshot is included above — reference it if relevant to their issue."
        if attachment_b64 else ""
    )

    prompt = f"""You are a customer support agent for {company_name}.

Email context:
- From: {sender_name} <{sender_email}>
- Subject: {subject}
- Category: {category} — {cat_context}
- Sentiment: {sentiment}
- Tone required: {tone_desc}
{lang_note}{vision_note}

Customer's email:
\"\"\"
{body}
\"\"\"

Write a complete, ready-to-send reply. Follow these rules:
1. Greet the customer by first name if identifiable.
2. Acknowledge their specific concern — never be generic.
3. Address every point they raised.
4. If sentiment is negative, lead with genuine empathy first.
5. If a screenshot/image is provided, reference what you see in it.
6. Close with a professional sign-off.
7. Do NOT include a Subject line — body only.
8. max 500 words. Plain text, no markdown.

Write only the reply body:"""

    result = _gemini_generate(
        prompt=prompt,
        api_key=key,
        image_b64=attachment_b64,
        image_mime=attachment_mime,
        max_tokens=600,
    )

    if result["success"]:
        return {"success": True, "reply": result["text"], "error": None}
    return {"success": False, "reply": "", "error": result["error"]}


def summarize_email(body: str, subject: str = "", api_key: str = "") -> dict:
    """
    Summarize an email in 1–2 sentences.
    Returns: {success: bool, summary: str, error: str|None}
    """
    key = _get_api_key(api_key)
    if not key:
        return {"success": False, "summary": "", "error": "No Gemini API key configured."}

    prompt = f"""Summarize this customer email in 1–2 clear sentences. Capture the core request or concern.

Subject: {subject}
Body:
{body[:1500]}

Return only the summary, no labels or preamble:"""

    result = _gemini_generate(prompt=prompt, api_key=key, max_tokens=150)
    if result["success"]:
        return {"success": True, "summary": result["text"], "error": None}
    return {"success": False, "summary": "", "error": result["error"]}


def classify_email_ai(subject: str, body: str, api_key: str = "") -> dict:
    """
    AI-powered email classification using Gemini Flash.
    Returns: {category, sentiment, priority}
    """
    key = _get_api_key(api_key)
    if not key:
        return {"category": "general", "sentiment": "neutral", "priority": "normal"}

    prompt = f"""Classify this customer email. Return ONLY a JSON object — no explanation, no markdown fences.

Keys:
- "category": "query" | "feedback" | "support" | "general"
- "sentiment": "positive" | "negative" | "neutral"
- "priority": "high" | "normal" | "low"

Subject: {subject}
Body: {body[:800]}

JSON only:"""

    result = _gemini_generate(prompt=prompt, api_key=key, max_tokens=80)
    if result["success"]:
        try:
            text = re.sub(r"```(?:json)?|```", "", result["text"]).strip()
            parsed = json.loads(text)
            # Validate values
            valid_cats  = {"query", "feedback", "support", "general"}
            valid_sents = {"positive", "negative", "neutral"}
            valid_pris  = {"high", "normal", "low"}
            return {
                "category":  parsed.get("category",  "general")  if parsed.get("category")  in valid_cats  else "general",
                "sentiment": parsed.get("sentiment", "neutral")  if parsed.get("sentiment") in valid_sents else "neutral",
                "priority":  parsed.get("priority",  "normal")   if parsed.get("priority")  in valid_pris  else "normal",
            }
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning(f"Gemini classification parse failed: {result['text']}")
    return {"category": "general", "sentiment": "neutral", "priority": "normal"}


def analyze_image_attachment(
    image_b64: str,
    image_mime: str = "image/jpeg",
    email_context: str = "",
    api_key: str = "",
) -> dict:
    """
    Use Gemini Vision to analyze an image/screenshot attachment.
    Returns: {success: bool, analysis: str, error: str|None}
    """
    key = _get_api_key(api_key)
    if not key:
        return {"success": False, "analysis": "", "error": "No Gemini API key configured."}

    prompt = f"""You are analyzing an image attachment sent by a customer in a support email.
{f'Email context: {email_context}' if email_context else ''}

Describe what you see in 2–6 sentences. Focus on:
- What the image shows (product photo, error screenshot, document, receipt, etc.)
- Any visible errors, defects, damage, or issues
- Key text/numbers visible (error codes, order numbers, amounts)

Be factual and concise — this helps a support agent respond appropriately."""

    result = _gemini_generate(
        prompt=prompt, api_key=key,
        image_b64=image_b64, image_mime=image_mime,
        max_tokens=550,
    )
    if result["success"]:
        return {"success": True, "analysis": result["text"], "error": None}
    return {"success": False, "analysis": "", "error": result["error"]}


def suggest_reply_templates(category: str, sentiment: str, api_key: str = "") -> dict:
    """
    Generate 3 short reply opening templates for quick selection.
    Returns: {success: bool, templates: list[str], error: str|None}
    """
    key = _get_api_key(api_key)
    if not key:
        return {"success": False, "templates": [], "error": "No Gemini API key configured."}

    prompt = f"""Generate exactly 3 short opening sentence templates for a customer support reply.
Category: {category}, Sentiment: {sentiment}

Each must be a single sentence suitable as the opening line of a reply.
Return ONLY a JSON array of 3 strings. No other text.
Example: ["Thank you for reaching out!", "I'm sorry to hear about...", "We appreciate your feedback."]"""

    result = _gemini_generate(prompt=prompt, api_key=key, max_tokens=200)
    if result["success"]:
        try:
            text = re.sub(r"```(?:json)?|```", "", result["text"]).strip()
            templates = json.loads(text)
            if isinstance(templates, list):
                return {"success": True, "templates": templates[:3], "error": None}
        except Exception:
            pass
    return {"success": False, "templates": [], "error": result.get("error", "Parse error")}
