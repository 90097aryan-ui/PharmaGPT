"""
app.py — Flask application factory for PharmaGPT.

Responsibilities
----------------
1. Create and configure the Flask application object.
2. Register all route blueprints from the routes/ package.
3. Initialise the SQLite database tables.
4. Serve the single-page application shell at /.

Application logic is distributed across the routes/ package.
Shared runtime state (Gemini client, history cache) lives in state.py.
"""

import uuid
from flask import Flask, jsonify, render_template, session

from pharmagpt.config import FLASK_SECRET_KEY, FLASK_DEBUG, FLASK_PORT, MAX_FILE_SIZE
from pharmagpt.logging_config import configure_logging
from pharmagpt import database as db
from pharmagpt.auth import register_auth_middleware

configure_logging()

from pharmagpt.routes.auth           import bp as auth_bp
from pharmagpt.routes.projects       import bp as projects_bp
from pharmagpt.routes.chat           import bp as chat_bp
from pharmagpt.routes.docs           import bp as docs_bp
from pharmagpt.routes.validation     import bp as validation_bp
from pharmagpt.routes.knowledge_base import bp as kb_bp
from pharmagpt.routes.dashboard      import bp as dashboard_bp
from pharmagpt.routes.risk           import bp as risk_bp
from pharmagpt.routes.urs            import bp as urs_bp
from pharmagpt.routes.qual           import bp as qual_bp
from pharmagpt.routes.report         import bp as report_bp
from pharmagpt.routes.qms_common     import bp as qms_common_bp
from pharmagpt.routes.qms_documents  import bp as qms_documents_bp
from pharmagpt.routes.qms_deviations import bp as qms_deviations_bp
from pharmagpt.routes.qms_capa       import bp as qms_capa_bp
from pharmagpt.routes.qms_change_control import bp as qms_change_control_bp
from pharmagpt.routes.equipment       import bp as equipment_bp


# ── Application setup ─────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key                  = FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

# The session cookie now doubles as a secondary auth channel (see
# auth/middleware.py) for requests that can't carry an Authorization header
# — e.g. the DOCX export download navigation. HttpOnly keeps it unreadable
# to page JS (an improvement over the bearer token, which already sits in
# localStorage); SameSite=Lax still allows it on the same-origin top-level
# navigation a download link performs; Secure is enabled outside debug mode
# so it's never sent over plain HTTP in production.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"]   = not FLASK_DEBUG

db.init_db()

register_auth_middleware(app)


# ── Blueprint registration ────────────────────────────────────────────────────

app.register_blueprint(auth_bp)
app.register_blueprint(projects_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(validation_bp)
app.register_blueprint(kb_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(risk_bp)
app.register_blueprint(urs_bp)
app.register_blueprint(qual_bp)
app.register_blueprint(report_bp)
app.register_blueprint(qms_common_bp)
app.register_blueprint(qms_documents_bp)
app.register_blueprint(qms_deviations_bp)
app.register_blueprint(qms_capa_bp)
app.register_blueprint(qms_change_control_bp)
app.register_blueprint(equipment_bp)


# ── SPA shell ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the single-page application shell. Assign a session ID to new visitors."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return render_template("index.html")


# ── Health check ──────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    """Unauthenticated liveness endpoint for deployment/uptime checks."""
    return jsonify({"status": "ok"})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
