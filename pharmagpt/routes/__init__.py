# routes/ — Flask Blueprint package for PharmaGPT route handlers.
#
# Each module registers one Blueprint that covers a single logical area:
#   projects.py      — project CRUD, message history, conversation clear
#   chat.py          — SSE streaming chat (/stream)
#   docs.py          — document upload, view, download, delete, insights
#   validation.py    — validation document generation, export, save
#   knowledge_base.py — Knowledge Base management
#   workspace.py     — Validation Workspace projects + audit trail
#   dashboard.py     — Home Dashboard statistics
