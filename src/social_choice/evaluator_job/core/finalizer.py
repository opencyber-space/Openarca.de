import logging
from typing import List, Dict
from datetime import datetime
import os
import json
from nats.aio.client import Client as NATS

from .schema import (
    SocialTaskCoreData,
    SocialChoiceSubjectSpecInput,
    SocialChoiceEvaluationInput,
    Votes
)
from .basic_crud import SocialTaskCoreDataDB

logger = logging.getLogger("VoteResultFinalizer")
logging.basicConfig(level=logging.INFO)


class VoteResultFinalizer:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)

    def finalize(self,
                 task: SocialTaskCoreData,
                 subject_spec: SocialChoiceSubjectSpecInput,
                 evaluation_input: SocialChoiceEvaluationInput,
                 votes: List[Votes],
                 winners: List[str],
                 post_award_payload: Dict,
                 dsl_outputs: Dict):
        logger.info(f"Finalizing results for task: {task.social_task_id}")

        report_json = {
            "task": task.to_dict(),
            "subject_spec": subject_spec.to_dict(),
            "evaluation_spec": evaluation_input.to_dict(),
            "votes": [v.to_dict() for v in votes],
            "winners": winners,
            "post_award_payload": post_award_payload,
            "dsl_outputs": dsl_outputs,
            "evaluated_at": datetime.utcnow().isoformat()
        }

        self.task_db.update(task.social_task_id, {
            "report_json": report_json,
            "status": "complete",
            "end_time": datetime.utcnow()
        })

        logger.info(
            f"Voting task {task.social_task_id} marked as complete and report saved.")

        return report_json


class ResultNotifier:
    def __init__(self):
        self.nats_url = os.getenv("ORG_NATS_URL", "nats://localhost:4222")

    async def notify(self, winners: List[str], task_id: str, post_award_payload: dict):
        try:
            nc = NATS()
            await nc.connect(servers=[self.nats_url])

            message = {
                "event_type": "voting_result",
                "task_id": task_id,
                "event_data": {
                    "social_task_id": task_id,
                    "winners": winners,
                    "post_award_payload": post_award_payload
                }
            }

            for subject_id in winners:
                try:
                    logger.info(
                        f"Notifying subject {subject_id} about vote result.")
                    await nc.publish(subject_id, json.dumps(message).encode())
                except Exception as e:
                    logger.warning(
                        f"Failed to notify subject {subject_id}: {str(e)}")

            await nc.drain()
            logger.info("All result notifications sent.")
        except Exception as e:
            raise e
