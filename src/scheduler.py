"""
Runs the agent on a repeating interval using APScheduler. This is the
"real time and scheduled batch" piece — a new cycle fires every
`interval_minutes` (default 60), and each cycle only processes emails
it hasn't seen before (see agent.py's dedupe logic), so a missed or
delayed run always catches up cleanly on the next cycle.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from src.agent import MailToSheetAgent
from src.config import Settings

logger = logging.getLogger(__name__)


def run_scheduled(settings: Settings) -> None:
    agent = MailToSheetAgent(settings)
    scheduler = BlockingScheduler()

    def job():
        try:
            agent.run_once()
        except Exception:
            logger.exception("Scheduled run failed — will retry next cycle")

    scheduler.add_job(job, "interval", minutes=settings.schedule_interval_minutes, next_run_time=None)
    logger.info("Scheduler started — running every %d minutes. First run now.", settings.schedule_interval_minutes)

    job()  # run immediately on startup, then wait for the interval
    scheduler.start()
