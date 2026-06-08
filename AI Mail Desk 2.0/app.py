"""
MailDesk AI — Flask Email Management Application
"""
from flask import Flask
from extensions import db, login_manager, scheduler
import os


def create_app():
    app = Flask(__name__)

    # Config
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///maildesk.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")

    # Extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.setup"

    # Blueprints
    from routes.auth import auth_bp
    from routes.emails import emails_bp
    from routes.ai import ai_bp
    from routes.dashboard import dashboard_bp
    from routes.settings_routes import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(emails_bp, url_prefix="/api/emails")
    app.register_blueprint(ai_bp, url_prefix="/api/ai")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(settings_bp, url_prefix="/api/settings")

    # DB Init
    with app.app_context():
        db.create_all()

    # Background Sync
    if not scheduler.running:
        from services.email_client import sync_all_accounts
        scheduler.add_job(
            func=sync_all_accounts,
            args=[app],
            trigger="interval",
            minutes=5,
            id="email_sync",
            replace_existing=True,
        )
        scheduler.start()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
