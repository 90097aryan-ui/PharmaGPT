"""
scripts/generate_backup_key.py — Print a fresh BACKUP_ENCRYPTION_KEY.

One-time setup helper. Prints a new Fernet key to stdout for the operator to
store in a secrets vault (or Render's env var dashboard, sync: false) and
set as BACKUP_ENCRYPTION_KEY — never committed to the repo, never written to
the backup directory itself. See docs/BACKUP_SOP.md "Key management".

Usage:
    python scripts/generate_backup_key.py
"""

from cryptography.fernet import Fernet

if __name__ == "__main__":
    key = Fernet.generate_key().decode("utf-8")
    print("Generated a new backup encryption key. Store it in your secrets")
    print("vault and set it as BACKUP_ENCRYPTION_KEY — do not commit it.\n")
    print(key)
