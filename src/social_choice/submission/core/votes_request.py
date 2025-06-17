import os
import json
import asyncio
import logging
from queue import Queue
from threading import Thread
from datetime import datetime

from nats.aio.client import Client as NATS
from dsl_executor import new_dsl_workflow_executor, parse_dsl_output

from .schema import SocialTaskCoreData
from .basic_crud import SocialTaskCoreDataDB, SocialChoiceSubjectSpecInputDB
from .scheduler import CronScheduler

logger = logging.getLogger("VotingTaskInitiator")
logging.basicConfig(level=logging.INFO)

WORKFLOWS_API_URL = os.getenv("WORKFLOWS_API_URL", "http://localhost:5001")


class VotingTaskInitiator(Thread):
    def __init__(self, task_queue: Queue, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.nats_url = os.getenv("ORG_NATS_URL", "nats://localhost:4222")
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)
        self.subject_spec_db = SocialChoiceSubjectSpecInputDB(
            mongo_uri, db_name)

    def run(self):
        logger.info("VotingTaskInitiator started.")
        while True:
            try:
                task: SocialTaskCoreData = self.task_queue.get()
                logger.info(f"Picked task from queue: {task.social_task_id}")
                asyncio.run(self.process_task(task))
            except Exception as e:
                logger.exception("Unexpected failure in task processing loop")

    async def process_task(self, task: SocialTaskCoreData):
        try:
            # Step 1: Fetch Subject Spec
            logger.info(
                f"Fetching subject spec for task {task.social_task_id}")
            subject_spec = self.subject_spec_db.get(task.social_task_id)
            if not subject_spec:
                logger.error(
                    f"No subject spec found for task {task.social_task_id}")
                return

            # Step 2: Prepare DSL Executor
            logger.info(
                f"Initializing DSL executor for task {task.social_task_id}")
            executor = new_dsl_workflow_executor(
                workflow_id=subject_spec.voting_message_request_creator_dsl,
                workflows_base_uri=WORKFLOWS_API_URL,
                is_remote=False,
                addons={"initiator_subject_id": task.created_by_subject_id}
            )

            input_data = {
                "user_input": {
                    "task": task.to_dict(),
                    "subject_spec": subject_spec.to_dict()
                }
            }

            logger.info("Executing DSL workflow")
            raw_output = executor.execute(input_data)
            dsl_output = parse_dsl_output(raw_output)

            logger.info(
                f"DSL Output Parsed for task {task.social_task_id}: {dsl_output}")

            # Step 3: Prepare and Send Invite Message via NATS
            event_payload = {
                "event_type": "voting_invite",
                "sender_subject_id": task.created_by_subject_id,
                "event_data": {
                    "dsl_output": dsl_output,
                    "voting_info": subject_spec.to_dict()
                }
            }

            logger.info(f"Connecting to NATS at {self.nats_url}")
            nc = NATS()
            await nc.connect(servers=[self.nats_url])

            for subject_id in subject_spec.voting_options_map.keys():
                try:
                    logger.info(f"Publishing to subject: {subject_id}")
                    await nc.publish(subject_id, json.dumps(event_payload).encode())
                except Exception as e:
                    logger.warning(
                        f"Failed to publish to {subject_id}: {str(e)}")

            await nc.drain()
            logger.info("All notifications sent successfully.")

            # Step 4: Update DB Status
            logger.info(
                f"Updating task {task.social_task_id} status to 'started'")
            self.task_db.update(task.social_task_id, {
                "status": "started",
                "start_time": datetime.utcnow()
            })
            logger.info(f"Task {task.social_task_id} marked as started.")

        except Exception as e:
            logger.exception(
                f"Failed to process task {task.social_task_id}: {str(e)}")



def start_voting_tasks_scheduler(mongo_uri="mongodb://localhost:27017", db_name="voting_db"):


    logger.info("Starting Voting Tasks Scheduler System...")

    task_queue = Queue()

    # Initialize components
    scheduler = CronScheduler(task_queue, mongo_uri=mongo_uri, db_name=db_name)
    initiator = VotingTaskInitiator(task_queue, mongo_uri=mongo_uri, db_name=db_name)

    # Start both threads
    scheduler.start()
    initiator.start()

    logger.info("VotingTasksScheduler: All background threads started successfully.")
    return task_queue