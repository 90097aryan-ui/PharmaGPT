import os
from dotenv import load_dotenv

# Load the .env file from the project root (one level up from this file)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Gemini model to use across the entire application
GEMINI_MODEL = "gemini-2.5-flash"

# API key loaded from .env
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Flask secret key — used to sign session cookies
# In production, replace this with a long random string stored in .env
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "pharmagpt-dev-secret-key")

# Flask debug mode — set to False in production
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"

# Port the Flask app will run on
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))

# ── Document upload settings ──────────────────────────────────────────────────

# Folder where uploaded files are stored, organised as uploads/{project_id}/
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")

# Maximum upload size in bytes (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# File types users are allowed to upload
ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "txt"}
