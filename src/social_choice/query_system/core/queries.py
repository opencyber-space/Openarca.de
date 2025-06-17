import logging
from typing import Any, Dict, List

from .basic_crud import (
    SocialTaskCoreDataDB,
    SocialChoiceSubjectSpecInputDB,
    SocialChoiceEvaluationInputDB,
    VotesDB
)

logger = logging.getLogger("QueriesManager")
logging.basicConfig(level=logging.INFO)


class QueriesManager:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)
        self.spec_db = SocialChoiceSubjectSpecInputDB(mongo_uri, db_name)
        self.eval_db = SocialChoiceEvaluationInputDB(mongo_uri, db_name)
        self.votes_db = VotesDB(mongo_uri, db_name)

        self.collections = {
            "social_task_core_data": self.task_db,
            "social_choice_subject_spec": self.spec_db,
            "social_choice_evaluation_input": self.eval_db,
            "votes": self.votes_db
        }

    def get_report(self, social_task_id: str) -> Dict[str, Any]:
        try:
            task = self.task_db.get(social_task_id)
            if not task:
                raise ValueError("Task not found.")
            return task.report_json
        except Exception as e:
            logger.exception("Failed to fetch report.")
            raise Exception(f"Error fetching report: {str(e)}")

    def generic_query(self, collection_name: str, filters: dict) -> List[dict]:
        try:
            if collection_name not in self.collections:
                raise ValueError(f"Unsupported collection: {collection_name}")

            db_obj = self.collections[collection_name]
            entries = db_obj.collection.find(filters)
            return [entry for entry in entries]
        except Exception as e:
            logger.exception("Generic query failed.")
            raise Exception(f"Error during query: {str(e)}")

    def get_status(self, social_task_id: str) -> str:
        try:
            task = self.task_db.get(social_task_id)
            if not task:
                raise ValueError("Task not found.")
            return task.status
        except Exception as e:
            logger.exception("Failed to get task status.")
            raise Exception(f"Error fetching status: {str(e)}")

    def get_full_task_bundle(self, social_task_id: str) -> Dict[str, Any]:
        try:
            task = self.task_db.get(social_task_id)
            spec = self.spec_db.get(social_task_id)
            eval_input = self.eval_db.get(social_task_id)
            votes = self.votes_db.list_by_task(social_task_id)

            if not all([task, spec, eval_input]):
                raise ValueError("Incomplete task data found.")

            return {
                "task": task.to_dict(),
                "subject_spec": spec.to_dict(),
                "evaluation_input": eval_input.to_dict(),
                "votes": [v.to_dict() for v in votes]
            }

        except Exception as e:
            logger.exception("Failed to fetch task bundle.")
            raise Exception(f"Error fetching full task data: {str(e)}")

    def is_live_streaming_enabled(self, social_task_id: str) -> bool:
        try:
            task = self.task_db.get(social_task_id)
            if not task:
                raise ValueError("Task not found.")
            return bool(task.enable_live_streaming)
        except Exception as e:
            logger.exception("Failed to check live streaming flag.")
            raise Exception(f"Error checking live streaming flag: {str(e)}")
