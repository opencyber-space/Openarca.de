import os
import logging

from .schema import (
    SocialTaskCoreData,
    SocialChoiceSubjectSpecInput,
    SocialChoiceEvaluationInput,
    Votes
)
from .basic_crud import (
    SocialTaskCoreDataDB,
    SocialChoiceSubjectSpecInputDB,
    SocialChoiceEvaluationInputDB,
    VotesDB
)

logger = logging.getLogger("EvaluatorInitiator")
logging.basicConfig(level=logging.INFO)


class Initiator:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)
        self.subject_spec_db = SocialChoiceSubjectSpecInputDB(mongo_uri, db_name)
        self.evaluation_input_db = SocialChoiceEvaluationInputDB(mongo_uri, db_name)
        self.votes_db = VotesDB(mongo_uri, db_name)

    def load(self):
        try:
            task_id = os.getenv("SOCIAL_TASK_ID")
            if not task_id:
                raise RuntimeError("SOCIAL_TASK_ID not set in environment.")

            logger.info(f"Loading data for SOCIAL_TASK_ID: {task_id}")

            task: SocialTaskCoreData = self.task_db.get(task_id)
            if not task:
                raise Exception(f"Task not found for id: {task_id}")

            subject_spec: SocialChoiceSubjectSpecInput = self.subject_spec_db.get(task_id)
            if not subject_spec:
                raise Exception(f"Subject spec not found for task id: {task_id}")

            evaluation_input: SocialChoiceEvaluationInput = self.evaluation_input_db.get(task_id)
            if not evaluation_input:
                raise Exception(f"Evaluation input not found for task id: {task_id}")

            qualified_votes: list[Votes] = [
                vote for vote in self.votes_db.list_by_task(task_id) if vote.qualified
            ]

            logger.info(f"Fetched {len(qualified_votes)} qualified votes for evaluation.")

            return task, subject_spec, evaluation_input, qualified_votes
        except Exception as e:
            raise e
