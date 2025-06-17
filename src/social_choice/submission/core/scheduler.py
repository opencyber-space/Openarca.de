import time
import logging
from queue import Queue
from threading import Thread
from datetime import datetime
from typing import List

from .schema import SocialTaskCoreData
from .basic_crud import SocialTaskCoreDataDB

logger = logging.getLogger("CronScheduler")
logging.basicConfig(level=logging.INFO)


class CronScheduler(Thread):
    def __init__(self, task_queue: Queue, poll_interval: int = 60, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.poll_interval = poll_interval
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)
        self.pending_tasks: List[SocialTaskCoreData] = []

    def run(self):
        logger.info("CronScheduler started.")
        while True:
            try:
                self.refresh_pending_tasks()
                self.dispatch_ready_tasks()
            except Exception as e:
                logger.exception("Exception in cron scheduler loop: %s", str(e))
            time.sleep(self.poll_interval)

    def refresh_pending_tasks(self):
        try:
            logger.info("Refreshing pending tasks from DB.")
            now = datetime.utcnow()
            self.pending_tasks = [
                task for task in self.task_db.list_all()
                if task.status == "scheduled" and task.scheduled_time and task.scheduled_time <= now
            ]
            logger.info(f"Found {len(self.pending_tasks)} pending tasks ready to be dispatched.")
        except Exception as e:
            logger.exception("Failed to refresh pending tasks: %s", str(e))

    def dispatch_ready_tasks(self):
        now = datetime.utcnow()
        to_dispatch = [task for task in self.pending_tasks if task.scheduled_time <= now]

        for task in to_dispatch:
            try:
                logger.info(f"Dispatching task {task.social_task_id} scheduled at {task.scheduled_time}")
                self.task_queue.put(task)
                self.pending_tasks.remove(task)
            except Exception as e:
                logger.exception(f"Failed to dispatch task {task.social_task_id}: %s", str(e))
