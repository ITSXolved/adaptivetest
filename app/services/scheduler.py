# app/services/scheduler.py - Background task scheduler
import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class SessionCleanupScheduler:
    """Background scheduler for cleaning up inactive sessions"""

    def __init__(self, redis_service, interval_minutes=10, inactivity_threshold=30):
        """
        Initialize the scheduler

        Args:
            redis_service: RedisService instance
            interval_minutes: How often to run cleanup (default: 10 minutes)
            inactivity_threshold: Minutes of inactivity before session is removed (default: 30)
        """
        self.redis_service = redis_service
        self.interval_seconds = interval_minutes * 60
        self.inactivity_threshold = inactivity_threshold
        self.running = False
        self.thread = None

    def start(self):
        """Start the background cleanup scheduler"""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_cleanup_loop, daemon=True)
        self.thread.start()
        logger.info(f"Session cleanup scheduler started (interval: {self.interval_seconds}s, threshold: {self.inactivity_threshold}min)")

    def stop(self):
        """Stop the background cleanup scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Session cleanup scheduler stopped")

    def _run_cleanup_loop(self):
        """Main loop for periodic cleanup"""
        while self.running:
            try:
                logger.info("Running scheduled session cleanup...")
                cleanup_count = self.redis_service.cleanup_inactive_sessions(self.inactivity_threshold)
                logger.info(f"Scheduled cleanup completed: {cleanup_count} sessions removed at {datetime.now().isoformat()}")
            except Exception as e:
                logger.error(f"Error during scheduled cleanup: {str(e)}")

            # Sleep in small intervals to allow quick shutdown
            for _ in range(self.interval_seconds):
                if not self.running:
                    break
                time.sleep(1)
