"""Background workers for Vizion/Vizion Panel (Discord bot, health monitor,
expiration + schedule workers).

The web panel runs under gunicorn (``app:app``), so the ``if __name__ ==
"__main__"`` block in app.py never executes there and these workers never
started. This runner is started by ``omega-bot.service`` as a single process,
so the bot is not duplicated by gunicorn's multiple workers.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

import app as panel


def _schedule_loop():
    last_minute = None
    while not panel.OMEGA_HEALTH_STOP.is_set():
        try:
            current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
            if current_minute != last_minute:
                panel.check_schedules()
                last_minute = current_minute
        except Exception:
            panel.app.logger.exception("Schedule worker failed")
        time.sleep(15)


def main():
    panel.init_db()
    try:
        panel.migrate_nodes()
    except Exception:
        panel.app.logger.exception("Node migration failed during startup")
    threading.Thread(target=panel.check_expirations, name="omega-expiration-worker", daemon=True).start()
    threading.Thread(target=_schedule_loop, name="omega-schedule-worker", daemon=True).start()
    panel.omega_start_background_workers()
    print("[Vizion bot] workers started (Discord bot, health monitor, schedules, expirations)", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        panel.OMEGA_HEALTH_STOP.set()


if __name__ == "__main__":
    main()
