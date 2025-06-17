import logging
import uuid
from typing import Dict, Tuple
from datetime import datetime
from .schema import (
    SocialTaskCoreData,
    SocialChoiceSubjectSpecInput,
    SocialChoiceEvaluationInput
)

from .basic_crud import (
    SocialChoiceEvaluationInputDB,
    SocialChoiceSubjectSpecInputDB,
    SocialTaskCoreDataDB
)

logger = logging.getLogger("SubmissionParser")


class SubmissionValidationError(Exception):
    pass


class SubmissionParser:
    @staticmethod
    def parse_datetime(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except Exception as e:
            raise SubmissionValidationError(f"Invalid datetime: {value}") from e

    @staticmethod
    def validate_and_parse(payload: Dict) -> Tuple[SocialTaskCoreData, SocialChoiceSubjectSpecInput, SocialChoiceEvaluationInput]:
        required_keys = {"social_task", "subject_spec", "evaluation_spec"}
        if not all(k in payload for k in required_keys):
            raise SubmissionValidationError(f"Missing keys in payload. Required: {required_keys}")

        task_id = f"task_{uuid.uuid4().hex[:8]}"  # generate a unique ID

        # Parse task core
        task_raw = payload["social_task"]
        creation_time = SubmissionParser.parse_datetime(task_raw["creation_time"])
        scheduled_time = SubmissionParser.parse_datetime(task_raw["scheduled_time"]) if task_raw.get("scheduled_time") else None

        task = SocialTaskCoreData(
            social_task_id=task_id,
            created_by_subject_id=task_raw["created_by_subject_id"],
            created_by_subject_data=task_raw["created_by_subject_data"],
            org_ids=task_raw["org_ids"],
            social_task_access_type=task_raw["access_type"],
            goal_data=task_raw["goal"],
            social_tasks_topics=task_raw["topics"],
            social_task_properties=task_raw["properties"],
            creation_time=creation_time,
            scheduled_time=scheduled_time,
            duration=task_raw.get("duration"),
            status=task_raw.get("status"),
            report_json=task_raw.get("report", {}),
            job_id=None,
            enable_live_streaming=task_raw.get("enable_live_streaming", False)
        )

        # Parse subject spec
        subject_raw = payload["subject_spec"]
        subject = SocialChoiceSubjectSpecInput(
            social_task_id=task_id,
            topic_title=subject_raw["title"],
            topic_description=subject_raw["description"],
            voting_options_map=subject_raw["voting_options"],
            voting_option_metadata_map=subject_raw["voting_metadata"],
            supported_protocols=subject_raw["supported_protocols"],
            voting_message_request_creator_dsl=subject_raw["voting_request_dsl"]
        )

        # Parse evaluation spec
        eval_raw = payload["evaluation_spec"]
        evaluation = SocialChoiceEvaluationInput(
            social_task_id=task_id,
            constraints_entry_id=eval_raw["constraints_primary"],
            constraints_entry_id_1=eval_raw["constraints_secondary"],
            voting_pqt_dsl=eval_raw["voting_pqt_dsl"],
            choice_evaluation_dsl=eval_raw["evaluation_dsl"],
            tie_breaker_dsl=eval_raw["tie_breaker_dsl"],
            post_awarding_dsl=eval_raw["post_award_dsl"]
        )

        logger.info(f"Parsed submission with task_id: {task_id}")
        return task, subject, evaluation



class SocialTaskController:
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "voting_db"):
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)
        self.subject_spec_db = SocialChoiceSubjectSpecInputDB(mongo_uri, db_name)
        self.evaluation_input_db = SocialChoiceEvaluationInputDB(mongo_uri, db_name)

    def create_social_choice_task(self, payload: Dict) -> str:
        try:
            logger.info("Received request to create social choice task.")
            task: SocialTaskCoreData
            subject_spec: SocialChoiceSubjectSpecInput
            evaluation: SocialChoiceEvaluationInput

            task, subject_spec, evaluation = SubmissionParser.validate_and_parse(payload)

            # Store entries in their respective collections
            logger.info(f"Inserting social_task_id: {task.social_task_id} into DB.")
            self.task_db.create(task)
            self.subject_spec_db.create(subject_spec)
            self.evaluation_input_db.create(evaluation)

            logger.info(f"Task created successfully with ID: {task.social_task_id}")
            return task.social_task_id

        except SubmissionValidationError as e:
            logger.error(f"Validation failed: {str(e)}")
            raise e
        except Exception as e:
            logger.exception("Failed to create social choice task.")
            raise e
