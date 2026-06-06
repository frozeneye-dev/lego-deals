"""
Local web server entry point.

Usage:
    python run.py

The APScheduler daily job runs in a background thread.
To prevent double-start when Flask reloader is active, we check
WERKZEUG_RUN_MAIN.
"""

import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from app import create_app
from app.scheduler import build_scheduler, start_scheduler

app = create_app()

if __name__ == "__main__":
    scheduler = build_scheduler()

    # Reloader forks the process; only start scheduler in the child
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_scheduler(scheduler, app)

    try:
        app.run(host="127.0.0.1", port=5000, debug=False)
    finally:
        if scheduler.running:
            scheduler.shutdown()
