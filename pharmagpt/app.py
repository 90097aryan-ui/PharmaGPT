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
from flask import Flask, render_template, session

from pharmagpt.config import FLASK_SECRET_KEY, FLASK_DEBUG, FLASK_PORT, MAX_FILE_SIZE
from pharmagpt import database as db

from routes.projects       import bp as projects_bp
from routes.chat           import bp as chat_bp
from routes.docs           import bp as docs_bp
from routes.validation     import bp as validation_bp
from routes.knowledge_base import bp as kb_bp
from routes.workspace      import bp as workspace_bp
from routes.dashboard      import bp as dashboard_bp


# ── Application setup ─────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key                  = FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

db.init_db()


# ── Blueprint registration ────────────────────────────────────────────────────

app.register_blueprint(projects_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(validation_bp)
app.register_blueprint(kb_bp)
app.register_blueprint(workspace_bp)
app.register_blueprint(dashboard_bp)


# ── SPA shell ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the single-page application shell. Assign a session ID to new visitors."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return render_template("index.html")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
