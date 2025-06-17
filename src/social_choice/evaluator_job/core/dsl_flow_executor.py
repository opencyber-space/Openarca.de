import os
import logging
from typing import List, Dict, Union

from .schema import SocialTaskCoreData, SocialChoiceSubjectSpecInput, SocialChoiceEvaluationInput, Votes
from dsl_executor import new_dsl_workflow_executor, parse_dsl_output

logger = logging.getLogger("DSLEvaluator")
logging.basicConfig(level=logging.INFO)


class DSLEvaluator:
    def __init__(self):
        self.dsl_host = os.getenv("WORKFLOWS_API_URL", "http://localhost:5001")

    def _build_executor(self, workflow_id: str, addons: Dict = None):
        return new_dsl_workflow_executor(
            workflow_id=workflow_id,
            workflows_base_uri=self.dsl_host,
            is_remote=False,
            addons=addons or {}
        )

    def _build_input(self, task, subject_spec, evaluation_input, votes, extra={}):
        return {
            "user_input": {
                "task": task.to_dict(),
                "subject_spec": subject_spec.to_dict(),
                "evaluation_spec": evaluation_input.to_dict(),
                "votes": [v.to_dict() for v in votes],
                **extra
            }
        }

    def evaluate(
        self,
        task: SocialTaskCoreData,
        subject_spec: SocialChoiceSubjectSpecInput,
        evaluation_input: SocialChoiceEvaluationInput,
        votes: List[Votes]
    ) -> Dict:
        dsl_outputs = {}

        logger.info(
            f"Running choice evaluation DSL: {evaluation_input.choice_evaluation_dsl}")
        evaluation_executor = self._build_executor(
            workflow_id=evaluation_input.choice_evaluation_dsl,
            addons={"social_task_id": task.social_task_id}
        )
        input_data = self._build_input(task, subject_spec, evaluation_input, votes)

        try:
            output = evaluation_executor.execute(input_data)
            result = parse_dsl_output(output)
            dsl_outputs["choice_evaluation_dsl"] = result
        except Exception as e:
            logger.exception("Choice evaluation DSL execution failed.")
            raise

        logger.info(f"Choice evaluation result: {result}")

        # Determine winner(s)
        if "winner" in result:
            winners = [result["winner"]]
        elif "winners" in result:
            winners = result["winners"]
        else:
            raise Exception(
                "Choice evaluation DSL must return 'winner' or 'winners'")

        # Tie breaker if needed
        if len(winners) > 1 and evaluation_input.tie_breaker_dsl:
            logger.info("Running tie-breaker DSL")
            tie_breaker_executor = self._build_executor(
                workflow_id=evaluation_input.tie_breaker_dsl,
                addons={"social_task_id": task.social_task_id}
            )
            input_data = self._build_input(
                task, subject_spec, evaluation_input, votes,
                extra={"winners": winners}
            )
            try:
                output = tie_breaker_executor.execute(input_data)
                result = parse_dsl_output(output)
                dsl_outputs["tie_breaker_dsl"] = result

                if "winner" in result:
                    winners = [result["winner"]]
                elif "winners" in result:
                    winners = result["winners"]
                else:
                    raise Exception(
                        "Tie-breaker DSL must return 'winner' or 'winners'")
            except Exception as e:
                logger.exception("Tie-breaker DSL execution failed.")
                raise

        logger.info(f"Final winner(s): {winners}")

        # Run post-award DSL
        logger.info("Running post-awarding DSL")
        post_award_executor = self._build_executor(
            workflow_id=evaluation_input.post_awarding_dsl,
            addons={"social_task_id": task.social_task_id}
        )
        input_data = self._build_input(
            task, subject_spec, evaluation_input, votes,
            extra={"winners": winners}
        )
        try:
            post_output = post_award_executor.execute(input_data)
            post_result = parse_dsl_output(post_output)
            dsl_outputs["post_awarding_dsl"] = post_result
            logger.info("Post-awarding DSL completed.")
        except Exception as e:
            logger.exception("Post-awarding DSL execution failed.")
            raise

        return {
            "winners": winners,
            "post_award_payload": post_result,
            "dsl_outputs": dsl_outputs
        }
