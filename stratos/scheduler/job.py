# stratos/scheduler/job.py
"""
Scheduler for automatic weekly intelligence runs.
Uses APScheduler for cron-like scheduling.
"""
import datetime
import logging
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from stratos.agents.orchestrator import run_pipeline
from stratos.config import settings
from stratos.logging_config import get_logger

# Create logger
logger = get_logger("scheduler")


class Scheduler:
    """
    Manages scheduled runs of the intelligence pipeline.
    Runs weekly on Monday at 9:00 AM by default.
    """
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self._setup_jobs()
        self._setup_listeners()
    
    def _setup_jobs(self):
        """Configure scheduled jobs."""
        # Weekly on Monday at 9:00 AM
        self.scheduler.add_job(
            self._run_weekly,
            CronTrigger(day_of_week='mon', hour=9, minute=0),
            id='weekly_intelligence',
            replace_existing=True,
            name='Weekly Intelligence Briefing'
        )
        
        # Also run on startup for testing
        # Comment out or remove for production
        # self.scheduler.add_job(
        #     self._run_startup,
        #     trigger='date',
        #     run_date=datetime.datetime.now() + datetime.timedelta(seconds=10),
        #     id='startup_run',
        #     name='Startup Test Run'
        # )
        
        logger.info("✅ Scheduler jobs configured")
    
    def _setup_listeners(self):
        """Add listeners for job events."""
        def job_listener(event):
            if event.exception:
                logger.error(f"❌ Job failed: {event.job_id} - {event.exception}")
            else:
                logger.info(f"✅ Job completed: {event.job_id}")
        
        self.scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    
    def _run_weekly(self):
        """Weekly intelligence run."""
        logger.info("📋 Running weekly intelligence briefing...")
        try:
            run_id = asyncio.run(run_pipeline(trigger_type="scheduled"))
            if run_id:
                logger.info(f"✅ Weekly run completed: {run_id}")
            else:
                logger.error("❌ Weekly run failed")
        except Exception as e:
            logger.error(f"❌ Weekly run error: {e}", exc_info=True)
    
    def _run_startup(self):
        """Run once on startup (for testing)."""
        logger.info("🚀 Running startup test run...")
        try:
            run_id = asyncio.run(run_pipeline(trigger_type="startup"))
            if run_id:
                logger.info(f"✅ Startup run completed: {run_id}")
            else:
                logger.error("❌ Startup run failed")
        except Exception as e:
            logger.error(f"❌ Startup run error: {e}", exc_info=True)
    
    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("🚀 Scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("🛑 Scheduler shutdown")
    
    def get_jobs(self):
        """Get list of scheduled jobs."""
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
            for job in self.scheduler.get_jobs()
        ]
    
    def trigger_manual_run(self):
        """Manually trigger an immediate run (for testing)."""
        logger.info("📋 Manual run triggered...")
        try:
            run_id = asyncio.run(run_pipeline(trigger_type="manual"))
            return run_id
        except Exception as e:
            logger.error(f"❌ Manual run error: {e}", exc_info=True)
            return None