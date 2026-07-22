web: gunicorn pharmagpt.app:app --bind 0.0.0.0:$PORT --worker-class=gthread --workers=2 --threads=4 --timeout=60 --worker-tmp-dir /dev/shm --keep-alive=5
