import os
import asyncio
import threading
import logging
from typing import Dict, List
from .db import BidTaskResultsRegistry, BidTaskRegistryDB, BidRegistryDB
from .events import EventsPusher
from .schema import BidTasksDB, BidTaskResults, Bid

from .dsl_executor import new_dsl_workflow_executor, parse_dsl_output


class BidsEvaluator:
    def __init__(self, bid_task_id: str):
        self.bid_task_id = bid_task_id
        self.bid_task = None
        self.bids = []
        self.bid_task_db = BidTaskRegistryDB()
        self.bid_db = BidRegistryDB()
        self.results_registry = BidTaskResultsRegistry()
        self.events_pusher = EventsPusher(nats_url=os.getenv("NATS_URL"))

    def get_bid_data(self) -> Dict:
        try:
            bid_task = self.bid_task_db.get_bid_task(self.bid_task_id)
            if not bid_task:
                return {"success": False, "message": f"Bid task with ID '{self.bid_task_id}' does not exist."}

            bids = self.bid_db.query_bids({"bid_task_id": self.bid_task_id})
            if not bids:
                return {"success": False, "message": "No bids found for the given bid task ID."}

            self.bid_task = bid_task
            self.bids = bids
            return {"success": True, "data": (bid_task, bids)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def evaluate(self):
        try:
            # Fetch bid task and bids
            data = self.get_bid_data()
            if not data["success"]:
                raise ValueError(data["message"])

            bid_task: BidTasksDB = self.bid_task
            bids: List[Bid] = self.bids

            # Convert bids to dict for evaluation
            to_dict_bids = [bid.to_dict() for bid in bids]

            # Evaluate DSL
            workflow = new_dsl_workflow_executor(
                workflow_id=bid_task.bid_task_eval_dsl_id,
                workflows_base_uri=os.getenv("DSL_DB_URL")
            )
            eval_result = workflow.execute({
                "bid_data": bid_task.to_dict(),
                "bids": to_dict_bids
            })
            eval_output = parse_dsl_output(eval_result)

            # Post Evaluation DSL
            if bid_task.bid_task_post_evaluation_id:
                workflow = new_dsl_workflow_executor(
                    workflow_id=bid_task.bid_task_post_evaluation_id,
                    workflows_base_uri=os.getenv("DSL_DB_URL")
                )
                post_eval_result = workflow.execute({
                    "bid_data": bid_task.to_dict(),
                    "bids": to_dict_bids,
                    "eval_result": eval_output
                })
                eval_output = parse_dsl_output(post_eval_result)

            # Extract results
            winner_subjects = eval_output["output"]
            eval_op_data = eval_output["eval_result_data"]

            eval_push_data = {
                "bid_task_id": bid_task.bid_task_id,
                "bid_task_data": bid_task.to_dict(),
                "winner_subject_ids": winner_subjects,
                "eval_result_data": eval_op_data,
                "initiated_by": bid_task.bid_task_initiator_subject_id,
                "bid_task_type": bid_task.bid_task_type
            }

            # Save evaluation results
            result = BidTaskResults(
                bid_task_id=bid_task.bid_task_id,
                bid_task_data=bid_task.to_dict(),
                winner_subject_ids=winner_subjects,
                eval_result_data=eval_op_data,
                initiated_by=bid_task.bid_task_initiator_subject_id,
                bid_task_type=bid_task.bid_task_type,
            )
            self.results_registry.create_result(result)

            # Push events
            asyncio.run(self._push_events(winner_subjects,
                        bid_task.bid_task_initiator_subject_id, eval_push_data))

        except Exception as e:
            logging.error(
                f"Evaluation failed for BidTask {self.bid_task_id}: {e}")
            raise

    async def _push_events(self, winner_subjects, initiator, eval_push_data):
        try:
            for subject_id in winner_subjects + [initiator]:
                topic = f"{subject_id}_bid_events"
                await self.events_pusher.push(topic, eval_push_data)
        except Exception as e:
            logging.error(
                f"Error pushing events for BidTask {self.bid_task_id}: {e}")


