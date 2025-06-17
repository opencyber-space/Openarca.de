import logging
from typing import Tuple
import os
import datetime
from dsl_executor import new_dsl_workflow_executor, parse_dsl_output

from .schema import Votes
from .basic_crud import VotesDB, SocialTaskCoreDataDB, SocialChoiceEvaluationInputDB, SocialChoiceSubjectSpecInputDB
from .votes_initiator import VotingEvaluationInitiator

logger = logging.getLogger("VotingInitialChecker")
logging.basicConfig(level=logging.INFO)


class VotingInitialChecker:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.votes_db = VotesDB(mongo_uri, db_name)
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)

    def validate_vote(self, vote: Votes) -> Tuple[bool, str]:

        logger.info(
            f"Validating vote for task: {vote.social_task_id}, subject: {vote.submitter_subject_id}")

        # 1. Check for duplicate vote
        existing_votes = self.votes_db.list_by_task(vote.social_task_id)
        for v in existing_votes:
            if v.submitter_subject_id == vote.submitter_subject_id:
                logger.warning("Duplicate vote detected.")
                return False, "Vote already submitted for this task."

        # 2. Fetch task
        task = self.task_db.get(vote.social_task_id)
        if not task:
            logger.error(f"Task {vote.social_task_id} not found.")
            return False, "Invalid social_task_id."

        # 3. Check if task has started
        if task.status != "started":
            logger.warning(
                f"Task {vote.social_task_id} is not started. Current status: {task.status}")
            return False, "Voting task is not active yet."

        # 4. If private, check if subject is allowed
        if task.social_task_access_type == "private":
            if vote.submitter_subject_id not in task.org_ids:
                logger.warning(
                    "Subject not authorized to vote in private task.")
                return False, "You are not authorized to vote in this private task."

        logger.info("Vote passed initial validation.")
        return True, ""


class VoteAcceptor:
    def __init__(self, mongo_uri="mongodb://localhost:27017", db_name="voting_db"):
        self.votes_db = VotesDB(mongo_uri, db_name)
        self.task_db = SocialTaskCoreDataDB(mongo_uri, db_name)
        self.subject_spec_db = SocialChoiceSubjectSpecInputDB(
            mongo_uri, db_name)
        self.evaluation_db = SocialChoiceEvaluationInputDB(mongo_uri, db_name)
        self.checker = VotingInitialChecker(mongo_uri, db_name)

    def accept_vote(self, vote: Votes) -> bool:
        logger.info(
            f"Processing vote from subject {vote.submitter_subject_id} for task {vote.social_task_id}")

        # Step 1: Initial validations
        valid, msg = self.checker.validate_vote(vote)
        if not valid:
            logger.warning(f"Vote rejected: {msg}")
            raise Exception(f"Vote rejected: {msg}")

        # Step 2: Load task, spec, and evaluation data
        task = self.task_db.get(vote.social_task_id)
        subject_spec = self.subject_spec_db.get(vote.social_task_id)
        evaluation = self.evaluation_db.get(vote.social_task_id)

        if not (task and subject_spec and evaluation):
            logger.error("Missing task or spec or evaluation input.")
            raise Exception("Voting task configuration is incomplete.")

        if not evaluation.voting_pqt_dsl:
            logger.error("Missing voting_pqt_dsl field in evaluation input.")
            raise Exception("Voting PQT DSL is not defined.")

        # Step 3: Execute PQT DSL
        try:
            logger.info(f"Executing PQT DSL: {evaluation.voting_pqt_dsl}")
            executor = new_dsl_workflow_executor(
                workflow_id=evaluation.voting_pqt_dsl,
                workflows_base_uri=os.getenv(
                    "WORKFLOWS_API_URL", "http://localhost:5001"),
                is_remote=False,
                addons={"submitter_subject_id": vote.submitter_subject_id}
            )

            input_data = {
                "user_input": {
                    "task": task.to_dict(),
                    "subject_spec": subject_spec.to_dict(),
                    "evaluation_spec": evaluation.to_dict(),
                    "vote_data": vote.vote_data
                }
            }

            raw_output = executor.execute(input_data)
            result = parse_dsl_output(raw_output)
            qualified = bool(result.get("qualified", False))
            logger.info(f"DSL PQT output: {result}")

            initiator = VotingEvaluationInitiator()
            initiator.launch_evaluation_job(vote.social_task_id)

        except Exception as e:
            logger.warning(f"DSL PQT execution failed: {str(e)}")
            qualified = False  # Fail-safe: disqualify on failure

        vote.submission_time = datetime.utcnow()
        vote.qualified = qualified
        self.votes_db.create(vote)
        logger.info(f"Vote saved with qualified = {qualified}")

        return qualified
